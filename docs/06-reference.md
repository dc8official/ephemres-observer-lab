# 06 Reference

A lookup page: what the lab needs, and every command-line flag, environment variable and fixed limit. For what the settings *mean*, see [02 Test methodology](02-test-methodology.md); for a step-by-step protocol, see [09 Replication guide](09-replication.md).

## Requirements

| Item | Needed for | Notes |
|---|---|---|
| Linux, x86-64 | everything | the timestamping interface and the memory layouts it uses are specific to Linux on x86-64 |
| root, or `cap_net_raw` | the raw ICMP socket | the dashboard runs as root; the compiled workers can use `setcap` instead |
| Python 3.10+ | engine and dashboard | developed on 3.14; the engine itself needs only the standard library |
| `fastapi`, `uvicorn[standard]` | dashboard only | listed in `requirements.txt` and installed into `.venv` |
| Go 1.22+ | Go engine | standard library only |
| Rust stable (edition 2021) | Rust engine | crates: tokio, libc, serde_json |
| `taskset` (util-linux) | multi-core launches, Go single-core pinning | normally installed |
| `node` (optional) | one unit test | checks that [09](09-replication.md) §7 matches the dashboard; the test is skipped without it |

## `probe_lab.py` (Python engine and terminal runner)

`sudo python3 probe_lab.py --targets IP[,IP…] [options]`

| Flag | Default | Meaning |
|---|---|---|
| `--targets` | required | comma-separated IPv4 addresses (ranges such as `10.0.0.1-10.0.0.20` are also accepted) |
| `--virtual-endpoints N` | one per target | number of endpoints, spread round-robin over the targets (max 65536 − 0x1000 − warm-up ids) |
| `--pings` | 5 | pings per cycle |
| `--interval` | 1.0 | seconds between one endpoint's pings |
| `--timeout` | 2.0 | seconds to wait for a reply before counting it lost |
| `--stagger-window S` | none | spread endpoint starts over exactly S seconds; 0 = burst |
| `--burst` | off | all endpoints start together |
| `--cycle-length S` | 60 | start-to-start time of an endpoint's cycles. Without `--stagger-window` it also sets the stagger (window = S − (pings − 1) × interval − timeout, an older convention) |
| `--cycles` | 1 | cycles per endpoint; with more than one, cycle 0 is a warm-up left out of the summary. `cycles × pings` ≤ 65536 |
| `--semaphore` | 15 | `db_write_semaphore` size |
| `--simulated-db-ms` | 3.0 | CPU spin per endpoint cycle |
| `--simulated-db-io-ms` | 1.0 | asynchronous sleep inside the semaphore |
| `--cpu-mode` | `single_core` | `single_core` = ORM inline on the loop; `multi_core` = process-pool offload |
| `--cpu N` | last allowed core | core to pin the event loop to; `-1` = do not pin |
| `--hw` | off | also record NIC hardware receive stamps (changes the NIC setting for the run; leave off when comparing with Go/Rust) |
| `--no-hw` | (default) | no hardware stamps; kept so older commands still work |
| `--no-warmup` | off | skip the unrecorded warm-up ping |
| `--quiet` | off | only the final summary, no per-cycle rows |
| `--csv PATH` | `test_results/<generated name>.csv` | per-packet CSV (a `_cycles.csv` is written beside it) |
| `--tag`, `--note` | empty | series label for the file name / description stored in `INDEX.md` |
| `--jsonl` | off | emit the NDJSON event stream on stdout instead of the console table (used by the dashboard; no CSV) |

**Ending a run.** Ctrl-C and `kill` (SIGTERM) both end a run cleanly:
- files are closed, and any NIC setting that was changed is restored;
- the cycles that finished are summarised, written to `<name>.meta.json`, and logged in `INDEX.md` as stopped early.

**What a terminal run writes.** The same files as a dashboard save:
- `<name>.csv`, with the same columns;
- `<name>_cycles.csv`;
- `<name>.meta.json`: configuration, counters and host conditions.

It also prints the host-condition warnings at the start. Late-reply columns in the terminal CSV are filled only when the late reply arrived before its cycle was written.

**The terminal defaults are not the Ephemres defaults.** The terminal runner's flag defaults (1 s interval, one cycle) are for quick checks and differ from the dashboard's Ephemres defaults.
- A run made with them is a different scenario, so it is not grouped with dashboard runs.
- To compare with dashboard runs, pass the Ephemres values, as in the second example below.

Example runs:
```bash
sudo python3 probe_lab.py --targets 127.0.0.1 --virtual-endpoints 30 --burst              # functional check
sudo python3 probe_lab.py --targets 10.0.0.5 --virtual-endpoints 100 --interval 8 --stagger-window 60 --cycles 3 --cycle-length 60   # Ephemres configuration (same scenario as the dashboard defaults)
sudo python3 probe_lab.py --targets 10.0.0.5 --virtual-endpoints 100 --burst --cpu-mode multi_core --tag orm-offload
```

## Compiled workers

`bin/go_prober` and `bin/rust_prober` accept the same flags and always emit NDJSON:

`--targets --virtual-endpoints --pings --interval --timeout --stagger-window --cycles --cycle-length --semaphore
--simulated-db-ms --simulated-db-io-ms --id-base --cpu-mode {single_core|multi_core} --cpu N --no-warmup --jsonl`

Differences from the Python command line:
- `--cpu-mode` selects the runtime's shape (a single thread, or all threads);
- `--cpu N` pins the worker in single-core mode;
- there is no CSV file or console table (the dashboard saves results);
- targets must be comma-separated (no ranges);
- there are no hardware timestamps.

The identifier space (`--id-base` + endpoints + warm-up ids) must fit in 16 bits; the worker refuses to start otherwise.

## `server.app` (dashboard)

`sudo .venv/bin/python -m server.app [--host H] [--port P] [--allowed-host NAME …] [--no-autosave] [--check]`

| Flag | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | bind address; anything else prints a no-authentication warning |
| `--port` | 8080 | port |
| `--no-autosave` | off | do not save finished runs automatically; save them with Save / Save all unsaved (unsaved runs are lost when the dashboard closes) |
| `--check` | off | do not start the dashboard; only report anything of the lab left running (probe or worker processes, NIC timestamping left on). The exit code is 1 if something is. Use `sudo`, or root's processes are invisible |
| `--allowed-host NAME` | none | an extra `Host` header value to accept (repeatable), for example this machine's IP when binding to `0.0.0.0` |

## `build_workers.sh`

`./build_workers.sh [--no-setcap]` builds `bin/go_prober` and `bin/rust_prober` (see [04 Engines](04-engines.md)). Run it as your normal user; only the `setcap` step asks for sudo.

## `verify_analysis.py`

`python3 verify_analysis.py [--print-tables]` checks every figure quoted in [10 Results analysis](10-results-analysis.md) against the saved runs and exits 1 on any mismatch. `--print-tables` prints the rows of Tables 3.1–3.5 as they should appear in the report. No root is needed.

## Environment variables

| Variable | Used by | Meaning |
|---|---|---|
| `OBSERVER_ROW_BUDGET` | dashboard | packet rows of saved runs kept in memory (default 200000, about 200 MB); beyond it the least recently used saved runs are released and reloaded from disk when needed |
| `OBSERVER_RESULTS_DIR` | dashboard | a folder to load and save results in instead of `test_results/` (useful for experiments and tests) |
| `GO_PROBER_PINNED` | Go worker | an internal marker set when the worker has re-launched itself under `taskset`; do not set it by hand |

## Limits and defaults worth remembering

| Item | Value |
|---|---|
| ICMP identifiers | `0x1000 + endpoint index`; warm-up pings use the identifiers after the last endpoint |
| ICMP payload | 56 bytes |
| Reply timeout | 2 s (dashboard: 0.1–10 s) |
| Dashboard defaults | Ephemres: 100 endpoints, 5 pings 8 s apart, stagger 60 s, 3 cycles × 60 s, semaphore 15, 3 ms ORM |
| Receive queue | 8 MiB requested (force-set when root); the run note shows the size granted |
| Canary tick | 10 ms; window kept: 120 000 ticks (20 minutes) |
| Live update period | 0.5 s |
| Max comparison columns | 8 (with combine repeats, a column holds all repeats of one engine) |
