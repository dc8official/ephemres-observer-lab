"""Turn raw per-packet rows into the numbers, tables and chart data the dashboard shows.

A *run* is a list of packet rows (plain dicts) plus a small ``meta`` dict
(counters that only the prober process knows, such as reader wakeups and the
canary summary).  Everything here is pure Python so it can be tested without
a web server or root privileges.

Packet row keys
    ep, cyc, icmp_id, seq, target     identity of the probe
    tx, krx, urx, hrx                 ns stamps: send, kernel arrival (Clock A),
                                      Python read (Clock B), NIC hardware (other clock)
    batch, wakeup                     packets drained by the same reader wakeup / wakeup id
    k_us, u_us, lag_us                kernel RTT, Python RTT, observer lag (None if lost)
    send_lag_us                       how late the ping was SENT vs its schedule (None in old runs)
    late_krx, late_urx                for a lost ping: the reply that arrived after the timeout, if any

Warm-up cycle: when a run has several cycles per endpoint, cycle 0 is left out of every
statistic (the staggered schedule is still ramping up, so fewer endpoints overlap than in
steady state).  It stays in the saved files.  The terminal runner applies the same rule.
"""
from __future__ import annotations

import csv
import io
import json
import os
import time
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

from server.stats import percentile, rfc3550_jitter

# Histogram buckets for observer lag (upper edges in microseconds).  The low
# buckets show the normal event-loop wake-up floor; the high ones show packets
# that waited behind somebody else's ORM burn.
HIST_EDGES_US = [50, 100, 150, 250, 500, 1000, 2000, 5000, 10000, 25000, 50000]
HIST_LABELS = ["<50 µs", "50-100 µs", "100-150 µs", "150-250 µs", "250-500 µs", "0.5-1 ms",
               "1-2 ms", "2-5 ms", "5-10 ms", "10-25 ms", "25-50 ms", ">50 ms"]


QUANTILES = [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 0.999, 1.0]
MAX_SCATTER = 3000
MAX_BURSTS = 2000
# Below this kernel RTT an error % is not meaningful: an ordinary 100 µs wake-up is already 100 %+ of a
# loopback round trip.  The dashboard greys error % out for such runs and points to the lag in µs instead.
MIN_RTT_FOR_ERROR_US = 100.0


def _burst_windows(bursts: List[list], t0: Optional[int], skip: int) -> List[List[float]]:
    """ORM-work windows as [start_ms, end_ms] on the scatter's time axis (ms since the first measured ping),
    warm-up cycles left out and overlapping windows merged, so the chart can shade when the CPU work ran.
    Each burst is [endpoint, cycle, start_ns, end_ns] (CLOCK_REALTIME, the packets' clock)."""
    if t0 is None:
        return []
    spans = sorted(((b[2] - t0) / 1e6, (b[3] - t0) / 1e6) for b in bursts
                   if b[1] >= skip and b[2] is not None and b[3] is not None and b[3] >= b[2])
    merged: List[List[float]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    if len(merged) > MAX_BURSTS:                     # keep the chart light: evenly thin very long runs
        step = len(merged) / MAX_BURSTS
        merged = [merged[int(i * step)] for i in range(MAX_BURSTS)]
    return [[round(a, 3), round(b, 3)] for a, b in merged]


def _scatter(meas: List[Dict[str, Any]]) -> List[List[float]]:
    """[(ms since the first packet was sent, observer lag in microseconds)] for the timeline plot.
    Large runs are thinned evenly, but the 200 largest lags are always kept so spikes are never lost."""
    if not meas:
        return []
    t0 = min(r["tx"] for r in meas)
    pts = sorted(((r["tx"] - t0) / 1e6, r["lag_us"]) for r in meas)
    if len(pts) > MAX_SCATTER:
        keep = {id(p) for p in sorted(pts, key=lambda p: -p[1])[:200]}
        stride = len(pts) / (MAX_SCATTER - 200)
        thinned = [p for i, p in enumerate(pts) if id(p) in keep or int(i % stride) == 0]
        pts = thinned
    return [[round(t, 2), round(v, 1)] for t, v in pts]


def make_row(ep: int, cyc: int, icmp_id: int, target: str, pkt: list) -> Dict[str, Any]:
    """Build a row from a 'cycle' event packet:
    [seq, tx_ns, kernel_rx_ns, user_rx_ns, hw_rx_ns, batch, wakeup, send_lag_ns]
    (engines older than send-lag recording send only the first 7 fields)."""
    seq, tx, krx, urx, hrx, batch, wakeup = pkt[:7]
    send_lag = pkt[7] if len(pkt) > 7 else None
    row = {"ep": ep, "cyc": cyc, "icmp_id": icmp_id, "seq": seq, "target": target, "tx": tx,
           "krx": krx, "urx": urx, "hrx": hrx, "batch": batch, "wakeup": wakeup,
           "k_us": None, "u_us": None, "lag_us": None,
           "send_lag_us": None if send_lag is None else send_lag / 1e3, "late_krx": None, "late_urx": None}
    if urx is not None:
        row["u_us"] = (urx - tx) / 1e3
    if krx is not None:
        row["k_us"] = (krx - tx) / 1e3
        if urx is not None:
            row["lag_us"] = (urx - krx) / 1e3
    return row


def attach_late(rows: List[Dict[str, Any]], ev: Dict[str, Any]) -> bool:
    """Record a 'late' event (a reply that arrived after its ping timed out) on the lost packet's row.
    Rows are found by (icmp_id, seq), which is unique within a run.  Returns False if no row matches
    (e.g. a warm-up ping, or the cycle has not been reported yet)."""
    for r in reversed(rows):
        if r["icmp_id"] == ev["icmp_id"] and r["seq"] == ev["seq"] and r["urx"] is None:
            r["late_krx"], r["late_urx"] = ev.get("krx"), ev.get("urx")
            return True
    return False


def warmup_cycles(cfg: Optional[Dict[str, Any]]) -> int:
    """How many leading cycles are excluded from the statistics: 1 when a run has several cycles."""
    return 1 if int((cfg or {}).get("cycles") or 1) > 1 else 0


def loss_causes(lost: List[Dict[str, Any]], timeout_s: float) -> Dict[str, int]:
    """Split lost packets by what the kernel saw:
    no_reply      nothing ever came back (real network loss, or the target ignored it)
    after_timeout a reply came, but the kernel received it after the timeout (slow network/target)
    read_late     the kernel received it IN TIME, but the program read it after its timeout fired:
                  a loss caused by the observer, not by the network"""
    t_ns = timeout_s * 1e9
    read_late = sum(1 for r in lost if r.get("late_krx") and r["late_krx"] - r["tx"] <= t_ns)
    late = sum(1 for r in lost if r.get("late_krx"))
    return {"no_reply": len(lost) - late, "after_timeout": late - read_late, "read_late": read_late}


def _mean(xs: Iterable[float]) -> Optional[float]:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def _bucket(lag_us: float) -> int:
    for i, edge in enumerate(HIST_EDGES_US):
        if lag_us < edge:
            return i
    return len(HIST_EDGES_US)


def analyse(rows: List[Dict[str, Any]], meta: Optional[Dict[str, Any]] = None,
            cfg: Optional[Dict[str, Any]] = None, bursts: Optional[List[list]] = None) -> Dict[str, Any]:
    """Summary cards, per-endpoint table, histogram and worst-10 for one run."""
    meta, cfg = meta or {}, cfg or {}
    skip = warmup_cycles(cfg)
    if skip:                              # counters in meta cover the whole run: recount from the rows
        rows = [r for r in rows if r["cyc"] >= skip]
        meta = {k: v for k, v in meta.items() if k not in ("sent", "replied", "reader_calls")}
        meta["reader_calls"] = len({r["wakeup"] for r in rows if r["urx"] is not None and r["wakeup"]}) or None
    got = [r for r in rows if r["u_us"] is not None]
    meas = [r for r in got if r["lag_us"] is not None]
    lags = [r["lag_us"] for r in meas]
    # Error % three ways (see docs/02).  PRIMARY: total lag / total kernel RTT ("what share of all
    # measured time was error"), which no single tiny-RTT packet can dominate.  Then the median of the
    # per-packet errors (a typical reading), then their mean (sensitive to outliers) and max.
    err_rows = [r for r in meas if r["k_us"] and r["k_us"] > 0]
    pcts = [100.0 * r["lag_us"] / r["k_us"] for r in err_rows]
    k_total = sum(r["k_us"] for r in err_rows)
    pct_total = 100.0 * sum(r["lag_us"] for r in err_rows) / k_total if k_total else None

    # ---- per-cycle RFC 3550 jitter (kernel clock vs Python clock) -----------
    cycles: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for r in meas:
        cycles[(r["ep"], r["cyc"])].append(r)
    jk, ju = [], []
    for pk in cycles.values():
        pk.sort(key=lambda r: r["seq"])
        jk.append(rfc3550_jitter([r["k_us"] for r in pk]))
        ju.append(rfc3550_jitter([r["u_us"] for r in pk]))

    # ---- per endpoint --------------------------------------------------------
    by_ep: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_ep[r["ep"]].append(r)
    endpoints = []
    for ep, rs in by_ep.items():
        m = [r for r in rs if r["lag_us"] is not None]
        if not m:
            endpoints.append({"ep": ep, "target": rs[0]["target"], "sent": len(rs), "replied": 0,
                              "kernel_us": None, "python_us": None, "lag_mean_us": None, "lag_max_us": None,
                              "pct_total": None, "wakeups": None, "max_batch": None})
            continue
        kmean, umean = _mean(r["k_us"] for r in m), _mean(r["u_us"] for r in m)
        lmean = _mean(r["lag_us"] for r in m)
        endpoints.append({
            "ep": ep, "target": rs[0]["target"], "sent": len(rs), "replied": len(m),
            "kernel_us": kmean, "python_us": umean, "lag_mean_us": lmean,
            "lag_max_us": max(r["lag_us"] for r in m),
            "pct_total": 100.0 * lmean / kmean if kmean else None,     # the endpoint's total lag / total RTT
            "wakeups": (len({r["wakeup"] for r in m}) if any(r["batch"] for r in m) else None),
            "max_batch": (max(r["batch"] for r in m) or None)})
    endpoints.sort(key=lambda e: (e["lag_mean_us"] is None, -(e["lag_mean_us"] or 0)))

    # ---- lag percentiles and timeline ---------------------------------------
    lag_sorted = sorted(lags)
    quantiles = [{"q": q, "lag_us": percentile(lag_sorted, q)} for q in QUANTILES] if lag_sorted else []
    scatter = _scatter(meas)
    t0 = min((r["tx"] for r in meas), default=None)          # the scatter's time origin
    k_sorted = sorted(r["k_us"] for r in meas if r["k_us"] is not None)
    k_median = percentile(k_sorted, 0.5) if k_sorted else None

    # ---- histogram -----------------------------------------------------------
    hist = [0] * (len(HIST_EDGES_US) + 1)
    for v in lags:
        hist[_bucket(v)] += 1

    sent = meta.get("sent", len(rows))
    replied = meta.get("replied", len(got))
    reader_calls = meta.get("reader_calls")
    causes = loss_causes([r for r in rows if r["urx"] is None], float(cfg.get("timeout_s") or 2.0))
    send = sorted(r["send_lag_us"] for r in rows if r.get("send_lag_us") is not None)
    return {
        "summary": {
            "sent": sent, "replied": replied, "lost": max(0, sent - replied),
            "lost_no_reply": causes["no_reply"], "lost_after_timeout": causes["after_timeout"],
            "lost_read_late": causes["read_late"],
            "n_lag": len(lags), "warmup_cycles_excluded": skip,
            "kernel_rtt_median_us": k_median,
            "rtt_too_small": k_median is not None and k_median < MIN_RTT_FOR_ERROR_US,
            "send_lag_mean_us": _mean(send), "send_lag_p95_us": percentile(send, 0.95) if send else None,
            "send_lag_max_us": send[-1] if send else None,
            "kernel_rtt_mean_us": _mean(r["k_us"] for r in meas),
            "python_rtt_mean_us": _mean(r["u_us"] for r in meas),
            "lag_mean_us": _mean(lags),
            "lag_p50_us": percentile(lag_sorted, 0.50) if lags else None,
            "lag_p95_us": percentile(lag_sorted, 0.95) if lags else None,
            "lag_p99_us": percentile(lag_sorted, 0.99) if lags else None,
            "lag_max_us": max(lags) if lags else None,
            "pct_total": pct_total, "pct_median": percentile(sorted(pcts), 0.5) if pcts else None,
            "pct_mean": _mean(pcts), "pct_max": max(pcts) if pcts else None,
            "jitter_kernel_us": _mean(jk), "jitter_python_us": _mean(ju),
            "reader_calls": reader_calls,
            "packets_per_wakeup": (replied / reader_calls) if reader_calls else None,
            "max_batch": (max((r["batch"] for r in meas), default=0) or None),
            "canary": meta.get("canary"),
            "ipc_ms_mean": meta.get("ipc_ms_mean"), "ipc_ms_max": meta.get("ipc_ms_max"),
            "emit_us_per_event": ((meta["emit_us_total"] / meta["emit_n"])
                                  if meta.get("emit_n") else None),
        },
        "endpoints": endpoints,
        "worst": endpoints[:10],
        "hist": {"labels": HIST_LABELS, "counts": hist},
        "quantiles": quantiles,
        # Kernel RTT (Clock A) at the same percentiles: the external observer effect shows up here, as the
        # probe load itself slowing the target or the wire, independent of when the program read the reply.
        "kernel_quantiles": [{"q": q, "rtt_us": percentile(k_sorted, q)} for q in QUANTILES] if k_sorted else [],
        "scatter": scatter,
        "bursts": _burst_windows(bursts or [], t0, skip),
    }


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------
PACKET_FIELDS = ["endpoint", "cycle", "icmp_id", "icmp_seq", "target_ip", "lost", "tx_realtime_ns",
                 "kernel_rx_ns", "user_rx_ns", "hw_rx_ns", "kernel_rtt_us", "user_rtt_us",
                 "observer_lag_us", "reader_batch", "wakeup_id", "send_lag_us", "late_kernel_rx_ns", "late_user_rx_ns",
                 "engine", "cpu_mode"]
ENDPOINT_FIELDS = ["endpoint", "target_ip", "sent", "replied", "kernel_rtt_mean_us", "python_rtt_mean_us",
                   "intrusion_mean_us", "intrusion_max_us", "error_pct_total", "reader_wakeups", "max_queue_depth"]


def packets_csv(rows: List[Dict[str, Any]], cfg: Optional[Dict[str, Any]] = None) -> str:
    cfg = cfg or {}
    engine, cpu = cfg.get("engine") or "python", cfg.get("cpu_mode") or "single_core"
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(PACKET_FIELDS)
    for r in rows:
        w.writerow([r["ep"], r["cyc"], r["icmp_id"], r["seq"], r["target"], int(r["urx"] is None), r["tx"],
                    r["krx"], r["urx"], r["hrx"], r["k_us"], r["u_us"], r["lag_us"], r["batch"], r["wakeup"],
                    r.get("send_lag_us"), r.get("late_krx"), r.get("late_urx"), engine, cpu])
    return buf.getvalue()


def endpoints_csv(an: Dict[str, Any]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(ENDPOINT_FIELDS)
    for e in an["endpoints"]:
        w.writerow([e["ep"], e["target"], e["sent"], e["replied"], e["kernel_us"], e["python_us"],
                    e["lag_mean_us"], e["lag_max_us"], e["pct_total"], e["wakeups"], e["max_batch"]])
    return buf.getvalue()


def cycles_csv(rows: List[Dict[str, Any]]) -> str:
    """Per endpoint-cycle statistics (same idea as the CLI's *_cycles.csv)."""
    from server.stats import compute_stats
    groups: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[(r["ep"], r["cyc"])].append(r)
    buf = io.StringIO()
    w = csv.writer(buf)
    head = ["endpoint", "cycle", "target_ip", "icmp_id"] + [
        f"{n}_{m}" for n in ("kernel", "user", "lag") for m in
        ("min_us", "max_us", "avg_us", "p95_us", "std_us", "jitter_us")]
    w.writerow(head)
    for (ep, cyc), rs in sorted(groups.items()):
        rs.sort(key=lambda r: r["seq"])
        m = [r for r in rs if r["lag_us"] is not None]
        row: List[Any] = [ep, cyc, rs[0]["target"], rs[0]["icmp_id"]]
        for key in ("k_us", "u_us", "lag_us"):
            st = compute_stats([r[key] for r in m])
            row += [st.min, st.max, st.avg, st.p95, st.std_dev, st.jitter]
        w.writerow(row)
    return buf.getvalue()


def _pct(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v:.1f} %"


def _us(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    return f"{v / 1000:.2f} ms" if abs(v) >= 1000 else f"{v:.1f} µs"


def markdown(name: str, cfg: Dict[str, Any], an: Dict[str, Any], meta: Dict[str, Any]) -> str:
    """A run's analysis as a Markdown report (the dashboard's "export report")."""
    s = an["summary"]
    c = s.get("canary") or {}
    lines = [f"# {name}", "",
             f"- **Engine:** {cfg.get('engine') or 'python'}  |  **CPU mode:** {cfg.get('cpu_mode') or 'single_core'}",
             f"- **Targets:** {cfg.get('targets')}  |  **Virtual endpoints:** {cfg.get('virtual_endpoints')}  |  "
             f"**Pings/cycle:** {cfg.get('pings_per_cycle')}",
             f"- **Stagger window:** {cfg.get('stagger_window_s')} s "
             f"({'burst' if not cfg.get('stagger_window_s') else 'staggered'})  |  "
             f"**db_write_semaphore:** {cfg.get('db_write_semaphore')}  |  **Simulated DB:** {cfg.get('simulated_db_ms')} ms"]
    if cfg.get("note"):
        lines.append(f"- **Note:** {cfg['note']}")
    lines += ["", "## Summary", "", "| Metric | Value |", "|---|---|",
              f"| Packets sent / replied / lost | {s['sent']} / {s['replied']} / {s['lost']} |",
              f"| Kernel Control RTT (mean) | {_us(s['kernel_rtt_mean_us'])} |",
              f"| Python Observer RTT (mean) | {_us(s['python_rtt_mean_us'])} |",
              f"| Observer intrusion mean / p95 / max | {_us(s['lag_mean_us'])} / {_us(s['lag_p95_us'])} / {_us(s['lag_max_us'])} |",
              f"| Error: total lag ÷ total kernel RTT (primary) | {_pct(s.get('pct_total'))} |",
              f"| Error per packet: median / mean / max | {_pct(s.get('pct_median'))} / {_pct(s['pct_mean'])} / {_pct(s['pct_max'])} |",
              f"| Cycle jitter, kernel vs Python | {_us(s['jitter_kernel_us'])} vs {_us(s['jitter_python_us'])} |",
              f"| Lost: no reply / reply after timeout / read too late | {s.get('lost_no_reply')} / {s.get('lost_after_timeout')} / {s.get('lost_read_late')} |",
              f"| Send lag (ping sent late vs schedule) mean / p95 / max | {_us(s.get('send_lag_mean_us'))} / {_us(s.get('send_lag_p95_us'))} / {_us(s.get('send_lag_max_us'))} |",
              f"| Reader wakeups vs packets | {'n/a' if s['reader_calls'] is None else s['reader_calls']} vs {s['replied']} |",
              f"| ORM offload overhead (IPC + pool wait) mean / max | {_us(None if s.get('ipc_ms_mean') is None else s['ipc_ms_mean'] * 1000)} / "
              f"{_us(None if s.get('ipc_ms_max') is None else s['ipc_ms_max'] * 1000)} |",
              f"| Canary avg / p95 / max lag | {_us(c.get('avg_lag_us'))} / {_us(c.get('p95_lag_us'))} / {_us(c.get('max_lag_us'))} |",
              "", "## Worst-hit endpoints (top 10 by mean intrusion)", "",
              "| Endpoint | Kernel RTT | Python RTT | Intrusion (mean) | Intrusion (max) | % Error | Reader wakeups | Max queue depth |",
              "|---|---|---|---|---|---|---|---|"]
    for e in an["worst"]:
        lines.append(f"| {e['ep']} | {_us(e['kernel_us'])} | {_us(e['python_us'])} | {_us(e['lag_mean_us'])} | "
                     f"{_us(e['lag_max_us'])} | {_pct(e['pct_total'])} | "
                     f"{'n/a' if e['wakeups'] is None else e['wakeups']} | {e['max_batch'] or 'n/a'} |")
    lines += ["", "## Intrusion distribution (packets)", "", "| Bucket | Packets |", "|---|---|"]
    lines += [f"| {l} | {n} |" for l, n in zip(an["hist"]["labels"], an["hist"]["counts"])]
    lines += ["", "## All endpoints (sorted by mean intrusion)", "",
              "| Endpoint | Kernel RTT | Python RTT | Intrusion (mean) | % Error | Wakeups |", "|---|---|---|---|---|---|"]
    for e in an["endpoints"]:
        lines.append(f"| {e['ep']} | {_us(e['kernel_us'])} | {_us(e['python_us'])} | {_us(e['lag_mean_us'])} | "
                     f"{_pct(e['pct_total'])} | {'n/a' if e['wakeups'] is None else e['wakeups']} |")
    if s.get("rtt_too_small"):
        lines += ["", f"> **Error % is not meaningful for this run:** the median kernel RTT ({_us(s.get('kernel_rtt_median_us'))}) "
                      f"is under {MIN_RTT_FOR_ERROR_US:g} µs, so even an ordinary wake-up is a large percentage. Judge the lag in µs."]
    fl = s.get("floor")
    if fl:
        lines += ["", f"> **Idle floor** (same setup, no ORM work: `{fl['name']}`): intrusion mean {_us(fl.get('lag_mean_us'))}, "
                      f"p95 {_us(fl.get('lag_p95_us'))}. This run above the floor: mean {_us(_above(s, 'lag_mean_us'))}, "
                      f"p95 {_us(_above(s, 'lag_p95_us'))}, p99 {_us(_above(s, 'lag_p99_us'))}."]
    if s.get("warmup_cycles_excluded"):
        lines += ["", f"> Cycle 0 of {cfg.get('cycles')} is a warm-up and is excluded from every figure above "
                      f"(it is still in the CSV files)."]
    host = meta.get("host") or {}
    if host.get("warnings"):
        lines += ["", "## Host conditions during the run", ""] + [f"- {w}" for w in host["warnings"]]
    if meta.get("canary_note"):
        lines += ["", f"> {meta['canary_note']}"]
    return "\n".join(lines) + "\n"


def _num(v: Any, digits: int = 1) -> str:
    return "n/a" if v is None else (f"{v:.{digits}f}" if isinstance(v, float) else str(v))


COMPARE_FIELDS = ["virtual_endpoints", "stagger_window_s", "db_write_semaphore", "simulated_db_ms",
                  "pings_per_cycle", "interval_s", "cycles", "cycle_length_s", "timeout_s", "hw_timestamps", "targets"]
# Settings older runs did not record, and the value they implicitly had.  A missing value is compared as
# this default so an old single-cycle run is not flagged against a new one with cycles=1.
COMPARE_DEFAULTS = {"cycles": 1, "timeout_s": 2.0, "hw_timestamps": False}


def _setting(v: Any) -> str:
    """Canonical text of a setting, so 24, 24.0 and "24" compare equal (older meta.json files
    store whole numbers, the dashboard stores floats).  Non-numeric values stay as they are."""
    if isinstance(v, bool) or v is None:
        return str(v)
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return str(v)


def _is_floor(cfg: Dict[str, Any]) -> bool:
    return cfg.get("role") == "floor" or (cfg.get("role") is None and cfg.get("tag") == "floor")


def differing_settings(runs: List[Dict[str, Any]]) -> List[str]:
    """Settings that are not identical across the runs (so the comparison is not like for like).
    Idle-floor runs differ on purpose (0 ms ORM) and are left out when test runs are present."""
    tests = [r for r in runs if not _is_floor(r["cfg"])]
    runs = tests or runs
    out = []
    for f in COMPARE_FIELDS:
        vals = {"n/a" if f == "cycle_length_s" and int(r["cfg"].get("cycles") or 1) <= 1   # only matters with several cycles
                else _setting(r["cfg"].get(f, COMPARE_DEFAULTS.get(f))) for r in runs}
        if len(vals) > 1:
            out.append(f"{f}: " + " / ".join(sorted(vals)))
    return out


# (label, formatted value, raw number used for the ratio column; None = not a ratio row)
def _metric_rows(s: Dict[str, Any]):
    c = s.get("canary") or {}
    ms = lambda v: None if v is None else v * 1000
    return [
        ("Packets sent / replied / lost", f"{s['sent']} / {s['replied']} / {s['lost']}", None),
        ("Lost: no reply / reply after timeout / read too late",
         f"{s.get('lost_no_reply', 'n/a')} / {s.get('lost_after_timeout', 'n/a')} / {s.get('lost_read_late', 'n/a')}", None),
        ("Packets with an observer-lag measurement", _num(s.get("n_lag")), None),
        ("Kernel Control RTT (mean)", _us(s["kernel_rtt_mean_us"]), s["kernel_rtt_mean_us"]),
        ("Observer RTT (mean)", _us(s["python_rtt_mean_us"]), s["python_rtt_mean_us"]),
        ("Observer intrusion mean", _us(s["lag_mean_us"]), s["lag_mean_us"]),
        ("Observer intrusion p50", _us(s.get("lag_p50_us")), s.get("lag_p50_us")),
        ("Observer intrusion p95", _us(s["lag_p95_us"]), s["lag_p95_us"]),
        ("Observer intrusion p99", _us(s.get("lag_p99_us")), s.get("lag_p99_us")),
        ("Observer intrusion max", _us(s["lag_max_us"]), s["lag_max_us"]),
        # Above the idle floor: this run minus the most recent no-ORM run of the same setup (n/a without one).
        ("Intrusion above idle floor, mean", _us(_above(s, "lag_mean_us")), _above(s, "lag_mean_us")),
        ("Intrusion above idle floor, p95", _us(_above(s, "lag_p95_us")), _above(s, "lag_p95_us")),
        ("Intrusion above idle floor, p99", _us(_above(s, "lag_p99_us")), _above(s, "lag_p99_us")),
        ("Error %: total lag ÷ total kernel RTT (primary)", _num(s.get("pct_total")), s.get("pct_total")),
        ("Error %, per packet: median", _num(s.get("pct_median")), s.get("pct_median")),
        ("Error %, per packet: mean", _num(s["pct_mean"]), s["pct_mean"]),
        ("Error %, per packet: max", _num(s["pct_max"]), s["pct_max"]),
        ("Cycle jitter, kernel clock", _us(s["jitter_kernel_us"]), s["jitter_kernel_us"]),
        ("Cycle jitter, observer clock", _us(s["jitter_python_us"]), s["jitter_python_us"]),
        ("Reader wakeups", _num(s["reader_calls"]), s["reader_calls"]),
        ("Max queue depth (packets per wakeup)", _num(s["max_batch"]), s["max_batch"]),
        ("Send lag (ping sent late vs schedule) mean", _us(s.get("send_lag_mean_us")), s.get("send_lag_mean_us")),
        ("Send lag p95", _us(s.get("send_lag_p95_us")), s.get("send_lag_p95_us")),
        ("Send lag max", _us(s.get("send_lag_max_us")), s.get("send_lag_max_us")),
        ("ORM offload overhead (IPC + pool wait) mean", _us(ms(s.get("ipc_ms_mean"))), ms(s.get("ipc_ms_mean"))),
        ("Canary max lag", _us(c.get("max_lag_us")), c.get("max_lag_us")),
        ("Canary avg lag", _us(c.get("avg_lag_us")), c.get("avg_lag_us")),
    ]


def _above(s: Dict[str, Any], key: str) -> Optional[float]:
    """This run's statistic minus the same statistic of its idle-floor run (None without a floor run).
    Percentiles are subtracted percentile by percentile, so the result can be slightly negative from noise."""
    f = s.get("floor") or {}
    return None if s.get(key) is None or f.get(key) is None else s[key] - f[key]


def _col_label(r: Dict[str, Any]) -> str:
    c = r["cfg"]
    return f"{c.get('engine') or 'python'} / {c.get('cpu_mode') or 'single_core'}" + (" / idle floor" if _is_floor(c) else "")


def compare_markdown(runs: List[Dict[str, Any]]) -> str:
    """Side-by-side table for any number of runs.  Each item: {"name", "cfg", "analysis", "meta"}.
    The first run is the baseline: every other column shows its value as a multiple of the baseline."""
    letters = [chr(ord("A") + i) for i in range(len(runs))]
    out = ["# Run comparison", ""]
    for l, r in zip(letters, runs):
        c = r["cfg"]
        out.append(f"- **{l}** `{r['name']}` - {_col_label(r)}; {c.get('virtual_endpoints')} endpoints, "
                   f"stagger {c.get('stagger_window_s')} s, semaphore {c.get('db_write_semaphore')}, "
                   f"DB {c.get('simulated_db_ms')} ms" + (f"  \n  *Purpose:* {c['note']}" if c.get("note") else ""))
    diffs = differing_settings(runs)
    if diffs:
        out += ["", "> **Not like for like.** These settings differ between the runs: " + "; ".join(diffs)]
    out += ["", "| Metric | " + " | ".join(f"{l} ({_col_label(r)})" for l, r in zip(letters, runs)) + " |",
            "|---|" + "---|" * len(runs)]
    tables = [_metric_rows(r["analysis"]["summary"]) for r in runs]
    for i, (label, _v, _raw) in enumerate(tables[0]):
        cells = []
        base = tables[0][i][2]
        for j, t in enumerate(tables):
            _l, val, raw = t[i]
            if j > 0 and raw is not None and base:
                val += f" ({raw / base:.2f}x)"
            cells.append(val)
        out.append(f"| {label} | " + " | ".join(cells) + " |")
    out += ["", "Multiples in brackets are relative to run A. 'Observer' means the runtime's own user-space clock "
            "(Python, Go or Rust). Timer granularity differs between runtimes, so compare canary *increases* "
            "between engines, not absolute levels.", ""]
    return "\n".join(out)


def group_key(cfg: Dict[str, Any]) -> str:
    """Runs that are repeats of each other: same batch series, engine, CPU mode and role. A run outside a
    series is its own group."""
    if not cfg.get("series_id"):
        return ""
    return f"{cfg['series_id']}|{cfg.get('engine') or 'python'}|{cfg.get('cpu_mode') or 'single_core'}|{cfg.get('role') or 'test'}"


def combine(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group repeated runs. Each group: name, cfg (of its first run), n, and for every metric row of the
    comparison: the median, min and max over the group's runs (None where no run has a value)."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for i, r in enumerate(runs):
        groups.setdefault(group_key(r["cfg"]) or f"single-{i}", []).append(r)
    out = []
    for members in groups.values():
        tables = [_metric_rows(m["analysis"]["summary"]) for m in members]
        rows = []
        for i, (label, text, _raw) in enumerate(tables[0]):
            vals = sorted(t[i][2] for t in tables if t[i][2] is not None)
            rows.append((label, text, (percentile(vals, 0.5), vals[0], vals[-1]) if vals else None))
        out.append({"name": members[0]["name"], "cfg": members[0]["cfg"], "n": len(members), "rows": rows})
    return out


def compare_combined_markdown(runs: List[Dict[str, Any]]) -> str:
    """Comparison with repeats combined: one column per group, each cell 'median (min-max)'."""
    gs = combine(runs)
    letters = [chr(ord("A") + i) for i in range(len(gs))]
    out = ["# Run comparison (repeats combined)", ""]
    for l, g in zip(letters, gs):
        c = g["cfg"]
        out.append(f"- **{l}** {_col_label(g)} x{g['n']} run(s)" + (f", series `{c['series_id']}`" if c.get("series_id") else "")
                   + (f"  \n  *Purpose:* {c['note']}" if c.get("note") else ""))
    out += ["", "| Metric | " + " | ".join(f"{l} ({_col_label(g)}, n={g['n']})" for l, g in zip(letters, gs)) + " |",
            "|---|" + "---|" * len(gs)]
    for i, (label, _t, _r) in enumerate(gs[0]["rows"]):
        cells = []
        for g in gs:
            label_i, text, stat = g["rows"][i]
            if stat is None or g["n"] == 1:
                cells.append(text)
            else:
                med, lo, hi = stat
                fmt = (lambda v: _num(v)) if "%" in label or "Reader" in label or "depth" in label else _us
                cells.append(f"{fmt(med)} ({fmt(lo)} to {fmt(hi)})")
        out.append(f"| {label} | " + " | ".join(cells) + " |")
    out += ["", "Each cell is the median over the group's repeated runs, with the lowest and highest run in brackets. "
            "A difference between groups is only meaningful when their ranges do not overlap.", ""]
    return "\n".join(out)


def compare_csv(runs: List[Dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["metric"] + [r["name"] for r in runs])
    w.writerow(["engine / cpu mode"] + [_col_label(r) for r in runs])
    w.writerow(["note (what the run checks)"] + [r["cfg"].get("note") or "" for r in runs])
    tables = [_metric_rows(r["analysis"]["summary"]) for r in runs]
    for i, (label, _v, _raw) in enumerate(tables[0]):
        # raw number when the metric has one (machine-readable), otherwise the formatted text
        w.writerow([label] + [t[i][1] if t[i][2] is None else t[i][2] for t in tables])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Persistence (test_results/)
# ---------------------------------------------------------------------------
def save_run(results_dir: str, base: str, cfg: Dict[str, Any], meta: Dict[str, Any],
             rows: List[Dict[str, Any]], an: Dict[str, Any]) -> str:
    """Write <base>.csv, <base>_cycles.csv, <base>.meta.json and append to INDEX.md."""
    os.makedirs(results_dir, exist_ok=True)
    with open(os.path.join(results_dir, base + ".csv"), "w", newline="") as f:
        f.write(packets_csv(rows, cfg))
    with open(os.path.join(results_dir, base + "_cycles.csv"), "w", newline="") as f:
        f.write(cycles_csv(rows))
    with open(os.path.join(results_dir, base + ".meta.json"), "w") as f:
        json.dump({"config": cfg, "meta": meta, "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}, f, indent=1)
    s = an["summary"]
    c = s.get("canary") or {}
    cmd = (f"dashboard run: engine={cfg.get('engine') or 'python'} cpu={cfg.get('cpu_mode') or 'single_core'} "
           f"targets={cfg.get('targets')} endpoints={cfg.get('virtual_endpoints')} pings={cfg.get('pings_per_cycle')} "
           f"interval={cfg.get('interval_s')}s timeout={cfg.get('timeout_s', 2.0)}s stagger={cfg.get('stagger_window_s')}s "
           f"cycles={cfg.get('cycles', 1)}x{cfg.get('cycle_length_s')}s semaphore={cfg.get('db_write_semaphore')} "
           f"db={cfg.get('simulated_db_ms')}ms hw_timestamps={cfg.get('hw_timestamps', False)}")
    desc = cfg.get("note") or (f"{'Burst' if not cfg.get('stagger_window_s') else 'Staggered'} "
                               f"{cfg.get('engine') or 'python'} ({cfg.get('cpu_mode') or 'single_core'}) run from the web dashboard")
    with open(os.path.join(results_dir, "INDEX.md"), "a") as f:
        f.write(f"\n## {base}\n\n- **Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n- **Description:** {desc}\n"
                f"- **Command:** `{cmd}`\n- **Files:** `{base}.csv` (per packet), `{base}_cycles.csv` (per cycle), "
                f"`{base}.meta.json`\n\n```text\n"
                f"SUMMARY  packets sent={s['sent']} replied={s['replied']} lost={s['lost']} "
                f"(reader wakeups={s['reader_calls']})\n"
                f"  Loss by cause        no reply {s.get('lost_no_reply')}   reply after the timeout {s.get('lost_after_timeout')}   "
                f"reply in time but read too late {s.get('lost_read_late')}\n"
                f"  Send lag             mean {_us(s.get('send_lag_mean_us'))}   p95 {_us(s.get('send_lag_p95_us'))}   max {_us(s.get('send_lag_max_us'))}\n"
                f"  Kernel Control RTT   mean {_us(s['kernel_rtt_mean_us'])}   mean cycle jitter {_us(s['jitter_kernel_us'])}\n"
                f"  Python Observer RTT  mean {_us(s['python_rtt_mean_us'])}   mean cycle jitter {_us(s['jitter_python_us'])}\n"
                f"  Observer intrusion   mean {_us(s['lag_mean_us'])}   p95 {_us(s['lag_p95_us'])}   max {_us(s['lag_max_us'])}\n"
                f"                       error {_pct(s.get('pct_total'))} (total lag / total RTT)   per packet: median "
                f"{_pct(s.get('pct_median'))}  mean {_pct(s['pct_mean'])}  max {_pct(s['pct_max'])}\n"
                f"  Event-loop canary    avg {_us(c.get('avg_lag_us'))}   p95 {_us(c.get('p95_lag_us'))}   max {_us(c.get('max_lag_us'))}\n"
                f"```\n")
    return base


RUN_SUFFIXES = (".csv", "_cycles.csv", ".meta.json")


def trash_run(results_dir: str, base: str, trash_dir: str) -> List[str]:
    """Move a saved run out of the results folder into ``trash_dir``: its files, and its INDEX.md entry (appended to
    the trash folder's own INDEX.md, so moving the files back and pasting the entry restores the run exactly).
    Returns the names of the files moved. Nothing is erased; delete the trash folder to make it permanent."""
    if not base or os.sep in base or base.startswith("."):
        raise ValueError(f"not a run name: {base!r}")
    os.makedirs(trash_dir, exist_ok=True)
    moved = []
    for suffix in RUN_SUFFIXES:
        src = os.path.join(results_dir, base + suffix)
        if os.path.exists(src):
            os.replace(src, os.path.join(trash_dir, base + suffix))
            moved.append(base + suffix)
    ip = os.path.join(results_dir, "INDEX.md")
    if os.path.exists(ip):
        with open(ip) as f:
            text = f.read()
        kept, removed = _split_index_entry(text, base)
        if removed:
            with open(ip, "w") as f:
                f.write(kept)
            with open(os.path.join(trash_dir, "INDEX.md"), "a") as f:
                f.write(removed)
    return moved


def _split_index_entry(text: str, base: str):
    """(INDEX.md without the entry for ``base``, the entry itself). An entry runs from its '## <base>' heading
    (the heading may carry a remark after the name) to the next '## ' heading."""
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.startswith("## ") and l[3:].split()[:1] == [base]), None)
    if start is None:
        return text, ""
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    # (each entry already ends with the blank line before the next heading, so nothing before it is taken)
    return "\n".join(lines[:start] + lines[end:]), "\n".join(lines[start:end]) + "\n"


def update_note(results_dir: str, base: str, note: str) -> None:
    """Change the note (what the run was checking) of a saved run: in its .meta.json and in the
    Description line of its INDEX.md entry, so every place that shows it stays in agreement."""
    mp = os.path.join(results_dir, base + ".meta.json")
    if os.path.exists(mp):
        with open(mp) as f:
            j = json.load(f)
        j.setdefault("config", {})["note"] = note
        with open(mp, "w") as f:
            json.dump(j, f, indent=1)
    ip = os.path.join(results_dir, "INDEX.md")
    if not os.path.exists(ip):
        return
    with open(ip) as f:
        lines = f.read().split("\n")
    inside = False
    for i, line in enumerate(lines):
        if line.startswith("## "):
            inside = line[3:].strip() == base
        elif inside and line.startswith("- **Description:**"):
            lines[i] = "- **Description:** " + (note.replace("\n", " ") or "(no note)")
            break
    with open(ip, "w") as f:
        f.write("\n".join(lines))


def _f(v: str) -> Optional[float]:
    return float(v) if v not in ("", None) else None


def _i(v: str) -> Optional[int]:
    return int(v) if v not in ("", None) else None


def load_rows(path: str) -> List[Dict[str, Any]]:
    """Read a per-packet CSV written by the CLI or the dashboard."""
    rows = []
    with open(path, newline="") as f:
        for d in csv.DictReader(f):
            rows.append({"ep": int(d["endpoint"]), "cyc": int(d["cycle"]), "icmp_id": int(d["icmp_id"]),
                         "seq": int(d["icmp_seq"]), "target": d["target_ip"], "tx": _i(d["tx_realtime_ns"]),
                         "krx": _i(d["kernel_rx_ns"]), "urx": _i(d["user_rx_ns"]), "hrx": _i(d.get("hw_rx_ns")),
                         "batch": _i(d.get("reader_batch")) or 0, "wakeup": _i(d.get("wakeup_id")) or 0,
                         "k_us": _f(d["kernel_rtt_us"]), "u_us": _f(d["user_rtt_us"]),
                         "lag_us": _f(d["observer_lag_us"]), "send_lag_us": _f(d.get("send_lag_us")),
                         "late_krx": _i(d.get("late_kernel_rx_ns")), "late_urx": _i(d.get("late_user_rx_ns"))})
    return rows


def list_saved(results_dir: str) -> List[str]:
    """Base names (no extension) of per-packet CSVs in the results folder."""
    if not os.path.isdir(results_dir):
        return []
    return sorted(f[:-4] for f in os.listdir(results_dir)
                  if f.endswith(".csv") and not f.endswith("_cycles.csv"))
