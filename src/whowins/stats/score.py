"""How well a fitted model predicted data it was not fitted on.
Held-out log score is primary (R-squared over aggregates is unstable); Brier,
calibration and MAE sit alongside. Coverage is part of the score, a zero is
counted rather than averaged away, and uncertainty is clustered on the item.
"""

from __future__ import annotations

import collections
import math
import random
from typing import Any, Mapping, Optional

from .choice import Choice, Dataset, predict_actions

FLOOR = 1e-12       # a probability of zero, as a number the arithmetic can hold


class ScoreError(ValueError):
    """These models cannot be compared on this data."""


def _probability_of_what_happened(fitted, choice: Choice) -> Optional[float]:
    predicted = fitted.predict(choice)
    if predicted is None:
        return None
    return predicted.get(choice.won, 0.0)


def top_one(predicted: Mapping[str, float], won: Optional[str]) -> float:
    """1 when the option the prediction rates highest is the one that won; a tie at the top
    shares the credit, so a flat prediction over k options scores 1/k."""
    best = max(predicted.values(), default=0.0)
    top = [o for o, q in predicted.items() if q == best]
    return (1.0 / len(top)) if won in top else 0.0


def evaluate(fitted, dataset: Dataset, *, floor: float = FLOOR) -> dict[str, Any]:
    """Every scoring rule at once, for one fitted model on one held-out set.
    `top1` is the share of draws whose winner the prediction rated highest: the log score in
    a form a reader can take in, never instead of it."""
    total_log, total_brier, total_mae, total_top = 0.0, 0.0, 0.0, 0.0
    scored, missed, surprises = 0, 0, 0
    # Reliability is over EVERY (choice, outcome) pair: the realised outcome occurred every time by construction, so binning it measures nothing.
    bins: dict[int, list[float]] = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
    for choice in dataset:
        predicted = fitted.predict(choice)
        if predicted is None:
            missed += choice.weight
            continue
        p = predicted.get(choice.won, 0.0)
        if p <= 0.0:
            surprises += choice.weight
        scored += choice.weight
        total_log += choice.weight * math.log(max(p, floor))
        total_mae += choice.weight * (1.0 - p)
        total_top += choice.weight * top_one(predicted, choice.won)
        for outcome, q in predicted.items():
            happened = 1.0 if outcome == choice.won else 0.0
            # Brier over the whole predicted simplex, so a model that spreads the rest of its mass badly pays for it.
            total_brier += choice.weight * (q - happened) ** 2
            cell = bins[min(9, int(q * 10))]
            cell[0] += choice.weight * q
            cell[1] += choice.weight * happened
            cell[2] += choice.weight

    calibration = []
    for index in sorted(bins):
        predicted_mean, hits, n = bins[index]
        calibration.append({
            "bin": f"{index / 10:.1f}-{(index + 1) / 10:.1f}",
            "predicted": predicted_mean / n, "observed": hits / n, "n": int(n)})
    return {
        "model": fitted.name,
        "n_scored": scored, "n_declined": missed,
        "coverage": scored / (scored + missed) if (scored + missed) else 0.0,
        "log_score": total_log / scored if scored else None,
        "brier": total_brier / scored if scored else None,
        "mae": total_mae / scored if scored else None,
        "top1": total_top / scored if scored else None,
        "surprises": surprises,
        "calibration": calibration,
        "calibration_error": (
            sum(abs(c["predicted"] - c["observed"]) * c["n"] for c in calibration)
            / sum(c["n"] for c in calibration)) if calibration else None,
    }


def evaluate_free(fitted, dataset: Dataset, *, floor: float = FLOOR) -> dict[str, Any]:
    """How well a fit predicted free predictions, and which way it was wrong.
    `shared`: among draws where an option won, the predicted and observed wins of the option more
    sources demand. Above is consensus, below is discounting; a mispredicted rate of no winner
    would read as either, so it is left out. Groups of one size have no such option."""
    total_log, scored, missed = 0.0, 0, 0
    predicted_shared, observed_shared, n_shared = 0.0, 0.0, 0
    for choice in dataset:
        predicted = predict_actions(fitted, choice)
        if predicted is None:
            missed += choice.weight
            continue
        won = choice.tags["action_won"]
        scored += choice.weight
        total_log += choice.weight * math.log(max(predicted.get(won, 0.0), floor))
        counts = collections.Counter(choice.tags["actions"].values())
        ranked = counts.most_common()
        decided = 1.0 - predicted.get(None, 0.0)
        if won is not None and decided > 0 and len(ranked) > 1 and ranked[0][1] > ranked[1][1]:
            shared = ranked[0][0]
            predicted_shared += choice.weight * predicted.get(shared, 0.0) / decided
            observed_shared += choice.weight * (won == shared)
            n_shared += choice.weight
    return {
        "n_scored": scored, "n_declined": missed,
        "coverage": scored / (scored + missed) if scored + missed else 0.0,
        "log_score": total_log / scored if scored else None,
        "shared": {"n": n_shared,
                   "predicted": predicted_shared / n_shared if n_shared else None,
                   "observed": observed_shared / n_shared if n_shared else None},
    }


def log_score(fitted, dataset: Dataset, *, floor: float = FLOOR) -> Optional[float]:
    return evaluate(fitted, dataset, floor=floor)["log_score"]


def per_item_log_scores(fitted, dataset: Dataset, *, floor: float = FLOOR
                        ) -> dict[str, tuple[float, int]]:
    """Summed log score and draw count per item, for clustered resampling."""
    out: dict[str, list] = collections.defaultdict(lambda: [0.0, 0])
    for choice in dataset:
        p = _probability_of_what_happened(fitted, choice)
        if p is None:
            continue
        out[choice.item][0] += choice.weight * math.log(max(p, floor))
        out[choice.item][1] += choice.weight
    return {k: (v[0], v[1]) for k, v in out.items()}


def bootstrap(fitted_a, fitted_b, dataset: Dataset, *, draws: int = 1000,
              seed: int = 20260915, floor: float = FLOOR) -> dict[str, Any]:
    """An interval for (log score of A) - (log score of B), clustered on items.
    Resamples ITEMS, never draws: three draws of one scenario measure one thing, and
    treating them as independent looks ~1.7x more certain than it is."""
    a = per_item_log_scores(fitted_a, dataset, floor=floor)
    b = per_item_log_scores(fitted_b, dataset, floor=floor)
    shared = sorted(set(a) & set(b))
    if not shared:
        raise ScoreError("no item has a prediction from both models")
    rng = random.Random(seed)
    observed = (sum(a[i][0] for i in shared) / sum(a[i][1] for i in shared)
                - sum(b[i][0] for i in shared) / sum(b[i][1] for i in shared))
    differences = []
    for _ in range(draws):
        picked = [shared[rng.randrange(len(shared))] for _ in shared]
        na = sum(a[i][1] for i in picked)
        nb = sum(b[i][1] for i in picked)
        if not na or not nb:
            continue
        differences.append(sum(a[i][0] for i in picked) / na
                           - sum(b[i][0] for i in picked) / nb)
    differences.sort()
    if not differences:
        raise ScoreError("every resample was empty")
    lo = differences[int(0.025 * (len(differences) - 1))]
    hi = differences[int(0.975 * (len(differences) - 1))]
    return {
        "a": fitted_a.name, "b": fitted_b.name,
        "difference": observed, "lo": lo, "hi": hi,
        "items": len(shared), "resamples": len(differences),
        "excludes_zero": (lo > 0) or (hi < 0),
    }


def compare(fits: Mapping[str, Any], dataset: Dataset, *,
            allow_unequal_coverage: bool = False,
            floor: float = FLOOR) -> dict[str, Any]:
    """Every model on the same held-out data, ranked, or a refusal to rank.
    The refusal is the useful part: a model that declined half the test set can look
    excellent on the half it kept. `equal_coverage` says if the ranking means anything."""
    rows = {name: evaluate(f, dataset, floor=floor) for name, f in fits.items()}
    coverages = {name: round(r["coverage"], 12) for name, r in rows.items()}
    equal = len(set(coverages.values())) <= 1
    ranked: Optional[list[str]] = None
    if equal or allow_unequal_coverage:
        scored = [n for n, r in rows.items() if r["log_score"] is not None]
        ranked = sorted(scored, key=lambda n: rows[n]["log_score"], reverse=True)
    return {
        "n_test_draws": dataset.n_draws,
        "rows": rows,
        "coverage": coverages,
        "equal_coverage": equal,
        "ranked": ranked,
        "why_no_ranking": None if ranked is not None else (
            "the models predicted different amounts of this test set, so a "
            "ranking would be comparing different questions. Coverage: "
            + ", ".join(f"{n} {c:.3f}" for n, c in sorted(coverages.items()))),
    }
