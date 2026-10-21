"""A rate over replicate units, and the paired difference of two, with intervals that respect
the unit. Each unit's (kept, out of) counts give its own rate; the mean over units weighs each
equally. Intervals are the wider of a t interval over units and a Wilson (or Newcombe)
interval over every draw, so units that all agree still show the noise of a few draws."""

from __future__ import annotations

import math
from statistics import NormalDist, mean, stdev
from typing import Any, Mapping, Optional, Sequence

Counts = Mapping[str, tuple[int, int]]   # unit -> (kept, out of), units with out of > 0


class PairedError(ValueError):
    """A question these counts cannot answer."""


def t_quantile(p: float, df: int) -> float:
    """Student's t quantile for a whole number of degrees of freedom, by bisection on the
    exact cumulative distribution (Abramowitz and Stegun 26.7.3 and 26.7.4)."""
    def cdf(t: float) -> float:
        theta = math.atan(abs(t) / math.sqrt(df))
        c, s = math.cos(theta), math.sin(theta)
        term, total = (c, c if df > 1 else 0.0) if df % 2 else (1.0, 1.0)
        for j in range(3 if df % 2 else 2, df, 2):
            term *= (j - 1) / j * c * c
            total += term
        within = 2 / math.pi * (theta + s * total) if df % 2 else s * total
        return 0.5 + math.copysign(within / 2, t)

    if df < 1 or not 0.0 < p < 1.0:
        raise PairedError(f"no t quantile at p={p} with {df} degrees of freedom")
    lo, hi = -1e6, 1e6
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cdf(mid) < p else (lo, mid)
    return (lo + hi) / 2


def wilson(kept: int, total: int, alpha: float) -> tuple[float, float]:
    """Wilson's interval for a proportion, every trial taken as independent."""
    z = NormalDist().inv_cdf(1 - alpha / 2)
    p = kept / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z / (1 + z * z / total) * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return max(0.0, centre - half), min(1.0, centre + half)


def over_units(values: Sequence[float], alpha: float) -> Optional[tuple[float, float]]:
    """A t interval for the mean of per-unit values, or None with fewer than two units."""
    if len(values) < 2:
        return None
    half = t_quantile(1 - alpha / 2, len(values) - 1) * stdev(values) / math.sqrt(len(values))
    return mean(values) - half, mean(values) + half


def rate(counts: Counts, alpha: float = 0.05) -> Optional[dict[str, Any]]:
    """The mean of the units' rates, with its interval, or None when no unit has a draw."""
    per = {u: c for u, c in counts.items() if c[1]}
    if not per:
        return None
    rates = [k / t for k, t in per.values()]
    kept, total = sum(k for k, _ in per.values()), sum(t for _, t in per.values())
    low, high = wilson(kept, total, alpha)
    spread = over_units(rates, alpha)
    if spread is not None:
        low, high = min(low, max(0.0, spread[0])), max(high, min(1.0, spread[1]))
    return {"rate": mean(rates), "low": low, "high": high, "units": len(per),
            "kept": kept, "of": total}


def difference(a: Counts, b: Counts, alpha: float = 0.05) -> Optional[dict[str, Any]]:
    """The rate under `a` minus the rate under `b`, paired within each unit that has both."""
    both = sorted(u for u in set(a) & set(b) if a[u][1] and b[u][1])
    if not both:
        return None
    diffs = [a[u][0] / a[u][1] - b[u][0] / b[u][1] for u in both]
    ka, ta = sum(a[u][0] for u in both), sum(a[u][1] for u in both)
    kb, tb = sum(b[u][0] for u in both), sum(b[u][1] for u in both)
    (la, ua), (lb, ub) = wilson(ka, ta, alpha), wilson(kb, tb, alpha)
    pa, pb = ka / ta, kb / tb
    low = pa - pb - math.sqrt((pa - la) ** 2 + (ub - pb) ** 2)
    high = pa - pb + math.sqrt((ua - pa) ** 2 + (pb - lb) ** 2)
    spread = over_units(diffs, alpha)
    if spread is not None:
        low, high = min(low, spread[0]), max(high, spread[1])
    return {"difference": mean(diffs), "low": max(-1.0, low), "high": min(1.0, high),
            "units": len(both)}
