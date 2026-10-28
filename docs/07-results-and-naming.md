# 07 Results and naming

This page explains where results are stored, how result files are named, and what every column means. Terms are defined in the [glossary](../README.md#glossary).

## Where results go

Everything saved lives in `test_results/` (or `$OBSERVER_RESULTS_DIR`). The terminal runner and the dashboard write the same set of files for a run, named by the convention below. The dashboard saves automatically when a run finishes, or on **Save** / **Save all unsaved** under `--no-autosave`.

| File | Content |
|---|---|
| `<name>.csv` | one row per packet |
| `<name>_cycles.csv` | one row per endpoint cycle: per-cycle statistics |
| `<name>.meta.json` | the full run configuration (including the note); counters (reader wakeups, late replies, canary summary, stream cost); the **host conditions** at the start of the run; and, for dashboard-saved runs, the canary heartbeat series. Written by the terminal runner too |
| `INDEX.md` | one appended entry per run: date, description (the note), command or settings, and a summary including loss by cause and send lag |

**Deleting runs.** In the dashboard (Manage results → Delete ticked…), a saved run is never erased.
- **Where it goes:** its three files and its `INDEX.md` entry are moved to `test_results/.deleted/<date-time>/`, which has its own `INDEX.md` holding the removed entries.
- **To restore:** move the files back and paste the entry into `test_results/INDEX.md`.
- **To make the deletion permanent:** delete the `.deleted` folder.
- **Effect on the dashboard:** runs in `.deleted/` are not loaded.

**Notes: what each run was checking.** Give every run a one-sentence note: the form's "What is this run checking?", or `--note` on the command line.
- **Where it shows:** the run table, the comparison header and every export.
- **Changing it later:** it can be changed after the run, saved or not (drill-down → Save note). For a saved run, the change is written to its `.meta.json` and to the Description line of its `INDEX.md` entry.
- **Keep it short:** the run table's column is narrow, so a note of about 25–40 characters stays readable, e.g. "Burst sem 5 · Rust single-core".

**Loading.** At start-up the dashboard loads every per-packet CSV in the folder, so saved runs can be compared in later sessions. Runs with no `.meta.json` get their settings from the readable part of their file name.

## Naming convention

`<WHEN>_<RUNTIME>_<LOAD>_<TARGET>[_<tag>]`

```
20261021-224241_go-mc_100ep-burst-sem15-db3_172-40-0-253
20261022-090500_py-sc_50ep-stg30-sem5-db0p5-p3-i0p2_10-0-0-1+1_sem-sweep
20261022-101500_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_172-40-0-253          <- the Ephemres defaults
```

**Which values are left out of a name.**
- **Values left out:** 5 pings, a 1 s interval and one cycle.
- **Why those values:** they are fixed parts of the naming convention, so that every existing file name keeps its meaning. They are not the dashboard's defaults.
- **Consequence:** a run with the Ephemres defaults carries `-i8-c3x60`.

| Group | Format | Meaning |
|---|---|---|
| WHEN | `YYYYMMDD-HHMMSS` | start time; sorts chronologically |
| RUNTIME | `<py\|go\|rs>-<sc\|mc>` | engine, and single-core (pinned) or multi-core |
| LOAD | `<N>ep-<burst\|stg<S>>-sem<S>-db<ms>` | endpoints, schedule, semaphore size, simulated ORM milliseconds; `-p<pings>` and `-i<interval>` are added **only** when they differ from 5 pings and 1 s, and `-c<cycles>x<cycle seconds>` **only** when there is more than one cycle |
| TARGET | first target, with dashes for dots | `+K` means K more targets |
| tag | optional | your label for a series, for example `sem-sweep` |

Decimal points are written `p` (0.5 → `0p5`), so they never look like a file extension.

**Why it is arranged this way.**
- **The scenario key.** LOAD + TARGET is identical for every run that asked the same question of a different engine. That text is the **scenario key**, and the dashboard uses it to group runs that can be compared like for like.
- **The order.** WHEN comes first, so a directory listing is a timeline. RUNTIME comes second, because the engine and core mode are what you usually compare.
- **Which source wins.** Everything is in the name, but the authoritative values are in `.meta.json`.

**Code and tests.**
- Runs saved before the other engines existed (the first two in `test_results/`) are all Python single-core (`py-sc`), and were renamed to this scheme.
- `server/naming.py` contains the name generator, the parser and the scenario key. The unit tests check that every saved file name regenerates itself.

**Tags used in `test_results/`.**

| Tag | Runs |
|---|---|
| `floor` | idle floors (no ORM work), including floors recorded inside batches |
| `sem-sweep` | staggered, semaphore 5 / 30 / 50 (2026-10-24) |
| `ep-sweep` | staggered, 25 / 100 / 250 endpoints |
| `burst` | burst, semaphore 15, first session (2026-10-25 morning) |
| `burst-sem` | burst, single-core, semaphore 5 / 15 / 50 (follow-up session) |
| `burst-mc` | burst, multi-core, semaphore 15 (follow-up session) |
| `same-day` | staggered 100-endpoint tests recorded with their floors (follow-up session) |

## CSV column dictionary

### `<name>.csv` (per packet)

| Column | Unit | Meaning |
|---|---|---|
| `endpoint` | index | virtual endpoint number |
| `cycle` | index | cycle number (0 unless there are several cycles) |
| `icmp_id`, `icmp_seq` | | the identifier and sequence number on the wire (use them to match a row in tcpdump or Wireshark) |
| `target_ip` | | destination |
| `lost` | 0/1 | 1 if no reply arrived in time |
| `tx_realtime_ns` | ns | `CLOCK_REALTIME` just before `sendto` |
| `kernel_rx_ns` | ns | Clock A: the kernel's arrival time |
| `user_rx_ns` | ns | Clock B: the program's read time |
| `hw_rx_ns` | ns | NIC hardware stamp (its own clock; Python on supporting NICs only) |
| `kernel_rtt_us` | µs | `kernel_rx_ns − tx_realtime_ns` |
| `user_rtt_us` | µs | `user_rx_ns − tx_realtime_ns` (observer RTT) |
| `observer_lag_us` | µs | `user_rx_ns − kernel_rx_ns` |
| `reader_batch` | packets | replies read in the same reader wakeup (queue depth) |
| `wakeup_id` | | which reader wakeup delivered it |
| `send_lag_us` | µs | how late the ping was sent compared with its schedule |
| `late_kernel_rx_ns`, `late_user_rx_ns` | ns | for a lost ping: the late reply's Clock A and Clock B, if one arrived after the timeout |
| `engine`, `cpu_mode` | | which runtime and mode produced the row |

**Notes on the columns.**
- Terminal and dashboard runs write the same columns.
- Files saved before 2026-10-22 lack the newer columns: `send_lag_us` and the late-reply columns, and in terminal files also `reader_batch` … `cpu_mode`. They load with those fields empty.
- In runs with several cycles, cycle 0 is in the files but left out of every statistic (warm-up).
- The last ping of a cycle (ping 5 by default, `icmp_seq % pings == pings − 1`) is the one whose reply releases the endpoint into its ORM write. In burst runs it is often the slowest; see [10](10-results-analysis.md) Table 2.4.

### `<name>_cycles.csv` (per endpoint cycle)

**Columns in both runners' files:** `endpoint, cycle, target_ip, icmp_id`, then for each of `kernel`, `user` and `lag` the six statistics `min_us, max_us, avg_us, p95_us, std_us, jitter_us`.

**Extra columns in the terminal runner's file:**
- `db_wait_ms`: time spent waiting for the semaphore;
- `db_start_ns, db_end_ns`: when the ORM work ran;
- the canary columns `canary_avg_us, canary_p95_us, canary_max_us`.

**ORM windows.** Both runners also keep the ORM-work windows in `.meta.json` → `bursts` (`[endpoint, cycle, start_ns, end_ns]`). The burst shading reads them from there.

**Batch runs.** Runs from a **batch** carry `series_id`, `repeat` and `repeats` in their configuration, so repeats can be grouped again after a restart. Unless you set a tag, their tag is the series id.

### Endpoint CSV (dashboard export)

`endpoint, target_ip, sent, replied, kernel_rtt_mean_us, python_rtt_mean_us, intrusion_mean_us, intrusion_max_us, error_pct_total, reader_wakeups, max_queue_depth`

- `error_pct_total` is the endpoint's total lag ÷ total kernel RTT. Before 2026-10-22 it was called `error_pct_mean`, with the same values.
- `python_rtt_mean_us` is the observer RTT, whichever engine produced it.

### Comparison CSV / Markdown

One row per metric, one column per run. The Markdown version also shows each value as a multiple of the first run, and a warning line listing the settings that differ between the runs.

## Recorded corpora and analysis

All 173 benchmark runs in `test_results/` are indexed in `test_results/INDEX.md` and analysed in full in [10 Empirical Results and Comparative Analysis](10-results-analysis.md):
- **First corpus (90 runs, 2026-10-24 to 2026-10-25 daytime):** staggered and burst idle floors (`floor`), semaphore sweeps at 5, 30 and 50 (`sem-sweep`), endpoint scaling at 25, 100 and 250 endpoints (`ep-sweep`), and single-core burst runs (`burst`) ([10](10-results-analysis.md) §R1–§R2).
- **Follow-up session (81 runs, 2026-10-25 evening):** single-core burst semaphore sweeps (`burst-sem`), multi-core burst runs (`burst-mc`), and staggered runs at 25, 100 and 250 endpoints (`ep-sweep`, `same-day`) paired with interleaved idle floors (`floor`) ([10](10-results-analysis.md) §R3).
- **Runtime scheduler observations** (Go single-thread timer starvation, tokio 1 ms timer resolution, Rust burst stall bounds, and Python process-pool offload overhead) are documented in [04 Engines](04-engines.md) and [10 Results analysis](10-results-analysis.md#architectural-anomalies--host-effects).
