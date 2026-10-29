# ephemres-observer-lab

A standalone lab that measures the **observer effect** in asynchronous ICMP network monitoring: how much delay a monitor adds to the round-trip times it reports. It's companion research for [Ephemres](https://github.com/dc8official/ephemres), which I also wrote.

I built it after noticing that Ephemres and a plain terminal `ping`, run on the same host, didn't quite agree. A monitor is software sharing the host's CPU and scheduler with everything else. If it's busy with its own post-processing when a reply arrives (computing cycle statistics, evaluating state machines, serialising database records), the reply waits in the operating system's socket receive buffer until the application gets round to reading it. The monitor then reports more latency and jitter than the wire actually had.

## How it measures: two clocks on every packet

Every ICMP echo reply is timestamped twice on the same clock (`CLOCK_REALTIME`, in nanoseconds):
- **Clock A (kernel):** recorded by the Linux kernel (`SO_TIMESTAMPING` or `SO_TIMESTAMPNS`) when the network stack receives the packet, and handed to the application as `recvmsg()` ancillary data (`cmsg`).
- **Clock B (observer):** recorded by the application runtime as soon as `recvmsg()` returns in user space.

```text
Observer Lag (Intrusion) = Clock B − Clock A
```

That gives the delay the application runtime adds, on every packet, without external capture hardware or any software on the target device.

The lab reproduces the Ephemres probing schedule (100 virtual endpoints, 5 pings per cycle 8 s apart, a 60 s cycle and stagger window, semaphore 15, a 3 ms simulated ORM CPU spin) and compares six runtime and CPU configurations:
- **Python (`asyncio`):** single-core inline, or multi-core with a `ProcessPoolExecutor` worker pool
- **Go (`goroutines`):** single-core (`GOMAXPROCS=1`) or multi-core (`GOMAXPROCS=N`)
- **Rust (`tokio`):** single-core (`current_thread`) or the multi-core work-stealing runtime

What the 173 recorded runs found, and what they leave open, is in [10 Results analysis](docs/10-results-analysis.md).

## Quick start

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

**Requirements:** Linux x86-64. Nothing is installed or changed on the target device, which only has to answer standard ICMP echo requests.

## Documentation

| Document | Contents |
|---|---|
| [00 Research background](docs/00-research-background.md) | Where the research started (terminal ping and Ephemres disagreeing on one host, the single-core GNS3 heritage, the semaphore 4 to 15 change and what the lab found about it), internal and external observer effects, the theory and published work, and the hypotheses |
| [01 Project scope](docs/01-project-scope.md) | The research questions, what is in and out of scope, and the design constraints |
| [02 Test methodology](docs/02-test-methodology.md) | Measurement model, workload defaults, metric definitions and formulas, replication rules and threats to validity |
| [03 Architecture (Part 1: Harness)](docs/03-architecture.md) | Two-tier architecture, part 1: the Tier 1 harness (supervisor, NDJSON IPC, analysis, lifecycle) and an overview of Tier 2 |
| [04 Architecture (Part 2: Engines)](docs/04-engines.md) | Two-tier architecture, part 2: the Tier 2 probing engines (Python, Go, Rust) side by side, `cmsg` timestamp extraction, CPU modes and how each runtime schedules work |
| [05 Dashboard](docs/05-dashboard.md) | Web UI guide, comparison table and chart reference, HTTP and WebSocket API, and security model |
| [06 Reference](docs/06-reference.md) | Command-line flags, environment variables, system requirements and operational limits |
| [07 Results and naming](docs/07-results-and-naming.md) | File naming convention, scenario keys, per-packet and per-cycle CSV columns, and recorded corpora |
| [08 Development](docs/08-development.md) | Coding conventions, unit and network-namespace tests, adding an engine, and troubleshooting |
| [09 Replication guide](docs/09-replication.md) | Host preparation step by step, the experimental protocol, a reporting checklist and the full dashboard controls reference |
| [10 Results analysis](docs/10-results-analysis.md) | **Findings:** analysis of all 173 benchmark runs across engines, CPU modes, semaphores, endpoint counts, and burst and staggered schedules |

## Repository layout

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
verify_analysis.py           Checks every metric cited in docs/10-results-analysis.md against the raw runs
docs/                        Project documentation (00 to 10)
```

## Glossary

| Term | Meaning |
|---|---|
| **ICMP echo / ping** | The standard reachability and round-trip test (RFC 792): the prober sends an Echo Request and the target returns an Echo Reply carrying the same 16-bit identifier and sequence number. |
| **RTT (round-trip time)** | Time from sending the Echo Request (`tx`) to receiving the Echo Reply, reported in microseconds (`µs`) or milliseconds (`ms`; `1 ms = 1,000 µs`). |
| **Kernel** | The Linux operating system core. It handles network interface interrupts, copies arriving packets into socket receive buffers and records arrival timestamps before any user-space scheduling. |
| **User space** | Where application processes (Python, Go, Rust) run, outside the kernel. A packet sits in the kernel's socket receive buffer until the process calls `recvmsg()`. |
| **Clock A / Clock B** | The two `CLOCK_REALTIME` timestamps taken on every reply. **Clock A** is the kernel arrival stamp (`SO_TIMESTAMPING` or `SO_TIMESTAMPNS`). **Clock B** is the user-space timestamp read as soon as `recvmsg()` returns. |
| **Observer lag (intrusion)** | `Clock B − Clock A`: how long a reply waited in the kernel socket buffer before the application read it. This is the error the observer adds. |
| **Kernel RTT** | `Clock A − tx`: the round-trip time as the kernel sees it, used as the reference RTT without user-space receive delay. |
| **Observer RTT** | `Clock B − tx = Kernel RTT + Observer lag`: the round-trip time a user-space monitoring application reports. |
| **Raw socket** | A `SOCK_RAW` (`IPPROTO_ICMP`) socket that lets a process build and read ICMP packets directly; it needs `root` or `cap_net_raw`. |
| **Event loop** | A single-threaded cooperative scheduler (such as Python's `asyncio`) that multiplexes I/O tasks and callbacks. Synchronous CPU work in any coroutine blocks the whole loop, socket reads included. |
| **Goroutine / tokio task** | Lightweight user-space threads in Go, and asynchronous tasks in Rust's `tokio` runtime. They can run on one OS thread (single-core mode) or across an M:N thread pool (multi-core mode). |
| **Single-core / multi-core mode** | Single-core pins the probe process to one CPU core and one execution thread, modelling the 1-vCPU Debian and Ubuntu VMs in the GNS3 environment where Ephemres was first designed. Multi-core lets Go and Rust use every core, and moves Python's CPU work to a `ProcessPoolExecutor`. |
| **Virtual endpoint** | A simulated monitored device with its own ICMP identifier (`0x1000 + i`), so up to 500 concurrent endpoints can share one raw socket and one or more target IPs. |
| **Cycle** | One endpoint's repeating unit of work: sending `pings` (5 by default) every `interval` (8 s by default), then taking the semaphore and doing the post-cycle database write. |
| **ORM work** | The synchronous CPU work after an endpoint's pings complete (statistics, state-machine evaluation, building ORM objects, serialising SQL parameters), simulated as a deterministic CPU spin (`3.0 ms` by default). |
| **Semaphore (`db_write_semaphore`)** | Caps how many endpoints can do their post-cycle database write at once (15 by default). Ephemres raised it from 4 expecting better ICMP accuracy; under the 60 s stagger the lab found no measurable effect. |
| **Staggered / burst** | Schedule shapes. *Staggered* spreads endpoint start offsets evenly across `stagger_window` (60 s by default); *burst* (`0 s`) starts every endpoint at the same instant. |
| **Idle floor** | A baseline control run with the same probing parameters but `simulated_db_ms = 0.0`. It measures the runtime's own wake-up and socket-read cost with no ORM work. |
| **Canary** | A background task that sleeps in 10 ms ticks and records how late it wakes (`elapsed − 10 ms`), which measures scheduler starvation independently of network traffic. |
| **Median, mean, p95, p99** | Summary statistics: the median (`p50`) is the 50th percentile, the mean is the arithmetic average, and `p95` and `p99` are the 95th and 99th percentiles, which describe the tail. |
| **Ephemres** | The production network monitoring platform whose probing architecture and default parameters this lab models. |

## Author contributions and AI assistance

I developed the software harness, the probing engines (Python, Go, Rust) and the verification suites with agentic AI coding tools (Google Gemini / Antigravity and Anthropic Claude) as pair programmers, under my own architectural direction. The hypotheses, test methodology, kernel instrumentation design and interpretation of the data are mine. I reviewed all of the code and take full responsibility for the integrity, reproducibility and correctness of the published findings.

## Licence

Apache License 2.0: see [LICENSE](LICENSE) and [NOTICE](NOTICE). Chart.js, vendored in `server/static/vendor/`, is MIT licensed.
