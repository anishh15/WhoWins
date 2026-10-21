"""The second half of the statistics: the normal-error families, the context model,
regularity and capacity. As in test_stats.py, every number is checked against one worked out
another way -- by hand, by a closed form, by simulating the utilities, or by a second code path."""

from __future__ import annotations

import itertools
import math
import random

import pytest

from whowins.stats import capacity, families, ladder, models, normal, power, regularity, score
from whowins.stats import simulate as sim
from whowins.stats.choice import Choice, Dataset, Option, canonical

SOURCES = ("S1", "S2", "S3", "S4", "S5")
MEANS = {"S1": 0.0, "S2": 0.3, "S3": 0.6, "S4": 0.9, "S5": 1.2}
SPLIT = ladder.load_ladder()
PAIRS, _ = ladder.stage_compositions(SPLIT["stages"][0])
SLICE, _ = ladder.stage_compositions(SPLIT["stages"][1])
COMPARABLE = [tuple(c) for c in SPLIT["comparable_triples"]["sets"]]


def choice(sources, won=None, *, item="i", positions=None):
    positions = positions or {s: i for i, s in enumerate(sources)}
    return Choice(item=item, options=tuple(Option(f"{item}:{s}", s, position=positions[s])
                                           for s in sources),
                  won=f"{item}:{won}" if won else None)


# --- The normal distribution ---


@pytest.mark.parametrize("r", [-0.999, -0.95, -0.6, -0.1, 0.0, 0.2, 0.5, 0.8, 0.93, 0.999])
def test_the_bivariate_normal_meets_sheppards_formula(r):
    """P(X > 0, Y > 0) = 1/4 + asin(r) / 2pi, on both sides of every branch Genz's routine takes."""
    assert normal.bvn_upper(0.0, 0.0, r) == pytest.approx(0.25 + math.asin(r) / (2 * math.pi),
                                                          abs=1e-14)


def test_the_bivariate_normal_at_its_edges():
    """No correlation is a product; perfect correlation is one normal; and it is symmetric."""
    for h, k in ((-1.3, 0.4), (0.7, 2.1), (2.5, -0.2)):
        assert normal.bvn_upper(h, k, 0.0) == pytest.approx(normal.cdf(-h) * normal.cdf(-k),
                                                            abs=1e-15)
        assert normal.bvn_upper(h, k, 1.0) == pytest.approx(normal.cdf(-max(h, k)), abs=1e-15)
        assert normal.bvn_upper(h, k, -1.0) == pytest.approx(
            max(0.0, normal.cdf(-k) - normal.cdf(h)), abs=1e-15)
        assert normal.bvn_upper(h, k, 0.63) == pytest.approx(normal.bvn_upper(k, h, 0.63),
                                                             abs=1e-15)


@pytest.mark.parametrize("rho", [0.0, 0.3, 0.7])
def test_the_orthant_above_two_dimensions_meets_a_one_dimensional_integral(rho):
    """Equicorrelated normals are one common factor plus independent noise, so their orthant
    is one integral over the factor -- computed here by a trapezoid sharing no code with it."""
    b = [0.3, -0.4, 1.0, 0.1]
    for d in (3, 4):
        cov = [[1.0 if i == j else rho for j in range(d)] for i in range(d)]
        s = math.sqrt(1 - rho)
        exact = sum(0.01 * normal.pdf(z) * math.prod(
            normal.cdf((bi - math.sqrt(rho) * z) / s) for bi in b[:d])
            for z in (-12 + 0.01 * i for i in range(2401)))
        assert normal.orthant(b[:d], cov) == pytest.approx(exact, abs=2e-5)


def test_a_variable_that_no_longer_varies_is_a_step_and_not_a_crash():
    """A probit at a boundary has a difference of errors with no variance left."""
    assert normal.orthant([0.3], [[0.0]]) == 1.0
    assert normal.orthant([-0.3], [[0.0]]) == 0.0
    assert normal.orthant([0.3, 0.5], [[0.0, 0.0], [0.0, 1.0]]) == pytest.approx(normal.cdf(0.5))
    # Z2 is exactly Z1, so the three-way orthant is the two-way one on Z1 and Z3.
    cov = [[1.0, 1.0, 0.3], [1.0, 1.0, 0.3], [0.3, 0.3, 1.0]]
    assert normal.orthant([0.2, 0.5, 0.1], cov) == pytest.approx(
        normal.orthant([0.2, 0.1], [[1.0, 0.3], [0.3, 1.0]]), abs=1e-4)


def test_round_off_after_near_zero_pivots_is_a_step_and_not_a_crash():
    """The matrix that stopped `strengths.sh` on the Qwen 3 0.6B ladder run: singular (three
    sources' errors merged), a last pivot of -1e-9 from round-off, and a slack of -1e-11."""
    cov = [[4.948870669152209, 4.951111577860239, 4.952743370803785, 1.0597625916353153],
           [4.951111577860239, 4.9533543572545815, 4.954985447441108, 1.059429002939363],
           [4.952743370803785, 4.954985447441108, 4.956619683420493, 1.0611484545443302],
           [1.0597625916353153, 1.059429002939363, 1.0611484545443302, 1.0]]
    normal.cholesky(cov, degenerate=True)
    b = [0.1, 0.3, 0.5, 0.9]
    jittered = [[v + (1e-6 if i == j else 0.0) for j, v in enumerate(r)] for i, r in enumerate(cov)]
    assert normal.orthant(b, cov) == pytest.approx(normal.orthant(b, jittered), abs=1e-3)


def test_a_covariance_that_is_not_one_is_refused():
    with pytest.raises(normal.NormalError, match="not positive definite"):
        normal.cholesky([[1.0, 2.0], [2.0, 1.0]])
    with pytest.raises(normal.NormalError, match="not positive definite"):
        normal.cholesky([[1.0, 2.0], [2.0, 1.0]], degenerate=True)


# --- Thurstone and the probit ---


def test_thurstone_and_the_independent_probit_are_two_computations_that_agree():
    """One integral over z for independent errors, against the orthant with every
    Var(e_a - e_b) = 1. Exact on pairs and triples; quasi-Monte Carlo above."""
    rng = random.Random(3)
    for n in (2, 3, 4, 5):
        for _ in range(4):
            m = [rng.uniform(-2, 2) for _ in range(n)]
            ones = [[0.0 if a == b else 1.0 for b in range(n)] for a in range(n)]
            got, other = families.probabilities(m), families.probabilities(m, ones)
            assert max(abs(x - y) for x, y in zip(got, other)) < (1e-12 if n <= 3 else 1e-4)
    # And on a pair it is the link the scale is defined by: P(a beats b) = Phi(mean_a - mean_b).
    assert families.probabilities([0.7, 0.2])[0] == pytest.approx(normal.cdf(0.5), abs=1e-15)


@pytest.mark.parametrize("sources", [("S1", "S3", "S5"), SOURCES])
def test_the_probit_probabilities_are_what_simulating_its_utilities_gives(sources):
    """Draw correlated normal utilities, take the highest, count. Nothing of the orthant
    machinery is used, so a wrong differenced covariance cannot hide here."""
    truth = sim.ProbitTruth(MEANS, {("S3", "S5"): 0.8, ("S1", "S2"): -0.4}, later=0.0)
    options = tuple(Option(s, s, position=i) for i, s in enumerate(sources))
    predicted = truth.probabilities(options)
    names = list(sources)
    chol = normal.cholesky([[truth._rho(a, b) for b in names] for a in names])
    rng = random.Random(11)
    n, wins = 60_000, dict.fromkeys(names, 0)
    for _ in range(n):
        z = [rng.gauss(0, 1) for _ in names]
        u = {a: MEANS[a] + sum(chol[i][j] * z[j] for j in range(i + 1))
             for i, a in enumerate(names)}
        wins[max(u, key=u.get)] += 1
    for a in names:
        p = predicted[a]
        assert abs(wins[a] / n - p) < 4 * math.sqrt(p * (1 - p) / n), a


def test_the_probit_is_refused_on_pairs_even_though_a_position_term_would_pin_it():
    """The decision the whole block turns on. With a shared recency effect, ten pairs in two
    orders reach full rank, but only by assuming recency is the same size in every pair, which
    the within-message pairs already contradict. So identification is judged on compositions."""
    spec = families._Spec("probit", True, SOURCES)
    patterns = [(tuple(range(5)[SOURCES.index(a)] for a in pair), ranks)
                for pair in PAIRS for ranks in ((0.0, 1.0), (1.0, 0.0))]
    assert families._jacobian_rank(spec, families._generic(spec), patterns) == 14, (
        "with position, pairs alone pin all fourteen parameters")
    why = families._unidentified(spec, patterns)
    assert why and "pin 10 of its 13" in why

    data = sim.simulate(sim.ProbitTruth(MEANS, later=0.8), PAIRS, items=60, seed=1)
    for model in ("probit", "probit_position"):
        with pytest.raises(models.FitError, match="not identified by these compositions"):
            models.fit(data, model)


def test_the_frozen_stage_two_slice_identifies_the_probit():
    """Ten pairs pin 10 of the 13 means and covariances; the four-triple slice pins all 13,
    which is what `set.json` chose it for: every source pair sits in some triple."""
    bare = families._Spec("probit", False, SOURCES)
    point = families._generic(bare)
    index = {s: i for i, s in enumerate(SOURCES)}

    def pats(comps):
        return [(tuple(index[s] for s in c), tuple(0.0 for _ in c)) for c in comps]

    assert families._jacobian_rank(bare, point, pats(PAIRS)) == 10
    assert families._jacobian_rank(bare, point, pats(SLICE)) == 13


def test_the_probit_recovers_a_planted_correlation_and_nests_thurstone():
    truth = sim.ProbitTruth(MEANS, {("S3", "S5"): 0.8}, later=0.8)
    data = sim.simulate(truth, SLICE, items=1500, repeats=1, seed=5)
    probit = models.fit(data, "probit_position")
    thurstone = models.fit(data, "thurstone_position")
    got, want = probit.reading(), truth.reading()
    assert got["variogram"]["S3-S5"] == pytest.approx(want["variogram"]["S3-S5"], abs=0.08)
    assert max(abs(got["means"][s] - want["means"][s]) for s in SOURCES) < 0.1
    assert got["later"] == pytest.approx(want["later"], abs=0.1)
    # Thurstone is the probit with every Var(e_a - e_b) equal, so the probit can only fit better.
    assert probit.loglik >= thurstone.loglik - 1e-6
    assert "variogram" not in thurstone.reading()


def test_a_family_refuses_what_it_does_not_model():
    """Abstaining is its own process; the probit is fitted only where its likelihood is exact;
    and a source that never won has no finite mean."""
    abstained = Dataset([choice(("S1", "S2"), "S1", item="a"), choice(("S1", "S2"), None, item="b")])
    with pytest.raises(models.FitError, match="decided draws only"):
        models.fit(abstained, "thurstone")
    four = Dataset([choice(("S1", "S2", "S3", "S4"), s, item=f"i{k}{s}")
                    for k in range(3) for s in ("S1", "S2", "S3", "S4")])
    with pytest.raises(models.FitError, match="up to three"):
        models.fit(four, "probit")
    dead = Dataset([choice(("S1", "S2"), "S1", item=f"i{k}") for k in range(10)])
    with pytest.raises(models.FitError, match="never won"):
        models.fit(dead, "thurstone")
    with pytest.raises(models.FitError, match="no ridge"):
        models.fit(dead, "thurstone", ridge=1.0)


def test_a_fit_on_a_boundary_says_so():
    """S3 and S5 given identical errors: their variogram is zero, and a reader must be told the
    0.00 is a limit the fit ran into, not a measured quantity."""
    spec = families._Spec("probit", False, SOURCES)
    theta = spec.start()
    cells = dict(zip(spec.cells, range(len(spec.names) - len(spec.cells), len(spec.names))))
    # Row S5 of the differenced Cholesky copies row S3 and loses its own variance.
    theta[cells[(3, 0)]], theta[cells[(3, 1)]] = 0.5, math.sqrt(0.75)
    theta[cells[(3, 2)]], theta[cells[(3, 3)]] = 0.0, -30.0
    fitted = families.RumFitted(name="probit", sources=SOURCES, _spec=spec, _theta=tuple(theta))
    assert fitted.reading()["variogram"]["S3-S5"] < 1e-12
    assert "S3-S5" in families.boundary_note(fitted)
    assert families.boundary_note(families.RumFitted(
        name="probit", sources=SOURCES, _spec=spec, _theta=tuple(spec.start()))) is None
    with pytest.raises(models.FitError, match="not Plackett-Luce"):
        fitted.strengths()


# --- The context model ---


def test_a_context_column_is_one_source_pulling_on_another():
    """On a pair each option carries the other's pull; on a triple, both others'."""
    names = models.DESIGNS["context"].names(SOURCES)
    rows = models.DESIGNS["context"].build(choice(("S1", "S2")), SOURCES)
    on = [{n for n, x in zip(names, row) if x and n.startswith("context[")} for row in rows]
    assert on == [{"context[S2 on S1]"}, {"context[S1 on S2]"}]
    rows = models.DESIGNS["context"].build(choice(("S1", "S2", "S3")), SOURCES)
    on = [{n for n, x in zip(names, row) if x and n.startswith("context[")} for row in rows]
    assert on[2] == {"context[S1 on S3]", "context[S2 on S3]"}


def test_the_ridge_shrinks_the_pulls_and_never_the_strengths():
    """A huge penalty on the pulls leaves Plackett-Luce, not a model with every strength
    pulled to zero; and a source that never won is still refused, because its strength is
    not the thing held finite."""
    data = sim.simulate(sim.LogitTruth({"S1": 0.5, "S2": 1.0, "S3": 2.0}), power.pairs(SOURCES[:3])
                        + power.triples(SOURCES[:3]), items=80, seed=2)
    luce = models.fit(data, "luce").strengths()
    held = models.fit(data, "context", ridge=1e9)
    assert max(abs(held.strengths()[s] - luce[s]) for s in luce) < 1e-5
    assert all(abs(v) < 1e-6 for k, v in held.coefficients.items() if k.startswith("context["))
    dead = Dataset([choice(("S1", "S2"), "S1", item=f"i{k}") for k in range(10)])
    with pytest.raises(models.FitError, match="never won"):
        models.fit(dead, "context", ridge=1.0)


def test_with_no_ridge_the_context_model_chooses_one_by_cross_validation_over_items():
    world = sim.ContextTruth({s: 1.0 for s in SOURCES}, later=0.5, pulls={("S5", "S1"): 1.5})
    train = sim.simulate(world, SLICE, items=400, repeats=1, seed=3)
    fitted = models.fit(train, "context_position")
    assert any("cross-validation over items" in n for n in fitted.notes)
    assert fitted.coefficients["context[S5 on S1]"] > 0.5, "the planted pull, found"
    held = sim.simulate(world, COMPARABLE, items=300, repeats=1, seed=4)
    out = score.bootstrap(fitted, models.fit(train, "luce_position"), held, draws=200)
    assert out["lo"] > 0, "and it predicts triples it never saw better than Plackett-Luce"


def test_canonical_data_fit_exactly_as_the_draws_they_came_from():
    """Forgetting items is a speed change for a fit: same ranks, same winners, same weights."""
    data = sim.simulate(sim.LogitTruth(dict(zip(SOURCES, (0.5, 1, 2, 4, 8))), later=1.0),
                        PAIRS + [("S1", "S3", "S5")], items=40, seed=6)
    short = canonical(data)
    assert short.n_draws == data.n_draws and len(short) < len(data)
    a = models.fit(data, "luce_position").coefficients
    b = models.fit(short, "luce_position").coefficients
    assert max(abs(a[k] - b[k]) for k in a) < 1e-9


# --- Regularity ---


def test_regularity_is_the_arithmetic_it_claims():
    """S1 wins 2 of 10 against S2 alone and 6 of 10 once S3 joins: a rise of 0.4."""
    rows = [choice(("S1", "S2"), "S1" if k < 2 else "S2", item=f"i{k}") for k in range(10)]
    rows += [choice(("S1", "S2", "S3"), "S1" if k < 6 else "S3", item=f"i{k}") for k in range(10)]
    out = regularity.check(Dataset(rows), draws=200)
    assert out["tests"] == 2, "S1 and S2, each from the pair to the triple"
    s1 = next(r for r in out["largest"] if r["option"] == "S1")
    assert (s1["share_before"], s1["share_after"]) == (0.2, 0.6)
    assert s1["rise"] == pytest.approx(0.4)
    assert s1["se"] > 0, "items are resampled, so the rise has an error"


def test_regularity_flags_a_planted_pull_and_no_random_utility_world():
    comps = PAIRS + [tuple(c) for c in power.triples(SOURCES)]
    pulled = sim.ContextTruth({s: 1.0 for s in SOURCES}, later=0.5, pulls={("S5", "S1"): 1.5})
    flagged = regularity.check(sim.simulate(pulled, comps, items=300, repeats=1, seed=2),
                               draws=200)["violations"]
    assert flagged and all(v["option"] == "S1" and "S5" in v["to"] for v in flagged)
    for world in (sim.LogitTruth(dict(zip(SOURCES, (0.5, 1, 2, 4, 8))), later=0.5),
                  sim.ProbitTruth(MEANS, {("S3", "S5"): 0.8}, later=0.8)):
        assert regularity.check(sim.simulate(world, comps, items=300, repeats=1, seed=2),
                                draws=200)["violations"] == []


def test_regularity_says_so_when_there_is_nothing_to_test():
    out = regularity.check(Dataset([choice(("S1", "S2"), "S1")]))
    assert out["tests"] == 0 and "no set above a pair" in out["note"]


# --- Capacity ---


def test_the_binomial_bounds_meet_the_numbers_worked_by_hand():
    """1 of 2: P(X >= 1 | p) = 1 - (1 - p)^2 = 0.05 gives p = 1 - sqrt(0.95), and the upper
    bound mirrors it. n of n gives alpha^(1/n), the formula behind the method's 59 and 299."""
    lo, hi = capacity.clopper_pearson(1, 2, 0.05, 0.05)
    assert lo == pytest.approx(1 - math.sqrt(0.95), abs=1e-12)
    assert hi == pytest.approx(math.sqrt(0.95), abs=1e-12)
    assert capacity.clopper_pearson(190, 190, 0.05, 0.05)[0] == pytest.approx(0.05 ** (1 / 190))
    assert capacity.clopper_pearson(0, 30, 0.05, 0.05)[1] == pytest.approx(1 - 0.05 ** (1 / 30))
    assert capacity.items_needed(0.95, 0.05) == 59
    assert capacity.items_needed(0.99, 0.05) == 299
    lo2, hi2 = capacity.clopper_pearson(7, 40, 0.01, 0.03)
    mirror = capacity.clopper_pearson(33, 40, 0.03, 0.01)
    assert (lo2, hi2) == pytest.approx((1 - mirror[1], 1 - mirror[0]), abs=1e-12)


def _draws(obey, tiers, items):
    return [capacity.TierDraw(f"i{k}", w, l, obey(w, l), "0")
            for k in range(items) for w, l in itertools.combinations(tiers, 2)]


def test_capacity_finds_a_subset_that_skips_tiers():
    """Neighbours always confused, tiers two apart always kept: the largest certified set is
    every other tier, which no reading of adjacent pairs in order would find."""
    out = capacity.capacity(_draws(lambda w, l: abs(w - l) >= 2, range(1, 7), 300), 0.95,
                            tiers=range(1, 7))
    assert out["lower"] == out["upper"] == 3
    assert out["lower_witness"] == [1, 3, 5]
    assert out["subsets_at_lower"] == 4, "{1,3,5} {1,3,6} {1,4,6} {2,4,6}"


def test_capacity_makes_no_claim_where_the_data_could_not_support_one():
    """Thirty items, every one obeyed, cannot clear 0.95 with fifteen pairs held at once: the
    answer is 'no claim', never a capacity of one."""
    out = capacity.capacity(_draws(lambda w, l: True, range(1, 7), 30), 0.95, tiers=range(1, 7))
    assert out["design_ceiling"] == 1 and out["lower"] == 1
    assert out["verdict"].startswith("no capacity claim")
    assert out["upper"] == 6, "nothing is ruled out either"


def test_one_draw_per_item_keeps_its_level_when_repeats_move_together():
    """The reason the unit is the item. Each item is obeyed or not as a whole, at exactly
    q = 0.95, so certifying the pair is always wrong: one draw per item does it about as
    often as its level allows, counting every draw does it several times as often."""
    rng = random.Random(7)
    wrong = {"item": 0, "draw": 0}
    for _ in range(300):
        draws = []
        for i in range(200):
            ok = rng.random() < 0.95
            draws += [capacity.TierDraw(f"i{i}", 1, 2, ok, str(k)) for k in range(3)]
        # The default is the item; counting draws has to be asked for.
        wrong["item"] += capacity.capacity(draws, 0.95, tiers=(1, 2))["lower"] == 2
        wrong["draw"] += capacity.capacity(draws, 0.95, tiers=(1, 2), unit="draw")["lower"] == 2
    assert wrong["item"] / 300 <= 0.025 + 0.02, "the per-bound level, with room for chance"
    assert wrong["draw"] / 300 > 0.08


def test_capacity_refuses_what_is_not_the_question():
    with pytest.raises(capacity.CapacityError, match="not two of"):
        capacity.capacity([capacity.TierDraw("i", 3, 3, True, "0")], 0.9)
    with pytest.raises(capacity.CapacityError, match="strictly between"):
        capacity.capacity([capacity.TierDraw("i", 1, 2, True, "0")], 1.0)
    with pytest.raises(capacity.CapacityError, match="unit"):
        capacity.capacity([capacity.TierDraw("i", 1, 2, True, "0")], 0.9, unit="call")


# --- The families block ---


def test_the_families_block_fits_every_family_alike_on_decided_draws():
    """Abstentions are counted and left out, the probit refuses stage one and fits stage two,
    and reusing each stage's fits for the comparable triples changes no number."""
    truth = sim.LogitTruth(dict(zip(SOURCES, (0.5, 1, 2, 4, 8))), later=0.8, abstain=0.0)
    comps = PAIRS + [tuple(c) for c in power.triples(SOURCES)] + [SOURCES]
    data = sim.simulate(truth, comps, items=60, repeats=1, seed=8)
    names = ("luce", "thurstone", "probit", "saturated")
    out = ladder.families(data, model_names=names, bootstrap_draws=50)
    assert out["decided_draws"] + out["left_out"] == data.n_draws and out["left_out"] > 0
    one, two = out["stages"]
    assert "not identified" in one["refused"]["probit"]
    assert "probit" in two["fitted"] and "probit" not in two["refused"]
    assert set(out["regularity"]) >= {"tests", "violations", "largest"}
    decided = data.filter(lambda c: c.won is not None)
    train, _ = ladder.stage_compositions(SPLIT["stages"][1])
    fresh = models.fit(decided.with_compositions(train), "thurstone")
    subset = decided.with_compositions(COMPARABLE)
    assert out["on_the_comparable_triples"]["two"]["rows"]["thurstone"]["log_score"] == \
        score.evaluate(fresh, subset)["log_score"]


def test_the_report_prints_the_families_block_and_what_it_refused(capsys):
    from whowins.stats import strengths

    stage = {"stage": "two", "train": ["S1-S2"], "test": ["S1-S2-S3"],
             "scores": {"rows": {"luce": {"log_score": -1.1, "coverage": 1.0},
                                 "probit_position": {"log_score": -0.9, "coverage": 1.0}}},
             "intervals": {"probit_position": {"difference": 0.2, "lo": 0.1, "hi": 0.3}},
             "refused": {"probit": "not identified by these compositions"},
             "fitted": {"probit_position": {"variogram": {"S3-S5": 0.2}}}}
    strengths._render_families({"decided_draws": 90, "left_out": 10, "stages": [stage],
                                "regularity": {"tests": 3, "alpha": 0.05, "violations": [],
                                               "largest": []}})
    printed = capsys.readouterr().out
    assert "THE FAMILIES" in printed and "10 with no winner left out" in printed
    assert "probit               REFUSED: not identified" in printed
    assert "S3-S5 0.20" in printed and "0 violation(s)" in printed
