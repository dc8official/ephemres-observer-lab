"""Result-file naming convention, shared by the CLI and the dashboard.

A name has four underscore-separated groups, ordered by how you read a results folder:

    <WHEN>_<RUNTIME>_<LOAD>_<TARGET>[_<tag>]

    20261021-224241_go-mc_100ep-burst-sem15-db3_172-40-0-253
    |               |     |                     |
    |               |     |                     where: first target IP (+K if K more targets)
    |               |     what was asked of it: endpoints, schedule, semaphore size, ORM ms
    |               what ran it: engine - cores
    when: start time, sorts chronologically

    WHEN     YYYYMMDD-HHMMSS
    RUNTIME  <py|go|rs>-<sc|mc>   engine, and single-core (pinned) or multi-core
    LOAD     <N>ep-<burst|stg<S>>-sem<S>-db<ms>   plus  -p<pings>  and  -i<interval>  ONLY when
             they differ from 5 pings and 1 s, and  -c<cycles>x<cycle seconds>  ONLY when there is
             more than one cycle (e.g. -c3x60).  These "defaults" are fixed parts of the naming
             convention, not the dashboard's defaults: changing them would change what every
             existing file name means.
    TARGET   dashes instead of dots (172-40-0-253)
    tag      optional label chosen by you to group a series of runs, e.g. semaphore-sweep

The useful property: LOAD + TARGET is the identical text for every run that asked the
same question of a different engine.  Runs with the same "scenario key"
(LOAD_TARGET) are directly comparable, and the dashboard uses that to group them.

Decimal points are written 'p' (0.2 -> 0p2) so they never look like a file extension.
Runs saved before the engine existed are all Python, single core (py-sc).
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, Optional, Sequence

DEFAULT_PINGS = 5
DEFAULT_INTERVAL = 1.0
ENGINE_CODES = {"python": "py", "go": "go", "rust": "rs"}
ENGINE_NAMES = {v: k for k, v in ENGINE_CODES.items()}


def _n(x: float) -> str:
    """3.0 -> '3', 0.05 -> '0p05'.  Fixed-point, never exponent form: f"{1e-05:g}" is
    '1e-05', which parse_name() could not read back.  Six decimals is far finer than any
    setting the lab uses."""
    return (f"{x:.6f}".rstrip("0").rstrip(".") or "0").replace(".", "p")


def _un(s: str) -> float:
    return float(s.replace("p", "."))


def slug(text: str, limit: int = 24) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:limit]


def load_part(endpoints: int, stagger_s: Optional[float], semaphore: Optional[int], db_ms: Optional[float],
              pings: int = DEFAULT_PINGS, interval_s: float = DEFAULT_INTERVAL,
              cycles: int = 1, cycle_s: Optional[float] = None) -> str:
    sched = "burst" if not stagger_s else f"stg{_n(stagger_s)}"
    out = f"{endpoints}ep-{sched}-sem{semaphore}-db{_n(db_ms) if db_ms is not None else 'x'}"
    if pings != DEFAULT_PINGS:
        out += f"-p{pings}"
    if abs(interval_s - DEFAULT_INTERVAL) > 1e-9:
        out += f"-i{_n(interval_s)}"
    if cycles > 1:                       # several cycles per endpoint: how many, and how long each lasts
        out += f"-c{cycles}x{_n(cycle_s or 0)}"
    return out


def target_part(targets: Sequence[str]) -> str:
    return targets[0].replace(".", "-") + (f"+{len(targets) - 1}" if len(targets) > 1 else "")


def scenario_key(cfg: Dict[str, Any]) -> str:
    """Engine-independent description of the workload; equal keys = comparable runs."""
    targets = [t for t in str(cfg.get("targets", "?")).split(",") if t]
    return (load_part(int(cfg.get("virtual_endpoints") or 0), cfg.get("stagger_window_s"),
                      cfg.get("db_write_semaphore"), cfg.get("simulated_db_ms"),
                      int(cfg.get("pings_per_cycle") or DEFAULT_PINGS),
                      float(cfg.get("interval_s") or DEFAULT_INTERVAL),
                      int(cfg.get("cycles") or 1), cfg.get("cycle_length_s"))
            + "_" + target_part(targets or ["?"]))


def result_name(targets: Sequence[str], endpoints: int, stagger_s: Optional[float], semaphore: int,
                db_ms: float, pings: int, interval_s: float, when: Optional[float] = None,
                engine: str = "python", cpu_mode: str = "single_core", tag: str = "",
                cycles: int = 1, cycle_s: Optional[float] = None) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(when))
    runtime = f"{ENGINE_CODES.get(engine, engine)}-{'mc' if cpu_mode == 'multi_core' else 'sc'}"
    name = f"{stamp}_{runtime}_{load_part(endpoints, stagger_s, semaphore, db_ms, pings, interval_s, cycles, cycle_s)}_{target_part(targets)}"
    return name + (f"_{slug(tag)}" if slug(tag) else "")


_NAME_RE = re.compile(r"^(?P<when>\d{8}-\d{6})_(?P<eng>py|go|rs)-(?P<cpu>sc|mc)_(?P<ep>\d+)ep-(?P<sched>burst|stg[\dp]+)"
                      r"-sem(?P<sem>\d+)-db(?P<db>[\dp]+)(?:-p(?P<pings>\d+))?(?:-i(?P<iv>[\dp]+))?"
                      r"(?:-c(?P<cyc>\d+)x(?P<clen>[\dp]+))?"
                      r"_(?P<target>[\d-]+)(?:\+(?P<more>\d+))?(?:_(?P<tag>[a-z0-9-]+))?$")


def parse_name(name: str) -> Optional[Dict[str, Any]]:
    """Recover the configuration from a file name (None if it does not follow the convention)."""
    m = _NAME_RE.match(name)
    if not m:
        return None
    g = m.groupdict()
    return {"engine": ENGINE_NAMES[g["eng"]], "cpu_mode": "multi_core" if g["cpu"] == "mc" else "single_core",
            "virtual_endpoints": int(g["ep"]),
            "stagger_window_s": 0.0 if g["sched"] == "burst" else _un(g["sched"][3:]),
            "db_write_semaphore": int(g["sem"]), "simulated_db_ms": _un(g["db"]),
            "pings_per_cycle": int(g["pings"] or DEFAULT_PINGS),
            "interval_s": _un(g["iv"]) if g["iv"] else DEFAULT_INTERVAL,
            "cycles": int(g["cyc"] or 1), "cycle_length_s": _un(g["clen"]) if g["clen"] else None,
            "targets": g["target"].replace("-", "."), "tag": g["tag"] or ""}
