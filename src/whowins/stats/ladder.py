"""The two-stage composition test, read off data/splits/set.json rather than restated.
Stage one fits the 10 pairs and predicts all 10 triples plus the five-way; stage
two adds a 4-triple slice. Stage one is at risk because pairwise data cannot pin a
correlated model; `families` runs it again with the correlated and context families.
"""

from __future__ import annotations

import collections
import json
import math
import os
from fractions import Fraction
from typing import Any, Iterable, Mapping, Optional, Sequence

from .choice import Choice, Dataset, Option
from . import models, regularity, score
from .rankings import WORLDS, RankingWorld

TIE = 1e-9      # closer than this is a tie, not a winner

SPLIT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "data", "splits", "set.json")

# The models the ladder runs; `saturated` is here to decline rather than to win.
LADDER_MODELS = ("uniform", "position", "luce", "luce_position",
                 "luce_position_size", "saturated")

# Every family, fitted alike on decided draws: the comparison H3 is judged on.
FAMILY_MODELS = ("uniform", "position", "luce", "luce_position", "thurstone",
                 "thurstone_position", "context", "context_position", "probit",
                 "probit_position", "mixed", "mixed_position", "saturated")


class LadderError(ValueError):
    """The ladder cannot be run as the split describes it."""


def load_ladder(path: Optional[str] = None) -> dict[str, Any]:
    """The frozen composition split, as data rather than as a restatement."""
    where = path or SPLIT
    if not os.path.exists(where):
        raise LadderError(f"{where}: the composition split is not here")
    with open(where, encoding="utf-8") as fh:
        split = json.load(fh)
    if split.get("split_id") != "set":
        raise LadderError(f"{where}: split_id is {split.get('split_id')!r}, not 'set'")
    if not split.get("stages"):
        raise LadderError(f"{where}: no stages in it")
    return split


def stage_compositions(stage: Mapping[str, Any]) -> tuple[list, list]:
    train = [tuple(sorted(c)) for c in stage["train"]]
    test = [tuple(sorted(c))
            for _, sets in sorted(stage["test_by_size"].items())
            for c in sets]
    return train, test


def fit_models(train: Dataset, model_names: Sequence[str]) -> tuple[dict, dict]:
    """Every model that fits, and why each of the others refused."""
    fits: dict[str, Any] = {}
    refused: dict[str, str] = {}
    for name in model_names:
        try:
            fits[name] = models.fit(train, name)
        except models.FitError as exc:
            # A refusal is a result: `luce_position_size` refuses stage one for the reason the whole project exists.
            refused[name] = str(exc)
    return fits, refused


def run_stage(data: Dataset, stage: Mapping[str, Any], *,
              model_names: Sequence[str] = LADDER_MODELS,
              bootstrap_draws: int = 400,
              seed: int = 20260915,
              fitted: Optional[tuple[dict, dict]] = None) -> dict[str, Any]:
    """Fit on this stage's training compositions, score on the ones it predicts.
    `fitted` is `fit_models` already run on this stage's training data."""
    train_comps, test_comps = stage_compositions(stage)
    train = data.with_compositions(train_comps)
    test = data.with_compositions(test_comps)
    if not len(train):
        raise LadderError(f"stage {stage.get('stage')}: no training data")
    if not len(test):
        raise LadderError(f"stage {stage.get('stage')}: no held-out data")

    fits, refused = fitted if fitted is not None else fit_models(train, model_names)
    comparison = score.compare(fits, test, allow_unequal_coverage=True)
    against = "luce" if "luce" in fits else next(iter(fits), None)
    intervals = {}
    if against:
        for name, fitted in fits.items():
            if name == against:
                continue
            try:
                intervals[name] = score.bootstrap(
                    fitted, fits[against], test, draws=bootstrap_draws, seed=seed)
            except score.ScoreError as exc:
                intervals[name] = {"error": str(exc)}
    return {
        "stage": stage.get("stage"),
        "carries": stage.get("carries"),
        "headroom": headroom(fits, test),
        "train": ["-".join(c) for c in train_comps],
        "test": ["-".join(c) for c in test_comps],
        "train_draws": train.n_draws, "test_draws": test.n_draws,
        "fitted": {k: v.as_dict() for k, v in fits.items()},
        "refused": refused,
        "scores": comparison,
        "against": against,
        "intervals": intervals,
    }


def two_stage(data: Dataset, *, split: Optional[Mapping[str, Any]] = None,
              model_names: Sequence[str] = LADDER_MODELS,
              bootstrap_draws: int = 400,
              seed: int = 20260915) -> dict[str, Any]:
    """Both stages, plus the comparison the split says is the like-for-like one."""
    split = split or load_ladder()
    stages, fitted = [], []
    for s in split["stages"]:
        train, _ = stage_compositions(s)
        fitted.append(fit_models(data.with_compositions(train), model_names))
        stages.append(run_stage(data, s, model_names=model_names,
                                bootstrap_draws=bootstrap_draws, seed=seed,
                                fitted=fitted[-1]))
    comparable = [tuple(sorted(c))
                  for c in (split.get("comparable_triples") or {}).get("sets", [])]
    both: dict[str, Any] = {}
    if comparable:
        # Stage one predicts ten triples and stage two six, so these six are what both predict out of sample.
        subset = data.with_compositions(comparable)
        for stage, (fits, _) in zip(split["stages"], fitted):
            both[str(stage.get("stage"))] = score.compare(
                fits, subset, allow_unequal_coverage=True)
    return {
        "split_id": split.get("split_id"),
        "question": split.get("question"),
        "stages": stages,
        "comparable_triples": ["-".join(c) for c in comparable],
        "on_the_comparable_triples": both,
    }


def families(data: Dataset, *, split: Optional[Mapping[str, Any]] = None,
             model_names: Sequence[str] = FAMILY_MODELS, bootstrap_draws: int = 400,
             seed: int = 20260915) -> dict[str, Any]:
    """The composition test again, every family on the same DECIDED draws, plus regularity.
    Abstaining is left to its own process, which a shared abstention model would add equally
    to every family, so it cancels from each difference. Log scores are per decided draw and
    are not comparable with `two_stage`'s, which count abstaining as an outcome."""
    decided = data.filter(lambda c: c.won is not None)
    out = two_stage(decided, split=split, model_names=model_names,
                    bootstrap_draws=bootstrap_draws, seed=seed)
    out["decided_draws"] = decided.n_draws
    out["left_out"] = data.n_draws - decided.n_draws
    try:
        reference = models.fit(decided, "luce_position")
    except models.FitError:
        reference = None
    out["regularity"] = regularity.check(decided, reference=reference, seed=seed)
    return out


# --- The counterexample, end to end ---


def _exact_pair_dataset(world: RankingWorld, denominator: int = 10) -> Dataset:
    """The world's pairwise probabilities as data, with no sampling at all.
    Weights are exact integers proportional to the true probabilities, so the fit below
    is the POPULATION fit -- sampling noise would let a reader think the two worlds
    differ by luck, when the point is that they do not differ at all."""
    rows = []
    for (a, b), p in sorted(world.pairwise().items()):
        weight_a = Fraction(p) * denominator
        weight_b = Fraction(1 - p) * denominator
        if weight_a.denominator != 1 or weight_b.denominator != 1:
            raise LadderError(
                f"{a}>{b} is {p}, which is not a whole number of parts in "
                f"{denominator}; raise the denominator so the data stays exact")
        options = (Option(f"pair:{a}", a, position=0), Option(f"pair:{b}", b, position=1))
        if weight_a:
            rows.append(Choice(item=f"{a}{b}", options=options, won=f"pair:{a}",
                               weight=int(weight_a)))
        if weight_b:
            rows.append(Choice(item=f"{a}{b}", options=options, won=f"pair:{b}",
                               weight=int(weight_b)))
    return Dataset(rows)


def _winner(distribution: Mapping[str, float]) -> str:
    """Which option this distribution picks, or a tie.
    A tie is reported as one: the pair-only fit puts A and B on exactly 7/17, differing
    only in the last bit of a float. A fit that cannot separate them has named no
    winner, which is a stronger statement than naming the wrong one."""
    ranked = sorted(distribution, key=lambda k: (-distribution[k], k))
    top = ranked[0]
    tied = [k for k in ranked if abs(distribution[k] - distribution[top]) <= TIE]
    return top if len(tied) == 1 else "tie(" + ",".join(sorted(tied)) + ")"


def insufficiency() -> dict[str, Any]:
    """Fit pairs in two worlds that agree on every pair, predict the triple, price it.
    Both have pairwise rates 1/2, 7/10, 7/10, so the fits and predictions are identical
    while the truths differ -- wrong in at least one, and more pairwise data changes
    nothing. This is not a sample-size problem and no budget fixes it."""
    out: dict[str, Any] = {"worlds": {}, "identical_pairwise": True}
    fits, predictions = {}, {}
    triple = ("A", "B", "C")
    options = tuple(Option(f"t:{s}", s, position=i) for i, s in enumerate(triple))
    probe = Choice(item="triple", options=options, won=None)

    baseline: Optional[dict] = None
    for name, world in sorted(WORLDS.items()):
        data = _exact_pair_dataset(world)
        fitted = models.fit(data, "luce")
        fits[name] = fitted
        predicted = fitted.predict(probe) or {}
        by_source = {o.source: o.option_id for o in options}
        predictions[name] = {s: predicted[by_source[s]] for s in triple}
        truth = {s: float(p) for s, p in world.choice_probs(list(triple)).items()}
        best = sum(p * math.log(p) for p in truth.values() if p > 0)
        got = sum(truth[s] * math.log(max(predictions[name][s], 1e-12)) for s in triple)
        pairwise = {f"{a}>{b}": str(p) for (a, b), p in sorted(world.pairwise().items())}
        if baseline is None:
            baseline = pairwise
        elif pairwise != baseline:
            out["identical_pairwise"] = False
        out["worlds"][name] = {
            "pairwise": pairwise,
            "strengths": fitted.strengths(),
            "true_triple": truth,
            "predicted_triple": predictions[name],
            "true_winner": _winner(truth),
            "predicted_winner": _winner(predictions[name]),
            "best_possible_log_score": best,
            "log_score_of_the_pair_only_fit": got,
            "cost_in_nats_per_draw": best - got,
        }

    names = sorted(out["worlds"])
    first, second = out["worlds"][names[0]], out["worlds"][names[1]]
    out["predictions_identical"] = all(
        abs(predictions[names[0]][s] - predictions[names[1]][s]) < 1e-12
        for s in triple)
    out["true_winners_differ"] = first["true_winner"] != second["true_winner"]
    out["true_triples_differ"] = any(
        abs(first["true_triple"][s] - second["true_triple"][s]) > TIE for s in triple)
    # A PROOF, NOT A MEASUREMENT: one prediction cannot equal two different truths, so no tolerance decides the central claim.
    out["wrong_in_at_least_one_world"] = bool(
        out["predictions_identical"] and out["true_triples_differ"])
    out["named_no_winner"] = [
        n for n, w in out["worlds"].items() if w["predicted_winner"].startswith("tie(")]
    out["worst_cost_in_nats_per_draw"] = max(
        w["cost_in_nats_per_draw"] for w in out["worlds"].values())
    out["detected"] = bool(out["identical_pairwise"]
                           and out["predictions_identical"]
                           and out["true_winners_differ"]
                           and out["wrong_in_at_least_one_world"])
    out["reading"] = (
        "Identical pairwise rates, identical fits, identical predictions -- and a "
        "different true winner. A pair-only fit is wrong in at least one of these "
        "worlds and no amount of pairwise data tells it which."
        if out["detected"] else
        "The counterexample did not reproduce, which means this package no longer "
        "demonstrates the result the project is built on. Do not ship it.")
    return out


# --- How wrong is stage one, exactly ---


def expected_log_score(truth, fitted, compositions: Iterable[Sequence[str]],
                       *, arrangement_positions: bool = True) -> float:
    """The log score this fit would get on infinite data from this truth.
    No sampling: in a simulation the truth is known, so the ceiling is a sum. Using a
    model fitted to the test set as the ceiling instead flatters it by however much it
    overfits. The gap to this is exactly the KL divergence."""
    import itertools as _it
    total, weight = 0.0, 0
    for comp in compositions:
        comp = sorted(comp)
        orders = (list(_it.permutations(comp)) if arrangement_positions
                  else [tuple(comp)])
        for order in orders:
            options = tuple(Option(f"x:{s}", s, position=i)
                            for i, s in enumerate(order))
            options = tuple(sorted(options, key=lambda o: o.source))
            truths = truth.probabilities(options)
            probe = Choice(item="probe", options=options, won=None)
            predicted = fitted.predict(probe)
            if predicted is None:
                continue
            for key, p in truths.items():
                if p <= 0:
                    continue
                total += p * math.log(max(predicted.get(key, 0.0), 1e-12))
            weight += 1
    return total / weight if weight else float("nan")


def empirical_ceiling(data: Dataset) -> dict[str, Any]:
    """The best in-sample log score for a model that sees composition AND order.
    A SATURATED MODEL IS NOT THIS. It is saturated over compositions and blind to
    arrangement, so `position` beats it -- on the ladder run, -1.19 against -1.30.
    Fitted on the very data it scores, so nothing honest beats it.
    """
    cells: dict[tuple, collections.Counter] = collections.defaultdict(
        collections.Counter)
    for c in data:
        cells[_cell(c)][c.winning_source()] += c.weight
    total, top, n = 0.0, 0.0, 0
    for c in data:
        counts = cells[_cell(c)]
        p = counts[c.winning_source()] / sum(counts.values())
        total += c.weight * math.log(max(p, 1e-12))
        top += c.weight * score.top_one(counts, c.winning_source())
        n += c.weight
    return {"ceiling": total / n if n else None, "top1": top / n if n else None,
            "cells": len(cells), "draws": n}


def _cell(choice: Choice) -> tuple[str, ...]:
    """A composition and the order its sources arrived in."""
    return tuple(o.source for o in sorted(
        choice.options, key=lambda o: (o.position is None, o.position, o.source)))


def headroom(fits: Mapping[str, Any], data: Dataset) -> dict[str, Any]:
    """How far each fitted model is from what this data allows, in nats, and as the share of
    the gap between the fitted `uniform` model (0) and the empirical ceiling (1) it recovers.
    `uniform` and not log(1/options): the outcome space also holds a reply where nothing won."""
    top = empirical_ceiling(data)
    uniform = score.log_score(fits["uniform"], data) if "uniform" in fits else None
    out = {"ceiling": top["ceiling"], "cells": top["cells"], "uniform": uniform,
           "top1_ceiling": top["top1"], "short_by": {}, "share_recovered": {}}
    gap = None if top["ceiling"] is None or uniform is None else top["ceiling"] - uniform
    for name, fitted in fits.items():
        got = score.log_score(fitted, data)
        out["short_by"][name] = None if got is None or top["ceiling"] is None \
            else top["ceiling"] - got
        out["share_recovered"][name] = None if got is None or not gap \
            else (got - uniform) / gap
    return out


def ceiling(truth, compositions: Iterable[Sequence[str]]) -> float:
    """The best log score anything could get: the truth scoring itself."""
    import itertools as _it
    total, weight = 0.0, 0
    for comp in compositions:
        comp = sorted(comp)
        for order in _it.permutations(comp):
            options = tuple(sorted(
                (Option(f"x:{s}", s, position=i) for i, s in enumerate(order)),
                key=lambda o: o.source))
            for p in truth.probabilities(options).values():
                if p > 0:
                    total += p * math.log(p)
            weight += 1
    return total / weight if weight else float("nan")


def misspecification(truth, train: Iterable[Sequence[str]],
                     test: Iterable[Sequence[str]], *, model: str = "luce",
                     items: int = 400, repeats: int = 3,
                     seed: int = 20260915) -> dict[str, Any]:
    """Fit on `train`, and price the error on `test` against the exact ceiling.
    A property of the WORLD and the MODEL, not of the sample: enough training data is
    drawn that the fit has converged, so "0.03 nats" means permanently that wrong."""
    from .simulate import simulate

    data = simulate(truth, list(train), items=items, repeats=repeats, seed=seed)
    fitted = models.fit(data, model)
    test = [sorted(c) for c in test]
    best = ceiling(truth, test)
    got = expected_log_score(truth, fitted, test)
    per_composition = {}
    for comp in test:
        per_composition["-".join(comp)] = (
            ceiling(truth, [comp]) - expected_log_score(truth, fitted, [comp]))
    return {
        "model": model,
        "trained_on": ["-".join(sorted(c)) for c in train],
        "tested_on": ["-".join(c) for c in test],
        "ceiling": best,
        "expected_log_score": got,
        "cost_in_nats_per_draw": best - got,
        "per_composition": per_composition,
        "training_draws": data.n_draws,
    }
