"""Live web dashboard for the Observer-Effect lab (FastAPI + WebSocket, no auth).

    sudo python3 -m server.app            # then open http://127.0.0.1:8080

WHY THE PROBE RUNS IN A SEPARATE PROCESS
----------------------------------------
The whole point of this lab is that anything running on the prober's asyncio
event loop delays when ping replies get read.  If this web server (JSON
encoding, WebSocket pushes, HTTP handlers) shared that loop, the dashboard
itself would contaminate the measurement.  So each run launches
``probe_lab.py --jsonl`` as a child process pinned to its OWN CPU core; this
server pins itself to the remaining cores and only relays the child's JSON-line
events.  The child's only dashboard-related cost is writing one small JSON line
per endpoint-cycle plus a heartbeat every 0.5 s (the writing time is measured and
reported as "stream overhead" on the dashboard).

DO NOT LET THE DASHBOARD BLOCK THE PROBE
----------------------------------------
The child's stdout is a pipe with a 64 KiB kernel buffer.  If this server stops
reading it (busy computing an analysis, or waiting for a slow browser), the
buffer fills and the child's next ``write()`` BLOCKS - in Python that freezes the
very event loop being measured.  So reading is kept separate from everything
else: ``_pump`` only parses lines and appends them to memory (it never awaits a
client), and ``_live`` pushes updates at most every 0.5 s, computing the
analysis in a worker thread and giving each WebSocket send a timeout.

The server must run as root because the child opens a raw ICMP socket.  It
listens on 127.0.0.1 by default precisely because there is no authentication,
and it rejects requests whose Host / Origin headers show they come from another
web site (see ``request_allowed``).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import socket
import sys
import shutil
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from probe_lab import parse_targets
from server import housekeeping
from server.hostinfo import collect as collect_host_info
from server.kernel_clock import discover_route
from server import analysis
from server.naming import parse_name, result_name, scenario_key

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = Path(os.environ.get("OBSERVER_RESULTS_DIR") or ROOT / "test_results")   # override for experiments
STATIC_DIR = Path(__file__).resolve().parent / "static"
LIVE_PERIOD_S = 0.5        # live dashboard refresh (the probes' heartbeat period)
# Packet rows held in memory at most (about 1 KB each, so the default is roughly 200 MB). Runs that are saved on disk
# beyond this are released, least recently used first, and reloaded from their CSV when needed again. Unsaved runs
# are never released (their data exists nowhere else), so the page shows how many there are.
ROW_BUDGET = int(os.environ.get("OBSERVER_ROW_BUDGET", "200000"))
SHUTDOWN_WAIT_S = (10.0, 3.0)  # on shutdown: wait for the probe after Ctrl-C, then after SIGTERM, before SIGKILL
SEND_TIMEOUT_S = 2.0       # a WebSocket client that cannot take a message within this is dropped

# ---------------------------------------------------------------------------
# Cross-site / DNS-rebinding guard
# ---------------------------------------------------------------------------
# Binding to 127.0.0.1 keeps other MACHINES out, but not other WEB PAGES: any site open
# in your browser can send requests to http://127.0.0.1:8080, and WebSockets are not
# covered by the browser's same-origin policy at all.  With "DNS rebinding" an attacker's
# domain can even be made to resolve to 127.0.0.1 so the browser treats our answers as
# theirs.  Two header checks stop all of that:
#   * Host must name this server   - a rebinding attack arrives as "Host: evil.example";
#   * Origin, when a browser sends it, must equal Host - blocks cross-site POSTs
#     (e.g. a hidden form hitting /api/stop) and cross-site WebSocket connections.
# Non-browser clients (curl, scripts) send no Origin and are allowed.
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}   # main() adds --host / --allowed-host


def _hostname(netloc: str) -> str:
    """'127.0.0.1:8080' -> '127.0.0.1', '[::1]:8080' -> '::1'."""
    netloc = netloc.strip().lower()
    if netloc.startswith("["):
        return netloc[1:netloc.find("]")] if "]" in netloc else netloc
    return netloc.rsplit(":", 1)[0] if netloc.count(":") == 1 else netloc


def request_allowed(host: Optional[str], origin: Optional[str]) -> bool:
    if not host or _hostname(host) not in ALLOWED_HOSTS:
        return False
    if origin is None:
        return True
    return urlsplit(origin).netloc.lower() == host.strip().lower()   # "null" origins fail too


# Defaults = Ephemres' own configuration, so an untouched form reproduces the system being studied and
# every change is a deliberate deviation from it.  The CPU-work figure is the lab's estimate.
EPHEMRES = {"virtual_endpoints": 100, "pings_per_cycle": 5, "interval_s": 8.0, "timeout_s": 2.0,
            "stagger_window_s": 60.0, "cycles": 3, "cycle_length_s": 60.0, "db_write_semaphore": 15,
            "simulated_db_ms": 3.0}


class RunConfig(BaseModel):
    """The settings of one run as sent by the dashboard page, with the allowed range of each value."""
    targets: str = Field(..., description="IPv4 or comma-separated IPv4s")
    virtual_endpoints: int = Field(EPHEMRES["virtual_endpoints"], ge=1, le=500)
    pings_per_cycle: int = Field(EPHEMRES["pings_per_cycle"], ge=1, le=20)
    stagger_window_s: float = Field(EPHEMRES["stagger_window_s"], ge=0.0, le=600.0, description="0 = burst")
    db_write_semaphore: int = Field(EPHEMRES["db_write_semaphore"], ge=1, le=100)
    simulated_db_ms: float = Field(EPHEMRES["simulated_db_ms"], ge=0.0, le=15.0)
    interval_s: float = Field(EPHEMRES["interval_s"], ge=0.05, le=30.0, description="seconds between pings of one endpoint")
    timeout_s: float = Field(EPHEMRES["timeout_s"], ge=0.1, le=10.0, description="wait for a reply before counting it lost")
    cycles: int = Field(EPHEMRES["cycles"], ge=1, le=60, description="cycles per endpoint; cycle 0 is a warm-up when > 1")
    cycle_length_s: float = Field(EPHEMRES["cycle_length_s"], ge=1.0, le=600.0, description="start-to-start time of an endpoint's cycles")
    hw_timestamps: bool = Field(False, description="NIC hardware RX stamps (Python only; breaks engine parity)")
    role: Literal["test", "floor"] = Field("test", description="floor = the same setup with no ORM work: the idle floor")
    note: str = Field("", max_length=300)
    engine: Literal["python", "go", "rust"] = "python"
    cpu_mode: Literal["single_core", "multi_core"] = "single_core"
    tag: str = Field("", max_length=24, description="optional series label appended to the file name")


WORKER_BIN = {"go": ROOT / "bin" / "go_prober", "rust": ROOT / "bin" / "rust_prober"}


def engine_available() -> Dict[str, bool]:
    return {"python": True, **{k: p.is_file() and os.access(p, os.X_OK) for k, p in WORKER_BIN.items()}}


@dataclass
class Run:
    """A run the dashboard knows about: its settings, status, live counters and, once finished, its packets."""
    id: str
    name: str
    cfg: Dict[str, Any]
    status: str = "starting"          # starting | running | done | stopped | error | saved-on-disk
    started_at: float = field(default_factory=time.time)
    clock: str = ""
    routes: List[Dict[str, str]] = field(default_factory=list)
    rows: Optional[List[Dict[str, Any]]] = field(default_factory=list)   # None = released from memory (saved runs only)
    meta: Dict[str, Any] = field(default_factory=dict)
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""
    saved_as: Optional[str] = None
    on_disk: bool = False
    last_tick: Optional[Dict[str, Any]] = None   # newest heartbeat, pushed by Manager._live
    live_dirty: bool = False                     # new data since the last live push
    state_dirty: bool = False                    # run metadata changed (start event)

    host: Dict[str, Any] = field(default_factory=dict)          # host conditions (server/hostinfo.py)
    bursts: List[list] = field(default_factory=list)            # [endpoint, cycle, start_ns, end_ns] of each ORM work window
    late_waiting: Dict[tuple, Dict[str, Any]] = field(default_factory=dict)   # late replies whose cycle is not reported yet
    n_packets: int = 0            # packet count while the rows are released from memory (rows is None)

    @property
    def expected(self) -> int:
        return self.cfg["virtual_endpoints"] * self.cfg["pings_per_cycle"] * int(self.cfg.get("cycles") or 1)

    def full_meta(self) -> Dict[str, Any]:
        return {**self.meta, "host": self.host} if self.host else dict(self.meta)

    def brief(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "status": self.status, "cfg": self.cfg,
                "clock": self.clock, "routes": self.routes, "saved_as": self.saved_as,
                "on_disk": self.on_disk, "error": self.error, "expected": self.expected,
                "scenario": scenario_key(self.cfg), "started_at": self.started_at,
                "packets": len(self.rows) if self.rows is not None else self.n_packets}


class Manager:
    """The dashboard's state: starts and stops probe processes, queues batches, collects their events and
    pushes updates to every open browser tab over WebSocket."""
    def __init__(self) -> None:
        self.runs: Dict[str, Run] = {}
        self.current: Optional[Run] = None
        self.proc: Optional[asyncio.subprocess.Process] = None
        self.clients: set[WebSocket] = set()
        self._counter = 0
        self.probe_core: Optional[int] = None
        self._floor_cache: Dict[str, Dict[str, Any]] = {}
        self._lru: "OrderedDict[str, None]" = OrderedDict()   # run ids with rows in memory, least recently used first
        self.startup_check: Dict[str, Any] = {}
        self.batch: Optional[Dict[str, Any]] = None      # queued repeats (start_batch)
        # Save every finished run (done or stopped, with data) to the results folder straight away, like the terminal
        # runner does, so a batch can never be lost by closing the dashboard. --no-autosave turns it off.
        self.autosave = True
        self._batch_counter = 0
        self.all_cores: List[int] = []

    def forget(self, run: Run) -> None:
        """Drop a run from the dashboard (after it was deleted): memory, caches, and the current-run pointer."""
        self.runs.pop(run.id, None)
        self._lru.pop(run.id, None)
        self._floor_cache.pop(run.id, None)
        if self.current is run:
            self.current = None

    # -- saving ------------------------------------------------------------------
    async def save(self, run: Run) -> str:
        """Write the run to the results folder (CSVs, .meta.json, INDEX.md entry); no-op if already saved.
        The file writing runs in a worker thread so the event loop keeps reading probe output meanwhile."""
        if run.saved_as:
            return run.saved_as
        rows = self.rows_of(run)
        meta = run.full_meta()
        meta["timeline"], meta["bursts"] = run.timeline, run.bursts
        meta["clock"], meta["routes"] = run.clock, run.routes          # shown in the drill-down after a reload
        an = await asyncio.to_thread(analysis.analyse, rows, run.meta, run.cfg)
        await asyncio.to_thread(analysis.save_run, str(RESULTS_DIR), run.name, run.cfg, meta, rows, an)
        run.saved_as = run.name
        return run.name

    # -- memory: packet rows of saved runs are released and reloaded on demand ----------
    def rows_of(self, run: Run) -> List[Dict[str, Any]]:
        """The run's packet rows, reloading them from its saved CSV if they were released."""
        if run.rows is None:
            try:
                run.rows = analysis.load_rows(str(RESULTS_DIR / f"{run.saved_as}.csv"))
            except OSError as exc:           # the saved files were moved or deleted while the dashboard ran
                run.rows, run.error = [], f"saved data could not be reloaded: {exc}"
        self._lru.pop(run.id, None)
        self._lru[run.id] = None
        self._enforce_budget(keep=run.id)
        return run.rows

    def _enforce_budget(self, keep: Optional[str] = None) -> None:
        def evictable(r: Run) -> bool:
            return (r.rows is not None and r.saved_as is not None and r.id != keep and r is not self.current
                    and r.status not in ("starting", "running"))
        total = sum(len(r.rows) for r in self.runs.values() if r.rows is not None)
        for rid in list(self._lru):
            if total <= ROW_BUDGET:
                break
            r = self.runs.get(rid)
            if r is not None and evictable(r):
                total -= len(r.rows)
                r.n_packets, r.rows = len(r.rows), None       # the CSV on disk still has every packet
                self._lru.pop(rid, None)

    def memory(self) -> Dict[str, Any]:
        """What the dashboard holds: process memory, runs, packets in memory, unsaved runs."""
        loaded = sum(len(r.rows) for r in self.runs.values() if r.rows is not None)
        unsaved = [r for r in self.runs.values() if not r.saved_as and r.status not in ("starting", "running")]
        return {"pid": os.getpid(), "rss_mb": housekeeping.rss_mb(), "runs": len(self.runs), "packets_in_memory": loaded,
                "row_budget": ROW_BUDGET, "released_runs": sum(1 for r in self.runs.values() if r.rows is None),
                "unsaved_runs": len(unsaved), "unsaved_packets": sum(len(r.rows or []) for r in unsaved)}

    # -- persistence ---------------------------------------------------------
    def load_saved(self) -> None:
        for base in analysis.list_saved(str(RESULTS_DIR)):
            try:
                rows = analysis.load_rows(str(RESULTS_DIR / f"{base}.csv"))
            except Exception:
                continue
            cfg: Dict[str, Any] = {"targets": ",".join(dict.fromkeys(r["target"] for r in rows)) or "?",
                                   "virtual_endpoints": len({r["ep"] for r in rows}),
                                   "pings_per_cycle": 5, "interval_s": 1.0, "stagger_window_s": None,
                                   "db_write_semaphore": None, "simulated_db_ms": None, "note": "",
                                   "engine": "python", "cpu_mode": "single_core", "cycles": 1, "timeout_s": 2.0,
                                   # runs saved before this was a setting: the data shows whether NIC stamps were on
                                   "hw_timestamps": any(r["hrx"] for r in rows)}
            cfg.update({k: v for k, v in (parse_name(base) or {}).items() if k != "targets"})   # name carries the config
            meta: Dict[str, Any] = {}
            mp = RESULTS_DIR / f"{base}.meta.json"
            if mp.exists():
                try:
                    j = json.loads(mp.read_text())
                    cfg.update(j.get("config", {}))
                    meta = j.get("meta", {})
                except Exception:
                    pass
            timeline = meta.pop("timeline", [])        # canary heartbeat series saved with the run
            host = meta.pop("host", {})
            bursts = meta.pop("bursts", [])
            clock, routes = meta.pop("clock", ""), meta.pop("routes", [])
            r = Run(id="disk-" + base, name=base, cfg=cfg, status="saved-on-disk", rows=rows, meta=meta, timeline=timeline,
                    saved_as=base, on_disk=True, started_at=run_start_time(base, RESULTS_DIR / f"{base}.csv"), host=host,
                    bursts=bursts, clock=clock, routes=routes)
            self.runs[r.id] = r
            self._lru[r.id] = None
            self._enforce_budget()                    # a large results folder is not all held in memory

    def make_name(self, cfg: Dict[str, Any]) -> str:
        return result_name(cfg["targets"].split(","), cfg["virtual_endpoints"], cfg["stagger_window_s"],
                           cfg["db_write_semaphore"], cfg["simulated_db_ms"], cfg["pings_per_cycle"],
                           cfg["interval_s"], engine=cfg["engine"], cpu_mode=cfg["cpu_mode"], tag=cfg.get("tag", ""),
                           cycles=cfg.get("cycles", 1), cycle_s=cfg.get("cycle_length_s"))

    def build_argv(self, c: Dict[str, Any]) -> List[str]:
        """Command line for the chosen engine.  All three engines take the same flags."""
        common = ["--targets", c["targets"], "--virtual-endpoints", str(c["virtual_endpoints"]),
                  "--pings", str(c["pings_per_cycle"]), "--interval", str(c["interval_s"]),
                  "--stagger-window", str(c["stagger_window_s"]), "--semaphore", str(c["db_write_semaphore"]),
                  "--simulated-db-ms", str(c["simulated_db_ms"]), "--timeout", str(c["timeout_s"]),
                  "--cycles", str(c["cycles"]), "--cycle-length", str(c["cycle_length_s"])]
        single = c["cpu_mode"] == "single_core"
        if c["engine"] == "python":
            argv = [sys.executable, str(ROOT / "probe_lab.py"), "--jsonl", *common,
                    "--cpu-mode", c["cpu_mode"], "--cpu", str(self.probe_core) if self.probe_core is not None else "-1"]
            argv.append("--hw" if c["hw_timestamps"] else "--no-hw")
        else:
            argv = [str(WORKER_BIN[c["engine"]]), *common, "--cpu-mode", c["cpu_mode"]]
            if single and self.probe_core is not None:
                argv += ["--cpu", str(self.probe_core)]
        # The web server keeps itself off the probe core, and children inherit that mask.  For
        # multi_core runs give the child every core back (taskset sets the mask before it starts).
        if not single and self.all_cores and shutil.which("taskset"):
            argv = ["taskset", "-c", ",".join(map(str, self.all_cores))] + argv
        # If this dashboard dies for ANY reason (kill -9, crash, closed terminal), the kernel sends the probe SIGTERM
        # ("parent-death signal"), and every engine ends cleanly on SIGTERM (Python also restores the NIC setting).
        # Without setpriv the probes still stop by themselves once they notice nobody reads their output.
        if shutil.which("setpriv"):
            argv = ["setpriv", "--pdeathsig", "TERM", "--"] + argv
        return argv

    # -- websocket fan-out ---------------------------------------------------
    async def broadcast(self, msg: Dict[str, Any]) -> None:
        dead = []
        text = json.dumps(msg)
        for ws in list(self.clients):
            try:
                # A browser that stopped reading must not stall updates for everyone else.
                await asyncio.wait_for(ws.send_text(text), SEND_TIMEOUT_S)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    def state(self) -> Dict[str, Any]:
        cur = self.current
        return {"root": os.geteuid() == 0, "running": bool(cur and cur.status in ("starting", "running")),
                "current": cur.brief() if cur else None,
                "runs": [r.brief() for r in self.runs.values()],
                "probe_core": self.probe_core, "engines": engine_available(), "defaults": EPHEMRES,
                "batch": None if not self.batch else {"id": self.batch["id"], "done": self.batch["done"],
                                                      "total": self.batch["total"]},
                "server": self.memory(), "problems": self.startup_check.get("problems", []), "autosave": self.autosave}

    # -- run lifecycle -------------------------------------------------------
    async def start(self, cfg: RunConfig, extra: Optional[Dict[str, Any]] = None) -> Run:
        """Start one run. ``extra`` adds bookkeeping fields to its config (batch series id, repeat number)."""
        if self.current and self.current.status in ("starting", "running"):
            raise HTTPException(409, "a run is already in progress")
        try:
            targets = parse_targets(cfg.targets)
        except ValueError as exc:
            raise HTTPException(422, f"bad targets: {exc}")
        if not targets or len(targets) > 32:
            raise HTTPException(422, "provide 1-32 IPv4 targets")
        if not engine_available()[cfg.engine]:
            raise HTTPException(422, f"the {cfg.engine} worker is not built; run ./build_workers.sh")
        if cfg.hw_timestamps and cfg.engine != "python":
            raise HTTPException(422, "NIC hardware timestamps exist only in the Python engine; switch them off "
                                     "for Go/Rust (and for any run you want to compare with Go/Rust)")
        busy = (cfg.pings_per_cycle - 1) * cfg.interval_s + cfg.timeout_s
        if cfg.cycles > 1 and cfg.cycle_length_s < busy:
            raise HTTPException(422, f"Cycle length must be at least {busy:g} s: one cycle's pings take "
                                     f"(pings - 1) x interval + timeout = {busy:g} s")
        if cfg.cycles * cfg.pings_per_cycle > 0x10000:
            raise HTTPException(422, "Cycles x pings per cycle must be at most 65536 (16-bit ICMP sequence numbers)")
        self._counter += 1
        c = cfg.model_dump()
        c["targets"] = ",".join(targets)
        if c["role"] == "floor":
            # The idle floor: identical packets, schedule, timeout and engine, only the CPU work removed, so
            # "lag above floor" isolates exactly what the ORM work adds (a near-idle 1-endpoint run would let
            # the CPU sleep deeper and give a misleadingly HIGH floor).
            c["simulated_db_ms"] = 0.0
            c["tag"] = c["tag"] or "floor"
            c["note"] = c["note"] or "idle floor: this setup with no ORM work"
        c.update(extra or {})
        run = Run(id=f"run{self._counter}", name=self.make_name(c), cfg=c)
        self.runs[run.id] = run
        self.current = run          # registered BEFORE any await, so a second start gets its 409 straight away
        # Host conditions at the start of the run (CPU governor, sleep states, NIC interrupts...).
        probe_core = self.probe_core if (cfg.engine == "python" or cfg.cpu_mode == "single_core") else None
        ifaces = await asyncio.to_thread(lambda: [discover_route(t).interface for t in targets])
        run.host = await asyncio.to_thread(collect_host_info, ifaces, probe_core)

        argv = self.build_argv(c)
        try:
            # start_new_session: the probe gets its own process group, so Ctrl-C typed in the dashboard's terminal
            # does not ALSO hit the probe (and Python's worker processes) directly. Only the dashboard stops it, once,
            # in order; a second, overlapping Ctrl-C would make Python abort its cleanup half-way.
            self.proc = await asyncio.create_subprocess_exec(
                *argv, cwd=str(ROOT), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                start_new_session=True)
        except Exception as exc:
            # Never leave the run in "starting": that status blocks every later run (409).
            run.status, run.error = "error", f"could not start the {cfg.engine} engine: {exc}"
            await self.broadcast({"type": "state", **self.state()})
            raise HTTPException(500, run.error)
        run.status = "running"
        asyncio.create_task(self._pump(run, self.proc))
        await self.broadcast({"type": "state", **self.state()})
        return run

    async def shutdown(self) -> List[str]:
        """Close down for good: cancel any batch, stop the running probe and WAIT until it has exited (escalating
        from Ctrl-C to SIGTERM to SIGKILL), then check nothing of the lab is left running. Returns the report
        printed in the terminal."""
        report = []
        self.batch = None
        proc, run = self.proc, self.current
        if proc and proc.returncode is None:
            t0 = time.monotonic()
            how = "stopped with Ctrl-C (SIGINT)"
            for sig, wait in ((signal.SIGINT, SHUTDOWN_WAIT_S[0]), (signal.SIGTERM, SHUTDOWN_WAIT_S[1]), (signal.SIGKILL, 2.0)):
                try:
                    proc.send_signal(sig)
                except ProcessLookupError:
                    break
                try:
                    await asyncio.wait_for(proc.wait(), wait)
                    break
                except asyncio.TimeoutError:
                    how = {signal.SIGINT: "did not stop on Ctrl-C; sent SIGTERM",
                           signal.SIGTERM: "did not stop on SIGTERM; KILLED (its cleanup did not run)"}.get(sig, how)
            report.append(f"probe pid {proc.pid} ({run.name if run else '?'}): {how}; exited with code {proc.returncode} "
                          f"after {time.monotonic() - t0:.1f} s")
        else:
            report.append("no probe was running")
        unsaved = [r for r in self.runs.values() if not r.saved_as and r.rows]
        if unsaved:
            report.append(f"{len(unsaved)} unsaved run(s) discarded: " + ", ".join(r.name for r in unsaved))
        m = self.memory()
        report.append(f"this dashboard held {m['rss_mb']} MB ({m['packets_in_memory']} packets in memory); the system gets all "
                      f"of it back when the process exits")
        left = await asyncio.to_thread(housekeeping.check)
        report += [f"STILL RUNNING: {p}" for p in left["problems"]] or ["check: no probe or worker process of the lab is left, "
                                                                        "and no NIC timestamping is left on"]
        return report

    async def stop(self) -> None:
        self.batch = None                           # Stop also cancels the rest of a batch
        if self.proc and self.proc.returncode is None:
            self.proc.send_signal(signal.SIGINT)    # probe_lab freezes the canary and emits a summary

    async def _pump(self, run: Run, proc: asyncio.subprocess.Process) -> None:
        """Read the child's stdout as fast as it is written.  Nothing in this loop waits
        for a browser or does heavy work, so the pipe never fills up (see module docstring)."""
        stderr_task = asyncio.create_task(proc.stderr.read())
        live_task = asyncio.create_task(self._live(run))
        assert proc.stdout is not None
        try:
            async for raw in proc.stdout:
                try:
                    ev = json.loads(raw)
                except ValueError:
                    continue
                self._handle(run, ev)
        finally:
            live_task.cancel()
            await proc.wait()
            err = (await stderr_task).decode(errors="replace").strip()
            if run.meta.get("stopped"):
                run.status = "stopped"
            elif run.meta and proc.returncode == 0:
                run.status = "done"
            else:
                run.status = "error"
                run.error = err[-600:] or f"probe exited with code {proc.returncode}"
            # Final analysis in a worker thread too: on a big run it takes long enough to
            # freeze every connected browser's WebSocket if it ran on the event loop.
            try:
                payload = await asyncio.to_thread(self._payload, run)
            except Exception as exc:          # browsers must still learn that the run ended
                print(f"final analysis failed: {exc!r}", file=sys.stderr)
                payload = {"analysis": analysis.analyse([], {}), "timeline": run.timeline}
            if self.autosave and run.status in ("done", "stopped") and run.rows:
                try:
                    await self.save(run)
                except Exception as exc:              # a full disk etc.: keep the run in memory, say why
                    run.error = f"auto-save failed: {exc}"
                    print(f"auto-save of {run.name} failed: {exc!r}", file=sys.stderr)
            await self.broadcast({"type": "done", "run": run.brief(), **payload, "state": self.state()})
            if self.batch:
                asyncio.create_task(self._next_in_batch(run))

    # -- batches (repeated runs) -----------------------------------------------
    async def start_batch(self, body: "BatchBody") -> Dict[str, Any]:
        """Queue repeats of one setup over one or more engines, then run them one after another.

        Round k runs every engine once, the order rotated each round (Py Go Rs, Go Rs Py, Rs Py Go, ...), so a
        slow drift on the machine (temperature, background load) is spread over all engines instead of
        hitting whichever runs last.  With ``with_floor`` each engine's idle-floor run comes just before its
        test run in every round, so each test is matched to a floor measured moments earlier."""
        if self.current and self.current.status in ("starting", "running"):
            raise HTTPException(409, "a run is already in progress")
        engines = list(dict.fromkeys(body.engines or [body.run.engine]))
        if body.run.hw_timestamps and any(e != "python" for e in engines):
            raise HTTPException(422, "NIC hardware timestamps exist only in the Python engine; switch them off to "
                                     "alternate engines")
        for e in engines:
            if not engine_available()[e]:
                raise HTTPException(422, f"the {e} worker is not built; run ./build_workers.sh")
        self._batch_counter += 1
        series = f"b{self._batch_counter}-{time.strftime('%H%M%S')}"
        queue = []
        for k in range(body.repeats):
            order = engines[k % len(engines):] + engines[:k % len(engines)]
            for e in order:
                for role in (["floor", "test"] if body.with_floor else ["test"]):
                    cfg = body.run.model_copy(update={"engine": e, "role": role, "hw_timestamps": body.run.hw_timestamps and e == "python",
                                                      "tag": body.run.tag or series})
                    queue.append((cfg, {"series_id": series, "repeat": k + 1, "repeats": body.repeats}))
        total = len(queue)                      # before the first run is taken off the queue
        self.batch = {"id": series, "total": total, "done": 0, "queue": queue}
        first = await self._next_in_batch(None)
        return {"series_id": series, "total": total, "first": first.brief() if first else None}

    async def _next_in_batch(self, finished: Optional[Run]) -> Optional[Run]:
        b = self.batch
        if not b:
            return None
        if finished is not None:
            if finished.status != "done":           # stopped or failed: do not carry on blindly
                self.batch = None
                await self.broadcast({"type": "state", **self.state()})
                return None
            b["done"] += 1
        if not b["queue"]:
            self.batch = None
            await self.broadcast({"type": "state", **self.state()})
            return None
        cfg, extra = b["queue"].pop(0)
        try:
            return await self.start(cfg, extra)
        except HTTPException as exc:
            self.batch = None
            print(f"batch stopped: {exc.detail}", file=sys.stderr)
            await self.broadcast({"type": "state", **self.state()})
            if finished is None:
                raise
            return None

    def _payload(self, run: Run) -> Dict[str, Any]:
        return {"analysis": self.analysis_of(run), "timeline": run.timeline}

    def analysis_of(self, run: Run) -> Dict[str, Any]:
        """The run's analysis plus its matching idle floor (summary["floor"]; None if no floor run exists)."""
        an = analysis.analyse(self.rows_of(run), run.meta, run.cfg, run.bursts)
        an["summary"]["floor"] = self.floor_for(run)
        an["summary"]["is_floor"] = is_floor(run.cfg)
        return an

    # Everything that sets the packet rate and the wake-up pattern; db_ms and the semaphore are what a
    # floor run deliberately leaves out.
    FLOOR_KEYS = ("engine", "cpu_mode", "targets", "virtual_endpoints", "pings_per_cycle", "interval_s", "timeout_s",
                  "stagger_window_s", "cycles", "cycle_length_s", "hw_timestamps")

    def floor_for(self, run: Run) -> Optional[Dict[str, Any]]:
        """Lag figures of the most recent finished floor run measured with the same setup, or None."""
        if is_floor(run.cfg):
            return None
        key = floor_key(run.cfg, self.FLOOR_KEYS)
        cands = [r for r in self.runs.values() if is_floor(r.cfg) and r.status in ("done", "saved-on-disk")
                 and floor_key(r.cfg, self.FLOOR_KEYS) == key]
        if not cands:
            return None
        f = max(cands, key=lambda r: r.started_at)
        if f.id not in self._floor_cache:          # a finished run's data never changes
            s = analysis.analyse(self.rows_of(f), f.meta, f.cfg)["summary"]
            self._floor_cache[f.id] = {"run_id": f.id, "name": f.name, "started_at": f.started_at, **{
                k: s.get(k) for k in ("lag_mean_us", "lag_p50_us", "lag_p95_us", "lag_p99_us", "lag_max_us",
                                      "n_lag", "send_lag_mean_us", "send_lag_p95_us", "pct_total")}}
        return self._floor_cache[f.id]

    async def _live(self, run: Run) -> None:
        """Push live updates while a run is in progress, at most once per LIVE_PERIOD_S.

        Runs as its own task so that a slow analysis or a slow browser delays only the
        dashboard, never the reading of the probe's stdout.  The analysis runs in a worker
        thread on a snapshot of the rows (the reader keeps appending to the real list)."""
        while True:
            await asyncio.sleep(LIVE_PERIOD_S)
            if run.state_dirty:
                run.state_dirty = False
                await self.broadcast({"type": "state", **self.state()})
            if not run.live_dirty:
                continue
            run.live_dirty = False
            rows, timeline, tick = run.rows[:], run.timeline[:], run.last_tick
            try:
                an = await asyncio.to_thread(analysis.analyse, rows, run.meta, run.cfg, run.bursts[:])
                an["summary"]["floor"] = self.floor_for(run)
                an["summary"]["is_floor"] = is_floor(run.cfg)
            except Exception as exc:          # a bad row must not end live updates for the whole run
                print(f"live analysis failed: {exc!r}", file=sys.stderr)
                continue
            await self.broadcast({"type": "live", "run": run.brief(), "tick": tick,
                                  "analysis": an, "timeline": timeline})

    def _handle(self, run: Run, ev: Dict[str, Any]) -> None:
        """Store one event.  Deliberately synchronous: it must never wait on anything."""
        kind = ev.get("e")
        if kind == "start":
            run.clock, run.routes = ev.get("clock", ""), ev.get("routes", [])
            run.state_dirty = True
        elif kind == "cycle":
            if ev.get("db_start_ns") is not None:
                run.bursts.append([ev["ep"], ev["cyc"], ev["db_start_ns"], ev.get("db_end_ns")])
            for pkt in ev["packets"]:
                row = analysis.make_row(ev["ep"], ev["cyc"], ev["icmp_id"], ev["target"], pkt)
                run.rows.append(row)
                late = run.late_waiting.pop((row["icmp_id"], row["seq"]), None) if run.late_waiting else None
                if late:
                    analysis.attach_late([row], late)
        elif kind == "late":
            # A reply that arrived after its ping timed out.  Usually its cycle is still running (the
            # cycle event comes after the database step), so park it until the row exists.
            if not analysis.attach_late(run.rows, ev):
                run.late_waiting[(ev["icmp_id"], ev["seq"])] = ev
        elif kind == "tick":
            run.timeline.append({"t": ev["t"], "avg": ev["recent_avg_us"], "max": ev["recent_max_us"],
                                 "replied": ev["replied"]})
            run.last_tick, run.live_dirty = ev, True
        elif kind == "summary":
            run.meta = {k: v for k, v in ev.items() if k != "e"}
            run.late_waiting.clear()           # replies for warm-up pings or unreported cycles


def run_start_time(base: str, csv_path: Path) -> float:
    """When the run STARTED: the WHEN part of its name (YYYYMMDD-HHMMSS, local time). The file's modification time
    is when it was SAVED, which for runs saved together (or copied) is the same for all of them."""
    try:
        return time.mktime(time.strptime(base[:15], "%Y%m%d-%H%M%S"))
    except ValueError:
        return csv_path.stat().st_mtime         # a name outside the convention: the best we have


def is_floor(cfg: Dict[str, Any]) -> bool:
    return cfg.get("role") == "floor" or (cfg.get("role") is None and cfg.get("tag") == "floor")


def floor_key(cfg: Dict[str, Any], keys) -> tuple:
    """Comparable form of the settings a floor run must share with a test run (same normalisation as the
    like-for-like check, so 24 == 24.0 and an old run's missing values take their implicit defaults)."""
    out = []
    for k in keys:
        if k == "cycle_length_s" and int(cfg.get("cycles") or 1) <= 1:
            out.append("n/a")
        else:
            out.append(analysis._setting(cfg.get(k, analysis.COMPARE_DEFAULTS.get(k))))
    return tuple(out)


mgr = Manager()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start-up check for leftovers from an earlier session, and a clean shutdown of any running probe."""
    # Start-up: anything left over from an earlier session (orphaned probes, NIC stamping left on)?
    mgr.startup_check = await asyncio.to_thread(housekeeping.check)
    for line in mgr.startup_check["problems"]:
        print(f"WARNING at start-up: {line}", file=sys.stderr)
    mgr.load_saved()
    m = mgr.memory()
    print(f"dashboard pid {m['pid']}: {m['runs']} saved run(s) loaded, {m['packets_in_memory']} packets in memory, "
          f"{m['rss_mb']} MB", file=sys.stderr)
    yield
    print("shutting down...", file=sys.stderr)
    for line in await mgr.shutdown():
        print(f"  {line}", file=sys.stderr)
    print("dashboard closed.", file=sys.stderr)


app = FastAPI(title="ephemres-observer-lab", lifespan=lifespan)
# Everything the page needs (including Chart.js, under static/vendor/) is served from this machine: no internet needed.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def same_site_only(request, call_next):
    """Applies request_allowed() to every HTTP request (WebSockets are checked in ws_endpoint)."""
    if not request_allowed(request.headers.get("host"), request.headers.get("origin")):
        return PlainTextResponse("forbidden: request from another site or unexpected Host header", 403)
    return await call_next(request)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/state")
async def api_state() -> Dict[str, Any]:
    return mgr.state()


@app.post("/api/run")
async def api_run(cfg: RunConfig) -> Dict[str, Any]:
    run = await mgr.start(cfg)
    return run.brief()


class BatchBody(BaseModel):
    run: RunConfig
    repeats: int = Field(3, ge=1, le=20, description="rounds; each round runs every engine once")
    engines: List[Literal["python", "go", "rust"]] = Field(default_factory=list, description="empty = run.engine")
    with_floor: bool = Field(False, description="also measure each engine's idle floor in every round")


@app.post("/api/batch")
async def api_batch(body: BatchBody) -> Dict[str, Any]:
    return await mgr.start_batch(body)


@app.post("/api/stop")
async def api_stop() -> Dict[str, str]:
    await mgr.stop()
    return {"ok": "stopping"}


def _get(run_id: str) -> Run:
    run = mgr.runs.get(run_id)
    if not run:
        raise HTTPException(404, "unknown run")
    return run


@app.get("/api/runs/{run_id:path}/analysis")
async def api_analysis(run_id: str) -> Dict[str, Any]:
    run = _get(run_id)
    return {"run": run.brief(), **mgr._payload(run), "meta": run.full_meta()}


class SaveBody(BaseModel):
    note: str = Field("", max_length=300)


@app.post("/api/runs/{run_id:path}/save")
async def api_save(run_id: str, body: SaveBody) -> Dict[str, Any]:
    run = _get(run_id)
    if run.status in ("starting", "running"):
        raise HTTPException(409, "run still in progress")
    if run.saved_as:
        return {"saved_as": run.saved_as, "already": True}
    if body.note:
        run.cfg["note"] = body.note
    await mgr.save(run)
    await mgr.broadcast({"type": "state", **mgr.state()})
    return {"saved_as": run.name, "folder": _folder_label()}


class IdsBody(BaseModel):
    ids: List[str] = Field(..., min_length=1, max_length=2000)


@app.post("/api/runs/save-selected")
async def api_save_selected(body: IdsBody) -> Dict[str, Any]:
    """Save the given runs (already-saved ones are skipped)."""
    saved, skipped, failed = [], [], []
    for rid in body.ids:
        run = _get(rid)
        if run.saved_as:
            skipped.append(run.name)
        elif run.status in ("starting", "running") or not run.rows:
            failed.append(f"{run.name}: still running or no data")
        else:
            try:
                saved.append(await mgr.save(run))
            except Exception as exc:
                failed.append(f"{run.name}: {exc}")
    await mgr.broadcast({"type": "state", **mgr.state()})
    return {"saved": saved, "already_saved": skipped, "failed": failed, "folder": _folder_label()}


@app.post("/api/runs/delete")
async def api_delete(body: IdsBody) -> Dict[str, Any]:
    """Remove runs from the lab. A saved run's files and INDEX.md entry are MOVED to <results>/.deleted/<date-time>/
    (recoverable: move them back); an unsaved run is simply dropped from memory. Running runs are refused."""
    runs = [_get(rid) for rid in body.ids]
    busy = [r.name for r in runs if r.status in ("starting", "running")]
    if busy:
        raise HTTPException(409, "cannot delete a run that is still in progress: " + ", ".join(busy))
    trash = RESULTS_DIR / ".deleted" / time.strftime("%Y%m%d-%H%M%S")
    moved, dropped, failed = [], [], []
    for run in runs:
        try:
            if run.saved_as:
                await asyncio.to_thread(analysis.trash_run, str(RESULTS_DIR), run.saved_as, str(trash))
                moved.append(run.name)
            else:
                dropped.append(run.name)
        except Exception as exc:
            failed.append(f"{run.name}: {exc}")
            continue
        mgr.forget(run)
    await mgr.broadcast({"type": "state", **mgr.state()})
    return {"moved_to_trash": moved, "discarded_unsaved": dropped, "failed": failed,
            "trash": _folder_label() + "/" + str(trash.relative_to(RESULTS_DIR)) if moved else None}


@app.post("/api/save-all")
async def api_save_all() -> Dict[str, Any]:
    """Save every finished run that is not saved yet (useful with --no-autosave)."""
    saved, failed = [], []
    for run in list(mgr.runs.values()):
        if run.saved_as or run.status in ("starting", "running") or not run.rows:
            continue
        try:
            saved.append(await mgr.save(run))
        except Exception as exc:
            failed.append(f"{run.name}: {exc}")
    await mgr.broadcast({"type": "state", **mgr.state()})
    return {"saved": saved, "failed": failed, "folder": _folder_label()}


def _folder_label() -> str:
    """Where saves really go: test_results/ unless OBSERVER_RESULTS_DIR points elsewhere."""
    try:
        return str(RESULTS_DIR.resolve().relative_to(ROOT))
    except ValueError:
        return str(RESULTS_DIR)


class NoteBody(BaseModel):
    note: str = Field("", max_length=300)


@app.post("/api/runs/{run_id:path}/note")
async def api_note(run_id: str, body: NoteBody) -> Dict[str, Any]:
    """Set what this run was checking.  Works before and after saving; a saved run's .meta.json and
    INDEX.md entry are updated too, so the note is the same everywhere it is shown."""
    run = _get(run_id)
    run.cfg["note"] = body.note.strip()
    if run.saved_as:
        await asyncio.to_thread(analysis.update_note, str(RESULTS_DIR), run.saved_as, run.cfg["note"])
    await mgr.broadcast({"type": "state", **mgr.state()})
    return {"ok": True, "note": run.cfg["note"]}


@app.get("/api/runs/{run_id:path}/export/{kind}")
async def api_export(run_id: str, kind: str) -> PlainTextResponse:
    run = _get(run_id)
    an = mgr.analysis_of(run)
    if kind == "packets.csv":
        body, mime = analysis.packets_csv(mgr.rows_of(run), run.cfg), "text/csv"
    elif kind == "endpoints.csv":
        body, mime = analysis.endpoints_csv(an), "text/csv"
    elif kind == "report.md":
        body, mime = analysis.markdown(run.name, run.cfg, an, run.full_meta()), "text/markdown"
    else:
        raise HTTPException(404, "unknown export")
    fname = f"{run.name}_{kind}"
    return PlainTextResponse(body, media_type=mime,
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


def _compare_items(ids: str) -> List[Dict[str, Any]]:
    items = []
    for rid in [x for x in ids.split(",") if x]:
        run = _get(rid)
        items.append({"name": run.name, "cfg": run.cfg, "meta": run.meta,
                      "analysis": mgr.analysis_of(run)})
    if not items:
        raise HTTPException(422, "no runs selected")
    return items


@app.get("/api/compare.md")
async def api_compare_md(ids: str, combine: bool = False) -> PlainTextResponse:
    """Markdown comparison table for any number of runs (ids = comma-separated run ids); combine=true merges
    repeated runs into one column per group (median and range)."""
    items = _compare_items(ids)
    body = analysis.compare_combined_markdown(items) if combine else analysis.compare_markdown(items)
    return PlainTextResponse(body, media_type="text/markdown",
                             headers={"Content-Disposition": 'attachment; filename="comparison.md"'})


@app.get("/api/compare.csv")
async def api_compare_csv(ids: str) -> PlainTextResponse:
    """The same comparison as CSV: one row per metric, one column per run."""
    return PlainTextResponse(analysis.compare_csv(_compare_items(ids)), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="comparison.csv"'})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    if not request_allowed(ws.headers.get("host"), ws.headers.get("origin")):
        await ws.close(code=1008)          # policy violation: a page from another site
        return
    await ws.accept()
    mgr.clients.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "state", **mgr.state()}))
        if mgr.current:
            await ws.send_text(json.dumps({"type": "live", "run": mgr.current.brief(), "tick": None,
                                           **mgr._payload(mgr.current)}))
        while True:
            await ws.receive_text()       # we only push; reading detects disconnects
    except WebSocketDisconnect:
        pass
    finally:
        mgr.clients.discard(ws)


def main() -> int:
    """Command-line entry point: parse the options and serve the dashboard with uvicorn."""
    import uvicorn
    ap = argparse.ArgumentParser(description="Observer-effect lab dashboard")
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address (default localhost: the dashboard has NO authentication and runs as root)")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--no-autosave", action="store_true",
                    help="do not save finished runs automatically (then use Save or 'Save all unsaved' on the page)")
    ap.add_argument("--check", action="store_true",
                    help="only check that nothing of the lab is left running (probes, workers, NIC stamping), then exit")
    ap.add_argument("--allowed-host", action="append", default=[],
                    help="extra Host name the dashboard may be reached as (repeatable), "
                         "e.g. this machine's IP when using --host 0.0.0.0")
    a = ap.parse_args()
    if a.check:
        r = housekeeping.check()
        for line in r["problems"] or ["nothing of the lab is running, and no NIC timestamping is left on"]:
            print(line)
        if os.geteuid() != 0:
            print("(run with sudo to also see root's processes: dashboard runs belong to root)")
        return 1 if r["problems"] else 0
    ALLOWED_HOSTS.update(h.lower() for h in [a.host, *a.allowed_host] if h not in ("0.0.0.0", "::"))
    if os.geteuid() != 0:
        print("WARNING: not root - runs will fail to open the raw ICMP socket. Use: sudo python3 -m server.app",
              file=sys.stderr)
    if a.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"WARNING: listening on {a.host} with no authentication; anyone who can reach it can "
              f"send ICMP from this machine.", file=sys.stderr)
    # Is the port free? Check BEFORE loading anything, and say who holds it (usually an older dashboard still open).
    try:
        with socket.socket(socket.AF_INET6 if ":" in a.host else socket.AF_INET) as probe_sock:
            probe_sock.bind((a.host, a.port))
    except OSError as exc:
        owner = housekeeping.port_owner(a.port)
        print(f"Cannot start: port {a.port} on {a.host} is already in use ({exc.strerror}).", file=sys.stderr)
        if owner:
            what = "another Observer Lab dashboard" if "server.app" in str(owner["cmd"]) else "another program"
            print(f"  It is held by pid {owner['pid']}, {what}, started {owner['started']}: {owner['cmd']}", file=sys.stderr)
            print(f"  Stop it with Ctrl-C in its terminal, or: sudo kill {owner['pid']}", file=sys.stderr)
            if owner.get("suspended"):
                print(" " + housekeeping.resume_hint(owner["pid"]), file=sys.stderr)
        print(f"  Or start this one on another port: --port {a.port + 1}", file=sys.stderr)
        return 1
    # Keep the web server off the core the probe will be pinned to.
    cores = sorted(os.sched_getaffinity(0))
    if len(cores) > 1:
        mgr.probe_core = cores[-1]
        mgr.all_cores = cores
        os.sched_setaffinity(0, set(cores[:-1]))
    mgr.autosave = not a.no_autosave
    print(f"auto-save: {'on: finished runs are saved to ' + _folder_label() if mgr.autosave else 'OFF: save runs yourself'}",
          file=sys.stderr)
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
