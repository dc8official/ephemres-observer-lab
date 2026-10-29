# ephemres-observer-lab

A standalone measurement lab that quantifies the **observer effect** in asynchronous ICMP network monitoring. It is companion research for [Ephemres](https://github.com/dc8official/ephemres), by the same author.

When a network monitoring program pings devices and reports round-trip times (RTT), the program itself is software sharing CPU and scheduling resources on the host. If the program is busy with its own post-processing work when a reply arrives (for example, computing cycle statistics, evaluating state machines, and serialising database records), the reply waits in the operating system's socket receive buffer until the application reads it. The monitor then reports a higher latency and jitter than actually occurred on the wire.

## How It Measures: Dual Clocks on Every Packet

Every ICMP echo reply is timestamped twice on the same clock (`CLOCK_REALTIME` nanoseconds):
- **Clock A (kernel):** recorded by the Linux kernel (`SO_TIMESTAMPING` / `SO_TIMESTAMPNS`) when the network stack receives the packet, handed to the application via `recvmsg()` ancillary data (`cmsg`).
- **Clock B (observer):** recorded by the application runtime immediately after `recvmsg()` returns in user space.

```text
Observer Lag (Intrusion) = Clock B − Clock A
```

This isolates the exact microsecond delay added by the application runtime on every single packet, without requiring external hardware capture cards or any software on the target device.

The lab reproduces the probing schedule of the Ephemres monitoring engine (100 virtual endpoints, 5 pings per cycle at 8 s intervals, 60 s cycle and stagger window, semaphore 15, 3 ms simulated ORM CPU spin) and compares six runtime and CPU configurations:
- **Python (`asyncio`):** single-core inline vs. multi-core `ProcessPoolExecutor` worker pool
- **Go (`goroutines`):** single-core (`GOMAXPROCS=1`) vs. multi-core (`GOMAXPROCS=N`)
- **Rust (`tokio`):** single-core (`current_thread`) vs. multi-core work-stealing runtime

## Quick Start

```bash
# 1. Set up the Python virtual environment and build the Go and Rust engines
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./build_workers.sh                       # optional: builds bin/go_prober and bin/rust_prober (needs go and cargo)

# 2. Launch the live web dashboard (root is required for raw ICMP sockets)
sudo .venv/bin/python -m server.app      # open http://127.0.0.1:8080

# 3. Or run a single benchmark from the terminal with Ephemres defaults
sudo python3 probe_lab.py --targets 10.0.0.5 --virtual-endpoints 100 --interval 8 --stagger-window 60 --cycles 3 --cycle-length 60

# 4. Run the unit test suite and verify the empirical report against test_results/
.venv/bin/python -m unittest discover -s tests -t .
python3 verify_analysis.py
```

**Requirements:** Linux x86-64. Nothing is installed or changed on the target device, which only needs to answer standard ICMP echo requests.

## Documentation

| Document | Contents |
|---|---|
| [00 Research background](docs/00-research-background.md) | Origin of the research (field discovery of terminal ping vs. app RTT discrepancy, GNS3 1-core legacy, the semaphore 4→15 change and what the lab found about it), internal vs. external observer effects, theoretical framework, core vs. extended literature review, and hypotheses |
| [01 Project scope](docs/01-project-scope.md) | Core research questions, in-scope and out-of-scope boundaries, and design constraints |
| [02 Test methodology](docs/02-test-methodology.md) | Measurement model, workload defaults, metric definitions and formulas, statistical replication rules, and threats to validity |
| [03 Architecture (Part 1: Harness)](docs/03-architecture.md) | Two-tier system architecture (Part 1): Tier 1 Harness (supervisor, NDJSON IPC, analysis, lifecycle) and high-level Tier 2 overview |
| [04 Architecture (Part 2: Engines)](docs/04-engines.md) | Two-tier system architecture (Part 2): Tier 2 probing engines (Python, Go, Rust) side-by-side parity, `cmsg` timestamp extraction, CPU modes, and runtime scheduler mechanics |
| [05 Dashboard](docs/05-dashboard.md) | Web UI guide, comparison table and chart reference, HTTP/WebSocket API, and security model |
| [06 Reference](docs/06-reference.md) | Command-line flags, environment variables, system requirements, and operational limits |
| [07 Results and naming](docs/07-results-and-naming.md) | File naming convention, scenario keys, per-packet and per-cycle CSV column schemas, and recorded corpora |
| [08 Development](docs/08-development.md) | Coding conventions, unit and network-namespace test suites, adding an engine, and troubleshooting |
| [09 Replication guide](docs/09-replication.md) | Step-by-step host preparation, experimental protocol, reporting checklist, and complete dashboard controls reference |
| [10 Results analysis](docs/10-results-analysis.md) | **Empirical findings:** comparative analysis of all 173 benchmark runs across engines, CPU modes, semaphores, endpoint counts, and burst vs. staggered schedules |

## Repository Layout

```text
probe_lab.py                 Python probing engine and CLI benchmark runner
server/                      Kernel clock, canary, statistics, analysis, naming, and FastAPI dashboard backend
server/static/index.html     Single-page web interface (Lab & Research tabs)
workers/go_prober/           Go probing engine (standard library only)
workers/rust_prober/         Rust probing engine (tokio + libc + serde_json)
build_workers.sh             Builds compiled Go and Rust engines into ./bin
bin/                         Compiled worker binaries (generated by build_workers.sh)
test_results/                173 recorded benchmark runs (.csv, _cycles.csv, .meta.json) and INDEX.md
tests/                       Unit and network-namespace test suite (104 tests, runs without root)
verify_analysis.py           Programmatically verifies all metrics cited in docs/10-results-analysis.md
docs/                        Project documentation (00 through 10)
```

## Glossary

| Term | Meaning |
|---|---|
| **ICMP echo / ping** | Standard network reachability and round-trip test (RFC 792): the prober sends an Echo Request and the target returns an Echo Reply echoing the 16-bit identifier and sequence number. |
| **RTT (round-trip time)** | Elapsed time from sending the Echo Request (`tx`) to receiving the Echo Reply, reported in microseconds (`µs`) or milliseconds (`ms`; `1 ms = 1,000 µs`). |
| **Kernel** | The Linux operating system core, which handles network interface interrupts, copies arriving packets into socket receive buffers, and records arrival timestamps before user-space scheduling. |
| **User space** | Where application processes (Python, Go, Rust) execute outside the kernel. A packet sits in the kernel's socket receive buffer until the user-space process calls `recvmsg()`. |
| **Clock A / Clock B** | The two `CLOCK_REALTIME` timestamps captured on every reply. **Clock A** is the kernel arrival stamp (`SO_TIMESTAMPING` / `SO_TIMESTAMPNS`). **Clock B** is the user-space timestamp read immediately after `recvmsg()` returns. |
| **Observer lag (intrusion)** | `Clock B − Clock A`: how long a reply waited in the kernel socket buffer before the application read it. This is the measurement error added by the observer. |
| **Kernel RTT** | `Clock A − tx`: the round-trip time as seen by the kernel, used as the reference RTT free of user-space receive delays. |
| **Observer RTT** | `Clock B − tx = Kernel RTT + Observer lag`: the round-trip time reported by a user-space monitoring application. |
| **Raw socket** | A `SOCK_RAW` (`IPPROTO_ICMP`) socket allowing a process to construct and read ICMP packets directly; requires `root` or `cap_net_raw`. |
| **Event loop** | A single-threaded cooperative scheduler (such as Python's `asyncio`) that multiplexes I/O tasks and callbacks; synchronous CPU work in any coroutine blocks the entire loop, including socket reads. |
| **Goroutine / tokio task** | Lightweight user-space threads in Go and asynchronous tasks in Rust's `tokio` runtime, which can be scheduled onto one OS thread (single-core mode) or across an M:N thread pool (multi-core mode). |
| **Single-core / multi-core mode** | Single-core pins the probe process to one CPU core on a single execution thread (modelling the 1-vCPU Debian/Ubuntu VMs in the GNS3 simulated network environment where Ephemres was originally designed). Multi-core allows Go and Rust to use all cores and offloads Python's CPU work to a `ProcessPoolExecutor`. |
| **Virtual endpoint** | A simulated monitored device assigned a distinct ICMP identifier (`0x1000 + i`), allowing up to 500 concurrent endpoints to share one raw socket and one or more target IPs. |
| **Cycle** | One endpoint's repeating unit of work: sending `pings` (5 by default) at `interval` (8 s by default), followed by acquiring the semaphore and executing the post-cycle database write. |
| **ORM work** | The synchronous CPU work performed after an endpoint's pings complete (statistics, state-machine evaluation, ORM object construction, and SQL parameter serialisation), simulated as a deterministic CPU spin (`3.0 ms` by default). |
| **Semaphore (`db_write_semaphore`)** | Concurrency limiter (15 by default; raised from 4 in Ephemres in the expectation that it would improve ICMP measurement accuracy, though the lab found no measurable effect under the 60 s stagger) capping how many endpoints may execute their post-cycle database write simultaneously. |
| **Staggered / burst** | Schedule shapes: *staggered* spreads endpoint start offsets evenly across `stagger_window` (60 s by default); *burst* (`0 s`) starts all endpoints at the exact same instant. |
| **Idle floor** | A baseline control run with identical probing parameters but `simulated_db_ms = 0.0`, measuring the runtime's inherent wake-up and socket-read cost without ORM work. |
| **Canary** | A background task that sleeps in 10 ms ticks and records wake-up lateness (`elapsed − 10 ms`), measuring scheduler starvation independently of network traffic. |
| **Median, mean, p95, p99** | Summary statistics: the median (`p50`) is the 50th percentile; the mean is the arithmetic average; `p95` and `p99` are the 95th and 99th percentiles capturing tail latency. |
| **Ephemres** | The production network monitoring platform whose probing architecture and default parameters this lab models. |

## Author Contributions & AI Assistance

The software harness, multi-runtime probing engines (Python, Go, Rust), and benchmark verification suites in this work were developed with the assistance of agentic AI coding tools (Google Gemini / Antigravity and Anthropic Claude) acting as pair programmers under the direct architectural supervision of the author. All experimental hypotheses, test methodologies, kernel instrumentation designs, and data interpretations were conceived and directed by the author, who reviewed all code and takes full responsibility for the scientific integrity, reproducibility, and correctness of the published findings.

## License

Apache License 2.0: see [LICENSE](LICENSE) and [NOTICE](NOTICE). Chart.js, vendored in `server/static/vendor/`, is MIT licensed.
