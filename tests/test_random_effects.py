"""Random effects: item tastes and family shifts in one run, model and harness shifts across runs.
Checked against planted worlds, and the joint mode against its own gradient, because the block
elimination that finds it is exactly the code a sign error would hide in."""

from __future__ import annotations

import itertools
import random

import pytest

from whowins.stats import mixed, models, pooled, score
from whowins.stats import simulate as sim
from whowins.stats.choice import Choice, Dataset, Option

SOURCES = ("S1", "S2", "S3", "S4", "S5")
MEANS = {"S1": 0.0, "S2": 0.4, "S3": 0.8, "S4": 1.2, "S5": 1.6}
FAMILIES = ("fmt", "tool", "path", "ord")


def world(items: int, sigma_item: float, sigma_family: float, *, later: float = 1.0,
          comps=None, seed: int = 1, shifts=None) -> Dataset:
    """`simulate_tastes` over pairs and triples, with a family shift of the given spread."""
    shift = shifts if shifts is not None else {
        (g, s): random.Random(f"{g}{s}").gauss(0, sigma_family) for g in FAMILIES for s in SOURCES}
    comps = comps or [c for n in (2, 3) for c in itertools.combinations(SOURCES, n)]
    return sim.simulate_tastes(MEANS, comps, items=items, sigma_item=sigma_item, shift=shift,
                               later=later, families=FAMILIES, seed=seed)


def test_item_tastes_are_found_and_carry_to_an_items_larger_sets():
    """Tastes learned from an item's pairs and triples predict its five-way set; Plackett-Luce,
    which pools every item into one, cannot."""
    train = world(120, 1.0, 0.0)
    fitted = models.fit(train, "mixed_position")
    plain = models.fit(train, "luce_position")
    assert fitted.sigmas["item"] > 0.6, fitted.sigmas
    held = world(120, 1.0, 0.0, comps=[SOURCES], seed=9)
    gain = score.bootstrap(fitted, plain, held, draws=200)
    assert gain["lo"] > 0, gain


def test_and_they_undo_the_attenuation_a_pooled_fit_suffers():
    """Averaging sigmoid(d + b) and sigmoid(d - b) is not sigmoid(d). A fit that
    ignores item tastes shrinks every effect toward zero, and the mixed fit restores it."""
    train = world(200, 1.2, 0.0)
    got = models.fit(train, "mixed_position").coefficients
    flat = models.fit(train, "luce_position").coefficients
    assert abs(got["strength[S5]"]) > abs(flat["strength[S5]"])
    assert abs(got["later"] - 1.0) < abs(flat["later"] - 1.0)


def test_a_world_with_no_tastes_gets_a_small_item_variance():
    fitted = models.fit(world(100, 0.0, 0.0), "mixed_position")
    assert fitted.sigmas["item"] < 0.35, fitted.sigmas


def test_family_shifts_are_recovered_in_their_direction():
    shifts = {(g, s): (0.8 if (g, s) in {("fmt", "S1"), ("tool", "S5")} else 0.0)
              for g in FAMILIES for s in SOURCES}
    fitted = models.fit(world(160, 0.3, 0.0, shifts=shifts), "mixed_position")
    got = fitted.shifts()["family"]
    assert got["fmt"]["S1"] > got["path"]["S1"] and got["tool"]["S5"] > got["ord"]["S5"]


def test_the_joint_mode_is_where_the_gradient_is_zero():
    """Recomputed from scratch at the fitted point, every gradient entry is zero."""
    data = world(40, 0.8, 0.3)
    lay = mixed._layout(data, True, (("family", mixed.family_of),), True)
    fitted = models.fit(data, "mixed_position")
    prec_g = [0.0] * lay.n_fixed + [1.0 / fitted.sigmas["family"] ** 2] * (
        len(lay.names) - lay.n_fixed)
    a = [[fitted._tastes[item][o][0] for o in opts]
         for item, opts in zip(lay.block_items, lay.block_options)]
    state = mixed._pass(lay, list(fitted._beta), a, 1.0 / fitted.sigmas["item"] ** 2, prec_g)
    assert max(abs(g) for g in state["gg"]) < 1e-5
    assert max(abs(g) for gb, _, _ in state["blocks"] for g in gb) < 1e-5


def test_a_mixed_model_refuses_abstentions():
    data = Dataset([Choice("fmt-0001", (Option("o1", "S1", 0), Option("o2", "S2", 1)), None)])
    with pytest.raises(models.FitError, match="decided draws only"):
        models.fit(data, "mixed")


# --- Across runs ---


def test_a_harness_is_separable_only_when_some_model_crosses_harnesses():
    models_of = {"a": "m1", "b": "m2"}
    assert "one harness" in pooled.harness_separable(models_of, {"a": "h1", "b": "h1"})
    assert "no model was served" in pooled.harness_separable(models_of, {"a": "h1", "b": "h2"})
    assert pooled.harness_separable({"a": "m1", "b": "m1", "c": "m2"},
                                    {"a": "h1", "b": "h2", "c": "h1"}) is None


def test_pooling_finds_a_planted_model_spread_and_says_why_it_left_harness_out():
    runs, models_of, harness = {}, {}, {}
    rng = random.Random(4)
    for r in range(6):
        shift = {(g, s): 0.0 for g in FAMILIES for s in SOURCES}
        spread = {s: rng.gauss(0, 0.8) for s in SOURCES}
        for g in FAMILIES:
            for s in SOURCES:
                shift[(g, s)] = spread[s]
        pairs = [c for c in itertools.combinations(SOURCES, 2)]
        runs[f"run{r}"] = world(80, 0.0, 0.0, comps=pairs, seed=r, shifts=shift)
        models_of[f"run{r}"] = f"model{r}"
        harness[f"run{r}"] = "v100" if r < 3 else "sm80"
    fitted, info = pooled.pool(runs, models_of, harness)
    assert fitted.sigmas["model"] > 0.3, fitted.sigmas
    assert info["harness_effect"].startswith("not fitted: no model was served")
    assert set(fitted.shifts()["model"]) == {f"model{r}" for r in range(6)}
