# 10 Empirical Results and Comparative Analysis

This document analyses the **173 benchmark runs** recorded in `test_results/`:
- a first corpus of 90 runs (§R1, §R2);
- an 81-run follow-up session with interleaved floors (§R3).

**What was measured.** The ICMP observer effect is the distortion a monitoring program adds to the round-trip time it reports, through its own scheduling and post-processing. It was measured across:
- three runtimes: **Python asyncio**, **Go goroutines**, **Rust tokio**;
- two CPU modes: **single-core pinned** and **multi-core**;
- three semaphore sizes: **5, 30, 50**;
- three endpoint counts: **25, 100, 250**;
- two schedule shapes: **burst** and **staggered**.

**Idle-floor runs**, with no ORM work, are the baseline for each. Terms are defined in the [glossary](../README.md#glossary).

**How to read the numbers.**
- **Intrusion** is observer lag, the user-space read time minus the kernel arrival stamp ([02 Test methodology](02-test-methodology.md) §1).
- **Median** means the 50th percentile of a run's packets. **Mean** is reported separately, because in burst runs the two differ by up to 40×.
- Where a setting has repeats, a value is the median across repeats, with the min–max range in parentheses.
- **"Ping 5"** is the last ping of each endpoint's cycle (`icmp_seq % 5 == 4`), the one whose reply releases the endpoint into its database write.
- **What counts as a difference.**
  - With 2–3 repeats, a difference counts here only when the repeat ranges do not overlap, and even then it is exploratory: [02](02-test-methodology.md) §3 sets 5 repeats as the minimum for a claim.
  - The first corpus's floors are single runs, so differences of a few µs against them are within noise.
- **p99** needs about 1,000 packets ([02](02-test-methodology.md) §3). The 25-endpoint runs have 250 packets, so their p99 is not reported as a finding.
- Statements marked *hypothesis* fit the data but were not tested by a dedicated run.
- **Only interleaved comparisons are trusted.** The machine's state drifts during the day by more than any staggered intrusion (§R3.4, §R3.5). A floor is matched to a test only when it was recorded in the same session, ideally just before it.

---

## Executive Summary

The first corpus has **94,500 analysed packets** to a local-network target (`192.168.70.2`, staggered kernel RTT ≈ 370–480 µs). Together with the follow-up session, the data shows:

1. **Under the Ephemres staggered load, the ORM work adds no measurable intrusion.** That load is 100 endpoints, a 60 s stagger, semaphore 15 and 3 ms of ORM work.
   - Python single-core has a median intrusion of **100.8 µs** (mean 121.1 µs, p95 187.2 µs), **27.3 %** of the kernel RTT. Go and Rust single-core have a median of **70–75 µs**.
   - Floors recorded just before each test match them: within ±2 µs at the median for Python and Rust, overlapping ranges for Go, and overlapping p99 ranges for all three (§R3.4). The cost is each engine's own read path, paid with or without the ORM work.
2. **Only the burst schedule produces real intrusion, and it splits the engines.** Burst means a 0 s stagger.
   - **Python** is slow on every packet, at ≈ 1–2.5 ms. It pays the same with no ORM work: the burst floor recorded just before each test matches it (§R3.2). The level depends on a machine state that changed during the day (§R3.5).
   - **Go and Rust** read pings 1–4 within ≈ 0.03–0.3 ms, and their medians equal their floors'. The ORM work delays the last ping of each cycle.
     - Follow-up session: Rust ≈ 15–28 ms, Go ≈ 43–79 ms.
     - First session: Rust ≈ 48 ms, Go up to 208 ms (§R2.3).
   - Means are pulled up by that one ping per cycle, so on their own they misrank the engines.
3. **A larger semaphore never shortens a burst stall** (§R3.1).
   - Rust's runtime freezes for ≈ sem × 3 ms (canary 16, 43 and 149 ms at sem 5, 15 and 50). Its reader waits that long only at sem 5 (15 ms); at 15 and 50 it waits ≈ 24 ms.
   - Go shows no semaphore effect.
4. **Multi-core helps the tail, and in a burst it helps Go most.**
   - Staggered: Go and Rust p99 falls from ≈ 370–920 µs to ≈ 110–140 µs while the median moves 3–6 µs. The same gap is in the idle floors, so it comes with pinning to the probe core. It is not caused by NIC interrupts, which never ran there (§R3.6).
   - Burst: Go multi-core reads ping 5 in 46 µs, Rust's delay falls to ≈ 3 ms, and Python does not change (§R3.3).
5. **Python's ≈ 100 µs is its baseline read cost.** The Python multi-core floor, with no ORM work and no worker pool, also has a 100.3 µs median. Offloading to a `ProcessPoolExecutor` costs ≈ **0.74 ms** per write and leaves the median where it was.
6. **Three first-session findings did not reproduce once floors were interleaved:**
   - Python degrading at 250 endpoints (§R3.4);
   - the 43 % burst-floor share in Table 2.6 (§R3.2);
   - the morning burst stall sizes (§R3.1).
7. **No packets were lost.** Across all 173 runs every packet was answered and read in time (`no_reply = 0`, `after_timeout = 0`, `read_late = 0`).

---

## Dataset Architecture & Corpus Mapping

The first 90 runs were recorded on 2026-10-24 and on 2026-10-25 up to 14:50, the follow-up session on 2026-10-25 from 19:11 to 23:16, all on one host: an Intel Core i5-8250U, Linux kernel 7.0.0-38-generic, `powersave` governor, TSC clocksource, probe pinned to core 7. Every run produced three files (`.csv`, `_cycles.csv`, `.meta.json`) and an entry in `test_results/INDEX.md`.

```
test_results/ (90 runs, 270 artifact files + INDEX.md)
├── floor (12 runs)
│   ├── Staggered Idle Floor (db = 0.0ms, sem = 15, stg = 60s): 6 runs (1 per config), 2026-10-24
│   └── Burst Idle Floor     (db = 0.0ms, sem = 15, stg = 0s) : 6 runs (1 per config), 2026-10-25
├── sem-sweep (54 runs, 2026-10-24)
│   ├── Semaphore = 5  (db = 3.0ms, stg = 60s): 18 runs (3 repeats × 6 configs)
│   ├── Semaphore = 30 (db = 3.0ms, stg = 60s): 18 runs (3 repeats × 6 configs)
│   └── Semaphore = 50 (db = 3.0ms, stg = 60s): 18 runs (3 repeats × 6 configs)
├── ep-sweep (18 runs, 2026-10-25)
│   ├── 25 Endpoints  (sem = 15, db = 3.0ms, stg = 60s): 6 runs (2 repeats × 3 sc configs)
│   ├── 100 Endpoints (sem = 15, db = 3.0ms, stg = 60s): 6 runs (2 repeats × 3 sc configs)
│   └── 250 Endpoints (sem = 15, db = 3.0ms, stg = 60s): 6 runs (2 repeats × 3 sc configs)
└── burst (6 runs, 2026-10-25)
    └── 100 Endpoints Burst (sem = 15, db = 3.0ms, stg = 0s): 6 runs (2 repeats × 3 sc configs)

follow-up session (81 runs, 2026-10-25 19:11–23:16, §R3)
├── burst-sem: burst sc, sem 5 / 15 / 50, db 3 ms: 27 runs (3 repeats × 3 engines × 3 sems)
├── burst-mc:  burst mc, sem 15, db 3 ms: 9 runs (3 repeats × 3 engines)
├── ep-sweep:  staggered sc, 25 and 250 endpoints, db 3 ms: 12 runs (2 repeats × 3 engines × 2)
├── same-day:  staggered sc, 100 endpoints, db 3 ms: 6 runs (2 repeats × 3 engines)
└── floor:     27 runs: 9 burst sem 15 and 6 staggered 100-endpoint floors, each just before
               its test; 12 staggered floors at 25 and 250 endpoints, an hour after their tests

interrupted attempt (2 runs, 18:56–18:59): Python burst floor and test, used only in Table 3.5
```

As the methodology requires ([02 Test methodology](02-test-methodology.md) §2), cycle 0 of every 3-cycle run is excluded as warm-up. This leaves 1,000 packets per 100-endpoint run, 250 per 25-endpoint run and 2,500 per 250-endpoint run.

**Day effect.** The staggered floors and the semaphore sweep were recorded on 2026-10-24, the endpoint sweep and burst runs on 2026-10-25. At equivalent settings the 2026-10-25 daytime runs have a p99 about 200 µs heavier (Python single-core p99 580.1 µs at 100 endpoints and sem 15, against 346.5–436.3 µs across the 2026-10-24 semaphore runs). The follow-up session's tail was lighter again: 340.9 µs at the same setting (§R3.4). The drift is a state of the machine at the time of a run, not of the day, so comparisons across sessions are marked as such.

---

## R1. Engine & Core Mode Comparative Analysis

### R1.1 Ephemres Workload Baseline Comparison

Table 1.1 compares all six runtime and CPU-mode combinations under the staggered load: 100 endpoints, 8 s interval, 60 s cycle, 60 s stagger window, 3 cycles with cycle 0 excluded, target `192.168.70.2`.

The two halves of the table come from different runs:
- **Single-core** (`py-sc`, `go-sc`, `rs-sc`) is from the 100-endpoint endpoint-sweep runs: sem 15, 2026-10-25.
- **Multi-core** (`py-mc`, `go-mc`, `rs-mc`) is from the semaphore sweep at sem 30, 2026-10-24.

The semaphore makes no measurable difference when staggered (§R2.1). The day does, mostly in the tail, so for a same-day single-core vs multi-core comparison use Table 1.4.

#### Table 1.1: Engine & Core Mode Baseline Comparative Performance

| Metric | Python SC (`py-sc`) | Go SC (`go-sc`) | Rust SC (`rs-sc`) | Python MC (`py-mc`) | Go MC (`go-mc`) | Rust MC (`rs-mc`) |
|---|---|---|---|---|---|---|
| **Intrusion Median (p50)** (µs) | **100.8** (99.6–102.0) | **74.7** (73.9–75.6) | **70.0** (68.0–72.1) | **98.5** (97.7–102.5) | **71.2** (70.8–72.7) | **68.1** (67.7–69.2) |
| **Intrusion Mean** (µs) | **121.1** (119.9–122.3) | **88.4** (81.3–95.5) | **96.3** (90.0–102.5) | **106.5** (102.0–109.3) | **69.9** (69.7–72.2) | **71.7** (69.7–72.3) |
| **Intrusion p95** (µs) | **187.3** (180.6–193.9) | **152.2** (115.5–188.9) | **140.7** (135.8–145.6) | **169.3** (160.0–170.8) | **109.6** (107.9–110.1) | **103.8** (101.9–105.2) |
| **Intrusion p99** (µs) | 580.1 (362.7–797.5) | 539.1 (444.9–633.4) | 921.1 (865.3–976.9) | 207.1 (204.6–241.5) | 135.7 (125.4–140.7) | 120.2 (116.0–139.3) |
| **Intrusion Max** (ms) | **2.66** (2.40–2.91) | **3.15** (3.13–3.17) | **2.90** (2.00–3.80) | **0.99** (0.56–1.72) | **0.60** (0.58–2.39) | **3.13** (3.11–3.16) |
| **Primary Error %** (`total lag ÷ total kRTT`) | **27.3%** (26.2–28.3%) | **20.2%** (19.2–21.1%) | **22.7%** (21.6–23.8%) | **24.4%** (24.3–24.8%) | **15.5%** (15.3–15.9%) | **15.9%** (15.1–16.1%) |
| **Kernel Control RTT** (µs) | 444.7 (432.4–457.0) | 437.2 (422.5–451.9) | 423.1 (416.0–430.1) | 429.7 (418.1–450.0) | 454.0 (449.7–456.6) | 450.4 (448.1–461.0) |
| **Observer RTT** (µs) | 565.8 (554.7–576.9) | 525.6 (503.8–547.4) | 519.3 (506.0–532.6) | 536.1 (520.0–559.3) | 526.2 (519.5–526.4) | 522.1 (520.4–530.7) |
| **Send Lag Mean** (µs) | 907.6 (895.5–919.7) | 634.5 (619.3–649.6) | 893.6 (876.3–910.9) | 858.6 (834.9–886.5) | 634.6 (617.8–639.8) | 1510.0 (1480.0–1520.0) |
| **Canary Avg Lag** (µs) | 333.2 (327.6–338.8) | 331.8 (298.0–365.5) | 1175.0 (1160.0–1190.0) | 276.5 (275.1–312.6) | 329.4 (323.0–333.5) | 1170.0 (1170.0–1180.0) |
| **Canary Max Lag** (ms) | 8.26 (7.79–8.73) | 7.91 (7.51–8.31) | 6.77 (6.20–7.34) | 4.93 (4.89–5.59) | 5.07 (2.90–6.29) | 6.29 (6.07–7.00) |
| **Reader Wakeups / Packets** | 690.5 / 1000 | 681.5 / 1000 | 680.0 / 1000 | 693.0 / 1000 | 684.0 / 1000 | 682.0 / 1000 |
| **Queue Depth (pkts/wakeup)** | 1.45 | 1.47 | 1.47 | 1.44 | 1.46 | 1.47 |
| **Packet Loss (no/late/timeout)** | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

Mean and max columns are the mean of the two repeats for single-core, and the median of three for multi-core.

#### Key Takeaways:
- **Python costs ≈ 30 µs more per packet.** Python's median (≈ 100 µs) is ≈ 26–33 µs above Go and Rust (68–75 µs) in both CPU modes. The idle floors show the same gap (§R1.2), so this is the cost of Python's read path, not of the load.
- **Medians hide a long single-core tail.** The single-core mean sits 17–26 µs above the median for every engine. The cause is a p99 of 539–921 µs, against 120–207 µs for multi-core. Go and Rust single-core are in practice equal: medians 74.7 vs 70.0 µs, with overlapping p95 ranges.
- **Multi-core moves the tail, not the median.** §R1.4 shows this on same-day data, and that the gap exists without ORM work.
- **The Rust canary reads ≈ 1.17 ms because of its timer.** The canary is a periodic sleep. Tokio's timer has 1 ms granularity ([04 Engines](04-engines.md) §Known runtime behaviour), so its sleeps overshoot by up to 1 ms. This says nothing about how promptly Rust reads packets: its intrusion is the lowest of the three engines. Python's and Go's canaries resolve sub-millisecond sleeps, at ≈ 275–333 µs.

---

### R1.2 Idle Floor Quantification and Net Intrusion

Even with no ORM work, every runtime has a wake-up cost for reading a packet from the raw socket. Table 1.2 lists the staggered idle floors (`db = 0.0 ms`, recorded on 2026-10-24) and the net intrusion, Δ = loaded mean − floor mean. The loaded values are the Table 1.1 means.

#### Table 1.2: Runtime Idle Floors and Net Intrusion Above Floor

| Configuration | Floor Intrusion Median (µs) | Floor Intrusion Mean (µs) | Floor Intrusion p95 (µs) | Floor p99 (µs) | Floor Primary Error % | Loaded Intrusion Mean (µs) | Net Mean Intrusion (µs) | Net p95 Intrusion (µs) |
|---|---|---|---|---|---|---|---|---|
| **Python SC (`py-sc`)** | 98.3 | **111.3** | 174.6 | 334.6 | 23.4% | 121.1 | **+9.8** | **+12.7** |
| **Go SC (`go-sc`)** | 72.2 | **86.2** | 139.3 | 563.9 | 19.0% | 88.4 | **+2.2** | **+12.9** |
| **Rust SC (`rs-sc`)** | 71.8 | **86.0** | 124.3 | 621.7 | 18.7% | 96.3 | **+10.3** | **+16.4** |
| **Python MC (`py-mc`)** | 100.3 | **112.9** | 176.6 | 433.2 | 24.8% | 106.5 | **-6.4** | **-7.3** |
| **Go MC (`go-mc`)** | 69.7 | **70.8** | 105.9 | 138.0 | 15.4% | 69.9 | **-0.9** | **+3.7** |
| **Rust MC (`rs-mc`)** | 69.0 | **74.5** | 108.4 | 136.4 | 15.9% | 71.7 | **-2.8** | **-4.6** |

#### Reading the net intrusion:
- **Under a staggered schedule the net effect of the ORM work is not distinguishable from zero.** Every Δ lies between −7.3 and +16.4 µs. That is no larger than the spread between repeats of the same setting (for example `py-mc` sem 5 means range 110.4–118.8 µs, `rs-sc` ep-100 means 90.0–102.5 µs). Each floor is a single run, and the single-core loaded values come from a different day.
- **The negative values are best read as noise.** A *hypothesis* sometimes offered is that deep CPU C-states make the idle floor slower: the host has C10 enabled, with ≈ 890 µs exit latency, and the dashboard warns about it. That hypothesis is not supported here, for two reasons:
  - The ORM spin uses ≈ 0.5 % of the CPU at this load (100 × 3 ms per 60 s), too little to keep the core out of deep sleep.
  - The differences are inside the noise band.

  Testing it would take floors and loaded runs interleaved on the same day, with C-states limited (`cpupower idle-set` or a PM-QoS latency request).
- **The floors carry the single-core tail.** The single-core floors already have a p99 of 335–622 µs against 136–138 µs for Go and Rust multi-core, with no ORM work running. §R1.4 discusses the cause.

---

### R1.3 Python Multi-Core (`py-mc`) Offload Overhead Analysis

In `py-mc`, the event loop sends the simulated ORM work (`server/orm_burn.py`) to a `ProcessPoolExecutor` of 7 worker processes (`spawn` method). The dict payload of packet records, sequence numbers and timestamps is serialised with `pickle` across IPC pipes.

The offload overhead is the total offload wall time minus the worker's own 3.0 ms burn. It was measured in the 9 loaded `py-mc` runs of the semaphore sweep:

#### Table 1.3: Python Multi-Core ORM Offload Overhead (`ipc_ms`)

| Metric | Semaphore 5 | Semaphore 30 | Semaphore 50 | Overall py-mc Corpus |
|---|---|---|---|---|
| **Mean Offload Delay (`ipc_ms_mean`)** | 0.786 ms (0.718–0.808) | 0.726 ms (0.677–0.733) | 0.767 ms (0.741–0.771) | **0.741 ms** (range 0.677–0.808 ms) |
| **Max Offload Delay (`ipc_ms_max`)** | 5.610 ms (3.912–11.624) | 3.227 ms (1.740–4.721) | 4.366 ms (3.344–12.110) | **4.366 ms** (peaks 11.62 ms & 12.11 ms) |
| **Event-Loop Canary Avg** | 313.8 µs (309.9–316.8) | 276.5 µs (275.1–312.6) | 254.1 µs (252.1–260.7) | **276.5 µs** |
| **Same-day `py-sc` Canary Avg** | 334.0 µs | 336.6 µs | 327.5 µs | - |
| **Observer Intrusion Median** | 99.2 µs (97.3–100.8) | 98.5 µs (97.7–102.5) | 100.1 µs (98.4–101.1) | - |
| **Same-day `py-sc` Intrusion Median** | 101.2 µs | 100.4 µs | 100.6 µs | - |
| **Observer Intrusion Mean** | 117.0 µs (110.4–118.8) | 106.5 µs (102.0–109.3) | 109.7 µs (106.2–111.1) | **109.7 µs** |

The same-day `py-sc` rows are the single-core semaphore-sweep runs from 2026-10-24.

#### Analysis:
1. **What Python gains: a calmer event loop.** The loop no longer runs the 3 ms burn inline, so its canary average falls by 20–73 µs against same-day single-core runs (334 → 314, 337 → 277, 328 → 254 µs).
2. **What Python pays: ≈ 0.74 ms per write.** Moving the payload between processes adds **0.741 ms** on average to each offloaded write, with peaks of **11.6–12.1 ms**.
3. **The packet median does not move.** Python's median intrusion is ≈ 98–101 µs with and without the offload, on the same day. The Python **multi-core idle floor**, with no ORM work and no worker pool, has a **100.3 µs** median too. So the ≈ 30 µs gap to Go and Rust is Python's baseline read cost. It is not caused by GIL contention or pipe handling: those exist only when there is ORM work to offload, and the floor has none.

---

### R1.4 Single-Core vs Multi-Core on Same-Day Data

Table 1.4 compares the two CPU modes within the 2026-10-24 semaphore sweep, plus the staggered floors from the same day. The values are packet medians and p99s, as the median of three repeats.

#### Table 1.4: Single-core vs multi-core, staggered, 2026-10-24

| Engine | Set | SC Median | MC Median | SC p99 | MC p99 |
|---|---|---|---|---|---|
| Python | floor | 98.3 µs | 100.3 µs | 334.6 µs | 433.2 µs |
| Python | sem 5 / 30 / 50 | 101.2 / 100.4 / 100.6 µs | 99.2 / 98.5 / 100.1 µs | 346.5 / 389.3 / 436.3 µs | 424.1 / 207.1 / 311.4 µs |
| Go | floor | 72.2 µs | 69.7 µs | 563.9 µs | 138.0 µs |
| Go | sem 5 / 30 / 50 | 76.7 / 74.8 / 73.8 µs | 68.9 / 71.2 / 69.9 µs | 372.0 / 478.3 / 512.5 µs | 112.1 / 135.7 / 128.2 µs |
| Rust | floor | 71.8 µs | 69.0 µs | 621.7 µs | 136.4 µs |
| Rust | sem 5 / 30 / 50 | 73.1 / 72.4 / 71.7 µs | 67.3 / 68.1 / 69.9 µs | 506.0 / 571.1 / 509.5 µs | 111.9 / 120.2 / 140.3 µs |

#### Findings:
- **For Go and Rust, multi-core cuts p99 by a factor of 3–5 and moves the median by only 2–8 µs.** That is why their means fall from ≈ 85–91 µs to ≈ 65–73 µs, while the typical packet hardly changes.
- **The single-core tail exists without ORM work.** The single-core floors have the same heavy p99 (564 and 622 µs) as the loaded runs. Separating packet reading from the CPU burn therefore cannot be what removes it.
- **Cause: not the NIC interrupt.** Every host report warns that the network card's interrupts (`enp0s31f6`, IRQ 159, allowed on CPUs 0–7) may be handled on core 7. In fact all of them ran on CPU 5 (§R3.6). The remaining *hypotheses* are:
  - the hyper-threading sibling, CPU 3, which shares the physical core;
  - the `powersave` governor and deep C-states on a lightly loaded pinned core.

  To test them, isolate core 7 and CPU 3 and repeat the single-core floor, with and without C-states limited.
- **Python gains nothing at the median.** Its p99 is mixed (sem 30 is better, the floor and sem 5 are not), so there is no consistent multi-core benefit for Python.

---

## R2. Sensitivity & Scaling Sweeps Analysis

### R2.1 Semaphore Sweep (`sem-sweep`)

The semaphore (`db_write_semaphore`) limits how many endpoints may run their post-cycle ORM write at the same time. Table 2.1 compares semaphores 5, 30 and 50 across all six configurations: 3 repeats each, 18 runs per semaphore, 54 runs in total.

#### Table 2.1: Semaphore Sweep Performance (Medians across 3 Repeats)

| Config | Semaphore 5 Mean / p95 | Semaphore 5 Err% | Semaphore 30 Mean / p95 | Semaphore 30 Err% | Semaphore 50 Mean / p95 | Semaphore 50 Err% |
|---|---|---|---|---|---|---|
| **`py-sc`** | 112.2 µs / 174.4 µs | 24.2% | 113.6 µs / 176.5 µs | 24.2% | 116.1 µs / 176.3 µs | 25.4% |
| **`go-sc`** | 85.1 µs / 115.9 µs | 18.5% | 91.3 µs / 130.9 µs | 19.5% | 89.2 µs / 120.0 µs | 19.7% |
| **`rs-sc`** | 86.7 µs / 112.2 µs | 18.7% | 88.7 µs / 120.3 µs | 20.4% | 88.8 µs / 120.9 µs | 20.0% |
| **`py-mc`** | 117.0 µs / 172.4 µs | 26.2% | 106.5 µs / 169.3 µs | 24.4% | 109.7 µs / 166.1 µs | 28.3% |
| **`go-mc`** | 68.6 µs / 94.6 µs | 15.4% | 69.9 µs / 109.6 µs | 15.5% | 67.1 µs / 104.8 µs | 15.4% |
| **`rs-mc`** | 64.8 µs / 93.8 µs | 14.8% | 71.7 µs / 103.8 µs | 15.9% | 72.6 µs / 105.2 µs | 16.0% |

The packet medians for sem 5 / 30 / 50 are in Table 1.4. They do not move by more than ≈ 3 µs for any engine.

#### Observations:
- **The semaphore makes no difference under a 60 s stagger.** For all six runtimes, the repeat ranges at sem 5, 30 and 50 overlap for the median, mean and p95.
  - The p99 of `py-sc` looks as if it rises (346.5 → 389.3 → 436.3 µs), but its ranges overlap widely (sem 5: 282.1–591.5 µs).
  - The single-core Go floor's p99 (563.9 µs) is higher than any of the Go tests.
- **Mechanism.** With 100 endpoints spread over 60 s, an endpoint finishes its pings about every 600 ms. Each ORM write takes 3 ms of CPU plus 1 ms of async wait, about 4 ms, so the average number of writers at one time is

  ```text
  Mean Concurrent Writers = (100 × 4 ms) ÷ 60,000 ms = 0.0067 ≪ 1
  ```

  Even with chance clustering, a cap of 5 is almost never reached. The semaphore can only matter when many writes start together, which means a burst schedule. Under burst it was measured in the follow-up session (§R3.1). A larger semaphore never shortened the stall there.

---

### R2.2 Endpoint Scaling Sweep (`ep-sweep`)

Table 2.2 covers 25, 100 and 250 endpoints for the single-core runtimes (`py-sc`, `go-sc`, `rs-sc`), with semaphore 15 and a 60 s stagger. These are the first-corpus runs. The follow-up session repeated 25 and 250 endpoints and added floors at both (§R3.4), and did not confirm insight 1 below.

#### Table 2.2: Endpoint Scaling Sweep Performance (Medians across Repeats)

| Config | Endpoints | Intrusion Median | Intrusion Mean | Intrusion p95 | Intrusion Max | Primary Error % | Canary Avg | Wakeups / Packets | Pkts/Wakeup |
|---|---|---|---|---|---|---|---|---|---|
| **`py-sc`** | 25 | 98.1 µs (97–100) | 113.5 µs | 171.7 µs | 1.24 ms | 25.7% | 286.6 µs | 172.5 / 250 | 1.45 |
| | 100 | 100.8 µs (100–102) | 121.1 µs | 187.3 µs | 2.66 ms | 27.3% | 333.2 µs | 690.5 / 1000 | 1.45 |
| | 250 | **113.7 µs** (109–119) | **131.9 µs** | **203.8 µs** | **3.71 ms** | **30.5%** | **409.2 µs** | 1720.5 / 2500 | 1.45 |
| **`go-sc`** | 25 | 74.2 µs (74–75) | 87.2 µs | 167.3 µs | 0.70 ms | 20.8% | 295.7 µs | 170.5 / 250 | 1.47 |
| | 100 | 74.7 µs (74–76) | 88.4 µs | 152.2 µs | 3.15 ms | 20.2% | 331.8 µs | 681.5 / 1000 | 1.47 |
| | 250 | 57.0 µs (47–67) | **87.1 µs** | **165.9 µs** | **3.31 ms** | **21.6%** | **316.0 µs** | 1704.5 / 2500 | 1.47 |
| **`rs-sc`** | 25 | 72.5 µs (72–73) | 87.9 µs | 177.0 µs | 1.27 ms | 20.4% | 1180.0 µs | 170.5 / 250 | 1.47 |
| | 100 | 70.0 µs (68–72) | 96.3 µs | 140.7 µs | 2.90 ms | 22.7% | 1175.0 µs | 680.0 / 1000 | 1.47 |
| | 250 | 71.6 µs (72–72) | **79.9 µs** | **113.7 µs** | **2.19 ms** | **18.6%** | **1170.0 µs** | 1700.5 / 2500 | 1.47 |

#### Key Insights:
1. **Python looked worse at 250 endpoints in these runs, but this did not reproduce** (§R3.4: 87.9 µs at 250 endpoints in the follow-up session).
   - Its median is 98.1 and 100.8 µs at 25 and 100 endpoints, then **113.7 µs** at 250, outside both lower ranges. The mean rises 113.5 → 121.1 → 131.9 µs.
   - The event-loop canary rises **286.6 → 333.2 → 409.2 µs** with no overlap between repeats. This is the clearest load-scaling signal in the staggered data.
   - The 100 → 250 step in mean is not separate (250 range 120–144 µs, 100 range 120–122 µs). So "rising with endpoint count" is well supported only for the median and canary at 250 endpoints.
2. **Go and Rust show no endpoint effect.** Their medians and means do not move outside the repeat noise.
   - Go's lower median at 250 (57.0 µs, range 47–67) and Rust's lower mean at 250 (79.9 µs) are better read as noise than as improvements.
   - The 25-endpoint p95s for Go and Rust are widely spread (130–205 and 136–218 µs), because each run has only 250 packets.
3. **Packets per wakeup stay at ≈ 1.45–1.47** at every scale. Under a stagger, replies arrive spread out and are read one or two at a time.

---

### R2.3 Schedule Impact: Burst (0 s) vs Staggered (60 s)

Table 2.3 contrasts burst mode (all 100 endpoints start together at `t = 0`) with staggered mode (start times spread over 60 s). Both are single-core, with 100 endpoints, sem 15 and db 3.0 ms, all recorded on 2026-10-25.

#### Table 2.3: Schedule Impact: Burst (0 s) vs Staggered (60 s)

| Metric | Python Staggered | Python Burst | Go Staggered | Go Burst | Rust Staggered | Rust Burst |
|---|---|---|---|---|---|---|
| **Intrusion Median (p50)** | **100.8 µs** | **2.30 ms** *(23x)* | **74.7 µs** | **0.32 ms** *(4.3x)* | **70.0 µs** | **0.16 ms** *(2.3x)* |
| **Intrusion Mean** | **121.1 µs** | **2.65 ms** *(21.9x)* | **88.4 µs** | **13.02 ms** *(147x)* | **96.3 µs** | **6.88 ms** *(71.5x)* |
| **Intrusion p95** | **187.3 µs** | **6.13 ms** *(32.7x)* | **152.2 µs** | **84.35 ms** *(554x)* | **140.7 µs** | **48.40 ms** *(344x)* |
| **Intrusion Max** | **2.66 ms** | **8.54 ms** | **3.15 ms** | **208.22 ms** | **2.90 ms** | **48.98 ms** |
| **Primary Error %** | **27.3%** | **1621.9%** | **20.2%** | **2216.5%** | **22.7%** | **998.8%** |
| **Canary Max Lag** | **8.26 ms** | **159.42 ms** | **7.91 ms** | **223.14 ms** | **6.77 ms** | **49.33 ms** |
| **Send Lag Mean** | 907.6 µs | **3.63 ms** | 634.5 µs | **1.37 ms** | 893.6 µs | **1.34 ms** |
| **Reader Wakeups** | 690.5 | **10** | 681.5 | **53** | 680.0 | **72** |
| **Queue Depth (pkts/wakeup)** | 1.45 | **100.0** | 1.47 | **18.9** | 1.47 | **13.9** |
| **Kernel Control RTT** | 444.7 µs | 163.8 µs | 437.2 µs | 594.7 µs | 423.1 µs | 691.5 µs |

#### Table 2.4: Burst intrusion split by ping

The last ping of each cycle is ping 5 (`icmp_seq % 5 == 4`). That is the ping whose reply releases the endpoint into its ORM write. Values are medians of the two repeats, with the range in parentheses.

| Burst, single-core | Pings 1–4 Median | Pings 1–4 Max | Ping 5 Median | Ping 5 Max |
|---|---|---|---|---|
| Python | 2.52 ms (2.46–2.58) | 8.54 ms | 1.76 ms (1.66–1.86) | 3.04 ms |
| Go | 0.22 ms (0.18–0.26) | 1.10 ms | 62.6 ms (0.75–124.4) | 208.22 ms |
| Rust | 0.13 ms (0.12–0.14) | 0.67 ms | 47.27 ms (47.26–47.28) | 48.98 ms |

```
                BURST INTRUSION: MEDIAN vs TAIL (single-core)
              Median (typical packet)          p95 (one ping per cycle)
   Python     ██ 2.30 ms                       ███ 6.13 ms
   Go         ▏ 0.32 ms                        ████████████████████████████████████ 84.35 ms
   Rust       ▏ 0.16 ms                        ████████████████████ 48.40 ms
```

#### Burst Dynamics:
1. **Python and the compiled engines fail in opposite ways.**
   - Python is slow on every ping: a 2.3 ms median, with the worst packet at 8.5 ms.
   - Go and Rust read pings 1–4 within ≈ 0.1–0.3 ms. Their whole tail sits on ping 5, which in each run is read in 2–3 single late wakeups (one per cycle).
   - The means and error % in Table 2.3 combine these two behaviours. They should not be used on their own to rank the engines under burst.
2. **Rust's ≈ 48 ms matched one full semaphore of spins in these runs only.**
   - When the burst's last replies arrive, the endpoint tasks that receive them start their 3 ms ORM spin on the one thread. With sem 15, 15 × 3 ms ≈ 45 ms of spinning can run before the reader task is scheduled again. Rust's ping-5 median (47.27 ms) and canary max (≈ 48–50 ms) matched that.
   - The follow-up session tested it (§R3.1). The canary still follows ≈ sem × 3 ms, but the reader's ping-5 delay was ≈ 24 ms at both sem 15 and sem 50, and 15 ms at sem 5. The 47 ms seen here did not reproduce.
3. **Go single-core stalls longer, and unevenly.**
   - Its ping-5 delay ranges from 0.75 ms to 124 ms between the two repeats (median), and up to 208 ms at worst. The canary is starved for up to 281 ms.
   - Go 1.22 does preempt long-running goroutines, but only after ≈ 10 ms. Each spin lasts 3 ms, so preemption does not help.
   - *Hypothesis:* with `GOMAXPROCS=1`, goroutines woken by the network poller and timers are queued behind the many goroutines made runnable by the burst, so the reader waits for more than one semaphore's worth of work.
   - In the follow-up session the Go max was 43–79 ms at every semaphore, and multi-core Go removed the stall (§R3.1, §R3.3).
4. **Python reads in large batches because of the burst, not the ORM work.**
   - Python reads 100 packets per wakeup, but the burst idle floor (no ORM work, §R2.4) does the same.
   - In the loaded burst, pings 1–4 (no ORM work near them) have a **higher** median (2.52 ms) than ping 5 (1.76 ms).
   - The cost comes from one event loop sending 100 requests and handling 100 replies at once. Send lag supports this: 3.63 ms mean, against 2.14 ms in the floor.
   - The ≈ 1.5 ms gap between these tests and the floor is **not** caused by the ORM work. The tests (10:35) ran in a slow machine state and the floors (14:33) in a fast one. Floors and tests recorded back to back agree (§R3.2, §R3.5).
5. **Burst also moves the kernel-measured RTT.** In this data it is not "unaffected", and it is not purely a wire effect.
   - Under burst, the kernel control RTT falls to ≈ 150–250 µs for Python and rises to ≈ 525–890 µs for Go and Rust. The same happens in the burst floors, without ORM work (Table 2.5).
   - `tx` is read in user space just before `sendto()` ([02](02-test-methodology.md) §1), so this RTT includes the host's own send path. A tight Go or Rust burst queues requests on the local send path and at the target. Python's slower, serial sends queue less.
   - Python's burst RTT is below even the staggered value (≈ 420 µs). One *hypothesis* is that steady traffic keeps the CPU and NIC out of deep power-saving states.
   - Either way, the RTT a monitor reports under burst is shifted on both sides of the program. The intrusion figure (lag) measures only the program's own part.
6. **Still no loss.** All burst packets were answered and read before the 2 s timeout.

---

### R2.4 Burst Idle Floors (no ORM work)

The six burst floors repeat the burst schedule with `db = 0.0 ms`, one run per engine and CPU mode, on 2026-10-25. They separate the cost of the burst itself from the cost of the ORM work.

#### Table 2.5: Burst idle floors (100 endpoints, stagger 0 s, db 0 ms)

| Config | Median | Mean | p95 | Max | Pings 1–4 Median | Ping 5 Median | Ping 5 Max | Pkts/Wakeup | Canary Max | Kernel RTT Median | Send Lag Mean | Error % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **`py-sc`** | 984.1 µs | 994.6 µs | 1652.8 µs | 2.10 ms | 1008.7 µs | 928.7 µs | 1.64 ms | 100.0 | 59.21 ms | 246.9 µs | 2137.1 µs | 376.5% |
| **`go-sc`** | 68.0 µs | 1082.1 µs | 5131.7 µs | 13.92 ms | 40.5 µs | 4421.6 µs | 13.92 ms | 7.4 | 19.46 ms | 746.7 µs | 1071.4 µs | 137.3% |
| **`rs-sc`** | 67.5 µs | 345.8 µs | 2364.1 µs | 4.14 ms | 46.3 µs | 722.7 µs | 4.14 ms | 6.9 | 7.26 ms | 886.8 µs | 1126.1 µs | 37.6% |
| **`py-mc`** | 1205.5 µs | 1233.8 µs | 2456.8 µs | 3.46 ms | 1253.1 µs | 987.0 µs | 1.72 ms | 100.0 | 69.09 ms | 223.5 µs | 2370.5 µs | 552.7% |
| **`go-mc`** | 33.4 µs | 68.8 µs | 208.7 µs | 0.94 ms | 32.9 µs | 36.3 µs | 0.18 ms | 5.1 | 3.04 ms | 527.9 µs | 940.9 µs | 12.5% |
| **`rs-mc`** | 35.5 µs | 332.9 µs | 2029.1 µs | 2.37 ms | 29.6 µs | 1628.5 µs | 2.37 ms | 6.7 | 6.87 ms | 623.3 µs | 1727.6 µs | 48.5% |

#### Table 2.6: How much of the burst intrusion the ORM work adds (single-core medians), withdrawn

*Withdrawn.* This table compares the 10:35 tests with the 14:33 floors, which ran in different machine states (§R3.5). With interleaved floors, Python's floor and test match, and Go's and Rust's medians match their floors (Table 3.2). It is kept here only as a record.

| Engine | Burst floor median | Loaded burst median | Share present without ORM work |
|---|---|---|---|
| Python | 984.1 µs | 2295.0 µs | ≈ 43 % |
| Go | 68.0 µs | 321.1 µs | ≈ 21 % |
| Rust | 67.5 µs | 163.7 µs | ≈ 41 % |

#### Findings:
- **Python pays ≈ 1 ms per packet in a burst even with no ORM work,** in both CPU modes (984 µs single-core, 1,206 µs multi-core). It reads all 100 replies in one wakeup either way. Multi-core does not help, because the cost is in the one event loop.
- **Go and Rust read the last ping late even without ORM work.**
  - Go single-core: ping-5 median 4.4 ms, max 13.9 ms. Rust single-core: 0.7 ms and 4.1 ms. Rust multi-core: 1.6 ms.
  - So part of the end-of-cycle stall comes from the rest of the cycle's wrap-up: the semaphore, the 1 ms simulated I/O wait, and building and reporting results for 100 endpoints at once. The ORM spin turns a few milliseconds into 15–208 ms (Table 2.4, Table 3.1).
- **Go multi-core is the only configuration that handles a burst cleanly.** Its median is 33.4 µs, p95 208.7 µs, and ping 5 is no slower than pings 1–4. Rust multi-core still shows a late ping 5 (1.6 ms).
- **The canary is starved during a burst, even in the floors.** Python reaches 59–69 ms. Python multi-core is the higher of the two, so the offload is no protection here.
- **Loaded multi-core burst runs and a burst semaphore sweep** were recorded in the follow-up session (§R3.1, §R3.3). Go multi-core stays clean with ORM work on.

---

## R3. Follow-up Session: Burst Sweeps and Interleaved Floors

The follow-up session was recorded on 2026-10-25 from 19:11 to 23:16, after a network link drop at 19:03–19:08.
- **81 runs**, every packet answered and read in time.
- **The run hit by the link drop was deleted.** Two clean runs from that interrupted attempt (18:56–18:59) are used only in Table 3.5.
- **Engine order rotates each round.** In the burst sem-15 batch and the 100-endpoint staggered batch, each test is preceded by its own idle floor: same engine, recorded minutes earlier.
- **The 25- and 250-endpoint floors are not interleaved.** They were recorded at 22:33–23:16, about an hour after their tests (21:06–21:49).

**How to read Tables 3.1–3.5.**
- Each cell is the median across repeats, with the min–max range in parentheses.
- Per run, **Median** is the packet p50. **Pings 1–4** and **Ping 5** are the p50 of those pings only. **Max** is the worst packet. **Canary Max** is the longest delay of the engine's timer canary. **Kernel RTT** is the packet p50 of the kernel RTT.
- Every row is rebuilt from the packet CSVs by `verify_analysis.py --print-tables`.

### R3.1 Burst semaphore sweep (single-core, ORM on)

#### Table 3.1: Burst, single-core, 100 endpoints, db 3 ms, by semaphore

| Engine | Semaphore | Runs | Median | Pings 1–4 Median | Ping 5 Median | Max | Canary Max |
|---|---|---|---|---|---|---|---|
| Python | sem 5 | 3 | 1.19 ms (1.10–1.22) | 1.23 ms (1.14–1.25) | 1.01 ms (0.98–1.03) | 4.52 ms (3.27–4.64) | 79.36 ms (78.42–85.92) |
| Python | sem 15 | 3 | 1.22 ms (1.11–1.29) | 1.28 ms (1.12–1.30) | 1.01 ms (0.97–1.37) | 3.41 ms (2.19–3.49) | 107.87 ms (101.40–110.06) |
| Python | sem 50 | 3 | 1.48 ms (1.19–1.51) | 1.59 ms (1.24–1.76) | 975.1 µs (973.9–1060.5) | 3.52 ms (3.47–4.50) | 218.71 ms (213.89–218.97) |
| Go | sem 5 | 3 | 65.8 µs (40.7–80.7) | 37.4 µs (31.1–52.5) | 36.77 ms (0.42–62.42) | 59.16 ms (42.87–66.32) | 270.34 ms (248.82–310.08) |
| Go | sem 15 | 3 | 65.9 µs (56.7–78.0) | 40.6 µs (28.7–62.1) | 48.84 ms (0.45–57.57) | 53.05 ms (52.57–73.37) | 318.94 ms (271.24–328.70) |
| Go | sem 50 | 3 | 77.3 µs (46.5–79.6) | 60.6 µs (27.9–61.9) | 62.01 ms (49.04–68.97) | 78.87 ms (63.32–79.25) | 238.04 ms (237.87–265.38) |
| Rust | sem 5 | 3 | 32.3 µs (32.3–41.8) | 26.2 µs (24.8–33.7) | 15.21 ms (15.01–15.87) | 16.05 ms (15.84–17.31) | 15.83 ms (15.37–18.13) |
| Rust | sem 15 | 3 | 70.3 µs (57.9–72.3) | 55.0 µs (39.1–59.7) | 24.23 ms (21.57–27.86) | 27.85 ms (25.13–34.04) | 42.81 ms (40.39–45.65) |
| Rust | sem 50 | 3 | 69.9 µs (45.3–71.9) | 37.1 µs (28.4–46.7) | 24.46 ms (24.09–26.89) | 74.46 ms (24.77–156.09) | 148.51 ms (144.98–155.95) |

#### Findings:
- **Rust's runtime freezes for one semaphore's worth of spins, but its reader does not wait for all of it.**
  - The canary max grows with the semaphore: 15.83, 42.81 and 148.51 ms at sem 5, 15 and 50. That is ≈ sem × 3 ms (15, 45 and 150 ms), as §R2.3 predicted.
  - The reader follows that rule only at sem 5, reading ping 5 after 15.21 ms. At sem 15 and 50 it reads ping 5 after ≈ 24 ms in both cases, so its stall stops growing after about 8 spins. One sem-50 run still had a worst packet of 156 ms.
  - Why the reader gets in partway through a longer chain is not tested. *Hypothesis:* tokio's single-thread runtime polls its I/O driver after a fixed number of task polls, not only when the run queue is empty.
- **Go shows no semaphore effect.**
  - Ping-5 median and max overlap across sem 5, 15 and 50, with the max at 43–79 ms in every run.
  - With `GOMAXPROCS=1` only one spin runs at a time anyway. The semaphore decides how many goroutines hold a permit, not how much CPU work queues ahead of the reader.
  - The ping-5 median swings between repeats from 0.42 ms to 62 ms. Even the runs with a fast median have a max of 43–59 ms.
  - The canary is starved for 238–329 ms, about all 100 spins (100 × 3 ms).
- **Python's ICMP lag does not depend on the semaphore.** Ping 5 is ≈ 1.0 ms at every setting. Only the canary grows: 79.36, 107.87 and 218.71 ms, against 66 ms in the floor. The event loop is blocked for longer, but no reply is waiting while it is blocked (§R3.2).
- **A larger semaphore never shortens a burst stall.** For Rust's runtime and for Python's event loop it lengthens it.

### R3.2 Burst floors interleaved with tests (sem 15)

#### Table 3.2: Burst, single-core, sem 15: each test with the floor recorded just before it

| Engine | Run | Runs | Median | Mean | Ping 5 Median | Max | Canary Max | Kernel RTT Median |
|---|---|---|---|---|---|---|---|---|
| Python | floor | 3 | 1.11 ms (1.02–1.27) | 1.30 ms (1.03–1.36) | 1.02 ms (0.97–1.62) | 3.58 ms (2.16–3.80) | 66.09 ms (60.44–79.87) | 235.4 µs (211.7–248.2) |
| Python | test | 3 | 1.22 ms (1.11–1.29) | 1.29 ms (1.08–1.37) | 1.01 ms (0.97–1.37) | 3.41 ms (2.19–3.49) | 107.87 ms (101.40–110.06) | 225.6 µs (215.0–228.2) |
| Go | floor | 3 | 79.3 µs (73.7–82.2) | 626.6 µs (485.6–633.1) | 443.3 µs (368.7–532.1) | 7.30 ms (4.97–7.88) | 17.99 ms (9.99–21.27) | 680.1 µs (666.2–684.1) |
| Go | test | 3 | 65.9 µs (56.7–78.0) | 6.35 ms (4.48–8.60) | 48.84 ms (0.45–57.57) | 53.05 ms (52.57–73.37) | 318.94 ms (271.24–328.70) | 743.6 µs (670.1–747.4) |
| Rust | floor | 3 | 70.2 µs (61.9–72.0) | 370.9 µs (334.8–504.9) | 637.5 µs (596.9–1793.7) | 3.95 ms (3.45–4.91) | 7.26 ms (7.22–7.29) | 847.3 µs (821.5–875.5) |
| Rust | test | 3 | 70.3 µs (57.9–72.3) | 4.54 ms (4.47–5.54) | 24.23 ms (21.57–27.86) | 27.85 ms (25.13–34.04) | 42.81 ms (40.39–45.65) | 744.6 µs (737.6–889.4) |

#### Findings:
- **The ORM work adds nothing to Python's ICMP lag in a burst.**
  - Floor and test agree on every packet measure: median 1.11 vs 1.22 ms with overlapping ranges, and ping 5 at 1.02 vs 1.01 ms.
  - Only the canary rises, from 66.09 to 107.87 ms.
  - This replaces Table 2.6, which compared morning tests with afternoon floors (§R3.5).
- **For Go and Rust, the ORM effect is all on ping 5.**
  - Their medians equal the floor's, and pings 1–4 are untouched.
  - Ping 5 goes from 443.3 µs to 48.84 ms for Go, and from 637.5 µs to 24.23 ms for Rust.
  - The floor mean is ≈ 10 % of the test mean for Go (0.63 of 6.35 ms) and ≈ 8 % for Rust (0.37 of 4.54 ms).
- **Burst's shift in kernel RTT comes from the send pattern, not the ORM work.** Floor and test have the same kernel RTT: Python ≈ 225–235 µs, Go ≈ 680–745 µs, Rust ≈ 745–850 µs.

### R3.3 Multi-core under burst (ORM on, sem 15)

#### Table 3.3: Burst, 100 endpoints, db 3 ms, sem 15, by CPU mode

| Engine | CPU Mode | Runs | Median | Pings 1–4 Median | Ping 5 Median | Max | Canary Max |
|---|---|---|---|---|---|---|---|
| Python | single-core | 3 | 1.22 ms (1.11–1.29) | 1.28 ms (1.12–1.30) | 1.01 ms (0.97–1.37) | 3.41 ms (2.19–3.49) | 107.87 ms (101.40–110.06) |
| Python | multi-core | 3 | 1.13 ms (1.12–1.17) | 1.20 ms (1.06–1.21) | 1.01 ms (0.98–1.53) | 3.39 ms (3.24–3.48) | 74.34 ms (65.79–84.66) |
| Go | single-core | 3 | 65.9 µs (56.7–78.0) | 40.6 µs (28.7–62.1) | 48.84 ms (0.45–57.57) | 53.05 ms (52.57–73.37) | 318.94 ms (271.24–328.70) |
| Go | multi-core | 3 | 33.3 µs (32.1–33.8) | 31.3 µs (30.5–32.5) | 46.2 µs (36.5–85.7) | 869.2 µs (365.5–1440.1) | 2.98 ms (2.44–3.19) |
| Rust | single-core | 3 | 70.3 µs (57.9–72.3) | 55.0 µs (39.1–59.7) | 24.23 ms (21.57–27.86) | 27.85 ms (25.13–34.04) | 42.81 ms (40.39–45.65) |
| Rust | multi-core | 3 | 32.8 µs (32.7–33.1) | 26.4 µs (26.0–27.4) | 3.17 ms (3.09–7.06) | 9.04 ms (8.22–11.22) | 10.41 ms (9.18–25.60) |

#### Findings:
- **Go multi-core removes the ORM effect completely.** Ping 5 is read after 46.2 µs, the max is at most 1.44 ms and the canary max is ≈ 3 ms.
- **Rust multi-core cuts it by 3–8× but does not remove it.** Ping 5 takes 3.17 ms (3.09–7.06) and the max is 8–11 ms. *Hypothesis:* tokio's multi-thread scheduler can leave the reader task queued on a worker that is spinning, until another worker steals it.
- **Python does not change.** Its median is 1.13 vs 1.22 ms and ping 5 is ≈ 1.0 ms in both modes. The burst cost is in the one event loop, which multi-core does not split.

### R3.4 Staggered floors and tests at 25, 100 and 250 endpoints

#### Table 3.4: Staggered, single-core, sem 15: floor (db 0 ms) vs test (db 3 ms), 2 runs each

| Engine | Endpoints | Floor Median | Test Median | Floor p99 | Test p99 | Floor Kernel RTT | Test Kernel RTT |
|---|---|---|---|---|---|---|---|
| Python | 25 | 98.8 µs (97.4–100.2) | 95.3 µs (92.9–97.7) | 644.5 µs (569.6–719.4) | 395.3 µs (256.9–533.7) | 382.0 µs (380.9–383.1) | 370.7 µs (370.4–370.9) |
| Python | 100 | 95.6 µs (95.0–96.2) | 97.7 µs (96.7–98.7) | 364.6 µs (155.5–573.7) | 340.9 µs (167.7–514.0) | 380.5 µs (366.8–394.3) | 384.7 µs (369.5–400.0) |
| Python | 250 | 98.1 µs (96.2–99.9) | 87.9 µs (81.8–94.1) | 736.2 µs (498.3–974.1) | 168.7 µs (158.2–179.2) | 402.3 µs (399.6–405.1) | 370.0 µs (369.8–370.3) |
| Go | 25 | 71.2 µs (69.1–73.4) | 59.4 µs (43.1–75.8) | 831.3 µs (812.0–850.6) | 610.7 µs (244.1–977.4) | 402.4 µs (401.9–403.0) | 375.4 µs (373.0–377.7) |
| Go | 100 | 74.8 µs (73.0–76.7) | 59.1 µs (41.6–76.6) | 306.8 µs (289.9–323.8) | 484.8 µs (125.6–844.0) | 378.2 µs (368.3–388.0) | 371.7 µs (369.4–373.9) |
| Go | 250 | 52.3 µs (48.3–56.2) | 63.4 µs (55.0–71.8) | 748.6 µs (615.4–881.8) | 370.5 µs (291.8–449.2) | 384.5 µs (378.9–390.1) | 384.9 µs (381.5–388.4) |
| Rust | 25 | 69.9 µs (67.7–72.0) | 71.9 µs (69.7–74.0) | 700.1 µs (661.8–738.3) | 622.2 µs (449.2–795.2) | 402.5 µs (401.4–403.6) | 376.0 µs (372.0–380.1) |
| Rust | 100 | 72.1 µs (71.6–72.6) | 71.5 µs (71.2–71.9) | 357.2 µs (140.9–573.5) | 310.3 µs (173.9–446.7) | 390.9 µs (380.7–401.2) | 380.9 µs (374.8–387.0) |
| Rust | 250 | 69.3 µs (66.9–71.7) | 73.2 µs (71.4–75.0) | 674.9 µs (532.2–817.7) | 258.5 µs (194.1–322.9) | 392.7 µs (383.6–401.7) | 374.8 µs (363.0–386.6) |

#### Findings:
- **At 100 endpoints, with interleaved floors, staggered intrusion cannot be told from zero.**
  - Test and floor medians are within ±2 µs for Python and Rust. Go's ranges overlap.
  - The p99 ranges overlap for every engine.
- **At 25 and 250 endpoints no engine is above its floor.**
  - Python's 250-endpoint test is below its floor: 87.9 µs (81.8–94.1) against 98.1 µs (96.2–99.9).
  - These floors were recorded an hour after their tests, so time drift cannot be excluded.
- **The 25- and 250-endpoint floors have heavier tails and slower kernel RTTs than their tests.**
  - p99: Python 250 endpoints 736.2 vs 168.7 µs; Go 25 endpoints 831.3 vs 610.7 µs.
  - Kernel RTT: Python 250 endpoints 402.3 vs 370.0 µs.
  - This fits the C-state *hypothesis* that an idle CPU sleeps more deeply, and it also fits drift. Neither is tested.
- **Python does not degrade at 250 endpoints.** Its median is 87.9 µs at 250 endpoints, 97.7 µs at 100 and 95.3 µs at 25. The finding in §R2.2 did not reproduce.
- **Go's median switches between ≈ 42–56 µs and ≈ 72–77 µs from run to run.** It does so in floors and tests alike, as ranges such as 41.6–76.6 µs show. With 2 runs per setting, Go medians cannot be compared to better than ≈ 30 µs.

### R3.5 Python's two burst regimes

#### Table 3.5: Python burst runs on 2026-10-25, grouped by when they were recorded

| Recorded | Run | Runs | Median | Kernel RTT Median | Send Lag Mean |
|---|---|---|---|---|---|
| 10:35–10:50 | test | 2 | 2.30 ms (2.27–2.32) | 149.7 µs (145.8–153.7) | 3.63 ms (3.42–3.84) |
| 14:33–14:50 | floor | 2 | 1.09 ms (0.98–1.21) | 235.2 µs (223.5–246.9) | 2.25 ms (2.14–2.37) |
| 18:56–18:59 | floor | 1 | 2.48 ms | 134.9 µs | 3.77 ms |
| 18:56–18:59 | test | 1 | 2.25 ms | 141.5 µs | 3.62 ms |
| 19:11–21:04 | floor | 3 | 1.11 ms (1.02–1.27) | 235.4 µs (211.7–248.2) | 2.29 ms (2.10–2.65) |
| 19:11–21:04 | test | 12 | 1.19 ms (1.10–1.51) | 224.6 µs (150.6–257.2) | 2.27 ms (2.12–2.83) |

The 14:33 floors are the single-core and multi-core burst floors of §R2.4. The 19:11–21:04 tests include sem 5, 15 and 50 and the multi-core runs.

#### Findings:
- **Python's burst runs fall into two groups, and floors and tests switch together.** So the group is set by a machine state, not by the ORM work.
  - **Slow (10:35, 18:56):** median ≈ 2.25–2.48 ms, send lag ≈ 3.6–3.8 ms, kernel RTT ≈ 135–154 µs.
  - **Fast (14:33, and from 19:11):** median ≈ 1.0–1.5 ms, send lag ≈ 2.1–2.8 ms.
- **The median tracks the send lag.**
  - *Hypothesis:* in a burst, Python's read cost is its own send loop. The loop sends the 100 pings one after another while the replies queue in the kernel, and reads them in one wakeup once it is free (100 packets per wakeup, §R2.4).
  - The ORM spins start only after that read, when no reply is in flight, so they do not delay ICMP. A slower send loop, from the CPU clock or from other load, delays every reply.
- **The cause of the switch is not known.** The 18:59 → 19:11 switch coincides with the link drop, but the slow morning runs had no link event, so the link is not the whole story.
- **Consequence for §R2.3 and §R2.4:** Python's 2.30 ms burst median and the 43 % in Table 2.6 compare a slow-regime test with fast-regime floors.

### R3.6 Host check: where the NIC interrupt runs

The NIC interrupt never ran on the probe core.
- `/proc/irq/159/effective_affinity_list` (`enp0s31f6`) is CPU 5.
- `/proc/interrupts` shows all 192,205 interrupts of IRQ 159 on CPU 5, counted since boot at 2026-10-23 09:41, which is before any run. None ran on probe core 7 or on its sibling, CPU 3.

The run metadata records only the allowed mask (CPUs 0–7), which is why every host report carries the "may run on the probe core" warning.

---

## R4. Answers to the Core Research Questions

### Question 1: How large is the distortion for a single-threaded asyncio monitor under realistic database-write load?

**Empirical Answer:**
The Ephemres configuration is 100 endpoints, 5 pings 8 s apart, a 60 s stagger window, semaphore 15 and a 3 ms ORM CPU spin. Under it, a single-threaded Python asyncio monitor shows:
- **Median observer intrusion:** **100.8 µs** (repeat range 99.6–102.0 µs).
- **Mean intrusion:** **121.1 µs** (119.9–122.3 µs). It sits above the median because of a p99 of 363–798 µs.
- **95th percentile intrusion:** **187.3 µs** (180.6–193.9 µs).
- **Maximum spike:** **2.66 ms** (2.40–2.91 ms).
- **Primary measurement error:** **27.3 %** of the kernel RTT (`total lag ÷ total kRTT`, range 26.2–28.3 %).

**What it means:**
- On a LAN where the kernel RTT is ≈ 445 µs, the monitor reports ≈ 566 µs, so about a fifth to a quarter of the reported latency comes from the monitor.
- The idle floor shows the same median (98.3 µs). In the follow-up session, floors recorded just before each test matched within ±2 µs (§R3.4). So the intrusion is the cost of Python's read path, which the monitor pays on every packet regardless of the ORM work.

---

### Question 2: How does the distortion vary with load shape (burst vs staggered), semaphore size, and CPU work duration?

**Empirical Answer:**
1. **Load shape is the dominant factor, and its effect depends on the engine.**
   - Python's median rises from ≈ 100 µs to ≈ 1–2.5 ms under burst, depending on the machine state (§R3.5). The same happens with no ORM work.
   - Go's and Rust's medians stay at their floors. The last ping of each cycle waits behind the ORM work:
     - Rust ≈ 15–28 ms and Go ≈ 43–79 ms in the follow-up session;
     - Rust ≈ 48 ms and Go up to 208 ms in the first session.
   - Burst also shifts the kernel-measured RTT in both directions, with or without ORM work (§R2.3, Table 3.2).
2. **Semaphore size: no effect under a stagger, and under burst a larger one never helps.**
   - Staggered: sem 5, 30 and 50 give overlapping results for every engine, because fewer than one write is active at a time on average.
   - Burst: Rust's runtime freezes for ≈ sem × 3 ms, but its reader's stall is 15 ms at sem 5 and ≈ 24 ms at both 15 and 50. Go shows no semaphore effect. Python's ICMP lag does not change, though its event loop is blocked longer (§R3.1).
3. **CPU work duration was not varied.** Only 0 ms (floors) and 3 ms (tests) exist.
   - Staggered: the difference between them is within noise, now also with interleaved floors (§R3.4).
   - Burst: the 3 ms work leaves every median at its floor. For Go and Rust it turns the end-of-cycle stall from ≈ 0.4–1.8 ms into ≈ 15–79 ms; for Python it adds nothing (§R3.2).

---

### Question 3: How do Go (`goroutines`) and Rust (`tokio`) compare to Python (`asyncio`) under the same load, both pinned to one core and across all cores?

**Empirical Answer:**

Because Python (`asyncio`) is the current production engine in Ephemres, Go and Rust must be evaluated directly against the Python baseline under identical loads:

| Execution Mode | Python (`asyncio`) Baseline | Go (`goroutines`) Performance | Rust (`tokio`) Performance | Comparative Analysis vs. Python (`asyncio`) |
|---|---|---|---|---|
| **Single-Core Staggered** | Median: **100.8 µs** (95–98 µs in §R3.4)<br>Mean: **121.1 µs** (120–122 µs)<br>p95: **187.3 µs** (181–194 µs)<br>p99: **580.1 µs** (341 µs in §R3.4)<br>Error: **27.3%** | Median: **74.7 µs** (59 µs in §R3.4)<br>Mean: **88.4 µs** (81–96 µs)<br>p95: **152.2 µs** (116–189 µs)<br>p99: **539.1 µs** (485 µs in §R3.4)<br>Error: **20.2%** | Median: **70.0 µs** (71.5 µs in §R3.4)<br>Mean: **96.3 µs** (90–103 µs)<br>p95: **140.7 µs** (136–146 µs)<br>p99: **921.1 µs** (310 µs in §R3.4)<br>Error: **22.7%** | **Go and Rust are in practice equal, and only ≈ 25–31 µs faster than Python at the median.** For all three engines, the 3 ms ORM work adds zero measurable intrusion above the idle floor (§R3.4). On a single core, all three share a heavy `p99` tail (310–921 µs) inherited from the pinned core's idle floor. |
| **Multi-Core Staggered** | Median: **98.5 µs**<br>Mean: **106.5 µs** (102–109 µs)<br>p95: **169.3 µs** (160–171 µs)<br>p99: **207.1 µs** (205–424 µs across sems)<br>Error: **24.4%** | Median: **71.2 µs**<br>Mean: **69.9 µs** (70–72 µs)<br>p95: **109.6 µs** (108–110 µs)<br>p99: **135.7 µs** (112–136 µs across sems)<br>Error: **15.5%** | Median: **68.1 µs**<br>Mean: **71.7 µs** (70–72 µs)<br>p95: **103.8 µs** (102–105 µs)<br>p99: **120.2 µs** (112–140 µs across sems)<br>Error: **15.9%** | **Multi-core barely changes Python's median (98.5 vs. 100.8 µs), whereas Go and Rust cut `p99` tail latency by 3–5× (to 112–140 µs).** Go and Rust are virtually identical in multi-core staggered mode and stay ≈ 30 µs below Python's baseline read floor (§R1.4). |
| **Single-Core Burst** | First session: median **2.30 ms**, mean **2.65 ms**, p95 **6.13 ms**, max **8.54 ms**<br>Follow-up, sem 15: median **1.22 ms**, Pings 1–4 **1.28 ms**, Ping 5 **1.01 ms**, max **3.41 ms**, canary max **107.87 ms** | First session: median **0.32 ms**, mean **13.02 ms**, p95 **84.35 ms**, max **208.22 ms**<br>Follow-up, sem 15: median **65.9 µs**, Pings 1–4 **40.6 µs**, Ping 5 **48.84 ms**, max **53.05 ms**, canary max **318.94 ms** | First session: median **0.16 ms**, mean **6.88 ms**, p95 **48.40 ms**, max **48.98 ms**<br>Follow-up, sem 15: median **70.3 µs**, Pings 1–4 **55.0 µs**, Ping 5 **24.23 ms**, max **27.85 ms**, canary max **42.81 ms** | **Opposite failure modes relative to Python.** Python delays *every* packet in a burst by **1.1–2.3 ms** (even at 0 ms ORM work), but caps its worst packet at **3.4–8.5 ms** because it drains all 100 replies before starting ORM spins. Go and Rust read Pings 1–4 **20–30× faster than Python** (41–55 µs), but stall severely on Ping 5 behind ORM spins: **Rust (24.23 ms)** is twice as fast and far steadier than **Go (48.84 ms, max up to 208 ms)**. |
| **Multi-Core Burst** | Floor: median **1205.5 µs**, Ping 5 **987.0 µs**<br>Loaded: median **1.13 ms**, Pings 1–4 **1.20 ms**, Ping 5 **1.01 ms**, max **3.39 ms**, canary max **74.34 ms** | Floor: median **33.4 µs**, Ping 5 **36.3 µs**<br>Loaded: median **33.3 µs**, Pings 1–4 **31.3 µs**, Ping 5 **46.2 µs**, max **869.2 µs**, canary max **2.98 ms** | Floor: median **35.5 µs**, Ping 5 **1628.5 µs**<br>Loaded: median **32.8 µs**, Pings 1–4 **26.4 µs**, Ping 5 **3.17 ms**, max **9.04 ms**, canary max **10.41 ms** | **Multi-core does not help Python in a burst (1.13 ms vs. 1.22 ms), turns Rust into a 3.17 ms Ping-5 tail, and makes Go completely immune (46.2 µs Ping 5).** Relative to Python's 1.13 ms median, both compiled engines cut typical burst lag by **34×** (to ~33 µs), and Go eliminates the end-of-cycle stall entirely (§R3.3). |

---

### Question 4: What does Python gain, and pay, by moving the CPU work into worker processes?

**Empirical Answer:**
1. **What Python gains:**
   - **A calmer event loop.** The loop no longer runs the 3 ms spin, so its canary average is 20–73 µs lower than same-day single-core runs (276.5 µs against 336.6 µs at sem 30).
2. **What Python pays:**
   - **IPC overhead.** Moving each payload to a worker and back costs **0.741 ms** on average per write, with peaks of **11.62 ms** and **12.11 ms**.
3. **What does not change:**
   - **Packet intrusion.** The median stays at ≈ 98–101 µs with and without the offload. The multi-core idle floor, which does no offloading at all, also has a **100.3 µs** median. The ≈ 30 µs gap to Go and Rust is Python's baseline read cost, which no offload can remove.
   - **Burst behaviour.** In a burst, Python multi-core is no better than single-core.
     - Floors: median 1,206 µs against 984 µs, canary max 69.09 ms against 59.21 ms.
     - Loaded runs (§R3.3): median 1.13 ms against 1.22 ms.

     The burst cost is the event loop sending and reading 100 packets at once, and the offload does not touch that.

---

### Question 5: How do schedule design, hardware scaling, and language runtime each relate to the observer error measured here, for Ephemres and for monitoring platforms with a similar asynchronous probing architecture?

**Empirical Answer:**

#### 5a. Can the observer error be eliminated, and how does hardware scaling affect each language?
1. **User-space observer error can never be eliminated (`Clock B − Clock A > 0`), only reduced, unless the monitor reads kernel timestamps (`Clock A`):**
   - Even with zero post-cycle CPU work (`0 ms` idle floor, Table 1.2), user-space socket reading adds a mandatory baseline floor of **≈ 98–100 µs in Python** and **≈ 68–75 µs in Go and Rust** under staggered load.
   - Rewriting a monitoring engine from Python to Go or Rust cannot eliminate this kernel-to-user-space boundary; at best it trims the staggered median by **≈ 25–30 µs** (and down to **≈ 33 µs** in multi-core burst).
   - In these measurements, no language change brought the staggered median below ≈ 68 µs. **Kernel arrival timestamping (`SO_TIMESTAMPING` / `Clock A` via `recvmsg()` ancillary data)** is taken before the user-space scheduler and socket queue, so by construction it excludes the lag measured here. The lab engines read `Clock A` only as the reference. This study did not test it as the monitor's own timestamp inside Ephemres.
2. **Multi-core hardware makes almost no difference for Python, but dramatically reduces observer error for Go and Rust:**
   - **Why multi-core fails to help Python (`py-sc` → `py-mc`):** Because Python's `asyncio` socket reader is single-threaded and CPython's GIL prevents shared-memory multi-threading, scaling across CPU cores requires cross-process IPC (`ProcessPoolExecutor`). That leaves staggered median lag unchanged (**100.8 µs vs. 98.5 µs**), adds **0.741 ms** of `pickle` serialisation overhead per write (Table 1.3), and provides **zero relief under burst** (**1.22 ms vs. 1.13 ms** median, Table 3.3), because the single event loop is still the bottleneck for sending and draining 100 packets at once.
   - **Why multi-core transforms Go (`go-sc` → `go-mc`) and Rust (`rs-sc` → `rs-mc`):** Both compiled runtimes schedule tasks across OS threads in shared memory without IPC serialisation. Adding CPU cores cuts staggered `p99` tail latency by **3–5×** (**372–571 µs → 112–140 µs**, Table 1.4). Under a 100-endpoint burst, adding cores drops Rust's `Ping 5` stall **~8×** (**24.23 ms → 3.17 ms**) and drops Go's `Ping 5` stall **>1,000×** (**48.84 ms → 46.2 µs**, Table 3.3), allowing a free OS thread to read incoming ICMP replies immediately while other cores execute the 3 ms CPU spins.

#### 5b–5d. Runtime Trade-offs Irrespective of Hardware: Advantages and Disadvantages

| Runtime | Empirical Advantages | Empirical Disadvantages | Where It Performed Best in These Tests |
|---|---|---|---|
| **5b. Python (`asyncio`)** | 1. **Zero ORM penalty under staggered load:** With a 60 s stagger (25–250 endpoints), 3 ms of post-cycle CPU work adds **0 µs** of net intrusion above its idle floor (Table 3.4).<br>2. **Bounded worst-case packet in a single-core burst:** Because Python sends sequentially and drains all 100 burst replies in one wakeup *before* starting ORM spins, its worst burst packet is **3.41–8.54 ms**, avoiding the 28–208 ms single-ping stalls seen in single-core Go and Rust (Tables 2.3, 3.1).<br>3. **Architectural simplicity:** Shares ORM models and application code with the main platform without multi-language build or FFI complexity. | 1. **Highest baseline read floor:** Costs **≈ 98–101 µs** per packet at the median (~30 µs slower than Go/Rust even when completely idle, Table 1.1).<br>2. **Every packet suffers in a burst:** Serial event-loop send/receive handling inflates *every* burst packet (Pings 1–5 alike) to **1.1–2.3 ms** even at 0 ms ORM work (Table 3.2), and shifts between 1.1 ms and 2.3 ms with host state (Table 3.5).<br>3. **Cannot scale socket reading across cores:** `ProcessPoolExecutor` adds **0.741 ms mean (12.11 ms max)** IPC overhead per write without lowering packet intrusion in either staggered or burst mode (Tables 1.3, 3.3). | **Staggered schedules** (25–250 endpoints, 60 s stagger) on one core or many, where 3 ms of ORM work added no measurable intrusion. Its worst single-core burst packet (≤ 8.54 ms) was also the smallest of the three engines. |
| **5c. Go (`goroutines`)** | 1. **Best multi-core burst resilience:** `go-mc` is the **only** configuration that absorbs a 100-endpoint burst with zero end-of-cycle stall (**33.3 µs** median, **46.2 µs** Ping 5, **2.98 ms** canary max, Table 3.3).<br>2. **Fastest send path & low staggered floor:** Lowest staggered send lag (**~635 µs**, Table 1.1), sub-millisecond timer canary (**~330 µs**), and a **~70–75 µs** staggered read floor.<br>3. **Shared-memory multi-core scaling:** Scales across cores via `GOMAXPROCS` with zero IPC serialisation tax. | 1. **Worst single-core burst starvation (`GOMAXPROCS=1`):** On a 1-vCPU host under burst, 3 ms spins finish inside Go's ~10 ms preemption window and queue ahead of the netpoller reader, stalling Ping 5 to **37–62 ms median (up to 208.22 ms max)** and starving the canary for **238–329 ms** regardless of semaphore size (Tables 2.3, 3.1).<br>2. **Single-core run-to-run variance:** Staggered single-core medians switch bimodally between **~42–56 µs** and **~72–77 µs** across runs (Table 3.4). | **Multi-core bursts (`go-mc`)**, the only configuration tested with no end-of-cycle stall (**46.2 µs** Ping 5). The same engine under `GOMAXPROCS=1` had the longest burst stalls measured. |
| **5d. Rust (`tokio`)** | 1. **Lowest staggered latency & tightest consistency:** Lowest median intrusion in both single-core (**70.0 µs**) and multi-core (**68.1 µs**, p99 **120.2 µs**, Table 1.1) with minimal run-to-run variance (±0.4–2 µs in Table 3.4).<br>2. **Controlled single-core burst stall:** Tokio's cooperative polling budget lets the reader run after ~8 spins even when the canary is frozen for `sem × 3 ms`, keeping single-core burst Ping 5 at **15.21–24.46 ms** (~2× lower and far steadier than Go, Table 3.1).<br>3. **Zero garbage collection:** Compile-time memory management guarantees no GC pause spikes as in-memory state scales. | 1. **Residual multi-core burst stall on Ping 5:** Unlike Go (`46.2 µs`), Tokio's multi-thread runtime (`rs-mc`) still leaves Ping 5 delayed at **3.17 ms median (9.04 ms max)** under loaded burst (Table 3.3) and **1.63 ms** in the burst floor (Table 2.5) when synchronous work blocks the worker holding the socket reader before work-stealing intervenes.<br>2. **Coarse 1 ms timer wheel & multi-core send lag:** Default 1 ms timer resolution inflates sleep timers (canary avg **~1.17 ms**) and shows higher staggered multi-core send lag (**~1.51 ms**, Table 1.1). | **Staggered schedules**, where it had the lowest and most repeatable median (68–70 µs), and **single-core bursts**, where its Ping 5 stall was about half of Go's. Moving the burst CPU work to `tokio::task::spawn_blocking` or a dedicated reader thread was not tested: the spin runs inline, for parity with the other engines. |

---

## Architectural Anomalies & Host Effects

### 1. Go scheduling under `GOMAXPROCS=1`
The Go engine is built with Go 1.22, which preempts goroutines that run longer than ≈ 10 ms.
- Each simulated ORM spin lasts 3 ms, so preemption does not interrupt it.
- After a burst, the reader goroutine (woken by the network poller) and the canary (woken by a timer) wait behind the many goroutines the burst made runnable.
  - First session: the canary was starved for up to **281.17 ms**, and packet intrusion reached **208.22 ms**.
  - Follow-up session: canary 238–329 ms, packets up to 79 ms, at every semaphore (§R3.1).
- Under multi-core (`go-mc`) the problem disappears, in the floor and with ORM work on (ping 5 at 46 µs, §R3.3).
- The exact queueing path inside the Go scheduler is a *hypothesis*. The size of the effect is measured.

### 2. Tokio 1 ms timer granularity
- **Canary.** The Rust canary averages **1.17–1.22 ms** in all modes, against ≈ 250–340 µs for Python and Go. This is consistent with Tokio's 1 ms timer granularity ([04 Engines](04-engines.md) §Known runtime behaviour), which affects timed sleeps, not socket reads.
- **Send lag.** The timer explanation does **not** cover Rust's send lag:
  - single-core staggered Rust sends with ≈ 0.85–0.97 ms mean lag, the same as Python;
  - only multi-core staggered Rust is higher, at ≈ 1.45–1.54 ms, including its floor (1.40 ms).

  Why Rust multi-core sends later is unexplained.

### 3. The probe core and the single-core tail
- **Observed.** Single-core runs have a p99 of ≈ 335–920 µs whether or not ORM work runs. Go and Rust multi-core have ≈ 110–140 µs.
- **Host report.** Every run records that the probe core (7) shares a physical core with CPU 3, that the NIC interrupt may be handled on core 7, and that the `powersave` governor and turbo are active.
- **Checked: not the NIC interrupt.** IRQ 159 ran only on CPU 5 since boot (§R3.6). The sibling CPU, the governor and C-states remain candidates.
- **Recommendation.** For a production appliance, before attributing the single-core tail to the runtime:
  - isolate the probe core and its sibling;
  - pin NIC interrupts away from it explicitly, since today they stay off core 7 only by chance;
  - use the `performance` governor.

### 4. Deep C-states
- **The host has C10 enabled,** with ≈ 890 µs exit latency. In principle a lightly loaded run can wake more slowly than a busy one.
- **The staggered data does not show it.** Loaded and floor medians differ by only a few µs, within noise (§R1.2). Python's lower kernel RTT under burst is one place it could plausibly show (§R2.3).
- **The follow-up floors fit it, without settling it.** The 25- and 250-endpoint floors have heavier tails and slower kernel RTTs than their tests (§R3.4). Those floors ran an hour later, though, so drift explains them as well.
- **Treat C-state effects as untested.** Limiting C-states for one set of runs would settle the question.

---

## Methodological Lessons, Limitations & Future Work

Because this study evolved across two recording sessions as we discovered artifacts in the initial measurements, it is important to separate **what we did and found** from **what we did not test and leave for extended research**:

1. **Why Session 2 was needed (interleaved floors and per-ping breakdown).**
   - In Session 1 (90 runs), idle floors were recorded once per configuration rather than interleaved with each test, and burst runs were initially summarised using run-level `mean`, `p95`, and `Primary Error %`.
   - That revealed two traps: (a) host baseline speed drifted by up to 2× between morning and afternoon (§R3.5), invalidating non-interleaved floor subtraction (Table 2.6), and (b) in Go and Rust burst runs, Pings 1–4 arrived at the 30–60 µs floor while all ORM stall sat on **Ping 5**, causing run-level means to misrank the engines (§R2.3).
   - Session 2 (81 runs) corrected both by introducing rotating batches with **interleaved idle floors** just before each test and reporting **Pings 1–4 Median vs. Ping 5 Median** alongside the run median.
2. **Sample repeats (2–3 repeats vs. 5+ repeats).**
   - All sweeps in `test_results/` use `2` repeats (`ep-sweep`, Session 1 `burst`, `same-day`) or `3` repeats (`sem-sweep`, `burst-sem`, `burst-mc`). While 3 repeats clearly separate multi-millisecond burst stalls (e.g., `46 µs` in `go-mc` vs `48.84 ms` in `go-sc`), 2–3 repeats have a minimum two-sided Mann-Whitney p-value of `0.33` and `0.10` on non-overlap ([02 Test methodology](02-test-methodology.md) §3). Repeating the matrix with `5` rounds (`p = 0.008`) and interleaved floors on every batch is the recommended standard for follow-up studies seeking to resolve single-digit microsecond differences.
3. **Untuned host power management (`powersave`, `C10`, hyper-threading).**
   - All 173 runs were recorded under the laptop's default `powersave` governor with `C10` deep sleep and turbo boost active, and with probe core 7 sharing a physical core with CPU 3. Repeating the single-core and floor runs with `cpupower frequency-set -g performance`, deep C-states disabled (`cpupower idle-set -D 10`), and cores 3 and 7 isolated will test whether the single-core `p99` tail (`335–920 µs`) and bimodal Go medians come from power management or OS scheduling.
4. **CPU work duration (`simulated_db_ms`) and memory allocation.**
   - Only `0.0 ms` (floor) and `3.0 ms` (loaded) CPU spins were tested, and the spin allocates no heap memory. Sweeping `simulated_db_ms` across `0.5, 1, 2, 5, 10 ms` and testing allocation-heavy ORM payloads (to exercise Python GC and Go GC) are direct extensions of this lab.
5. **Isolating Python multi-core pure IPC cost under burst.**
   - Under burst we tested `py-mc` only at `db_write_semaphore = 15` (where 15 jobs share 7 workers). Running `py-mc` under burst with `db_write_semaphore ≤ 7` will separate pure `pickle`/pipe serialisation cost from worker-pool queue wait when all endpoints finish simultaneously.

---

## Related Work & Theoretical Grounding

The findings from this lab connect with five areas of published research and systems engineering literature:

### 1. Kernel vs. User-Space Timestamping in Fleetwide Monitoring (de Bruijn, 2023)
At Netdev 0x17, Willem de Bruijn (Linux kernel maintainer for socket timestamping at Google) showed in *"SO_TIMESTAMPING: Powering Fleetwide RPC Monitoring"* that standard user-space measurement falsely blames network paths for delays occurring within the host's own software and scheduling stack. De Bruijn listed as an open question: *"How much do measurements perturb the measured system?"*
For an asynchronous ICMP monitor on this hardware, our measurements show:
- Under a **staggered schedule**, each runtime's baseline read path inflates reported latency on short LAN links (440 µs RTT) by **27.3%** in Python (100.8 µs median lag) and **20–23%** in Go and Rust (70–75 µs), paid whether or not ORM work runs (§R1.2, §R3.4).
- Under a **burst schedule**, post-cycle ORM serialisation stalls the cycle's final ping by **15–79 ms** in single-core Go and Rust and starves Python's event-loop canary from **66 ms to 108–219 ms** (§R3.1–§R3.2).

### 2. High-Precision Active Probing and Software Clock Jitter (Pásztor & Veitch, 2001, 2002)
Pásztor and Veitch showed that Unix user-space active probers suffer from systemic timing jitter caused by operating system scheduling and interrupt handling, requiring dedicated hardware capture cards (DAG) or modified kernel timers to achieve microsecond fidelity. This lab shows how standard Linux kernel software timestamping (`SO_TIMESTAMPING` via `cmsg`), paired with ordinary raw ICMP sockets, gives self-checking dual-clock measurements (`Clock B − Clock A`) without proprietary capture cards or kernel patches.

### 3. Active SLA Monitoring and Schedule Distortion (Sommers et al., 2005, 2007)
In their work on SLA compliance monitoring (SLAM) and packet loss accuracy (Badabing), Sommers et al. showed that active probing schedules perturb the network when probes bunch into bursts. This lab separates both halves of the probe effect:
1. **The External Observer Effect:** How burst probing shifts kernel-measured RTT across runtimes (150–250 µs in Python vs. 528–889 µs in Go and Rust).
2. **The Internal Observer Effect:** How burst packet arrivals and post-cycle database writes stall the monitor's own event loop (550%–2,240% error rates) even when physical network loss remains 0%.

### 4. High-Frequency Trading & Real-Time Linux Benchmarks (2025–2026)
Low-latency and HFT benchmarking literature (e.g., HFT-Bench) highlights the microsecond penalty of logging, serialisation, and database writes on hot paths, as well as hardware-level effects like CPU C-state wake-up penalties:
- Offloading ORM work to worker processes (`py-mc`) adds a **741 µs average IPC penalty** (peaking at 12.11 ms), showing that crossing a process boundary adds measurable overhead without reducing packet read lag (§R1.3).
- While HFT benchmarks document wake-up penalties under `powersave` governors and deep CPU sleep states (C10 exit latency ≈ 890 µs), in our dataset C-state wake-up effects and session drift remain open hypotheses that require runs with fixed CPU governors and disabled C-states (§R3.4, §Architectural Anomalies & Host Effects).

### 5. Answering the Ephemres Engineering Questions (Dean & Barroso, 2013; Galindo Salgado, 2019; Instagram, 2017; Nowack, 2020; Clements, 2019)
The original motivation for this work ([00 Research background](00-research-background.md) §1) was to find out why Ephemres reported a slight, regular RTT offset compared to terminal `ping`, how its single-core GNS3 design and `4 → 15` semaphore change behaved under load, and whether Python's `asyncio` runtime warranted rewriting the engine in Go or Rust:
- **Why the terminal `ping` vs. Ephemres discrepancy existed:** Even when post-cycle ORM work adds zero stall (`0 ms` idle floor), Python's user-space `asyncio` wake-up and socket read path adds a **≈ 100.8 µs median lag** (and p99 tails of 335–920 µs on an untuned single core). Reading kernel arrival timestamps (`SO_TIMESTAMPING` / `Clock A`) inside Python removes this user-space read lag directly without changing languages.
- **Testing the `4 → 15` semaphore change and staggered schedule:** Under Ephemres's 60 s staggered schedule at 100 endpoints, average post-cycle concurrency is `0.0067 ≪ 1`, so semaphores 5, 15, 30, and 50 all allow post-cycle work to clear without measurably inflating packet intrusion above the idle floor (§R1.2, §R2.1). A cap of 4 would almost never be reached either (4 was not run; 5 was the smallest setting), so the semaphore change is unlikely to explain the better ICMP readings Ephemres showed after it. Other improvements to the Ephemres code are the more likely cause. Under a burst schedule on a single core, however, raising the semaphore from 5 to 15 or 50 increases the number of back-to-back 3 ms spins that run before the event loop yields, pushing Python's canary from **108 ms (`sem=5`) to 219 ms (`sem=50`)** (§R3.1).
- **Why testing before rewriting in Go or Rust mattered:** On a single core (the GNS3 1-vCPU baseline) under Ephemres's staggered load, Go and Rust reduce median read lag by only **≈ 25–30 µs** compared to Python (`70–75 µs` vs. `100.8 µs`), while under a single-core burst Go's scheduler starves timer-woken goroutines for **238–329 ms** (Clements, 2019; §R3.1). Only under a **multi-core burst** does Go (`go-mc`, Ping 5 at `46 µs`) clearly beat Python and Rust (§R3.3). Keeping Python for Ephemres's staggered workload (and reading kernel timestamps where sub-100 µs precision is needed) avoids an unnecessary rewrite.

### What this lab adds
1. **Per-packet differential self-control:** Real-time dual timestamping (`Clock B − Clock A`) on every packet without external capture hardware.
2. **Event-loop cross-talk measurement:** Direct measurement of how post-cycle DB work behind an async semaphore affects concurrent in-flight measurements.
3. **The 6-way concurrency matrix:** Side-by-side evaluation of cooperative single-thread, preemptive runtime, and work-stealing multi-thread models under identical workloads.
4. **Measuring the process offload tax:** Evidence that process-pool offloading trades CPU burn for IPC latency and GIL contention without lowering event-loop read lag.
5. **Loss by cause:** Separation of observer-induced packet loss (replies that arrived in the kernel on time but were read after user-space timeout) from true network loss.

---

## Methodological Verification

To keep the published numbers consistent with the raw records:
1. Every figure in this report was computed from `test_results/*.csv` (packet level, cycle 0 excluded) and `test_results/*.meta.json`.
   - Percentiles use linear interpolation.
   - Means and error % match the run summaries in `test_results/INDEX.md`.
2. A standalone script, `verify_analysis.py`, at the repository root parses all 173 runs and checks the cited figures against them.
   - It checks that INDEX.md and the `.meta.json` files list the same runs, and that every run has zero loss.
   - It checks the first-corpus figures in §R1 and §R2 against the first 90 runs, including the packet medians in Tables 1.1 and 2.3 and the burst-floor medians in Table 2.5.
   - It rebuilds every row of Tables 3.1–3.5 from the packet CSVs and requires each row to appear in this report exactly; `--print-tables` prints them.
   ```bash
   python3 verify_analysis.py
   ```
   The script checks that the numbers are right. It does not check whether an interpretation follows from them, so the *hypothesis* labels above matter.
3. The unit tests in `tests/` pass:
   ```bash
   .venv/bin/python -m unittest discover -s tests -t .
   ```

---

## Open Questions and Next Runs

The follow-up session answered the semaphore, multi-core, 25/250-endpoint floor, interleaving and same-day questions (§R3). Still open:

| Question | Run needed |
|---|---|
| What sets Python's burst regime (≈ 1.1 vs ≈ 2.3 ms)? | Python burst floors repeated through a day, logging CPU frequency and load; and one with the `performance` governor |
| Is the single-core tail caused by the sibling CPU or by C-states? | Single-core floor with core 7 and CPU 3 isolated; then with C-states limited |
| Why does Rust's reader stop waiting after ≈ 8 spins when its runtime is frozen for sem × 3 ms? | Burst at sem 8, 10 and 12, Rust single-core |
| Why does Rust multi-core still read ping 5 late? | Burst, Rust multi-core, with the reader on a dedicated thread |
| Are the 25/250-endpoint floor tails C-states or drift? | Those floors recorded just before their tests |

---

## Author Contributions & AI Assistance

The software harness, multi-runtime probing engines (Python, Go, Rust), and benchmark verification suites in this work were developed with the assistance of agentic AI coding tools (Google Gemini / Antigravity and Anthropic Claude) acting as pair programmers under the direct architectural supervision of the author. All experimental hypotheses, test methodologies, kernel instrumentation designs, and data interpretations were conceived and directed by the author, who reviewed all code and takes full responsibility for the scientific integrity, reproducibility, and correctness of the published findings.
