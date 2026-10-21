"""How much data is enough, answered by simulation rather than by a formula.
Plant a truth, draw a run of a given size, ask the study's question, repeat; power
is the fraction answering yes. EVERY CURVE IS CONDITIONAL ON THE PLANTED EFFECT,
which `ladder.misspecification` prices. Items are the unit a run buys.
"""

from __future__ import annotations

import itertools
from typing import Any, Callable, Mapping, Optional, Sequence

from . import models, score
from .choice import Dataset
from .simulate import simulate

# A question returns None when it could not be asked at all, counted apart from a no: "unanswerable" and "answered no" are different facts.
Question = Callable[[Dataset], Optional[bool]]


class PowerError(ValueError):
    """A power curve that would not mean anything."""


def recovers(truth, *, tolerance: float = 0.02, model: str = "luce") -> Question:
    """Did the fit land within `tolerance` of every planted strength?
    On the normalised scale, the only one a Plackett-Luce strength is defined on."""
    planted = {k: v / sum(truth.strengths.values())
               for k, v in truth.strengths.items()}

    def ask(data: Dataset) -> Optional[bool]:
        try:
            fitted = models.fit(data, model)
        except models.FitError:
            return None
        got = fitted.strengths()
        return max(abs(got[s] - planted[s]) for s in planted) <= tolerance

    return ask


def beats(a: str, b: str, *, train: Sequence[Sequence[str]],
          test: Sequence[Sequence[str]], bootstrap_draws: int = 200,
          seed: int = 20260915) -> Question:
    """Did model `a` beat `b` out of sample, with the interval clear of zero?
    Both halves matter: the right direction with an interval straddling zero is not a
    detection, and the wrong direction clear of zero detects something else."""
    train_keys = [sorted(c) for c in train]
    test_keys = [sorted(c) for c in test]

    def ask(data: Dataset) -> Optional[bool]:
        fitting = data.with_compositions(train_keys)
        held_out = data.with_compositions(test_keys)
        if not len(fitting) or not len(held_out):
            return None
        try:
            fa = (models.fit_saturated(fitting) if a == "saturated"
                  else models.fit(fitting, a))
            fb = (models.fit_saturated(fitting) if b == "saturated"
                  else models.fit(fitting, b))
        except models.FitError:
            return None
        try:
            interval = score.bootstrap(fa, fb, held_out, draws=bootstrap_draws,
                                       seed=seed)
        except score.ScoreError:
            return None
        return bool(interval["difference"] > 0 and interval["lo"] > 0)

    return ask


def beats_on_held_out_items(a: str, b: str, *, holdout: float = 0.5,
                            bootstrap_draws: int = 200,
                            seed: int = 20260915) -> Question:
    """Did `a` beat `b` on items neither was fitted on, at the same compositions?
    Review #9's other arm: holding out compositions tests extrapolation, holding out
    items tests the link. a="saturated", b="luce" detects misspecification -- the
    saturated model can only win if the structure Luce imposes is wrong."""
    def ask(data: Dataset) -> Optional[bool]:
        import random as _random

        items = sorted(data.items)
        if len(items) < 4:
            return None
        # Shuffled, because a sorted cut of real scenario ids splits by family -- they carry the family as a prefix.
        _random.Random(seed).shuffle(items)
        cut = max(2, int(len(items) * (1 - holdout)))
        fit_items, test_items = set(items[:cut]), set(items[cut:])
        if not test_items:
            return None
        fitting = data.filter(lambda c: c.item in fit_items)
        held_out = data.filter(lambda c: c.item in test_items)
        try:
            fa = (models.fit_saturated(fitting) if a == "saturated"
                  else models.fit(fitting, a))
            fb = (models.fit_saturated(fitting) if b == "saturated"
                  else models.fit(fitting, b))
        except models.FitError:
            return None
        try:
            interval = score.bootstrap(fa, fb, held_out, draws=bootstrap_draws,
                                       seed=seed)
        except score.ScoreError:
            return None
        return bool(interval["difference"] > 0 and interval["lo"] > 0)

    return ask


def power_at(truth, question: Question, compositions: Sequence[Sequence[str]], *,
             items: int, replicates: int = 40, repeats: int = 3,
             arrangement: str = "balanced", seed: int = 20260915) -> dict[str, Any]:
    """Run the same study `replicates` times at one size and count the yeses."""
    yes = no = unanswerable = 0
    for r in range(replicates):
        data = simulate(truth, compositions, items=items, repeats=repeats,
                        arrangement=arrangement, seed=seed + 1000 * r)
        verdict = question(data)
        if verdict is None:
            unanswerable += 1
        elif verdict:
            yes += 1
        else:
            no += 1
    answered = yes + no
    return {
        "items": items, "replicates": replicates,
        "draws_per_replicate": items * len(list(compositions)) * repeats,
        "yes": yes, "no": no, "unanswerable": unanswerable,
        "power": (yes / answered) if answered else None,
    }


def curve(truth, question: Question, compositions: Sequence[Sequence[str]], *,
          item_counts: Sequence[int] = (25, 50, 100, 200, 400),
          replicates: int = 40, repeats: int = 3, arrangement: str = "balanced",
          seed: int = 20260915) -> dict[str, Any]:
    """Power at each size, and the smallest size that clears the usual bar."""
    comps = [sorted(c) for c in compositions]
    if not comps:
        raise PowerError("no composition to simulate")
    points = [power_at(truth, question, comps, items=n, replicates=replicates,
                       repeats=repeats, arrangement=arrangement, seed=seed)
              for n in sorted(item_counts)]
    return {
        "compositions": ["-".join(c) for c in comps],
        "repeats": repeats, "arrangement": arrangement,
        "replicates": replicates,
        "points": points,
        "enough_for_80": _first_at(points, 0.80),
        "enough_for_90": _first_at(points, 0.90),
        "note": ("power is against the planted effect and nothing else; a "
                 "different truth gives a different curve"),
    }


def _first_at(points: Sequence[Mapping[str, Any]], target: float) -> Optional[int]:
    """The smallest size clearing `target` that every larger size also clears.
    A curve from finitely many replicates can clear the bar once by luck; requiring
    the rest costs nothing when the rise is real."""
    for i, point in enumerate(points):
        if point["power"] is None or point["power"] < target:
            continue
        if all(p["power"] is not None and p["power"] >= target
               for p in points[i:]):
            return int(point["items"])
    return None


def pairs(sources: Sequence[str]) -> list[list[str]]:
    return [list(c) for c in itertools.combinations(sorted(sources), 2)]


def triples(sources: Sequence[str]) -> list[list[str]]:
    return [list(c) for c in itertools.combinations(sorted(sources), 3)]
