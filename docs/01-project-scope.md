# 01 Project scope

Why the lab exists, and the theory and hypotheses behind it, are in [00 Research background](00-research-background.md). I built the lab for Ephemres, the parent project, and it models the Ephemres probing engine.

## The question

A network monitor sends ICMP echo requests (pings) from an application and reports the round-trip time (RTT) it sees. A reply's journey has two parts:
1. **The network part.** The reply crosses the network and reaches the machine.
2. **The waiting part.** The reply waits in a queue inside the operating system until the application reads it.

If the application is busy, for example preparing results for a database, the waiting part grows. The monitor then reports a longer RTT and more jitter than the network really had. This is the **observer effect**.

The lab measures that distortion on **every packet**, and sets out to answer five questions:

1. **How large is the distortion for a single-threaded `asyncio` monitor under a realistic workload?** The baseline models the open-source Ephemres engine on a single core, as it was first deployed on 1-vCPU Debian and Ubuntu virtual machines in GNS3 network simulations.
2. **How does it change with schedule and concurrency tuning?** I varied the schedule (burst at second 0, or staggered over 60 s), the endpoint count (25, 100, 250), whether post-cycle work runs (`0 ms` idle floor or a `3 ms` ORM spin) and the semaphore size (**5, 15, 30, 50**). The semaphore sweep tests the production change that raised the semaphore from 4 to 15 in the hope of better ICMP accuracy: does its size affect observer lag at all, and does higher concurrency (30, 50) swamp a single core?
3. **How do Go (`goroutines`) and Rust (`tokio`) compare against the baseline Python (`asyncio`) engine under identical loads?** I compare Go and Rust directly with the current Ephemres Python (`asyncio`) engine, both pinned to a single core (as in a resource-constrained deployment) and spread across every core of a modern multi-core machine, and set out what each runtime gains and loses.
4. **What does Python gain, and what does it pay, by moving CPU work into separate worker processes?** Does offloading to a `ProcessPoolExecutor` remove the event-loop delay, or do IPC pickling and GIL contention add new delays of their own?
5. **How do schedule design, hardware scaling, and language runtime each relate to the observer error measured here, for Ephemres and for monitoring platforms with a similar asynchronous probing architecture?** A user-space timestamp always comes after the kernel's, so without kernel timestamps the lag can't reach zero. How far can more cores and a different runtime reduce it, and what does each of Python, Go and Rust trade away?

The lab separates two effects:
- **Internal:** the monitor's own CPU work delays when it reads a reply.
- **External:** the probe traffic itself disturbs the target or the network.

Section 2 of the [background page](00-research-background.md) covers both.

## How it answers: two clocks on every packet

Each reply is timestamped twice, using the same clock (`CLOCK_REALTIME`), so the two stamps can be subtracted:

* **Clock A (kernel):** the operating system's own record of when the packet arrived, handed to the program together with the packet. It does not depend on what the program is doing.
* **Clock B (observer):** the program's own clock, read right after the program reads the packet.

`observer lag = Clock B − Clock A`. That's how long the packet waited for the program, which is the error the observer effect adds. Details are in [02 Test methodology](02-test-methodology.md).

## In scope

* **Two ways to run tests:** a terminal benchmark (`probe_lab.py`), and a live web dashboard to run, watch, save and compare runs.
* **Three engines with identical mechanics:** Python asyncio, Go and Rust (tokio).
* **Many virtual endpoints** on one or more target IP addresses, told apart by distinct ICMP identifiers, run in burst or staggered mode.
* **Simulated post-cycle database work** (a semaphore plus a CPU spin), in single-core and multi-core modes.
* **Measurement aids:** a scheduler "canary" in each runtime, and per-cycle statistics (min, max, average, p95, standard deviation, RFC 3550 jitter).
* **Results handling:**
  - saved results (CSV files, metadata, an index) under a naming convention;
  - comparison of up to 8 columns, where a column can combine a batch's repeats;
  - repeated batches with the engine order rotated each round;
  - an idle-floor measurement.

## Out of scope

* **Anything on the target.** The lab never requires running software or changing settings on the device being pinged (a Windows PC, a router, a GNS3 node, loopback). The target only has to answer ICMP echo.
* **Measuring the network itself.** The lab measures *the observer's* contribution. The wire RTT is reported only as the baseline the contribution is judged against.
* **A production monitor.** The ORM and database work is simulated with a CPU spin; there is no real database.
* **Authentication or multi-user hosting.** The dashboard is a local research tool (see [05 Dashboard](05-dashboard.md)).
* **Non-Linux hosts.** The kernel timestamping interface it uses is specific to Linux.

## Constraints that shape the design

* **Linux, a raw ICMP socket, and root (or the `cap_net_raw` capability).** These are needed to send echo requests and receive replies directly.
* **No target cooperation.** The target only has to echo back the ICMP identifier and sequence number, which RFC 792 requires of every implementation. That is how one socket can serve hundreds of virtual endpoints.
* **No mock data.** Every number comes from live sockets. The tests use fakes only to check the code.
* **Parity between engines.** Anything that could favour one language is treated as a bug: different packet bytes, different clocks, different schedules. See the parity table in [04 Engines](04-engines.md).

Every metric and chart is defined in [02 Test methodology](02-test-methodology.md) §3, and shared terms in the [glossary](../README.md#glossary). The results, and the questions they leave open, are in [10 Empirical Results and Comparative Analysis](10-results-analysis.md).
