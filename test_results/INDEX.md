# probe_lab test results

## Naming convention

`<WHEN>_<RUNTIME>_<LOAD>_<TARGET>[_<tag>]`

    20261021-224241_go-mc_100ep-burst-sem15-db3_172-40-0-253

| Group | Meaning | Example |
|---|---|---|
| WHEN | start time, sorts chronologically | `20261021-224241` |
| RUNTIME | engine (`py` `go` `rs`) and cores (`sc` single/pinned, `mc` multi) | `go-mc` |
| LOAD | endpoints, schedule (`burst` or `stg<seconds>`), semaphore size, simulated ORM ms; `-p<pings>` / `-i<interval>` appear only when not the defaults (5 pings, 1 s) | `100ep-burst-sem15-db3` |
| TARGET | first target IP with dashes (`+K` = K more targets) | `172-40-0-253` |
| tag | optional label you choose to group a series | `sem-sweep` |

LOAD + TARGET is identical for every run that asked the same question of a different engine, so
runs with the same text there are directly comparable (the dashboard groups them automatically).
Decimal points are written `p` (0.2 = `0p2`). Files per run: `<name>.csv` (per packet), `<name>_cycles.csv`
(per cycle), `<name>.meta.json` (full configuration and counters). Runs from before engines existed are all
Python single core (`py-sc`) and were renamed to this scheme.

One entry per run. New runs (CLI or dashboard) save here under this naming scheme and append an entry below automatically.
Add `--note "what this run was for"` to set the description.

Per run: `<name>.csv` = one row per packet; `<name>_cycles.csv` = per endpoint-cycle statistics.
Units: microseconds unless stated. "Kernel" = Clock A (kernel arrival stamp), "Python" = Clock B.

## (summary only, CSV overwritten) first burst run, 21:12

- **Description:** First burst run against the same target. Shows the semaphore stall: 15 endpoints x 3 ms ORM = ~45 ms, matching the 46 ms max lag. Also overloaded the target (kernel RTT ~21 ms, 50 lost). Its CSV was overwritten by the re-run above.
- **Command:** `sudo python3 probe_lab.py --targets 172.40.0.253 --virtual-endpoints 100 --burst --cycle-length 10 --semaphore 15 --simulated-db-ms 3.0`

```text
SUMMARY  packets sent=500 replied=450 lost=50 (unmatched replies=0, reader wakeups=44)
  Kernel Control RTT   mean   20846.2 us   mean cycle jitter   1194.5 us
  Python Observer RTT  mean   26991.7 us   mean cycle jitter   2662.6 us
  Observer intrusion   mean    6145.4 us   p95   42996.8 us   max   46190.2 us
                       mean error   34.0 %   max error  436.4 %
  Event-loop canary    avg     771.8 us   p95     572.0 us   max   50161.7 us
```

## (no CSV kept) loopback 127.0.0.1, 30 endpoints, burst

- **Date:** 2026-10-21
- **Description:** First real `sudo` run on loopback (software timestamps only; lo has no NIC hardware). CSV was overwritten by a later run, only the summary survives. Shows the effect when true RTT is ~16 us, so percentages are huge.
- **Command:** `sudo python3 probe_lab.py --targets 127.0.0.1 --virtual-endpoints 30 --burst --cycle-length 5 --interval 0.3 --simulated-db-ms 3`

```text
SUMMARY  packets sent=150 replied=150 lost=0 (unmatched replies=0, reader wakeups=6)
  Kernel Control RTT   mean      15.9 us   mean cycle jitter      1.5 us
  Python Observer RTT  mean     679.4 us   mean cycle jitter     88.5 us
  Observer intrusion   mean     663.5 us   p95    1439.3 us   max    1821.2 us
                       mean error 4422.9 %   max error 8302.2 %
  Event-loop canary    avg     924.7 us   p95     897.9 us   max   45378.1 us
```

## 20261024-093023_py-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-24 09:33:55
- **Description:** Idle floor · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261024-093023_py-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261024-093023_py-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261024-093023_py-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=685)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 857.0 µs   p95 1.67 ms   max 2.44 ms
  Kernel Control RTT   mean 476.1 µs   mean cycle jitter 39.7 µs
  Python Observer RTT  mean 587.4 µs   mean cycle jitter 43.6 µs
  Observer intrusion   mean 111.3 µs   p95 174.6 µs   max 1.85 ms
                       error 23.4 % (total lag / total RTT)   per packet: median 21.2 %  mean 27.0 %  max 609.6 %
  Event-loop canary    avg 321.3 µs   p95 656.1 µs   max 6.36 ms
```

## 20261024-095303_go-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-24 09:56:34
- **Description:** Idle floor · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261024-095303_go-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261024-095303_go-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261024-095303_go-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 718.4 µs   p95 1.26 ms   max 5.60 ms
  Kernel Control RTT   mean 453.0 µs   mean cycle jitter 35.2 µs
  Python Observer RTT  mean 539.2 µs   mean cycle jitter 40.2 µs
  Observer intrusion   mean 86.2 µs   p95 139.3 µs   max 1.01 ms
                       error 19.0 % (total lag / total RTT)   per packet: median 15.9 %  mean 21.6 %  max 276.1 %
  Event-loop canary    avg 327.9 µs   p95 800.3 µs   max 5.18 ms
```

## 20261024-101910_rs-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-24 10:22:42
- **Description:** Idle floor · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261024-101910_rs-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261024-101910_rs-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261024-101910_rs-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 894.5 µs   p95 1.27 ms   max 3.88 ms
  Kernel Control RTT   mean 460.3 µs   mean cycle jitter 36.3 µs
  Python Observer RTT  mean 546.4 µs   mean cycle jitter 41.5 µs
  Observer intrusion   mean 86.0 µs   p95 124.3 µs   max 1.82 ms
                       error 18.7 % (total lag / total RTT)   per packet: median 15.4 %  mean 21.4 %  max 454.6 %
  Event-loop canary    avg 1.20 ms   p95 1.57 ms   max 7.52 ms
```

## 20261024-103917_py-mc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-24 10:42:49
- **Description:** Idle floor · Python multi-core
- **Command:** `dashboard run: engine=python cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261024-103917_py-mc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261024-103917_py-mc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261024-103917_py-mc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=689)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 926.7 µs   p95 1.86 ms   max 3.81 ms
  Kernel Control RTT   mean 454.6 µs   mean cycle jitter 37.9 µs
  Python Observer RTT  mean 567.5 µs   mean cycle jitter 42.1 µs
  Observer intrusion   mean 112.9 µs   p95 176.6 µs   max 1.07 ms
                       error 24.8 % (total lag / total RTT)   per packet: median 22.7 %  mean 28.7 %  max 688.7 %
  Event-loop canary    avg 322.4 µs   p95 687.3 µs   max 5.32 ms
```

## 20261024-105030_go-mc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-24 10:54:01
- **Description:** Idle floor · Go multi-core
- **Command:** `dashboard run: engine=go cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261024-105030_go-mc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261024-105030_go-mc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261024-105030_go-mc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=682)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 613.2 µs   p95 1.13 ms   max 3.87 ms
  Kernel Control RTT   mean 459.9 µs   mean cycle jitter 37.6 µs
  Python Observer RTT  mean 530.8 µs   mean cycle jitter 41.0 µs
  Observer intrusion   mean 70.8 µs   p95 105.9 µs   max 3.36 ms
                       error 15.4 % (total lag / total RTT)   per packet: median 14.1 %  mean 19.1 %  max 2638.3 %
  Event-loop canary    avg 338.7 µs   p95 741.9 µs   max 6.95 ms
```

## 20261024-111855_rs-mc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-24 11:22:26
- **Description:** Idle floor · Rust multi-core
- **Command:** `dashboard run: engine=rust cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261024-111855_rs-mc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261024-111855_rs-mc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261024-111855_rs-mc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=681)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.40 ms   p95 1.82 ms   max 3.55 ms
  Kernel Control RTT   mean 468.9 µs   mean cycle jitter 37.4 µs
  Python Observer RTT  mean 543.4 µs   mean cycle jitter 42.4 µs
  Observer intrusion   mean 74.5 µs   p95 108.4 µs   max 2.86 ms
                       error 15.9 % (total lag / total RTT)   per packet: median 13.7 %  mean 18.2 %  max 845.1 %
  Event-loop canary    avg 1.17 ms   p95 1.55 ms   max 4.76 ms
```

## 20261024-115607_py-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 11:59:39
- **Description:** sem 5 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-115607_py-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-115607_py-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-115607_py-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=686)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 869.1 µs   p95 1.75 ms   max 3.34 ms
  Kernel Control RTT   mean 463.5 µs   mean cycle jitter 38.2 µs
  Python Observer RTT  mean 587.1 µs   mean cycle jitter 46.1 µs
  Observer intrusion   mean 123.6 µs   p95 176.8 µs   max 2.41 ms
                       error 26.7 % (total lag / total RTT)   per packet: median 22.3 %  mean 31.1 %  max 774.1 %
  Event-loop canary    avg 334.0 µs   p95 803.2 µs   max 6.04 ms
```

## 20261024-115939_py-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 12:03:11
- **Description:** sem 5 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-115939_py-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-115939_py-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-115939_py-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=688)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 897.2 µs   p95 1.86 ms   max 2.37 ms
  Kernel Control RTT   mean 461.7 µs   mean cycle jitter 39.0 µs
  Python Observer RTT  mean 573.3 µs   mean cycle jitter 43.9 µs
  Observer intrusion   mean 111.6 µs   p95 174.3 µs   max 3.21 ms
                       error 24.2 % (total lag / total RTT)   per packet: median 21.9 %  mean 27.9 %  max 1037.0 %
  Event-loop canary    avg 336.0 µs   p95 818.0 µs   max 6.36 ms
```

## 20261024-120311_py-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 12:06:43
- **Description:** sem 5 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-120311_py-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-120311_py-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-120311_py-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=687)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 823.7 µs   p95 1.75 ms   max 3.99 ms
  Kernel Control RTT   mean 466.8 µs   mean cycle jitter 37.4 µs
  Python Observer RTT  mean 579.0 µs   mean cycle jitter 41.4 µs
  Observer intrusion   mean 112.2 µs   p95 174.4 µs   max 950.0 µs
                       error 24.0 % (total lag / total RTT)   per packet: median 22.3 %  mean 27.1 %  max 247.3 %
  Event-loop canary    avg 334.0 µs   p95 722.7 µs   max 5.28 ms
```

## 20261024-120921_go-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 12:12:53
- **Description:** sem 5 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-120921_go-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-120921_go-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-120921_go-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=682)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 660.1 µs   p95 1.20 ms   max 2.34 ms
  Kernel Control RTT   mean 460.1 µs   mean cycle jitter 35.0 µs
  Python Observer RTT  mean 545.3 µs   mean cycle jitter 40.0 µs
  Observer intrusion   mean 85.1 µs   p95 121.6 µs   max 2.00 ms
                       error 18.5 % (total lag / total RTT)   per packet: median 17.0 %  mean 20.9 %  max 540.5 %
  Event-loop canary    avg 341.7 µs   p95 800.9 µs   max 3.50 ms
```

## 20261024-121253_go-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 12:16:24
- **Description:** sem 5 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-121253_go-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-121253_go-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-121253_go-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=681)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 612.1 µs   p95 1.21 ms   max 3.22 ms
  Kernel Control RTT   mean 452.4 µs   mean cycle jitter 32.3 µs
  Python Observer RTT  mean 534.1 µs   mean cycle jitter 36.2 µs
  Observer intrusion   mean 81.7 µs   p95 111.9 µs   max 873.7 µs
                       error 18.0 % (total lag / total RTT)   per packet: median 17.4 %  mean 20.7 %  max 305.8 %
  Event-loop canary    avg 350.3 µs   p95 794.6 µs   max 4.24 ms
```

## 20261024-121624_go-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 12:19:56
- **Description:** sem 5 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-121624_go-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-121624_go-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-121624_go-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 690.4 µs   p95 1.21 ms   max 2.12 ms
  Kernel Control RTT   mean 449.9 µs   mean cycle jitter 33.8 µs
  Python Observer RTT  mean 535.5 µs   mean cycle jitter 40.9 µs
  Observer intrusion   mean 85.5 µs   p95 115.9 µs   max 2.92 ms
                       error 19.0 % (total lag / total RTT)   per packet: median 16.1 %  mean 21.6 %  max 777.6 %
  Event-loop canary    avg 340.5 µs   p95 809.0 µs   max 4.01 ms
```

## 20261024-122134_rs-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 12:25:06
- **Description:** sem 5 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-122134_rs-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-122134_rs-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-122134_rs-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 985.9 µs   p95 1.39 ms   max 3.47 ms
  Kernel Control RTT   mean 456.5 µs   mean cycle jitter 35.1 µs
  Python Observer RTT  mean 554.0 µs   mean cycle jitter 46.7 µs
  Observer intrusion   mean 97.5 µs   p95 127.3 µs   max 3.49 ms
                       error 21.4 % (total lag / total RTT)   per packet: median 16.4 %  mean 24.8 %  max 1028.7 %
  Event-loop canary    avg 1.20 ms   p95 1.57 ms   max 6.45 ms
```

## 20261024-122506_rs-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 12:28:38
- **Description:** sem 5 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-122506_rs-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-122506_rs-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-122506_rs-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 914.3 µs   p95 1.48 ms   max 3.42 ms
  Kernel Control RTT   mean 463.8 µs   mean cycle jitter 33.6 µs
  Python Observer RTT  mean 550.5 µs   mean cycle jitter 38.8 µs
  Observer intrusion   mean 86.7 µs   p95 112.2 µs   max 3.17 ms
                       error 18.7 % (total lag / total RTT)   per packet: median 16.0 %  mean 21.2 %  max 841.9 %
  Event-loop canary    avg 1.21 ms   p95 1.56 ms   max 6.01 ms
```

## 20261024-122838_rs-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 12:32:09
- **Description:** sem 5 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-122838_rs-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-122838_rs-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-122838_rs-sc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 816.5 µs   p95 1.27 ms   max 3.58 ms
  Kernel Control RTT   mean 456.9 µs   mean cycle jitter 34.9 µs
  Python Observer RTT  mean 534.0 µs   mean cycle jitter 37.9 µs
  Observer intrusion   mean 77.1 µs   p95 107.7 µs   max 560.1 µs
                       error 16.9 % (total lag / total RTT)   per packet: median 15.7 %  mean 19.7 %  max 596.0 %
  Event-loop canary    avg 1.19 ms   p95 1.56 ms   max 4.73 ms
```

## 20261024-123746_py-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 12:41:18
- **Description:** sem 30 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-123746_py-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-123746_py-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-123746_py-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=688)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 857.5 µs   p95 1.58 ms   max 2.42 ms
  Kernel Control RTT   mean 469.3 µs   mean cycle jitter 39.8 µs
  Python Observer RTT  mean 582.9 µs   mean cycle jitter 43.4 µs
  Observer intrusion   mean 113.6 µs   p95 175.1 µs   max 1.51 ms
                       error 24.2 % (total lag / total RTT)   per packet: median 22.2 %  mean 27.8 %  max 304.9 %
  Event-loop canary    avg 336.6 µs   p95 762.2 µs   max 6.07 ms
```

## 20261024-124118_py-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 12:44:50
- **Description:** sem 30 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-124118_py-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-124118_py-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-124118_py-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=688)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 833.3 µs   p95 1.73 ms   max 3.84 ms
  Kernel Control RTT   mean 467.6 µs   mean cycle jitter 40.0 µs
  Python Observer RTT  mean 579.0 µs   mean cycle jitter 42.9 µs
  Observer intrusion   mean 111.4 µs   p95 176.5 µs   max 1.23 ms
                       error 23.8 % (total lag / total RTT)   per packet: median 22.6 %  mean 27.5 %  max 234.4 %
  Event-loop canary    avg 335.2 µs   p95 765.5 µs   max 5.75 ms
```

## 20261024-124450_py-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 12:48:22
- **Description:** sem 30 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-124450_py-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-124450_py-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-124450_py-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=691)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 806.6 µs   p95 1.75 ms   max 3.89 ms
  Kernel Control RTT   mean 458.0 µs   mean cycle jitter 38.2 µs
  Python Observer RTT  mean 576.8 µs   mean cycle jitter 42.9 µs
  Observer intrusion   mean 118.8 µs   p95 178.1 µs   max 2.58 ms
                       error 25.9 % (total lag / total RTT)   per packet: median 22.5 %  mean 34.1 %  max 2430.9 %
  Event-loop canary    avg 340.7 µs   p95 805.3 µs   max 6.52 ms
```

## 20261024-142351_go-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 14:27:22
- **Description:** sem 30 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-142351_go-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-142351_go-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-142351_go-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=681)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 635.0 µs   p95 1.22 ms   max 4.17 ms
  Kernel Control RTT   mean 456.0 µs   mean cycle jitter 36.8 µs
  Python Observer RTT  mean 543.9 µs   mean cycle jitter 42.3 µs
  Observer intrusion   mean 87.9 µs   p95 130.9 µs   max 3.20 ms
                       error 19.3 % (total lag / total RTT)   per packet: median 15.9 %  mean 24.0 %  max 2401.9 %
  Event-loop canary    avg 336.6 µs   p95 809.8 µs   max 6.96 ms
```

## 20261024-142722_go-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 14:30:54
- **Description:** sem 30 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-142722_go-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-142722_go-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-142722_go-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=681)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 675.6 µs   p95 1.21 ms   max 3.47 ms
  Kernel Control RTT   mean 462.3 µs   mean cycle jitter 36.4 µs
  Python Observer RTT  mean 553.6 µs   mean cycle jitter 43.5 µs
  Observer intrusion   mean 91.3 µs   p95 138.7 µs   max 2.62 ms
                       error 19.7 % (total lag / total RTT)   per packet: median 16.3 %  mean 23.0 %  max 643.0 %
  Event-loop canary    avg 343.2 µs   p95 806.5 µs   max 6.79 ms
```

## 20261024-143054_go-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 14:34:25
- **Description:** sem 30 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-143054_go-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-143054_go-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-143054_go-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=681)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 653.3 µs   p95 1.22 ms   max 4.22 ms
  Kernel Control RTT   mean 480.5 µs   mean cycle jitter 37.2 µs
  Python Observer RTT  mean 574.1 µs   mean cycle jitter 44.7 µs
  Observer intrusion   mean 93.6 µs   p95 118.8 µs   max 3.58 ms
                       error 19.5 % (total lag / total RTT)   per packet: median 15.9 %  mean 24.1 %  max 2206.1 %
  Event-loop canary    avg 348.7 µs   p95 800.9 µs   max 4.38 ms
```

## 20261024-144526_rs-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 14:48:58
- **Description:** sem 30 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-144526_rs-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-144526_rs-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-144526_rs-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 850.4 µs   p95 1.44 ms   max 3.24 ms
  Kernel Control RTT   mean 445.7 µs   mean cycle jitter 34.9 µs
  Python Observer RTT  mean 539.7 µs   mean cycle jitter 43.7 µs
  Observer intrusion   mean 94.0 µs   p95 136.2 µs   max 3.45 ms
                       error 21.1 % (total lag / total RTT)   per packet: median 16.5 %  mean 24.5 %  max 905.5 %
  Event-loop canary    avg 1.21 ms   p95 1.58 ms   max 9.38 ms
```

## 20261024-144858_rs-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 14:52:29
- **Description:** sem 30 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-144858_rs-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-144858_rs-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-144858_rs-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=682)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 824.8 µs   p95 1.38 ms   max 4.23 ms
  Kernel Control RTT   mean 434.8 µs   mean cycle jitter 31.9 µs
  Python Observer RTT  mean 523.5 µs   mean cycle jitter 40.1 µs
  Observer intrusion   mean 88.7 µs   p95 120.3 µs   max 2.49 ms
                       error 20.4 % (total lag / total RTT)   per packet: median 16.6 %  mean 23.6 %  max 813.3 %
  Event-loop canary    avg 1.19 ms   p95 1.55 ms   max 7.08 ms
```

## 20261024-145229_rs-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 14:56:01
- **Description:** sem 30 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-145229_rs-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-145229_rs-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-145229_rs-sc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 962.3 µs   p95 1.51 ms   max 4.34 ms
  Kernel Control RTT   mean 452.4 µs   mean cycle jitter 36.0 µs
  Python Observer RTT  mean 538.3 µs   mean cycle jitter 42.0 µs
  Observer intrusion   mean 85.9 µs   p95 112.4 µs   max 2.83 ms
                       error 19.0 % (total lag / total RTT)   per packet: median 16.4 %  mean 21.8 %  max 754.6 %
  Event-loop canary    avg 1.20 ms   p95 1.57 ms   max 6.86 ms
```

## 20261024-150329_py-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 15:07:01
- **Description:** sem 50 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-150329_py-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-150329_py-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-150329_py-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=689)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 875.5 µs   p95 1.95 ms   max 2.97 ms
  Kernel Control RTT   mean 453.5 µs   mean cycle jitter 39.2 µs
  Python Observer RTT  mean 569.6 µs   mean cycle jitter 44.3 µs
  Observer intrusion   mean 116.1 µs   p95 186.3 µs   max 1.31 ms
                       error 25.6 % (total lag / total RTT)   per packet: median 23.2 %  mean 29.3 %  max 393.0 %
  Event-loop canary    avg 325.6 µs   p95 753.0 µs   max 4.31 ms
```

## 20261024-150701_py-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 15:10:32
- **Description:** sem 50 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-150701_py-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-150701_py-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-150701_py-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=689)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 838.6 µs   p95 1.56 ms   max 3.13 ms
  Kernel Control RTT   mean 467.2 µs   mean cycle jitter 41.1 µs
  Python Observer RTT  mean 586.0 µs   mean cycle jitter 47.4 µs
  Observer intrusion   mean 118.8 µs   p95 171.9 µs   max 3.31 ms
                       error 25.4 % (total lag / total RTT)   per packet: median 23.3 %  mean 28.8 %  max 1084.5 %
  Event-loop canary    avg 333.2 µs   p95 661.1 µs   max 6.15 ms
```

## 20261024-151032_py-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 15:14:04
- **Description:** sem 50 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-151032_py-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-151032_py-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-151032_py-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=689)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 865.7 µs   p95 1.78 ms   max 3.44 ms
  Kernel Control RTT   mean 451.4 µs   mean cycle jitter 39.6 µs
  Python Observer RTT  mean 564.5 µs   mean cycle jitter 43.7 µs
  Observer intrusion   mean 113.1 µs   p95 176.3 µs   max 1.25 ms
                       error 25.0 % (total lag / total RTT)   per packet: median 22.7 %  mean 30.6 %  max 916.0 %
  Event-loop canary    avg 327.5 µs   p95 703.9 µs   max 6.33 ms
```

## 20261024-151724_go-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 15:20:55
- **Description:** sem 50 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-151724_go-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-151724_go-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-151724_go-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=681)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 657.6 µs   p95 1.14 ms   max 4.35 ms
  Kernel Control RTT   mean 443.0 µs   mean cycle jitter 33.4 µs
  Python Observer RTT  mean 532.2 µs   mean cycle jitter 39.9 µs
  Observer intrusion   mean 89.2 µs   p95 140.8 µs   max 2.52 ms
                       error 20.1 % (total lag / total RTT)   per packet: median 16.5 %  mean 23.5 %  max 687.9 %
  Event-loop canary    avg 333.9 µs   p95 807.0 µs   max 4.75 ms
```

## 20261024-152055_go-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 15:24:27
- **Description:** sem 50 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-152055_go-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-152055_go-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-152055_go-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=682)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 670.2 µs   p95 1.09 ms   max 2.06 ms
  Kernel Control RTT   mean 457.0 µs   mean cycle jitter 36.0 µs
  Python Observer RTT  mean 536.8 µs   mean cycle jitter 41.1 µs
  Observer intrusion   mean 79.8 µs   p95 106.5 µs   max 3.19 ms
                       error 17.5 % (total lag / total RTT)   per packet: median 15.0 %  mean 21.7 %  max 2382.7 %
  Event-loop canary    avg 334.9 µs   p95 796.3 µs   max 6.78 ms
```

## 20261024-152427_go-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 15:27:58
- **Description:** sem 50 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-152427_go-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-152427_go-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-152427_go-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=681)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 605.0 µs   p95 1.15 ms   max 3.33 ms
  Kernel Control RTT   mean 454.3 µs   mean cycle jitter 35.6 µs
  Python Observer RTT  mean 543.7 µs   mean cycle jitter 43.1 µs
  Observer intrusion   mean 89.4 µs   p95 120.0 µs   max 2.52 ms
                       error 19.7 % (total lag / total RTT)   per packet: median 16.3 %  mean 22.8 %  max 775.6 %
  Event-loop canary    avg 336.9 µs   p95 797.2 µs   max 4.32 ms
```

## 20261024-161059_rs-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 16:14:31
- **Description:** sem 50 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-161059_rs-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-161059_rs-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-161059_rs-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 838.5 µs   p95 1.28 ms   max 2.84 ms
  Kernel Control RTT   mean 444.9 µs   mean cycle jitter 31.3 µs
  Python Observer RTT  mean 533.7 µs   mean cycle jitter 39.0 µs
  Observer intrusion   mean 88.8 µs   p95 139.8 µs   max 2.43 ms
                       error 20.0 % (total lag / total RTT)   per packet: median 15.8 %  mean 23.2 %  max 715.6 %
  Event-loop canary    avg 1.18 ms   p95 1.58 ms   max 6.37 ms
```

## 20261024-161431_rs-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 16:18:02
- **Description:** sem 50 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-161431_rs-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-161431_rs-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-161431_rs-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 932.5 µs   p95 1.34 ms   max 3.47 ms
  Kernel Control RTT   mean 450.1 µs   mean cycle jitter 34.5 µs
  Python Observer RTT  mean 542.8 µs   mean cycle jitter 43.3 µs
  Observer intrusion   mean 92.7 µs   p95 120.9 µs   max 3.38 ms
                       error 20.6 % (total lag / total RTT)   per packet: median 16.8 %  mean 22.9 %  max 729.6 %
  Event-loop canary    avg 1.18 ms   p95 1.56 ms   max 6.88 ms
```

## 20261024-161802_rs-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 16:21:34
- **Description:** sem 50 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-161802_rs-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-161802_rs-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-161802_rs-sc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 820.3 µs   p95 1.29 ms   max 4.07 ms
  Kernel Control RTT   mean 423.6 µs   mean cycle jitter 31.8 µs
  Python Observer RTT  mean 503.7 µs   mean cycle jitter 36.1 µs
  Observer intrusion   mean 80.1 µs   p95 110.3 µs   max 1.20 ms
                       error 18.9 % (total lag / total RTT)   per packet: median 16.9 %  mean 21.5 %  max 354.9 %
  Event-loop canary    avg 1.19 ms   p95 1.57 ms   max 6.24 ms
```

## 20261024-162319_go-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 16:26:50
- **Description:** sem 30 · Go multi-core
- **Command:** `dashboard run: engine=go cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-162319_go-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-162319_go-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-162319_go-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=684)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 639.8 µs   p95 1.22 ms   max 7.35 ms
  Kernel Control RTT   mean 449.7 µs   mean cycle jitter 35.4 µs
  Python Observer RTT  mean 519.5 µs   mean cycle jitter 37.5 µs
  Observer intrusion   mean 69.9 µs   p95 109.6 µs   max 577.3 µs
                       error 15.5 % (total lag / total RTT)   per packet: median 15.1 %  mean 17.5 %  max 162.3 %
  Event-loop canary    avg 323.0 µs   p95 709.0 µs   max 5.07 ms
```

## 20261024-162650_go-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 16:30:22
- **Description:** sem 30 · Go multi-core
- **Command:** `dashboard run: engine=go cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-162650_go-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-162650_go-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-162650_go-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=684)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 617.8 µs   p95 1.13 ms   max 2.41 ms
  Kernel Control RTT   mean 454.0 µs   mean cycle jitter 33.9 µs
  Python Observer RTT  mean 526.2 µs   mean cycle jitter 37.1 µs
  Observer intrusion   mean 72.2 µs   p95 107.9 µs   max 2.39 ms
                       error 15.9 % (total lag / total RTT)   per packet: median 15.3 %  mean 17.5 %  max 634.8 %
  Event-loop canary    avg 329.4 µs   p95 735.1 µs   max 6.29 ms
```

## 20261024-163022_go-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 16:33:54
- **Description:** sem 30 · Go multi-core
- **Command:** `dashboard run: engine=go cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-163022_go-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-163022_go-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-163022_go-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=683)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 634.6 µs   p95 1.24 ms   max 3.25 ms
  Kernel Control RTT   mean 456.6 µs   mean cycle jitter 36.8 µs
  Python Observer RTT  mean 526.4 µs   mean cycle jitter 39.3 µs
  Observer intrusion   mean 69.7 µs   p95 110.1 µs   max 601.9 µs
                       error 15.3 % (total lag / total RTT)   per packet: median 14.6 %  mean 17.0 %  max 162.1 %
  Event-loop canary    avg 333.5 µs   p95 753.2 µs   max 2.90 ms
```

## 20261024-164956_go-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 16:53:27
- **Description:** sem 50 · Go multi-core
- **Command:** `dashboard run: engine=go cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-164956_go-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-164956_go-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-164956_go-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=685)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 720.5 µs   p95 1.11 ms   max 4.72 ms
  Kernel Control RTT   mean 435.5 µs   mean cycle jitter 32.9 µs
  Python Observer RTT  mean 502.5 µs   mean cycle jitter 34.9 µs
  Observer intrusion   mean 67.1 µs   p95 104.8 µs   max 854.1 µs
                       error 15.4 % (total lag / total RTT)   per packet: median 15.0 %  mean 17.4 %  max 228.6 %
  Event-loop canary    avg 327.3 µs   p95 765.9 µs   max 6.51 ms
```

## 20261024-165327_go-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 16:56:59
- **Description:** sem 50 · Go multi-core
- **Command:** `dashboard run: engine=go cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-165327_go-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-165327_go-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-165327_go-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=684)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 669.7 µs   p95 1.12 ms   max 2.05 ms
  Kernel Control RTT   mean 433.3 µs   mean cycle jitter 30.9 µs
  Python Observer RTT  mean 499.8 µs   mean cycle jitter 32.7 µs
  Observer intrusion   mean 66.5 µs   p95 104.2 µs   max 400.1 µs
                       error 15.3 % (total lag / total RTT)   per packet: median 14.8 %  mean 17.3 %  max 250.4 %
  Event-loop canary    avg 322.8 µs   p95 764.0 µs   max 6.39 ms
```

## 20261024-165659_go-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 17:00:31
- **Description:** sem 50 · Go multi-core
- **Command:** `dashboard run: engine=go cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-165659_go-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-165659_go-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-165659_go-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=684)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 647.1 µs   p95 1.13 ms   max 3.53 ms
  Kernel Control RTT   mean 425.6 µs   mean cycle jitter 28.4 µs
  Python Observer RTT  mean 495.2 µs   mean cycle jitter 30.9 µs
  Observer intrusion   mean 69.6 µs   p95 106.5 µs   max 1.44 ms
                       error 16.3 % (total lag / total RTT)   per packet: median 16.4 %  mean 18.3 %  max 462.8 %
  Event-loop canary    avg 307.2 µs   p95 735.2 µs   max 3.69 ms
```

## 20261024-170054_rs-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 17:04:26
- **Description:** sem 50 · Rust multi-core
- **Command:** `dashboard run: engine=rust cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-170054_rs-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-170054_rs-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-170054_rs-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.23 ms   p95 1.67 ms   max 3.38 ms
  Kernel Control RTT   mean 453.1 µs   mean cycle jitter 36.2 µs
  Python Observer RTT  mean 525.7 µs   mean cycle jitter 39.8 µs
  Observer intrusion   mean 72.6 µs   p95 104.9 µs   max 2.55 ms
                       error 16.0 % (total lag / total RTT)   per packet: median 14.2 %  mean 18.3 %  max 767.0 %
  Event-loop canary    avg 1.18 ms   p95 1.55 ms   max 6.97 ms
```

## 20261024-170426_rs-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 17:07:58
- **Description:** sem 50 · Rust multi-core
- **Command:** `dashboard run: engine=rust cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-170426_rs-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-170426_rs-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-170426_rs-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=684)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.54 ms   p95 2.10 ms   max 5.15 ms
  Kernel Control RTT   mean 468.3 µs   mean cycle jitter 34.6 µs
  Python Observer RTT  mean 544.8 µs   mean cycle jitter 40.2 µs
  Observer intrusion   mean 76.5 µs   p95 107.0 µs   max 3.13 ms
                       error 16.3 % (total lag / total RTT)   per packet: median 14.1 %  mean 20.3 %  max 1967.7 %
  Event-loop canary    avg 1.18 ms   p95 1.51 ms   max 7.34 ms
```

## 20261024-170758_rs-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 17:11:29
- **Description:** sem 50 · Rust multi-core
- **Command:** `dashboard run: engine=rust cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-170758_rs-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-170758_rs-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-170758_rs-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=681)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.61 ms   p95 2.10 ms   max 6.42 ms
  Kernel Control RTT   mean 453.1 µs   mean cycle jitter 34.9 µs
  Python Observer RTT  mean 521.3 µs   mean cycle jitter 37.5 µs
  Observer intrusion   mean 68.2 µs   p95 105.2 µs   max 940.5 µs
                       error 15.1 % (total lag / total RTT)   per packet: median 14.2 %  mean 16.8 %  max 282.2 %
  Event-loop canary    avg 1.18 ms   p95 1.53 ms   max 7.00 ms
```

## 20261024-171356_rs-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 17:17:28
- **Description:** sem 30 · Rust multi-core
- **Command:** `dashboard run: engine=rust cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-171356_rs-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-171356_rs-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-171356_rs-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=681)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.51 ms   p95 2.03 ms   max 2.90 ms
  Kernel Control RTT   mean 461.0 µs   mean cycle jitter 33.8 µs
  Python Observer RTT  mean 530.7 µs   mean cycle jitter 37.8 µs
  Observer intrusion   mean 69.7 µs   p95 105.2 µs   max 3.11 ms
                       error 15.1 % (total lag / total RTT)   per packet: median 14.0 %  mean 17.5 %  max 1195.1 %
  Event-loop canary    avg 1.17 ms   p95 1.53 ms   max 6.29 ms
```

## 20261024-171728_rs-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 17:20:59
- **Description:** sem 30 · Rust multi-core
- **Command:** `dashboard run: engine=rust cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-171728_rs-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-171728_rs-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-171728_rs-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=682)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.48 ms   p95 2.01 ms   max 5.98 ms
  Kernel Control RTT   mean 450.4 µs   mean cycle jitter 32.9 µs
  Python Observer RTT  mean 522.1 µs   mean cycle jitter 37.1 µs
  Observer intrusion   mean 71.7 µs   p95 103.8 µs   max 3.13 ms
                       error 15.9 % (total lag / total RTT)   per packet: median 14.1 %  mean 18.8 %  max 1346.1 %
  Event-loop canary    avg 1.18 ms   p95 1.55 ms   max 7.00 ms
```

## 20261024-172059_rs-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 17:24:31
- **Description:** sem 30 · Rust multi-core
- **Command:** `dashboard run: engine=rust cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-172059_rs-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-172059_rs-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-172059_rs-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=683)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.52 ms   p95 2.02 ms   max 3.84 ms
  Kernel Control RTT   mean 448.1 µs   mean cycle jitter 33.8 µs
  Python Observer RTT  mean 520.4 µs   mean cycle jitter 39.0 µs
  Observer intrusion   mean 72.3 µs   p95 101.9 µs   max 3.16 ms
                       error 16.1 % (total lag / total RTT)   per packet: median 13.7 %  mean 18.4 %  max 842.1 %
  Event-loop canary    avg 1.17 ms   p95 1.54 ms   max 6.07 ms
```

## 20261024-172501_py-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 17:28:34
- **Description:** sem 30 · Python multi-core
- **Command:** `dashboard run: engine=python cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-172501_py-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-172501_py-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-172501_py-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=693)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 858.6 µs   p95 1.83 ms   max 3.33 ms
  Kernel Control RTT   mean 450.0 µs   mean cycle jitter 37.0 µs
  Python Observer RTT  mean 559.3 µs   mean cycle jitter 40.6 µs
  Observer intrusion   mean 109.3 µs   p95 169.3 µs   max 1.72 ms
                       error 24.3 % (total lag / total RTT)   per packet: median 23.3 %  mean 27.3 %  max 468.3 %
  Event-loop canary    avg 312.6 µs   p95 671.0 µs   max 4.89 ms
```

## 20261024-172834_py-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 17:32:07
- **Description:** sem 30 · Python multi-core
- **Command:** `dashboard run: engine=python cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-172834_py-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-172834_py-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-172834_py-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=693)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 834.9 µs   p95 1.80 ms   max 3.45 ms
  Kernel Control RTT   mean 418.1 µs   mean cycle jitter 31.8 µs
  Python Observer RTT  mean 520.0 µs   mean cycle jitter 35.1 µs
  Observer intrusion   mean 102.0 µs   p95 160.0 µs   max 555.3 µs
                       error 24.4 % (total lag / total RTT)   per packet: median 23.4 %  mean 27.0 %  max 168.6 %
  Event-loop canary    avg 276.5 µs   p95 640.5 µs   max 5.59 ms
```

## 20261024-173207_py-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 17:35:39
- **Description:** sem 30 · Python multi-core
- **Command:** `dashboard run: engine=python cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=30 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-173207_py-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-173207_py-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-173207_py-mc_100ep-stg60-sem30-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=692)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 886.5 µs   p95 1.82 ms   max 2.75 ms
  Kernel Control RTT   mean 429.7 µs   mean cycle jitter 33.6 µs
  Python Observer RTT  mean 536.1 µs   mean cycle jitter 38.7 µs
  Observer intrusion   mean 106.5 µs   p95 170.8 µs   max 989.0 µs
                       error 24.8 % (total lag / total RTT)   per packet: median 23.6 %  mean 27.2 %  max 259.7 %
  Event-loop canary    avg 275.1 µs   p95 661.1 µs   max 4.93 ms
```

## 20261024-180531_py-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 18:09:03
- **Description:** sem 50 · Python multi-core
- **Command:** `dashboard run: engine=python cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-180531_py-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-180531_py-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-180531_py-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=692)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 809.3 µs   p95 1.82 ms   max 3.28 ms
  Kernel Control RTT   mean 407.0 µs   mean cycle jitter 28.5 µs
  Python Observer RTT  mean 513.2 µs   mean cycle jitter 31.6 µs
  Observer intrusion   mean 106.2 µs   p95 166.1 µs   max 695.5 µs
                       error 26.1 % (total lag / total RTT)   per packet: median 24.4 %  mean 29.0 %  max 646.4 %
  Event-loop canary    avg 260.7 µs   p95 652.5 µs   max 6.00 ms
```

## 20261024-180903_py-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 18:12:36
- **Description:** sem 50 · Python multi-core
- **Command:** `dashboard run: engine=python cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-180903_py-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-180903_py-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-180903_py-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=689)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 816.9 µs   p95 1.73 ms   max 4.27 ms
  Kernel Control RTT   mean 392.5 µs   mean cycle jitter 26.5 µs
  Python Observer RTT  mean 503.6 µs   mean cycle jitter 30.4 µs
  Observer intrusion   mean 111.1 µs   p95 163.9 µs   max 1.04 ms
                       error 28.3 % (total lag / total RTT)   per packet: median 25.6 %  mean 31.2 %  max 334.8 %
  Event-loop canary    avg 252.1 µs   p95 650.4 µs   max 3.88 ms
```

## 20261024-181236_py-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 18:16:09
- **Description:** sem 50 · Python multi-core
- **Command:** `dashboard run: engine=python cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-181236_py-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-181236_py-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-181236_py-mc_100ep-stg60-sem50-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=687)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 774.1 µs   p95 1.67 ms   max 2.58 ms
  Kernel Control RTT   mean 382.6 µs   mean cycle jitter 24.9 µs
  Python Observer RTT  mean 492.4 µs   mean cycle jitter 28.2 µs
  Observer intrusion   mean 109.7 µs   p95 166.1 µs   max 924.0 µs
                       error 28.7 % (total lag / total RTT)   per packet: median 26.0 %  mean 32.2 %  max 474.2 %
  Event-loop canary    avg 254.1 µs   p95 651.0 µs   max 7.29 ms
```

## 20261024-181946_py-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 18:23:19
- **Description:** sem 5 · Python multi-core
- **Command:** `dashboard run: engine=python cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-181946_py-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-181946_py-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-181946_py-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=687)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 829.8 µs   p95 1.71 ms   max 2.68 ms
  Kernel Control RTT   mean 442.7 µs   mean cycle jitter 35.9 µs
  Python Observer RTT  mean 561.5 µs   mean cycle jitter 42.7 µs
  Observer intrusion   mean 118.8 µs   p95 182.8 µs   max 3.17 ms
                       error 26.8 % (total lag / total RTT)   per packet: median 23.6 %  mean 31.0 %  max 1218.5 %
  Event-loop canary    avg 316.8 µs   p95 751.4 µs   max 6.35 ms
```

## 20261024-182319_py-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 18:26:52
- **Description:** sem 5 · Python multi-core
- **Command:** `dashboard run: engine=python cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-182319_py-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-182319_py-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-182319_py-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=689)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 890.9 µs   p95 1.88 ms   max 3.76 ms
  Kernel Control RTT   mean 447.2 µs   mean cycle jitter 36.5 µs
  Python Observer RTT  mean 564.2 µs   mean cycle jitter 43.1 µs
  Observer intrusion   mean 117.0 µs   p95 169.2 µs   max 3.61 ms
                       error 26.2 % (total lag / total RTT)   per packet: median 22.3 %  mean 34.7 %  max 4616.4 %
  Event-loop canary    avg 313.8 µs   p95 796.4 µs   max 6.74 ms
```

## 20261024-182652_py-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 18:30:24
- **Description:** sem 5 · Python multi-core
- **Command:** `dashboard run: engine=python cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-182652_py-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-182652_py-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-182652_py-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=687)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 821.3 µs   p95 1.71 ms   max 2.64 ms
  Kernel Control RTT   mean 442.0 µs   mean cycle jitter 37.3 µs
  Python Observer RTT  mean 552.4 µs   mean cycle jitter 41.3 µs
  Observer intrusion   mean 110.4 µs   p95 172.4 µs   max 2.54 ms
                       error 25.0 % (total lag / total RTT)   per packet: median 23.2 %  mean 28.8 %  max 639.1 %
  Event-loop canary    avg 309.9 µs   p95 774.0 µs   max 5.91 ms
```

## 20261024-183658_go-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 18:40:29
- **Description:** sem 5 · Go multi-core
- **Command:** `dashboard run: engine=go cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-183658_go-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-183658_go-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-183658_go-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 647.2 µs   p95 1.09 ms   max 3.14 ms
  Kernel Control RTT   mean 422.8 µs   mean cycle jitter 28.2 µs
  Python Observer RTT  mean 484.2 µs   mean cycle jitter 28.9 µs
  Observer intrusion   mean 61.4 µs   p95 90.9 µs   max 141.3 µs
                       error 14.5 % (total lag / total RTT)   per packet: median 13.8 %  mean 16.2 %  max 130.1 %
  Event-loop canary    avg 293.6 µs   p95 698.2 µs   max 4.73 ms
```

## 20261024-184029_go-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 18:44:01
- **Description:** sem 5 · Go multi-core
- **Command:** `dashboard run: engine=go cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-184029_go-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-184029_go-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-184029_go-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=684)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 671.5 µs   p95 1.09 ms   max 1.82 ms
  Kernel Control RTT   mean 460.9 µs   mean cycle jitter 34.5 µs
  Python Observer RTT  mean 531.7 µs   mean cycle jitter 37.3 µs
  Observer intrusion   mean 70.8 µs   p95 97.5 µs   max 2.19 ms
                       error 15.4 % (total lag / total RTT)   per packet: median 14.4 %  mean 17.1 %  max 588.2 %
  Event-loop canary    avg 329.2 µs   p95 727.3 µs   max 5.59 ms
```

## 20261024-184401_go-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 18:47:32
- **Description:** sem 5 · Go multi-core
- **Command:** `dashboard run: engine=go cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-184401_go-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-184401_go-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-184401_go-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=683)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 681.0 µs   p95 1.11 ms   max 4.75 ms
  Kernel Control RTT   mean 436.8 µs   mean cycle jitter 31.9 µs
  Python Observer RTT  mean 505.4 µs   mean cycle jitter 34.7 µs
  Observer intrusion   mean 68.6 µs   p95 94.6 µs   max 2.04 ms
                       error 15.7 % (total lag / total RTT)   per packet: median 14.3 %  mean 17.7 %  max 593.6 %
  Event-loop canary    avg 300.4 µs   p95 689.1 µs   max 6.66 ms
```

## 20261024-185740_rs-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 19:01:11
- **Description:** sem 5 · Rust multi-core
- **Command:** `dashboard run: engine=rust cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-185740_rs-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-185740_rs-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-185740_rs-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 997.2 µs   p95 1.45 ms   max 4.79 ms
  Kernel Control RTT   mean 437.8 µs   mean cycle jitter 32.2 µs
  Python Observer RTT  mean 502.6 µs   mean cycle jitter 35.0 µs
  Observer intrusion   mean 64.8 µs   p95 93.4 µs   max 1.20 ms
                       error 14.8 % (total lag / total RTT)   per packet: median 13.7 %  mean 17.3 %  max 704.1 %
  Event-loop canary    avg 1.17 ms   p95 1.48 ms   max 7.68 ms
```

## 20261024-190111_rs-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 19:04:43
- **Description:** sem 5 · Rust multi-core
- **Command:** `dashboard run: engine=rust cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-190111_rs-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-190111_rs-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-190111_rs-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=682)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.45 ms   p95 1.96 ms   max 2.29 ms
  Kernel Control RTT   mean 443.9 µs   mean cycle jitter 31.7 µs
  Python Observer RTT  mean 514.1 µs   mean cycle jitter 36.4 µs
  Observer intrusion   mean 70.3 µs   p95 94.3 µs   max 3.11 ms
                       error 15.8 % (total lag / total RTT)   per packet: median 13.7 %  mean 19.5 %  max 2359.3 %
  Event-loop canary    avg 1.16 ms   p95 1.49 ms   max 5.80 ms
```

## 20261024-190443_rs-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep

- **Date:** 2026-10-24 19:08:15
- **Description:** sem 5 · Rust multi-core
- **Command:** `dashboard run: engine=rust cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261024-190443_rs-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.csv` (per packet), `20261024-190443_rs-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep_cycles.csv` (per cycle), `20261024-190443_rs-mc_100ep-stg60-sem5-db3-i8-c3x60_192-168-70-2_sem-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.48 ms   p95 1.94 ms   max 5.25 ms
  Kernel Control RTT   mean 441.4 µs   mean cycle jitter 33.9 µs
  Python Observer RTT  mean 504.6 µs   mean cycle jitter 35.1 µs
  Observer intrusion   mean 63.2 µs   p95 93.8 µs   max 168.9 µs
                       error 14.3 % (total lag / total RTT)   per packet: median 13.9 %  mean 16.2 %  max 95.1 %
  Event-loop canary    avg 1.17 ms   p95 1.48 ms   max 4.99 ms
```

## 20261025-084054_py-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 08:44:26
- **Description:** 100 endpoints · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-084054_py-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-084054_py-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-084054_py-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=689)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 895.5 µs   p95 1.78 ms   max 3.48 ms
  Kernel Control RTT   mean 432.4 µs   mean cycle jitter 36.0 µs
  Python Observer RTT  mean 554.7 µs   mean cycle jitter 44.0 µs
  Observer intrusion   mean 122.3 µs   p95 180.6 µs   max 2.91 ms
                       error 28.3 % (total lag / total RTT)   per packet: median 23.4 %  mean 33.7 %  max 1362.0 %
  Event-loop canary    avg 327.6 µs   p95 896.6 µs   max 8.73 ms
```

## 20261025-084426_go-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 08:47:57
- **Description:** 100 endpoints · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-084426_go-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-084426_go-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-084426_go-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 649.6 µs   p95 1.09 ms   max 3.21 ms
  Kernel Control RTT   mean 422.5 µs   mean cycle jitter 29.7 µs
  Python Observer RTT  mean 503.8 µs   mean cycle jitter 35.0 µs
  Observer intrusion   mean 81.3 µs   p95 115.5 µs   max 3.13 ms
                       error 19.2 % (total lag / total RTT)   per packet: median 16.8 %  mean 21.8 %  max 853.0 %
  Event-loop canary    avg 298.0 µs   p95 737.2 µs   max 7.51 ms
```

## 20261025-084757_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 08:51:29
- **Description:** 100 endpoints · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-084757_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-084757_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-084757_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 876.3 µs   p95 1.49 ms   max 3.41 ms
  Kernel Control RTT   mean 416.0 µs   mean cycle jitter 27.2 µs
  Python Observer RTT  mean 506.0 µs   mean cycle jitter 36.9 µs
  Observer intrusion   mean 90.0 µs   p95 145.6 µs   max 2.00 ms
                       error 21.6 % (total lag / total RTT)   per packet: median 16.4 %  mean 24.7 %  max 617.7 %
  Event-loop canary    avg 1.16 ms   p95 1.50 ms   max 6.20 ms
```

## 20261025-085129_go-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 08:55:00
- **Description:** 100 endpoints · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-085129_go-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-085129_go-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-085129_go-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=683)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 619.3 µs   p95 1.22 ms   max 3.16 ms
  Kernel Control RTT   mean 451.9 µs   mean cycle jitter 35.0 µs
  Python Observer RTT  mean 547.4 µs   mean cycle jitter 42.7 µs
  Observer intrusion   mean 95.5 µs   p95 188.9 µs   max 3.17 ms
                       error 21.1 % (total lag / total RTT)   per packet: median 16.1 %  mean 25.3 %  max 844.7 %
  Event-loop canary    avg 365.5 µs   p95 848.0 µs   max 8.31 ms
```

## 20261025-085500_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 08:58:32
- **Description:** 100 endpoints · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-085500_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-085500_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-085500_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 910.9 µs   p95 1.41 ms   max 4.22 ms
  Kernel Control RTT   mean 430.1 µs   mean cycle jitter 29.7 µs
  Python Observer RTT  mean 532.6 µs   mean cycle jitter 43.0 µs
  Observer intrusion   mean 102.5 µs   p95 135.8 µs   max 3.80 ms
                       error 23.8 % (total lag / total RTT)   per packet: median 17.0 %  mean 28.7 %  max 1384.0 %
  Event-loop canary    avg 1.19 ms   p95 1.60 ms   max 7.34 ms
```

## 20261025-085832_py-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 09:02:04
- **Description:** 100 endpoints · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-085832_py-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-085832_py-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-085832_py-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=692)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 919.7 µs   p95 1.91 ms   max 3.54 ms
  Kernel Control RTT   mean 457.0 µs   mean cycle jitter 36.4 µs
  Python Observer RTT  mean 576.9 µs   mean cycle jitter 43.7 µs
  Observer intrusion   mean 119.9 µs   p95 193.9 µs   max 2.40 ms
                       error 26.2 % (total lag / total RTT)   per packet: median 23.4 %  mean 30.0 %  max 792.6 %
  Event-loop canary    avg 338.8 µs   p95 833.0 µs   max 7.79 ms
```

## 20261025-092537_py-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 09:29:07
- **Description:** 25 endpoints · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-092537_py-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-092537_py-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-092537_py-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=173)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 894.1 µs   p95 1.87 ms   max 2.27 ms
  Kernel Control RTT   mean 439.6 µs   mean cycle jitter 36.8 µs
  Python Observer RTT  mean 553.2 µs   mean cycle jitter 45.8 µs
  Observer intrusion   mean 113.6 µs   p95 165.7 µs   max 1.67 ms
                       error 25.8 % (total lag / total RTT)   per packet: median 22.4 %  mean 29.9 %  max 617.0 %
  Event-loop canary    avg 286.5 µs   p95 523.5 µs   max 6.88 ms
```

## 20261025-092907_go-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 09:32:36
- **Description:** 25 endpoints · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-092907_go-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-092907_go-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-092907_go-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=171)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 688.2 µs   p95 1.13 ms   max 2.70 ms
  Kernel Control RTT   mean 436.1 µs   mean cycle jitter 31.7 µs
  Python Observer RTT  mean 529.2 µs   mean cycle jitter 39.8 µs
  Observer intrusion   mean 93.1 µs   p95 204.6 µs   max 767.2 µs
                       error 21.4 % (total lag / total RTT)   per packet: median 17.2 %  mean 24.5 %  max 194.7 %
  Event-loop canary    avg 304.6 µs   p95 651.0 µs   max 7.82 ms
```

## 20261025-093236_rs-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 09:36:06
- **Description:** 25 endpoints · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-093236_rs-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-093236_rs-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-093236_rs-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=170)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 824.9 µs   p95 1.31 ms   max 1.66 ms
  Kernel Control RTT   mean 444.2 µs   mean cycle jitter 27.7 µs
  Python Observer RTT  mean 525.7 µs   mean cycle jitter 34.7 µs
  Observer intrusion   mean 81.5 µs   p95 135.9 µs   max 842.9 µs
                       error 18.4 % (total lag / total RTT)   per packet: median 16.5 %  mean 20.1 %  max 201.4 %
  Event-loop canary    avg 1.19 ms   p95 1.52 ms   max 6.65 ms
```

## 20261025-093606_go-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 09:39:36
- **Description:** 25 endpoints · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-093606_go-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-093606_go-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-093606_go-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=170)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 634.4 µs   p95 1.17 ms   max 1.33 ms
  Kernel Control RTT   mean 401.9 µs   mean cycle jitter 26.8 µs
  Python Observer RTT  mean 483.2 µs   mean cycle jitter 30.0 µs
  Observer intrusion   mean 81.3 µs   p95 130.0 µs   max 628.7 µs
                       error 20.2 % (total lag / total RTT)   per packet: median 18.6 %  mean 24.6 %  max 555.2 %
  Event-loop canary    avg 286.7 µs   p95 624.9 µs   max 6.56 ms
```

## 20261025-093936_rs-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 09:43:06
- **Description:** 25 endpoints · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-093936_rs-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-093936_rs-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-093936_rs-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=171)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.12 ms   p95 1.53 ms   max 3.52 ms
  Kernel Control RTT   mean 419.7 µs   mean cycle jitter 22.7 µs
  Python Observer RTT  mean 513.9 µs   mean cycle jitter 33.1 µs
  Observer intrusion   mean 94.2 µs   p95 218.0 µs   max 1.69 ms
                       error 22.4 % (total lag / total RTT)   per packet: median 17.4 %  mean 26.2 %  max 423.0 %
  Event-loop canary    avg 1.17 ms   p95 1.51 ms   max 7.41 ms
```

## 20261025-094306_py-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 09:46:36
- **Description:** 25 endpoints · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-094306_py-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-094306_py-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-094306_py-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=172)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 863.0 µs   p95 2.04 ms   max 2.29 ms
  Kernel Control RTT   mean 443.4 µs   mean cycle jitter 28.5 µs
  Python Observer RTT  mean 556.7 µs   mean cycle jitter 35.2 µs
  Observer intrusion   mean 113.3 µs   p95 177.7 µs   max 802.7 µs
                       error 25.6 % (total lag / total RTT)   per packet: median 23.4 %  mean 29.1 %  max 331.8 %
  Event-loop canary    avg 286.6 µs   p95 506.2 µs   max 7.33 ms
```

## 20261025-094719_py-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 09:50:52
- **Description:** 250 endpoints · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-094719_py-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-094719_py-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-094719_py-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1720)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 862.0 µs   p95 1.78 ms   max 4.34 ms
  Kernel Control RTT   mean 473.3 µs   mean cycle jitter 38.6 µs
  Python Observer RTT  mean 593.0 µs   mean cycle jitter 43.8 µs
  Observer intrusion   mean 119.7 µs   p95 180.2 µs   max 3.89 ms
                       error 25.3 % (total lag / total RTT)   per packet: median 23.6 %  mean 29.4 %  max 2960.8 %
  Event-loop canary    avg 415.4 µs   p95 1.29 ms   max 4.75 ms
```

## 20261025-095052_go-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 09:54:24
- **Description:** 250 endpoints · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-095052_go-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-095052_go-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-095052_go-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1704)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 574.5 µs   p95 1.07 ms   max 3.90 ms
  Kernel Control RTT   mean 411.3 µs   mean cycle jitter 29.8 µs
  Python Observer RTT  mean 495.9 µs   mean cycle jitter 39.5 µs
  Observer intrusion   mean 84.6 µs   p95 135.9 µs   max 3.31 ms
                       error 20.6 % (total lag / total RTT)   per packet: median 14.5 %  mean 22.6 %  max 876.6 %
  Event-loop canary    avg 317.5 µs   p95 871.2 µs   max 7.93 ms
```

## 20261025-095424_rs-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 09:57:56
- **Description:** 250 endpoints · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-095424_rs-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-095424_rs-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-095424_rs-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1700)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 731.6 µs   p95 1.16 ms   max 4.53 ms
  Kernel Control RTT   mean 430.7 µs   mean cycle jitter 33.5 µs
  Python Observer RTT  mean 515.0 µs   mean cycle jitter 40.9 µs
  Observer intrusion   mean 84.3 µs   p95 121.8 µs   max 3.20 ms
                       error 19.6 % (total lag / total RTT)   per packet: median 16.5 %  mean 22.4 %  max 923.9 %
  Event-loop canary    avg 1.17 ms   p95 1.64 ms   max 6.69 ms
```

## 20261025-095756_go-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 10:01:28
- **Description:** 250 endpoints · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-095756_go-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-095756_go-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-095756_go-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1705)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 599.1 µs   p95 1.03 ms   max 3.55 ms
  Kernel Control RTT   mean 398.6 µs   mean cycle jitter 25.1 µs
  Python Observer RTT  mean 488.2 µs   mean cycle jitter 39.8 µs
  Observer intrusion   mean 89.6 µs   p95 195.8 µs   max 3.30 ms
                       error 22.5 % (total lag / total RTT)   per packet: median 13.1 %  mean 29.0 %  max 3740.4 %
  Event-loop canary    avg 314.4 µs   p95 845.8 µs   max 5.94 ms
```

## 20261025-100128_rs-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 10:05:00
- **Description:** 250 endpoints · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-100128_rs-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-100128_rs-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-100128_rs-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1701)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 906.7 µs   p95 1.44 ms   max 4.24 ms
  Kernel Control RTT   mean 432.2 µs   mean cycle jitter 32.4 µs
  Python Observer RTT  mean 507.7 µs   mean cycle jitter 36.8 µs
  Observer intrusion   mean 75.5 µs   p95 105.5 µs   max 1.18 ms
                       error 17.5 % (total lag / total RTT)   per packet: median 16.8 %  mean 19.9 %  max 713.6 %
  Event-loop canary    avg 1.17 ms   p95 1.65 ms   max 6.01 ms
```

## 20261025-100500_py-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 10:08:32
- **Description:** 250 endpoints · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-100500_py-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-100500_py-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-100500_py-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1721)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 833.1 µs   p95 1.66 ms   max 4.22 ms
  Kernel Control RTT   mean 403.6 µs   mean cycle jitter 30.7 µs
  Python Observer RTT  mean 547.7 µs   mean cycle jitter 39.5 µs
  Observer intrusion   mean 144.1 µs   p95 227.4 µs   max 3.53 ms
                       error 35.7 % (total lag / total RTT)   per packet: median 29.3 %  mean 40.6 %  max 1083.3 %
  Event-loop canary    avg 403.0 µs   p95 1.45 ms   max 7.48 ms
```

## 20261025-103459_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst

- **Date:** 2026-10-25 10:37:31
- **Description:** Burst, no stagger · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-103459_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst.csv` (per packet), `20261025-103459_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst_cycles.csv` (per cycle), `20261025-103459_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 3.42 ms   p95 6.48 ms   max 8.51 ms
  Kernel Control RTT   mean 158.3 µs   mean cycle jitter 16.1 µs
  Python Observer RTT  mean 2.93 ms   mean cycle jitter 560.7 µs
  Observer intrusion   mean 2.77 ms   p95 6.98 ms   max 9.46 ms
                       error 1749.4 % (total lag / total RTT)   per packet: median 1485.8 %  mean 1979.6 %  max 12405.6 %
  Event-loop canary    avg 406.2 µs   p95 562.8 µs   max 162.12 ms
```

## 20261025-103731_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst

- **Date:** 2026-10-25 10:40:04
- **Description:** Burst, no stagger · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-103731_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst.csv` (per packet), `20261025-103731_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst_cycles.csv` (per cycle), `20261025-103731_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=60)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.28 ms   p95 1.93 ms   max 2.09 ms
  Kernel Control RTT   mean 618.8 µs   mean cycle jitter 45.7 µs
  Python Observer RTT  mean 10.30 ms   mean cycle jitter 2.97 ms
  Observer intrusion   mean 9.68 ms   p95 43.52 ms   max 204.32 ms
                       error 1564.6 % (total lag / total RTT)   per packet: median 52.6 %  mean 1347.1 %  max 32914.5 %
  Event-loop canary    avg 331.7 µs   p95 645.0 µs   max 281.17 ms
```

## 20261025-104004_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst

- **Date:** 2026-10-25 10:42:36
- **Description:** Burst, no stagger · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-104004_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst.csv` (per packet), `20261025-104004_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst_cycles.csv` (per cycle), `20261025-104004_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=73)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.45 ms   p95 2.03 ms   max 2.16 ms
  Kernel Control RTT   mean 738.6 µs   mean cycle jitter 48.2 µs
  Python Observer RTT  mean 7.77 ms   mean cycle jitter 2.18 ms
  Observer intrusion   mean 7.03 ms   p95 47.67 ms   max 48.05 ms
                       error 951.5 % (total lag / total RTT)   per packet: median 19.3 %  mean 769.0 %  max 7760.7 %
  Event-loop canary    avg 1.22 ms   p95 1.43 ms   max 48.35 ms
```

## 20261025-104236_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst

- **Date:** 2026-10-25 10:45:09
- **Description:** Burst, no stagger · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-104236_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst.csv` (per packet), `20261025-104236_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst_cycles.csv` (per cycle), `20261025-104236_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=46)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.45 ms   p95 2.31 ms   max 2.81 ms
  Kernel Control RTT   mean 570.6 µs   mean cycle jitter 53.4 µs
  Python Observer RTT  mean 16.94 ms   mean cycle jitter 5.06 ms
  Observer intrusion   mean 16.37 ms   p95 125.18 ms   max 212.13 ms
                       error 2868.3 % (total lag / total RTT)   per packet: median 75.7 %  mean 2288.5 %  max 41515.0 %
  Event-loop canary    avg 283.9 µs   p95 618.9 µs   max 165.11 ms
```

## 20261025-104509_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst

- **Date:** 2026-10-25 10:47:41
- **Description:** Burst, no stagger · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-104509_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst.csv` (per packet), `20261025-104509_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst_cycles.csv` (per cycle), `20261025-104509_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=71)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.24 ms   p95 1.88 ms   max 2.11 ms
  Kernel Control RTT   mean 644.4 µs   mean cycle jitter 88.5 µs
  Python Observer RTT  mean 7.39 ms   mean cycle jitter 2.12 ms
  Observer intrusion   mean 6.74 ms   p95 49.13 ms   max 49.90 ms
                       error 1046.1 % (total lag / total RTT)   per packet: median 39.4 %  mean 841.6 %  max 8208.5 %
  Event-loop canary    avg 1.21 ms   p95 1.42 ms   max 50.31 ms
```

## 20261025-104741_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst

- **Date:** 2026-10-25 10:50:14
- **Description:** Burst, no stagger · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-104741_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst.csv` (per packet), `20261025-104741_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst_cycles.csv` (per cycle), `20261025-104741_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 3.84 ms   p95 7.40 ms   max 9.80 ms
  Kernel Control RTT   mean 169.3 µs   mean cycle jitter 14.5 µs
  Python Observer RTT  mean 2.70 ms   mean cycle jitter 373.8 µs
  Observer intrusion   mean 2.53 ms   p95 5.28 ms   max 7.62 ms
                       error 1494.5 % (total lag / total RTT)   per packet: median 1361.3 %  mean 1697.6 %  max 7747.1 %
  Event-loop canary    avg 336.7 µs   p95 486.6 µs   max 156.72 ms
```

## 20261025-143322_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 14:35:54
- **Description:** Idle floor, burst · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-143322_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-143322_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-143322_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.14 ms   p95 3.30 ms   max 4.05 ms
  Kernel Control RTT   mean 264.2 µs   mean cycle jitter 23.8 µs
  Python Observer RTT  mean 1.26 ms   mean cycle jitter 138.9 µs
  Observer intrusion   mean 994.6 µs   p95 1.65 ms   max 2.10 ms
                       error 376.5 % (total lag / total RTT)   per packet: median 391.4 %  mean 399.6 %  max 1266.5 %
  Event-loop canary    avg 393.8 µs   p95 614.0 µs   max 59.21 ms
```

## 20261025-143740_go-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 14:40:13
- **Description:** Idle floor, burst · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-143740_go-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-143740_go-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-143740_go-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=136)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.07 ms   p95 2.17 ms   max 2.47 ms
  Kernel Control RTT   mean 788.4 µs   mean cycle jitter 79.2 µs
  Python Observer RTT  mean 1.87 ms   mean cycle jitter 353.4 µs
  Observer intrusion   mean 1.08 ms   p95 5.13 ms   max 13.92 ms
                       error 137.3 % (total lag / total RTT)   per packet: median 9.0 %  mean 155.1 %  max 2695.3 %
  Event-loop canary    avg 358.3 µs   p95 783.7 µs   max 19.46 ms
```

## 20261025-144031_rs-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 14:43:04
- **Description:** Idle floor, burst · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-144031_rs-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-144031_rs-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-144031_rs-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=144)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.13 ms   p95 1.72 ms   max 1.87 ms
  Kernel Control RTT   mean 919.8 µs   mean cycle jitter 10.4 µs
  Python Observer RTT  mean 1.27 ms   mean cycle jitter 98.2 µs
  Observer intrusion   mean 345.8 µs   p95 2.36 ms   max 4.14 ms
                       error 37.6 % (total lag / total RTT)   per packet: median 7.6 %  mean 35.2 %  max 387.4 %
  Event-loop canary    avg 1.21 ms   p95 1.54 ms   max 7.26 ms
```

## 20261025-144313_rs-mc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 14:45:45
- **Description:** Idle floor, burst · Rust multi-core
- **Command:** `dashboard run: engine=rust cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-144313_rs-mc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-144313_rs-mc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-144313_rs-mc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=149)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.73 ms   p95 2.47 ms   max 3.77 ms
  Kernel Control RTT   mean 686.6 µs   mean cycle jitter 66.2 µs
  Python Observer RTT  mean 1.02 ms   mean cycle jitter 117.2 µs
  Observer intrusion   mean 332.9 µs   p95 2.03 ms   max 2.37 ms
                       error 48.5 % (total lag / total RTT)   per packet: median 6.3 %  mean 54.0 %  max 744.5 %
  Event-loop canary    avg 1.17 ms   p95 1.45 ms   max 6.87 ms
```

## 20261025-144613_go-mc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 14:48:45
- **Description:** Idle floor, burst · Go multi-core
- **Command:** `dashboard run: engine=go cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-144613_go-mc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-144613_go-mc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-144613_go-mc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=197)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 940.9 µs   p95 1.57 ms   max 1.90 ms
  Kernel Control RTT   mean 552.0 µs   mean cycle jitter 57.7 µs
  Python Observer RTT  mean 620.7 µs   mean cycle jitter 52.1 µs
  Observer intrusion   mean 68.8 µs   p95 208.7 µs   max 938.5 µs
                       error 12.5 % (total lag / total RTT)   per packet: median 6.2 %  mean 19.7 %  max 523.9 %
  Event-loop canary    avg 291.9 µs   p95 612.8 µs   max 3.04 ms
```

## 20261025-144934_py-mc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 14:52:08
- **Description:** Idle floor, burst · Python multi-core
- **Command:** `dashboard run: engine=python cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-144934_py-mc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-144934_py-mc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-144934_py-mc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.37 ms   p95 4.15 ms   max 5.51 ms
  Kernel Control RTT   mean 223.2 µs   mean cycle jitter 16.7 µs
  Python Observer RTT  mean 1.46 ms   mean cycle jitter 202.4 µs
  Observer intrusion   mean 1.23 ms   p95 2.46 ms   max 3.46 ms
                       error 552.7 % (total lag / total RTT)   per packet: median 503.3 %  mean 645.8 %  max 3516.2 %
  Event-loop canary    avg 280.1 µs   p95 486.3 µs   max 69.09 ms
```

## 20261025-185642_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 18:59:15
- **Description:** Idle floor, burst · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-185642_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-185642_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-185642_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 3.77 ms   p95 6.37 ms   max 7.97 ms
  Kernel Control RTT   mean 154.1 µs   mean cycle jitter 16.2 µs
  Python Observer RTT  mean 2.81 ms   mean cycle jitter 348.4 µs
  Observer intrusion   mean 2.65 ms   p95 4.85 ms   max 5.78 ms
                       error 1721.8 % (total lag / total RTT)   per packet: median 1715.2 %  mean 1961.5 %  max 7112.0 %
  Event-loop canary    avg 392.2 µs   p95 916.4 µs   max 145.22 ms
```

## 20261025-185915_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 19:01:48
- **Description:** Burst sem 15 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-185915_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-185915_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-185915_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 3.62 ms   p95 6.23 ms   max 8.67 ms
  Kernel Control RTT   mean 158.3 µs   mean cycle jitter 14.5 µs
  Python Observer RTT  mean 2.64 ms   mean cycle jitter 384.8 µs
  Observer intrusion   mean 2.48 ms   p95 5.41 ms   max 6.57 ms
                       error 1566.3 % (total lag / total RTT)   per packet: median 1479.3 %  mean 1776.4 %  max 7678.1 %
  Event-loop canary    avg 410.5 µs   p95 589.0 µs   max 178.58 ms
```

## 20261025-191147_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 19:14:20
- **Description:** Idle floor, burst · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-191147_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-191147_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-191147_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.65 ms   p95 4.81 ms   max 6.15 ms
  Kernel Control RTT   mean 202.1 µs   mean cycle jitter 16.7 µs
  Python Observer RTT  mean 1.56 ms   mean cycle jitter 183.7 µs
  Observer intrusion   mean 1.36 ms   p95 3.03 ms   max 3.58 ms
                       error 674.3 % (total lag / total RTT)   per packet: median 550.2 %  mean 914.9 %  max 4638.3 %
  Event-loop canary    avg 298.9 µs   p95 464.0 µs   max 79.87 ms
```

## 20261025-191420_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 19:16:52
- **Description:** Burst sem 15 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-191420_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-191420_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-191420_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.35 ms   p95 4.03 ms   max 5.03 ms
  Kernel Control RTT   mean 225.3 µs   mean cycle jitter 18.5 µs
  Python Observer RTT  mean 1.52 ms   mean cycle jitter 211.2 µs
  Observer intrusion   mean 1.29 ms   p95 2.88 ms   max 3.41 ms
                       error 574.3 % (total lag / total RTT)   per packet: median 485.0 %  mean 695.5 %  max 3725.2 %
  Event-loop canary    avg 352.8 µs   p95 478.1 µs   max 110.06 ms
```

## 20261025-191652_go-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 19:19:25
- **Description:** Idle floor, burst · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-191652_go-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-191652_go-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-191652_go-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=118)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.12 ms   p95 1.76 ms   max 1.90 ms
  Kernel Control RTT   mean 672.3 µs   mean cycle jitter 107.1 µs
  Python Observer RTT  mean 1.16 ms   mean cycle jitter 190.6 µs
  Observer intrusion   mean 485.6 µs   p95 4.21 ms   max 4.97 ms
                       error 72.2 % (total lag / total RTT)   per packet: median 11.0 %  mean 107.4 %  max 894.5 %
  Event-loop canary    avg 312.0 µs   p95 625.0 µs   max 17.99 ms
```

## 20261025-191925_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 19:21:57
- **Description:** Burst sem 15 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-191925_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-191925_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-191925_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=135)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.06 ms   p95 1.53 ms   max 1.70 ms
  Kernel Control RTT   mean 764.1 µs   mean cycle jitter 77.3 µs
  Python Observer RTT  mean 7.11 ms   mean cycle jitter 2.01 ms
  Observer intrusion   mean 6.35 ms   p95 58.36 ms   max 73.37 ms
                       error 830.9 % (total lag / total RTT)   per packet: median 7.9 %  mean 1175.4 %  max 31532.6 %
  Event-loop canary    avg 361.3 µs   p95 611.4 µs   max 328.70 ms
```

## 20261025-192157_rs-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 19:24:29
- **Description:** Idle floor, burst · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-192157_rs-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-192157_rs-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-192157_rs-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=135)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.20 ms   p95 1.72 ms   max 1.92 ms
  Kernel Control RTT   mean 836.4 µs   mean cycle jitter 65.5 µs
  Python Observer RTT  mean 1.21 ms   mean cycle jitter 147.2 µs
  Observer intrusion   mean 370.9 µs   p95 3.33 ms   max 3.95 ms
                       error 44.3 % (total lag / total RTT)   per packet: median 8.9 %  mean 51.1 %  max 443.2 %
  Event-loop canary    avg 1.18 ms   p95 1.43 ms   max 7.29 ms
```

## 20261025-192429_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 19:27:02
- **Description:** Burst sem 15 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-192429_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-192429_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-192429_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=154)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.09 ms   p95 1.64 ms   max 1.81 ms
  Kernel Control RTT   mean 931.7 µs   mean cycle jitter 15.0 µs
  Python Observer RTT  mean 5.40 ms   mean cycle jitter 1.40 ms
  Observer intrusion   mean 4.47 ms   p95 27.18 ms   max 27.85 ms
                       error 479.4 % (total lag / total RTT)   per packet: median 6.9 %  mean 515.1 %  max 5814.4 %
  Event-loop canary    avg 1.23 ms   p95 1.43 ms   max 42.81 ms
```

## 20261025-192702_go-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 19:29:34
- **Description:** Idle floor, burst · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-192702_go-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-192702_go-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-192702_go-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=127)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.09 ms   p95 1.50 ms   max 1.74 ms
  Kernel Control RTT   mean 693.1 µs   mean cycle jitter 98.5 µs
  Python Observer RTT  mean 1.33 ms   mean cycle jitter 232.4 µs
  Observer intrusion   mean 633.1 µs   p95 7.10 ms   max 7.88 ms
                       error 91.3 % (total lag / total RTT)   per packet: median 10.7 %  mean 102.3 %  max 1293.6 %
  Event-loop canary    avg 298.6 µs   p95 614.9 µs   max 21.27 ms
```

## 20261025-192934_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 19:32:06
- **Description:** Burst sem 15 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-192934_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-192934_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-192934_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=106)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.05 ms   p95 1.68 ms   max 1.78 ms
  Kernel Control RTT   mean 771.6 µs   mean cycle jitter 83.7 µs
  Python Observer RTT  mean 9.37 ms   mean cycle jitter 2.72 ms
  Observer intrusion   mean 8.60 ms   p95 52.29 ms   max 53.05 ms
                       error 1114.0 % (total lag / total RTT)   per packet: median 11.1 %  mean 984.2 %  max 9875.9 %
  Event-loop canary    avg 351.3 µs   p95 612.8 µs   max 271.24 ms
```

## 20261025-193206_rs-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 19:34:39
- **Description:** Idle floor, burst · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-193206_rs-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-193206_rs-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-193206_rs-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=147)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.26 ms   p95 1.87 ms   max 2.01 ms
  Kernel Control RTT   mean 894.8 µs   mean cycle jitter 20.8 µs
  Python Observer RTT  mean 1.23 ms   mean cycle jitter 108.0 µs
  Observer intrusion   mean 334.8 µs   p95 2.71 ms   max 4.91 ms
                       error 37.4 % (total lag / total RTT)   per packet: median 7.0 %  mean 35.2 %  max 377.8 %
  Event-loop canary    avg 1.18 ms   p95 1.46 ms   max 7.26 ms
```

## 20261025-193439_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 19:37:11
- **Description:** Burst sem 15 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-193439_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-193439_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-193439_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=121)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.37 ms   p95 1.88 ms   max 2.02 ms
  Kernel Control RTT   mean 755.8 µs   mean cycle jitter 71.0 µs
  Python Observer RTT  mean 5.29 ms   mean cycle jitter 1.45 ms
  Observer intrusion   mean 4.54 ms   p95 24.64 ms   max 25.13 ms
                       error 600.4 % (total lag / total RTT)   per packet: median 11.2 %  mean 553.1 %  max 5323.5 %
  Event-loop canary    avg 1.22 ms   p95 1.41 ms   max 45.65 ms
```

## 20261025-193711_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 19:39:43
- **Description:** Idle floor, burst · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-193711_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-193711_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-193711_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.10 ms   p95 3.14 ms   max 4.20 ms
  Kernel Control RTT   mean 258.4 µs   mean cycle jitter 15.8 µs
  Python Observer RTT  mean 1.29 ms   mean cycle jitter 146.6 µs
  Observer intrusion   mean 1.03 ms   p95 1.78 ms   max 2.16 ms
                       error 399.1 % (total lag / total RTT)   per packet: median 399.1 %  mean 405.2 %  max 1075.2 %
  Event-loop canary    avg 279.3 µs   p95 434.6 µs   max 66.09 ms
```

## 20261025-193944_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 19:42:16
- **Description:** Burst sem 15 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-193944_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-193944_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-193944_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.14 ms   p95 3.48 ms   max 4.45 ms
  Kernel Control RTT   mean 219.3 µs   mean cycle jitter 18.9 µs
  Python Observer RTT  mean 1.29 ms   mean cycle jitter 140.0 µs
  Observer intrusion   mean 1.08 ms   p95 1.83 ms   max 2.19 ms
                       error 490.3 % (total lag / total RTT)   per packet: median 487.2 %  mean 576.5 %  max 2412.0 %
  Event-loop canary    avg 328.1 µs   p95 427.8 µs   max 107.87 ms
```

## 20261025-194216_rs-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 19:44:48
- **Description:** Idle floor, burst · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-194216_rs-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-194216_rs-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-194216_rs-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=143)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.28 ms   p95 4.26 ms   max 4.59 ms
  Kernel Control RTT   mean 897.1 µs   mean cycle jitter 19.9 µs
  Python Observer RTT  mean 1.40 ms   mean cycle jitter 150.5 µs
  Observer intrusion   mean 504.9 µs   p95 2.88 ms   max 3.45 ms
                       error 56.3 % (total lag / total RTT)   per packet: median 9.3 %  mean 60.5 %  max 862.8 %
  Event-loop canary    avg 1.17 ms   p95 1.45 ms   max 7.22 ms
```

## 20261025-194448_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 19:47:21
- **Description:** Burst sem 15 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-194448_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-194448_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-194448_rs-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=117)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.14 ms   p95 1.74 ms   max 1.83 ms
  Kernel Control RTT   mean 759.2 µs   mean cycle jitter 93.9 µs
  Python Observer RTT  mean 6.30 ms   mean cycle jitter 1.78 ms
  Observer intrusion   mean 5.54 ms   p95 33.34 ms   max 34.04 ms
                       error 729.3 % (total lag / total RTT)   per packet: median 12.3 %  mean 672.9 %  max 7025.8 %
  Event-loop canary    avg 1.22 ms   p95 1.48 ms   max 40.39 ms
```

## 20261025-194721_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 19:49:53
- **Description:** Idle floor, burst · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-194721_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-194721_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-194721_py-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.29 ms   p95 4.13 ms   max 5.62 ms
  Kernel Control RTT   mean 235.2 µs   mean cycle jitter 21.5 µs
  Python Observer RTT  mean 1.54 ms   mean cycle jitter 210.3 µs
  Observer intrusion   mean 1.30 ms   p95 3.31 ms   max 3.80 ms
                       error 553.3 % (total lag / total RTT)   per packet: median 427.4 %  mean 737.4 %  max 5938.5 %
  Event-loop canary    avg 280.0 µs   p95 429.2 µs   max 60.44 ms
```

## 20261025-194953_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 19:52:26
- **Description:** Burst sem 15 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-194953_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-194953_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-194953_py-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.75 ms   p95 4.72 ms   max 5.75 ms
  Kernel Control RTT   mean 212.1 µs   mean cycle jitter 21.0 µs
  Python Observer RTT  mean 1.58 ms   mean cycle jitter 200.6 µs
  Observer intrusion   mean 1.37 ms   p95 2.81 ms   max 3.49 ms
                       error 645.9 % (total lag / total RTT)   per packet: median 580.4 %  mean 802.1 %  max 4142.9 %
  Event-loop canary    avg 328.0 µs   p95 434.1 µs   max 101.40 ms
```

## 20261025-195226_go-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 19:54:58
- **Description:** Idle floor, burst · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-195226_go-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-195226_go-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-195226_go-sc_100ep-burst-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=104)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 917.1 µs   p95 1.62 ms   max 2.08 ms
  Kernel Control RTT   mean 688.2 µs   mean cycle jitter 99.0 µs
  Python Observer RTT  mean 1.31 ms   mean cycle jitter 220.2 µs
  Observer intrusion   mean 626.6 µs   p95 6.58 ms   max 7.30 ms
                       error 91.1 % (total lag / total RTT)   per packet: median 10.2 %  mean 135.1 %  max 1488.5 %
  Event-loop canary    avg 285.5 µs   p95 614.1 µs   max 9.99 ms
```

## 20261025-195458_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 19:57:31
- **Description:** Burst sem 15 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-195458_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-195458_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-195458_go-sc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=146)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.11 ms   p95 1.69 ms   max 1.81 ms
  Kernel Control RTT   mean 698.0 µs   mean cycle jitter 85.1 µs
  Python Observer RTT  mean 5.18 ms   mean cycle jitter 1.42 ms
  Observer intrusion   mean 4.48 ms   p95 51.81 ms   max 52.57 ms
                       error 641.6 % (total lag / total RTT)   per packet: median 8.4 %  mean 550.7 %  max 10092.2 %
  Event-loop canary    avg 281.0 µs   p95 559.9 µs   max 318.94 ms
```

## 20261025-195738_py-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:00:11
- **Description:** Burst sem 5 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-195738_py-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-195738_py-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-195738_py-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.28 ms   p95 3.94 ms   max 6.25 ms
  Kernel Control RTT   mean 203.2 µs   mean cycle jitter 17.8 µs
  Python Observer RTT  mean 1.59 ms   mean cycle jitter 173.1 µs
  Observer intrusion   mean 1.39 ms   p95 3.55 ms   max 4.64 ms
                       error 682.0 % (total lag / total RTT)   per packet: median 516.0 %  mean 971.1 %  max 7342.4 %
  Event-loop canary    avg 228.3 µs   p95 387.1 µs   max 85.92 ms
```

## 20261025-200011_go-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:02:43
- **Description:** Burst sem 5 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-200011_go-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-200011_go-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-200011_go-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=111)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.08 ms   p95 1.63 ms   max 1.98 ms
  Kernel Control RTT   mean 711.5 µs   mean cycle jitter 81.8 µs
  Python Observer RTT  mean 5.65 ms   mean cycle jitter 1.56 ms
  Observer intrusion   mean 4.94 ms   p95 58.45 ms   max 59.16 ms
                       error 694.7 % (total lag / total RTT)   per packet: median 13.4 %  mean 585.3 %  max 10818.6 %
  Event-loop canary    avg 231.3 µs   p95 212.7 µs   max 310.08 ms
```

## 20261025-200243_rs-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:05:16
- **Description:** Burst sem 5 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-200243_rs-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-200243_rs-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-200243_rs-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=154)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 993.1 µs   p95 1.55 ms   max 1.69 ms
  Kernel Control RTT   mean 903.1 µs   mean cycle jitter 15.5 µs
  Python Observer RTT  mean 3.72 ms   mean cycle jitter 876.6 µs
  Observer intrusion   mean 2.81 ms   p95 16.65 ms   max 17.31 ms
                       error 311.4 % (total lag / total RTT)   per packet: median 5.5 %  mean 339.4 %  max 3465.8 %
  Event-loop canary    avg 1.11 ms   p95 1.22 ms   max 18.13 ms
```

## 20261025-200516_go-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:07:48
- **Description:** Burst sem 5 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-200516_go-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-200516_go-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-200516_go-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=154)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 986.5 µs   p95 1.67 ms   max 1.94 ms
  Kernel Control RTT   mean 805.7 µs   mean cycle jitter 75.1 µs
  Python Observer RTT  mean 6.92 ms   mean cycle jitter 1.94 ms
  Observer intrusion   mean 6.12 ms   p95 42.14 ms   max 42.87 ms
                       error 759.1 % (total lag / total RTT)   per packet: median 6.6 %  mean 720.9 %  max 8130.3 %
  Event-loop canary    avg 221.0 µs   p95 197.4 µs   max 270.34 ms
```

## 20261025-200748_rs-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:10:21
- **Description:** Burst sem 5 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-200748_rs-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-200748_rs-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-200748_rs-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=170)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.25 ms   p95 1.83 ms   max 2.04 ms
  Kernel Control RTT   mean 862.8 µs   mean cycle jitter 26.9 µs
  Python Observer RTT  mean 3.66 ms   mean cycle jitter 879.4 µs
  Observer intrusion   mean 2.80 ms   p95 15.59 ms   max 16.05 ms
                       error 324.1 % (total lag / total RTT)   per packet: median 4.2 %  mean 327.9 %  max 3162.9 %
  Event-loop canary    avg 1.11 ms   p95 1.22 ms   max 15.83 ms
```

## 20261025-201021_py-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:12:53
- **Description:** Burst sem 5 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-201021_py-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-201021_py-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-201021_py-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.12 ms   p95 4.17 ms   max 5.92 ms
  Kernel Control RTT   mean 220.6 µs   mean cycle jitter 18.1 µs
  Python Observer RTT  mean 1.44 ms   mean cycle jitter 155.2 µs
  Observer intrusion   mean 1.22 ms   p95 2.31 ms   max 3.27 ms
                       error 554.5 % (total lag / total RTT)   per packet: median 466.0 %  mean 687.1 %  max 3615.4 %
  Event-loop canary    avg 202.8 µs   p95 215.3 µs   max 78.42 ms
```

## 20261025-201253_rs-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:15:26
- **Description:** Burst sem 5 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-201253_rs-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-201253_rs-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-201253_rs-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=181)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.19 ms   p95 1.70 ms   max 1.80 ms
  Kernel Control RTT   mean 890.2 µs   mean cycle jitter 16.2 µs
  Python Observer RTT  mean 3.71 ms   mean cycle jitter 882.7 µs
  Observer intrusion   mean 2.82 ms   p95 15.39 ms   max 15.84 ms
                       error 316.6 % (total lag / total RTT)   per packet: median 4.6 %  mean 340.7 %  max 3522.1 %
  Event-loop canary    avg 1.11 ms   p95 1.22 ms   max 15.37 ms
```

## 20261025-201526_py-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:17:59
- **Description:** Burst sem 5 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-201526_py-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-201526_py-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-201526_py-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.13 ms   p95 4.16 ms   max 7.21 ms
  Kernel Control RTT   mean 208.2 µs   mean cycle jitter 19.6 µs
  Python Observer RTT  mean 1.46 ms   mean cycle jitter 177.5 µs
  Observer intrusion   mean 1.25 ms   p95 3.60 ms   max 4.52 ms
                       error 600.1 % (total lag / total RTT)   per packet: median 489.7 %  mean 753.8 %  max 6149.3 %
  Event-loop canary    avg 202.9 µs   p95 219.2 µs   max 79.36 ms
```

## 20261025-201759_go-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:20:31
- **Description:** Burst sem 5 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=5 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-201759_go-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-201759_go-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-201759_go-sc_100ep-burst-sem5-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=136)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.09 ms   p95 1.70 ms   max 1.90 ms
  Kernel Control RTT   mean 780.7 µs   mean cycle jitter 66.7 µs
  Python Observer RTT  mean 9.89 ms   mean cycle jitter 2.85 ms
  Observer intrusion   mean 9.11 ms   p95 65.63 ms   max 66.32 ms
                       error 1166.4 % (total lag / total RTT)   per packet: median 8.5 %  mean 1108.1 %  max 12136.5 %
  Event-loop canary    avg 228.3 µs   p95 199.4 µs   max 248.82 ms
```

## 20261025-202043_py-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:23:16
- **Description:** Burst sem 50 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-202043_py-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-202043_py-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-202043_py-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.67 ms   p95 4.73 ms   max 6.49 ms
  Kernel Control RTT   mean 173.8 µs   mean cycle jitter 23.2 µs
  Python Observer RTT  mean 1.99 ms   mean cycle jitter 261.3 µs
  Observer intrusion   mean 1.82 ms   p95 3.57 ms   max 4.50 ms
                       error 1047.1 % (total lag / total RTT)   per packet: median 1121.0 %  mean 1344.4 %  max 4587.8 %
  Event-loop canary    avg 251.8 µs   p95 218.8 µs   max 218.71 ms
```

## 20261025-202316_go-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:25:49
- **Description:** Burst sem 50 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-202316_go-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-202316_go-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-202316_go-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=165)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.01 ms   p95 1.72 ms   max 1.85 ms
  Kernel Control RTT   mean 845.1 µs   mean cycle jitter 73.4 µs
  Python Observer RTT  mean 11.89 ms   mean cycle jitter 3.48 ms
  Observer intrusion   mean 11.04 ms   p95 78.47 ms   max 79.25 ms
                       error 1306.4 % (total lag / total RTT)   per packet: median 6.4 %  mean 1253.5 %  max 13985.7 %
  Event-loop canary    avg 231.3 µs   p95 200.9 µs   max 238.04 ms
```

## 20261025-202549_rs-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:28:21
- **Description:** Burst sem 50 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-202549_rs-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-202549_rs-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-202549_rs-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=138)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.25 ms   p95 1.80 ms   max 1.92 ms
  Kernel Control RTT   mean 732.5 µs   mean cycle jitter 87.0 µs
  Python Observer RTT  mean 8.43 ms   mean cycle jitter 2.44 ms
  Observer intrusion   mean 7.70 ms   p95 27.68 ms   max 156.09 ms
                       error 1051.2 % (total lag / total RTT)   per packet: median 8.8 %  mean 1948.7 %  max 55796.3 %
  Event-loop canary    avg 1.16 ms   p95 1.22 ms   max 155.95 ms
```

## 20261025-202821_go-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:30:54
- **Description:** Burst sem 50 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-202821_go-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-202821_go-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-202821_go-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=122)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.06 ms   p95 1.66 ms   max 1.86 ms
  Kernel Control RTT   mean 815.1 µs   mean cycle jitter 73.6 µs
  Python Observer RTT  mean 10.99 ms   mean cycle jitter 3.20 ms
  Observer intrusion   mean 10.18 ms   p95 78.13 ms   max 78.87 ms
                       error 1248.9 % (total lag / total RTT)   per packet: median 9.7 %  mean 1158.3 %  max 13397.1 %
  Event-loop canary    avg 232.6 µs   p95 199.0 µs   max 237.87 ms
```

## 20261025-203054_rs-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:33:26
- **Description:** Burst sem 50 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-203054_rs-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-203054_rs-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-203054_rs-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=129)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.13 ms   p95 1.73 ms   max 1.93 ms
  Kernel Control RTT   mean 742.8 µs   mean cycle jitter 89.9 µs
  Python Observer RTT  mean 8.66 ms   mean cycle jitter 2.51 ms
  Observer intrusion   mean 7.91 ms   p95 73.74 ms   max 74.46 ms
                       error 1065.4 % (total lag / total RTT)   per packet: median 11.7 %  mean 981.9 %  max 13590.3 %
  Event-loop canary    avg 1.17 ms   p95 1.22 ms   max 144.98 ms
```

## 20261025-203326_py-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:35:59
- **Description:** Burst sem 50 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-203326_py-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-203326_py-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-203326_py-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.28 ms   p95 3.90 ms   max 4.87 ms
  Kernel Control RTT   mean 261.8 µs   mean cycle jitter 26.0 µs
  Python Observer RTT  mean 1.52 ms   mean cycle jitter 203.1 µs
  Observer intrusion   mean 1.26 ms   p95 2.82 ms   max 3.47 ms
                       error 481.3 % (total lag / total RTT)   per packet: median 431.1 %  mean 550.9 %  max 3720.4 %
  Event-loop canary    avg 252.5 µs   p95 218.8 µs   max 213.89 ms
```

## 20261025-203559_rs-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:38:31
- **Description:** Burst sem 50 · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-203559_rs-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-203559_rs-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-203559_rs-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=156)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 918.2 µs   p95 1.54 ms   max 1.78 ms
  Kernel Control RTT   mean 840.0 µs   mean cycle jitter 56.7 µs
  Python Observer RTT  mean 5.34 ms   mean cycle jitter 1.43 ms
  Observer intrusion   mean 4.50 ms   p95 24.43 ms   max 24.77 ms
                       error 535.7 % (total lag / total RTT)   per packet: median 7.6 %  mean 543.3 %  max 5467.6 %
  Event-loop canary    avg 1.16 ms   p95 1.22 ms   max 148.51 ms
```

## 20261025-203831_py-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:41:04
- **Description:** Burst sem 50 · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-203831_py-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-203831_py-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-203831_py-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.83 ms   p95 4.82 ms   max 5.86 ms
  Kernel Control RTT   mean 201.7 µs   mean cycle jitter 22.7 µs
  Python Observer RTT  mean 1.79 ms   mean cycle jitter 250.7 µs
  Observer intrusion   mean 1.59 ms   p95 3.27 ms   max 3.52 ms
                       error 786.9 % (total lag / total RTT)   per packet: median 650.5 %  mean 995.2 %  max 4208.6 %
  Event-loop canary    avg 249.1 µs   p95 215.2 µs   max 218.97 ms
```

## 20261025-204104_go-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem

- **Date:** 2026-10-25 20:43:37
- **Description:** Burst sem 50 · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=50 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-204104_go-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.csv` (per packet), `20261025-204104_go-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem_cycles.csv` (per cycle), `20261025-204104_go-sc_100ep-burst-sem50-db3-i8-c3x60_192-168-70-2_burst-sem.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=121)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.06 ms   p95 1.43 ms   max 1.52 ms
  Kernel Control RTT   mean 710.8 µs   mean cycle jitter 123.5 µs
  Python Observer RTT  mean 9.98 ms   mean cycle jitter 2.95 ms
  Observer intrusion   mean 9.27 ms   p95 62.59 ms   max 63.32 ms
                       error 1304.6 % (total lag / total RTT)   per packet: median 13.6 %  mean 1116.2 %  max 11480.5 %
  Event-loop canary    avg 239.0 µs   p95 201.9 µs   max 265.38 ms
```

## 20261025-204349_py-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc

- **Date:** 2026-10-25 20:46:22
- **Description:** Burst sem 15 · Python multi-core
- **Command:** `dashboard run: engine=python cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-204349_py-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.csv` (per packet), `20261025-204349_py-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc_cycles.csv` (per cycle), `20261025-204349_py-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.25 ms   p95 3.87 ms   max 4.50 ms
  Kernel Control RTT   mean 238.4 µs   mean cycle jitter 17.6 µs
  Python Observer RTT  mean 1.45 ms   mean cycle jitter 172.6 µs
  Observer intrusion   mean 1.22 ms   p95 2.42 ms   max 3.39 ms
                       error 510.2 % (total lag / total RTT)   per packet: median 437.4 %  mean 586.6 %  max 3263.1 %
  Event-loop canary    avg 197.7 µs   p95 221.2 µs   max 74.34 ms
```

## 20261025-204622_go-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc

- **Date:** 2026-10-25 20:48:55
- **Description:** Burst sem 15 · Go multi-core
- **Command:** `dashboard run: engine=go cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-204622_go-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.csv` (per packet), `20261025-204622_go-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc_cycles.csv` (per cycle), `20261025-204622_go-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=196)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.14 ms   p95 1.91 ms   max 2.20 ms
  Kernel Control RTT   mean 535.7 µs   mean cycle jitter 83.5 µs
  Python Observer RTT  mean 639.0 µs   mean cycle jitter 89.7 µs
  Observer intrusion   mean 103.3 µs   p95 318.8 µs   max 1.44 ms
                       error 19.3 % (total lag / total RTT)   per packet: median 7.6 %  mean 26.6 %  max 331.5 %
  Event-loop canary    avg 186.1 µs   p95 235.5 µs   max 3.19 ms
```

## 20261025-204855_rs-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc

- **Date:** 2026-10-25 20:51:27
- **Description:** Burst sem 15 · Rust multi-core
- **Command:** `dashboard run: engine=rust cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-204855_rs-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.csv` (per packet), `20261025-204855_rs-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc_cycles.csv` (per cycle), `20261025-204855_rs-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=158)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.50 ms   p95 2.28 ms   max 5.33 ms
  Kernel Control RTT   mean 685.4 µs   mean cycle jitter 81.9 µs
  Python Observer RTT  mean 1.52 ms   mean cycle jitter 289.5 µs
  Observer intrusion   mean 836.4 µs   p95 7.85 ms   max 8.22 ms
                       error 122.0 % (total lag / total RTT)   per packet: median 6.7 %  mean 180.6 %  max 2648.9 %
  Event-loop canary    avg 1.10 ms   p95 1.22 ms   max 9.18 ms
```

## 20261025-205127_go-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc

- **Date:** 2026-10-25 20:53:59
- **Description:** Burst sem 15 · Go multi-core
- **Command:** `dashboard run: engine=go cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-205127_go-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.csv` (per packet), `20261025-205127_go-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc_cycles.csv` (per cycle), `20261025-205127_go-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=214)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.15 ms   p95 1.86 ms   max 2.38 ms
  Kernel Control RTT   mean 612.8 µs   mean cycle jitter 65.4 µs
  Python Observer RTT  mean 667.8 µs   mean cycle jitter 63.0 µs
  Observer intrusion   mean 55.0 µs   p95 186.8 µs   max 365.5 µs
                       error 9.0 % (total lag / total RTT)   per packet: median 5.8 %  mean 11.8 %  max 85.1 %
  Event-loop canary    avg 184.3 µs   p95 236.7 µs   max 2.44 ms
```

## 20261025-205359_rs-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc

- **Date:** 2026-10-25 20:56:31
- **Description:** Burst sem 15 · Rust multi-core
- **Command:** `dashboard run: engine=rust cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-205359_rs-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.csv` (per packet), `20261025-205359_rs-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc_cycles.csv` (per cycle), `20261025-205359_rs-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=161)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.61 ms   p95 2.22 ms   max 2.57 ms
  Kernel Control RTT   mean 669.0 µs   mean cycle jitter 104.0 µs
  Python Observer RTT  mean 1.67 ms   mean cycle jitter 363.4 µs
  Observer intrusion   mean 1.01 ms   p95 7.84 ms   max 9.04 ms
                       error 150.3 % (total lag / total RTT)   per packet: median 5.8 %  mean 422.6 %  max 11683.3 %
  Event-loop canary    avg 1.10 ms   p95 1.22 ms   max 25.60 ms
```

## 20261025-205631_py-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc

- **Date:** 2026-10-25 20:59:05
- **Description:** Burst sem 15 · Python multi-core
- **Command:** `dashboard run: engine=python cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-205631_py-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.csv` (per packet), `20261025-205631_py-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc_cycles.csv` (per cycle), `20261025-205631_py-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.18 ms   p95 3.49 ms   max 5.23 ms
  Kernel Control RTT   mean 250.4 µs   mean cycle jitter 16.4 µs
  Python Observer RTT  mean 1.45 ms   mean cycle jitter 169.8 µs
  Observer intrusion   mean 1.20 ms   p95 2.46 ms   max 3.24 ms
                       error 479.8 % (total lag / total RTT)   per packet: median 420.6 %  mean 547.4 %  max 3404.6 %
  Event-loop canary    avg 194.4 µs   p95 217.3 µs   max 65.79 ms
```

## 20261025-205905_rs-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc

- **Date:** 2026-10-25 21:01:37
- **Description:** Burst sem 15 · Rust multi-core
- **Command:** `dashboard run: engine=rust cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-205905_rs-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.csv` (per packet), `20261025-205905_rs-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc_cycles.csv` (per cycle), `20261025-205905_rs-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=157)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.86 ms   p95 2.50 ms   max 5.58 ms
  Kernel Control RTT   mean 700.4 µs   mean cycle jitter 79.4 µs
  Python Observer RTT  mean 1.70 ms   mean cycle jitter 341.6 µs
  Observer intrusion   mean 1.00 ms   p95 10.49 ms   max 11.22 ms
                       error 143.2 % (total lag / total RTT)   per packet: median 5.9 %  mean 156.8 %  max 2726.6 %
  Event-loop canary    avg 1.10 ms   p95 1.22 ms   max 10.41 ms
```

## 20261025-210137_py-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc

- **Date:** 2026-10-25 21:04:11
- **Description:** Burst sem 15 · Python multi-core
- **Command:** `dashboard run: engine=python cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-210137_py-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.csv` (per packet), `20261025-210137_py-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc_cycles.csv` (per cycle), `20261025-210137_py-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=10)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 2.14 ms   p95 3.85 ms   max 5.03 ms
  Kernel Control RTT   mean 254.8 µs   mean cycle jitter 17.9 µs
  Python Observer RTT  mean 1.44 ms   mean cycle jitter 171.5 µs
  Observer intrusion   mean 1.18 ms   p95 2.42 ms   max 3.48 ms
                       error 463.3 % (total lag / total RTT)   per packet: median 424.9 %  mean 562.5 %  max 3877.0 %
  Event-loop canary    avg 197.9 µs   p95 219.1 µs   max 84.66 ms
```

## 20261025-210411_go-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc

- **Date:** 2026-10-25 21:06:43
- **Description:** Burst sem 15 · Go multi-core
- **Command:** `dashboard run: engine=go cpu=multi_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=0.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-210411_go-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.csv` (per packet), `20261025-210411_go-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc_cycles.csv` (per cycle), `20261025-210411_go-mc_100ep-burst-sem15-db3-i8-c3x60_192-168-70-2_burst-mc.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=204)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.36 ms   p95 2.01 ms   max 2.36 ms
  Kernel Control RTT   mean 627.6 µs   mean cycle jitter 61.3 µs
  Python Observer RTT  mean 709.6 µs   mean cycle jitter 53.5 µs
  Observer intrusion   mean 81.9 µs   p95 265.2 µs   max 869.2 µs
                       error 13.1 % (total lag / total RTT)   per packet: median 5.0 %  mean 25.9 %  max 666.4 %
  Event-loop canary    avg 186.9 µs   p95 237.2 µs   max 2.98 ms
```

## 20261025-210654_py-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 21:10:24
- **Description:** 25 endpoints · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-210654_py-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-210654_py-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-210654_py-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=171)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 747.8 µs   p95 1.72 ms   max 2.21 ms
  Kernel Control RTT   mean 358.1 µs   mean cycle jitter 16.6 µs
  Python Observer RTT  mean 459.2 µs   mean cycle jitter 16.5 µs
  Observer intrusion   mean 101.2 µs   p95 134.8 µs   max 431.4 µs
                       error 28.3 % (total lag / total RTT)   per packet: median 25.9 %  mean 30.6 %  max 139.5 %
  Event-loop canary    avg 187.8 µs   p95 232.0 µs   max 4.16 ms
```

## 20261025-211024_go-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 21:13:54
- **Description:** 25 endpoints · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-211024_go-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-211024_go-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-211024_go-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=171)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 635.0 µs   p95 1.05 ms   max 3.99 ms
  Kernel Control RTT   mean 369.2 µs   mean cycle jitter 14.6 µs
  Python Observer RTT  mean 459.2 µs   mean cycle jitter 28.5 µs
  Observer intrusion   mean 90.0 µs   p95 345.8 µs   max 1.02 ms
                       error 24.4 % (total lag / total RTT)   per packet: median 11.8 %  mean 31.8 %  max 1178.3 %
  Event-loop canary    avg 170.8 µs   p95 203.3 µs   max 3.26 ms
```

## 20261025-211354_rs-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 21:17:24
- **Description:** 25 endpoints · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-211354_rs-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-211354_rs-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-211354_rs-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=170)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 817.4 µs   p95 1.24 ms   max 2.33 ms
  Kernel Control RTT   mean 362.7 µs   mean cycle jitter 11.6 µs
  Python Observer RTT  mean 465.9 µs   mean cycle jitter 24.5 µs
  Observer intrusion   mean 103.2 µs   p95 115.0 µs   max 3.22 ms
                       error 28.5 % (total lag / total RTT)   per packet: median 20.1 %  mean 29.8 %  max 937.6 %
  Event-loop canary    avg 1.11 ms   p95 1.22 ms   max 7.24 ms
```

## 20261025-211724_go-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 21:20:54
- **Description:** 25 endpoints · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-211724_go-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-211724_go-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-211724_go-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=170)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 613.3 µs   p95 1.04 ms   max 1.10 ms
  Kernel Control RTT   mean 361.8 µs   mean cycle jitter 14.2 µs
  Python Observer RTT  mean 438.4 µs   mean cycle jitter 16.6 µs
  Observer intrusion   mean 76.6 µs   p95 99.1 µs   max 453.1 µs
                       error 21.2 % (total lag / total RTT)   per packet: median 20.5 %  mean 23.2 %  max 144.7 %
  Event-loop canary    avg 183.9 µs   p95 214.0 µs   max 3.81 ms
```

## 20261025-212054_rs-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 21:24:23
- **Description:** 25 endpoints · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-212054_rs-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-212054_rs-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-212054_rs-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=170)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 600.7 µs   p95 1.04 ms   max 3.11 ms
  Kernel Control RTT   mean 365.5 µs   mean cycle jitter 16.0 µs
  Python Observer RTT  mean 447.6 µs   mean cycle jitter 25.9 µs
  Observer intrusion   mean 82.1 µs   p95 108.1 µs   max 942.0 µs
                       error 22.5 % (total lag / total RTT)   per packet: median 17.6 %  mean 23.6 %  max 230.2 %
  Event-loop canary    avg 1.10 ms   p95 1.22 ms   max 4.56 ms
```

## 20261025-212423_py-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 21:27:53
- **Description:** 25 endpoints · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-212423_py-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-212423_py-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-212423_py-sc_25ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=175)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 803.0 µs   p95 1.86 ms   max 2.82 ms
  Kernel Control RTT   mean 356.1 µs   mean cycle jitter 16.7 µs
  Python Observer RTT  mean 460.6 µs   mean cycle jitter 20.7 µs
  Observer intrusion   mean 104.4 µs   p95 126.9 µs   max 1.04 ms
                       error 29.3 % (total lag / total RTT)   per packet: median 25.3 %  mean 31.5 %  max 270.8 %
  Event-loop canary    avg 184.9 µs   p95 231.6 µs   max 3.60 ms
```

## 20261025-212800_py-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 21:31:32
- **Description:** 250 endpoints · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-212800_py-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-212800_py-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-212800_py-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1720)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 784.4 µs   p95 1.94 ms   max 4.01 ms
  Kernel Control RTT   mean 356.9 µs   mean cycle jitter 17.3 µs
  Python Observer RTT  mean 459.1 µs   mean cycle jitter 20.2 µs
  Observer intrusion   mean 102.2 µs   p95 134.7 µs   max 4.61 ms
                       error 28.6 % (total lag / total RTT)   per packet: median 25.5 %  mean 31.9 %  max 3763.0 %
  Event-loop canary    avg 343.2 µs   p95 1.45 ms   max 5.64 ms
```

## 20261025-213132_go-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 21:35:04
- **Description:** 250 endpoints · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-213132_go-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-213132_go-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-213132_go-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1703)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 535.8 µs   p95 1.04 ms   max 3.20 ms
  Kernel Control RTT   mean 369.4 µs   mean cycle jitter 15.2 µs
  Python Observer RTT  mean 439.3 µs   mean cycle jitter 20.4 µs
  Observer intrusion   mean 69.9 µs   p95 97.4 µs   max 3.27 ms
                       error 18.9 % (total lag / total RTT)   per packet: median 17.0 %  mean 22.0 %  max 2046.1 %
  Event-loop canary    avg 245.4 µs   p95 812.9 µs   max 4.83 ms
```

## 20261025-213504_rs-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 21:38:36
- **Description:** 250 endpoints · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-213504_rs-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-213504_rs-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-213504_rs-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1701)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.38 ms   p95 1.82 ms   max 4.44 ms
  Kernel Control RTT   mean 347.5 µs   mean cycle jitter 11.9 µs
  Python Observer RTT  mean 428.2 µs   mean cycle jitter 16.3 µs
  Observer intrusion   mean 80.8 µs   p95 103.0 µs   max 3.45 ms
                       error 23.2 % (total lag / total RTT)   per packet: median 21.1 %  mean 25.1 %  max 1368.1 %
  Event-loop canary    avg 1.12 ms   p95 1.62 ms   max 4.58 ms
```

## 20261025-213836_go-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 21:42:08
- **Description:** 250 endpoints · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-213836_go-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-213836_go-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-213836_go-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1703)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 634.4 µs   p95 1.05 ms   max 3.18 ms
  Kernel Control RTT   mean 371.5 µs   mean cycle jitter 14.8 µs
  Python Observer RTT  mean 446.4 µs   mean cycle jitter 19.3 µs
  Observer intrusion   mean 74.9 µs   p95 106.8 µs   max 1.44 ms
                       error 20.2 % (total lag / total RTT)   per packet: median 18.1 %  mean 23.8 %  max 1111.2 %
  Event-loop canary    avg 248.9 µs   p95 840.8 µs   max 7.79 ms
```

## 20261025-214208_rs-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 21:45:40
- **Description:** 250 endpoints · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-214208_rs-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-214208_rs-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-214208_rs-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1703)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 861.4 µs   p95 1.33 ms   max 3.08 ms
  Kernel Control RTT   mean 371.9 µs   mean cycle jitter 11.9 µs
  Python Observer RTT  mean 450.3 µs   mean cycle jitter 18.3 µs
  Observer intrusion   mean 78.3 µs   p95 100.8 µs   max 4.25 ms
                       error 21.1 % (total lag / total RTT)   per packet: median 18.5 %  mean 22.5 %  max 1225.4 %
  Event-loop canary    avg 1.11 ms   p95 1.60 ms   max 5.68 ms
```

## 20261025-214540_py-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep

- **Date:** 2026-10-25 21:49:12
- **Description:** 250 endpoints · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-214540_py-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.csv` (per packet), `20261025-214540_py-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep_cycles.csv` (per cycle), `20261025-214540_py-sc_250ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_ep-sweep.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1723)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 740.8 µs   p95 1.98 ms   max 3.40 ms
  Kernel Control RTT   mean 349.9 µs   mean cycle jitter 18.1 µs
  Python Observer RTT  mean 436.0 µs   mean cycle jitter 18.3 µs
  Observer intrusion   mean 86.1 µs   p95 126.9 µs   max 868.0 µs
                       error 24.6 % (total lag / total RTT)   per packet: median 24.7 %  mean 27.2 %  max 242.6 %
  Event-loop canary    avg 341.3 µs   p95 1.45 ms   max 4.34 ms
```

## 20261025-214921_py-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 21:52:52
- **Description:** Idle floor · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-214921_py-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-214921_py-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-214921_py-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=689)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 779.4 µs   p95 1.78 ms   max 2.82 ms
  Kernel Control RTT   mean 345.1 µs   mean cycle jitter 17.4 µs
  Python Observer RTT  mean 448.7 µs   mean cycle jitter 21.0 µs
  Observer intrusion   mean 103.6 µs   p95 132.5 µs   max 3.50 ms
                       error 30.0 % (total lag / total RTT)   per packet: median 26.3 %  mean 32.9 %  max 1237.0 %
  Event-loop canary    avg 216.3 µs   p95 634.5 µs   max 4.29 ms
```

## 20261025-215252_py-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day

- **Date:** 2026-10-25 21:56:24
- **Description:** Same day, 100ep · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-215252_py-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day.csv` (per packet), `20261025-215252_py-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day_cycles.csv` (per cycle), `20261025-215252_py-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=683)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 778.1 µs   p95 1.68 ms   max 2.51 ms
  Kernel Control RTT   mean 354.8 µs   mean cycle jitter 16.5 µs
  Python Observer RTT  mean 458.2 µs   mean cycle jitter 17.4 µs
  Observer intrusion   mean 103.3 µs   p95 132.7 µs   max 1.54 ms
                       error 29.1 % (total lag / total RTT)   per packet: median 26.7 %  mean 32.2 %  max 494.8 %
  Event-loop canary    avg 229.3 µs   p95 764.8 µs   max 3.94 ms
```

## 20261025-215624_go-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 21:59:56
- **Description:** Idle floor · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-215624_go-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-215624_go-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-215624_go-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 619.3 µs   p95 1.08 ms   max 2.53 ms
  Kernel Control RTT   mean 355.6 µs   mean cycle jitter 14.5 µs
  Python Observer RTT  mean 433.6 µs   mean cycle jitter 17.2 µs
  Observer intrusion   mean 78.1 µs   p95 107.7 µs   max 662.9 µs
                       error 22.0 % (total lag / total RTT)   per packet: median 21.0 %  mean 23.8 %  max 192.1 %
  Event-loop canary    avg 190.4 µs   p95 404.4 µs   max 2.93 ms
```

## 20261025-215956_go-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day

- **Date:** 2026-10-25 22:03:27
- **Description:** Same day, 100ep · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-215956_go-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day.csv` (per packet), `20261025-215956_go-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day_cycles.csv` (per cycle), `20261025-215956_go-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=681)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 607.2 µs   p95 1.09 ms   max 2.88 ms
  Kernel Control RTT   mean 358.8 µs   mean cycle jitter 13.4 µs
  Python Observer RTT  mean 438.6 µs   mean cycle jitter 16.0 µs
  Observer intrusion   mean 79.8 µs   p95 103.1 µs   max 848.1 µs
                       error 22.3 % (total lag / total RTT)   per packet: median 20.9 %  mean 23.8 %  max 226.6 %
  Event-loop canary    avg 203.0 µs   p95 463.8 µs   max 3.95 ms
```

## 20261025-220327_rs-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 22:06:59
- **Description:** Idle floor · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-220327_rs-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-220327_rs-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-220327_rs-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 744.1 µs   p95 1.14 ms   max 2.96 ms
  Kernel Control RTT   mean 367.7 µs   mean cycle jitter 13.8 µs
  Python Observer RTT  mean 444.5 µs   mean cycle jitter 17.2 µs
  Observer intrusion   mean 76.8 µs   p95 97.7 µs   max 1.13 ms
                       error 20.9 % (total lag / total RTT)   per packet: median 19.2 %  mean 22.2 %  max 337.6 %
  Event-loop canary    avg 1.10 ms   p95 1.23 ms   max 4.39 ms
```

## 20261025-220659_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day

- **Date:** 2026-10-25 22:10:30
- **Description:** Same day, 100ep · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-220659_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day.csv` (per packet), `20261025-220659_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day_cycles.csv` (per cycle), `20261025-220659_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 813.3 µs   p95 1.28 ms   max 3.32 ms
  Kernel Control RTT   mean 359.5 µs   mean cycle jitter 12.7 µs
  Python Observer RTT  mean 431.6 µs   mean cycle jitter 17.0 µs
  Observer intrusion   mean 72.1 µs   p95 95.6 µs   max 1.21 ms
                       error 20.0 % (total lag / total RTT)   per packet: median 19.0 %  mean 21.5 %  max 407.5 %
  Event-loop canary    avg 1.11 ms   p95 1.24 ms   max 4.92 ms
```

## 20261025-221030_go-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 22:14:02
- **Description:** Idle floor · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-221030_go-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-221030_go-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-221030_go-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=681)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 664.3 µs   p95 1.09 ms   max 3.37 ms
  Kernel Control RTT   mean 370.2 µs   mean cycle jitter 14.8 µs
  Python Observer RTT  mean 444.7 µs   mean cycle jitter 17.2 µs
  Observer intrusion   mean 74.5 µs   p95 97.5 µs   max 712.0 µs
                       error 20.1 % (total lag / total RTT)   per packet: median 18.8 %  mean 22.2 %  max 385.3 %
  Event-loop canary    avg 195.9 µs   p95 413.7 µs   max 3.88 ms
```

## 20261025-221402_go-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day

- **Date:** 2026-10-25 22:17:34
- **Description:** Same day, 100ep · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-221402_go-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day.csv` (per packet), `20261025-221402_go-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day_cycles.csv` (per cycle), `20261025-221402_go-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=685)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 609.8 µs   p95 1.06 ms   max 4.43 ms
  Kernel Control RTT   mean 359.7 µs   mean cycle jitter 14.8 µs
  Python Observer RTT  mean 427.3 µs   mean cycle jitter 22.7 µs
  Observer intrusion   mean 67.7 µs   p95 99.2 µs   max 947.4 µs
                       error 18.8 % (total lag / total RTT)   per packet: median 12.0 %  mean 20.0 %  max 308.0 %
  Event-loop canary    avg 182.9 µs   p95 395.2 µs   max 6.94 ms
```

## 20261025-221734_rs-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 22:21:05
- **Description:** Idle floor · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-221734_rs-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-221734_rs-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-221734_rs-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 840.4 µs   p95 1.31 ms   max 2.53 ms
  Kernel Control RTT   mean 378.4 µs   mean cycle jitter 12.0 µs
  Python Observer RTT  mean 452.9 µs   mean cycle jitter 17.0 µs
  Observer intrusion   mean 74.5 µs   p95 97.0 µs   max 992.0 µs
                       error 19.7 % (total lag / total RTT)   per packet: median 18.0 %  mean 20.9 %  max 258.7 %
  Event-loop canary    avg 1.11 ms   p95 1.22 ms   max 4.98 ms
```

## 20261025-222105_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day

- **Date:** 2026-10-25 22:24:37
- **Description:** Same day, 100ep · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-222105_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day.csv` (per packet), `20261025-222105_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day_cycles.csv` (per cycle), `20261025-222105_rs-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=680)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 782.6 µs   p95 1.26 ms   max 1.67 ms
  Kernel Control RTT   mean 378.2 µs   mean cycle jitter 14.5 µs
  Python Observer RTT  mean 451.3 µs   mean cycle jitter 16.4 µs
  Observer intrusion   mean 73.1 µs   p95 98.7 µs   max 820.7 µs
                       error 19.3 % (total lag / total RTT)   per packet: median 18.5 %  mean 21.0 %  max 439.3 %
  Event-loop canary    avg 1.12 ms   p95 1.32 ms   max 8.25 ms
```

## 20261025-222437_py-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 22:28:09
- **Description:** Idle floor · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-222437_py-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-222437_py-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-222437_py-sc_100ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=690)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 856.2 µs   p95 1.92 ms   max 4.25 ms
  Kernel Control RTT   mean 409.6 µs   mean cycle jitter 34.0 µs
  Python Observer RTT  mean 527.5 µs   mean cycle jitter 40.0 µs
  Observer intrusion   mean 117.9 µs   p95 209.0 µs   max 1.75 ms
                       error 28.8 % (total lag / total RTT)   per packet: median 23.9 %  mean 33.5 %  max 506.4 %
  Event-loop canary    avg 301.4 µs   p95 855.0 µs   max 6.69 ms
```

## 20261025-222809_py-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day

- **Date:** 2026-10-25 22:31:40
- **Description:** Same day, 100ep · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=100 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=3.0ms hw_timestamps=False`
- **Files:** `20261025-222809_py-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day.csv` (per packet), `20261025-222809_py-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day_cycles.csv` (per cycle), `20261025-222809_py-sc_100ep-stg60-sem15-db3-i8-c3x60_192-168-70-2_same-day.meta.json`

```text
SUMMARY  packets sent=1000 replied=1000 lost=0 (reader wakeups=686)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 878.1 µs   p95 1.94 ms   max 3.34 ms
  Kernel Control RTT   mean 413.1 µs   mean cycle jitter 31.5 µs
  Python Observer RTT  mean 523.7 µs   mean cycle jitter 35.8 µs
  Observer intrusion   mean 110.6 µs   p95 171.0 µs   max 1.07 ms
                       error 26.8 % (total lag / total RTT)   per packet: median 24.4 %  mean 30.4 %  max 283.5 %
  Event-loop canary    avg 288.8 µs   p95 798.2 µs   max 6.26 ms
```

## 20261025-223307_py-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 22:36:37
- **Description:** Idle floor 25ep · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-223307_py-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-223307_py-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-223307_py-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=173)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 925.6 µs   p95 2.03 ms   max 2.45 ms
  Kernel Control RTT   mean 394.5 µs   mean cycle jitter 25.6 µs
  Python Observer RTT  mean 508.5 µs   mean cycle jitter 32.5 µs
  Observer intrusion   mean 114.0 µs   p95 187.8 µs   max 922.5 µs
                       error 28.9 % (total lag / total RTT)   per packet: median 24.4 %  mean 32.5 %  max 269.1 %
  Event-loop canary    avg 276.6 µs   p95 532.7 µs   max 7.10 ms
```

## 20261025-223642_go-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 22:40:12
- **Description:** Idle floor 25ep · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-223642_go-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-223642_go-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-223642_go-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=170)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 656.4 µs   p95 1.16 ms   max 4.18 ms
  Kernel Control RTT   mean 428.9 µs   mean cycle jitter 23.2 µs
  Python Observer RTT  mean 518.9 µs   mean cycle jitter 31.1 µs
  Observer intrusion   mean 90.0 µs   p95 164.8 µs   max 925.8 µs
                       error 21.0 % (total lag / total RTT)   per packet: median 17.1 %  mean 23.2 %  max 265.3 %
  Event-loop canary    avg 281.9 µs   p95 646.1 µs   max 29.31 ms
```

## 20261025-224018_rs-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 22:43:47
- **Description:** Idle floor 25ep · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-224018_rs-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-224018_rs-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-224018_rs-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=170)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 843.4 µs   p95 1.36 ms   max 2.29 ms
  Kernel Control RTT   mean 417.5 µs   mean cycle jitter 26.2 µs
  Python Observer RTT  mean 505.9 µs   mean cycle jitter 38.0 µs
  Observer intrusion   mean 88.4 µs   p95 148.8 µs   max 1.27 ms
                       error 21.2 % (total lag / total RTT)   per packet: median 17.0 %  mean 23.2 %  max 311.8 %
  Event-loop canary    avg 1.17 ms   p95 1.43 ms   max 6.45 ms
```

## 20261025-224353_py-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 22:47:25
- **Description:** Idle floor 250ep · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-224353_py-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-224353_py-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-224353_py-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1721)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 852.0 µs   p95 1.73 ms   max 7.16 ms
  Kernel Control RTT   mean 416.6 µs   mean cycle jitter 34.8 µs
  Python Observer RTT  mean 557.7 µs   mean cycle jitter 49.4 µs
  Observer intrusion   mean 141.0 µs   p95 252.6 µs   max 6.30 ms
                       error 33.9 % (total lag / total RTT)   per packet: median 24.4 %  mean 41.6 %  max 3564.6 %
  Event-loop canary    avg 348.3 µs   p95 1.00 ms   max 6.56 ms
```

## 20261025-224728_go-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 22:51:00
- **Description:** Idle floor 250ep · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-224728_go-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-224728_go-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-224728_go-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1703)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 558.6 µs   p95 1.06 ms   max 3.11 ms
  Kernel Control RTT   mean 390.5 µs   mean cycle jitter 24.4 µs
  Python Observer RTT  mean 488.5 µs   mean cycle jitter 39.0 µs
  Observer intrusion   mean 98.0 µs   p95 274.0 µs   max 4.84 ms
                       error 25.1 % (total lag / total RTT)   per packet: median 14.6 %  mean 28.6 %  max 1437.0 %
  Event-loop canary    avg 282.1 µs   p95 793.6 µs   max 6.20 ms
```

## 20261025-225103_rs-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 22:54:35
- **Description:** Idle floor 250ep · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-225103_rs-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-225103_rs-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-225103_rs-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1702)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 901.1 µs   p95 1.38 ms   max 4.95 ms
  Kernel Control RTT   mean 395.6 µs   mean cycle jitter 26.6 µs
  Python Observer RTT  mean 490.8 µs   mean cycle jitter 39.5 µs
  Observer intrusion   mean 95.2 µs   p95 201.7 µs   max 3.66 ms
                       error 24.1 % (total lag / total RTT)   per packet: median 16.9 %  mean 27.2 %  max 1658.4 %
  Event-loop canary    avg 1.18 ms   p95 1.70 ms   max 8.94 ms
```

## 20261025-225438_go-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 22:58:08
- **Description:** Idle floor 25ep · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-225438_go-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-225438_go-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-225438_go-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=170)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 642.9 µs   p95 1.17 ms   max 1.48 ms
  Kernel Control RTT   mean 429.0 µs   mean cycle jitter 28.6 µs
  Python Observer RTT  mean 526.6 µs   mean cycle jitter 40.1 µs
  Observer intrusion   mean 97.6 µs   p95 116.9 µs   max 2.37 ms
                       error 22.7 % (total lag / total RTT)   per packet: median 15.6 %  mean 28.9 %  max 1127.2 %
  Event-loop canary    avg 279.8 µs   p95 649.5 µs   max 5.16 ms
```

## 20261025-225813_rs-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 23:01:43
- **Description:** Idle floor 25ep · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-225813_rs-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-225813_rs-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-225813_rs-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=170)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 1.13 ms   p95 1.55 ms   max 2.06 ms
  Kernel Control RTT   mean 427.8 µs   mean cycle jitter 32.4 µs
  Python Observer RTT  mean 513.9 µs   mean cycle jitter 38.5 µs
  Observer intrusion   mean 86.0 µs   p95 178.0 µs   max 1.17 ms
                       error 20.1 % (total lag / total RTT)   per packet: median 15.8 %  mean 23.5 %  max 350.7 %
  Event-loop canary    avg 1.17 ms   p95 1.45 ms   max 5.80 ms
```

## 20261025-230149_py-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 23:05:18
- **Description:** Idle floor 25ep · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=25 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-230149_py-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-230149_py-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-230149_py-sc_25ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=250 replied=250 lost=0 (reader wakeups=172)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 770.5 µs   p95 1.56 ms   max 4.35 ms
  Kernel Control RTT   mean 398.7 µs   mean cycle jitter 27.2 µs
  Python Observer RTT  mean 513.1 µs   mean cycle jitter 31.9 µs
  Observer intrusion   mean 114.4 µs   p95 174.0 µs   max 760.9 µs
                       error 28.7 % (total lag / total RTT)   per packet: median 25.6 %  mean 31.7 %  max 223.3 %
  Event-loop canary    avg 259.5 µs   p95 440.1 µs   max 6.30 ms
```

## 20261025-230524_go-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 23:08:56
- **Description:** Idle floor 250ep · Go single-core
- **Command:** `dashboard run: engine=go cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-230524_go-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-230524_go-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-230524_go-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1707)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 563.0 µs   p95 1.03 ms   max 3.22 ms
  Kernel Control RTT   mean 395.6 µs   mean cycle jitter 25.2 µs
  Python Observer RTT  mean 471.4 µs   mean cycle jitter 32.3 µs
  Observer intrusion   mean 75.8 µs   p95 121.6 µs   max 2.93 ms
                       error 19.2 % (total lag / total RTT)   per packet: median 13.2 %  mean 21.7 %  max 1074.8 %
  Event-loop canary    avg 275.8 µs   p95 765.1 µs   max 5.59 ms
```

## 20261025-230859_rs-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 23:12:31
- **Description:** Idle floor 250ep · Rust single-core
- **Command:** `dashboard run: engine=rust cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-230859_rs-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-230859_rs-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-230859_rs-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1701)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 904.7 µs   p95 1.40 ms   max 3.99 ms
  Kernel Control RTT   mean 425.7 µs   mean cycle jitter 32.9 µs
  Python Observer RTT  mean 508.5 µs   mean cycle jitter 40.2 µs
  Observer intrusion   mean 82.8 µs   p95 112.0 µs   max 3.29 ms
                       error 19.4 % (total lag / total RTT)   per packet: median 16.8 %  mean 21.8 %  max 886.6 %
  Event-loop canary    avg 1.16 ms   p95 1.62 ms   max 5.83 ms
```

## 20261025-231234_py-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor

- **Date:** 2026-10-25 23:16:06
- **Description:** Idle floor 250ep · Python single-core
- **Command:** `dashboard run: engine=python cpu=single_core targets=192.168.70.2 endpoints=250 pings=5 interval=8.0s timeout=2.0s stagger=60.0s cycles=3x60.0s semaphore=15 db=0.0ms hw_timestamps=False`
- **Files:** `20261025-231234_py-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.csv` (per packet), `20261025-231234_py-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor_cycles.csv` (per cycle), `20261025-231234_py-sc_250ep-stg60-sem15-db0-i8-c3x60_192-168-70-2_floor.meta.json`

```text
SUMMARY  packets sent=2500 replied=2500 lost=0 (reader wakeups=1728)
  Loss by cause        no reply 0   reply after the timeout 0   reply in time but read too late 0
  Send lag             mean 802.3 µs   p95 1.58 ms   max 4.33 ms
  Kernel Control RTT   mean 415.8 µs   mean cycle jitter 34.0 µs
  Python Observer RTT  mean 522.3 µs   mean cycle jitter 38.7 µs
  Observer intrusion   mean 106.5 µs   p95 161.9 µs   max 1.77 ms
                       error 25.6 % (total lag / total RTT)   per packet: median 23.5 %  mean 29.0 %  max 666.9 %
  Event-loop canary    avg 322.2 µs   p95 940.1 µs   max 6.35 ms
```
