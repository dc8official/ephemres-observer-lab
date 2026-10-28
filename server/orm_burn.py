"""Simulated ORM / serialisation work that can run in a separate process.

WHY THIS IS A SEPARATE MODULE
-----------------------------
Python's multi-core mode offloads the post-cycle "database write" CPU work to a
ProcessPoolExecutor.  Worker processes are started with the *spawn* method (a
fresh interpreter), which must import the function it is asked to run.  Keeping
it in a tiny module means a worker imports only this file, not the prober.

WHAT CROSSES THE PROCESS BOUNDARY (and why it matters for the experiment)
-------------------------------------------------------------------------
``loop.run_in_executor(pool, run_orm_burn, payload)`` does not share memory.
The payload (a dict holding lists of dicts, like an ORM row set) is
  1. pickled in the parent process (by the pool's feeder THREAD, which needs the GIL),
  2. sent through a pipe to a worker process,
  3. unpickled there, processed, and the result pickled back,
  4. unpickled in the parent by the pool's result-handler THREAD (GIL again).
Steps 1 and 4 steal GIL time from the event-loop thread, and the pipe
round-trip adds latency.  The prober measures the total wait minus the
worker's own burn time and reports it as "IPC overhead".
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional


def init_worker(avoid_core: Optional[int]) -> None:
    """Runs once in every worker process: keep it off the core the event loop uses."""
    if avoid_core is None:
        return
    cores = set(os.sched_getaffinity(0)) | set(range(os.cpu_count() or 1))
    others = cores - {avoid_core}
    if others:
        os.sched_setaffinity(0, others)


def warm(seconds: float = 0.05) -> int:
    """Forces the pool to actually start a worker process (sleeping, no CPU)."""
    time.sleep(seconds)
    return os.getpid()


def run_orm_burn(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Serialise the payload (like an ORM flush would) then spin the CPU until
    ``payload['burn_ms']`` milliseconds have elapsed in total."""
    t0 = time.perf_counter_ns()
    text = json.dumps(payload)                      # touch every field, as a real serialiser would
    end = t0 + int(payload["burn_ms"] * 1e6)
    while time.perf_counter_ns() < end:
        pass
    return {"pid": os.getpid(), "rows": len(payload["packets"]), "bytes": len(text),
            "burn_ms": (time.perf_counter_ns() - t0) / 1e6}
