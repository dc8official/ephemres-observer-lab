"""Small statistics helpers shared by the canary and the probe runner."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence


def percentile(sorted_vals: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile (numpy default) of an already-sorted list."""
    if not sorted_vals:
        return 0.0
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def rfc3550_jitter(samples: Sequence[float]) -> float:
    """RFC 3550 sec 6.4.1 smoothed inter-arrival jitter: ``J += (|D| - J) / 16``.

    RTP uses transit-time differences; for ping we use the difference between
    successive RTTs as D.  The 1/16 gain makes J a slow-moving average: after a spike it
    fades with a time constant of about 16 packets.
    """
    j = 0.0
    for prev, cur in zip(samples, samples[1:]):
        j += (abs(cur - prev) - j) / 16.0
    return j


@dataclass
class RingStats:
    n: int = 0
    min: Optional[float] = None
    max: Optional[float] = None
    avg: Optional[float] = None
    p95: Optional[float] = None
    std_dev: Optional[float] = None     # population standard deviation
    jitter: Optional[float] = None      # RFC 3550


def compute_stats(samples: Sequence[float]) -> RingStats:
    """min / max / avg / p95 / std_dev / RFC3550 jitter of ALL samples (no averaging away)."""
    if not samples:
        return RingStats()
    avg = sum(samples) / len(samples)
    var = sum((x - avg) ** 2 for x in samples) / len(samples)
    return RingStats(len(samples), min(samples), max(samples), avg,
                     percentile(sorted(samples), 0.95), math.sqrt(var), rfc3550_jitter(samples))
