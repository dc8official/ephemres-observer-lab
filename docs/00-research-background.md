# 00 Research background: origin, theory and hypotheses

**Principal investigator:** Kenneth Nnorom, network security engineer and systems researcher  
(kennethnnorom.com · linkedin.com/in/kennethnnorom)  
**Parent project:** Ephemres (formerly LNMP, the Lightweight Network Monitoring Platform)

This page covers why the lab exists: the gap I noticed in the field, the theory and published work behind it, and the hypotheses the lab tests. What was built is in [01 Project scope](01-project-scope.md), and how the measurements are taken is in [02 Test methodology](02-test-methodology.md). Terms are defined in the [glossary](../README.md#glossary).

---

## 1. Where this started

### Terminal ping and Ephemres disagreed
This lab began with a small discrepancy I couldn't explain. On a deployed Ephemres Linux host, I ran ordinary command-line `ping` against the targets Ephemres was monitoring. The round-trip times (RTTs) were steady and low. Ephemres, running on the same machine, reported something slightly different: a small, regular offset above the terminal `ping`, periodic tail spikes (p95 and p99, the slowest 5 % and 1 % of packets) and more jitter (the variation from one packet to the next).

Same host, two different answers. From the outside I couldn't tell which of two explanations was true: either the network only slowed down when Ephemres probed it, or Ephemres was adding its own delay to the measurements it recorded.

### Built for one core: the GNS3 environment
Ephemres was first built to run reliably on a **single-core, low-spec machine**. Early design and testing happened inside a **GNS3 simulated network**, on virtualised Debian and Ubuntu machines with one CPU core (1 vCPU).

Virtualised nodes in GNS3 share the host's CPU under tight limits, so keeping the monitor fast on a single core was a hard constraint from the start. As Ephemres grew, I needed to know how multi-core CPUs change the picture for each runtime, without giving up single-core performance.

### What Ephemres already does right (and the 4 to 15 semaphore change)
Before blaming the runtime, I audited the Ephemres engine code (`monitoring/engine.py`, `monitoring/ping.py`, `monitoring/state_machine.py`). It already avoids the obvious sources of self-interference:

1. **Process isolation.** The probing engine runs as its own service, separate from the web API workers.
2. **Measure first, save later.** Each endpoint cycle is 5 pings sent 8 s apart, which takes about 32 s, or 42 s in the worst case where pings time out. Database writes happen only after all 5 pings finish, in the spare time before the endpoint's next 60 s slot.
3. **Deterministic staggering.** Each endpoint gets its own start second (0 to 59), derived from its UUID, so endpoints don't all start together.
4. **Capped concurrency (the 4 to 15 semaphore change).** Post-cycle database writes pass through an asynchronous semaphore (`db_write_semaphore`) that limits how many run at once. Early versions of Ephemres set it to **4**. As the monitored deployment grew, it was raised to the current **15**, on the expectation that letting writes clear faster would leave fewer endpoints queued behind them and so **improve ICMP measurement accuracy**. Readings did improve after that release. This lab later found that under the 60 s stagger the cap is almost never reached, so the semaphore change is unlikely to be the cause ([10 Results analysis](10-results-analysis.md) §R2.1). Other improvements to the Ephemres code are the more likely explanation, though the lab didn't test them.
5. **Lean receive path.** One raw ICMP socket, watched by `loop.add_reader()`, reads packets into a preallocated 1500-byte buffer (`recvfrom_into`) and stamps `time.monotonic_ns()` straight away.
6. **Cycle aggregation.** Five pings collapse into one summary database insert per cycle.

### What's left: endpoints share one event loop
Even with those six measures in place, every endpoint still shares **one Python `asyncio` event-loop thread**, so one task's synchronous CPU work can hold up every other task.

At 100 endpoints on a 60 s cycle:
- on average **53.3 endpoints** are in the middle of probing at any moment (`100 × 32 s / 60 s`);
- **1.67 endpoints per second** (`100 / 60`) are finishing a cycle and doing synchronous post-cycle work: evaluating their state machine, building ORM objects and serialising SQL parameters.

While endpoint A does that CPU-bound work (or the runtime pauses to manage memory), the event loop can't react when endpoint B's echo reply arrives. B's packet waits in the operating system's socket receive queue. Ephemres stamps the arrival time in user space *after* reading the socket, so B's RTT is charged with the CPU time spent on A.

### Test before rewriting
My early reading pointed at Python's single-threaded `asyncio` event loop and CPython's cyclic garbage collector (GC) as likely causes of the delay. Compiled languages with similar asynchronous models, **Go `goroutines`** and **Rust `tokio`** in particular, are often credited with better concurrency and lower tail latency, especially on multi-core CPUs.

But Python already worked well in Ephemres. Replacing a working Python codebase with Go or Rust on a hunch would have been bad engineering. Before touching production code, I needed to measure the problem directly:
- How large is the internal observer effect in Python `asyncio` under Ephemres's real probing schedule?
- Did raising the semaphore from 4 to 15 actually improve accuracy, and what happens at 5, 15, 30 or 50?
- How do Go (`goroutines`) and Rust (`tokio`) compare with the current Python (`asyncio`) engine under the same load, both on a **single core** (the original GNS3 1-vCPU constraint) and on **multi-core CPUs**?
- Does moving Python's CPU work into a multi-core `ProcessPoolExecutor` solve the problem without switching languages?
- What do the results mean in practice for Ephemres, and for any monitoring platform built the same way, when weighing schedule design, hardware scaling and runtime (Python, Go or Rust)?

I built this standalone lab (`ephemres-observer-lab`) to isolate and measure those effects across operating-system layers, concurrency models and language runtimes.

---

## 2. Two different observer effects

The experiments separate two effects that are easy to confuse:

| | Internal observer effect | External observer effect |
|---|---|---|
| **Cause** | the monitor's own CPU work delays *when it reads* a reply | the monitor's probe load changes *what is being measured* |
| **What is distorted** | the program's reading (the packet's true RTT is unchanged) | the network's or target's behaviour (queues, rate limits, loss) |
| **Visible as** | observer lag: Clock B − Clock A | a change in kernel RTT and in packet loss |
| **Triggered by** | ORM work blocking the loop; bursts of writes released by the semaphore | firing many endpoints at once (burst) |
| **Usual remedy** | a different concurrency model, offloading, smaller bursts | staggering the schedule |

The kernel timestamp (Clock A) is what lets the lab tell them apart. The program's own busyness can't affect it, so any change in kernel RTT belongs to the external effect, and the gap `Clock B − Clock A` isolates the internal one.

---

## 3. Theory and published work

The idea that observing a system disturbs it turns up in physics and in computer-systems engineering alike. I've split the literature into a **core** set, which directly explains host-side timestamp distortion, event-loop blocking and runtime garbage collection, and an **adjacent** set that gives broader context for further studies.

### A. Core literature: the measuring host and asynchronous runtimes

#### 1. The measuring host as a source of error
* **Kernel timestamping and host delay across a fleet.** Willem de Bruijn (2023) showed how user-space timing can blame the physical network for delays that happen inside the host's own software stack, and how Linux `SO_TIMESTAMPING` separates NIC receive, kernel receive and application receive. He also left an open question: *"How much do measurements perturb the measured system?"*
* **Precision active probing without dedicated hardware.** Pásztor and Veitch (2001, 2002) showed that user-space active probers on standard Unix suffer from "system noise on the time the clocks are read", caused by interrupts, context switches and scheduling delays, and that this distorts the RTT and jitter they report.
* **A probe's own load inflates its RTTs.** Holterbach et al. (2015) showed that on RIPE Atlas, a global network of measurement probes, measurements running from and towards the same probe interfere with each other. The probe's CPU load inflates the RTTs it reports (less so on probes with a faster CPU) and can delay scheduled measurements. It's the closest published evidence I found of a monitor distorting its own readings.
* **User-space versus kernel delay.** Li et al. (2018) took apart the RTT inflation in smartphone measurement apps (Speedtest, MobiPerf) layer by layer. They found it in both user space (mostly the managed runtime) and the kernel (sleeping driver functions), and a native app kept the user-space part under 1.5 ms. Their method, splitting one RTT by where the time goes, is the one this lab applies to a monitoring engine.
* **Active SLA probing and schedule distortion.** Sommers et al. (2005, 2007) showed that active SLA monitors (measuring delay, loss and RFC 3550 jitter) distort the network when their probes bunch into bursts. That work is the starting point for asking how the shape of a schedule, burst or staggered, affects measurement accuracy.

#### 2. Event-loop blocking, GC pauses and runtime schedulers
When hundreds of probing tasks share one runtime, synchronous CPU work, memory management and thread scheduling all delay when the application can read arriving packets:
* **Tail latency in shared runtimes.** Dean and Barroso (2013, *The Tail at Scale*) described how background activity, GC pauses and queueing behind synchronous tasks amplify 95th and 99th percentile latency in networked systems. On a single-threaded event loop, any pause blocks every concurrent I/O reader behind it.
* **CPython `asyncio` and cyclic GC pauses.** Pablo Galindo Salgado (PyCon 2019) explained how CPython adds a generational cyclic garbage collector (`gc`) on top of reference counting. When a generation's threshold is exceeded, CPython stops the interpreter to walk tracked container objects (`PyGC_Head`) and break reference cycles, which freezes the `asyncio` event loop until the collection finishes.
* **GC overhead in production Python.** Wu and Ni at Instagram Engineering (2017, *Dismissing Python Garbage Collection at Instagram*) described how CPython's cyclic GC caused latency spikes, CPU cache churn and copy-on-write page faults in their Python workers. They disabled cyclic GC entirely, and report steadier response times and 10 % more throughput.
* **Go's concurrent GC versus Rust without one.** Nowack at Discord Engineering (2020, *Why Discord is Switching from Go to Rust*) compared Go and Rust in a latency-critical production service. Even with Go's concurrent collector, the forced GC pass (at least every 2 minutes) scanned a large object graph and caused recurring millisecond spikes. Discord reports that the Rust rewrite, which manages memory through compile-time ownership with no runtime collector, removed those spikes.
* **Goroutine preemption and scheduler starvation.** Clements (2019) set out the design of Go's goroutine preemption model, including how tight CPU-bound loops delay runnable and timer-woken goroutines until a preemption point is reached. That is directly relevant to the single-core Go behaviour this lab measured.

#### 3. Standards and kernel timestamping interfaces
* **RFC 3550 §6.4.1, smoothed inter-arrival jitter.** The standard jitter formula uses `D(i, j) = (R_j − S_j) − (R_i − S_i)`, the change in transit time between two packets:
  ```text
  J(i) = J(i-1) + ( |D(i-1,i)| − J(i-1) ) / 16
  ```
  Any observer delay on a receive timestamp `R_j` inflates `|D|`, and through the running average it contaminates the jitter of the packets that follow. That's why the lab reports jitter twice: once from the kernel timestamps and once from the observer's.
* **Linux kernel timestamping (`SO_TIMESTAMPNS`, `SO_TIMESTAMPING`).** The kernel records a packet's arrival time and hands it to the program as ancillary data (`cmsg`) with `recvmsg()`, before any user-space scheduling happens. Network cards that support IEEE 1588 (the Precision Time Protocol) can also stamp packets in hardware (`SOF_TIMESTAMPING_RAW_HARDWARE`), and the lab can record those as a cross-check.
* **Wire time versus host time.** The IETF's delay metrics distinguish the moment a packet arrives on the wire from the moment a host records it, and list the difference as a measurement error (RFC 2330 §10.2; RFC 7679 §3.7.2). Clock A and Clock B make that difference measurable on every packet.

---

### B. Adjacent literature for extended studies

These works span physics, benchmarking, hardware packet generation and wide-area measurement. Only parts of them apply directly to asynchronous ICMP monitoring on one host, but they give useful context and vocabulary for anyone taking the work further:

* **Physical analogies (conceptual vocabulary):**
  * *Heisenberg's microscope (1927):* observing an electron's position more sharply disturbs its momentum more (`Δx · Δp ≥ ℏ/2`). In telemetry, observing more often injects more interrupts, context switches and memory allocations into the host pipeline. It's an analogy, not a mechanism, but it's the one the field's name comes from.
  * *Reference frames and time (Rossi and Hall, 1941):* a moving muon's elapsed time differs from the laboratory's. In a loosely similar way, a packet passes through three "frames" of time inside a host: *wire time* (serialisation on the cable), the *kernel frame* (interrupt handling, DMA and socket buffer queueing) and the *observer frame* (scheduler wake-up, the `recvmsg` syscall and the user-space clock read). A packet waiting in the kernel for a busy program has finished its physical journey, but in the program's frame it keeps "ageing".
* **Software probe effects and benchmark bias:**
  * *Probe effect:* Gait (1986) showed that adding monitoring code to concurrent programs changes their scheduling and the order of events.
  * *Measurement intrusion and perturbation:* Malony, Reed and Wijshoff (1992) modelled monitor intrusion mathematically, the formal ancestor of subtracting an idle floor. Mytkowicz et al. (2009) showed that small, non-obvious differences in runtime and memory layout bias benchmarks systematically, which is why this lab compares engines with identical packets, schedules and statistics code.
* **Hardware timestamping, traffic generators and host latency:**
  * *Kernel timestamps in ping tools:* Dreibholz (2023) added Linux and FreeBSD kernel and hardware timestamping to the HiPerConTracer ping and traceroute tool, with a survey of socket timestamping options.
  * *Where host latency comes from:* Zilberman et al. (2017) broke end-to-end latency down from the application to the wire in data-centre hosts and found no single dominant term. Host-side latency has to be measured, not assumed.
  * *Software traffic generators:* Botta, Dainotti and Pescapé (2010) showed that software traffic generators don't produce or time packets as configured. MoonGen (Emmerich et al., 2015) uses NIC hardware timestamps for sub-µs latency measurement for that reason.
  * *Real-time host jitter and C-state penalties:* low-latency benchmarking and trading-systems literature (for example HFT-Bench, 2025 [source needed]) describes how database writes, serialisation and CPU idle states (C-states) perturb user-space timestamps on the hot path.
  * *Calibrating wide-area delay measurements:* Paxson (1998) showed that clock adjustments and skew cause large errors in measured transit times even under NTP. That is the background to the lab's clock-slew threat (see [02](02-test-methodology.md)).

---

### C. What this lab adds

The work above establishes that measuring hosts add error, and shows how to timestamp around it. As far as my literature search went (October 2026), none of it does the following. That's a statement about my search, not a claim that nobody has done it:

1. **Two clocks on the same packet:** the lab captures `SO_TIMESTAMPING` (Clock A) and the application clock (Clock B) on *every* ICMP packet, over standard raw sockets, which isolates user-space delay without hardware capture cards (DAG cards) or kernel patches.
2. **Event-loop cross-talk in a multi-endpoint SLA engine:** it measures, per packet and with no cooperation from the target, how much **the monitor's own application work** (preparing database writes behind an async semaphore) delays reading replies and contaminates the in-flight measurements of *other* endpoints sharing the loop.
3. **A 6-way runtime matrix:** it compares Python `asyncio` cooperative coroutines, Go preemptive goroutines with the M:N netpoller, and Rust `tokio` work-stealing tasks, each on one core and on all cores, under the same real-network probing schedule and the same CPU work.
4. **The cost of offloading in Python:** it measures what Python's multi-core worker-process offload costs (IPC serialisation; GIL contention on the main process may be part of it, but wasn't measured separately). In these runs, moving work off the event loop did not lower user-space measurement latency.
5. **Loss by cause:** it separates **loss caused by the observer** (a reply that reached the kernel in time but was read by the application after its timeout) from true network loss.

The dashboard's default configuration reproduces the Ephemres settings: 100 endpoints, 5 pings 8 s apart, a 60 s cycle with start times spread across it, and semaphore 15. Every experiment is a stated deviation from that real system ([02 Test methodology](02-test-methodology.md) §2).

---

## 4. Hypotheses and the experiment matrix

The lab compares three runtimes under two CPU arrangements:

| Runtime | Single core (one CPU pinned) | Multi core (all CPUs) | Question |
|---|---|---|---|
| **Python (`asyncio`)** | ORM work runs inline on the event loop | ORM work offloaded to a `ProcessPoolExecutor` (separate worker processes) | Blocking a single thread (the GNS3 1-vCPU baseline), against the cost of pickling (serialising) data and inter-process communication on the loop that reads the socket |
| **Go (`goroutines`)** | `GOMAXPROCS=1` (one thread runs Go code) | `GOMAXPROCS` = all CPUs (work-stealing scheduler) | How the Go scheduler handles a mix of I/O and CPU bursts, on a single core and with spare threads |
| **Rust (`tokio`)** | `current_thread` runtime (one thread) | Multi-thread work-stealing runtime | The latency floor of compiled code without a garbage collector, on one core and when other threads can take the CPU work |

### What varies
- **Single-core versus multi-core:** single-core mode tests the original Ephemres constraint (running smoothly on a 1-vCPU GNS3 virtual machine). Multi-core mode tests how each runtime uses modern hardware.
- **Semaphore sweep (`5, 15, 30, 50`):** tests the production change that raised `db_write_semaphore` from 4 to 15 in the hope of better ICMP accuracy, and whether smaller or larger limits reduce or worsen observer lag.
- **Schedule shape (`60 s` staggered or `0 s` burst):** separates normal staggered operation from the worst case, where every reply and every write arrives at once.
- **Idle floor (`0 ms` or `3 ms` of ORM work):** measures each runtime's own wake-up and socket-read cost with no post-cycle CPU work.

### Two cautions when reading this matrix
1. **Event-loop blocking is isolated; garbage collection is not.** The literature names both synchronous event-loop blocking and cyclic GC pauses as latency sources in Python and Go. The lab's simulated 3 ms of ORM work, though, is a deterministic CPU spin that allocates almost no heap memory. Differences in the baseline corpus therefore measure **event-loop blocking and scheduler contention**, and shouldn't be blamed on garbage collection without a separate allocation-heavy experiment ([10 Results analysis](10-results-analysis.md) §Methodological Lessons #4).
2. **The multi-core modes differ by design.** In Go and Rust, multi-core worker threads share memory with the socket reader. Python's multi-core mode crosses an operating-system process boundary (`ProcessPoolExecutor`) to get around the GIL. The comparison includes that structural difference on purpose.

---

## 5. Why the database work is simulated as CPU work

An asynchronous database write has two phases:

1. **Network I/O wait.** Waiting for the database over a socket hands control back to the event loop (`await`), so it doesn't stop packets being received.
2. **CPU preparation.** Before the I/O, the application computes cycle statistics, evaluates state-machine (z-score) transitions, builds ORM or Pydantic objects and serialises SQL parameters. This is *synchronous CPU work*: nothing else on that thread can run while it happens.

`simulated_db_ms` (default 3.0 ms) models the second phase, gated by `db_write_semaphore` (default 15). A short asynchronous sleep (1 ms) then stands in for the first. A fixed CPU spin removes disk and database variation, so what's left is scheduling contention inside the application's runtime and nothing else. The price is that real ORM work allocates memory and this spin doesn't, which is the GC gap described in §4.

---

## 6. From the field to the lab

I didn't want to guess why the terminal `ping` and Ephemres disagreed, and I didn't want to rewrite the Python engine in Go or Rust before knowing. So I turned the observation into a controlled measurement that anyone can reproduce:
1. **Measurement model ([02 Test methodology](02-test-methodology.md)):** every ICMP echo reply is stamped twice on `CLOCK_REALTIME`, once by the Linux kernel on arrival (Clock A) and once by the user-space runtime when it reads the packet (Clock B), which gives the observer lag on every packet.
2. **Two-tier lab architecture ([03 Architecture](03-architecture.md) and [04 Engines](04-engines.md)):** an isolated process harness runs functionally identical Python, Go and Rust probing engines in single-core and multi-core modes.
3. **Benchmark corpus ([10 Empirical Results and Comparative Analysis](10-results-analysis.md)):** all 173 recorded runs, covering staggered and burst schedules, semaphores 5 to 50, 25 to 250 endpoints and interleaved idle floors, are analysed there and checked by script against the raw data.

What the runs settled, and what they still leave open, is in [10 Results analysis](10-results-analysis.md) under Open Questions and Next Runs.

---

## 7. References

All academic entries were checked against Crossref (DOI given), ACM or IEEE proceedings, or the RFC Editor in October 2026. Industry engineering write-ups and core developer talks are cited with their venue and year.

### Core literature: host measurement error, async runtimes and GC latency
1. W. de Bruijn, "SO_TIMESTAMPING: Powering Fleetwide RPC Monitoring", *Proc. Netdev 0x17* (2023).
2. A. Pásztor, D. Veitch, "PC Based Precision Timing Without GPS", *Proc. ACM SIGMETRICS '02*, ACM, 1-10 (2002). doi:10.1145/511334.511336
3. A. Pásztor, D. Veitch, "A Precision Infrastructure for Active Probing", *Proc. PAM 2001* (2001).
4. T. Holterbach, C. Pelsser, R. Bush, L. Vanbever, "Quantifying Interference between Measurements on the RIPE Atlas Platform", *Proc. Internet Measurement Conference (IMC)*, ACM, 437-443 (2015). doi:10.1145/2815675.2815710
5. W. Li, D. Wu, R. K. C. Chang, R. K. P. Mok, "Toward Accurate Network Delay Measurement on Android Phones", *IEEE Transactions on Mobile Computing* 17(3), 717-732 (2018). doi:10.1109/TMC.2017.2737990
6. J. Sommers, P. Barford, N. Duffield, A. Ron, "Accurate and Efficient SLA Compliance Monitoring", *Proc. ACM SIGCOMM '07*, ACM, 109-120 (2007). doi:10.1145/1282380.1282394
7. J. Sommers, P. Barford, N. Duffield, A. Ron, "Improving Accuracy in End-to-End Packet Loss Measurement", *Proc. ACM SIGCOMM '05*, ACM, 157-168 (2005). doi:10.1145/1080091.1080111
8. J. Dean, L. A. Barroso, "The Tail at Scale", *Communications of the ACM* 56(2), 74-80 (2013). doi:10.1145/2408776.2408794
9. P. Galindo Salgado, "Time to take out the rubbish: garbage collector", *PyCon US 2019*, Python Software Foundation, Cleveland, OH (2019).
10. C. Wu, M. Ni (Instagram Engineering), "Dismissing Python Garbage Collection at Instagram", *Instagram Engineering Blog*, Meta (Jan. 2017).
11. M. Nowack (Discord Engineering), "Why Discord is Switching from Go to Rust", *Discord Engineering Blog* (Feb. 2020).
12. A. Clements, "Proposal: Non-cooperative goroutine preemption", *Go Design Documents*, Go Issue #24543 (2019).

### Standards
13. V. Paxson, G. Almes, J. Mahdavi, M. Mathis, "Framework for IP Performance Metrics", RFC 2330 (1998).
14. G. Almes, S. Kalidindi, M. Zekauskas, A. Morton (ed.), "A One-Way Delay Metric for IP Performance Metrics (IPPM)", RFC 7679 / STD 81 (2016).
15. H. Schulzrinne, S. Casner, R. Frederick, V. Jacobson, "RTP: A Transport Protocol for Real-Time Applications", RFC 3550 / STD 64 (2003), §6.4.1.

### Adjacent literature for extended studies
16. W. Heisenberg, "Über den anschaulichen Inhalt der quantentheoretischen Kinematik und Mechanik", *Zeitschrift für Physik* 43(3-4), 172-198 (1927). doi:10.1007/BF01397280
17. B. Rossi, D. B. Hall, "Variation of the Rate of Decay of Mesotrons with Momentum", *Physical Review* 59(3), 223-228 (1941). doi:10.1103/PhysRev.59.223
18. J. Gait, "A Probe Effect in Concurrent Programs", *Software: Practice and Experience* 16(3), 225-233 (1986). doi:10.1002/spe.4380160304
19. A. D. Malony, D. A. Reed, H. A. G. Wijshoff, "Performance Measurement Intrusion and Perturbation Analysis", *IEEE Transactions on Parallel and Distributed Systems* 3(4), 433-450 (1992). doi:10.1109/71.149962
20. T. Mytkowicz, A. Diwan, M. Hauswirth, P. F. Sweeney, "Producing Wrong Data Without Doing Anything Obviously Wrong!", *Proc. ASPLOS XIV*, ACM, 265-276 (2009). doi:10.1145/1508244.1508275
21. T. Dreibholz, "High-Precision Round-Trip Time Measurements in the Internet with HiPerConTracer", *Proc. SoftCOM 2023*, IEEE, 1-7 (2023). doi:10.23919/SoftCOM58365.2023.10271612
22. N. Zilberman, M. Grosvenor, D. A. Popescu, N. Manihatty-Bojan, G. Antichi, M. Wójcik, A. W. Moore, "Where Has My Time Gone?", *Passive and Active Measurement (PAM 2017)*, LNCS, Springer, 201-214 (2017). doi:10.1007/978-3-319-54328-4_15
23. A. Botta, A. Dainotti, A. Pescapé, "Do You Trust Your Software-Based Traffic Generator?", *IEEE Communications Magazine* 48(9), 158-165 (2010). doi:10.1109/MCOM.2010.5560600
24. P. Emmerich, S. Gallenmüller, D. Raumer, F. Wohlfart, G. Carle, "MoonGen: A Scriptable High-Speed Packet Generator", *Proc. Internet Measurement Conference (IMC)*, ACM, 275-287 (2015). doi:10.1145/2815675.2815692
25. V. Paxson, "On Calibrating Measurements of Packet Transit Times", *Proc. ACM SIGMETRICS '98*, 11-21 (1998). doi:10.1145/277851.277865
