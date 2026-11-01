# 08 Development

This page is for anyone changing the code: the conventions, the tests, how to run real sockets without root, how to add an engine, and what to do when something goes wrong.

## Coding conventions

* **Comments explain the system clearly.** The code is written so that a network security engineer moving into systems programming can trace every byte.
  - Explain what a struct holds, why a call is made, and what the kernel or runtime does; not what the syntax says.
  - Cover low-level ideas where they appear: raw socket queues, `cmsg` ancillary data, `ioctl` structs, event-loop scheduling, CPU affinity.
  - Don't label a comment as "plain English"; just write it that way.
* **Comments must stay true.**
  - When behaviour changes, update the comment in the same edit.
  - Quote only kernel facts you have verified, for example that `SO_RCVBUF` is capped at `rmem_max`, or that tokio timers have 1 ms resolution.
* **No placeholder numbers.** Anything shown to the user comes from live sockets. Tests use fakes only to check the code.
* **Graceful fallback.** If hardware timestamping is unavailable (a virtual NIC, loopback, GNS3, no root), fall back to software kernel timestamps; never crash.
* **Parity first.** A change to one engine's mechanics (packet bytes, schedule, ORM work, canary, matching) must be made in all three, and the parity table in [04 Engines](04-engines.md) updated.
* **Never touch the target.** No feature may require software or configuration on the device being pinged.
* **Keep the report checkable.** When [10 Results analysis](10-results-analysis.md) quotes a new figure, add a check for it to `verify_analysis.py`.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -t .   # 104 tests, about 25 seconds
python3 -m unittest                                   # works too; dashboard tests skip if FastAPI is missing
python3 verify_analysis.py                            # checks every figure in docs/10 against test_results/
```

**Isolation.** Every test uses a throwaway results folder (set in `tests/__init__.py`), so nothing a test does can write into the real `test_results/`.

**No root, no network.** The tests run without either: the raw socket, the NIC ioctl and the probe subprocess are replaced by small fakes.

**What each test file covers:**

| Test file | Covers |
|---|---|
| `test_analysis` | analysis and exports |
| `test_naming` | naming round trips, including every saved file |
| `test_packets` | packet bytes and checksum |
| `test_reader` | reply matching and the definition of a wakeup |
| `test_hw_timestamp` | reading and restoring the NIC setting |
| `test_dashboard` | the request guard, failed starts, the guarantee that a slow dashboard never blocks the probe; idle-floor matching and batches (round rotation, floor-before-test, Stop cancelling the rest) |
| `test_engines` | the compiled engines' argument checks (skipped if not built) |
| `test_shutdown` | clean shutdown, a probe whose reader disappears, signals arriving during the teardown |
| `test_late_and_warmup` | late replies, loss causes, send lag, the warm-up cycle, note editing, the three error-% definitions, burst windows, the tiny-RTT rule, combining repeats |
| `test_lifecycle` | process lifetime and memory: the parent-death signal, shutdown escalation, the leftover check, the row budget |
| `test_hostinfo` | host-condition warnings |
| `test_manage_results` | save selected, delete to `.deleted/`, auto-save, a reloaded run keeping its start time, clock and route |
| `test_controls_documented` | every dashboard control is documented, and the replication guide's table matches the page (needs `node`). Regenerate the table with `.venv/bin/python -m tests.test_controls_documented --print` |
| `test_page_loads` | the page's script runs from top to bottom: it executes the real script in Node with a stand-in DOM, because a syntax check cannot catch a helper used before it is defined |
| `test_live_netns` | see below |

**`test_live_netns`** runs all three engines on **real raw sockets** without root.
- **How:** `unshare -rn` gives it a private network namespace, and `tc netem` delays that namespace's loopback so every reply is late.
- **What it checks:** that the engines emit identical cycles, sequence numbers, send-lag fields and late-reply events, and that a terminal run writes its CSV, `.meta.json` and `INDEX.md`.
- **When it skips itself:** where unprivileged user namespaces or `tc` are unavailable.

## Running real sockets without sudo

A private network namespace gives you root-like rights on a private loopback, so the whole stack can be exercised without touching the host:

```bash
unshare -rn sh -c "ip link set lo up; python3 probe_lab.py --targets 127.0.0.1 --virtual-endpoints 20 --burst --csv ''"
unshare -rn sh -c "ip link set lo up; ./bin/go_prober --targets 127.0.0.1 --virtual-endpoints 20 --stagger-window 1"
```

- **`--csv ''`** skips file output.
- **No NIC features:** hardware timestamping and NIC-setting changes are not available in a namespace; the probe reports software stamps only.
- **Driving the dashboard:** start the server and a test client inside one `unshare` shell.
- **Keeping results apart:** use `OBSERVER_RESULTS_DIR` to keep test runs out of `test_results/`.

## Adding an engine

1. **Command line and events.** Implement the same flags ([06 Reference](06-reference.md)) and the five NDJSON events: `start`, `cycle`, `late`, `tick` and `summary` ([03 Architecture](03-architecture.md)).
2. **Parity.** Match every row of the parity table in [04 Engines](04-engines.md):
   - the packet bytes;
   - both clocks in `CLOCK_REALTIME`;
   - registration before sending;
   - the schedule formula and cycles (`seq = cycle × pings + n`);
   - semaphore + spin + 1 ms sleep;
   - the 10 ms canary with its gate;
   - the wakeup definition;
   - the 8 MiB receive queue;
   - late-reply events;
   - send lag (the 8th packet field);
   - no NIC changes.
3. **Wiring.**
   - Register the binary path in `WORKER_BIN`, and the engine code in `server/naming.py` (`ENGINE_CODES`).
   - Add the option to the UI's engine select.
   - Add the build to `build_workers.sh`.
4. **Tests.**
   - Add the engine to `ENGINES` in `tests/test_live_netns.py`.
   - Write argument-check tests like those in `tests/test_engines.py`.
   - Compare a loopback run with the existing engines before trusting it.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| every ping is lost (`0/5`) | the target cannot be reached from this host. Check the route line at start-up (`route: <target> via <iface> (src <ip>)`); the host's source address must be in the target's subnet or the ping goes to a gateway. Check that `ping` works; on Windows, allow inbound echo requests |
| `PermissionError` | raw sockets need root: run with `sudo` (the dashboard shows a banner when it is not root) |
| a dashboard "won't close", keeps its port and memory, and shows state `T` in `ps` | it was **suspended** with Ctrl-Z, which pauses a program rather than ending it. A paused process ignores Ctrl-C and `kill` until it is resumed: run `fg` in its terminal then press Ctrl-C, or `sudo kill -CONT <pid>`. The port message and `--check` point this out |
| "Cannot start: port 8080 … already in use" | usually an older dashboard is still open (run with `sudo`, and the message names its pid and start time). Stop it with Ctrl-C in its terminal or `sudo kill <pid>`, or use `--port 8081`. Leftover `sudo` wrappers from an earlier session can also hold the port |
| an engine is greyed out in the UI | its binary is missing: run `./build_workers.sh` (needs `go` / `cargo`) |
| charts are empty, tables fine | `server/static/vendor/chart.umd.min.js` is missing or was not served; Chart.js is kept on this machine (see `server/static/vendor/README.md`) |
| 403 "forbidden" from the dashboard | the `Host`/`Origin` check: use `http://127.0.0.1:<port>`; for another address add `--allowed-host` |
| lots of loss in a burst | the burst overloads the target or the path, or the receive queue is too small; use a stagger window, and check the "receive queue" note |
| hardware timestamps say "software only" | normal on virtual interfaces, without root, or on NICs without support; lag results are unaffected |
| huge error % on loopback | expected: the true RTT is a few microseconds, so any lag is a large percentage |
| canary maximum is a big number | it is real stall time while probing; the ORM spins of N endpoints, serialised on one thread, add up (15 × 3 ms = 45 ms) |
| Go single-core canary max is far larger than the others | Go scheduler behaviour, see [04 Engines](04-engines.md) |
| a run stays "starting" and no new run or batch can start | **known bug:** if starting the probe raises a network error (for example "Network is unreachable" because the link is down), the error escapes and leaves a phantom "starting" run. Restart the dashboard, then delete any incomplete run. Check the link with `ip link` and `journalctl -k` before resuming |
| a batch run lost packets around a link drop | check `journalctl --since … | grep -i 'link is'` for the run's time window; delete runs that overlap a link event and record them again |
| a batch meant as floors came out as tests | `POST /api/batch` sets every run to role `test` unless `with_floor` is on. Record floors with *Measure idle floor*, with *idle floor every round*, or with single `/api/run` calls that set `role: "floor"` |
| "is the lab closed properly?" | read the **shutdown report** in the terminal after Ctrl-C; at any time, run `sudo .venv/bin/python -m server.app --check` |
| red banner "Left over from an earlier session" | a probe or worker process is still running, or NIC stamping was left on (usually after a `kill -9` or a power cut); the banner shows the command that fixes it |
| memory grows during a long session | saved runs are released beyond `OBSERVER_ROW_BUDGET` (the header shows packets in memory); unsaved runs are kept until saved, so save batches as you go |
| "Cycle length must be at least … s" | with several cycles, one cycle's pings ((pings − 1) × interval + timeout) must fit in the cycle length |
| host warnings (governor, C-states, SMT, NIC IRQ, load) | not errors, but conditions that move the numbers. For a measurement session: use the `performance` governor, limit deep C-states, close other applications and keep the NIC interrupt off the probe core. Compare runs taken under the same conditions. The NIC warning is based on the *allowed* CPUs; `/proc/interrupts` shows where the interrupt really runs |
| `verify_analysis.py` fails after new runs were saved | it expects the run counts of the report's corpora (90 + 2 + 81). New runs belong in a new section of [10](10-results-analysis.md); extend `split_corpora` and the checks before updating the report |
