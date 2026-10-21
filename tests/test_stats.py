"""Phase 1: the strengths fit, the nulls, and the simulation that gates them.
Almost everything is checked against an answer worked out by hand or by a second algorithm,
because that is the only kind of test a fitter can have -- a suite asserting "the optimiser
returned something" passes on a fitter that returns the wrong number."""

from __future__ import annotations

import math
import os
from fractions import Fraction

import pytest

from whowins.stats import ladder, models, power, rankings, score
from whowins.stats import simulate as sim
from whowins.stats.choice import (
    Choice,
    ChoiceError,
    Dataset,
    Option,
    collapse,
    free_from_records,
    from_records,
    kinds,
    predict_actions,
)

SOURCES = ("S1", "S2", "S3", "S4", "S5")
PLANTED = {"S1": 0.5, "S2": 1.0, "S3": 2.0, "S4": 4.0, "S5": 8.0}


def choice(sources, won=None, *, item="i", positions=None, weight=1):
    positions = positions or {s: i for i, s in enumerate(sources)}
    options = tuple(Option(f"{item}:{s}", s, position=positions.get(s))
                    for s in sources)
    return Choice(item=item, options=options,
                  won=f"{item}:{won}" if won else None, weight=weight)


# --- The counterexample -- the claim the whole project rests on ---


def test_the_counterexample_is_exact_and_the_winner_really_flips():
    """Two worlds, identical on every pair, different three-way winner.
    The published result the project was reframed around. Checked as FRACTIONS: identical to
    fifteen decimal places would leave a reader wondering whether the difference is real and
    small."""
    out = rankings.verify()
    assert out["exact"], "the worlds must be exact rationals, not floats"
    assert out["pairwise_identical"]
    assert out["pairwise"] == {"A>B": "1/2", "A>C": "7/10", "B>C": "7/10"}
    assert out["triple_winner"] == {"a_wins_the_triple": "A",
                                    "b_wins_the_triple": "B"}
    assert out["winner_differs"]
    assert rankings.counterexample_holds()

    a = rankings.WORLDS["a_wins_the_triple"]
    b = rankings.WORLDS["b_wins_the_triple"]
    assert a.pairwise() == b.pairwise()
    assert a.top_choice() != b.top_choice()
    assert a.top_choice()["A"] == Fraction(1, 2)
    assert b.top_choice()["B"] == Fraction(1, 2)


def test_a_pair_only_fit_cannot_tell_the_two_worlds_apart():
    """And is therefore wrong in at least one of them, by a priced amount.
    The shared pairwise rates are exactly Plackett-Luce representable with strengths (7, 7, 3),
    so the fit predicts (7/17, 7/17, 3/17) in BOTH worlds."""
    out = ladder.insufficiency()
    assert out["detected"]
    assert out["identical_pairwise"] and out["predictions_identical"]
    assert out["wrong_in_at_least_one_world"]

    for world in out["worlds"].values():
        assert world["predicted_triple"]["A"] == pytest.approx(7 / 17, abs=1e-9)
        assert world["predicted_triple"]["C"] == pytest.approx(3 / 17, abs=1e-9)
        # A and B tie exactly, so no winner is named -- stronger than naming the wrong one, and not decided by floating-point noise.
        assert world["predicted_winner"] == "tie(A,B)"
    assert out["worst_cost_in_nats_per_draw"] == pytest.approx(0.11184, abs=1e-4)


def test_a_luce_world_induces_the_strengths_it_was_built_from():
    """P(i wins from S) = w_i / sum over S, at every subset size.

    That property is exactly what makes Plackett-Luce extrapolate from pairs,
    and exactly what the counterexample worlds do not have."""
    world = rankings.luce_world({"A": 3.0, "B": 2.0, "C": 1.0})
    assert world.choice_probs(["A", "B"])["A"] == pytest.approx(3 / 5)
    assert world.choice_probs(["A", "C"])["A"] == pytest.approx(3 / 4)
    assert world.choice_probs(["B", "C"])["B"] == pytest.approx(2 / 3)
    triple = world.top_choice()
    assert triple["A"] == pytest.approx(1 / 2)
    assert triple["B"] == pytest.approx(1 / 3)
    assert triple["C"] == pytest.approx(1 / 6)


def test_a_world_that_is_not_a_distribution_is_refused():
    with pytest.raises(rankings.WorldError, match="sum to"):
        rankings.RankingWorld(("A", "B"), {("A", "B"): Fraction(1, 2)})
    with pytest.raises(rankings.WorldError, match="not a ranking"):
        rankings.RankingWorld(("A", "B", "C"), {("A", "B"): 1.0})
    with pytest.raises(rankings.WorldError, match="must be positive"):
        rankings.luce_world({"A": 1.0, "B": 0.0})


# --- A choice, and what it refuses to be ---


def test_a_choice_refuses_what_is_not_a_measurement():
    with pytest.raises(ChoiceError, match="at least two options"):
        Choice(item="i", options=(Option("a", "S1"),), won="a")
    with pytest.raises(ChoiceError, match="two options from source"):
        Choice(item="i", options=(Option("a", "S1"), Option("b", "S1")), won="a")
    with pytest.raises(ChoiceError, match="did not compete"):
        Choice(item="i", options=(Option("a", "S1"), Option("b", "S2")), won="c")
    # None is an outcome and must be allowed
    assert Choice(item="i", options=(Option("a", "S1"), Option("b", "S2")),
                  won=None).winning_source() is None


def test_a_disconnected_comparison_graph_is_not_a_hard_fit_but_an_unanswerable_one():
    """Two groups with no measurement linking them slide apart freely, so any
    difference between them is whatever the optimiser stopped at."""
    linked = Dataset([choice(("S1", "S2"), "S1"), choice(("S2", "S3"), "S2")])
    assert linked.connected()
    split = Dataset([choice(("S1", "S2"), "S1"), choice(("S3", "S4"), "S3")])
    assert not split.connected()
    with pytest.raises(models.FitError, match="not connected"):
        models.fit(split, "luce")


def test_weights_are_a_speed_change_and_nothing_else():
    """A collapsed dataset and an expanded one must fit identically."""
    expanded = Dataset([choice(("S1", "S2"), "S1", item=f"i{i % 3}")
                        for i in range(30)]
                       + [choice(("S1", "S2"), "S2", item=f"i{i % 3}")
                          for i in range(10)])
    squashed = collapse(expanded)
    assert len(squashed) < len(expanded)
    assert squashed.n_draws == expanded.n_draws == 40
    a = models.fit(expanded, "luce").strengths()
    b = models.fit(squashed, "luce").strengths()
    assert max(abs(a[s] - b[s]) for s in a) < 1e-10


def test_only_the_conflict_arm_becomes_a_choice():
    """A solo trial shows one option, and a one-option choice measures whether
    the model CAN do a thing rather than which instruction it preferred."""
    rows = [
        {"meta": {"arm": "solo", "carries": {"S1": "o1"}, "slots": {"S1": 0}},
         "behaviour": "chose", "winning_option": "o1", "scenario_id": "a"},
        {"meta": {"arm": "pair", "carries": {"S1": "o1", "S2": "o2"},
                  "slots": {"S1": 0, "S2": 1}, "operator_pinned": ["S1"]},
         "behaviour": "chose", "winning_option": "o2", "scenario_id": "b"},
        {"meta": {"arm": "pair", "carries": {"S1": "o1", "S2": "o2"},
                  "slots": {"S1": 0, "S2": 1}},
         "behaviour": "unresolved", "winning_option": None, "scenario_id": "c"},
    ]
    data = from_records(rows)
    assert len(data) == 2, "the solo row is not a choice"
    assert data.abstentions() == 1, "an unresolved reply is an outcome, not a gap"
    assert data.choices[0].winning_source() == "S2"


def test_free_means_every_pair_inside_the_composition_varies():
    """The bug the ladder run exposed, and it is run 1's fault one level up.

    At two sources "did the order vary" is the right test. At three it is not: a
    triple whose operator block is always first has a varying order and still
    cannot separate the operator from being early, so the fit credited an
    always-first source with the HIGHEST strength to explain why it lost less
    than the position term predicted.
    """
    rows = []
    for i in range(4):
        # A genuine free triple: every pair seen both ways round.
        for order in ((0, 1, 2), (2, 0, 1), (1, 2, 0)):
            rows.append({"meta": {"arm": "pair",
                                  "carries": {"S3": "o1", "S4": "o2", "S5": "o3"},
                                  "slots": dict(zip(("S3", "S4", "S5"), order))},
                         "behaviour": "chose", "winning_option": "o1",
                         "scenario_id": f"free{i}{order}"})
        # An operator block that always precedes the third source.
        for a, b in ((0, 1), (1, 0)):
            rows.append({"meta": {"arm": "pair",
                                  "carries": {"S1": "o1", "S2": "o2", "S3": "o3"},
                                  "slots": {"S1": a, "S2": b, "S3": 2},
                                  "operator_pinned": ["S1", "S2"]},
                         "behaviour": "chose", "winning_option": "o3",
                         "scenario_id": f"pin{i}{a}"})
    got = kinds(from_records(rows))
    assert got["free"] == [("S3", "S4", "S5")]
    assert got["pinned"] == [("S1", "S2", "S3")], (
        "its order varies, but S3 is never earlier than S1, so a strength there "
        "is still confounded with being first")


def test_the_kinds_of_pair_are_measured_and_not_written_down():
    """Whether a pair's order can be read is a property of the run, and a design
    that pins a different source tomorrow must be described correctly with no
    edit here."""
    rows = []
    for i in range(4):
        rows.append({"meta": {"arm": "pair", "carries": {"S3": "o1", "S4": "o2"},
                              "slots": {"S3": i % 2, "S4": 1 - i % 2}},
                     "behaviour": "chose", "winning_option": "o1",
                     "scenario_id": f"free{i}"})
        rows.append({"meta": {"arm": "pair", "carries": {"S1": "o1", "S3": "o2"},
                              "slots": {"S1": 0, "S3": 1},
                              "operator_pinned": ["S1"]},
                     "behaviour": "chose", "winning_option": "o2",
                     "scenario_id": f"pin{i}"})
        rows.append({"meta": {"arm": "pair", "carries": {"S1": "o1", "S2": "o2"},
                              "slots": {"S1": i % 2, "S2": 1 - i % 2},
                              "operator_pinned": ["S1", "S2"]},
                     "behaviour": "chose", "winning_option": "o1",
                     "scenario_id": f"msg{i}"})
    got = kinds(from_records(rows))
    assert got["free"] == [("S3", "S4")]
    assert got["pinned"] == [("S1", "S3")]
    assert got["within_message"] == [("S1", "S2")], (
        "both sources pinned means one message and two labelled lines, which is "
        "primacy and must never be pooled with recency across messages")


# --- The estimators ---


def test_newton_and_minorize_maximize_agree():
    """The only defence against a bug in the optimiser.
    There is no reference implementation to check a strengths fit against, so a second one is
    written that shares no line of code. The likelihood is the strong claim; the parameters agree
    to 1e-8 and no tighter, which is the problem's conditioning."""
    data = sim.simulate(sim.LogitTruth(PLANTED), power.pairs(SOURCES),
                        items=150, seed=7)
    fitted = models.fit(data, "luce")
    newton, mm = fitted.strengths(), models.fit_mm(data)

    # THE LIKELIHOOD IS THE STRONG CLAIM and agrees to machine precision. The parameters agree to 1e-8 and no tighter because the likelihood is flat near its maximum; asserting only those would make this a thermometer for that flatness.
    beta = [math.log(mm[s] / mm[SOURCES[0]]) for s in SOURCES[1:]]
    prepared, _ = models._rows_for(data, models.DESIGNS["luce"], SOURCES, False)
    assert abs(models._loglik(prepared, beta) - fitted.loglik) < 1e-8
    assert max(abs(newton[s] - mm[s]) for s in newton) < 1e-7


def test_the_strengths_model_recovers_a_planted_truth():
    got = sim.recover(sim.LogitTruth(PLANTED), power.pairs(SOURCES), items=400)
    assert got["converged"]
    assert got["max_abs_error"] < 0.02
    # and the ordering, which is what a reader actually looks at
    ordered = sorted(got["recovered"], key=lambda s: got["recovered"][s])
    assert ordered == ["S1", "S2", "S3", "S4", "S5"]


def test_it_recovers_a_position_effect_without_eating_the_strengths():
    got = sim.recover(sim.LogitTruth(PLANTED, later=1.5), power.pairs(SOURCES),
                      model="luce_position", items=400)
    assert abs(got["later_error"]) < 0.15
    assert got["max_abs_error"] < 0.02


def test_a_sorted_arrangement_invents_a_precedence_order_that_is_not_there():
    """The bug that invalidated the first run, reproduced from a known truth.
    Planted: every source exactly as strong as every other, and a large position effect. Balanced
    returns flat strengths; sorted returns a ladder that is the alphabet."""
    flat = sim.LogitTruth({s: 1.0 for s in SOURCES}, later=2.0)
    out = sim.confounded(flat, power.pairs(SOURCES), items=250)
    assert out["planted_strength_spread"] == pytest.approx(0.0, abs=1e-12)
    assert out["balanced"]["spread"] < 0.05, "a balanced design finds the truth"
    assert out["sorted"]["spread"] > 0.4, "a sorted one invents a ladder"
    ordered = sorted(out["sorted"]["recovered"], key=out["sorted"]["recovered"].get)
    assert ordered == list(SOURCES), "and the ladder is the alphabet"


def test_a_source_that_never_wins_is_refused_rather_than_given_a_number():
    """Its maximum-likelihood strength is zero and no finite number is the
    answer. Returning whatever the iteration cap produced would look like a
    measurement."""
    data = Dataset([choice(("S1", "S2"), "S1", item=f"i{i}") for i in range(20)])
    with pytest.raises(models.FitError, match="never won"):
        models.fit(data, "luce")
    with pytest.raises(models.FitError, match="never won"):
        models.fit_mm(data)
    # on purpose, with a ridge, it is allowed and the strength is tiny
    fitted = models.fit(data, "luce", ridge=1.0)
    assert fitted.strengths()["S2"] < fitted.strengths()["S1"]


def test_a_parameter_pairs_cannot_identify_is_refused_and_triples_fit_it():
    """The published result, as a singular information matrix.
    `luce_position_size` carries rank * (size - 2), identically zero on pairs, so nothing in
    pairs-only data supports any value for it."""
    # The column is EXACTLY zero on a pair, making this a strict extension of luce_position. Pinned separately, because any rank * f(size) feature is collinear with `later` on pairs and would decline either way.
    pair = choice(("S1", "S2"), "S1")
    rows = models.DESIGNS["luce_position_size"].build(pair, SOURCES)
    assert [row[-1] for row in rows] == [0.0, 0.0]
    triple_rows = models.DESIGNS["luce_position_size"].build(
        choice(("S1", "S2", "S3"), "S1"), SOURCES)
    assert any(row[-1] for row in triple_rows), "and not zero on a triple"

    truth = sim.LogitTruth(PLANTED, later=1.0)
    pairs_only = sim.simulate(truth, power.pairs(SOURCES), items=60, seed=3)
    with pytest.raises(models.FitError, match="singular"):
        models.fit(pairs_only, "luce_position_size")

    with_triples = sim.simulate(truth, power.pairs(SOURCES) + power.triples(SOURCES),
                                items=60, seed=3)
    fitted = models.fit(with_triples, "luce_position_size")
    assert fitted.converged
    assert "later_x_size" in fitted.coefficients


def test_the_saturated_model_predicts_nothing_it_has_not_seen():
    """Review #9 asked for it by name. It fits any data and extrapolates to
    nothing, so a comparison on held-out whole compositions is the one that
    catches a model flattered by seeing every pair in training."""
    train = sim.simulate(sim.LogitTruth(PLANTED), power.pairs(SOURCES),
                         items=40, seed=1)
    fitted = models.fit_saturated(train)
    seen = choice(("S1", "S2"), "S1")
    assert fitted.predict(seen) is not None
    unseen = choice(("S1", "S2", "S3"), "S1")
    assert fitted.predict(unseen) is None, "a triple it never saw has no answer"


def test_uniform_is_the_floor_and_has_no_parameters():
    data = sim.simulate(sim.LogitTruth(PLANTED), power.pairs(SOURCES),
                        items=20, seed=2)
    fitted = models.fit(data, "uniform")
    assert fitted.n_parameters == 0 and fitted.converged
    got = fitted.predict(choice(("S1", "S2"), "S1"))
    assert got[f"i:S1"] == pytest.approx(0.5)


def test_a_missing_position_is_not_position_zero():
    """Inventing one would put a made-up covariate in the headline model."""
    data = Dataset([Choice(item=f"i{i}",
                           options=(Option(f"i{i}:S1", "S1"), Option(f"i{i}:S2", "S2")),
                           won=f"i{i}:S1") for i in range(10)])
    with pytest.raises(models.FitError, match="missing a recorded position"):
        models.fit(data, "position")


def test_the_reference_source_is_written_down_rather_than_inferred():
    data = sim.simulate(sim.LogitTruth(PLANTED), power.pairs(SOURCES),
                        items=30, seed=4)
    fitted = models.fit(data, "luce")
    assert fitted.coefficients["strength[S1]"] == 0.0
    assert sum(fitted.strengths().values()) == pytest.approx(1.0)


# --- Scoring ---


def test_the_log_score_is_the_arithmetic_it_claims_to_be():
    """Checked against a number worked out by hand."""
    data = Dataset([choice(("S1", "S2"), "S1", item="a")])
    fitted = models.fit(Dataset([choice(("S1", "S2"), "S1", item=f"i{i}")
                                 for i in range(8)]
                                + [choice(("S1", "S2"), "S2", item=f"j{i}")
                                   for i in range(2)]), "luce")
    # 8 of 10 to S1, so P(S1) = 0.8 and the log score of an S1 win is log 0.8
    out = score.evaluate(fitted, data)
    assert out["log_score"] == pytest.approx(math.log(0.8), abs=1e-6)
    assert out["mae"] == pytest.approx(0.2, abs=1e-6)
    assert out["brier"] == pytest.approx(0.2 ** 2 + 0.2 ** 2, abs=1e-6)


def test_models_that_predicted_different_amounts_are_not_ranked():
    """The equal-information-budget rule, made mechanical. A model that declined
    half the test set can look excellent on the half it kept."""
    train = sim.simulate(sim.LogitTruth(PLANTED), power.pairs(SOURCES),
                         items=30, seed=6)
    test = sim.simulate(sim.LogitTruth(PLANTED),
                        power.pairs(SOURCES) + power.triples(SOURCES),
                        items=10, seed=7)
    fits = {"luce": models.fit(train, "luce"),
            "saturated": models.fit_saturated(train)}
    out = score.compare(fits, test)
    assert out["equal_coverage"] is False
    assert out["ranked"] is None
    assert "different amounts" in out["why_no_ranking"]
    assert score.compare(fits, test, allow_unequal_coverage=True)["ranked"]


def test_a_zero_is_counted_rather_than_averaged_away():
    """A model that ruled out something that then happened must be visible."""
    train = Dataset([choice(("S1", "S2"), "S1", item=f"i{i}") for i in range(10)]
                    + [choice(("S1", "S2"), "S2", item=f"j{i}") for i in range(10)])
    fitted = models.fit_saturated(train.filter(lambda c: c.won.endswith("S1")))
    out = score.evaluate(fitted, Dataset([choice(("S1", "S2"), "S2", item="k")]))
    assert out["surprises"] == 1
    assert out["log_score"] < -20, "priced at the floor, not quietly finite"


def test_the_bootstrap_resamples_items_and_never_draws():
    """Three draws of one scenario are three measurements of one thing.
    Treating them as independent narrows the interval by about the square root of the repeat
    count -- roughly 1.7x too confident with three."""
    data = sim.simulate(sim.LogitTruth(PLANTED), power.pairs(SOURCES),
                        items=60, repeats=3, seed=8)
    fits = {n: models.fit(data, n) for n in ("luce", "uniform")}
    out = score.bootstrap(fits["luce"], fits["uniform"], data, draws=200)
    assert out["items"] == 60, "the unit is the item, not the 1800 draws"
    assert out["lo"] < out["difference"] < out["hi"]
    assert out["excludes_zero"] and out["difference"] > 0


def test_calibration_is_over_every_outcome_and_not_only_the_realised_one():
    """Binning the probability given to what happened measures nothing: that
    outcome occurred every time by construction."""
    data = sim.simulate(sim.LogitTruth(PLANTED), power.pairs(SOURCES),
                        items=80, seed=9)
    out = score.evaluate(models.fit(data, "luce"), data)
    assert out["calibration"], "there are bins"
    assert all("observed" in c for c in out["calibration"])
    assert out["calibration_error"] < 0.05
    # a well-fitted model's bins line up
    for cell in out["calibration"]:
        if cell["n"] > 200:
            assert abs(cell["predicted"] - cell["observed"]) < 0.12


# --- Simulating ---


def test_a_balanced_arrangement_really_balances():
    data = sim.simulate(sim.LogitTruth(PLANTED), [["S1", "S2"]], items=60,
                        repeats=2, arrangement="balanced")
    firsts = [min(c.options, key=lambda o: o.position).source for c in data]
    assert firsts.count("S1") == firsts.count("S2") == 60, (
        "nothing is last because of its name")


def test_the_mixture_is_exactly_flat_on_every_pair_and_not_on_a_triple():
    """Which is why the middle power curve is about identification and not size.
    Two Plackett-Luce regimes with reciprocal strengths: each pairwise win probability is the
    other's mirror image, so the 50/50 mixture is exactly 0.5 on every pair."""
    up = sim.LogitTruth(PLANTED)
    down = sim.LogitTruth({s: 1.0 / v for s, v in PLANTED.items()})
    mixture = sim.MixtureTruth([up, down], [0.5, 0.5])
    for pair in power.pairs(SOURCES):
        options = tuple(Option(f"x:{s}", s, position=i) for i, s in enumerate(pair))
        probs = mixture.probabilities(options)
        assert all(p == pytest.approx(0.5) for p in probs.values()), pair
    triple = ("S1", "S3", "S5")
    options = tuple(Option(f"x:{s}", s, position=i) for i, s in enumerate(triple))
    probs = mixture.probabilities(options)
    assert max(probs.values()) - min(probs.values()) > 0.15


def test_a_truth_cannot_be_asked_about_a_source_it_does_not_have():
    with pytest.raises(sim.SimulationError, match="not in this truth"):
        sim.simulate(sim.LogitTruth({"A": 1.0, "B": 1.0}), [["A", "Z"]], items=2)
    with pytest.raises(sim.SimulationError, match="is not an arrangement"):
        sim.simulate(sim.LogitTruth({"A": 1.0, "B": 1.0}), [["A", "B"]], items=2,
                     arrangement="whatever")


# --- The ladder ---


def test_the_ladder_is_read_from_the_frozen_split_and_not_restated():
    split = ladder.load_ladder()
    assert split["split_id"] == "set"
    stages = {s["stage"]: s for s in split["stages"]}
    assert set(stages) == {"one", "two"}
    train_one, test_one = ladder.stage_compositions(stages["one"])
    assert len(train_one) == 10 and all(len(c) == 2 for c in train_one)
    assert len(test_one) == 11, "ten triples and the five-way"
    train_two, test_two = ladder.stage_compositions(stages["two"])
    assert len(train_two) == 14, "the ten pairs plus the four-triple slice"
    assert len(test_two) == 7


def test_extrapolating_from_pairs_is_free_when_the_world_really_is_luce():
    """The sanity check that gives the misspecification number its meaning: if a
    correctly specified world also cost something, the number would be measuring
    the machinery rather than the model."""
    out = ladder.misspecification(sim.LogitTruth(PLANTED), power.pairs(SOURCES),
                                  power.triples(SOURCES), items=300)
    assert out["cost_in_nats_per_draw"] < 0.005


def test_and_costs_something_when_it_is_not():
    up = sim.LogitTruth(PLANTED)
    down = sim.LogitTruth({s: 1.0 / v for s, v in PLANTED.items()})
    out = ladder.misspecification(sim.MixtureTruth([up, down], [0.5, 0.5]),
                                  power.pairs(SOURCES), power.triples(SOURCES),
                                  items=300)
    assert out["cost_in_nats_per_draw"] > 0.01


def test_a_saturated_model_is_not_a_ceiling_and_the_empirical_one_is():
    """The trap the ladder run walked into: `saturated` is blind to arrangement.
    It holds one distribution per composition, so a model that knows only where an
    instruction sat beats it in sample -- which makes it useless as an upper bound.
    """
    # A world where position decides everything and the composition says nothing.
    rows = []
    for i in range(40):
        for first, second in (("S3", "S4"), ("S4", "S3")):
            rows.append(choice(("S3", "S4"), second, item=f"i{i}{first}",
                               positions={first: 0, second: 1}))
    data = Dataset(rows)
    sat = models.fit_saturated(data)
    pos = models.fit(data, "position")
    assert score.log_score(pos, data) > score.log_score(sat, data), (
        "the later option always wins, and saturated cannot see which one is later")

    top = ladder.empirical_ceiling(data)
    assert top["cells"] == 2, "one cell per order, not one per composition"
    assert top["ceiling"] >= score.log_score(pos, data) - 1e-9, "nothing beats it"
    assert top["ceiling"] >= score.log_score(sat, data)
    gaps = ladder.headroom({"position": pos, "saturated": sat}, data)["short_by"]
    assert gaps["saturated"] > gaps["position"] >= -1e-9


def test_top_1_credits_the_winner_the_prediction_rated_highest_and_shares_a_tie():
    assert score.top_one({"o1": 0.7, "o2": 0.3}, "o1") == 1.0
    assert score.top_one({"o1": 0.7, "o2": 0.3}, "o2") == 0.0
    assert score.top_one({"o1": 0.5, "o2": 0.5}, "o2") == 0.5
    assert score.top_one({"o1": 0.5, "o2": 0.5}, None) == 0.0


def test_the_share_recovered_runs_from_the_uniform_model_to_the_ceiling():
    """Where position decides everything, the position fit reaches the ceiling and recovers
    all of the gap, and uniform recovers none of it; both match the ceiling's top-1 or not."""
    rows = []
    for i in range(40):
        for first, second in (("S3", "S4"), ("S4", "S3")):
            rows.append(choice(("S3", "S4"), second, item=f"i{i}{first}",
                               positions={first: 0, second: 1}))
    data = Dataset(rows)
    fits = {"uniform": models.fit(data, "uniform"), "position": models.fit(data, "position")}
    head = ladder.headroom(fits, data)
    assert head["share_recovered"]["uniform"] == pytest.approx(0.0, abs=1e-9)
    assert head["share_recovered"]["position"] == pytest.approx(1.0, abs=0.02)
    assert head["top1_ceiling"] == 1.0
    assert score.evaluate(fits["position"], data)["top1"] == 1.0
    assert ladder.headroom({"position": fits["position"]}, data)["share_recovered"]["position"] is None


def test_the_ceiling_is_the_truth_scoring_itself():
    """A two-source world where every draw is a coin flip has a ceiling of
    log(1/2), and nothing can do better."""
    flat = sim.LogitTruth({"A": 1.0, "B": 1.0})
    assert ladder.ceiling(flat, [["A", "B"]]) == pytest.approx(math.log(0.5))


# --- Power ---


def test_power_rises_with_items_and_is_reported_against_the_planted_effect():
    truth = sim.LogitTruth(PLANTED)
    curve = power.curve(truth, power.recovers(truth, tolerance=0.02),
                        power.pairs(SOURCES), item_counts=(10, 200),
                        replicates=8)
    small, large = curve["points"]
    assert small["power"] < large["power"]
    assert small["items"] == 10 and large["items"] == 200


def test_a_size_only_counts_if_every_larger_size_clears_the_bar_too():
    """A curve is estimated from finitely many replicates, so one point can
    clear the bar by luck."""
    lucky = [{"items": 10, "power": 0.9}, {"items": 20, "power": 0.4},
             {"items": 40, "power": 0.95}]
    assert power._first_at(lucky, 0.8) == 40
    steady = [{"items": 10, "power": 0.5}, {"items": 20, "power": 0.85},
              {"items": 40, "power": 0.9}]
    assert power._first_at(steady, 0.8) == 20
    assert power._first_at([{"items": 10, "power": 0.1}], 0.8) is None


def test_the_misspecification_detector_does_not_cry_wolf():
    """Under a world that really is Plackett-Luce, the saturated model has
    nothing to find and must not find it anyway."""
    truth = sim.LogitTruth(PLANTED)
    curve = power.curve(
        truth, power.beats_on_held_out_items("saturated", "luce",
                                             bootstrap_draws=100),
        power.pairs(SOURCES) + power.triples(SOURCES),
        item_counts=(100,), replicates=8)
    assert curve["points"][0]["power"] <= 0.15


# --- The gate ---


def test_the_phase_one_gate_passes():
    """Run at fewer replicates than the command's default, against exactly the
    same checks and the same thresholds. A cheap run that passed while the real
    one failed would be worse than no test at all."""
    from whowins.stats import phase1

    out = phase1.run(replicates=5, item_counts=(100,))
    failed = [c["check"] for c in out["checks"] if not c["passed"]]
    assert failed == [], failed
    assert out["passed"]
    assert len(out["checks"]) >= 23


def test_the_gate_says_what_it_is_silent_about():
    """A green line that quietly covers less than the gate did is the most
    expensive kind of green line."""
    from whowins.stats import phase1

    out = phase1.run(replicates=2, item_counts=(25,))
    silent = " ".join(out["silent_about"]).lower()
    for clause in ("pre-registration", "harness", "capacity on real data", "above a pair"):
        assert clause in silent, clause
    # The families are checked now, so the gate must not go on calling them deferred.
    assert "probit" not in silent and "deferred" not in silent


@pytest.mark.parametrize("sizes", [{2: 9}, {2: 9, 3: 9, 5: 9}])
def test_the_strengths_caveat_follows_the_data_it_is_printed_under(capsys, sizes):
    """The footer once denied the composition test just after printing it, and the
    guard listed two runs by hand, so the ladder run walked past it."""
    from whowins.stats import strengths

    above_a_pair = max(sizes) > 2
    strengths.render({"run_id": "r", "sizes_present": sizes, "kinds": {}, "fits": {},
                      "data": {"draws": 27, "items": 3, "compositions": [], "abstentions": 0},
                      "can_run_the_composition_test": above_a_pair})
    printed = capsys.readouterr().out
    assert ("PAIRS ONLY" in printed) is not above_a_pair
    assert ("cannot answer" in printed) is not above_a_pair
    assert ("Only the composition test" in printed) is above_a_pair


@pytest.mark.skipif(
    not os.path.exists(os.path.join("results", "balanced-qwen3-14b", "records.jsonl")),
    reason="the run's records are on the operator's branch")
def test_a_real_run_reads_as_choices_and_the_design_is_described_correctly():
    from whowins.runner.analyse import read_records

    data = from_records(read_records(
        os.path.join("results", "balanced-qwen3-14b", "records.jsonl")))
    assert data.sizes == {2: 3240}, "pairs only, which is the whole caveat"
    assert len(data.items) == 1080
    got = kinds(data)
    assert got["within_message"] == [("S1", "S2")]
    assert len(got["free"]) == 3 and len(got["pinned"]) == 6
    assert data.connected()


# --- Free predictions: several sources demanding one option, predicted and never fitted ---


def _free_row(carries, won, slots=None, groups=None):
    slots = slots or {s: i for i, s in enumerate(sorted(carries))}
    return {"line": "record", "trial_id": "t", "scenario_id": "fmt-0001",
            "behaviour": "chose" if won else "unresolved", "winning_option": won,
            "meta": {"arm": "pair", "carries": carries, "slots": slots, "groups": groups}}


def test_an_unusable_reply_is_never_read_as_a_choice():
    """Every other reader left it out; the strengths, the ladder and the pool read its win."""
    row = _free_row({"S1": "o1", "S3": "o3"}, "o3")
    assert len(from_records([row])) == 1
    assert len(from_records([dict(row, usable=False)])) == 0
    free = _free_row({"S1": "o1", "S3": "o3", "S5": "o3"}, "o3")
    assert len(free_from_records([dict(free, usable=False)])) == 0


def test_a_free_prediction_is_not_read_as_a_choice_between_distinct_options():
    """`from_records` used to raise `the same option twice` on the first free prediction, which
    stopped `strengths.sh` on the whole run. It is now left to `free_from_records`."""
    row = _free_row({"S1": "o1", "S3": "o3", "S5": "o3"}, "o3")
    assert len(from_records([row])) == 0
    free = free_from_records([row])
    assert len(free) == 1
    only = next(iter(free))
    assert only.tags["action_won"] == "o3"
    assert sorted(only.tags["actions"].values()) == ["o1", "o3", "o3"]
    assert len(free_from_records([_free_row({"S1": "o1", "S3": "o3"}, "o1")])) == 0


def test_an_option_several_sources_demand_is_predicted_as_the_sum_of_their_chances():
    """The independent-draw reading, which a pair-only fit commits to with no new parameter."""
    pairs = Dataset(choice(("S1", "S3"), "S3", item=f"i{n}") for n in range(30))
    pairs = Dataset([*pairs, *(choice(("S1", "S5"), "S1", item=f"j{n}") for n in range(20)),
                     *(choice(("S3", "S5"), "S5", item=f"k{n}") for n in range(20))])
    fitted = models.fit(pairs, "luce")
    row = _free_row({"S1": "o1", "S3": "o3", "S5": "o3"}, "o3")
    free = next(iter(free_from_records([row])))
    by_source = fitted.predict(free)
    actions = predict_actions(fitted, free)
    assert actions["o3"] == pytest.approx(by_source["o3@S3"] + by_source["o3@S5"])
    assert actions["o1"] == pytest.approx(by_source["o1@S1"])
    assert sum(actions.values()) == pytest.approx(1.0)
    out = score.evaluate_free(fitted, free_from_records([row, _free_row(
        {"S1": "o1", "S3": "o3", "S5": "o3"}, "o1")]))
    assert out["n_scored"] == 2 and out["shared"]["n"] == 2
    assert out["shared"]["observed"] == 0.5
    assert out["shared"]["predicted"] == pytest.approx(actions["o3"])


def test_the_shared_option_is_read_among_draws_where_an_option_won():
    """A fit whose rate of no winner falls as sources are added predicted shared wins too high,
    and the flat rate seen read as sources discounting each other. Both sides now leave it out."""
    pairs = Dataset([*(choice(("S1", "S3"), "S3", item=f"i{n}") for n in range(30)),
                     *(choice(("S1", "S3"), None, item=f"a{n}") for n in range(10)),
                     *(choice(("S1", "S5"), "S1", item=f"j{n}") for n in range(20)),
                     *(choice(("S3", "S5"), "S5", item=f"k{n}") for n in range(20))])
    fitted = models.fit(pairs, "luce")
    row = _free_row({"S1": "o1", "S3": "o3", "S5": "o3"}, "o3")
    actions = predict_actions(fitted, next(iter(free_from_records([row]))))
    assert actions[None] > 0
    out = score.evaluate_free(fitted, free_from_records([row, _free_row(
        {"S1": "o1", "S3": "o3", "S5": "o3"}, None)]))
    assert out["n_scored"] == 2 and out["shared"]["n"] == 1
    assert out["shared"]["observed"] == 1.0
    assert out["shared"]["predicted"] == pytest.approx(actions["o3"] / (1 - actions[None]))
