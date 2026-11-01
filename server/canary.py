"""Event-loop lag canary.

A canary coroutine asks the event loop for one thing only: "wake me in 10 ms".
If the loop is busy (a CPU-bound ORM serialisation, a GC pause, a pile of ready
callbacks) the wake-up happens late.  The lateness is a direct measurement of
how long OTHER coroutines - such as our ICMP socket reader - are being starved:

    lag = (actual elapsed time) - (requested sleep)

Resolution note: asyncio's epoll selector rounds timeouts UP to whole
milliseconds, so even an idle loop shows a few hundred microseconds of "lag".
That is the measurement floor, not contention.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

from server.stats import percentile


class EventLoopCanary:
    """Sleeps 10 ms in a loop and records how late each wake-up was (see the module docstring).

    Keeps the most recent ``window`` samples (about 20 minutes at 10 ms) plus all-time maximum."""
    def __init__(self, interval_s: float = 0.010, window: int = 120000):
        self.interval_s = interval_s
        self._interval_ns = int(interval_s * 1e9)
        # Rolling window (default 120000 ticks = 20 min at 10 ms) of
        # (tick_start_ns, tick_end_ns, lag_us) on time.monotonic_ns().
        self._samples: Deque[Tuple[int, int, float]] = deque(maxlen=window)
        self._task: Optional[asyncio.Task] = None
        self.max_lag_us_all_time = 0.0
        # Measurement gate.  The canary runs from the moment the loop starts so
        # it is already "warm", but only ticks that BEGIN inside the open gate
        # are recorded.  reset() opens it (end of startup), freeze() closes it
        # (end of probing).  Startup work (socket setup, warm-up ping, task
        # creation) and shutdown work (summary formatting, CSV closing) are
        # therefore never counted as probe-time event-loop stalls.
        self._epoch_ns = 0
        self._frozen = False

    async def _run(self) -> None:
        while True:
            t0 = time.monotonic_ns()
            await asyncio.sleep(self.interval_s)
            t1 = time.monotonic_ns()
            if self._frozen or t0 < self._epoch_ns:
                continue                  # tick straddles the gate edge: discard it
            lag_us = max(0.0, (t1 - t0 - self._interval_ns) / 1000.0)
            self._samples.append((t0, t1, lag_us))
            if lag_us > self.max_lag_us_all_time:
                self.max_lag_us_all_time = lag_us

    def reset(self) -> None:
        """Discard everything measured so far and start recording (call after startup)."""
        self._samples.clear()
        self.max_lag_us_all_time = 0.0
        self._epoch_ns = time.monotonic_ns()   # ticks that began earlier are ignored
        self._frozen = False

    def freeze(self) -> None:
        """Stop recording; stats()/window_stats() keep returning what was measured."""
        self._frozen = True

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._run(), name="canary")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    @staticmethod
    def _summarise(lags) -> Dict[str, float]:
        if not lags:
            return {"avg_lag_us": 0.0, "p95_lag_us": 0.0, "max_lag_us": 0.0, "samples": 0}
        s = sorted(lags)
        return {"avg_lag_us": sum(s) / len(s), "p95_lag_us": percentile(s, 0.95),
                "max_lag_us": s[-1], "samples": len(s)}

    def stats(self) -> Dict[str, float]:
        """Rolling-window stats: avg_lag_us, p95_lag_us, max_lag_us."""
        return self._summarise([x[2] for x in self._samples])

    def window_stats(self, start_ns: int, end_ns: int) -> Dict[str, float]:
        """Stats over ticks overlapping [start_ns, end_ns] (monotonic ns):
        "how starved was the loop WHILE this endpoint's pings were in flight?".
        Walks newest-to-oldest and stops early, so cost depends on the window, not on history."""
        lags = []
        for a, b, lag in reversed(self._samples):
            if b < start_ns:
                break
            if a <= end_ns:
                lags.append(lag)
        return self._summarise(lags)

    def recent_stats(self, since_ns: int) -> Dict[str, float]:
        """Stats of ticks that ended after ``since_ns`` (cheap; used for live heartbeats)."""
        return self.window_stats(since_ns, time.monotonic_ns())
