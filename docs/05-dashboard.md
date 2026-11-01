# 05 Dashboard

The dashboard is a local web page for running tests, watching them live, and comparing their results.

## Starting it

Start it with `sudo .venv/bin/python -m server.app` and open <http://127.0.0.1:8080>.
- **Why root:** the probe opens a raw ICMP socket.
- **One file, no internet needed:** the page is a single file (`server/static/index.html`). Its charts use Chart.js 4.4.1, which is stored in the project (`server/static/vendor/`) and served by the dashboard itself.

Every control is described in one table: what it does, its default, its range, its Ephemres value, and whether it must match between runs you compare. That table appears in three places, all generated from one list in the page:
- [09 Replication guide](09-replication.md) §7;
- the *Research & Methodology* tab ("Controls reference");
- a tooltip on each control.

Terms are defined in the [glossary](../README.md#glossary).

## Basic ideas

**Language engine vs batch engines.**
- **Language engine** is the engine of a single run.
- **Batch engines** are the engines a batch runs in every round. The language engine is always one of them (its box is shown ticked and locked); tick the others to compare engines in one batch.

**Header status.** Next to the clock information, the header shows what the dashboard holds:
- its memory, the number of runs and the packets in memory;
- whether **auto-save** is on. This is the default: every finished run is saved to `test_results/` by itself; `--no-autosave` turns it off.
- the number of **unsaved** runs, in red. These are lost when the dashboard closes; **Save all unsaved** (section 2) saves them in one go.

A red banner appears when the start-up check found something left over from an earlier session (see [03 Architecture](03-architecture.md), "Process lifetime, shutdown and memory").

**Finding your way.** Both tabs are long, so each has a list of jump links.
- **Lab tab:** the **section bar** under the header (1 · Run, 2 · Runs, 3 · Comparison, Charts, 4 · Drill-down) jumps to each part and highlights the part you are in.
- **Research tab:** its **contents list** does the same. On wide screens it sits beside the text and stays in view while you scroll.
- **Folding panels:** every Lab panel can be folded with the **▾ / ▸** button in its heading, for example to fold the run form once a batch is running. The page remembers what you folded, and a jump link to a folded panel opens it.
- **On a phone:** the header scrolls away with the page instead of staying pinned, so it does not take up a third of the screen.

## Two tabs

* **Lab:** running, comparing and drilling into tests (described below).
* **Research & Methodology:** documentation built into the page (link: `#research`), in reading order:
  - the research question, the clocks diagram, the internal vs external observer effect, and why database work is simulated as CPU work;
  - the experiment matrix: engines × CPU modes, including how Python multi-core is measured;
  - **reading the comparison table:** what a column is, what each row group answers, when ▼/▲ appear, and the flags that limit trust;
  - **reading the charts:** a reading order; every chart's marks, reading and pitfalls; which evidence answers each research question;
  - a checklist for a valid test, with a table of the main threats, and **replicating the experiment**;
  - the academic references;
  - two reference tables, folded until opened (a contents link opens them): the **controls reference** (every option) and the glossary of every metric.

  The glossary text is the same text shown as hover tooltips on the sliders and on the comparison-table rows, so the two cannot drift apart.

## The Lab tab, top to bottom

### 1 · Run a test

**Fields.**
- **Where and with what:** targets (comma-separated IPv4 addresses); **Language engine** (Python / Go / Rust; an engine that is not built is greyed out); **CPU core mode** (Single-Core pinned / Multi-Core).
- **Load:** virtual endpoints (1 to 500), stagger window (0 = burst), `db_write_semaphore` (1 to 100), simulated DB work (0 to 15 ms).
- **Pings:** pings per cycle, ping interval (up to 30 s), reply timeout, cycles per endpoint, cycle length.
- **NIC hardware timestamps:** Python only, and off by default because it breaks engine parity.
- **Labels:** an optional **series tag**, which goes into the file name, and **what the run is checking** (the note).

**The form starts at Ephemres' own configuration:** 100 endpoints, 5 pings 8 s apart, 2 s timeout, starts spread over 60 s, 3 cycles of 60 s, semaphore 15, 3 ms ORM.
- A line under the form says how long the run will take, that cycle 0 is a warm-up, and **which settings differ from Ephemres**.
- The note's placeholder suggests that difference as the question the run answers.

**Buttons.**
- **Ephemres defaults** resets every field.
- **Burst (0 s)** sets the stagger to 0.
- **Measure idle floor** starts the current setup with the ORM work set to 0 ms (role `floor`, tag `floor`). This measures the engine's idle floor for that setup.

**Batches.** **Repeat (rounds)**, **engines to alternate** and **idle floor every round** turn Start into **Start batch (N runs)**.
- **What it runs:** the dashboard runs every round itself, rotating the engine order each round. With the floor option ticked, each engine's floor run comes just before its test run.
- **Before it starts:** the line under the form gives the number of runs and the total time.
- **While it runs:** progress ("Batch …: 4 of 18 runs finished") shows next to the progress bar, and each new run of the batch is added to the selection.
- **Stopping:** Stop cancels the rest of the batch.

**Checks.**
- Values are checked before anything is sent: ranges, a cycle long enough for its pings, and hardware stamps only with Python. Any rejection is shown as a readable sentence.
- A started run is selected automatically, so you can watch it live.

### 2 · Choose runs to compare

**The run list.**
- **What is listed:** every run in memory and in `test_results/`, newest first, with its note in the **what it checks** column.
- **Grouped by scenario:** runs in a group asked the same question, so they compare like for like.

**Selecting runs.**
- **How many:** tick runs to compare, up to 8 columns. With **combine repeats**, the repeats of one engine share a column, so a whole batch fits.
- **The baseline:** the ● column picks it. By default it is the first test run, never an idle-floor run.
- **Colours and markers:** each selected run gets a fixed colour **and marker shape** (● ▲ ■ ◆ …) used in every chart. The palette is checked for colour-blind separation in both themes.
- **Shortcuts:** "Select all N" ticks a whole scenario group, and a text filter narrows the list.

**Folding groups.** Scenario groups fold with ▾ / ▸. By default a group is open when it is the only one, has 3 runs or fewer, or holds a selected or running run. The page remembers any group you open or close yourself.

**Managing results.** Tick **Manage results (save / delete)** to get a separate tick column with no 8-column limit, and these buttons:
- **Tick all shown** follows the Filter, so you can tick, for example, every run with one tag.
- **Untick all** and **Save ticked**.
- **Delete ticked…** first shows a confirmation listing the runs. What happens next depends on the run:
  - **A saved run** is **moved**, not erased: its three files and its `INDEX.md` entry go to `test_results/.deleted/<date-time>/`, and that folder gets its own `INDEX.md` with the removed entries. To undo, move the files back and paste the entry. To make it permanent, delete the `.deleted` folder.
  - **An unsaved run** is discarded from memory.
  - **A run still in progress** cannot be deleted.

**The "not like-for-like" banner.** A yellow banner appears when the selected runs differ in endpoints, schedule, semaphore, ORM time, pings, interval, cycles, cycle length, timeout, NIC hardware stamps or target. Differences in the results may then come from the settings, not from the engine.

### 3 · Comparison

**Columns and rows.**
- **Columns:** one per selected run. With **combine repeats**, one per group of repeats; its header shows the note and "N repeats", and each cell shows the median with the lowest to highest repeat underneath.
- **Rows:** one per metric, grouped as volume and **loss by cause**, wire, observer, intrusion percentiles, error %, **send lag**, socket queue and runtime.
- **Multiples:** each non-baseline cell can also show its value as a multiple of the baseline (toggle).

**Best and worst marks.** For rows where lower is better, **▼ marks the best and ▲ the worst** value. They are also green and red, but colour is never used alone. They appear only when:
- best and worst differ by at least the chosen threshold (10 % by default; 5 to 50 % or never), because smaller gaps between single runs are usually noise;
- with repeats, the best column's highest repeat is below the worst column's lowest.

Idle-floor columns and the above-floor rows never get ▼/▲.

**Flags.**
- **Error % on a fast link:** for a run whose median kernel RTT is under 100 µs, it shows as "n/m (RTT too small)".
- **Too few packets:** a percentile the run has too few packets for is flagged **few samples**. p95 needs about 200 packets, p99 about 1000.

**Reading aids.**
- A thin bar under each value shows it relative to the row maximum.
- Error % rows lead with the primary definition (total lag ÷ total kernel RTT), then the per-packet median, mean and max.

**Idle floor.** **Subtract idle floor** adds rows showing each run's intrusion minus that of its matching floor run (see [02 Test methodology](02-test-methodology.md)). Floor runs carry an "idle floor" badge in the run table.

**Export.** The table exports as Markdown or CSV for any number of runs; both include each run's note.

**Layout.**
- **Shared settings are stated once.** What every column has in common, such as "20ep stagger 60s · 3×60s · every 8s · s15 d3" and the note, is shown in **a caption** above the table. Each column header then shows only what differs: engine, core mode, floor.
- **All-zero rows are collapsed.** Rows that are zero in every column (typically the loss rows of a clean run) are collected into one line, "Zero in every column (not drawn)", instead of a block of zeros.
- **Headers stay in view.** The table scrolls inside its own frame with the column headers pinned, so the engine names stay visible down to the last row.

### Charts (one series per comparison column)

**Series.** Every chart draws one series per column of the comparison table, in that column's colour and marker. With **combine repeats**:
- a column's series is the **median of its repeats** (the legend says "median of N");
- the percentile, kernel-RTT, ranking and canary charts show the lowest to highest repeat as a **shaded band** behind the median;
- the bar chart and the histogram show only the median;
- hovering shows the median line's values, not the band edges.

**Labels and axes.**
- The legend line above the charts states the setup every column shares.
- Charts carry a text description for screen readers.
- Log axes fit the data and label 1, 2 and 5 of each decade with units (µs or ms).

| Chart | What it shows | How to read it |
|---|---|---|
| Key metrics by run | a chosen metric set (intrusion, RTT, jitter, send lag, canary); bars on a linear axis, dots on the log axis (bar lengths on a log axis are not proportional); a percentile the run has too few packets for is left out, as in the table | a quick headline comparison |
| Intrusion at each percentile | observer lag at min, p10 … p99.9, max (log y); the x axis is tail-log, so p90, p99 and p99.9 are equally spaced; percentiles the run has too few packets for are left out, and the max sits at log₁₀ n | a low, flat curve = replies rarely wait; the right end is the worst case |
| Kernel RTT at each percentile | the same curve for the kernel's arrival clock (Clock A), on the same x range as the intrusion curve | rising with load = the probes slowed the target or wire (external effect); flat while intrusion rises = the delay is inside the monitor (internal effect) |
| Where the intrusion falls | share of replied packets per lag bucket | percentages, so runs with different loss are comparable |
| Intrusion over time | one dot per packet: time since the first ping vs lag, with the ORM-work windows shaded behind; shows **the drill-down run only** (named above the chart) unless **all selected runs** is ticked, since thousands of dots from several runs hide each other | stacked dots inside a shaded band = packets that waited behind that ORM work |
| Spread across repeats | one dot per repeat and a dash at the median (only with 2+ repeats), per column, labelled with its marker, engine and setup, for a chosen figure (intrusion mean/p95/p99/max, error %, above-floor p95, send lag, canary) | dots of two columns that overlap = no real difference |
| How concentrated is the damage | endpoints ranked by mean lag, worst to best; x is the rank as a % of the run's endpoints, so runs with different endpoint counts line up | steep drop = a few unlucky endpoints; flat = everyone suffers equally |
| Scheduler canary | the worst timer lateness in each 0.5 s window; a note names runs with no recorded timeline (e.g. imported terminal runs) | the runtime's own view of how long it kept other work waiting |
| Sweep | a chosen figure (as in the spread chart) against one setting (endpoints, stagger, semaphore, ORM ms, pings, interval, cycle length; by default the one that differs), one dot per selected test run and a line through the median per engine; a note names any other setting that also differs. Drawn only when the selected runs have at least two values of the setting (otherwise a note says so) | the dose-response view: how the effect grows with the load setting |

### 4 · Drill into one run

Pick any selected run to see the following:
* **Note.** An editable **what this run checks** note, saved with **Save note** or Enter. For a saved run, this also updates its `.meta.json` and `INDEX.md` entry.
* **Summary cards.** Twelve of them, including:
  - **error %**, with the primary definition first;
  - **intrusion above the idle floor** and **loss by cause**;
  - **send lag** and the dashboard stream cost.
* **Warm-up note.** A note says when cycle 0 was excluded as warm-up.
* **Host conditions.** The **host conditions** recorded with the run, and what in them can move the numbers.
* **Per-endpoint chart.** It shows kernel RTT plus intrusion, which equals observer RTT, or intrusion only.
* **Worst-10 endpoint table.** Its % Error is the endpoint's mean intrusion divided by its mean kernel RTT, a ratio of means (see [02 Test methodology](02-test-methodology.md)).
* **Save and exports:** packets CSV, endpoints CSV, and a Markdown report. Save never changes the run's note.
* **Run details.** A saved run keeps its clock information and route. A run loaded from `test_results/` shows the start time from its file name.

### Theme

The header's theme selector offers auto (follows the operating system), dark and light.
- **Contrast:** every text colour meets WCAG AA contrast (4.5:1) in both themes.
- **Run colours:** validated for colour-blind separation in each theme.
- **Small screens:** the layout fits a phone-width window; wide tables scroll inside their panel.

### Keyboard and screen readers

- **Keyboard:** every control can be reached with Tab and shows a clear focus ring.
- **Hit targets:** the run-table tick boxes and radio buttons are 20 px, and small buttons are at least 26 px high, so they are easy to hit.
- **Labels:** unlabelled inputs (row tick boxes, the baseline radio, the filter) carry a text label for screen readers.
- **Charts:** each chart has a text description of what it shows.

## HTTP API

The page talks to the server through these endpoints. Scripts can use them too.

| Method and path | Purpose |
|---|---|
| `GET /` | the page |
| `GET /api/state` | server state: running flag, root flag, current run, all runs, available engines |
| `POST /api/run` | start a run (JSON body below); 409 if one is running, 422 for bad settings or an unbuilt engine, 500 if the probe process cannot be launched (the run is marked `error`) |
| `POST /api/batch` | start a batch: `{"run": {…run configuration…}, "repeats": 3, "engines": ["python","go","rust"], "with_floor": true}`; returns the series id and the number of runs. Without `with_floor`, every run of the batch is a test run, whatever `run.role` says |
| `POST /api/stop` | interrupt the running probe (partial data is kept, status `stopped`) and cancel the rest of a batch |
| `GET /api/runs/{id}/analysis` | analysis for one run: summary, endpoints, worst-10, histogram, percentile curve, scatter, canary timeline, metadata |
| `POST /api/runs/{id}/save` | write the run to the results folder (`test_results/` or `$OBSERVER_RESULTS_DIR`; the response names the real folder) |
| `POST /api/runs/save-selected` | save the given runs `{"ids": [...]}` (already-saved ones are skipped) |
| `POST /api/runs/delete` | delete the given runs `{"ids": [...]}`: saved runs are moved to `.deleted/<date-time>/` in the results folder, unsaved runs are discarded; 409 if one is still running |
| `POST /api/save-all` | save every finished run that is not saved yet |
| `POST /api/runs/{id}/note` | set what the run checks (body `{"note": "..."}`); also updates a saved run's `.meta.json` and `INDEX.md` |
| `GET /api/runs/{id}/export/{kind}` | `packets.csv`, `endpoints.csv` or `report.md` for one run |
| `GET /api/compare.md?ids=a,b,c[&combine=true]` | a Markdown comparison of any number of runs; `combine=true` merges repeats into median (min to max) columns |
| `GET /api/compare.csv?ids=a,b,c` | the same comparison as CSV |
| `WS /ws` | the push channel (below) |

Run ids are `run1`, `run2`, … for runs made in this session, and `disk-<file name>` for saved runs.

**Run configuration (`POST /api/run`)**
```json
{"targets":"10.0.0.5","virtual_endpoints":100,"pings_per_cycle":5,"interval_s":8.0,"timeout_s":2.0,
 "stagger_window_s":60,"cycles":3,"cycle_length_s":60,"db_write_semaphore":15,"simulated_db_ms":3.0,
 "hw_timestamps":false,"role":"test","engine":"go","cpu_mode":"multi_core","tag":"sem-sweep","note":"does Go stay flat at semaphore 50?"}
```
Every field is optional except `targets`. Omitted fields take the Ephemres defaults, which `/api/state` also returns as `defaults`.

**Limits:**
- endpoints 1 to 500, pings 1 to 20, interval 0.05 to 30 s, timeout 0.1 to 10 s, stagger 0 to 600 s;
- cycles 1 to 60; cycle length 1 to 600 s, and at least (pings − 1) × interval + timeout when cycles > 1;
- semaphore 1 to 100, ORM 0 to 15 ms;
- `hw_timestamps` only with `engine: "python"`;
- `role` is `test` or `floor` (a floor run forces 0 ms ORM);
- tag ≤ 24 characters, note ≤ 300, 1 to 32 targets.

## WebSocket messages (server → browser)

| `type` | Content |
|---|---|
| `state` | the same payload as `/api/state`, sent on connect and whenever runs change |
| `live` | during a run, at most every 0.5 s: run summary, latest tick and the current analysis |
| `done` | when a run ends (`done`, `stopped` or `error`): final analysis and state |

The browser never sends data over the socket; commands use the HTTP API. A client that cannot accept a message within 2 s is dropped, so it cannot slow the server down.

## Security

There is no login. The dashboard protects itself in these ways:
- **Local only by default:** the server listens on 127.0.0.1.
- **Same-origin only:** it rejects requests whose `Host` or `Origin` header shows they come from another web page or a DNS-rebinding attack (see [03 Architecture](03-architecture.md)).
- **Other addresses are opt-in:** to bind to another address, you must add it with `--allowed-host`. Anyone who can reach that port can then send ICMP from the machine, so do this only on a trusted network.
