# 04 Architecture (Part 2): Probing Engines (Python, Go and Rust)

This is **part 2 of the architecture** (part 1 is [03 Architecture (Part 1): Harness, IPC Protocol and Process Isolation](03-architecture.md)) and covers the **Tier 2 probing engines**. All three engines implement the same lab mechanics (see the fairness rules in [02 Test methodology](02-test-methodology.md)), so that a difference in measured distortion can be put down to how each runtime schedules work and manages memory, not to differences in the implementations. Terms are defined in the [glossary](../README.md#glossary).

Each engine opens the same raw ICMP socket, sends the same packets on the same schedule, reads the same kernel timestamp, and performs the same simulated work. The only intended difference is *how the language runtime executes concurrent tasks and handles CPU contention*:
- **Python:** runs all coroutines on a single-threaded cooperative event loop (`asyncio`), with optional multi-core process offloading.
- **Go:** multiplexes goroutines over operating-system threads via an M:N scheduler and network poller.
- **Rust:** runs asynchronous tasks on `tokio` (single-thread `current_thread` vs. multi-thread work-stealing).

## Parity at a glance

| Mechanic | Python (`probe_lab.py`) | Go (`workers/go_prober`) | Rust (`workers/rust_prober`) |
|---|---|---|---|
| Socket | raw ICMP, non-blocking, ICMP filter = echo replies only, 8 MiB receive queue | same (`syscall`) | same (`libc`) |
| Reader | `loop.add_reader` callback | a goroutine parked in the network poller | a tokio task awaiting `AsyncFd::readable()` |
| Kernel stamp (Clock A) | cmsg from `recvmsg_into` | cmsg from `syscall.Recvmsg` | cmsg from `libc::recvmsg` |
| User stamp (Clock B) | `time.clock_gettime_ns(CLOCK_REALTIME)` right after the read | `time.Now().UnixNano()` right after the read | `clock_gettime(CLOCK_REALTIME)` right after the read |
| Endpoint | coroutine | goroutine | tokio task |
| Semaphore | `asyncio.Semaphore` | buffered channel | `tokio::sync::Semaphore` |
| ORM CPU spin | inline busy loop (single) / process pool (multi) | busy loop in the goroutine | busy loop in the task |
| Canary | asyncio task, `asyncio.sleep(0.010)` | goroutine, `time.Sleep(10ms)` | tokio task, `tokio::time::sleep(10ms)` |
| Single core | process pinned to one core | `GOMAXPROCS=1` + `taskset` re-launch | current-thread runtime + `sched_setaffinity` |
| Multi core | event loop on one core, ORM in `ProcessPoolExecutor` | `GOMAXPROCS` = CPUs | multi-thread runtime, one worker per CPU |
| Hardware timestamps | opt-in (`--hw`), off by default | no | no |
| Cycles per run | any | any (`--cycles`, `--cycle-length`) | any (`--cycles`, `--cycle-length`) |
| Late replies | timed-out pings kept; late reply reported (`late` event) | same | same |
| Send lag | `loop.time()` vs the slot | `time.Since(slot)` | `tokio::time::Instant` vs the slot |
| ORM work window | `CLOCK_REALTIME` around the spin (or the offloaded job) | `time.Now()` around the spin | `clock_gettime` around the spin |

## How each engine reads the kernel timestamp

The kernel hands over the packet and a "control message" (cmsg) in one `recvmsg` call. For `SCM_TIMESTAMPING`, the control message's data is a `struct scm_timestamping`: **three `struct timespec`** back to back. Each is `{int64 seconds, int64 nanoseconds}` (16 bytes, little-endian on x86-64):

```
bytes  0..15   timespec[0]  software stamp   <- Clock A
bytes 16..31   timespec[1]  legacy, unused
bytes 32..47   timespec[2]  raw NIC hardware stamp (0 when hardware stamping is off)
```

The same 48 bytes, in three languages:

```python
# Python: struct.unpack reads all six 64-bit integers at once
s0, n0, _s1, _n1, s2, n2 = struct.Struct("=6q").unpack_from(data)
kernel_ns = s0 * 1_000_000_000 + n0
```
```go
// Go: ParseSocketControlMessage splits the raw bytes into messages; read the integers explicitly
msgs, _ := syscall.ParseSocketControlMessage(oob[:oobn])
sec  := int64(binary.LittleEndian.Uint64(m.Data[0:8]))
nsec := int64(binary.LittleEndian.Uint64(m.Data[8:16]))
```
```rust
// Rust: walk the control messages with the libc macros and reinterpret the bytes as [timespec; 3]
let ts: [libc::timespec; 3] = std::ptr::read_unaligned(libc::CMSG_DATA(c) as *const [libc::timespec; 3]);
```

When the stamp is missing or refused:
- **No software stamp** (both fields zero): the kernel RTT and lag are reported as `null`.
- **`SO_TIMESTAMPING` refused by the kernel:** all engines fall back to the older `SO_TIMESTAMPNS`, which carries one timespec.

**All three readers empty the queue.** On each wakeup they read until the kernel reports the queue empty (`EAGAIN`), then hand the replies to the waiting endpoints.

## Python

* **One thread, one event loop.** A coroutine keeps the thread until it reaches an `await`.
* **single_core:** the ORM spin runs on the loop.
  - While it runs, the reader callback cannot, so every other endpoint's replies wait in the kernel queue.
  - This is the behaviour of a single-threaded monitor.
* **multi_core:** the spin is sent with `loop.run_in_executor` to a `ProcessPoolExecutor` of CPUs − 1 workers.
  - The workers are started with `spawn` (fresh interpreters) and run `server/orm_burn.py`.
  - They are started and warmed up *before* the canary gate opens, and are kept off the event loop's core.
  - The cost of the process boundary is real, and is reported as ORM offload overhead.
* **Extra: optional NIC hardware timestamps** (`--hw`). They are off by default because Go and Rust never touch the NIC, so a run with them on is not comparable across engines.

## Go

* **Goroutines and threads.** Goroutines are run by at most `GOMAXPROCS` operating-system threads. The reader is an ordinary goroutine waiting in Go's network poller; the socket is opened non-blocking so the poller owns it.
* **single_core:** `GOMAXPROCS=1`.
  - The program first re-launches itself under `taskset -c N`.
  - The reason: `sched_setaffinity` applies per thread, and the Go runtime has already started several threads by the time `main` runs. `taskset` sets the CPU mask before the runtime starts, so every thread inherits it.
* **multi_core:** the default `GOMAXPROCS` (all CPUs). The reader can run on another thread while an ORM spin burns.
* **Static binary.** There is no cgo, so the binary is static, which is what makes `setcap` clean.

## Rust

* **tokio runtime.**
  - **single_core:** `new_current_thread()`, where one thread runs every task, like asyncio. The process is first pinned with `sched_setaffinity` in `main`, before any thread exists.
  - **multi_core:** `new_multi_thread()`, with one worker per CPU (work stealing).
* **Reader.** The reader is a task on `AsyncFd`. After emptying the queue to `EAGAIN` it calls `clear_ready()` so that epoll is re-armed.
* **ORM spin.** The spin runs inline in the task, like Python's inline spin, rather than on `spawn_blocking`, for parity.

## Runtime scheduler and timer mechanics

Each runtime schedules timers, I/O readiness callbacks and runnable tasks differently, and that's the background you need to read the measurements in [10 Empirical Results and Comparative Analysis](10-results-analysis.md). A caution first: this section describes how the runtimes are designed and documented to behave. Where docs/10 ties a measured effect to one of these mechanisms (Go's run-queue ordering, tokio's poll budget, tokio's work-stealing delay), it marks the link as a *hypothesis*, because no run tested the mechanism directly.

* **Go (`GOMAXPROCS=1`) run-queue ordering and timer-woken goroutines.**
  - Under `GOMAXPROCS=1`, all runnable goroutines share a single logical processor (`P`). When many endpoint goroutines complete their final ping simultaneously and contend for the semaphore and CPU spin, newly runnable goroutines woken by a timer (such as the 10 ms scheduler canary or an outbound ping slot) can queue behind the full batch of runnable endpoint goroutines rather than preempting to the front of the queue.
  - Because only one CPU spin can execute on the single OS thread at a time regardless of how many permits the buffered channel holds, varying `db_write_semaphore` under `GOMAXPROCS=1` changes how many goroutines hold a permit simultaneously, not how much total CPU work executes on the single processor.
  - When `GOMAXPROCS` scales across multiple cores (`multi_core`), the network poller and reader goroutine can execute on a spare OS thread while other threads execute CPU spins.
* **Go (`GOMAXPROCS=1`) send-slot scheduling delay.**
  - When an outbound ping's scheduled timer slot falls inside another endpoint's synchronous CPU spin on a single logical processor, the sending goroutine is delayed until the spin yields, producing send-side observer lag (`send_lag_us`).
* **Rust (`tokio`) single-thread cooperative task budget vs. I/O driver polling.**
  - In `tokio::runtime::Builder::new_current_thread()`, synchronous CPU spins inside tasks block the single thread for up to `semaphore × simulated_db_ms`, which directly delays timer tasks such as the canary.
  - However, `tokio`'s single-thread scheduler periodically polls its I/O driver (`epoll`) after a fixed task poll budget (cooperative scheduling quantum), allowing the `AsyncFd` socket reader task to drain queued replies earlier than the end of the entire semaphore batch.
  - In `new_multi_thread()`, tasks are distributed across worker threads with work-stealing, though a task or reader assigned to a worker currently executing an inline spin can still experience a single spin's worth of delay before work-stealing or the next poll boundary intervenes.
* **Rust (`tokio`) 1 ms timer wheel granularity.**
  - `tokio`'s hierarchical timer wheel operates at a 1 ms tick resolution. So Rust's idle 10 ms canary and its scheduled ping slots show a baseline of about 1 ms even when the CPU has nothing else to do. Compare canary and send-lag *increases* under load between engines, not raw idle levels.
* **Python (`asyncio`) selector rounding, burst send loops, and `ProcessPoolExecutor` GIL contention.**
  - Python's `epoll` selector rounds timeout arguments to whole milliseconds, giving its idle canary a baseline of a few hundred microseconds.
  - Because `asyncio` executes all coroutines and socket callbacks sequentially in bytecode on a single thread, firing and draining 100 simultaneous endpoints in a burst (`stagger_window = 0 s`) incurs a multi-millisecond serial send/receive loop cost even when `simulated_db_ms = 0`.
  - In `multi_core` mode (`loop.run_in_executor` with `ProcessPoolExecutor`), offloading removes the inline CPU spin from the event loop thread, but `pickle` serialisation and pipe communication run on helper threads inside the main process that contend with the `asyncio` event loop for the Global Interpreter Lock (GIL), and jobs exceeding the worker count (`CPUs − 1`) queue for a free worker.
* **Host CPU C-state wake-up latency vs. active load.**
  - On hosts where deep processor idle states (`C-states`) are enabled, an unloaded core during an idle floor (`simulated_db_ms = 0`) can enter deeper sleep states between packets and take longer to wake on a NIC interrupt than a core kept in `C0` by periodic CPU work. How these runtime and hardware mechanisms show up across the 173 recorded runs is evaluated in [10 Results analysis](10-results-analysis.md) (§R1 to §R3).

## Building the compiled engines

```bash
./build_workers.sh              # builds bin/go_prober and bin/rust_prober, then asks sudo for setcap
./build_workers.sh --no-setcap  # build only
```

What the script does:
- **Finds the toolchains** in the usual user-level install locations: `~/go-toolchain/go/bin`, `/usr/local/go/bin`, `~/go/bin`, `~/.cargo/bin`.
- **Skips an engine whose toolchain is missing.** The dashboard then greys that engine out.
- **Applies `cap_net_raw+ep`**, so a normal user can run a worker by hand. The dashboard runs as root and does not need the capability.

Re-apply the capability after every rebuild, because it is stored on the file itself.
