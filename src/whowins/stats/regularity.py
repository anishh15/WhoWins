"""Regularity: adding a competitor must not raise an option's chance of winning.
Every random-utility model obeys it -- Plackett-Luce, Thurstone and the correlated probit
alike -- so a real violation is a context effect none of them can fit. Read off decided
draws, with item-clustered errors, simultaneous over every test by Bonferroni.
"""

from __future__ import annotations

import collections
import random
from statistics import NormalDist, stdev
from typing import Any, Optional

from .choice import Dataset

TOP = 5     # how many of the largest rises to show when none is a violation


def check(data: Dataset, *, alpha: float = 0.05, draws: int = 400,
          seed: int = 20260915, reference: Any = None) -> dict[str, Any]:
    """Every (option, smaller set, larger set) the data hold, and whether the larger set
    raised the option's share beyond what chance allows. `reference` is a fitted model whose
    predicted rise on the same draws shows what position alone would do: arrangements differ
    between a pair and a triple, and a rank-based position effect is itself contextual."""
    decided = data.filter(lambda c: c.won is not None)
    comps = decided.compositions
    tests = [(big, small, a) for big in comps if len(big) >= 3
             for small in comps if len(small) >= 2 and set(small) < set(big)
             for a in small]
    out: dict[str, Any] = {"alpha": alpha, "tests": len(tests), "items": len(decided.items),
                           "violations": [], "largest": []}
    if not tests:
        out["note"] = "no set above a pair holds a smaller set of its sources"
        return out

    # Per item: draws and wins for every composition it was asked, so a resample is a sum.
    by_item: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for c in decided:
        by_item[c.item][(c.sources, None)] += c.weight
        by_item[c.item][(c.sources, c.winning_source())] += c.weight
    items = sorted(by_item)

    def rises(picked) -> list[float]:
        total: collections.Counter = collections.Counter()
        for item in picked:
            total.update(by_item[item])
        return [total[(big, a)] / total[(big, None)] - total[(small, a)] / total[(small, None)]
                if total[(big, None)] and total[(small, None)] else 0.0
                for big, small, a in tests]

    observed = rises(items)
    rng = random.Random(seed)
    resampled = [rises([items[rng.randrange(len(items))] for _ in items]) for _ in range(draws)]
    z = NormalDist().inv_cdf(1.0 - alpha / len(tests))
    counts = collections.Counter()
    for item in items:
        counts.update(by_item[item])

    rows = []
    for k, (big, small, a) in enumerate(tests):
        se = stdev(r[k] for r in resampled)
        row = {"option": a, "from": "-".join(small), "to": "-".join(big),
               "share_before": counts[(small, a)] / counts[(small, None)],
               "share_after": counts[(big, a)] / counts[(big, None)],
               "rise": observed[k], "se": se, "lower": observed[k] - z * se,
               "draws_before": counts[(small, None)], "draws_after": counts[(big, None)]}
        if reference is not None:
            after = _predicted_share(reference, decided, big, a)
            before = _predicted_share(reference, decided, small, a)
            row["reference_rise"] = None if after is None or before is None else after - before
        rows.append(row)
    out["z"] = z
    out["violations"] = [r for r in rows if r["lower"] > 0]
    out["largest"] = sorted(rows, key=lambda r: -(r["rise"] / r["se"] if r["se"] else 0.0))[:TOP]
    out["note"] = (f"{len(tests)} tests, each one-sided at {alpha}/{len(tests)}; a violation's "
                   f"lower bound is above zero with every test held at once")
    return out


def _predicted_share(fitted, data: Dataset, comp: tuple[str, ...], source: str) -> Optional[float]:
    """The reference model's average chance for `source` over the draws of `comp`."""
    total, n = 0.0, 0
    for c in data.with_compositions([comp]):
        predicted = fitted.predict(c)
        if predicted is None:
            return None
        option = next(o.option_id for o in c.options if o.source == source)
        total += c.weight * predicted.get(option, 0.0)
        n += c.weight
    return total / n if n else None
