# 00 Research background: origin, theory and hypotheses

**Principal investigator:** Kenneth Nnorom, network security engineer and systems researcher  
(kennethnnorom.com · linkedin.com/in/kennethnnorom)  
**Parent project:** Ephemres (formerly LNMP, the Lightweight Network Monitoring Platform)

This page explains why the lab exists, the practical field discovery that motivated it, the theory and published work behind it, and the hypotheses it tests. For what was built, see [01 Project scope](01-project-scope.md). For how measurements are taken, see [02 Test methodology](02-test-methodology.md). Terms are defined in the [glossary](../README.md#glossary).

---

## 1. Origin of the research

### The field anomaly: terminal ping vs. application telemetry
This investigation started with a small discrepancy noticed while running Ephemres on deployed Linux machines. When I ran standard command-line `ping` tests from a terminal on the same deployed Ephemres Linux host, round-trip times (RTTs) to monitored targets were steady and low. Yet Ephemres itself, running on the exact same machine, reported a slight, regular RTT offset above the terminal `ping`, along with periodic tail spikes (p95 and p99, the slowest 5 % and 1 % of packets) and higher jitter (packet-to-packet variation).

Seeing that gap on the same host was the first clue that this behaviour existed: either the network only slowed down when Ephemres probed it, or Ephemres was adding its own delay to the measurements it recorded.

### The single-core heritage: GNS3 simulation environment
When Ephemres was first built, it was designed to run reliably on a **single-core, low-spec machine**. Early design and testing were done inside a **GNS3 simulated network environment** using virtualised Debian and Ubuntu machines with a single CPU core (1 vCPU).

Because virtualised nodes in GNS3 share host CPU time under tight limits, keeping the monitor fast on a single core was a hard constraint from day one. As Ephemres grew, we needed to know how multi-core CPUs affect these runtimes while keeping single-core performance intact.

### What Ephemres already does right (and the 4 → 15 semaphore tuning)
An audit of the Ephemres engine code (`monitoring/engine.py`, `monitoring/ping.py`, `monitoring/state_machine.py`) confirmed that the platform already removes the obvious sources of self-interference:

1. **Process isolation.** The probing engine runs as its own service, separate from the web API workers.
2. **Measure first, save later.** Each endpoint cycle is 5 pings sent 8 s apart: about 32 s normally, 42 s in the worst case where pings time out. Database writes happen only after all 5 pings finish, in the spare time before the endpoint's next 60 s slot.
3. **Deterministic staggering.** Each endpoint gets its own start second (0–59), derived from its UUID, so endpoints do not all start together.
4. **Capped concurrency (the 4 → 15 ICMP accuracy optimisation).** Post-cycle database writes pass through an asynchronous semaphore (`db_write_semaphore`), which limits how many run at once. In early versions of Ephemres, this semaphore was set to **4**. As the monitored deployment grew, expanding the semaphore from **4 to the current 15** was the single most effective performance update **specifically for improving ICMP measurement accuracy**, allowing post-cycle writes to clear with higher concurrency so fewer endpoints backed up behind the queue.
5. **Lean receive path.** One raw ICMP socket, watched by `loop.add_reader()`, reads packets into a preallocated 1500-byte buffer (`recvfrom_into`) and stamps `time.monotonic_ns()` immediately.
6. **Cycle aggregation.** Five pings collapse into one summary database insert per cycle.

### The remaining problem: shared event-loop cross-talk
Even with those six optimisations in place, all endpoints still share **one Python `asyncio` event-loop thread**, so one task's synchronous CPU work can hold up every other task.

At 100 endpoints on a 60 s cycle:
- on average **53.3 endpoints** are in the middle of probing at any moment (`100 × 32 s / 60 s`);
- **1.67 endpoints per second** (`100 / 60`) are finishing a cycle and doing synchronous post-cycle work: evaluating their state machine, building ORM objects, and serialising SQL parameters.

While endpoint A does that CPU-bound work (or if the runtime pauses for memory management), the event loop cannot react to the arrival of endpoint B's echo reply. B's packet waits in the operating system's socket receive queue. Because Ephemres stamps the arrival time in user space *after* reading the socket, B's RTT measurement is charged with the CPU time spent on A.

### The engineering dilemma: test before rewriting
Early reading pointed to Python's single-threaded `asyncio` event loop and CPython's cyclic Garbage Collector (GC) as likely causes of application-side delay. Compiled languages with similar asynchronous models (specifically **Go `goroutines`** and **Rust `tokio`**) are often credited with better concurrency and lower tail latency, especially on multi-core CPUs.

In Ephemres, however, Python already worked well. Replacing a working Python codebase with Go or Rust on a hunch would have been bad engineering. Before touching production code, we needed to test the problem directly:
- How large is the internal observer effect in Python `asyncio` under Ephemres's real probing schedule?
- Why did raising the semaphore from 4 to 15 help, and what happens at 5, 15, 30, or 50?
- How do Go (`goroutines`) and Rust (`tokio`) compare against the current Python (`asyncio`) engine under the same load, both on a **single core** (matching the original GNS3 1-vCPU constraint) and on **multi-core CPUs**?
- Does offloading Python's CPU work to a multi-core `ProcessPoolExecutor` solve the problem without switching languages?
- What do these results mean in practice for Ephemres (and any other monitoring platform built on a similar architecture) when weighing schedule design, hardware scaling, and runtime trade-offs (Python vs. Go vs. Rust)?

This standalone lab (`ephemres-observer-lab`) was built to isolate and measure those effects across operating-system layers, concurrency models, and language runtimes.

---

## 2. Two different observer effects

The experiments separate two effects that are easy to confuse:

| | Internal observer effect | External observer effect |
|---|---|---|
| **Cause** | the monitor's own CPU work delays *when it reads* a reply | the monitor's probe load changes *what is being measured* |
| **What is distorted** | the program's reading (the packet's true RTT is unchanged) | the network's or target's behaviour (queues, rate limits, loss) |
| **Visible as** | observer lag: Clock B − Clock A | a change in kernel RTT and in packet loss |
| **Triggered by** | ORM work blocking the loop; bursts of writes released by the semaphore | firing many endpoints at once (burst) |
| **Remedy** | a different concurrency model, offloading, smaller bursts | staggering the schedule |

The kernel timestamp (Clock A) is what lets the lab tell them apart. The program's own busy-ness cannot affect it, so any change in kernel RTT belongs to the external effect, while the gap `Clock B − Clock A` isolates the internal effect.

---

## 3. Theoretical framework and literature review

The idea that observing a system disturbs it appears both in physics and in computer-systems engineering. In reviewing the literature for this study, we separate **core literature** (which directly explains host-side timestamp distortion, asynchronous event-loop blocking, and runtime garbage collection) from **adjacent and extended literature** (which provides broader context for further studies).

### A. Core literature: the measuring host and asynchronous runtimes

#### 1. The measuring host as a source of error
* **Kernel timestamping and fleetwide host delay.** Willem de Bruijn (2023) demonstrated how traditional user-space timing falsely blames the physical network for delays inside the host's own software stack, showing how Linux `SO_TIMESTAMPING` separates NIC receive, host kernel receive, and application receive, and raising the open question: *"How much do measurements perturb the measured system?"*
* **Precision active probing without dedicated hardware.** Pásztor and Veitch (2001, 2002) proved that standard Unix user-space active probers suffer from "system noise on the time the clocks are read" due to OS interrupts, context switching, and scheduling delays, demonstrating that user-space software clocks systematically distort RTT and jitter.
* **A probe's own load inflates its RTTs.** Holterbach et al. (2015) showed that on RIPE Atlas, a global network of measurement probes, measurements running from and towards the same probe interfere. The probe's CPU load inflates the RTTs it reports (less so on probes with a faster CPU) and can delay scheduled measurements. This is the closest published evidence of a monitor distorting its own readings.
* **User-space vs. kernel delay.** Li et al. (2018) took apart the RTT inflation in smartphone measurement apps (Speedtest, MobiPerf) layer by layer. They found it in both user space (mostly the managed runtime) and the kernel (sleeping driver functions); a native app kept the user-space part under 1.5 ms. Their method, splitting one RTT by where the time is spent, is the one this lab applies to a monitoring engine.
* **Active SLA probing and probe schedule distortion.** Sommers et al. (2005, 2007) showed that active SLA monitors (measuring delay, loss, and RFC 3550 jitter) distort the network when probing bursts occur, establishing the foundation for analysing how schedule shapes (burst vs. staggered) impact measurement fidelity.

#### 2. Event-loop blocking, garbage collection pauses, and runtime schedulers
When hundreds of probing tasks share an application runtime, synchronous CPU work, memory management, and thread scheduling directly delay when the application can read arriving packets:
* **Tail latency amplification in shared runtimes.** Dean and Barroso (2013, *The Tail at Scale*) established how background runtime activities, garbage collection pauses, and queueing behind synchronous tasks amplify 95th and 99th percentile latency in networked systems. On a single-threaded event loop, any pause blocks every concurrent I/O reader behind it.
* **CPython `asyncio` and cyclic garbage collection pauses.** Pablo Galindo Salgado (PyCon 2019) detailed how CPython supplements reference counting with a generational cyclic garbage collector (`gc`). When generation thresholds are exceeded, CPython halts execution across the interpreter to traverse tracked container objects (`PyGC_Head`) and break reference cycles, freezing the `asyncio` event loop until collection finishes.
* **Production GC overhead in Python services.** Wu and Ni at Instagram Engineering (2017, *Dismissing Python Garbage Collection at Instagram*) documented how CPython's cyclic GC caused latency spikes, CPU cache churn, and copy-on-write page faults in production Python workers, leading them to disable cyclic GC entirely to stabilise response times and raise throughput by 10 %.
* **Go's concurrent GC vs. Rust's zero-GC deterministic execution.** Nowack at Discord Engineering (2020, *Why Discord is Switching from Go to Rust*) published a clear production comparison of Go and Rust in a latency-critical service. Even with Go's concurrent collector, mandatory GC passes (forced at least every 2 minutes) scanned large object graphs and caused recurring millisecond latency spikes; rewriting the service in Rust (which uses compile-time ownership without a runtime garbage collector) eliminated the latency spikes completely.
* **Goroutine preemption and scheduler starvation.** Clements (2019) documented the design of Go's goroutine preemption model, explaining how tight CPU-bound loops delay runnable and timer-woken goroutines until preemption points are reached, which directly informs the single-core Go behaviour observed in this lab.

#### 3. Standards and kernel timestamping interfaces
* **RFC 3550 §6.4.1, smoothed inter-arrival jitter.** This standard formula for jitter uses `D(i, j) = (R_j − S_j) − (R_i − S_i)`, the change in transit time between two packets:
  ```text
  J(i) = J(i-1) + ( |D(i-1,i)| − J(i-1) ) / 16
  ```
  Any observer delay on a receive timestamp `R_j` inflates `|D|` and, through the running average, contaminates the jitter of the packets that follow. That is why the lab reports jitter twice: from the kernel timestamps and from the observer's timestamps.
* **Linux kernel timestamping (`SO_TIMESTAMPNS`, `SO_TIMESTAMPING`).** The kernel records a packet's arrival time and hands it to the program as ancillary data (`cmsg`) with `recvmsg()`, before any user-space scheduling. Network cards that support IEEE 1588 (the Precision Time Protocol) can also stamp packets in hardware (`SOF_TIMESTAMPING_RAW_HARDWARE`). The lab can record those as a cross-check.
* **Wire time vs. host time.** The IETF's delay metrics distinguish the moment a packet arrives on the wire from the moment a host records it, and list the difference as a measurement error (RFC 2330 §10.2; RFC 7679 §3.7.2). Clock A and Clock B make this distinction measurable on every packet.

---

### B. Additional relevant literature for extended studies

The following works are valuable foundational references across physics, compiler benchmarking, hardware packet generation, and wide-area measurement. While only specific subsets of these works apply directly to single-host asynchronous ICMP monitoring, they are preserved here for context and extended research:

* **Physical analogies (conceptual vocabulary):**
  * *Heisenberg's microscope (1927):* Observing an electron more sharply disturbs its momentum more (`Δx · Δp ≥ ℏ/2`). In telemetry, observing more frequently injects interrupts, context switches, and memory allocations into the host pipeline.
  * *Reference frames and time (Rossi and Hall, 1941):* A moving muon's elapsed time differs from the laboratory frame. Analogously, a packet passes through three "frames" of time inside a host: *wire time* (cable serialisation), *kernel frame* (interrupt handling, DMA, and socket buffer queueing), and *observer frame* (scheduler wake-up, `recvmsg` syscall, and user-space clock read). A packet waiting in the kernel for a busy program has finished its physical journey, but in the program's frame it keeps "ageing".
* **General software probe effects and benchmark bias:**
  * *Probe effect:* Gait (1986) showed that adding monitoring code to concurrent programs changes their scheduling and event order.
  * *Measurement intrusion and perturbation:* Malony, Reed, and Wijshoff (1992) modelled monitor intrusion mathematically: the formal precursor to subtracting an idle floor. Mytkowicz et al. (2009) showed that small, non-obvious differences in runtime and memory layout systematically bias benchmarks, which is why this lab compares engines using identical packets, schedules, and statistical code.
* **Hardware timestamping, traffic generators, and host-latency decomposition:**
  * *Kernel timestamps in ping tools:* Dreibholz (2023) added Linux and FreeBSD kernel and hardware timestamping to the HiPerConTracer ping/traceroute tool, with a survey of socket timestamping options.
  * *Where host latency comes from:* Zilberman et al. (2017) broke end-to-end latency down from the application to the wire in data-centre hosts and found no single dominant term: host-side latency must be measured, not assumed.
  * *Software traffic generator inaccuracy:* Botta, Dainotti, and Pescapé (2010) showed that software traffic generators do not produce or time packets as configured. MoonGen (Emmerich et al., 2015) uses NIC hardware timestamps for sub-µs latency measurement for that reason.
  * *Real-time host jitter and C-state penalties:* Low-latency benchmarking and trading systems literature (e.g., HFT-Bench, 2025) demonstrates how database writes, serialisation, and CPU idle sleep states (C-states) perturb user-space measurement timestamps on the hot path.
  * *Calibrating wide-area delay measurements:* Paxson (1998) showed that clock adjustments and clock skew cause large errors in measured transit times even under NTP, forming the background to the lab's clock-slew threat (see [02](02-test-methodology.md)).

---

### C. What this lab adds

The published work above establishes that measuring hosts add error, and shows how to timestamp around it. As far as our literature search went (October 2026), none of it does the following, which are this lab's specific contributions:

1. **Same-packet dual-clock self-control:** It captures `SO_TIMESTAMPING` (Clock A) and the application clock (Clock B) on *every single ICMP packet simultaneously* over standard raw sockets, isolating user-space delay without dedicated hardware capture cards (DAG cards) or kernel patches.
2. **Event-loop cross-talk in multi-endpoint SLA engines:** It measures, per packet and with no cooperation from the target, how much **the monitor's own application work** (preparing a monitoring platform's database writes behind an async semaphore) delays reading replies and contaminates in-flight measurements of *other* endpoints sharing the loop.
3. **The 6-way concurrency and runtime matrix:** It compares **concurrency runtimes** (Python `asyncio` cooperative coroutines, Go preemptive goroutines with M:N netpoller, and Rust `tokio` compiled work-stealing tasks; on one core and on all cores) under an identical real-network probing schedule and identical CPU burn.
4. **Quantifying the process offload tax:** It measures the exact cost of Python multi-core worker process offloading (IPC serialisation and main-process GIL contention), demonstrating that offloading work from the event loop does not necessarily eliminate user-space measurement latency.
5. **Loss by cause:** It separates **loss caused by the observer** (a reply that arrived in the kernel in time, but was read by the application after its timeout expired) from true network loss.

The dashboard's default configuration reproduces the Ephemres settings: 100 endpoints, 5 pings 8 s apart, a 60 s cycle with start times spread over it, and semaphore 15. Every experiment is therefore a stated deviation from the real system ([02 Test methodology](02-test-methodology.md) §2).

---

## 4. Hypotheses and the experiment matrix

The lab compares three runtimes under two CPU arrangements:

| Runtime | Single core (one CPU pinned) | Multi core (all CPUs) | Question |
|---|---|---|---|
| **Python (`asyncio`)** | ORM work runs inline on the event loop | ORM work offloaded to a `ProcessPoolExecutor` (separate worker processes) | Blocking a single thread (the GNS3 1-vCPU baseline), versus the cost of pickling (serialising) data and inter-process communication on the loop that reads the socket |
| **Go (`goroutines`)** | `GOMAXPROCS=1` (one thread runs Go code) | `GOMAXPROCS` = all CPUs (work-stealing scheduler) | How the Go scheduler handles a mix of I/O and CPU bursts, on a single core and with spare threads |
| **Rust (`tokio`)** | `current_thread` runtime (one thread) | Multi-thread work-stealing runtime | The latency floor of compiled code without a garbage collector, on one core and when other threads can take the CPU work |

### Key experimental dimensions
- **Single-core vs. multi-core CPU modes:** Single-core mode tests the original Ephemres design constraint (running smoothly on a 1-vCPU virtual machine in GNS3), while multi-core mode tests how each runtime uses modern multi-core hardware.
- **Semaphore sweep (`5, 15, 30, 50`):** Directly tests the production tuning update where raising `db_write_semaphore` from 4 to 15 improved Ephemres's ICMP accuracy, checking whether smaller or larger concurrency limits reduce or worsen observer lag.
- **Schedule shape (`60 s` staggered vs. `0 s` burst):** Separates normal staggered operation from worst-case simultaneous arrival and write bursts.
- **Idle floor (`0 ms` vs. `3 ms` ORM work):** Measures each runtime's inherent wake-up and socket-read cost without post-cycle CPU work.

### Two methodological cautions when reading this matrix
1. **Event-loop blocking is isolated; garbage collection is not.** While the literature identifies both synchronous event-loop blocking and cyclic garbage collection pauses as latency sources in Python and Go, the simulated 3 ms ORM work in this lab is a deterministic CPU spin that allocates almost no heap memory. Differences in our baseline corpus therefore measure **event-loop blocking and scheduler contention**, and should not be blamed on garbage collection without a separate allocation-heavy experiment (see [10 Results analysis](10-results-analysis.md) §Methodological Lessons #4).
2. **The multi-core modes differ by design.** In Go and Rust, multi-core worker threads share memory with the socket reader. Python's multi-core mode crosses an operating-system process boundary (`ProcessPoolExecutor`) to bypass the GIL. The comparison includes that structural difference on purpose.

---

## 5. Why simulate the database work as CPU work

An asynchronous database write has two phases:

1. **Network I/O wait.** Waiting for the database over a socket hands control back to the event loop (`await`), so it does not stop packets being received.
2. **CPU preparation.** Before the I/O, the application computes cycle statistics, evaluates state-machine (z-score) transitions, builds ORM or Pydantic objects, and serialises SQL parameters. This is *synchronous CPU work*: nothing else on that thread can run during it.

`simulated_db_ms` (default 3.0 ms) models the second phase, gated by `db_write_semaphore` (default 15). A short asynchronous sleep (1 ms) then stands in for the first phase. Using a fixed CPU spin removes disk and database variation, so what remains is pure scheduling contention inside the application's runtime.

---

## 6. From field anomaly to empirical investigation

Rather than assuming why the terminal `ping` and Ephemres telemetry disagreed (or immediately rewriting the Python monitoring engine in Go or Rust), this project turned the field observation into a controlled, reproducible measurement pipeline:
1. **Measurement model ([02 Test methodology](02-test-methodology.md)):** Every ICMP echo reply is stamped twice on `CLOCK_REALTIME` (by the Linux kernel upon arrival as Clock A, and by the user-space runtime upon read as Clock B), quantifying observer lag on every packet.
2. **Two-tier lab architecture ([03 Architecture](03-architecture.md) and [04 Engines](04-engines.md)):** An isolated process harness runs functionally identical Python, Go, and Rust probing engines across single-core and multi-core modes.
3. **Empirical benchmark corpus ([10 Empirical Results and Comparative Analysis](10-results-analysis.md)):** All 173 recorded benchmark runs (covering staggered and burst schedules, semaphores 5 to 50, endpoints 25 to 250, and interleaved idle floors) are analysed and programmatically verified in [10 Results analysis](10-results-analysis.md).

---

## 7. References

All academic entries were checked against Crossref (DOI given), ACM/IEEE proceedings, or the RFC Editor in October 2026. Industry engineering studies and core developer presentations are cited with their publication venue and year.

### Core literature: host measurement error, async runtimes, and GC latency
1. W. de Bruijn, "SO_TIMESTAMPING: Powering Fleetwide RPC Monitoring", *Proc. Netdev 0x17* (2023).
2. A. Pásztor, D. Veitch, "PC Based Precision Timing Without GPS", *Proc. ACM SIGMETRICS '02*, ACM, 352-362 (2002). doi:10.1145/511334.511378
3. A. Pásztor, D. Veitch, "A Precision Infrastructure for Active Probing", *Proc. PAM 2001* (2001).
4. T. Holterbach, C. Pelsser, R. Bush, L. Vanbever, "Quantifying Interference between Measurements on the RIPE Atlas Platform", *Proc. Internet Measurement Conference (IMC)*, ACM, 437-443 (2015). doi:10.1145/2815675.2815710
5. W. Li, D. Wu, R. K. C. Chang, R. K. P. Mok, "Toward Accurate Network Delay Measurement on Android Phones", *IEEE Transactions on Mobile Computing* 17(3), 717-732 (2018). doi:10.1109/TMC.2017.2737990
6. J. Sommers, P. Barford, N. Duffield, A. Ron, "Accurate and Efficient SLA Compliance Monitoring", *Proc. ACM SIGCOMM '07*, ACM, 109-120 (2007). doi:10.1145/1282380.1282393
7. J. Sommers, P. Barford, N. Duffield, A. Ron, "Improving Accuracy in End-to-End Packet Loss Measurement", *Proc. ACM SIGCOMM '05*, ACM, 157-168 (2005). doi:10.1145/1080091.1080110
8. J. Dean, L. A. Barroso, "The Tail at Scale", *Communications of the ACM* 56(2), 74-80 (2013). doi:10.1145/2408776.2408794
9. P. Galindo Salgado, "Time to take out the rubbish: garbage collector", *PyCon US 2019*, Python Software Foundation, Cleveland, OH (2019).
10. C. Wu, M. Ni (Instagram Engineering), "Dismissing Python Garbage Collection at Instagram", *Instagram Engineering Blog*, Meta (Jan. 2017).
11. M. Nowack (Discord Engineering), "Why Discord is Switching from Go to Rust", *Discord Engineering Blog* (Feb. 2020).
12. A. Clements, "Proposal: Non-cooperative goroutine preemption", *Go Design Documents*, Go Issue #24543 (2019).

### Standards
13. V. Paxson, G. Almes, J. Mahdavi, M. Mathis, "Framework for IP Performance Metrics", RFC 2330 (1998).
14. G. Almes, S. Kalidindi, M. Zekauskas, A. Morton (ed.), "A One-Way Delay Metric for IP Performance Metrics (IPPM)", RFC 7679 / STD 81 (2016).
15. H. Schulzrinne, S. Casner, R. Frederick, V. Jacobson, "RTP: A Transport Protocol for Real-Time Applications", RFC 3550 / STD 64 (2003), §6.4.1.

### Additional relevant literature for extended studies
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
