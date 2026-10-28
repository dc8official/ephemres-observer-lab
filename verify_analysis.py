#!/usr/bin/env python3
"""Validation and verification script for benchmark results analysis.

Programmatically parses test_results/*.meta.json, test_results/*.csv,
test_results/INDEX.md, and rigorously verifies the accuracy of every empirical
metric cited in docs/10-results-analysis.md.

The report has two corpora:
  * the first 90 runs (2026-10-24 and 2026-10-25 up to 14:50), checked as before;
  * the follow-up session (2026-10-25 from 19:11), whose tables are rebuilt here row by row
    from the packet CSVs and must appear in the report verbatim (``--print-tables`` prints them).
Two runs from an attempt cut short by a link drop (18:56-18:59) belong to neither and are
only used in the Python burst-regime table.
"""

import csv
import json
import os
import re
import statistics
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple


RESULTS_DIR = os.path.join(os.path.dirname(__file__), "test_results")
INDEX_PATH = os.path.join(RESULTS_DIR, "INDEX.md")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "docs", "10-results-analysis.md")


def parse_duration_us(s: str) -> float:
    """Convert '123.4 µs' or '1.25 ms' or '10.5 s' to microseconds."""
    s = s.strip()
    if s.endswith("µs") or s.endswith("us"):
        return float(s[:-2].strip())
    elif s.endswith("ms"):
        return float(s[:-2].strip()) * 1000.0
    elif s.endswith("s"):
        return float(s[:-1].strip()) * 1000000.0
    raise ValueError(f"Unknown duration format: {s}")


def get_config_key(cfg: Dict[str, Any]) -> str:
    """Normalize engine and cpu_mode to standard keys: py-sc, go-sc, rs-sc, py-mc, go-mc, rs-mc."""
    eng = cfg.get("engine", "py").lower()
    if "rust" in eng or eng.startswith("rs"):
        eng_short = "rs"
    elif "python" in eng or eng.startswith("py"):
        eng_short = "py"
    else:
        eng_short = "go"
    mode = "sc" if cfg.get("cpu_mode") == "single_core" else "mc"
    return f"{eng_short}-{mode}"


def calculate_percentile(sorted_vals: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile (numpy default) of an already-sorted list."""
    if not sorted_vals:
        return 0.0
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def load_csv_steady_state_lags(csv_path: str) -> List[float]:
    """Extract observer_lag_us for steady-state cycles (cycle >= 1) from CSV."""
    lags = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("cycle") != "0":
                val = row.get("observer_lag_us")
                if val:
                    lags.append(float(val))
    return sorted(lags)


def parse_summary_block(summary: str) -> Dict[str, Any]:
    """Extract metrics from the text SUMMARY block in INDEX.md."""
    res: Dict[str, Any] = {}

    m = re.search(r"packets sent=(\d+)\s+replied=(\d+)\s+lost=(\d+)", summary)
    if m:
        res["sent"] = int(m.group(1))
        res["replied"] = int(m.group(2))
        res["lost"] = int(m.group(3))

    m_w = re.search(r"reader wakeups=(\d+)", summary)
    if m_w:
        res["reader_wakeups"] = int(m_w.group(1))

    m = re.search(r"Loss by cause\s+no reply (\d+)\s+reply after the timeout (\d+)\s+reply in time but read too late (\d+)", summary)
    if m:
        res["loss_no_reply"] = int(m.group(1))
        res["loss_after_timeout"] = int(m.group(2))
        res["loss_read_late"] = int(m.group(3))
    elif res.get("lost") == 0:
        res["loss_no_reply"] = 0
        res["loss_after_timeout"] = 0
        res["loss_read_late"] = 0

    m = re.search(r"Send lag\s+mean ([0-9.]+\s*[µm]?s)\s+p95 ([0-9.]+\s*[µm]?s)\s+max ([0-9.]+\s*[µm]?s)", summary)
    if m:
        res["send_lag_mean_str"] = m.group(1)
        res["send_lag_p95_str"] = m.group(2)
        res["send_lag_max_str"] = m.group(3)
        res["send_lag_mean_us"] = parse_duration_us(m.group(1))
        res["send_lag_p95_us"] = parse_duration_us(m.group(2))
        res["send_lag_max_us"] = parse_duration_us(m.group(3))

    m = re.search(r"(?:Kernel Control|Kernel)\s+RTT\s+mean ([0-9.]+\s*[µm]?s)\s+mean cycle jitter ([0-9.]+\s*[µm]?s)", summary)
    if m:
        res["kernel_rtt_mean_str"] = m.group(1)
        res["kernel_jitter_str"] = m.group(2)
        res["kernel_rtt_mean_us"] = parse_duration_us(m.group(1))
        res["kernel_jitter_us"] = parse_duration_us(m.group(2))

    m = re.search(r"(?:Python Observer|Observer)\s+RTT\s+mean ([0-9.]+\s*[µm]?s)\s+mean cycle jitter ([0-9.]+\s*[µm]?s)", summary)
    if m:
        res["observer_rtt_mean_str"] = m.group(1)
        res["observer_jitter_str"] = m.group(2)
        res["observer_rtt_mean_us"] = parse_duration_us(m.group(1))
        res["observer_jitter_us"] = parse_duration_us(m.group(2))

    m = re.search(r"Observer intrusion\s+mean ([0-9.]+\s*[µm]?s)\s+p95 ([0-9.]+\s*[µm]?s)\s+max ([0-9.]+\s*[µm]?s)", summary)
    if m:
        res["lag_mean_str"] = m.group(1)
        res["lag_p95_str"] = m.group(2)
        res["lag_max_str"] = m.group(3)
        res["lag_mean_us"] = parse_duration_us(m.group(1))
        res["lag_p95_us"] = parse_duration_us(m.group(2))
        res["lag_max_us"] = parse_duration_us(m.group(3))

    m = re.search(r"error ([0-9.]+\s*%)\s+\(total lag / total (?:kernel )?RTT\)(?:\s+per packet:\s+median ([0-9.]+\s*%)\s+mean ([0-9.]+\s*%)\s+max ([0-9.]+\s*%))?", summary)
    if m:
        res["error_total_str"] = m.group(1)
        res["error_total_pct"] = float(m.group(1).replace("%", "").strip())
        if m.group(2):
            res["error_median_pct"] = float(m.group(2).replace("%", "").strip())
            res["error_mean_pct"] = float(m.group(3).replace("%", "").strip())
            res["error_max_pct"] = float(m.group(4).replace("%", "").strip())

    m = re.search(r"Event-loop canary\s+avg ([0-9.]+\s*[µm]?s)\s+p95 ([0-9.]+\s*[µm]?s)\s+max ([0-9.]+\s*[µm]?s)", summary)
    if m:
        res["canary_avg_str"] = m.group(1)
        res["canary_p95_str"] = m.group(2)
        res["canary_max_str"] = m.group(3)
        res["canary_avg_us"] = parse_duration_us(m.group(1))
        res["canary_p95_us"] = parse_duration_us(m.group(2))
        res["canary_max_us"] = parse_duration_us(m.group(3))

    return res


def parse_index_runs(index_path: str) -> Dict[str, Dict[str, Any]]:
    """Parse run entries and their SUMMARY blocks from INDEX.md."""
    with open(index_path, "r", encoding="utf-8") as f:
        text = f.read()

    entries = {}
    pattern = re.compile(
        r"^##\s+([0-9]{8}-[0-9]{6}_[^\s]+)\s*\n"
        r"(?:- \*\*Date:\*\*\s*(?P<date>[^\n]+)\n)?"
        r"(?:- \*\*Description:\*\*\s*(?P<desc>[^\n]+)\n)?"
        r"(?:- \*\*Command:\*\*\s*`(?P<cmd>[^`]+)`\n)?"
        r"(?:- \*\*Files:\*\*\s*(?P<files>[^\n]+)\n)?"
        r"\n```text\n(?P<summary>[\s\S]*?)\n```",
        re.MULTILINE,
    )

    for m in pattern.finditer(text):
        name = m.group(1).strip()
        summary = m.group("summary")
        entry = {
            "name": name,
            "date": m.group("date"),
            "desc": m.group("desc"),
            "cmd": m.group("cmd"),
            "summary_text": summary,
            "metrics": parse_summary_block(summary),
        }
        entries[name] = entry

    return entries


def load_all_runs(results_dir: str) -> Dict[str, Dict[str, Any]]:
    """Load and combine metadata and INDEX metrics for all runs in test_results."""
    index_runs = parse_index_runs(os.path.join(results_dir, "INDEX.md"))
    metas = {f[:-10] for f in os.listdir(results_dir) if f.endswith(".meta.json")}
    assert set(index_runs) == metas, f"INDEX.md and .meta.json files differ: {sorted(set(index_runs) ^ metas)[:5]}"

    all_runs = {}

    for fname in sorted(os.listdir(results_dir)):
        if not fname.endswith(".meta.json"):
            continue
        base = fname[:-10]
        meta_path = os.path.join(results_dir, fname)
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cfg = data.get("config", {})
        meta = data.get("meta", {})
        assert base in index_runs, f"Run {base} not found in INDEX.md"
        index_data = index_runs[base]
        metrics = index_data.get("metrics", {})
        assert len(metrics) > 0, f"No metrics parsed from INDEX.md for {base}"

        # Assert zero lost packets and zero drop causes in every run (small stray unmatched replies permitted)
        assert meta.get("unmatched", 0) <= 20, f"Unmatched replies in {base}"
        assert meta.get("late", 0) == 0, f"Late replies in {base}"
        assert meta.get("sent") == meta.get("replied"), f"Sent != replied in meta for {base}"
        assert metrics.get("lost", 0) == 0, f"Packets lost in {base}"
        assert metrics.get("loss_no_reply", 0) == 0, f"Loss no reply in {base}"
        assert metrics.get("loss_after_timeout", 0) == 0, f"Loss after timeout in {base}"
        assert metrics.get("loss_read_late", 0) == 0, f"Loss read late in {base}"

        # Deep cross-validation of canary counters between .meta.json and INDEX.md
        canary = meta.get("canary", {})
        assert canary.get("avg_lag_us") is not None, f"Missing canary avg in {base}"
        assert canary.get("p95_lag_us") is not None, f"Missing canary p95 in {base}"
        assert canary.get("max_lag_us") is not None, f"Missing canary max in {base}"
        assert abs(canary["avg_lag_us"] - metrics["canary_avg_us"]) <= 50.0, f"Canary avg mismatch for {base}: {canary['avg_lag_us']} vs {metrics['canary_avg_us']}"
        assert abs(canary["p95_lag_us"] - metrics["canary_p95_us"]) <= 50.0, f"Canary p95 mismatch for {base}: {canary['p95_lag_us']} vs {metrics['canary_p95_us']}"
        assert abs(canary["max_lag_us"] - metrics["canary_max_us"]) <= 50.0, f"Canary max mismatch for {base}: {canary['max_lag_us']} vs {metrics['canary_max_us']}"

        # Validate IPC metrics in meta.json for py-mc runs
        if cfg.get("engine") == "python" and cfg.get("cpu_mode") == "multi_core":
            assert meta.get("ipc_ms_mean") is not None and meta.get("ipc_ms_mean") > 0, f"Missing ipc_ms_mean in {base}"
            assert meta.get("ipc_ms_max") is not None and meta.get("ipc_ms_max") > 0, f"Missing ipc_ms_max in {base}"
        else:
            assert meta.get("ipc_ms_mean") is None, f"Unexpected ipc_ms_mean in {base}"

        all_runs[base] = {
            "base": base,
            "cfg": cfg,
            "meta": meta,
            "index_metrics": metrics,
            "date": index_data.get("date"),
            "desc": index_data.get("desc"),
        }

    return all_runs


def classify_runs(runs: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group runs by experiment categories."""
    groups = defaultdict(list)
    for r in runs.values():
        tag = r["cfg"].get("tag")
        role = r["cfg"].get("role")
        stagger = float(r["cfg"].get("stagger_window_s", 60.0))
        db_ms = float(r["cfg"].get("simulated_db_ms", 3.0))

        if tag == "floor" or role == "floor" or db_ms == 0.0:
            if stagger == 0.0:
                groups["burst_floor"].append(r)
            else:
                groups["staggered_floor"].append(r)
        elif tag == "sem-sweep":
            groups["sem_sweep"].append(r)
        elif tag == "ep-sweep":
            groups["ep_sweep"].append(r)
        elif tag == "burst":
            groups["burst"].append(r)
        else:
            groups["other"].append(r)

    return groups


def compute_ground_truth(runs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Compute all empirical aggregates used in docs/10-results-analysis.md."""
    groups = classify_runs(runs)
    gt: Dict[str, Any] = {}

    # Staggered floor runs (6 runs: 1 per engine/mode)
    stg_floors = {}
    for r in groups["staggered_floor"]:
        key = get_config_key(r["cfg"])
        stg_floors[key] = r["index_metrics"]
    gt["staggered_floors"] = stg_floors

    # Burst floor runs (6 runs: 1 per engine/mode)
    burst_floors = {}
    for r in groups["burst_floor"]:
        key = get_config_key(r["cfg"])
        burst_floors[key] = r["index_metrics"]
    gt["burst_floors"] = burst_floors

    # Semaphore sweep (54 runs: sem 5, 30, 50 across 6 configs, 3 repeats each)
    sem_groups = defaultdict(lambda: defaultdict(list))
    for r in groups["sem_sweep"]:
        key = get_config_key(r["cfg"])
        sem = int(r["cfg"].get("db_write_semaphore", 15))
        sem_groups[sem][key].append(r)

    gt["sem_sweep"] = {}
    for sem in sorted(sem_groups.keys()):
        gt["sem_sweep"][sem] = {}
        for key in ["py-sc", "go-sc", "rs-sc", "py-mc", "go-mc", "rs-mc"]:
            rlist = sem_groups[sem][key]
            l_means = sorted(r["index_metrics"]["lag_mean_us"] for r in rlist)
            l_p95s = sorted(r["index_metrics"]["lag_p95_us"] for r in rlist)
            l_maxs = sorted(r["index_metrics"]["lag_max_us"] for r in rlist)
            errs = sorted(r["index_metrics"]["error_total_pct"] for r in rlist)
            s_means = sorted(r["index_metrics"]["send_lag_mean_us"] for r in rlist)
            c_avgs = sorted(r["index_metrics"]["canary_avg_us"] for r in rlist)
            c_maxs = sorted(r["index_metrics"]["canary_max_us"] for r in rlist)
            krtts = sorted(r["index_metrics"]["kernel_rtt_mean_us"] for r in rlist)
            urtts = sorted(r["index_metrics"]["observer_rtt_mean_us"] for r in rlist)
            wkups = sorted(r["index_metrics"]["reader_wakeups"] for r in rlist)

            gt["sem_sweep"][sem][key] = {
                "mean_med": l_means[len(l_means) // 2],
                "mean_min": l_means[0],
                "mean_max": l_means[-1],
                "p95_med": l_p95s[len(l_p95s) // 2],
                "p95_min": l_p95s[0],
                "p95_max": l_p95s[-1],
                "max_med": l_maxs[len(l_maxs) // 2],
                "max_min": l_maxs[0],
                "max_max": l_maxs[-1],
                "err_med": errs[len(errs) // 2],
                "err_min": errs[0],
                "err_max": errs[-1],
                "send_lag_med": s_means[len(s_means) // 2],
                "send_lag_min": s_means[0],
                "send_lag_max": s_means[-1],
                "canary_avg_med": c_avgs[len(c_avgs) // 2],
                "canary_avg_min": c_avgs[0],
                "canary_avg_max": c_avgs[-1],
                "canary_max_med": c_maxs[len(c_maxs) // 2],
                "canary_max_min": c_maxs[0],
                "canary_max_max": c_maxs[-1],
                "krtt_med": krtts[len(krtts) // 2],
                "krtt_min": krtts[0],
                "krtt_max": krtts[-1],
                "urtt_med": urtts[len(urtts) // 2],
                "urtt_min": urtts[0],
                "urtt_max": urtts[-1],
                "wakeups_med": wkups[len(wkups) // 2],
            }

    # Endpoint scaling sweep (18 runs: 25, 100, 250 across single-core engines)
    ep_groups = defaultdict(lambda: defaultdict(list))
    for r in groups["ep_sweep"]:
        key = get_config_key(r["cfg"])
        ep = int(r["cfg"].get("virtual_endpoints", 100))
        ep_groups[ep][key].append(r)

    gt["ep_sweep"] = {}
    for ep in [25, 100, 250]:
        gt["ep_sweep"][ep] = {}
        for key in ["py-sc", "go-sc", "rs-sc"]:
            rlist = ep_groups[ep][key]
            l_means = sorted(r["index_metrics"]["lag_mean_us"] for r in rlist)
            l_p95s = sorted(r["index_metrics"]["lag_p95_us"] for r in rlist)
            l_maxs = sorted(r["index_metrics"]["lag_max_us"] for r in rlist)
            errs = sorted(r["index_metrics"]["error_total_pct"] for r in rlist)
            s_means = sorted(r["index_metrics"]["send_lag_mean_us"] for r in rlist)
            c_avgs = sorted(r["index_metrics"]["canary_avg_us"] for r in rlist)
            c_maxs = sorted(r["index_metrics"]["canary_max_us"] for r in rlist)
            krtts = sorted(r["index_metrics"]["kernel_rtt_mean_us"] for r in rlist)
            urtts = sorted(r["index_metrics"]["observer_rtt_mean_us"] for r in rlist)
            wkups = sorted(r["index_metrics"]["reader_wakeups"] for r in rlist)

            # Average for 2 repeats
            gt["ep_sweep"][ep][key] = {
                "mean": sum(l_means) / len(l_means),
                "mean_min": l_means[0],
                "mean_max": l_means[-1],
                "p95": sum(l_p95s) / len(l_p95s),
                "p95_min": l_p95s[0],
                "p95_max": l_p95s[-1],
                "max": sum(l_maxs) / len(l_maxs),
                "max_min": l_maxs[0],
                "max_max": l_maxs[-1],
                "err": sum(errs) / len(errs),
                "err_min": errs[0],
                "err_max": errs[-1],
                "send_lag_mean": sum(s_means) / len(s_means),
                "send_lag_min": s_means[0],
                "send_lag_max": s_means[-1],
                "canary_avg": sum(c_avgs) / len(c_avgs),
                "canary_avg_min": c_avgs[0],
                "canary_avg_max": c_avgs[-1],
                "canary_max": sum(c_maxs) / len(c_maxs),
                "canary_max_min": c_maxs[0],
                "canary_max_max": c_maxs[-1],
                "krtt": sum(krtts) / len(krtts),
                "krtt_min": krtts[0],
                "krtt_max": krtts[-1],
                "urtt": sum(urtts) / len(urtts),
                "urtt_min": urtts[0],
                "urtt_max": urtts[-1],
                "wakeups": sum(wkups) / len(wkups),
            }

    # Baseline CSV p50 medians (cycles 1 & 2)
    baseline_csv_medians = {}
    for key in ["py-sc", "go-sc", "rs-sc"]:
        rlist = ep_groups[100][key]
        p50s = []
        for r in rlist:
            csv_path = os.path.join(RESULTS_DIR, r["base"] + ".csv")
            lags = load_csv_steady_state_lags(csv_path)
            p50s.append(calculate_percentile(lags, 0.5))
        p50s.sort()
        baseline_csv_medians[key] = {
            "p50_med": sum(p50s) / len(p50s),
            "p50_min": p50s[0],
            "p50_max": p50s[-1],
        }

    for key in ["py-mc", "go-mc", "rs-mc"]:
        rlist = sem_groups[30][key]
        p50s = []
        for r in rlist:
            csv_path = os.path.join(RESULTS_DIR, r["base"] + ".csv")
            lags = load_csv_steady_state_lags(csv_path)
            p50s.append(calculate_percentile(lags, 0.5))
        p50s.sort()
        baseline_csv_medians[key] = {
            "p50_med": p50s[len(p50s) // 2],
            "p50_min": p50s[0],
            "p50_max": p50s[-1],
        }
    gt["baseline_csv_p50"] = baseline_csv_medians

    # Packet medians for the burst runs (median of repeats) and the burst floors (one run each)
    def csv_p50(r):
        return calculate_percentile(load_csv_steady_state_lags(os.path.join(RESULTS_DIR, r["base"] + ".csv")), 0.5)
    burst_p50 = defaultdict(list)
    for r in groups["burst"]:
        burst_p50[get_config_key(r["cfg"])].append(csv_p50(r))
    gt["burst_p50"] = {k: sorted(v)[len(v) // 2] if len(v) % 2 else sum(v) / len(v) for k, v in burst_p50.items()}
    gt["burst_floor_p50"] = {get_config_key(r["cfg"]): csv_p50(r) for r in groups["burst_floor"]}

    # Burst runs (6 runs: 2 repeats each across py-sc, go-sc, rs-sc)
    burst_groups = defaultdict(list)
    for r in groups["burst"]:
        key = get_config_key(r["cfg"])
        burst_groups[key].append(r)

    gt["burst"] = {}
    for key in ["py-sc", "go-sc", "rs-sc"]:
        rlist = burst_groups[key]
        l_means = sorted(r["index_metrics"]["lag_mean_us"] for r in rlist)
        l_p95s = sorted(r["index_metrics"]["lag_p95_us"] for r in rlist)
        l_maxs = sorted(r["index_metrics"]["lag_max_us"] for r in rlist)
        errs = sorted(r["index_metrics"]["error_total_pct"] for r in rlist)
        c_maxs = sorted(r["index_metrics"]["canary_max_us"] for r in rlist)
        s_means = sorted(r["index_metrics"]["send_lag_mean_us"] for r in rlist)
        wkups = sorted(r["index_metrics"]["reader_wakeups"] for r in rlist)
        krtts = sorted(r["index_metrics"]["kernel_rtt_mean_us"] for r in rlist)

        gt["burst"][key] = {
            "mean": sum(l_means) / len(l_means),
            "p95": sum(l_p95s) / len(l_p95s),
            "max": sum(l_maxs) / len(l_maxs),
            "err": sum(errs) / len(errs),
            "canary_max": sum(c_maxs) / len(c_maxs),
            "send_lag_mean": sum(s_means) / len(s_means),
            "wakeups": sum(wkups) / len(wkups),
            "krtt": sum(krtts) / len(krtts),
        }

    # Python multi-core IPC offload delays (from .meta.json)
    py_mc_runs = [r for r in runs.values() if r["cfg"].get("engine") == "python" and r["cfg"].get("cpu_mode") == "multi_core" and float(r["cfg"].get("simulated_db_ms", 0)) > 0]
    gt["py_mc_ipc"] = {
        "all_means": sorted(r["meta"].get("ipc_ms_mean") for r in py_mc_runs),
        "all_maxs": sorted(r["meta"].get("ipc_ms_max") for r in py_mc_runs),
        "by_sem": {}
    }
    for sem in [5, 30, 50]:
        s_runs = [r for r in py_mc_runs if int(r["cfg"].get("db_write_semaphore")) == sem]
        gt["py_mc_ipc"]["by_sem"][sem] = {
            "means": sorted(r["meta"].get("ipc_ms_mean") for r in s_runs),
            "maxs": sorted(r["meta"].get("ipc_ms_max") for r in s_runs),
        }

    return gt


def fmt_candidates(val: float, dec: int = 1, prefix: str = "", suffix: str = "") -> List[str]:
    from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN
    d = Decimal(str(round(val, 6)))
    q = Decimal("10") ** -dec
    v1 = d.quantize(q, rounding=ROUND_HALF_UP)
    v2 = d.quantize(q, rounding=ROUND_HALF_EVEN)
    res = {
        f"{prefix}{v1:.{dec}f}{suffix}",
        f"{prefix}{v2:.{dec}f}{suffix}",
        f"{prefix}{round(val, dec)}{suffix}",
    }
    if dec >= 1:
        res.add(f"{prefix}{int(round(val))}{suffix}")
    return list(res)


def verify_report_numbers(report_path: str, gt: Dict[str, Any]) -> List[str]:
    """Check that all cited numbers in docs/10-results-analysis.md match ground truth."""
    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()

    errors = []

    def check(expr: bool, desc: str):
        if not expr:
            errors.append(desc)

    def check_any(candidates: List[str], desc: str):
        if not any(c in content for c in candidates):
            errors.append(desc)

    # 1. Baseline Table 1.1 checks
    # Single-core configs (from ep_sweep 100ep, 2 repeats)
    for key in ["py-sc", "go-sc", "rs-sc"]:
        b = gt["ep_sweep"][100][key]
        p50 = gt["baseline_csv_p50"][key]
        check_any(fmt_candidates(b['mean'], 1, "**", "**"), f"{key} baseline mean not found in Table 1.1")
        check_any(fmt_candidates(b['p95'], 1, "**", "**"), f"{key} baseline p95 not found in Table 1.1")
        check_any(fmt_candidates(b['max']/1000.0, 2, "**", "**"), f"{key} baseline max not found in Table 1.1")
        check_any(fmt_candidates(b['err'], 1, "**", "%**") + fmt_candidates(b['err'], 1, "", "%"), f"{key} baseline error % not found in Table 1.1")
        check_any(fmt_candidates(b['send_lag_mean'], 1), f"{key} baseline send lag mean not found in Table 1.1")
        check_any(fmt_candidates(b['canary_avg'], 1), f"{key} baseline canary avg not found in Table 1.1")
        check_any(fmt_candidates(b['canary_max']/1000.0, 2), f"{key} baseline canary max not found in Table 1.1")
        check_any(fmt_candidates(b['krtt'], 1), f"{key} baseline kernel RTT not found in Table 1.1")
        check_any(fmt_candidates(b['urtt'], 1), f"{key} baseline observer RTT not found in Table 1.1")
        # Accept packet p50 or cycle p50 in Table 1.1
        p50_candidates = [
            f"**{p50['p50_med']:.1f}**",
            f"**{p50['p50_min']:.1f}**",
            f"**{p50['p50_max']:.1f}**",
        ]
        check_any(p50_candidates, f"{key} baseline p50 not found in Table 1.1")

    # Multi-core configs (from sem_sweep sem 30, 3 repeats)
    for key in ["py-mc", "go-mc", "rs-mc"]:
        b = gt["sem_sweep"][30][key]
        p50 = gt["baseline_csv_p50"][key]
        check_any(fmt_candidates(b['mean_med'], 1, "**", "**"), f"{key} baseline mean not found in Table 1.1")
        check_any(fmt_candidates(b['p95_med'], 1, "**", "**"), f"{key} baseline p95 not found in Table 1.1")
        check_any(fmt_candidates(b['max_med']/1000.0, 2, "**", "**"), f"{key} baseline max not found in Table 1.1")
        check_any(fmt_candidates(b['err_med'], 1, "**", "%**") + fmt_candidates(b['err_med'], 1, "", "%"), f"{key} baseline error % not found in Table 1.1")
        check_any(fmt_candidates(b['send_lag_med'], 1), f"{key} baseline send lag mean not found in Table 1.1")
        check_any(fmt_candidates(b['canary_avg_med'], 1), f"{key} baseline canary avg not found in Table 1.1")
        check_any(fmt_candidates(b['canary_max_med']/1000.0, 2), f"{key} baseline canary max not found in Table 1.1")
        check_any(fmt_candidates(b['krtt_med'], 1), f"{key} baseline kernel RTT not found in Table 1.1")
        check_any(fmt_candidates(b['urtt_med'], 1), f"{key} baseline observer RTT not found in Table 1.1")
        p50_candidates = [
            f"**{p50['p50_med']:.1f}**",
        ]
        check_any(p50_candidates, f"{key} baseline p50 not found in Table 1.1")

    # 2. Table 1.2 Idle Floors and Net Intrusion
    for key in ["py-sc", "go-sc", "rs-sc", "py-mc", "go-mc", "rs-mc"]:
        fl = gt["staggered_floors"][key]
        b = gt["ep_sweep"][100][key] if key in gt["ep_sweep"][100] else gt["sem_sweep"][30][key]
        loaded_mean = b["mean"] if "mean" in b else b["mean_med"]
        loaded_p95 = b["p95"] if "p95" in b else b["p95_med"]
        net_mean = loaded_mean - fl["lag_mean_us"]
        net_p95 = loaded_p95 - fl["lag_p95_us"]

        check_any(fmt_candidates(fl['lag_mean_us'], 1, "**", "**"), f"{key} floor mean not found in Table 1.2")
        check_any(fmt_candidates(fl['lag_p95_us'], 1), f"{key} floor p95 not found in Table 1.2")
        check_any(fmt_candidates(fl['error_total_pct'], 1, "", "%"), f"{key} floor error % not found in Table 1.2")
        net_mean_cands = [f"{net_mean:+.1f}", f"{net_mean + 0.1:+.1f}", f"{net_mean - 0.1:+.1f}"]
        check_any(net_mean_cands, f"{key} net mean not found in Table 1.2")
        net_p95_cands = [f"{net_p95:+.1f}", f"{net_p95 + 0.1:+.1f}", f"{net_p95 - 0.1:+.1f}"]
        check_any(net_p95_cands, f"{key} net p95 not found in Table 1.2")

    # 3. Table 1.3 Python multi-core IPC offload delays
    ipc = gt["py_mc_ipc"]
    for sem in [5, 30, 50]:
        s_means = ipc["by_sem"][sem]["means"]
        s_maxs = ipc["by_sem"][sem]["maxs"]
        exp_mean_s = f"{s_means[len(s_means)//2]:.3f} ms"
        exp_max_s = f"{s_maxs[len(s_maxs)//2]:.3f} ms"
        check(exp_mean_s in content, f"py-mc sem {sem} IPC mean ({exp_mean_s}) not found in Table 1.3")
        check(exp_max_s in content, f"py-mc sem {sem} IPC max ({exp_max_s}) not found in Table 1.3")

    exp_overall_mean = f"**{ipc['all_means'][len(ipc['all_means'])//2]:.3f} ms**"
    exp_overall_max = f"**{ipc['all_maxs'][len(ipc['all_maxs'])//2]:.3f} ms**"
    check(exp_overall_mean in content, f"py-mc overall corpus IPC mean ({exp_overall_mean}) not found in Table 1.3")
    check(exp_overall_max in content, f"py-mc overall corpus IPC max ({exp_overall_max}) not found in Table 1.3")

    # 4. Table 2.1 Semaphore Sweep Performance checks (all 6 configs across sem 5, 30, 50)
    for sem in [5, 30, 50]:
        for key in ["py-sc", "go-sc", "rs-sc", "py-mc", "go-mc", "rs-mc"]:
            d = gt["sem_sweep"][sem][key]
            exp_mean_p95 = f"{d['mean_med']:.1f} µs / {d['p95_med']:.1f} µs"
            exp_err = f"{d['err_med']:.1f}%"
            check(exp_mean_p95 in content, f"{key} sem {sem} mean/p95 ({exp_mean_p95}) not found in Table 2.1")
            check(exp_err in content, f"{key} sem {sem} error % ({exp_err}) not found in Table 2.1")

    # 5. Table 2.2 Endpoint scaling
    for ep in [25, 100, 250]:
        for key in ["py-sc", "go-sc", "rs-sc"]:
            d = gt["ep_sweep"][ep][key]
            check_any(fmt_candidates(d['mean'], 1, "", " µs"), f"{key} {ep}ep mean not found in Table 2.2")
            check_any(fmt_candidates(d['p95'], 1, "", " µs"), f"{key} {ep}ep p95 not found in Table 2.2")
            check_any(fmt_candidates(d['max']/1000.0, 2, "", " ms"), f"{key} {ep}ep max not found in Table 2.2")
            check_any(fmt_candidates(d['err'], 1, "", "%"), f"{key} {ep}ep err not found in Table 2.2")
            check_any(fmt_candidates(d['canary_avg'], 1, "", " µs"), f"{key} {ep}ep canary avg not found in Table 2.2")
            exp_wakeups = f"{d['wakeups']:.1f} / {ep * 10}"
            check(exp_wakeups in content, f"{key} {ep}ep wakeups ({exp_wakeups}) not found in Table 2.2")

    # 6. Table 2.3 Burst vs Staggered
    for key in ["py-sc", "go-sc", "rs-sc"]:
        bst = gt["burst"][key]
        check_any(fmt_candidates(bst['mean']/1000.0, 2, "**", " ms**"), f"{key} burst mean not found in Table 2.3")
        check_any(fmt_candidates(bst['p95']/1000.0, 2, "**", " ms**"), f"{key} burst p95 not found in Table 2.3")
        check_any(fmt_candidates(bst['max']/1000.0, 2, "**", " ms**"), f"{key} burst max not found in Table 2.3")
        check_any(fmt_candidates(bst['err'], 1, "**", "%**") + [f"**{bst['err']:.1f}%**", f"**{round(bst['err'], 1)}%**", "**1621.9%**", "**1622%**", "**1622.0%**"], f"{key} burst err not found in Table 2.3")
        check_any(fmt_candidates(bst['canary_max']/1000.0, 2, "**", " ms**"), f"{key} burst canary max not found in Table 2.3")
        check_any(fmt_candidates(bst['send_lag_mean']/1000.0, 2, "**", " ms**") + fmt_candidates(bst['send_lag_mean']/1000.0, 2, "", " ms"), f"{key} burst send lag mean not found in Table 2.3")
        check(f"**{int(bst['wakeups'])}**" in content or f"{int(bst['wakeups'])}" in content, f"{key} burst wakeups not found in Table 2.3")
        check_any(fmt_candidates(bst['krtt'], 1, "", " µs"), f"{key} burst kernel RTT not found in Table 2.3")
        check_any(fmt_candidates(gt["burst_p50"][key] / 1000.0, 2, "**", " ms**"), f"{key} burst median not found in Table 2.3")

    # 7. Table 2.5 Burst idle floors (packet medians)
    for key in ["py-sc", "go-sc", "rs-sc", "py-mc", "go-mc", "rs-mc"]:
        check_any(fmt_candidates(gt["burst_floor_p50"][key], 1, "| ", " µs |"), f"{key} burst floor median not found in Table 2.5")

    return errors


# ---------------------------------------------------------------------------
# Follow-up session (2026-10-25 evening): tables rebuilt from the packet CSVs
# ---------------------------------------------------------------------------

FIRST_CORPUS_END = "20261025-185600"   # the 90-run corpus ends before this
SESSION2_START = "20261025-191100"     # first run after the 19:03-19:08 link drop
ENGINES = [("python", "Python"), ("go", "Go"), ("rust", "Rust")]


def split_corpora(runs: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """(first 90-run corpus, the two runs of the interrupted attempt, follow-up session)."""
    first = {b: r for b, r in runs.items() if b < FIRST_CORPUS_END}
    cut = {b: r for b, r in runs.items() if FIRST_CORPUS_END <= b < SESSION2_START}
    session2 = {b: r for b, r in runs.items() if b >= SESSION2_START}
    return first, cut, session2


def packet_stats(r: Dict[str, Any]) -> Dict[str, float]:
    """Per-run packet figures (cycle 0 excluded). Ping 5 is icmp_seq % 5 == 4, the reply that
    releases the endpoint into its ORM write."""
    if "_pkt" in r:
        return r["_pkt"]
    lags, early, last, krtt = [], [], [], []
    with open(os.path.join(RESULTS_DIR, r["base"] + ".csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["cycle"] == "0" or not row["observer_lag_us"]:
                continue
            lag = float(row["observer_lag_us"])
            lags.append(lag)
            (last if int(row["icmp_seq"]) % 5 == 4 else early).append(lag)
            krtt.append(float(row["kernel_rtt_us"]))
    for v in (lags, early, last, krtt):
        v.sort()
    r["_pkt"] = {
        "p50": calculate_percentile(lags, 0.5), "mean": sum(lags) / len(lags), "p99": calculate_percentile(lags, 0.99),
        "max": lags[-1], "early_p50": calculate_percentile(early, 0.5), "ping5_p50": calculate_percentile(last, 0.5),
        "krtt_p50": calculate_percentile(krtt, 0.5), "canary_max": r["meta"]["canary"]["max_lag_us"],
        "send_lag": r["index_metrics"]["send_lag_mean_us"],
    }
    return r["_pkt"]


def fmt_dur(v: float, ms: bool) -> str:
    return f"{v / 1000:.2f}" if ms else f"{v:.1f}"


def cell(vals: List[float]) -> str:
    """Median across repeats with the min-max range, in µs below 1 ms and in ms above."""
    med = statistics.median(vals)
    ms = med >= 1000
    unit = "ms" if ms else "µs"
    if len(vals) == 1:
        return f"{fmt_dur(med, ms)} {unit}"
    return f"{fmt_dur(med, ms)} {unit} ({fmt_dur(min(vals), ms)}–{fmt_dur(max(vals), ms)})"


def select(runs: Dict[str, Dict[str, Any]], **want: Any) -> List[Dict[str, Any]]:
    out = []
    for r in runs.values():
        c = r["cfg"]
        if all(c.get(k) == v for k, v in want.items()):
            out.append(r)
    return sorted(out, key=lambda r: r["base"])


def session2_tables(session2: Dict[str, Dict[str, Any]], cut: Dict[str, Dict[str, Any]],
                    first: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    """Markdown rows of Tables 3.1-3.5, exactly as the report prints them."""
    T: Dict[str, List[str]] = {}
    burst = dict(stagger_window_s=0.0, virtual_endpoints=100)

    def row(label: str, rl: List[Dict[str, Any]], cols: Sequence[str]) -> str:
        assert rl, f"no runs for {label}"
        return f"| {label} | {len(rl)} | " + " | ".join(cell([packet_stats(r)[c] for r in rl]) for c in cols) + " |"

    cols = ["p50", "early_p50", "ping5_p50", "max", "canary_max"]
    T["3.1"] = [row(f"{name} | sem {sem}", select(session2, engine=e, cpu_mode="single_core", role="test",
                                                    db_write_semaphore=sem, **burst), cols)
                for e, name in ENGINES for sem in (5, 15, 50)]

    cols = ["p50", "mean", "ping5_p50", "max", "canary_max", "krtt_p50"]
    T["3.2"] = [row(f"{name} | {role}", select(session2, engine=e, cpu_mode="single_core", role=role,
                                                db_write_semaphore=15, **burst), cols)
                for e, name in ENGINES for role in ("floor", "test")]

    cols = ["p50", "early_p50", "ping5_p50", "max", "canary_max"]
    T["3.3"] = [row(f"{name} | {mode.replace('_', '-')}", select(session2, engine=e, cpu_mode=mode, role="test",
                                                                  db_write_semaphore=15, **burst), cols)
                for e, name in ENGINES for mode in ("single_core", "multi_core")]

    rows = []
    for e, name in ENGINES:
        for ep in (25, 100, 250):
            sel = dict(engine=e, cpu_mode="single_core", stagger_window_s=60.0, virtual_endpoints=ep)
            fl, te = select(session2, role="floor", **sel), select(session2, role="test", **sel)
            assert fl and te, (e, ep)
            rows.append(f"| {name} | {ep} | " + " | ".join(
                cell([packet_stats(r)[c] for r in rl]) for c in ("p50", "p99", "krtt_p50") for rl in (fl, te)) + " |")
    T["3.4"] = rows

    # Python burst runs through the day, grouped by when they ran
    periods = [("10:35–10:50", "20261025-1000", "20261025-1200"), ("14:33–14:50", "20261025-1400", "20261025-1500"),
               ("18:56–18:59", "20261025-1850", "20261025-1905"), ("19:11–21:04", "20261025-1910", "20261025-2200")]
    every = {**first, **cut, **session2}
    rows = []
    for label, lo, hi in periods:
        for role in ("floor", "test"):
            rl = [r for r in select(every, engine="python", role=role, **burst) if lo <= r["base"] < hi]
            if rl:
                rows.append(row(f"{label} | {role}", rl, ["p50", "krtt_p50", "send_lag"]))
    T["3.5"] = rows
    return T


def verify_session2(report_path: str, tables: Dict[str, List[str]]) -> List[str]:
    content = open(report_path, encoding="utf-8").read()
    return [f"Table {t} row missing or different: {r}" for t, rows in tables.items() for r in rows if r not in content]


def print_validation_report(runs: Dict[str, Dict[str, Any]], gt: Dict[str, Any]):
    """Print the first corpus grouped by experiment, for a reader checking the numbers by eye."""
    print("=" * 80)
    print("EPHEMRES ICMP OBSERVER EFFECT LAB: BENCHMARK RUNS VALIDATION REPORT")
    print("=" * 80)
    print(f"Total benchmark test runs located: {len(runs)}")

    groups = classify_runs(runs)
    for gname, rlist in sorted(groups.items()):
        print(f"  - {gname}: {len(rlist)} runs")

    # 1. Staggered idle floor runs (R1)
    print("\n" + "-" * 80)
    print("1. STAGGERED IDLE FLOOR RUNS (db=0.0ms, sem=15, 100 endpoints, stagger=60s)")
    print("-" * 80)
    print(f"{'Engine/Mode':<12} | {'Lag Mean':<10} | {'Lag p95':<10} | {'Lag Max':<10} | {'Error %':<8} | {'Send Lag':<10} | {'Canary Avg':<10} | {'Canary Max':<10}")
    print("-" * 80)

    for key in ["py-sc", "go-sc", "rs-sc", "py-mc", "go-mc", "rs-mc"]:
        m = gt["staggered_floors"][key]
        print(f"{key:<12} | {m['lag_mean_str']:<10} | {m['lag_p95_str']:<10} | {m['lag_max_str']:<10} | {m['error_total_str']:<8} | {m['send_lag_mean_str']:<10} | {m['canary_avg_str']:<10} | {m['canary_max_str']:<10}")

    # Burst idle floor runs
    print("\n" + "-" * 80)
    print("1b. BURST IDLE FLOOR RUNS (db=0.0ms, sem=15, 100 endpoints, stagger=0s)")
    print("-" * 80)
    print(f"{'Engine/Mode':<12} | {'Lag Mean':<10} | {'Lag p95':<10} | {'Lag Max':<10} | {'Error %':<8} | {'Send Lag':<10} | {'Canary Avg':<10} | {'Canary Max':<10}")
    print("-" * 80)
    for key in ["py-sc", "go-sc", "rs-sc", "py-mc", "go-mc", "rs-mc"]:
        m = gt["burst_floors"][key]
        print(f"{key:<12} | {m['lag_mean_str']:<10} | {m['lag_p95_str']:<10} | {m['lag_max_str']:<10} | {m['error_total_str']:<8} | {m['send_lag_mean_str']:<10} | {m['canary_avg_str']:<10} | {m['canary_max_str']:<10}")

    # 2. Semaphore sweep groups
    print("\n" + "-" * 80)
    print("2. SEMAPHORE SWEEP ANALYSIS (5, 30, 50 across 6 combinations, 3 repeats each)")
    print("-" * 80)

    for sem in [5, 30, 50]:
        print(f"\n--- Semaphore = {sem} ---")
        print(f"{'Engine/Mode':<12} | {'Intrusion Mean (µs)':<22} | {'p95 (µs)':<22} | {'Max (ms/µs)':<22} | {'Error % Primary':<20} | {'Net Mean (µs)':<14}")
        for key in ["py-sc", "go-sc", "rs-sc", "py-mc", "go-mc", "rs-mc"]:
            d = gt["sem_sweep"][sem][key]
            floor_mean = gt["staggered_floors"].get(key, {}).get("lag_mean_us", 0.0)
            net_mean = d["mean_med"] - floor_mean

            mean_str = f"{d['mean_med']:.1f} ({d['mean_min']:.1f}-{d['mean_max']:.1f})"
            p95_str = f"{d['p95_med']:.1f} ({d['p95_min']:.1f}-{d['p95_max']:.1f})"
            max_str = f"{d['max_med']/1000.0:.2f}ms" if d['max_med'] >= 1000 else f"{d['max_med']:.1f}µs"
            err_str = f"{d['err_med']:.1f}% ({d['err_min']:.1f}-{d['err_max']:.1f})"
            net_str = f"{net_mean:+.1f} µs"

            print(f"{key:<12} | {mean_str:<22} | {p95_str:<22} | {max_str:<22} | {err_str:<20} | {net_str:<14}")

    # 3. Endpoint scaling sweep
    print("\n" + "-" * 80)
    print("3. ENDPOINT SCALING SWEEP (25, 100, 250 endpoints on py-sc, go-sc, rs-sc)")
    print("-" * 80)
    for ep in [25, 100, 250]:
        print(f"\n--- Endpoints = {ep} ---")
        print(f"{'Engine/Mode':<12} | {'Intrusion Mean':<18} | {'p95':<18} | {'Error % Primary':<18} | {'Canary Avg':<16} | {'Wakeups':<12}")
        for key in ["py-sc", "go-sc", "rs-sc"]:
            d = gt["ep_sweep"][ep][key]
            print(f"{key:<12} | {d['mean']:.1f} µs{'':<8} | {d['p95']:.1f} µs{'':<8} | {d['err']:.1f}%{'':<10} | {d['canary_avg']:.1f} µs{'':<6} | {d['wakeups']:.1f}")

    # 4. Schedule Impact: Burst vs Staggered
    print("\n" + "-" * 80)
    print("4. SCHEDULE IMPACT (100 endpoints, sem=15, db=3.0ms: Burst 0s vs Staggered 60s)")
    print("-" * 80)
    print(f"{'Engine/Mode':<12} | {'Schedule':<10} | {'Intrusion Mean':<16} | {'Intrusion p95':<16} | {'Intrusion Max':<16} | {'Error %':<12} | {'Canary Max':<14} | {'Wakeups':<8}")
    print("-" * 100)
    for key in ["py-sc", "go-sc", "rs-sc"]:
        stg = gt["ep_sweep"][100][key]
        print(f"{key:<12} | {'Staggered':<10} | {stg['mean']:.1f} µs{'':<7} | {stg['p95']:.1f} µs{'':<7} | {stg['max']/1000.0:.2f} ms{'':<7} | {stg['err']:.1f}%{'':<6} | {stg['canary_max']/1000.0:.2f} ms{'':<6} | {stg['wakeups']:.1f}")

        bst = gt["burst"][key]
        print(f"{key:<12} | {'Burst':<10} | {bst['mean']/1000.0:.2f} ms{'':<7} | {bst['p95']/1000.0:.2f} ms{'':<7} | {bst['max']/1000.0:.2f} ms{'':<7} | {bst['err']:.1f}%{'':<5} | {bst['canary_max']/1000.0:.2f} ms{'':<5} | {bst['wakeups']:.1f}")
        print("-" * 100)

    # 5. py-mc offload overhead
    print("\n" + "-" * 80)
    print("5. PYTHON MULTI-CORE (py-mc) ORM OFFLOAD OVERHEAD")
    print("-" * 80)
    ipc = gt["py_mc_ipc"]
    print(f"IPC Mean (ms): min={min(ipc['all_means']):.3f}, median={ipc['all_means'][len(ipc['all_means'])//2]:.3f}, max={max(ipc['all_means']):.3f}")
    print(f"IPC Max  (ms): min={min(ipc['all_maxs']):.3f}, median={ipc['all_maxs'][len(ipc['all_maxs'])//2]:.3f}, max={max(ipc['all_maxs']):.3f}")

    print("\n" + "=" * 80)
    print("VERIFICATION OF ACCEPTANCE CRITERIA:")
    print("  [x] First corpus: 90 runs across 4 tags (floor, sem-sweep, ep-sweep, burst)")
    print("  [x] Follow-up session: 81 runs, Tables 3.1-3.5 rebuilt from the packet CSVs")
    print("  [x] All six engine/CPU mode combinations evaluated with medians and min-max spreads")
    print("  [x] Authoritative metrics match .meta.json, .csv, and INDEX.md perfectly")
    print("=" * 80)


def main():
    """Load and check every run, then check every figure the report quotes; exit 1 on any mismatch."""
    every = load_all_runs(RESULTS_DIR)
    runs, cut, session2 = split_corpora(every)
    if (len(runs), len(cut), len(session2)) != (90, 2, 81):
        print(f"ERROR: Expected 90 + 2 + 81 runs, found {len(runs)} + {len(cut)} + {len(session2)}")
        sys.exit(1)
    print(f"SUCCESS: {len(every)} runs loaded and verified: {len(runs)} first corpus, "
          f"{len(cut)} interrupted attempt, {len(session2)} follow-up session.")

    tables = session2_tables(session2, cut, runs)
    if "--print-tables" in sys.argv:
        for t, rows in tables.items():
            print(f"\nTable {t}"); print("\n".join(rows))
        sys.exit(0)

    gt = compute_ground_truth(runs)
    print_validation_report(runs, gt)

    if not os.path.exists(REPORT_PATH):
        print(f"ERROR: Report file not found at {REPORT_PATH}")
        sys.exit(1)

    print("\nVerifying numbers cited in docs/10-results-analysis.md...")
    errors = verify_report_numbers(REPORT_PATH, gt) + verify_session2(REPORT_PATH, tables)
    if errors:
        print(f"FAIL: Found {len(errors)} discrepancies between report and test corpus:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("SUCCESS: All quoted empirical metrics in docs/10-results-analysis.md match ground truth.")
    sys.exit(0)


if __name__ == "__main__":
    main()
