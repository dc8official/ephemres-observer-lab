# 09 Replication guide: repeating the experiment, and every option explained

This page is for anyone who wants to repeat the engine comparison on their own machine and network, or check the results reported here. It covers:
- what you need, and how to prepare the host;
- the exact protocol;
- how to read and report the results;
- **every control of the dashboard**: what it does, its default, its allowed range, Ephemres' own value, and whether it may differ between runs you compare.

The same reference is on the dashboard's *Research & Methodology* tab and appears as tooltips on the controls. The table in §7 is generated from the dashboard's own list, and a unit test checks that every control on the page is documented here. Terms are defined in the [glossary](../README.md#glossary).

## 1. Language engine vs batch engines (the most common question)

| | Language engine | Batch engines (take turns each round) |
|---|---|---|
| Used by | a **single run** (Start run, Measure idle floor) | a **batch** (Start batch) |
| Choice | exactly one engine | the language engine (always included, shown ticked and locked) **plus** any others you tick |
| Effect | that engine probes the target | every round runs each chosen engine once; the order rotates each round (Py Go Rs → Go Rs Py → Rs Py Go) |

**To compare Python, Go and Rust under identical conditions:**
1. Pick any language engine.
2. Tick the other two batch engines.
3. Set Repeat to 5.
4. Press Start batch.

**To run one engine once:** leave the batch engines unticked and Repeat at 1.

## 1b. The six combinations: engines × CPU core modes

Each engine runs in two **CPU core modes**, and the full comparison covers all six combinations:

| Engine | Single-Core (1 CPU pinned) | Multi-Core |
|---|---|---|
| Python (asyncio) | one thread does everything; the ORM spin blocks reply reading | the event loop stays pinned to its core; the ORM work goes to a **pool of worker processes** (CPUs − 1) |
| Go (goroutines) | `GOMAXPROCS=1` | goroutines on every core |
| Rust (tokio) | current-thread runtime | multi-thread runtime, one worker per core |

**Python multi-core is monitored like every other mode, plus the offload instruments.** The usual measurements are all there: both clocks on every packet, the canary, send lag and loss by cause. On top of them:

* **Observer intrusion vs. event-loop starvation:** comparing `py-mc` against `py-sc` tests whether offloading the 3 ms CPU spin lowers both event-loop starvation (measured by the canary) and packet-reading intrusion (`Clock B − Clock A`), or whether baseline socket I/O and IPC serialisation keep packet intrusion bounded by the event loop itself ([10 Results analysis](10-results-analysis.md) §R1.3, §R3.3).
* **ORM offload overhead (IPC + pool wait)**, per cycle: the hand-over time beyond the work itself (`ipc_ms`). That covers pickling the data to a worker, waiting for a free worker, and getting the result back. It appears as a comparison row and a drill-down card, and as "n/a" in every other mode.
* **Offloading can still delay replies.** The pickling runs on helper threads *inside the probe process*, which take turns with the event loop for the GIL. Intrusion and the canary show how much.
* **ORM-work shading** marks the offloaded jobs. In this mode the high-lag stacks should *not* line up with the bands.

**Pool size versus semaphore.**
- **The mismatch:** the pool has CPUs − 1 workers (7 on an 8-CPU machine), but the Ephemres semaphore admits 15 jobs at once. Under a 60 s stagger, average concurrency is `0.0067 ≪ 1` so jobs rarely queue even at semaphore 50; under a burst schedule with semaphore 15, extra jobs wait for a free worker.
- **Extended experiment to isolate pure hand-over cost under burst:** run a Multi-Core burst variation with `db_write_semaphore` ≤ CPUs − 1 (e.g., 7 on an 8-CPU host) and compare its `ipc_ms` against semaphore 15.

## 2. What you need

* **Prober host:** Linux x86-64, root (for raw ICMP sockets), Python 3.10+.
  - Go 1.22+ and a Rust toolchain are needed only if you want those engines. `./build_workers.sh` builds them; a missing toolchain just greys that engine out.
* **Target:** a device on the same LAN segment that answers ICMP echo with 0 % loss: a PC, a router, a switch, a VM.
  - Nothing is installed or changed on it.
  - On Windows, allow inbound echo requests in the firewall.
* **A wired, stable link.** A link that drops during a run invalidates that run (see §4c).
* **Setup:**
  ```bash
  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
  ./build_workers.sh                                    # optional: Go and Rust engines
  .venv/bin/python -m unittest discover -s tests -t .   # sanity check (no root needed)
  ```

## 3. Prepare the prober host (untuned baseline vs. locked replication)

The lab measures tens to hundreds of microseconds, so the host's own power and scheduling state matters.
- **What we did in the 173 runs in `test_results/`:** all 173 runs were recorded with the host's default laptop power settings (`powersave` CPU governor, `C10` deep sleep enabled, Intel turbo active, and probe pinned to CPU 7), while the dashboard recorded those conditions and warnings into every `.meta.json` (`host` object). Leaving the host untuned revealed substantial time-of-day baseline drift ([10](10-results-analysis.md) §R3.5) and left open whether the single-core `p99` tail (`335–920 µs`) comes from deep C-states or hyper-threading sibling contention.
- **What you can do for a controlled replication or extended study:** the reversible commands below lock the CPU frequency, disable deep sleep states, and steer interrupts so you can isolate runtime behaviour from host power management. The probe core is the **last** CPU.

| Condition | Why it matters | Set for measuring | Restore afterwards |
|---|---|---|---|
| CPU governor | `powersave` lets clock speed drift between runs | `sudo cpupower frequency-set -g performance` | `sudo cpupower frequency-set -g powersave` |
| Deep sleep states (C-states) | waking from a deep state takes up to ~1 ms (C10 ≈ 890 µs on the development laptop); an idle run sleeps deeper | `sudo cpupower idle-set -D 10` (disable states slower than 10 µs) | `sudo cpupower idle-set -E` |
| Turbo | speed depends on temperature and other cores | `echo 1 \| sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo` (Intel) | write `0` |
| NIC interrupts on the probe core | packet handling and the measured program take turns on one CPU | `sudo systemctl stop irqbalance`; find the IRQ with `grep <iface> /proc/interrupts`; `echo 0-6 \| sudo tee /proc/irq/<N>/smp_affinity_list` (all but the last CPU on an 8-CPU host) | `sudo systemctl start irqbalance` |
| Other programs | compete for CPU | close them; check the 1-minute load average is below 1 | - |
| Battery | laptops throttle | plug in | - |

**Check where the NIC interrupt really runs.** The host report lists the CPUs it is *allowed* on. Where it actually runs is in `cat /proc/irq/<N>/effective_affinity_list` and in the per-CPU counts on its line in `/proc/interrupts`. On the development laptop it ran only on CPU 5 ([10](10-results-analysis.md) §R3.6).

**Check the target first.** `ping -c 20 <target>` should show 0 % loss and a stable RTT. Note the RTT: it is the "true" RTT the kernel clock should agree with.

## 4. The protocol (what we ran vs. recommended 5-round replication)

> **Note on what was run in this repository:** The 173 runs in `test_results/` were recorded across two sessions using **2 to 3 repeats per batch** (`3` repeats for `sem-sweep`, `burst-sem`, and `burst-mc`; `2` repeats for `ep-sweep`, Session 1 `burst`, and `same-day`), with **Idle floor every round** introduced in the evening follow-up session ([02 Test methodology](02-test-methodology.md) §5, [10 Results analysis](10-results-analysis.md)). The protocol below incorporates the lessons from both sessions (using **5 rounds** and **Idle floor every round** on every batch) for anyone replicating or extending the study.

1. **Start.** Run `sudo .venv/bin/python -m server.app`, open <http://127.0.0.1:8080>, and press **Ephemres defaults**.
2. **Target.** Enter the **Targets**. Keep **NIC hardware timestamps** off.
3. **Mode.** Choose the **CPU core mode** to test. Do the whole protocol once per mode:
   - the Single-Core batch gives the three single-core combinations;
   - the Multi-Core batch gives the other three, **including Python multi-core** (worker-process offload).
4. **Batch settings.**
   - Tick all three **Batch engines**.
   - Set **Repeat (rounds)** to **5** for formal statistical claims (`p = 0.008` on non-overlapping ranges), or **3** for an exploratory sweep like the ones in `test_results/` (see [02](02-test-methodology.md) §3).
   - Tick **Idle floor every round**, so each test is matched to a floor recorded just before it. Floors from another session are not a fair comparison: the machine's state drifts by more than the effect under a stagger ([10](10-results-analysis.md) §R3.4–§R3.5).
5. **Labels.**
   - Write the question in **What is this run checking?**, e.g. *"Ephemres defaults, single core: which engine keeps intrusion lowest?"*.
   - Give the series a **Series tag**, such as `engines-sc`.
   - Keep notes short (about 25–40 characters); the run table shows only the start of a note.
6. **Run.** Press **Start batch** and leave the machine alone until it finishes.
   - With the Ephemres defaults one run takes about 3.6 minutes.
   - At 3 rounds × 3 engines × (test + floor) = 18 runs ≈ 1 h 05 min; at 5 rounds = 30 runs ≈ 1 h 50 min.
   - The line under the form shows the estimate before you start.
7. **Saving.** Every finished run is **saved automatically** to `test_results/`; the header shows "auto-save on" and "0 unsaved".
   - If the dashboard was started with `--no-autosave`, press **Save all unsaved** before closing.
   - Saved runs reload whenever the dashboard restarts.
8. **Variations and extended experiments.** For each variation you study, change **one** setting from the Ephemres defaults, say so in the note, and run the batch with interleaved floors:
   - **Sweeps included in `test_results/`:** semaphore sweep (`5, 15, 30, 50` staggered; `5, 15, 50` burst), endpoint scaling (`25, 100, 250` staggered), and burst vs staggered (`0 s` vs `60 s`) in single-core and multi-core modes.
   - **Extended experiments for future researchers:** sweeping `simulated_db_ms` across `0.5, 1, 2, 5, 10 ms` (only `0 ms` and `3 ms` were run in `test_results/`), running Python multi-core burst at `db_write_semaphore ≤ CPUs − 1` to isolate pure IPC cost from worker-pool queueing, and repeating the single-core sweeps with C-states disabled and the `performance` governor locked (§3).

The terminal runner (`probe_lab.py`, Python only) gives the same measurement without the dashboard, for scripted sweeps; see [06 Reference](06-reference.md). For long scripted sequences through the dashboard's API, see the cautions in §4c.

## 4b. Ending a session cleanly

* **Nothing unsaved.** Check that the header says **0 unsaved**. Auto-save normally takes care of it; otherwise press **Save all unsaved**. Unsaved runs are lost when the dashboard closes.
* **Stop with Ctrl-C and read the shutdown report.**
  - Use Ctrl-C, not Ctrl-Z: Ctrl-Z only pauses the dashboard, which then keeps its memory and its port.
  - The report's last line should be "check: no probe or worker process of the lab is left, and no NIC timestamping is left on".
* **After an unclean end** (power cut, `kill -9`): run `sudo .venv/bin/python -m server.app --check`, or simply start the dashboard. Either reports anything left over, with the command that fixes it.
* **Undo the host preparation** (governor, C-states, turbo, irqbalance) with the "Restore afterwards" commands in §3.

## 4c. When something goes wrong during a long session

* **Check every run for loss.** A run whose `sent` and `replied` differ (in `.meta.json` → `meta`) is not clean. The study's runs all have `sent = replied`.
* **Check for link drops.** `journalctl --since "<start>" --until "<end>" | grep -i 'link is'` lists them. Delete any run that overlaps a link event (Manage results → Delete ticked…) and record it again.
* **A run stuck at "starting".** This is a known bug, triggered by a network error at the start of a run: it blocks further runs until the dashboard is restarted ([08](08-development.md), Troubleshooting).
* **Scripted batches.** `POST /api/batch` sets every run to role `test` unless `with_floor` is on. To record floors alone, use single `POST /api/run` calls with `"role": "floor"`, or the *Measure idle floor* button.

## 5. Reading the results

1. **Select the batch's runs.** The run table groups them by scenario; "select all N" ticks a group. Keep **combine repeats** on, so each engine becomes one column with the **median** and the **lowest to highest** repeat.
2. **Check the banner.** The yellow **not like for like** banner should be absent. Idle-floor runs are excluded from that check on purpose.
3. **Compare the main figures:**
   - **intrusion** (observer lag) mean and p95, between modes as well as engines; Python single-core vs Python multi-core shows what offloading buys;
   - the primary **error %** (total lag ÷ total kernel RTT);
   - **loss by cause** and **send lag**;
   - for Python multi-core, also the **ORM offload overhead** row.

   A difference counts only when the ranges do not overlap. With 5 repeats that is evidence; with 3, treat it as a hint. This is when ▼/▲ appear, and what the **spread across repeats** chart shows.
4. **Subtract the idle floor.** Tick **subtract idle floor** to see what the CPU work adds above each engine's own floor. A consistently *negative* result means CPU sleep states dominate (see [02 Test methodology](02-test-methodology.md)); limit them before relying on it.
5. **Find the cause.** In the drill-down, the intrusion-over-time chart shades when the ORM work ran. High-lag stacks inside the bands are the observer effect at work.
6. **Internal or external.** Compare the **kernel RTT** percentile chart with the intrusion one.
   - Kernel RTT rising with the load is the external effect: the probes slowed the target.
   - Intrusion rising alone is the internal effect.

   For a series that changes one setting, read the **sweep** chart.
7. **In burst runs, look at the last ping of each cycle.** For Go and Rust, the ORM effect sits almost entirely on that one ping ([10](10-results-analysis.md) Table 2.4, §R3.2). The median then hides it, and the mean mixes it with everything else.

What every row and chart means, and a full reading order, are in [02 Test methodology](02-test-methodology.md) §6 and on the dashboard's Research tab ("Reading the comparison table", "Reading the charts").

## 6. What to report

* **The question and the settings.** The question is the note. The comparison's Markdown export lists the settings for every column.
* **The run details:** engine, CPU core mode, number of repeats, packets per run (`n`), and the target's ordinary `ping` RTT.
  - Base any statistical statement on the per-run figures (one value per repeat), never on the packets pooled across runs.
* **The results:** medians with ranges for intrusion mean and p95, error % (primary), and loss by cause.
* **For Python multi-core:** the ORM offload overhead (mean), the semaphore size and the number of CPUs (pool size = CPUs − 1), because waiting for a worker is part of that figure.
* **The host conditions:** which warnings applied, which you removed, and when each set of runs was recorded.
* **The files:** every run's `<name>.csv`, `<name>_cycles.csv`, `<name>.meta.json`, and its `INDEX.md` entry. File names follow [07 Results and naming](07-results-and-naming.md), so anyone can see each run's setup from its name.

## 7. Every control

Generated from the dashboard's `CONTROLS` list (`server/static/index.html`); after changing it, regenerate with
`.venv/bin/python -m tests.test_controls_documented --print` and replace the tables below (the unit tests fail until you do).

Role column: **variable** = what you compare (may differ between compared runs); **must match** = keep identical across
runs you compare; **label** = bookkeeping only; **view only** = changes what you see, not what was measured; **action**
= a button.

### Run configuration

| Control | What it does | Default | Range | Ephemres | When comparing runs |
|---|---|---|---|---|---|
| **Targets** | The device(s) to ping. Endpoints are spread over them round-robin. Use a LAN device that answers ping with no loss; 127.0.0.1 is only a functional check (its true RTT is a few µs). | empty; then the last target you used in this browser | 1-32 IPv4 addresses, comma-separated; ranges like 10.0.0.1-10.0.0.20 | its monitored devices | must match |
| **Language engine** | The engine that does the probing in a SINGLE run. In a batch it is always one of the engines (see Batch engines). All three send identical packets, keep identical schedules and are analysed by the same code. | Python | Python (asyncio) · Go (goroutines) · Rust (tokio) | Python | variable |
| **CPU core mode** | Single-Core: the engine is pinned to one core (Python and Rust: one thread does everything; Go: GOMAXPROCS=1). Multi-Core: Go and Rust use every core; Python keeps its event loop on one core and sends the ORM work to a pool of worker processes (CPUs − 1), and the cost of that hand-over is reported as ORM offload overhead. Run every engine in both modes: 3 engines × 2 modes = 6 combinations. | Single-Core | Single-Core (1 CPU pinned) · Multi-Core | single thread (1-vCPU GNS3 baseline) | variable |
| **Virtual endpoints** | How many simulated monitored devices run at once. Each has its own ICMP identifier, so hundreds can share one target. More endpoints = more work competing for the engine's attention. | 100 | 1-500 | 100 (the scale at which the problem was seen) | must match |
| **Stagger window** | Endpoint i of N starts at window × i / N seconds. 0 = burst: every endpoint at once, the worst case, which can also overload the target and change the real RTT. | 60 s | 0-120 s on the slider (API: 0-600 s); 0 = burst | 60 s (each endpoint starts at a second 0-59) | must match |
| **db_write_semaphore** | The most endpoints allowed in the database-write step at the same moment. On one thread their CPU work runs back to back, so the worst stall is about semaphore × simulated DB work (15 × 3 ms = 45 ms). | 15 | 1-100 | 15 (raised from 4) | must match |
| **Simulated DB work** | Milliseconds of CPU spent preparing each endpoint's database write (statistics, state machine, ORM objects). It keeps the thread busy, so other endpoints' replies wait. 0 = none: that is the idle floor. | 3 ms | 0-15 ms in 0.5 ms steps | 3 ms (the lab's estimate) | must match |
| **Pings per cycle** | How many pings one endpoint sends per cycle before its database write. | 5 | 1-20 (cycles × pings ≤ 65536) | 5 | must match |
| **Ping interval** | Seconds between one endpoint's pings. With 8 s, a cycle's pings span 32 s, so many endpoints are mid-cycle at once, as in Ephemres. | 8 s | 0.05-30 s | 8 s | must match |
| **Reply timeout** | How long to wait for a reply before counting the ping as lost. A reply that comes later is still recorded as late, so loss can be split into real loss and loss caused by reading too late. | 2 s | 0.1-10 s | (lab value) | must match |
| **Cycles per endpoint** | How many times each endpoint repeats pings + database write. With more than one, cycle 0 is a warm-up (endpoints still starting) and is left out of every statistic. | 3 | 1-60 | runs continuously | must match |
| **Cycle length** | Seconds from the start of one cycle to the start of the next, for the same endpoint. Only matters with more than one cycle. | 60 s | 1-600 s, and at least (pings − 1) × interval + timeout | 60 s | must match |
| **NIC hardware timestamps** | Also record the network card's own receive stamp (a different clock, for cross-checking with tcpdump only). It changes a setting on the card for the run, which Go and Rust never do, so leave it off for any run you compare across engines. | off | Python engine only; needs root and a NIC that supports it | off | must match (keep off across engines) |

### Batch (repeated runs)

| Control | What it does | Default | Range | Ephemres | When comparing runs |
|---|---|---|---|---|---|
| **Repeat (rounds)** | Run the same setup this many rounds. More than 1 (or more than one batch engine, or idle floor every round) turns Start into Start batch: the dashboard runs every round itself. Use 5 rounds to report a difference (3 is enough only for a first look; see 'How many repeats a claim needs' in docs/02). | 1 (no batch) | 1-20 | - | label |
| **Batch engines (take turns each round)** | Which engines a batch runs in every round. The language engine selected above is always included (its box is shown ticked and locked); tick others to compare engines in one batch. The order rotates each round (Py Go Rs, then Go Rs Py, then Rs Py Go) so a slow drift of the machine hits every engine equally. Ignored for a single run. | only the language engine | any of Python, Go, Rust (built engines only) | - | variable |
| **Idle floor every round** | In every round, run each engine's idle floor (this setup with 0 ms ORM work) just before its test run, so each test is matched to a floor measured moments earlier. Doubles the number of runs. | off | on / off | - | label |

### Labels

| Control | What it does | Default | Range | Ephemres | When comparing runs |
|---|---|---|---|---|---|
| **Series tag** | A short label appended to the saved file name, to find a family of runs later (e.g. sem-sweep). | empty (a batch uses its series id) | ≤ 24 characters; letters, digits, dashes | - | label |
| **What is this run checking?** | One sentence on the question the run answers. Shown in the run table, the comparison and every export; editable after the run (drill-down). | empty | ≤ 300 characters | - | label |

### Buttons

| Control | What it does | Default | Range | Ephemres | When comparing runs |
|---|---|---|---|---|---|
| **Start run / Start batch** | Starts one run of the form's setup, or a batch when Repeat > 1, other batch engines are ticked, or idle floor every round is on. Values are checked first; the line under the form says how long it will take. | - | - | - | action |
| **Stop** | Interrupts the running probe (it still writes its summary and keeps the data, status 'stopped') and cancels the rest of a batch. | - | - | - | action |
| **Measure idle floor** | Runs the form's setup once with 0 ms ORM work: the engine's idle floor for exactly this setup. Needed for 'subtract idle floor'. | - | - | - | action |
| **Ephemres defaults** | Resets every run setting to Ephemres' configuration (100 endpoints, 5 pings 8 s apart, 2 s timeout, 60 s stagger, 3 cycles of 60 s, semaphore 15, 3 ms ORM, NIC stamps off). | - | - | - | action |
| **Burst (0 s)** | Sets the stagger window to 0: every endpoint starts at once (worst case). | - | - | - | action |

### Choosing runs

| Control | What it does | Default | Range | Ephemres | When comparing runs |
|---|---|---|---|---|---|
| **Run tick boxes and ● baseline** | Tick runs to compare. The ● picks the baseline column: other columns also show their value as a multiple of it. An idle-floor run is never the default baseline. | baseline = first test run | up to 8 columns | - | view only |
| **Filter** | Shows only runs whose name, status or settings contain the text (e.g. 'go', a tag, a target). | empty | any text | - | view only |
| **Group by scenario** | Groups the run table by scenario: runs that asked the same question (same load and target) of any engine. 'Select all N' ticks a whole group. | on | on / off | - | view only |
| **Combine repeats** | Repeats of one setup (same batch, engine, CPU mode and role) become ONE column showing the median with the lowest-highest repeat underneath, and share one colour. Off: every run is its own column. | on | on / off | - | view only |
| **Clear** | Unticks every run. | - | - | - | action |
| **Save all unsaved** | Saves every finished run that is not saved yet. With auto-save on (the default) finished runs are saved by themselves; this is for runs made with --no-autosave, or a run whose auto-save failed. | - | - | - | action |

### Managing results

| Control | What it does | Default | Range | Ephemres | When comparing runs |
|---|---|---|---|---|---|
| **Manage results (save / delete)** | Shows an extra tick column for saving or deleting runs, separate from the comparison ticks and without their 8-column limit. Turning it off unticks everything. | off | on / off | - | view only |
| **Tick all shown** | Ticks every run the table shows right now; combine with the Filter (e.g. a tag, an engine or a date) to tick a whole family of runs. | - | - | - | action |
| **Untick all** | Unticks every run in the manage column. | - | - | - | action |
| **Save ticked** | Saves the ticked runs that are not saved yet (already-saved ones are skipped). | - | - | - | action |
| **Delete ticked…** | After a confirmation that lists them, removes the ticked runs from the lab. Saved runs' files and INDEX.md entries are MOVED to test_results/.deleted/<date-time>/, so they can be restored by moving them back; delete that folder to make it permanent. Unsaved runs are discarded from memory. Running runs cannot be deleted. | - | - | - | action |

### Comparison table

| Control | What it does | Default | Range | Ephemres | When comparing runs |
|---|---|---|---|---|---|
| **Show × baseline** | Adds each value as a multiple of the baseline column (0.50× = half the baseline). | on | on / off | - | view only |
| **Subtract idle floor** | Adds rows with each run's intrusion minus that of its matching idle-floor run (the latest floor run of the same engine, mode, target and schedule). Raw figures stay; negative results are labelled noise. | off | on / off | - | view only |
| **Mark best/worst when they differ by** | ▼ best and ▲ worst appear only when the best and worst values differ by at least this much; with repeats, also only when their ranges do not overlap. Idle-floor columns never compete. | ≥ 10 % | never, 5, 10, 25, 50 % | - | view only |
| **⬇ Markdown (comparison)** | Downloads the comparison as a Markdown table (repeats combined when 'combine repeats' is on), including each run's note. | - | - | - | action |
| **⬇ CSV (comparison)** | Downloads the comparison as CSV: one row per metric, one column per run, raw numbers. | - | - | - | action |

### Charts

| Control | What it does | Default | Range | Ephemres | When comparing runs |
|---|---|---|---|---|---|
| **Key metrics: metric set** | Which figures the 'Key metrics by run' chart shows. | Intrusion | intrusion, RTT, jitter, send lag, canary | - | view only |
| **Log scale (dots)** | Logarithmic axis for values from µs to tens of ms. On a log axis bars would mislead, so dots are drawn instead. | on | on / off | - | view only |
| **Intrusion over time: all selected runs** | Off: the chart shows only the run picked in the drill-down, with its ORM work shaded, so stalls line up with their cause. On: every selected run is overlaid (each on its own time axis, ms since its first ping). | off (the drill-down run only) | on / off | - | view only |
| **Spread across repeats: figure** | Which figure the spread chart plots: one dot per repeat and a dash at the median, per column. | Intrusion p95 | intrusion mean/p95/p99/max, error %, above-floor p95, send lag p95, canary max | - | view only |
| **Sweep: setting (x axis)** | Which run setting the sweep chart puts on the x axis. 'The setting that differs' picks the first of these that varies between the selected test runs. | the setting that differs | endpoints, stagger window, semaphore, ORM ms, pings per cycle, ping interval, cycle length | - | view only |
| **Sweep: figure (y axis)** | Which figure the sweep chart plots for each run against the chosen setting; the line joins the median per engine. | Intrusion p95 | intrusion mean/p95/p99/max, error %, above-floor p95, send lag p95, canary max | - | view only |

### Drill-down

| Control | What it does | Default | Range | Ephemres | When comparing runs |
|---|---|---|---|---|---|
| **Drill-down run** | The run whose cards, per-endpoint chart, worst-10 table and host conditions are shown, and whose ORM work is shaded in the intrusion-over-time chart. | the baseline | any selected run | - | view only |
| **What this run checks (edit)** | Edit the drill-down run's note; Save note (or Enter) stores it, also in a saved run's .meta.json and INDEX.md. | the run's note | ≤ 300 characters | - | label |
| **Save to test_results/** | Writes the run's CSVs, .meta.json and an INDEX.md entry to the results folder (test_results/ unless OBSERVER_RESULTS_DIR is set). With auto-save on (the default) every finished run is saved by itself and this shows ✔ Saved. | - | - | - | action |
| **⬇ Packets CSV** | Every packet of the run, both clocks, lag, send lag, late replies. | - | - | - | action |
| **⬇ Endpoints CSV** | One row per endpoint: RTTs, intrusion, error %, wakeups. | - | - | - | action |
| **⬇ Report (MD)** | A Markdown report of the run: summary, worst endpoints, distribution, idle floor, host conditions. | - | - | - | action |
| **Per-endpoint chart mode** | Stacked: kernel RTT plus intrusion per endpoint (their sum is what the monitor reports). Intrusion only: just the waiting time. | RTT stacked | RTT stacked · Intrusion only | - | view only |

### Page

| Control | What it does | Default | Range | Ephemres | When comparing runs |
|---|---|---|---|---|---|
| **Section bar** | The links under the header (1 · Run, 2 · Runs, 3 · Comparison, Charts, 4 · Drill-down) jump to each part of the Lab tab and highlight the part you are in. The Research tab has the same as its contents list (beside the text on wide screens). | - | - | - | view only |
| **▾ / ▸ (fold)** | In a panel heading: folds the panel away or opens it (remembered in this browser). In the run table: shows or hides the runs of one scenario; by default a scenario is open when it has a selected or running run, or 3 runs or fewer. | open | open / folded | - | view only |
| **Theme** | Colour theme. Both themes meet WCAG AA text contrast and use colour-blind-checked run colours; every run also has its own marker shape. | auto | auto (follows the OS) · dark · light | - | view only |

### Terms used above

* **Scenario**: Runs with identical endpoints, schedule, semaphore, ORM time, pings, interval, cycles, timeout and target: they asked the same question, of any engine. Only runs in the same scenario compare like for like; the page warns otherwise.
* **few samples**: A percentile needs enough packets to mean anything: about 10 ÷ (1 − q), so p95 needs ~200 packets and p99 ~1000. Below that the value is flagged in the table and left out of the percentile chart.
* **Log scale**: Charts spanning microseconds to tens of milliseconds are easier to read on a logarithmic axis, where each gridline is ten times the previous one.
