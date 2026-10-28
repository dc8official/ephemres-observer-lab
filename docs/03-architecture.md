# 03 Architecture (Part 1): Harness, IPC Protocol and Process Isolation

This page describes the complete two-tier architecture of the lab, how data flows between its tiers, and how runs start, end, and clean up after themselves. The architecture is documented across two companion files:
1. **Part 1 (Tier 1: Harness & Supervisory Architecture, this document):** Process isolation, the FastAPI dashboard, live event streaming, the NDJSON IPC protocol, run lifecycle, and fail-safe teardown, alongside a high-level overview of Tier 2.
2. **Part 2 (Tier 2: Probing Engine Runtime Architecture, [04 Architecture (Part 2): Probing Engines](04-engines.md)):** Side-by-side implementation parity across the three measurement engines (Python, Go, Rust), raw socket multiplexing, dual-clock `cmsg` extraction, CPU core modes, and low-level runtime scheduler mechanics.

Terms are defined in the [glossary](../README.md#glossary).

---

## 1. Two-tier system architecture

The dashboard server starts a separate *probe* child process for each run (Python, Go, or Rust). The probe performs the ICMP probing and streams its results back as lines of JSON; the server analyses them, displays them live, and saves them to `test_results/`.

```text
====================================================================================================
 TIER 1: HARNESS & SUPERVISORY ARCHITECTURE (server/)
====================================================================================================
   browser ──HTTP / WebSocket──▶  server/app.py (FastAPI)  ──starts──▶  probe process (one per run)
   (index.html)                   · starts/stops runs                    · probe_lab.py --jsonl       (Python)
                                  · reads probe stdout                   · bin/go_prober               (Go)
                                  · analysis, save, export               · bin/rust_prober             (Rust)
                                  · host baseline & housekeeping                │
                                          │                                     │
                                          ▼                                     ▼
                                   test_results/                  isolated child process (pinned CPU)
================================================================================│===================
 TIER 2: PROBING ENGINE RUNTIME ARCHITECTURE (inside the probe process)         │
================================================================================▼===================
  ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
  │   Endpoint Scheduler (up to 500 virtual endpoints: ICMP ID 0x1000 + i)                       │
  │   · Schedule shapes: Staggered (spread over 60 s) vs. Burst (all at 0 s)                     │
  │   · Ping loop: 5 pings @ 8 s interval (tx = CLOCK_REALTIME before sendto)                    │
  │        │                                                                                     │
  │        ▼ sendto()                                                                            │
  │   Raw ICMP Socket (SOCK_RAW, non-blocking, 8 MiB receive queue, SO_TIMESTAMPING enabled)     │
  │        ▲                                                                                     │
  │        │ recvmsg() + cmsg (Clock A: kernel arrival)                                          │
  │   Socket Event Demultiplexer                                                                 │
  │   · Python: loop.add_reader() callback                                                       │
  │   · Go: network poller goroutine                                                             │
  │   · Rust: tokio AsyncFd::readable() task                                                     │
  │   · Immediate user timestamp (Clock B = CLOCK_REALTIME)                                      │
  │   · Match reply (ICMP ID + seq) ──▶ Observer Lag = Clock B − Clock A                         │
  │        │                                                                                     │
  │        ▼ (after all 5 pings complete)                                                        │
  │   Post-Cycle Work (simulated ORM preparation: 3.0 ms CPU spin + 1 ms async sleep)            │
  │   · Concurrency gate: db_write_semaphore (default 15; swept: 5, 15, 30, 50)                  │
  │   · Single-core: inline spin on the reader thread (Python) or pinned runtime (Go, Rust)      │
  │   · Multi-core: offloaded to ProcessPoolExecutor (Python) or work-stealing pool (Go, Rust)   │
  │        │                                                                                     │
  │        ▼                                                                                     │
  │   NDJSON Event Streamer (stdout) ──▶ [start, cycle, tick, late, summary]                     │
  │                                                                                              │
  │   Independent Canary Task (10 ms sleep tick ──▶ measures runtime scheduler starvation)       │
  └──────────────────────────────────────────────────────────────────────────────────────────────┘
        │                                                     │
        ▼ ICMP Echo Requests                                  ▲ ICMP Echo Replies
  Linux Kernel Network Stack (`SO_TIMESTAMPING`)               │
        │                                                     │
        ▼ NIC / loopback                                      │
  Target Device (Echoes back ID & Seq: RFC 792) ──────────────┘
```

### Components

| Tier | Part | File | Job |
|---|---|---|---|
| **Tier 2** | Python engine and CLI | `probe_lab.py` | the Ephemres-style cycle, reply matching, ORM simulation, console table, CSV output, JSON-lines mode |
| **Tier 2** | Go engine | `workers/go_prober/main.go` | the same mechanics with goroutines and Go's network poller |
| **Tier 2** | Rust engine | `workers/rust_prober/src/main.rs` | the same mechanics with `tokio` (`current_thread` and multi-thread) |
| **Tier 2** | Kernel clock | `server/kernel_clock.py` | opens the raw ICMP socket, turns on kernel timestamps, reads a packet and its timestamp with `recvmsg_into`, finds the route to each target, builds packets |
| **Tier 2** | Hardware timestamps | `server/hw_timestamp.py` | optional NIC timestamping via `SIOCSHWTSTAMP` (read first, changed only when safe, restored on close) |
| **Tier 2** | Canary | `server/canary.py` | the 10 ms scheduler-lag task, with the start-up/shutdown gate |
| **Tier 2** | ORM worker | `server/orm_burn.py` | the CPU work that runs in a separate process in Python multi-core mode |
| **Tier 1** | Dashboard backend | `server/app.py` | REST and WebSocket API, process control, live updates |
| **Tier 1** | Dashboard UI | `server/static/index.html` | the single-page interface (Lab & Research tabs) |
| **Tier 1** | Statistics | `server/stats.py` | percentile, RFC 3550 jitter, per-sample statistics |
| **Tier 1** | Analysis | `server/analysis.py` | turns raw packet rows into the summary, endpoint table, histogram, percentile curves and scatter; exports; save and load |
| **Tier 1** | Naming | `server/naming.py` | the result-file naming convention, its parser, the scenario key |
| **Tier 1** | Host information | `server/hostinfo.py` | records CPU, sleep-state, NIC and load conditions for each run, with warnings |
| **Tier 1** | Housekeeping | `server/housekeeping.py` | checks for leftover probes, worker processes and NIC settings; reports memory |
| **Tier 1** | Report checker | `verify_analysis.py` | checks the figures in [10](10-results-analysis.md) against the saved runs |

---

## 2. Tier 1: Harness & Supervisory Architecture

### Why the probe is a separate process

The experiment is about what delays an event loop, so nothing but the experiment may run on that loop. If the web server shared the probe's event loop, its JSON encoding and WebSocket traffic would add delay to the very thing being measured. So every run is a **child process**:

* **Separate cores.** The child is pinned to its own core (the last allowed CPU); the web server pins itself to the others.
* **One-way output.** The child writes newline-delimited JSON (NDJSON) to its standard output; the server only reads it.
* **Multi-core mode.** The child is given all cores back (via `taskset`) so the engine can spread its work.

**The dashboard must never block the probe.**
- **The risk:** a child's standard output is a pipe with a 64 KiB kernel buffer. If the server stopped reading, the buffer would fill and the child's next write would block. In Python that would freeze the very event loop being measured.
- **The safeguard:** the server keeps reading separate from everything else.
  - The reader task only parses lines and appends them in memory.
  - Live updates are pushed by a separate task, at most every 0.5 s.
  - The analysis is computed in a worker thread, and every WebSocket send has a timeout.

### Event protocol (NDJSON on the probe's stdout)

The probe writes one JSON object per line. All three engines emit the same five event types (`start`, `cycle`, `late`, `tick`, `summary`), so the dashboard has no engine-specific code. Timestamps are integer nanoseconds (`CLOCK_REALTIME`); `null` means "not available".

**`start`** (once, after set-up)
```json
{"e":"start","clock":"SO_TIMESTAMPING software [go GOMAXPROCS=1]","notes":["receive queue: 16384 KiB"],
 "routes":[{"target":"10.0.0.5","interface":"enp0s31f6","src_ip":"10.0.0.2"}]}
```

**`cycle`** (one per finished endpoint cycle)
```json
{"e":"cycle","ep":7,"cyc":0,"target":"10.0.0.5","icmp_id":4103,"db_wait_ms":0.0,"db_ipc_ms":0.9,
 "db_start_ns":1792618704206301000,"db_end_ns":1792618704209305000,
 "canary":{"avg_lag_us":312.4,"p95_lag_us":619.2,"max_lag_us":2024.1,"samples":78},
 "packets":[[0, 1792618700206236991, 1792618700206286883, 1792618700206328902, null, 1, 12, 412000]]}
```

How to read a `cycle` event:
- **Packets.** Each packet is `[seq, tx_ns, kernel_rx_ns, user_rx_ns, hw_rx_ns, batch, wakeup, send_lag_ns]`. A lost packet has `null` receive times and batch/wakeup 0. `seq` is `cycle × pings + n`.
- **ORM window.** `db_start_ns` / `db_end_ns` mark the start and end of the cycle's ORM work on `CLOCK_REALTIME`, for the shading in the charts. For inline work this is the CPU spin; for Python multi-core it is the offloaded job.
- **`db_ipc_ms`** appears only for Python multi-core.
- **Canary.** The `canary` object describes the interval during which this endpoint's pings were in flight.
- **Receive queue.** The 8 MiB queue request is reported as 16384 KiB because the kernel doubles it for its own bookkeeping.

**`late`** (whenever a reply arrives after its ping timed out)
```json
{"e":"late","icmp_id":4103,"seq":6,"tx":1792618700206236991,"krx":1792618702306286883,"urx":1792618702306328902}
```
The server attaches it to the lost packet's row; if that cycle has not been reported yet, it waits for it. The analysis then classifies the loss by comparing `krx − tx` with the timeout.

**`tick`** (every 0.5 s while probing)
```json
{"e":"tick","t":1.5,"sent":120,"replied":120,"reader_calls":36,"recent_avg_us":328.8,"recent_max_us":932.6,"max_us":1131.7}
```

**`summary`** (once, at the end or on stop)
```json
{"e":"summary","sent":500,"replied":500,"reader_calls":44,"unmatched":0,"late":0,
 "canary":{"avg_lag_us":471.2,"p95_lag_us":1513.1,"max_lag_us":3000.0,"samples":167},
 "emit_us_total":894.6,"emit_n":12,"ipc_ms_mean":null,"ipc_ms_max":null,"stopped":false}
```

**Stopping a run.**
- The dashboard sends the probe an interrupt.
- The probe freezes its canary, emits `summary` with `"stopped": true`, and exits.
- The dashboard marks the run `stopped` and keeps the partial data.

---

## 3. Tier 2: Probing Engine Runtime Architecture

Tier 2 is the core measurement engine inside each probe subprocess. All three engines (Python, Go, and Rust) implement an identical functional state machine modelled on Ephemres, differing only in how their language runtime schedules tasks and handles CPU contention:

```text
                  ┌────────────────────────────────────────────────────────┐
                  │                Endpoint Cycle Loop                     │
                  │   (5 pings @ 8 s interval across 60 s cycle window)    │
                  └──────────────────────────┬─────────────────────────────┘
                                             │
                       Send Ping 1..5        │ (pings 1–5 sent on schedule)
                       ─────────────────────▶│
                                             │
                                             ▼
                  ┌────────────────────────────────────────────────────────┐
                  │                 All 5 Pings Complete                   │
                  │             (Wait for db_write_semaphore)              │
                  └──────────────────────────┬─────────────────────────────┘
                                             │
                                             ▼
                  ┌────────────────────────────────────────────────────────┐
                  │        Execute Synchronous ORM CPU Work (3.0 ms)       │
                  │                                                        │
                  │  * Python Single-Core: inline spin blocks event loop   │
                  │  * Python Multi-Core:  offloaded to ProcessPoolExecutor│
                  │  * Go:                 goroutine spins on OS thread    │
                  │  * Rust:               task spins on tokio worker      │
                  └──────────────────────────┬─────────────────────────────┘
                                             │
                                             ▼
                  ┌────────────────────────────────────────────────────────┐
                  │      1 ms Async I/O Sleep ──▶ Release Semaphore        │
                  │     Emit `cycle` NDJSON & sleep until next 60 s slot   │
                  └────────────────────────────────────────────────────────┘
```

### Internal engine subsystems
1. **Single raw socket multiplexing:** One non-blocking `SOCK_RAW` (`IPPROTO_ICMP`) socket serves up to 500 virtual endpoints (`0x1000 + i`), with an 8 MiB receive buffer (`SO_RCVBUFFORCE`) and a kernel `ICMP_FILTER` that drops non-Echo-Reply frames before user space.
2. **Drain-to-`EAGAIN` reader:** Whenever the runtime's I/O poller wakes on socket readability, the reader loop drains every queued packet via `recvmsg()` until `EAGAIN`, capturing the kernel arrival timestamp (`Clock A` from `cmsg` `SCM_TIMESTAMPING`) and the immediate user-space timestamp (`Clock B` on `CLOCK_REALTIME`) for each packet.
3. **Semaphore-gated post-cycle simulation:** After an endpoint finishes its 5 pings, it acquires `db_write_semaphore` (default 15), performs the synchronous CPU spin (`simulated_db_ms`, default 3.0 ms) plus a 1 ms asynchronous sleep, and releases the semaphore.
4. **Runtime concurrency comparison:**
   - **Python (`probe_lab.py`):** Cooperative coroutines on a single `asyncio` event loop; multi-core mode offloads the spin across a process boundary (`ProcessPoolExecutor`).
   - **Go (`workers/go_prober`):** Goroutines scheduled onto `GOMAXPROCS` OS threads (`1` in single-core, `N` in multi-core) with Go's integrated network poller.
   - **Rust (`workers/rust_prober`):** Compiled `tokio` tasks on either a single-threaded `current_thread` runtime or a multi-threaded work-stealing pool, reading the socket via `AsyncFd`.

For the complete side-by-side parity table, `cmsg` byte layout, CPU affinity pinning mechanics, and observed scheduler anomalies across Python, Go, and Rust, see [04 Engines](04-engines.md).

---

## 4. Run life cycle

1. **Start.** `POST /api/run` does the following:
   - validates the configuration and checks that the engine is built;
   - records the **host conditions** with `server/hostinfo.py`: CPU governor, sleep states, turbo, hyper-threading sibling, NIC interrupts and coalescing, load;
   - builds the command line and starts the child.

   A failed start is reported and does not block later runs.
2. **Probing.** The child:
   - opens the socket and starts the canary;
   - emits `start` and sends the warm-up pings;
   - **opens the canary gate**, then starts all endpoints on the schedule and emits `cycle` and `tick` events.
3. **End.** When all endpoints finish (or on stop), the child:
   - **closes the canary gate**;
   - emits `summary`;
   - restores any NIC setting it changed, and exits.
4. **Analysis.**
   - The server marks the run `done`, `stopped` or `error`; error text is taken from the child's standard error.
   - It computes the final analysis and pushes it to every connected browser.
5. **Batches.** For a batch (`POST /api/batch`), the server queues every run of every round up front, and starts the next one as soon as the previous one finishes `done`.
   - A stopped or failed run, or the Stop button, cancels the rest.
   - Each run's configuration carries `series_id`, `repeat` and `repeats`, which is how the dashboard groups repeats.
6. **Auto-save** (on by default). As soon as a run ends `done` or `stopped` with data, the server saves it to `test_results/` (CSV files, `.meta.json`, `INDEX.md` entry). This happens in a worker thread, before the next run of a batch starts.
   - `--no-autosave` turns this off. Runs then stay in memory until saved (**Save**, or **Save all unsaved**), and are lost when the dashboard closes.
   - Saved runs are loaded again when the server starts (see [07 Results and naming](07-results-and-naming.md)).

---

## 5. Process lifetime, shutdown and memory

Nothing of the lab may outlive the dashboard, and it must be possible to check that closing it left nothing behind.

* **The probe dies with the dashboard.** Every probe is started through `setpriv --pdeathsig TERM`. If the dashboard process ends for any reason (Ctrl-C, `kill`, `kill -9`, a crash, the terminal closed), the kernel sends the probe SIGTERM.
  - All three engines end cleanly on SIGTERM.
  - Python also stops its multi-core worker processes and restores the NIC setting.
  - Verified: after `kill -9` of the dashboard, every engine's processes (9 for Python multi-core) are gone within 1.5 s.
* **Backstop: a probe whose output is closed stops itself.** If nobody reads its standard output any more (dashboard gone, or `setpriv` missing), the probe's next event write fails.
  - Python then cancels its run, so the normal cleanup still happens.
  - Go and Rust exit; they never change the NIC.
  - The heartbeat writes every 0.5 s, so this takes at most half a second.
* **Teardown cannot be skipped.**
  - In the Python probe every cleanup step runs on its own: summary, canary, worker processes, socket reader, raw socket and NIC setting, CSV files. A failure in one is reported on standard error, and the others still run.
  - A signal arriving *during* the teardown (a second Ctrl-C, or SIGTERM) cannot cut it short either. Every Ctrl-C only means "stop the run" (Python's default would turn a second one into an immediate abort), and the teardown's one wait tolerates being interrupted.
* **One stop signal, from the dashboard only.** Each probe runs in its own process group. So Ctrl-C typed in the dashboard's terminal reaches the dashboard only, not also the probe and its worker processes. The dashboard then stops the probe once, in order.
* **The dashboard waits on shutdown.** Ctrl-C (or SIGTERM) does the following, then prints a **shutdown report**:
  - cancels any batch;
  - sends the probe Ctrl-C and waits up to 10 s;
  - then sends SIGTERM and waits 3 s;
  - then sends SIGKILL.

  ```text
  shutting down...
    probe pid 1833146 (…py-mc…): stopped with Ctrl-C (SIGINT); exited with code 0 after 0.0 s
    2 unsaved run(s) discarded: …
    this dashboard held 58.3 MB (…packets in memory); the system gets all of it back when the process exits
    check: no probe or worker process of the lab is left, and no NIC timestamping is left on
  dashboard closed.
  ```
  "KILLED (its cleanup did not run)" in that report means a probe ignored both signals. The closing check then says whether anything (e.g. a NIC setting) was left behind.
* **Start-up check.** On start, the dashboard looks for anything left from an earlier session:
  - probe or worker processes of this project still running;
  - NIC receive timestamping left on.

  Each finding is printed in the terminal and shown as a red banner, with the command that fixes it. Run the same check at any time with `sudo .venv/bin/python -m server.app --check`; the exit code is 1 if something is left.
* **Memory is bounded and visible.**
  - **Cost:** a packet row costs about 1 KB.
  - **Saved runs:** rows of runs that are **saved on disk** are released beyond a budget (`OBSERVER_ROW_BUDGET`, default 200 000 rows ≈ 200 MB), least recently used first, and reloaded from their CSV when needed.
  - **Unsaved runs:** these are **never released**, because their data exists nowhere else. With auto-save on there are none once a run ends. They are lost when the dashboard closes.
  - **Visibility:** the page header shows the server's memory, runs, packets in memory and unsaved runs. The browser keeps only the analyses of the runs selected.

---

## 6. Process and thread layout

| Mode | Processes | Threads that matter |
|---|---|---|
| Python single-core | server + 1 probe | probe: 1 (the event loop does everything, including the ORM spin) |
| Python multi-core | server + 1 probe + (CPUs − 1) ORM workers | probe: event loop + pool helper threads that pickle and unpickle |
| Go | server + 1 probe | goroutines on at most `GOMAXPROCS` OS threads |
| Rust single-core | server + 1 probe | 1 runtime thread |
| Rust multi-core | server + 1 probe | one runtime worker per CPU |

---

## 7. Security model

The dashboard has no login. It runs as root (for raw sockets) and can send ICMP from the machine, so it protects itself in three ways:

* **Local only by default.** It listens on `127.0.0.1` and prints a warning if told otherwise.
* **Same-origin requests only.** Every HTTP request and every WebSocket connection must carry a `Host` header naming the server. If a browser sends an `Origin`, it must equal the host. This stops other web pages open in your browser, and DNS-rebinding attacks, from driving the dashboard through your own browser. Scripts such as `curl` send no `Origin` and are allowed.
* **Validated settings.** Run configuration is checked against these limits:
  - 1–500 endpoints, 1–100 semaphore, 0–15 ms ORM, 0–600 s stagger;
  - 0.05–30 s interval, 1–60 cycles, a cycle long enough for one cycle's pings;
  - NIC hardware stamps only with Python, 1–32 IPv4 targets.
