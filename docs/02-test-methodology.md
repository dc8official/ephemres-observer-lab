# 02 Test methodology

This document defines what is measured, how it is measured, and how to read the results. Every number the dashboard or a CSV file shows is defined here. Terms are also defined in the [glossary](../README.md#glossary).

## 1. The measurement model

A ping travels like this:

```
 program                         kernel                       network            target
 ───────                         ──────                       ───────            ──────
 tx = clock()  ── sendto() ───▶  send path ───────────────────▶ wire ─▶ echo request ─▶ target OS
                                                                                          │
                                                                                          ▼
 Clock B = clock()  ◀─ recvmsg ─ socket queue ◀─ Clock A ◀──── wire ◀── echo reply ◀─────┘
 (program reads the packet)      (packet waits)  (kernel stamps
                                                  arrival here)
```

* **`tx`** is read by the program (in user space) immediately before it calls `sendto()` to send the request.
* **Clock A** is the kernel's arrival timestamp. It is the `SO_TIMESTAMPING` software stamp, or `SO_TIMESTAMPNS` where that is unavailable.
  - The kernel hands it to the program together with the packet, as ancillary data (a "cmsg").
  - It is fixed when the network stack first handles the packet, so it does not depend on what the program is doing.
* **Clock B** is read the instant the program's `recvmsg` call (the read of the packet) returns.
* All three timestamps are `CLOCK_REALTIME` nanoseconds, so they can be subtracted directly.
* In IETF terms (RFC 2330 §10.2, RFC 7679 §3.7.2), Clock A approximates the packet's *wire time* and Clock B is *host time*. The standards treat the gap between them as a measurement error, and the lab measures it on every packet.

### Per-packet quantities

| Quantity | Definition | Meaning |
|---|---|---|
| kernel RTT | Clock A − tx | the round trip as the operating system saw it: send path + network + target + arrival |
| observer RTT | Clock B − tx | the round trip as the monitoring program reports it |
| **observer lag** (also called intrusion) | Clock B − Clock A | how long the reply sat waiting for the program: the measurement error |
| error % | 100 × observer lag ÷ kernel RTT | the error relative to the true RTT (only where kernel RTT > 0) |

`tx` cancels out of observer lag, so the lag does not depend on how long the send system call took.

**Kernel RTT is the reference, not a perfect "true" RTT.** Because `tx` is read in user space just before `sendto()`, kernel RTT also contains:
- the send system call itself;
- any moment the program is paused between reading `tx` and the packet leaving. That is a few µs normally, more if the thread is preempted at exactly that point.

Observer lag is unaffected, because `tx` cancels out. The denominator of error %, and the external-effect reading, are slightly inflated. A kernel transmit stamp (`SOF_TIMESTAMPING_TX_SOFTWARE`) would remove this; it is planned but on hold.

A packet is **lost** if no matching reply arrives within the timeout (2 s by default). Lost packets have no RTT or lag, so they are left out of those statistics, but they are counted as loss.

### Loss by cause (late replies)

A reply that turns up *after* its ping timed out is not thrown away. Every engine remembers timed-out pings and reports such a reply as a **late** reply, with its kernel stamp. The analysis then splits loss three ways:

| Cause | Test | Meaning |
|---|---|---|
| no reply | nothing ever came back | real network loss, or the target ignored the ping |
| reply after the timeout | late reply, `Clock A − tx` > timeout | the network or the target was slow |
| reply in time, read too late | late reply, `Clock A − tx` ≤ timeout | the kernel had the reply in time, but the program read it after its timeout had fired. **This loss is caused by the observer.** |

### Send lag (the send-side observer effect)

A busy program also *sends* late. The coroutine, goroutine or task that should send ping *n* at its scheduled moment wakes up late.
- **What is recorded:** every engine records, per packet, **send lag = actual send time − scheduled send time**, on the monotonic clock.
- **Effect:** it does not change the RTT, because `tx` is read at the real send. It does bend the probing schedule.
- **Floors differ per engine.** As with the canary, each runtime has its own floor set by its timer resolution. On the development laptop this is roughly 0.3–0.7 ms for Go, 0.7 ms for Python and 1–1.6 ms for Rust. Compare *increases*, not absolute levels.

### Hardware timestamps (opt-in, Python only)

This option is off by default. It is enabled with `--hw` on the command line, or the "NIC hardware timestamps" box in the dashboard.
- **What it does:** when run as root on a real network card (NIC) that supports it, the Python engine also turns on the NIC's own hardware receive timestamp and records it as `hw_rx_ns`.
- **It breaks comparisons with Go and Rust.** It changes a setting on the network card for the duration of the run, and Go and Rust never do that. So **a run with hardware stamps on is not comparable with Go or Rust runs**. The dashboard refuses the option for Go and Rust, and flags mixed comparisons.
- **It is a cross-check, not a third clock to subtract.** The stamp comes from the NIC's own clock, which is a different clock from A and B, so it is never subtracted from them. It lets a row be checked against `tcpdump --time-stamp-precision=nano -j adapter_unsynced`.
- **The NIC is left as it was found.** The setting is read first, changed only if that is safe, and restored when the run ends.

## 2. The workload (what the program is asked to do)

Each **virtual endpoint** (a simulated monitored device) runs `cycles` cycles, one every `cycle_length` seconds. Each cycle is:

1. Send `pings` echo requests, one every `interval` seconds, each waiting up to `timeout` for its reply.
2. Wait for a slot in the **database-write semaphore** (`db_write_semaphore`, default 15).
3. Do the simulated ORM work: a CPU spin of `simulated_db_ms` (default 3.0 ms), then an asynchronous 1 ms sleep while still holding the semaphore. The sleep stands in for the I/O half of a database write.
4. Release the semaphore and wait for the next cycle.

### Defaults: Ephemres' own configuration

The dashboard starts from the configuration of the system being modelled. An untouched form reproduces Ephemres, and every change is a deliberate, visible deviation (the form lists the differences):

| Setting | Default | Source |
|---|---|---|
| virtual endpoints | 100 | the scale at which the problem was first seen |
| pings per cycle, interval | 5 pings, 8 s apart | Ephemres |
| reply timeout | 2 s | lab default |
| stagger window, cycle length | 60 s, 60 s | Ephemres: each endpoint starts at a second 0–59 of a 60 s slot |
| cycles | 3 | Ephemres runs continuously; 3 gives two steady-state cycles after the warm-up |
| `db_write_semaphore` | 15 | Ephemres production default (tuned from 4 to 15 specifically to improve ICMP measurement accuracy; swept at 5, 15, 30, 50) |
| simulated ORM work | 3 ms | the lab's estimate of Ephemres' post-cycle CPU work |

With these values about 53 endpoints are in the middle of a cycle at any moment (100 × 32 s / 60 s). The old lab defaults (1 s interval, 30 s window) gave about 13, so contention is now far closer to the real system. The command-line runner keeps its own flag defaults (1 s interval, one cycle) for quick checks.

### The warm-up cycle

When a run has more than one cycle, **cycle 0 is left out of every statistic**, in the dashboard and in the terminal summary alike.
- **Why:** endpoints are still starting during cycle 0, so fewer of them overlap than in steady state.
- **What is kept:** cycle 0 is still saved in the files. The canary summary and heartbeat cover the whole probing period, including cycle 0.

### Virtual endpoints and addressing

`N` endpoints are spread round-robin over the target IP addresses.
- **Identifiers:** endpoint *i* uses ICMP identifier `0x1000 + i`.
- **Sequence numbers:** ping *n* of cycle *c* uses sequence number `c × pings + n`, which is unique within the run.
- **Matching:** the target echoes both numbers back (RFC 792), and replies are matched on `(identifier, sequence)` alone. So 500 endpoints can share one raw socket and one target.
- **Warm-up ping:** a single unrecorded ping is sent to each target first, so the target's address resolution (ARP) is cached and ping #1 is not an outlier.

### Schedule: burst vs staggered

Endpoint *i* of *N* starts cycle *c* at `c × cycle_length + stagger_window × i / N` seconds after the run begins.
- **Burst** is `stagger_window = 0`: every endpoint starts at once. This maximises contention, and can overload the target (see §6).
- **Staggered** spreads the load, so only a few endpoints are in flight together.

### CPU modes

| Mode | Python | Go | Rust | Rationale |
|---|---|---|---|---|
| **single_core** | process pinned to one core; the ORM spin runs inline on the event loop | `GOMAXPROCS=1`, pinned to one core | single-threaded tokio runtime, pinned to one core | Models resource-constrained 1-vCPU hosts and GNS3 network simulation environments where Ephemres was first built |
| **multi_core** | the event loop stays on its core; the ORM spin runs in a process pool (`ProcessPoolExecutor`), and its data is pickled across the process boundary | `GOMAXPROCS` = all cores | multi-threaded (work-stealing) tokio runtime | Models modern multi-core server hardware to assess whether scaling cores eliminates event-loop starvation |

**Python multi-core deliberately pays the real price of offloading.**
- **The payload is serialised on the main process's side.** The ORM-style payload is a dict holding five packet dicts, strings and tags. It is serialised on helper threads in the main process. Those threads compete with the event loop for Python's interpreter lock (the GIL).
- **What is reported:** the wall time of the offload minus the worker's own burn time, as **ORM offload overhead (IPC + pool wait)**.
- **Why pool wait is included:** when the semaphore allows more concurrent writers than there are workers (`CPUs − 1`, which is 7 on the 8-CPU test host), extra jobs queue inside the pool. Under a 60 s staggered schedule, average concurrency is `0.0067 ≪ 1`, so jobs rarely overlap even at semaphore 50; under a burst schedule with semaphore 15, up to 15 jobs enter the 7-worker pool at once. Isolating pure IPC cost under burst requires setting `db_write_semaphore ≤ CPUs − 1` (an extended experiment noted in §5).

**How Python multi-core is monitored.** Everything measured in the other modes is measured here too: both clocks on every packet, the canary, send lag and loss by cause.
- **What is added:** the **ORM offload overhead**, reported per cycle and per run. The ORM-work shading marks the offloaded jobs.
- **What this tests:** whether moving the 3 ms CPU spin off the main thread eliminates both event-loop starvation (measured by the canary) and packet-reading intrusion (measured by `Clock B − Clock A`), or whether the remaining socket I/O and IPC serialisation costs keep intrusion bounded by the event loop itself (evaluated in [10 Results analysis](10-results-analysis.md) §R1.3, §R3.3).

## 3. Metrics and analysis choices

All statistics are computed once on the server (`server/analysis.py` and `server/stats.py`) from the raw per-packet timestamps using a single implementation shared across all three engines. When a run has multiple cycles, cycle `0` is excluded from all packet and cycle statistics as warm-up (§2). Percentiles use linear interpolation (`pos = (n - 1) × q`, the NumPy default).

| Metric | Scope | Definition and Why It Matters |
|---|---|---|
| **Run-level `mean`, `p50` (median), `p95`, `p99`, `max`** | All steady-state replied packets of a run | Summary statistics of **observer lag** (`Clock B − Clock A`) across the run's measured packets (`cycle >= 1`). Reporting both `p50` (median) and `p95`/`p99`/`mean` is essential because under burst load, Go and Rust read the first four pings of each cycle near the idle floor (`p50 ≈ 30–80 µs`) while stalling on the final ping for tens of milliseconds, pulling the `mean` and `p95` up by 40×. |
| **Cycle-level `min`, `max`, `avg`, `p95`, `std dev`** | The replied packets of one endpoint cycle (`5` pings by default) | Recorded in `<name>_cycles.csv` separately for `kernel_rtt_us`, `user_rtt_us`, and `observer_lag_us`. Standard deviation uses the population formula `sqrt((1/k) × sum((x_i − mean)^2))`. |
| **Pings 1–4 vs. Ping 5 (`icmp_seq % pings == pings - 1`)** | Early pings vs. final ping of each cycle | In a 5-ping cycle, **Pings 1–4** arrive while endpoints are still probing (no post-cycle database work triggered). **Ping 5** (`icmp_seq % 5 == 4`) is the final ping whose reply releases the endpoint into the `db_write_semaphore` and 3 ms ORM spin. Comparing Pings 1–4 against Ping 5 isolates whether stalls are caused by post-cycle ORM serialisation or by send/receive loop batching. |
| **RFC 3550 jitter** | Per endpoint cycle, then averaged across cycles | Smoothed inter-arrival transit-time variation defined by RFC 3550 §6.4.1: for consecutive replied packets `i − 1` and `i` in sequence order within the same cycle, `D(i − 1, i) = RTT_i − RTT_{i − 1}` and `J_i = J_{i − 1} + (|D(i − 1, i)| − J_{i − 1}) / 16`. Computed independently on **Kernel RTTs** (true network jitter) and **Observer RTTs** (reported jitter). The gap `Observer Jitter − Kernel Jitter` is artificial jitter invented by the monitor's runtime scheduling. |
| **Error % (primary)** | Run, endpoint, or cycle | `100 × sum(observer_lag) ÷ sum(kernel_rtt)` across all measured packets in the scope. Answers *"what percentage of the total wire time measured was added by the observer?"* and prevents a single packet with a tiny denominator from dominating the result. |
| **Error % (secondary)** | Per packet, summarised by median, mean, and max | For each packet `i` with `kernel_rtt_i > 0`, `e_i = 100 × observer_lag_i ÷ kernel_rtt_i`. The median `e_i` shows a typical packet's relative error; the arithmetic mean is sensitive to single low-RTT outliers (see worked example below). |
| **Intrusion above idle floor (`Δ`)** | Run vs. matching floor run | A loaded run's intrusion statistic (`mean`, `p50`, `p95`, `p99`) minus the same statistic from the matching idle-floor run (`simulated_db_ms = 0.0`, identical engine, CPU mode, schedule, and target), isolating the delay added specifically by the post-cycle ORM work. |
| **Reader wakeup (`reader_calls`)** | Run counter | One invocation of the socket read loop (`recvmsg` until `EAGAIN`) that delivers at least one expected in-flight reply. Passes that read only late (post-timeout) or foreign ICMP packets are ignored by all three engines. |
| **Packets per wakeup & queue depth (`reader_batch`)** | Per wakeup / per packet | Each packet records `reader_batch`, the total number of replies drained from the kernel socket buffer during the wakeup that delivered it; **max queue depth** is `max(reader_batch)` and **packets per wakeup** is `replied ÷ reader_calls`. A value near `1.0` indicates the runtime woke promptly for each reply; `100.0` indicates 100 replies piled up in the kernel buffer while the event loop was busy. |
| **Send lag (`send_lag_us`)** | Per packet (`mean`, `p95`, `max` over measured cycles) | `actual send time − scheduled slot time` measured on the runtime's monotonic clock immediately before `sendto()`. Quantifies the send-side observer effect (how late a busy scheduler dispatches outbound probes). |
| **Loss by cause** | Run counters (`no_reply`, `after_timeout`, `read_late`) | Classifies every timed-out ping using late-reply tracking (§1): **no reply** (true packet loss), **reply after the timeout** (`Clock A − tx > timeout`, slow network/target), or **reply in time, read too late** (`Clock A − tx <= timeout`, false timeout caused by the observer's event loop). |
| **ORM offload overhead (`ipc_ms`)** | Per cycle (`mean` and `max` per run, Python `multi_core` only) | Total wall-clock duration of `loop.run_in_executor()` minus the worker's `simulated_db_ms` CPU spin. Captures `pickle` serialisation/deserialisation on main-process helper threads, IPC pipe transfer, and worker-pool queueing when `db_write_semaphore` exceeds the worker count (`CPUs − 1`). |
| **Dashboard stream cost (`emit_us`)** | Run summary | Mean time spent serialising and writing each NDJSON `cycle` event to `stdout` (`emit_us_total / emit_n`), verifying that telemetry emission itself takes only tens of microseconds. |
| **Sample size `n` and percentile gate** | Run replied packet count | The number of steady-state packets with both Clock A and Clock B. A percentile `q` is plotted and unmarked only when `n >= 10 ÷ (1 − q)` (at least 10 packets in the tail above `q`: `n >= 200` for `p95`, `n >= 1,000` for `p99`), and is flagged **few samples** otherwise. |
| **▼ best / ▲ worst** | Comparison table row | Marked on lower-is-better rows only when the best and worst columns differ by at least the chosen threshold (`10%` by default) and, when combining repeats, their min–max repeat ranges do not overlap. |
| **Intrusion histogram** | Run distribution | Share of measured packets falling into 12 logarithmic lag buckets: `<50 µs`, `50–100 µs`, `100–150 µs`, `150–250 µs`, `250–500 µs`, `0.5–1 ms`, `1–2 ms`, `2–5 ms`, `5–10 ms`, `10–25 ms`, `25–50 ms`, and `>50 ms`. |

### The scheduler canary

Each engine runs a small task that asks to sleep 10 ms and measures how late it really wakes: `lag = elapsed − 10 ms`. This is the runtime's own measure of how long other work was kept waiting, independent of any network traffic. It is reported as average, p95 and max.

* **Gate.** The canary is already running during start-up, but it records only ticks that *begin* after start-up has finished (socket set-up, warm-up ping, process-pool start). It stops recording before shutdown and summary work begins. So start-up and teardown work never count as probing-time lag. (The two oldest runs in `test_results/` predate this gate; see [07](07-results-and-naming.md).)
* **The floor differs per runtime.** An idle canary reads about 0.1–0.4 ms in Python, because its selector rounds timeouts up to whole milliseconds. It reads 0.1–0.4 ms in Go, and about 1 ms in Rust, because tokio's timers have 1 ms resolution. Compare canary *increases* between engines, not absolute levels.
* **Per-cycle window.** Each cycle also reports the canary over the interval its pings were in flight.

### Error %: which one, and why

Per packet, error = observer lag ÷ kernel RTT. There are three ways to summarise a set of packets. The lab reports them in this order of importance:

1. **Total lag ÷ total kernel RTT (primary).** Add up all the lag, add up all the RTT, and divide. It answers "what share of all the time we measured was error?", and no single packet can dominate it.
2. **Median of the per-packet errors.** The middle packet's error: "how wrong is a typical reading?".
3. **Mean of the per-packet errors, and the max.** The mean is easily dominated by one packet whose RTT happens to be tiny.

**Worked example.** Take four packets with RTT 4 ms and lag 0.1 ms (2.5 % each), plus one packet with RTT 0.2 ms and lag 1 ms (500 %):
- total ÷ total = 1.4 ms ÷ 16.2 ms = **8.6 %**;
- median = **2.5 %**;
- mean = (4 × 2.5 + 500) ÷ 5 = **102 %**.

The same rule (total ÷ total) is used everywhere a single error figure is shown: run summaries, the per-endpoint table, and the terminal runner's per-cycle `Err%` column. Older runs that originally reported the mean are listed with both figures in [07 Results and naming](07-results-and-naming.md).

### The idle floor (optional subtraction)

**Why a floor is needed.** Even with nothing else to do, every runtime needs some time to notice that a reply has arrived: waking up, the system call, reading the clock. That time is its **idle floor**. It differs per language, so raw lag mixes two things: how slow this runtime is to wake, and how much the CPU work delays it.

**How it is measured.** The **Measure idle floor** button (or the batch **idle floor every round** option) runs the current setup with the ORM work set to `0 ms`. Everything else stays identical: engine, CPU mode, target, endpoints, pings, interval, timeout, stagger, cycles and NIC stamps. Ticking **subtract idle floor** then shows each run's intrusion minus the floor run's, which is what the CPU work adds.

**Protocol rules for idle floors:**
1. **Interleave floors in the same session (`Idle floor every round`):** Because host operating conditions (thermal throttling, power-governor state, and background system activity) drift across hours of the day, comparing a loaded test from one session against an idle floor recorded hours later can confound ORM load with baseline host drift. Always record each engine's idle floor *immediately before* its loaded test in rotating engine order.
2. **Why floor subtractions can be negative:** When the true overhead added by ORM work is near zero, the difference `loaded − floor` (`Δ`) fluctuates inside normal run-to-run variance and can be slightly negative. In addition, an unloaded CPU core can enter deeper power-saving sleep states (`C-states`, such as `C10 ≈ 890 µs` exit latency on modern laptops) and wake more slowly during an idle floor than during a loaded run where CPU work keeps the core awake ([10 Results analysis](10-results-analysis.md) §R3.4, §R3.5).

### Statistical replication and non-parametric significance

The **Repeat** setting runs one setup several times as a *batch*, rotating the engine order every round (`Python → Go → Rust`, then `Go → Rust → Python`, then `Rust → Python → Go`) so that slow host drift is spread across all engines. With **combine repeats** on, the dashboard reports the **median** across repeats and the **min–max range**, and only marks **▼ best / ▲ worst** when the repeat ranges do not overlap.

- **Unit of replication:** The unit of replication is the **run**, not the individual packet (packets within one run share the same ORM bursts and schedule collisions).
- **Exact Mann-Whitney rank test on non-overlapping ranges:** If every repeat of configuration A is below every repeat of configuration B (complete non-overlap), the exact two-sided Mann-Whitney rank-test p-value for `k` repeats per configuration is `2 ÷ C(2k, k)`:

| Repeats per column (`k`) | Exact `p` on complete non-overlap | Methodological interpretation |
|---|---|---|
| `2` | `0.33` | Exploratory check; non-overlap alone is weak evidence and can reflect run-to-run host drift |
| `3` | `0.10` | Exploratory sweep; clearly separates large regime differences (e.g., tens of microseconds vs. tens of milliseconds), but cannot prove small microsecond gaps at the 5 % level |
| `5` (recommended for formal replication) | `0.008` | **Minimum for a formal statistical claim** at the `p < 0.01` level |
| `7` | `0.0006` | High-power replication when testing small microsecond differences |

The recorded benchmark corpus in `test_results/` (catalogued in [07 Results and naming](07-results-and-naming.md) and analysed in [10 Empirical Results and Comparative Analysis](10-results-analysis.md)) uses 2 to 3 repeats per sweep, reports the median and full min–max range across repeats, and requires non-overlapping ranges before calling any difference real.

### Error % is not meaningful for tiny round trips

When a run's median kernel RTT is under **100 µs** (loopback, or a very fast local link), an ordinary 100 µs wake-up is already 100 % or more of the round trip. For such runs:
- error % is shown as "not meaningful" / "n/m";
- it is left out of best/worst, and the reports say so;
- observer lag in µs is the figure to judge.

### Seeing the cause: ORM-work shading

Every engine reports, per endpoint cycle, when its ORM work started and ended (`db_start_ns`, `db_end_ns`, on the same `CLOCK_REALTIME` as the packets).
- **What the chart shows:** the intrusion-over-time chart shades those windows for the run picked in the drill-down. When the work is what delayed the packets, stacks of high-lag dots sit inside the shaded bands.
- **Python multi-core is the exception:** there the window is the offloaded job (from hand-over to result), so the dots should *not* line up with the bands.

## 4. Fairness rules between engines

| Item | Rule |
|---|---|
| packet bytes | identical echo request: 56-byte payload `EPHEMRES` + id + seq, then `0xA5` fill |
| clocks | Clock A from the kernel via `recvmsg` ancillary data; Clock B read immediately after the read call returns; both `CLOCK_REALTIME` |
| matching | `(icmp_id, icmp_seq)`, registered before sending so a fast reply cannot arrive before the program is ready for it |
| schedule | the same start-offset formula, interval, timeout and warm-up |
| ORM work | the same semaphore size, the same CPU-spin duration and the same 1 ms I/O sleep inside the semaphore |
| canary | the same 10 ms tick, gate and statistics |
| statistics | computed once on the server, not separately per language |
| receive queue | 8 MiB requested by every engine (force-set when root), so queue overflow does not masquerade as loss |
| NIC state | hardware timestamping off unless explicitly enabled (Python only); the comparison warns when runs differ |
| cycles, late replies, send lag | the same cycle schedule and sequence numbering; every engine reports late replies and send lag |

Some differences cannot be avoided: timer resolution (see above), each language's memory management, and the IPC cost that only Python's multi-core mode pays. They are part of what is being compared.

## 5. Experimental protocol and extensions for future studies

### Experimental design protocol

To evaluate the research questions in [01 Project scope](01-project-scope.md), the benchmark protocol varies one factor at a time around the Ephemres production defaults (`100` endpoints, `5` pings @ `8 s` interval, `60 s` cycle, `db_write_semaphore = 15`, `simulated_db_ms = 3.0 ms`):

1. **Host telemetry and baseline capture.**
   - Before every run, `server/hostinfo.py` records the CPU model, core/thread topology, kernel version, clocksource (`TSC`), CPU frequency governor (`powersave` vs. `performance`), deepest enabled CPU idle state (`C-states`), NIC interrupt (`IRQ`) core affinity, and 1-minute load average into the run's `.meta.json`.
   - When the host is run in its default untuned operating state, these recorded telemetry fields allow the analysis to check whether anomalies stem from power management or interrupt placement rather than the language runtime.
2. **Staggered vs. burst schedule sweeps.**
   - **Staggered (`stagger_window = 60 s`):** Models Ephemres's steady-state operating profile (`1.67` endpoints/s starting and finishing), swept across `db_write_semaphore` values (`5, 15, 30, 50`) and endpoint scales (`25, 100, 250`) across all six engine × CPU-mode combinations.
   - **Synchronised burst (`stagger_window = 0 s`):** Models worst-case simultaneous startup (`100` endpoints firing and completing their 5th ping simultaneously), swept across semaphore values (`5, 15, 50`) and single-core vs. multi-core modes.
3. **Separating Pings 1–4 from Ping 5 in burst analysis.**
   - In a 5-ping cycle under burst load, **Pings 1–4** arrive while all endpoints are still mid-cycle (`0` ORM spins running), whereas **Ping 5** (`icmp_seq % 5 == 4`) triggers the post-cycle semaphore acquisition and `3.0 ms` ORM spin across all endpoints simultaneously.
   - Because run-level `mean` and `p95` mix these two distinct phases together, burst runs must be decomposed into **Pings 1–4 Median** (pure send/receive burst overhead) and **Ping 5 Median** (post-cycle ORM serialisation stall).
4. **Same-session interleaved idle floors.**
   - Every batch configuration should be paired with an interleaved idle floor (`simulated_db_ms = 0.0`, recorded immediately before the loaded run via `Idle floor every round`) in rotating engine order (`Py → Go → Rs`, `Go → Rs → Py`, `Rs → Py → Go`) to prevent time-of-day thermal or power-state drift from biasing floor subtraction.

*(The complete inventory of the 173 recorded runs across Session 1 and Session 2 is catalogued in [07 Results and naming](07-results-and-naming.md), and their empirical findings are presented in [10 Empirical Results and Comparative Analysis](10-results-analysis.md).)*

### Open extensions for future research and replication

The step-by-step guide in [09 Replication guide](09-replication.md) documents both how to repeat the baseline protocol and how to execute stricter controls left open for extended studies:

1. **Locking CPU power states (`performance` governor, C-states disabled, turbo off, core isolation).**
   - Repeating the single-core staggered and burst sweeps with `cpupower frequency-set -g performance`, `cpupower idle-set -D 10`, and `isolcpus` on both sibling threads of the pinned physical core separates deep C-state wake-up latency from hyper-threading sibling contention and thermal drift.
2. **Sweeping CPU work duration (`simulated_db_ms`).**
   - Extending beyond `0.0 ms` (idle floor) and `3.0 ms` (the Ephemres estimate) to sweep `simulated_db_ms` across `0.5, 1, 2, 5, 10 ms` under both burst and staggered schedules.
3. **5-round batches with interleaved floors on every sweep.**
   - Running `5` repeats per configuration (`p = 0.008` on non-overlap) with **idle floor every round** enabled across all endpoint and semaphore sweeps.
4. **Isolating Python multi-core pure IPC overhead under burst (`db_write_semaphore ≤ CPUs − 1`).**
   - Running `py-mc` under burst with `db_write_semaphore` at or below the worker count (`CPUs − 1`, e.g., `7` on an 8-CPU host) vs. `15` to separate `pickle`/pipe serialisation time from worker-pool queue wait when all 100 endpoints finish together.
5. **Kernel transmit timestamps (`SOF_TIMESTAMPING_TX_SOFTWARE`).**
   - Capturing the transmit timestamp in the kernel rather than reading `tx` in user space before `sendto()`, removing the host send-path component from `kernel_rtt_us` under burst load.

## 6. Reading the results, and threats to validity

**What a result means.** Compare *observer lag* (intrusion) and its percentiles between runs:
- **Under a staggered schedule**, compare the **median (`p50`)**, **`p95`**, and **`p99`** against an **interleaved idle floor** recorded in the same session to determine whether post-cycle ORM work adds measurable delay above each runtime's baseline socket-read floor.
- **Under a burst schedule**, do **not** rely on the run-level `mean`, `p95`, or `Primary Error %` alone. Because early pings in a cycle arrive while no ORM work is running and only the final ping triggers the post-cycle ORM write, split the burst reading into **Pings 1–4 Median** and **Ping 5 Median** ([10](10-results-analysis.md) Table 2.4, Tables 3.1–3.3).
- **Kernel RTT** is the reference. If it shifts between staggered and burst runs (even when `simulated_db_ms = 0 ms`), that shift comes from the send pattern and local/target queueing, not from the ORM spin.

### A reading order

1. **Check comparability and sample size.**
   - Verify the runs share the same parameters and session (or use interleaved floors).
   - Check `n`: at least `200` replied packets for `p95`, `1,000` for `p99` (25-endpoint runs have `250` packets, so their `p99` is flagged `few samples` and not used for findings).
   - Check loss by cause (`no_reply`, `after_timeout`, `read_late`).
2. **Check the median (`p50`) and tail (`p95`, `p99`), plus Ping 5 in burst runs.**
   - Compare medians and min–max repeat ranges across repeats. Treat overlapping repeat ranges as no difference shown.
3. **Compare against the same-session idle floor.**
   - Subtract or compare against the floor recorded just before the test to see whether post-cycle ORM work added anything above the runtime's baseline read path.
4. **Separate internal vs. external effects.**
   - Compare intrusion against kernel RTT and send lag.
5. **Inspect the mechanism.**
   - Use the intrusion-over-time chart (with ORM-work shading), reader wakeups and queue depth (`reader_batch`), and the scheduler canary (`canary_max_us`).

### Dashboard comparison table and charts

Full reference tables for every comparison-table row group, best/worst (▼/▲) rule, and chart series are in [05 Dashboard](05-dashboard.md#3--comparison).

### Which evidence answers which question

| Question ([01](01-project-scope.md)) | Evidence used in [10 Results analysis](10-results-analysis.md) |
|---|---|
| 1. Size of the distortion, Python single-core | Staggered `py-sc` at Ephemres defaults (`100` ep, `60 s` stagger, `sem = 15`, `db = 3 ms`) compared against its interleaved idle floor (`db = 0 ms`): median (`p50`), mean, `p95`, `p99`, and Primary Error % |
| 2. Effect of load shape, endpoint count, and semaphore | Staggered vs burst comparisons (`stg60` vs `burst`), `sem-sweep` (`5, 30, 50`), `burst-sem` (`5, 15, 50`), and `ep-sweep` (`25, 100, 250`), broken down by Pings 1–4 vs Ping 5 and canary max |
| 3. How Go and Rust compare to Python (`asyncio`) under the same load | 6-way staggered comparisons (Tables 1.1, 1.4, 3.4) and single-core vs multi-core burst comparisons (Tables 2.3, 2.4, 3.1, 3.2, 3.3), directly benchmarking Go and Rust against the Python baseline |
| 4. What offloading gains and costs (`py-mc` vs `py-sc`) | Packet intrusion median/tail vs idle floor, event-loop canary reduction, and `ipc_ms` offload overhead (Table 1.3, Table 3.3) |
| 5. Practical implications for Ephemres and monitoring platforms (hardware scaling & runtime trade-offs) | Cross-table synthesis of idle floors (Table 1.2), single-core vs multi-core scaling (Tables 1.4, 3.3), and runtime advantages/disadvantages across Python, Go, and Rust (§R4 Questions 3 & 5) |

### Threats to validity

| Threat | Effect | Mitigation in the lab design & replication protocol (evaluated in [10](10-results-analysis.md)) |
|---|---|---|
| **Target overload or send-path queueing in burst mode** | kernel RTT shifts under burst even without ORM work | verify with burst idle floors (`db = 0 ms`); use `observer_lag_us` (`Clock B − Clock A`), where `tx` cancels out, to measure internal intrusion |
| **Loopback has no real wire** | kernel RTT is a few microseconds, so error % is thousands of % even for tiny lag | use loopback only for automated unit tests; run benchmarks against a physical or LAN target |
| **Receive-queue overflow** | the kernel drops replies, which looks like loss | all engines request an 8 MiB receive buffer (`16384 KiB` effective) and verify `lost = 0` |
| **Clock slew** | Clocks A and B are `CLOCK_REALTIME`, so an NTP step during a run would affect timestamps | verify `CLOCK_REALTIME` with `TSC` clocksource in `.meta.json` and check for monotonic continuity |
| **Send stamp in user space** | kernel RTT includes the `sendto()` syscall and any pause after reading `tx` | does not affect observer lag (`tx` cancels out); kernel transmit timestamping (`SOF_TIMESTAMPING_TX_SOFTWARE`) is an optional future extension |
| **Software timestamp placement** | Clock A is stamped when the kernel network stack handles the packet, not at the physical NIC | identical across all three engines; optional hardware stamps (`--hw`) exist in Python for cross-checking |
| **Host power states (C-states, governor, turbo)** | `powersave`, turbo, and deep sleep (`C10 ≈ 890 µs`) let wake-up latency and clock speed vary with load and time of day | logged automatically in `.meta.json`; for controlled replication, lock `performance` governor and disable deep C-states (`cpupower idle-set -D 10`, see [09](09-replication.md) §3) |
| **Hyper-threading sibling** | two logical CPUs sharing one physical core compete for execution resources when only one logical CPU is pinned | recorded as a host warning in `.meta.json`; for controlled replication, isolate both sibling logical CPUs |
| **NIC interrupts on the probe core** | IRQ processing and the probe could compete on one CPU | recorded in `.meta.json` and verified via `/proc/interrupts` and `effective_affinity_list`; steer NIC IRQs away from the probe core if needed |
| **Interrupt coalescing** | the NIC batches interrupts, delaying Clock A | affects kernel RTT, not observer lag; recorded via `ethtool -c` |
| **Drift during a session or a day** | host baseline speed can shift between morning, afternoon, and evening sessions | rotate engine order every round and record interleaved idle floors (`Idle floor every round`) immediately before each test |
| **Small repeat counts (2–3 repeats)** | 2–3 repeats cannot prove small microsecond differences at `p < 0.05` | require non-overlapping min–max ranges, report full repeat spreads, and use 5 repeats (`p = 0.008`) for formal statistical claims |
| **Simulated ORM work** | a fixed `3.0 ms` CPU spin has no memory-allocation or GC pressure | isolates pure scheduler and event-loop contention; sweeping `simulated_db_ms` and testing allocation-heavy GC workloads are documented extensions |

## 7. What the instrumentation itself costs

The dashboard needs events from the probe, and producing them is itself work the probe does.
- **What the probe sends:** one small JSON line per finished endpoint cycle, plus a heartbeat every 0.5 s.
- **How much it costs:** the time spent writing is measured per event and shown as "dashboard stream cost". It is typically tens of microseconds per event, against milliseconds of ORM work.
- **Why the dashboard stays out of the measurement:**
  - The web server runs in a different process on different cores, so its own work never shares the measured event loop.
  - The probe's output pipe is read continuously, so the probe never blocks waiting on the dashboard.
