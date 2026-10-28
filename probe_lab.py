#!/usr/bin/env python3
"""probe_lab.py - measure the Observer Effect in an asyncio ICMP monitor (modelled on Ephemres).

Each *virtual endpoint* runs the Ephemres cycle:
    5 pings  ->  wait for db_write_semaphore  ->  CPU-heavy "ORM" work  ->  done
All endpoints share ONE raw ICMP socket and ONE asyncio event loop.  Every reply is
timestamped twice:

    Clock A  the kernel's arrival time, delivered with the packet by recvmsg_into
    Clock B  Python's own clock, read the moment recvmsg_into returns

    observer lag = B - A = how long the reply sat in the kernel's socket queue before
                           this program got around to reading it.

WHY THE LAG HAPPENS
-------------------
asyncio runs everything on one thread, and a coroutine keeps that thread until it
reaches an `await`.  When one endpoint runs its CPU-heavy ORM work inline, the event
loop cannot call the socket reader, so replies for every other endpoint wait in the
kernel queue (their Clock-A stamps are already fixed).  When the loop is finally
free it reads them all, and each Python-side RTT is longer by however long the loop
stayed busy.

CPU MODES (--cpu-mode)
    single_core  the ORM work runs inline on the event loop (how a single-threaded monitor behaves)
    multi_core   the ORM work is sent to a pool of worker processes; the loop stays free to read
                 the socket, but pickling the data across the process boundary has its own cost,
                 which is measured and reported.

Usage (raw sockets need root):
    sudo python3 probe_lab.py --targets 127.0.0.1 --virtual-endpoints 20 --burst
    sudo python3 probe_lab.py --targets 10.0.0.5 --virtual-endpoints 100 --stagger-window 30
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import contextlib
import csv
import io
import ipaddress
import json
import multiprocessing
import os
import shlex
import signal
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from server.canary import EventLoopCanary
from server import orm_burn
from server.naming import result_name
from server.kernel_clock import KernelClockSocket, Reception, RouteInfo, discover_route
from server.analysis import MIN_RTT_FOR_ERROR_US, PACKET_FIELDS
from server.hostinfo import collect as collect_host_info
from server.stats import RingStats, compute_stats, percentile


ID_BASE = 0x1000     # first icmp_id; endpoint i uses ID_BASE + i, the warm-up pings the ids after the last endpoint

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass(eq=False)
class Pending:
    """An echo request waiting for its reply, keyed by (icmp_id, icmp_seq)."""
    target: str
    icmp_id: int
    icmp_seq: int
    tx_real_ns: int
    future: asyncio.Future
    rx: Optional[Reception] = None
    batch: int = 0        # packets drained by the SAME reader wakeup (kernel queue depth)
    wakeup: int = 0       # id of the reader wakeup that delivered this packet
    late_rx: Optional[Reception] = None   # reply that turned up AFTER this ping had timed out


@dataclass
class PacketResult:
    """One echo request and what came back: its send time, the reply (if any) and how the reader got it.

    The properties derive the three numbers the lab is about: kernel RTT (Clock A - send),
    user RTT (Clock B - send) and observer lag (Clock B - Clock A)."""
    endpoint: int
    cycle: int
    target: str
    icmp_id: int
    icmp_seq: int
    tx_real_ns: int
    rx: Optional[Reception]
    batch: int = 0
    wakeup: int = 0
    send_lag_ns: Optional[int] = None    # how late the ping was sent vs its scheduled slot
    pending: Optional[Pending] = None    # keeps late_rx reachable (a late reply may arrive afterwards)

    @property
    def late_rx(self) -> Optional[Reception]:
        return self.pending.late_rx if self.pending else None

    @property
    def kernel_rtt_us(self) -> Optional[float]:
        return None if not self.rx or self.rx.kernel_ns is None else (self.rx.kernel_ns - self.tx_real_ns) / 1e3

    @property
    def user_rtt_us(self) -> Optional[float]:
        return None if not self.rx else (self.rx.user_real_ns - self.tx_real_ns) / 1e3

    @property
    def observer_lag_us(self) -> Optional[float]:
        lag = self.rx.observer_lag_ns if self.rx else None
        return None if lag is None else lag / 1e3

    @property
    def lag_pct(self) -> Optional[float]:
        k, lag = self.kernel_rtt_us, self.observer_lag_us
        return None if k is None or lag is None or k <= 0 else 100.0 * lag / k


@dataclass
class CycleResult:
    """One endpoint's cycle: its pings, per-cycle statistics and the timing of the "database write"
    that followed it (semaphore wait, offload overhead, start/end of the ORM work)."""
    endpoint: int
    cycle: int
    target: str
    icmp_id: int
    packets: List[PacketResult]
    kernel: RingStats
    user: RingStats
    lag: RingStats
    canary: Dict[str, float]
    db_wait_ms: float = 0.0
    db_ipc_ms: float = 0.0      # multi_core only: offload wall time minus the worker's own burn
    db_start_ns: Optional[int] = None   # CLOCK_REALTIME around the ORM work (for the burst shading)
    db_end_ns: Optional[int] = None


@dataclass
class Config:
    """Everything one run needs, as parsed from the command line (or sent by the dashboard)."""
    targets: List[str]
    endpoints: int
    pings: int = 5
    interval: float = 1.0
    timeout: float = 2.0
    cycle_length: float = 60.0
    cycles: int = 1
    semaphore: int = 15
    db_ms: float = 3.0
    db_io_ms: float = 1.0
    burst: bool = False
    warmup: bool = True
    hw: bool = False      # NIC hardware stamps: opt-in, because Go/Rust never enable them (engine parity)
    quiet: bool = False
    cpu: Optional[int] = None
    cpu_mode: str = "single_core"   # single_core: ORM burn inline on the loop; multi_core: ProcessPoolExecutor offload
    id_base: int = ID_BASE
    csv_path: Optional[str] = "test_results/probe_lab.csv"   # None => do not write CSV files
    stagger_window: Optional[float] = None   # seconds over which starts are spread; 0 = burst
    jsonl: bool = False                      # machine-readable events on stdout (used by the dashboard)


# ---------------------------------------------------------------------------
# Raw socket multiplexer: one socket, many virtual endpoints
# ---------------------------------------------------------------------------
class _RawICMPMultiplexer:
    """Owns the raw socket and routes each reply to the coroutine awaiting it.

    Every virtual endpoint gets a unique 16-bit icmp_id.  RFC 792 obliges any
    responder (Windows, Cisco IOS, Linux, pfSense...) to echo id+seq back, so
    (icmp_id, icmp_seq) is a return address even when all endpoints ping the
    SAME target IP.
    """

    def __init__(self, ksock: KernelClockSocket):
        self.k = ksock
        self._pending: Dict[Tuple[int, int], Pending] = {}
        # Pings that timed out, kept so a reply that turns up later is recognised as LATE (and
        # its kernel stamp kept) instead of being lumped together with other programs' pings.
        # A late reply whose Clock A is still inside the timeout was "lost" only because the
        # program read it too late: that loss is caused by the observer, not the network.
        self._expired: Dict[Tuple[int, int], Pending] = {}
        self.on_late = None                     # optional callback(Pending) for each late reply
        self.late = 0
        self.unmatched = 0
        self.reader_calls = 0
        self.sent = 0
        self.replied = 0

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        loop.add_reader(self.k.sock.fileno(), self._on_readable)

    def detach(self, loop: asyncio.AbstractEventLoop) -> None:
        loop.remove_reader(self.k.sock.fileno())

    def _on_readable(self) -> None:
        """Called by the event loop when epoll says the socket has data.

        This only runs when the loop is FREE.  We drain the whole queue because
        epoll is level-triggered: leaving packets behind would just re-fire.

        ``reader_calls`` counts wakeups that delivered at least one reply we were
        waiting for (a wakeup that only found late or foreign replies is not
        counted).  The Go and Rust engines use exactly the same definition, so
        "reader wakeups" and "packets per wakeup" compare like for like.
        """
        drained: List[Pending] = []
        while True:
            try:
                rx = self.k.recv_one()
            except (BlockingIOError, OSError):
                break
            if rx is None:
                continue
            p = self._pending.pop((rx.icmp_id, rx.icmp_seq), None)
            if p is None:
                late = self._expired.pop((rx.icmp_id, rx.icmp_seq), None)
                if late is None:
                    self.unmatched += 1         # someone else's ping (or a duplicate reply)
                else:
                    late.late_rx = rx           # our ping, but it had already timed out
                    self.late += 1
                    if self.on_late:
                        self.on_late(late)
                continue
            p.rx = rx
            drained.append(p)
            if not p.future.done():
                p.future.set_result(None)
        if not drained:
            return
        # Queue depth seen by this wakeup: 1 = the reader was prompt; a big number
        # means that many replies had piled up in the kernel while the loop was busy.
        # (The futures resolved above only wake their coroutines on a LATER loop
        # iteration, so batch/wakeup are filled in before anyone reads them.)
        self.reader_calls += 1
        self.replied += len(drained)
        for p in drained:
            p.batch = len(drained)
            p.wakeup = self.reader_calls

    async def ping(self, target: str, icmp_id: int, seq: int, timeout: float) -> Pending:
        fut = asyncio.get_running_loop().create_future()
        p = Pending(target, icmp_id, seq, 0, fut)
        self._pending[(icmp_id, seq)] = p        # register BEFORE sending: reply can't beat us
        try:
            p.tx_real_ns = self.k.send_echo(target, icmp_id, seq)
            self.sent += 1
        except OSError:
            self._pending.pop((icmp_id, seq), None)
            return p                              # treated as lost
        try:
            await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            if self._pending.pop((icmp_id, seq), None) is not None:
                self._expired[(icmp_id, seq)] = p     # remember it: a late reply may still come
        return p


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
def total_error_pct(packets) -> Optional[float]:
    """PRIMARY error %: total observer lag / total kernel RTT of the packets that have both.  Unlike the
    mean of per-packet ratios, one packet with a tiny RTT cannot dominate it (docs/02, "error %")."""
    pairs = [(p.observer_lag_us, p.kernel_rtt_us) for p in packets
             if p.observer_lag_us is not None and p.kernel_rtt_us and p.kernel_rtt_us > 0]
    k = sum(b for _, b in pairs)
    return 100.0 * sum(a for a, _ in pairs) / k if k else None


def burn_cpu_ms(ms: float) -> None:
    """Synchronous busy loop = stand-in for ORM model building / JSON serialisation.
    It never awaits, so the whole event loop (and the socket reader) is frozen."""
    end = time.perf_counter_ns() + int(ms * 1e6)
    while time.perf_counter_ns() < end:
        pass


class Lab:
    """Runs the experiment: schedules the virtual endpoints, pings, does the simulated database write
    after each cycle, and reports the results (console table, CSV files or JSON events for the dashboard)."""
    HEADER = (f"{'ep':>4} {'cyc':>3} {'target':<15} {'ok/n':>5} | {'K-RTT':>8} {'K-Jit':>7} | "
              f"{'Py-RTT':>8} {'Py-Jit':>7} | {'LagMean':>8} {'LagMax':>8} {'Err%':>6} | "
              f"{'CnryAvg':>7} {'CnryP95':>7} {'CnryMax':>7}")
    UNITS = (f"{'':>4} {'':>3} {'':<15} {'':>5} | {'(us)':>8} {'(us)':>7} | {'(us)':>8} {'(us)':>7} | "
             f"{'(us)':>8} {'(us)':>8} {'':>6} | {'(us)':>7} {'(us)':>7} {'(us)':>7}")

    def __init__(self, cfg: Config, routes: Dict[str, RouteInfo]):
        self.cfg = cfg
        self.routes = routes
        self.k = KernelClockSocket(list(routes.values()), cfg.hw)
        self.mux = _RawICMPMultiplexer(self.k)
        self.canary = EventLoopCanary()
        self.results: List[CycleResult] = []
        self.db_sem: Optional[asyncio.Semaphore] = None
        self._rows = 0
        self._pkt_w = self._cyc_w = None
        self._files: list = []
        self.summary_block = ""
        self.pool: Optional[concurrent.futures.ProcessPoolExecutor] = None
        self.main_core: Optional[int] = None     # core the event loop is pinned to (pool workers avoid it)
        self.ipc_ms: List[float] = []
        self.emit_ns = 0
        self.canary_summary: Dict[str, float] = {}
        self.cyc_path: Optional[str] = None
        self.host: Dict[str, Any] = {}
        self.stopped = False
        self.output_lost = False           # jsonl: the reader of stdout is gone
        self.tearing_down = False          # run() has reached its cleanup
        self._main_task: Optional[asyncio.Task] = None
        self.emit_n = 0

    # -- endpoint plan -------------------------------------------------------
    def endpoint_target(self, idx: int) -> str:
        return self.cfg.targets[idx % len(self.cfg.targets)]     # round-robin over targets

    def start_offset(self, idx: int) -> float:
        """Spread starts evenly across the cycle so one target never sees a flood."""
        c = self.cfg
        if c.burst or c.endpoints <= 1 or c.stagger_window == 0:
            return 0.0
        if c.stagger_window is not None:
            return c.stagger_window * idx / c.endpoints
        window = max(0.0, c.cycle_length - (c.pings - 1) * c.interval - c.timeout)
        return window * idx / c.endpoints

    # -- one endpoint --------------------------------------------------------
    def _orm_payload(self, idx: int, cyc: int, target: str, packets: List[PacketResult]) -> Dict[str, Any]:
        """A realistic ORM-style row set (dicts inside lists, strings and numbers).  In multi_core
        mode this is what gets pickled across the process boundary, so it should look like real
        data rather than an empty dict."""
        return {"burn_ms": self.cfg.db_ms, "endpoint": idx, "cycle": cyc, "target": target,
                "model": "EndpointCycleResult", "tags": ["icmp", "sla", f"ep-{idx}"],
                "packets": [{"seq": p.icmp_seq, "icmp_id": p.icmp_id, "tx_ns": p.tx_real_ns,
                             "kernel_rx_ns": p.rx.kernel_ns if p.rx else None,
                             "user_rx_ns": p.rx.user_real_ns if p.rx else None,
                             "kernel_rtt_us": p.kernel_rtt_us, "user_rtt_us": p.user_rtt_us,
                             "observer_lag_us": p.observer_lag_us, "lost": p.rx is None,
                             "note": f"probe {p.icmp_seq} of endpoint {idx} to {target}"} for p in packets]}

    async def _db_write(self, idx: int, cyc: int, target: str, packets: List[PacketResult]):
        """Semaphore-gated simulated ORM work.
        Returns (semaphore wait ms, IPC overhead ms, start ns, end ns): start/end are CLOCK_REALTIME (the
        packet clocks) around the CPU work, so the dashboard can shade WHEN the work ran behind each
        packet's lag.  Inline: the spin itself.  Offloaded: from handing the job over to getting it back.

        single_core: burn the CPU right here, on the event-loop thread (blocks everything).
        multi_core : hand the payload to a worker process and await it.  The loop stays free to
                     read the socket, but pickling/unpickling happens on pool helper threads in
                     THIS process and contends for the GIL with the loop thread.
        """
        t0 = time.perf_counter()
        ipc_ms = 0.0
        async with self.db_sem:
            waited = (time.perf_counter() - t0) * 1000.0
            work_start = time.clock_gettime_ns(time.CLOCK_REALTIME)
            if self.pool is None:
                burn_cpu_ms(self.cfg.db_ms)                   # blocks the whole loop
            else:
                payload = self._orm_payload(idx, cyc, target, packets)
                t1 = time.perf_counter()
                result = await asyncio.get_running_loop().run_in_executor(self.pool, orm_burn.run_orm_burn, payload)
                ipc_ms = max(0.0, (time.perf_counter() - t1) * 1000.0 - result["burn_ms"])
                self.ipc_ms.append(ipc_ms)
            work_end = time.clock_gettime_ns(time.CLOCK_REALTIME)
            await asyncio.sleep(self.cfg.db_io_ms / 1000)  # async I/O part; still holds the semaphore
        return waited, ipc_ms, work_start, work_end

    async def _endpoint(self, idx: int, t_origin: float) -> None:
        c = self.cfg
        target = self.endpoint_target(idx)
        icmp_id = (c.id_base + idx) & 0xFFFF
        loop = asyncio.get_running_loop()
        for cyc in range(c.cycles):
            start = t_origin + cyc * c.cycle_length + self.start_offset(idx)
            await asyncio.sleep(max(0.0, start - loop.time()))
            w0 = time.monotonic_ns()
            packets: List[PacketResult] = []
            for n in range(c.pings):
                slot = start + n * c.interval              # when this ping SHOULD go out (loop clock)
                await asyncio.sleep(max(0.0, slot - loop.time()))
                # Send-side observer effect: a busy loop also wakes this coroutine late, so the
                # ping leaves late.  It does not change the RTT (tx is read at the real send),
                # but it bends the probing schedule.  loop.time() is CLOCK_MONOTONIC seconds.
                send_lag_ns = int((loop.time() - slot) * 1e9)
                seq = (cyc * c.pings + n) & 0xFFFF
                p = await self.mux.ping(target, icmp_id, seq, c.timeout)
                packets.append(PacketResult(idx, cyc, target, icmp_id, seq, p.tx_real_ns, p.rx, p.batch, p.wakeup,
                                            send_lag_ns, p))
            w1 = time.monotonic_ns()
            canary = self.canary.window_stats(w0, w1)
            wait_ms, ipc_ms, db_start, db_end = await self._db_write(idx, cyc, target, packets)
            res = self._summarise(idx, cyc, target, icmp_id, packets, canary, wait_ms)
            res.db_ipc_ms, res.db_start_ns, res.db_end_ns = ipc_ms, db_start, db_end
            self.results.append(res)
            self._emit(res)

    @staticmethod
    def _summarise(idx, cyc, target, icmp_id, packets, canary, wait_ms) -> CycleResult:
        got = [p for p in packets if p.rx]
        vals = lambda attr: [v for v in (getattr(p, attr) for p in got) if v is not None]
        return CycleResult(idx, cyc, target, icmp_id, packets,
                           compute_stats(vals("kernel_rtt_us")), compute_stats(vals("user_rtt_us")),
                           compute_stats(vals("observer_lag_us")), canary, wait_ms)

    # -- output --------------------------------------------------------------
    @staticmethod
    def _f(v: Optional[float], w: int, d: int = 1) -> str:
        return f"{'n/a':>{w}}" if v is None else f"{v:>{w}.{d}f}"

    def _event(self, obj: dict) -> None:
        """One JSON line on stdout (jsonl mode).  Timed, so the dashboard can report its own cost.

        Never raises.  If the reader is gone (the dashboard closed or died, so the pipe is broken) there is
        nobody left to measure for: stop the run, so the normal cleanup in run() still happens (sockets
        closed, NIC setting restored, worker processes ended) instead of a BrokenPipeError skipping it."""
        if self.output_lost:
            return
        t0 = time.perf_counter_ns()
        try:
            sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
            sys.stdout.flush()
        except (BrokenPipeError, OSError):
            self.output_lost = True
            try:                                   # later prints (and the interpreter's exit flush) go nowhere
                null = os.open(os.devnull, os.O_WRONLY)
                os.dup2(null, sys.stdout.fileno())
                os.close(null)
            except OSError:
                pass
            print("probe: output closed (the dashboard is gone): stopping the run", file=sys.stderr)
            # Stop the run, unless it is already tearing down: a cancel delivered INSIDE the teardown would
            # interrupt it at its next await and skip the remaining steps.
            if self._main_task is not None and not self._main_task.done() and not self.tearing_down:
                self._main_task.cancel()
            return
        self.emit_ns += time.perf_counter_ns() - t0
        self.emit_n += 1

    def _emit(self, r: CycleResult) -> None:
        """Report one finished cycle: as a JSON event (dashboard), or as a console row plus CSV rows."""
        f = self._f
        if self.cfg.jsonl:
            self._event({"e": "cycle", "ep": r.endpoint, "cyc": r.cycle, "target": r.target,
                         "icmp_id": r.icmp_id, "db_wait_ms": round(r.db_wait_ms, 3),
                         "db_ipc_ms": round(r.db_ipc_ms, 3), "db_start_ns": r.db_start_ns, "db_end_ns": r.db_end_ns,
                         "canary": {k: round(v, 1) for k, v in r.canary.items()},
                         "packets": [[p.icmp_seq, p.tx_real_ns,
                                      p.rx.kernel_ns if p.rx else None, p.rx.user_real_ns if p.rx else None,
                                      p.rx.hw_ns if p.rx else None, p.batch, p.wakeup, p.send_lag_ns]
                                     for p in r.packets]})
            return
        if not self.cfg.quiet:
            if self._rows % 25 == 0:
                print(self.HEADER); print(self.UNITS); print("-" * len(self.HEADER))
            self._rows += 1
            err = total_error_pct(r.packets)          # Err% = this cycle's total lag / total kernel RTT
            ok = sum(1 for p in r.packets if p.rx)
            print(f"{r.endpoint:>4} {r.cycle:>3} {r.target:<15} {ok:>2}/{len(r.packets):<2} | "
                  f"{f(r.kernel.avg, 8)} {f(r.kernel.jitter, 7)} | {f(r.user.avg, 8)} {f(r.user.jitter, 7)} | "
                  f"{f(r.lag.avg, 8)} {f(r.lag.max, 8)} {f(err, 6)} | "
                  f"{f(r.canary['avg_lag_us'], 7, 0)} {f(r.canary['p95_lag_us'], 7, 0)} {f(r.canary['max_lag_us'], 7, 0)}",
                  flush=True)
        if self._pkt_w is None:
            return
        for p in r.packets:
            late = p.late_rx      # only known if the late reply came before this row is written
            self._pkt_w.writerow({
                "endpoint": p.endpoint, "cycle": p.cycle, "icmp_id": p.icmp_id, "icmp_seq": p.icmp_seq,
                "target_ip": p.target, "lost": int(p.rx is None), "tx_realtime_ns": p.tx_real_ns,
                "kernel_rx_ns": p.rx.kernel_ns if p.rx else None,
                "user_rx_ns": p.rx.user_real_ns if p.rx else None,
                "hw_rx_ns": p.rx.hw_ns if p.rx else None,
                "kernel_rtt_us": p.kernel_rtt_us, "user_rtt_us": p.user_rtt_us,
                "observer_lag_us": p.observer_lag_us, "reader_batch": p.batch, "wakeup_id": p.wakeup,
                "send_lag_us": None if p.send_lag_ns is None else p.send_lag_ns / 1e3,
                "late_kernel_rx_ns": late.kernel_ns if late else None,
                "late_user_rx_ns": late.user_real_ns if late else None,
                "engine": "python", "cpu_mode": self.cfg.cpu_mode})
        row = {"endpoint": r.endpoint, "cycle": r.cycle, "target_ip": r.target, "icmp_id": r.icmp_id,
               "db_wait_ms": round(r.db_wait_ms, 3), "db_start_ns": r.db_start_ns, "db_end_ns": r.db_end_ns,
               "canary_avg_us": r.canary["avg_lag_us"],
               "canary_p95_us": r.canary["p95_lag_us"], "canary_max_us": r.canary["max_lag_us"]}
        for name, st in (("kernel", r.kernel), ("user", r.user), ("lag", r.lag)):
            row.update({f"{name}_{m}": getattr(st, a) for m, a in
                        (("min_us", "min"), ("max_us", "max"), ("avg_us", "avg"), ("p95_us", "p95"),
                         ("std_us", "std_dev"), ("jitter_us", "jitter"))})
        self._cyc_w.writerow(row)
        for fh in self._files:
            fh.flush()

    def _open_csv(self) -> Optional[str]:
        """Open the per-packet and per-cycle CSV files; returns the per-cycle file's path (None = no CSV)."""
        if not self.cfg.csv_path:
            return None
        base, ext = os.path.splitext(self.cfg.csv_path)
        cyc_path = f"{base}_cycles{ext or '.csv'}"
        pf, cf = open(self.cfg.csv_path, "w", newline=""), open(cyc_path, "w", newline="")
        self._files = [pf, cf]
        self._pkt_w = csv.DictWriter(pf, PACKET_FIELDS)        # same columns as a dashboard-saved run
        cyc_fields = ["endpoint", "cycle", "target_ip", "icmp_id", "db_wait_ms", "db_start_ns", "db_end_ns"] + [
            f"{n}_{m}" for n in ("kernel", "user", "lag")
            for m in ("min_us", "max_us", "avg_us", "p95_us", "std_us", "jitter_us")] + [
            "canary_avg_us", "canary_p95_us", "canary_max_us"]
        self._cyc_w = csv.DictWriter(cf, cyc_fields)
        self._pkt_w.writeheader(); self._cyc_w.writeheader()
        return cyc_path

    # -- run -----------------------------------------------------------------
    def _say(self, *args) -> None:
        """Human console output; silent in jsonl mode (stdout is the event channel there)."""
        if not self.cfg.jsonl:
            print(*args)

    async def _ticker(self) -> None:
        """jsonl mode: heartbeat every 0.5 s with live counters and recent canary lag.
        Uses recent_stats(), which only walks the newest few dozen canary samples."""
        t_start = last = time.monotonic_ns()
        while True:
            await asyncio.sleep(0.5)
            now = time.monotonic_ns()
            rec = self.canary.recent_stats(last)
            last = now
            self._event({"e": "tick", "t": round((now - t_start) / 1e9, 2), "sent": self.mux.sent,
                         "replied": self.mux.replied, "reader_calls": self.mux.reader_calls,
                         "recent_avg_us": round(rec["avg_lag_us"], 1), "recent_max_us": round(rec["max_lag_us"], 1),
                         "max_us": round(self.canary.max_lag_us_all_time, 1)})

    async def run(self) -> None:
        """The whole run: warm-up ping, all endpoints' cycles in parallel, then the summary and cleanup."""
        loop = asyncio.get_running_loop()
        c = self.cfg
        # asyncio.run() turns Ctrl-C (SIGINT) into a cancellation of this task, so every
        # `finally` below runs: CSVs are closed, the summary is emitted and the NIC's
        # hardware-timestamping setting is restored.  A plain `kill` (SIGTERM) would instead
        # end the process on the spot and skip all of that, so treat it the same way.
        self._main_task = asyncio.current_task()
        loop.add_signal_handler(signal.SIGTERM, self._main_task.cancel)
        # Ctrl-C too, replacing asyncio.run()'s own handler: that one turns a SECOND Ctrl-C into a KeyboardInterrupt
        # raised wherever the code happens to be, which could cut the teardown short (before the NIC is restored).
        # Here every Ctrl-C simply means "stop the run"; repeats are harmless.
        loop.add_signal_handler(signal.SIGINT, self._main_task.cancel)
        self.db_sem = asyncio.Semaphore(c.semaphore)
        try:
            self.k.open()
            self.mux.attach(loop)
            cyc_path = self.cyc_path = self._open_csv()
        except BaseException:
            self.k.close()        # open() may have reconfigured the NIC: always restore it
            raise
        self.canary.start()
        ticker: Optional[asyncio.Task] = None
        try:
            for r in self.routes.values():
                self._say(f"route: {r.target} -> via {r.interface} (src {r.src_ip})")
            for n in self.k.notes:
                self._say(n)
            self._say(f"clock A: {self.k.mode}")
            self._say(f"endpoints={c.endpoints} targets={len(c.targets)} pings={c.pings} interval={c.interval}s "
                      f"cycle={c.cycle_length}s x{c.cycles} semaphore={c.semaphore} db={c.db_ms}ms "
                      f"{'BURST' if c.burst or c.stagger_window == 0 else 'staggered'}")
            runtime = "python asyncio, ORM inline on the loop"
            if c.cpu_mode == "multi_core":
                # Worker processes start with "spawn" (fresh interpreters).  Start and warm them NOW,
                # before the canary opens, so process start-up never counts as probing-time lag.
                n = max(1, (os.cpu_count() or 2) - 1)
                self.pool = concurrent.futures.ProcessPoolExecutor(
                    max_workers=n, mp_context=multiprocessing.get_context("spawn"),
                    initializer=orm_burn.init_worker, initargs=(self.main_core,))
                await asyncio.gather(*(loop.run_in_executor(self.pool, orm_burn.warm, 0.1) for _ in range(n)))
                runtime = f"python asyncio, ORM offloaded to ProcessPool x{n}"
            self._say(f"runtime: {runtime}")
            if c.jsonl:
                self._event({"e": "start", "clock": f"{self.k.mode} [{runtime}]", "notes": self.k.notes,
                             "routes": [{"target": r.target, "interface": r.interface, "src_ip": r.src_ip}
                                        for r in self.routes.values()]})
            if c.warmup:     # prime ARP/neighbour caches so ping #1 isn't an outlier
                w = await asyncio.gather(*(self.mux.ping(t, c.id_base + c.endpoints + i, 0, c.timeout)
                                           for i, t in enumerate(c.targets)))
                self._say(f"warm-up: {sum(1 for p in w if p.rx)}/{len(w)} targets answered")
            # Startup is finished (socket, ioctl, warm-up ping, task creation).  Only
            # now does the canary start counting, so its max/p95/avg describe stalls
            # while probes are in flight, not one-off initialisation work.
            self.canary.reset()
            self.mux.sent = self.mux.replied = self.mux.reader_calls = self.mux.unmatched = self.mux.late = 0
            self.mux._expired.clear()             # warm-up pings are not part of the run
            if c.jsonl:                           # late replies are reported the moment they arrive
                self.mux.on_late = lambda p: self._event({
                    "e": "late", "icmp_id": p.icmp_id, "seq": p.icmp_seq, "tx": p.tx_real_ns,
                    "krx": p.late_rx.kernel_ns, "urx": p.late_rx.user_real_ns})
            if c.jsonl:
                ticker = loop.create_task(self._ticker())
            t_origin = loop.time() + 0.1
            await asyncio.gather(*(self._endpoint(i, t_origin) for i in range(c.endpoints)))
        finally:
            # Probing is over (or was interrupted): freeze the canary BEFORE any
            # teardown / summary formatting so that work cannot pollute the numbers.
            self.canary.freeze()
            canary = self.canary.stats()
            self.canary_summary = {k: round(v, 1) for k, v in canary.items()}
            if ticker:
                ticker.cancel()
            # Teardown: every step runs even if an earlier one fails, so one problem (e.g. a broken
            # pipe while reporting) can never leave the NIC reconfigured or worker processes running.
            self.tearing_down = True
            if c.jsonl:
                self._step("summary event", lambda: self._event({
                    "e": "summary", "sent": self.mux.sent, "replied": self.mux.replied,
                    "reader_calls": self.mux.reader_calls, "unmatched": self.mux.unmatched, "late": self.mux.late,
                    "canary": {k: round(v, 1) for k, v in canary.items()},
                    "emit_us_total": round(self.emit_ns / 1e3, 1), "emit_n": self.emit_n,
                    "ipc_ms_mean": round(sum(self.ipc_ms) / len(self.ipc_ms), 3) if self.ipc_ms else None,
                    "ipc_ms_max": round(max(self.ipc_ms), 3) if self.ipc_ms else None,
                    "stopped": sys.exc_info()[0] is not None}))
            try:
                await self.canary.stop()
            except (Exception, asyncio.CancelledError) as exc:
                # The only await in the teardown. A second Ctrl-C or a SIGTERM (e.g. the dashboard's parent-death
                # signal) arriving now cancels the task right here: note it and carry on with the remaining steps
                # instead of letting the cancellation skip them. The run ends straight after anyway.
                print(f"probe: teardown step 'canary' interrupted: {exc!r}", file=sys.stderr)
            if self.pool is not None:
                self._step("worker processes", self._stop_pool)
            self._step("socket reader", lambda: self.mux.detach(loop))
            self._step("raw socket + NIC setting", self.k.close)
            for fh in self._files:
                self._step("CSV file", fh.close)
        if not c.jsonl:
            text = self.summary_text(canary, cyc_path)
            print(text, end="")
            self.summary_block = text

    @staticmethod
    def _step(name: str, fn) -> None:
        """One teardown step; a failure is reported and does not stop the steps after it."""
        try:
            fn()
        except Exception as exc:
            print(f"probe: teardown step '{name}' failed: {exc!r}", file=sys.stderr)

    def _stop_pool(self) -> None:
        """End the ORM worker processes now (multi-core): cancel queued jobs and terminate the workers."""
        workers = list((getattr(self.pool, "_processes", None) or {}).values())
        self.pool.shutdown(wait=False, cancel_futures=True)
        for proc in workers:
            try:
                proc.terminate()
            except Exception:
                pass
        for proc in workers:                       # reap them, so none lingers as a zombie or keeps memory
            proc.join(timeout=2)

    def summary_text(self, canary: Dict[str, float], cyc_path: str) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.summary(canary, cyc_path)
        return buf.getvalue()

    def summary(self, canary: Dict[str, float], cyc_path: str) -> None:
        """Print the end-of-run summary block (the text saved in INDEX.md), cycle 0 excluded when there are several."""
        # With several cycles the first one is a warm-up (the schedule is still ramping up, so
        # fewer endpoints overlap than in steady state): it is saved but left out of the summary.
        # The dashboard's analysis applies exactly the same rule.
        warm = 1 if self.cfg.cycles > 1 else 0
        measured = [r for r in self.results if r.cycle >= warm]
        pk = [p for r in measured for p in r.packets]
        got = [p for p in pk if p.rx]
        if not pk:
            return
        col = lambda attr: [v for v in (getattr(p, attr) for p in got) if v is not None]
        kr, ur, lag, pct = col("kernel_rtt_us"), col("user_rtt_us"), col("observer_lag_us"), col("lag_pct")
        mean = lambda xs: sum(xs) / len(xs) if xs else None
        jit = lambda sel: mean([sel(r).jitter for r in measured if sel(r).jitter is not None])
        f = self._f
        bar = "=" * len(self.HEADER)
        lost = [p for p in pk if not p.rx]
        # Loss split by cause, from the late reply's KERNEL stamp: inside the timeout means the
        # reply was there in time and only the program's lateness made it "lost".
        t_ns = self.cfg.timeout * 1e9
        read_late = sum(1 for p in lost if p.late_rx and p.late_rx.kernel_ns and p.late_rx.kernel_ns - p.tx_real_ns <= t_ns)
        net_late = sum(1 for p in lost if p.late_rx) - read_late
        print(bar)
        if warm:
            print(f"(cycle 0 of {self.cfg.cycles} is a warm-up and is excluded below)")
        print(f"SUMMARY  packets sent={len(pk)} replied={len(got)} lost={len(lost)} "
              f"(reader wakeups={len({p.wakeup for p in got if p.wakeup})}, unmatched replies={self.mux.unmatched})")
        if lost:
            print(f"  Loss by cause        no reply {len(lost) - read_late - net_late}   reply after the timeout {net_late}   "
                  f"reply in time but read too late {read_late}")
        print(f"  Kernel Control RTT   mean {f(mean(kr), 9)} us   mean cycle jitter {f(jit(lambda r: r.kernel), 8)} us   (true wire + OS arrival)")
        print(f"  Python Observer RTT  mean {f(mean(ur), 9)} us   mean cycle jitter {f(jit(lambda r: r.user), 8)} us   (contaminated by event loop)")
        print(f"  Observer intrusion   mean {f(mean(lag), 9)} us   p95 {f(percentile(sorted(lag), 0.95) if lag else None, 9)} us   "
              f"max {f(max(lag) if lag else None, 9)} us")
        k_med = percentile(sorted(kr), 0.5) if kr else None
        if k_med is not None and k_med < MIN_RTT_FOR_ERROR_US:
            print(f"  (median kernel RTT {k_med:.1f} us is under {MIN_RTT_FOR_ERROR_US:g} us: error % is not meaningful "
                  f"here, judge the lag in us)")
        print(f"                       error {f(total_error_pct(got), 6)} %  (total lag / total kernel RTT)   per packet: "
              f"median {f(percentile(sorted(pct), 0.5) if pct else None, 6)} %  mean {f(mean(pct), 6)} %  "
              f"max {f(max(pct) if pct else None, 6)} %")
        print(f"  Event-loop canary    avg {f(canary['avg_lag_us'], 9)} us   p95 {f(canary['p95_lag_us'], 9)} us   "
              f"max {f(canary['max_lag_us'], 9)} us")
        if cyc_path:
            print(f"CSV: {self.cfg.csv_path}  and  {cyc_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_targets(spec: str) -> List[str]:
    """Comma-separated IPv4 addresses; 'a.b.c.d-e.f.g.h' and 'a.b.c.d-N' ranges also accepted."""
    out: List[str] = []
    for part in filter(None, (s.strip() for s in spec.split(","))):
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            lo = ipaddress.IPv4Address(lo_s)
            hi = ipaddress.IPv4Address(hi_s if "." in hi_s else ".".join(lo_s.split(".")[:3] + [hi_s]))
            out.extend(str(ipaddress.IPv4Address(i)) for i in range(int(lo), int(hi) + 1))
        else:
            out.append(str(ipaddress.IPv4Address(part)))
    return list(dict.fromkeys(out))


def pin_cpu(cpu: Optional[int]) -> Optional[int]:
    """Pin the process to one core (sched_setaffinity bitmask) to remove scheduler-migration noise."""
    if cpu is not None and cpu < 0:
        return None
    core = sorted(os.sched_getaffinity(0))[-1] if cpu is None else cpu
    os.sched_setaffinity(0, {core})
    return core


RESULTS_DIR = "test_results"


def effective_window(cfg: Config) -> float:
    """Seconds over which endpoint starts are spread (0 = burst), whichever flag set it."""
    if cfg.burst or cfg.stagger_window == 0:
        return 0.0
    if cfg.stagger_window is not None:
        return cfg.stagger_window
    return max(0.0, cfg.cycle_length - (cfg.pings - 1) * cfg.interval - cfg.timeout)


def write_meta(args: argparse.Namespace, cfg: Config, lab: Lab, host: Dict[str, Any]) -> str:
    """<name>.meta.json: the same layout the dashboard saves, so CLI runs carry their full configuration,
    the counters only the prober knows, and the host conditions (CPU governor, sleep states, NIC IRQs...)."""
    base = os.path.splitext(cfg.csv_path)[0]
    mux = lab.mux
    meta = {"config": {"targets": ",".join(cfg.targets), "virtual_endpoints": cfg.endpoints,
                       "pings_per_cycle": cfg.pings, "interval_s": cfg.interval, "timeout_s": cfg.timeout,
                       "stagger_window_s": effective_window(cfg), "cycles": cfg.cycles,
                       "cycle_length_s": cfg.cycle_length, "db_write_semaphore": cfg.semaphore,
                       "simulated_db_ms": cfg.db_ms, "engine": "python", "cpu_mode": cfg.cpu_mode,
                       "hw_timestamps": cfg.hw, "note": args.note, "tag": args.tag},
            "meta": {"sent": mux.sent, "replied": mux.replied, "reader_calls": mux.reader_calls,
                     "unmatched": mux.unmatched, "late": mux.late, "canary": lab.canary_summary,
                     "ipc_ms_mean": round(sum(lab.ipc_ms) / len(lab.ipc_ms), 3) if lab.ipc_ms else None,
                     "ipc_ms_max": round(max(lab.ipc_ms), 3) if lab.ipc_ms else None, "host": host,
                     "clock": lab.k.mode, "stopped": lab.stopped,
                     # when each endpoint's ORM work ran (dashboard shades these behind the lag dots)
                     "bursts": [[r.endpoint, r.cycle, r.db_start_ns, r.db_end_ns] for r in lab.results]},
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(base + ".meta.json", "w") as fh:
        json.dump(meta, fh, indent=1)
    return base + ".meta.json"


def log_run(args: argparse.Namespace, cfg: Config, lab: Lab) -> None:
    """Append this run (description, exact command, files, summary) to test_results/INDEX.md."""
    base, ext = os.path.splitext(cfg.csv_path)
    cmd = "sudo python3 probe_lab.py " + shlex.join(sys.argv[1:] + ([] if args.csv_given else ["--csv", cfg.csv_path]))
    desc = args.note or (f"{cfg.endpoints} virtual endpoint(s) -> {', '.join(cfg.targets)}; "
                         f"{'burst' if not effective_window(cfg) else 'staggered over %gs' % effective_window(cfg)}; "
                         f"semaphore {cfg.semaphore}, simulated DB {cfg.db_ms} ms")
    index = os.path.join(os.path.dirname(cfg.csv_path) or ".", "INDEX.md")
    with open(index, "a") as fh:
        fh.write(f"\n## {os.path.basename(base)}\n\n- **Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                 f"- **Description:** {desc}\n- **Command:** `{cmd}`\n"
                 f"- **Files:** `{os.path.basename(cfg.csv_path)}` (per packet), "
                 f"`{os.path.basename(base)}_cycles{ext or '.csv'}` (per cycle), `{os.path.basename(base)}.meta.json`\n\n```text\n{lab.summary_block.rstrip()}\n```\n")
    print(f"logged to {index}")


def build_parser() -> argparse.ArgumentParser:
    """Command-line options; the dashboard passes the same options when it starts a Python run."""
    ap = argparse.ArgumentParser(description="Observer-effect benchmark for asyncio ICMP monitoring.")
    ap.add_argument("--targets", required=True, help="comma-separated IPv4s, e.g. 10.0.0.5 or 10.0.0.1,10.0.0.2")
    ap.add_argument("--virtual-endpoints", type=int, default=None,
                    help="number of virtual endpoints (default: one per target); spread round-robin over targets")
    ap.add_argument("--pings", type=int, default=5)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--cycle-length", type=float, default=60.0, help="window over which endpoint starts are staggered")
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--semaphore", type=int, default=15, help="db_write_semaphore size")
    ap.add_argument("--simulated-db-ms", type=float, default=3.0, help="CPU-bound ORM work per endpoint cycle")
    ap.add_argument("--simulated-db-io-ms", type=float, default=1.0, help="async I/O sleep inside the DB write")
    ap.add_argument("--burst", action="store_true", help="no staggering: all endpoints start together (max contention)")
    ap.add_argument("--cpu-mode", choices=["single_core", "multi_core"], default="single_core",
                    help="single_core: ORM burn runs inline on the event loop; "
                         "multi_core: offloaded to a ProcessPoolExecutor (IPC cost is measured)")
    ap.add_argument("--no-warmup", action="store_true")
    ap.add_argument("--hw", action="store_true",
                    help="also record NIC hardware RX timestamps (Python only; changes the NIC setting for the run, so "
                         "leave it off when comparing with Go/Rust runs)")
    ap.add_argument("--no-hw", action="store_true", help="(default) no NIC hardware timestamping; kept for old commands")
    ap.add_argument("--quiet", action="store_true", help="suppress per-cycle rows; print summary only")
    ap.add_argument("--cpu", type=int, default=None, help="core to pin (default last allowed; -1 = don't pin)")
    ap.add_argument("--csv", default=None,
                    help="per-packet CSV path (default: test_results/<timestamp>_<target>_<N>ep.csv); "
                         "also writes <name>_cycles.csv")
    ap.add_argument("--stagger-window", type=float, default=None,
                    help="spread endpoint starts over exactly this many seconds (0 = burst); overrides --cycle-length logic")
    ap.add_argument("--jsonl", action="store_true",
                    help="emit machine-readable JSON events on stdout (used by the web dashboard); no CSV/console table")
    ap.add_argument("--tag", default="", help="short label appended to the result file name to group a series of runs")
    ap.add_argument("--note", default="", help="free-text description stored in test_results/INDEX.md")
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Command-line entry point: check the options, find the route to each target, pin the CPU and run."""
    a = build_parser().parse_args(argv)
    a.csv_given = a.csv is not None
    try:
        targets = parse_targets(a.targets)
    except ValueError as exc:
        print(f"bad --targets: {exc}", file=sys.stderr); return 2
    n_ep = a.virtual_endpoints or len(targets)
    # icmp_id is 16 bits: endpoints use ID_BASE .. ID_BASE+N-1, the warm-up the next len(targets) ids.
    if n_ep < 1 or ID_BASE + n_ep + len(targets) > 0x10000:
        print(f"{n_ep} endpoints + {len(targets)} warm-up ids do not fit the 16-bit icmp_id space "
              f"(max {0x10000 - ID_BASE - len(targets)} endpoints)", file=sys.stderr); return 2
    if a.cycles < 1 or a.cycles * a.pings > 0x10000:      # icmp_seq = cycle * pings + n is 16 bits too
        print("--cycles x --pings must be between 1 and 65536 (the 16-bit icmp_seq space)", file=sys.stderr); return 2
    if a.jsonl:
        a.csv = ""        # dashboard process owns persistence
    if a.csv is None:     # every run is saved under test_results/ with a self-describing name
        window = (a.stagger_window if a.stagger_window is not None else
                  0 if a.burst else max(0.0, a.cycle_length - (a.pings - 1) * a.interval - a.timeout))
        a.csv = os.path.join(RESULTS_DIR, result_name(targets, n_ep, window, a.semaphore, a.simulated_db_ms,
                                                      a.pings, a.interval, cpu_mode=a.cpu_mode, tag=a.tag,
                                                      cycles=a.cycles, cycle_s=a.cycle_length) + ".csv")
    if a.csv:
        os.makedirs(os.path.dirname(a.csv) or ".", exist_ok=True)
    routes = {t: discover_route(t) for t in targets}
    core = pin_cpu(a.cpu)
    host = collect_host_info([r.interface for r in routes.values()], core)
    if not a.jsonl:
        print(f"cpu: {'pinned to core %d' % core if core is not None else 'not pinned'}")
        for w in host.get("warnings", []):
            print(f"host: {w}")
    cfg = Config(targets=targets, endpoints=n_ep, pings=a.pings, interval=a.interval, timeout=a.timeout,
                 cycle_length=a.cycle_length, cycles=a.cycles, semaphore=a.semaphore, db_ms=a.simulated_db_ms,
                 db_io_ms=a.simulated_db_io_ms, burst=a.burst, warmup=not a.no_warmup, hw=a.hw and not a.no_hw,
                 quiet=a.quiet, cpu=a.cpu, cpu_mode=a.cpu_mode, csv_path=a.csv or None,
                 stagger_window=a.stagger_window, jsonl=a.jsonl)
    lab = Lab(cfg, routes)
    lab.main_core = core
    lab.host = host
    try:
        asyncio.run(lab.run())
    except PermissionError:
        print("PermissionError: SOCK_RAW needs root (sudo) or CAP_NET_RAW.", file=sys.stderr); return 1
    except (KeyboardInterrupt, asyncio.CancelledError):    # Ctrl-C / SIGTERM: cleanup already ran
        # Keep what was measured: summarise the finished cycles and log the run as stopped.
        lab.stopped = True
        if lab.results and not cfg.jsonl:
            lab.summary_block = "(stopped early: summary of the cycles that finished)\n" + \
                lab.summary_text(lab.canary_summary, lab.cyc_path)
            print(lab.summary_block, end="")
    if lab.summary_block and cfg.csv_path:
        write_meta(a, cfg, lab, host)
        log_run(a, cfg, lab)
    return 0


if __name__ == "__main__":
    sys.exit(main())
