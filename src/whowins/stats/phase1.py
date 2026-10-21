"""The phase-1 gate, run end to end, with a verdict.
Prints PASS or FAIL against checks written down before it ran. PASSING DOES NOT
RELEASE PHASE 2 on its own: see SILENT_ABOUT. There is no pre-registration, by the
owner's decision, so every result is exploratory.
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
from typing import Any, Mapping, Optional, Sequence

from ..logs import add_arguments, from_arguments, get_logger
from . import capacity, families, ladder, models, pooled, power, rankings, regularity, score
from . import simulate as sim

log = get_logger(__name__)

SOURCES = ("S1", "S2", "S3", "S4", "S5")

# The truth used for recovery and power. An octave apart on purpose: an easy truth makes an encouraging curve that means nothing.
PLANTED = {"S1": 0.5, "S2": 1.0, "S3": 2.0, "S4": 4.0, "S5": 8.0}

# The tolerance and item count recovery is judged at. Arbitrary, and written down, which is what makes them answerable.
TOLERANCE = 0.02
RECOVERY_ITEMS = 400


# Reciprocal strengths, so the 50/50 mixture is EXACTLY 0.5 on every pair -- what makes the middle power curve about identification.
_UP = sim.LogitTruth(PLANTED)
_MIXTURE = sim.MixtureTruth(
    [_UP, sim.LogitTruth({s: 1.0 / v for s, v in PLANTED.items()})], [0.5, 0.5])

# A correlated world for the families: S3 and S5 (user and memory, one transport) move together.
PROBIT_MEANS = {"S1": 0.0, "S2": 0.3, "S3": 0.6, "S4": 0.9, "S5": 1.2}
PROBIT_TRUTH = sim.ProbitTruth(PROBIT_MEANS, {("S3", "S5"): 0.8}, later=0.8)
# A world that breaks regularity: S5's presence pulls S1 up.
CONTEXT_TRUTH = sim.ContextTruth({s: 1.0 for s in SOURCES}, later=0.5,
                                 pulls={("S5", "S1"): 1.5})

# What the gate does NOT cover.
SILENT_ABOUT = (
    "a pre-registration -- there is none, by the owner's decision, so every result is "
    "exploratory",
    "a harness effect on real data -- every model is served on one machine, so a harness "
    "cannot be told from its models until one model is served on both",
    "capacity on real data -- no run design sends declared-tier pairs, so "
    "`capacity.py` is checked on simulated tiers only",
    "any real composition above a pair -- the gate is simulated; "
    "`scripts/strengths.sh <run>` runs the composition test on a real run",
)


def _ok(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"check": name, "passed": bool(passed), "detail": detail}


def _theorem() -> tuple[dict[str, Any], list]:
    """Two worlds that agree on every pair and disagree about the triple."""
    ce = rankings.verify()
    ins = ladder.insufficiency()
    checks = [
        _ok("the counterexample is exact", ce["exact"] and ce["pairwise_identical"],
            "two worlds agree on every pair, as fractions and not as decimals"),
        _ok("their three-way winners differ", ce["winner_differs"],
            f"{ce['triple_winner']}"),
        _ok("a pair-only fit cannot tell the two worlds apart",
            ins["predictions_identical"],
            "identical data, identical fit, identical prediction"),
        _ok("so it is wrong in at least one of them",
            ins["wrong_in_at_least_one_world"],
            f"costing {ins['worst_cost_in_nats_per_draw']:.4f} nats per draw, "
            f"which no amount of pairwise data recovers"),
    ]
    return {"counterexample": ce, "insufficiency": ins}, checks


def _recovery(seed: int) -> tuple[dict[str, Any], list]:
    """Plant strengths, draw from them, and ask the fit to find them again."""
    plain = sim.recover(sim.LogitTruth(PLANTED), power.pairs(SOURCES),
                        items=RECOVERY_ITEMS, seed=seed)
    moved = sim.recover(sim.LogitTruth(PLANTED, later=1.5), power.pairs(SOURCES),
                        model="luce_position", items=RECOVERY_ITEMS, seed=seed)
    checks = [
        _ok("the strengths model recovers a planted truth",
            (plain["max_abs_error"] or 1) <= TOLERANCE,
            f"max error {plain['max_abs_error']:.4f} at {RECOVERY_ITEMS} items, "
            f"tolerance {TOLERANCE}"),
        _ok("and recovers them with a position effect present",
            abs(moved.get("later_error", 9)) <= 0.15
            and (moved["max_abs_error"] or 1) <= TOLERANCE,
            f"later planted 1.5, recovered {moved['recovered_later']:.3f}"),
    ]
    return {"recovery": plain, "recovery_with_position": moved}, checks


def _cross_check(seed: int) -> tuple[dict[str, Any], list]:
    """Newton against minorize-maximize: the only check on the optimiser."""
    data = sim.simulate(sim.LogitTruth(PLANTED), power.pairs(SOURCES),
                        items=200, seed=seed)
    newton, mm = models.fit(data, "luce").strengths(), models.fit_mm(data)
    gap = max(abs(newton[s] - mm[s]) for s in newton)
    check = _ok(
        "two independent algorithms agree", gap < 1e-7,
        f"Newton and minorize-maximize differ by {gap:.2e}. The bound is 1e-7 and "
        f"not machine precision because the likelihood is flat near its maximum, "
        f"so the two agree on it far more closely than on the parameters")
    return {"cross_check": {"newton": newton, "mm": mm, "max_difference": gap}}, [check]


def _confound(seed: int) -> tuple[dict[str, Any], list]:
    """A sorted arrangement, caught inventing an order that is not there."""
    flat = sim.LogitTruth({s: 1.0 for s in SOURCES}, later=2.0)
    out = sim.confounded(flat, power.pairs(SOURCES), items=200, seed=seed)
    check = _ok(
        "a sorted arrangement is caught inventing a precedence order",
        (out["sorted"]["spread"] or 0) > 3 * (out["balanced"]["spread"] or 1e-9),
        f"flat truth, position effect 2.0: balanced spread "
        f"{out['balanced']['spread']:.4f}, sorted {out['sorted']['spread']:.4f}")
    return {"confound": out}, [check]


def _identification(seed: int) -> tuple[dict[str, Any], list]:
    """A parameter pairs cannot identify, refused on pairs and fitted on triples."""
    truth = sim.LogitTruth(PLANTED)
    pairs = sim.simulate(truth, power.pairs(SOURCES), items=100, seed=seed)
    triples = sim.simulate(truth, power.pairs(SOURCES) + power.triples(SOURCES),
                           items=100, seed=seed)
    refused = None
    try:
        models.fit(pairs, "luce_position_size")
    except models.FitError as exc:
        refused = str(exc)
    try:
        fitted = models.fit(triples, "luce_position_size").converged
    except models.FitError as exc:            # pragma: no cover - a regression
        fitted = False
        log.error("luce_position_size failed on three-way data: %s", exc)
    check = _ok("a parameter pairs cannot identify is refused, and triples fit it",
                bool(refused) and bool(fitted),
                "the published result, as a singular information matrix")
    return {"identification": {"refused_on_pairs": refused,
                               "fitted_on_triples": bool(fitted)}}, [check]


def _misspecification(seed: int) -> tuple[dict[str, Any], list]:
    """What extrapolating from pairs costs, exactly, in two worlds."""
    out = {
        "pure_luce": ladder.misspecification(
            _UP, power.pairs(SOURCES), power.triples(SOURCES), items=400, seed=seed),
        "half_and_half_mixture": ladder.misspecification(
            _MIXTURE, power.pairs(SOURCES), power.triples(SOURCES), items=400,
            seed=seed),
    }
    check = _ok(
        "a correctly specified world costs almost nothing to extrapolate",
        out["pure_luce"]["cost_in_nats_per_draw"] < 0.005,
        f"{out['pure_luce']['cost_in_nats_per_draw']:.5f} nats per draw, which is "
        f"the residue of a finite fit and not a bias")
    return {"misspecification": out}, [check]


def _power(replicates: int, item_counts: Sequence[int], full: bool,
           seed: int) -> tuple[dict[str, Any], list]:
    """Three curves that are one argument; read them in the order given.
    The planted mixture is exactly flat Plackett-Luce on every PAIR and is not on any
    triple, so the middle curve measures something absent from that data at any size."""
    detector = power.beats_on_held_out_items("saturated", "luce", bootstrap_draws=150)
    counts = tuple(n for n in item_counts if n <= (400 if full else 200)) \
        or tuple(item_counts[:1])
    truth = sim.LogitTruth(PLANTED)
    curves = {
        "recovery": power.curve(
            truth, power.recovers(truth, tolerance=TOLERANCE), power.pairs(SOURCES),
            item_counts=item_counts, replicates=replicates, seed=seed),
        "spot_misspecification_from_pairs": power.curve(
            _MIXTURE, detector, power.pairs(SOURCES), item_counts=counts,
            replicates=replicates, seed=seed),
        "spot_misspecification_with_triples": power.curve(
            _MIXTURE, detector, power.pairs(SOURCES) + power.triples(SOURCES),
            item_counts=counts, replicates=replicates, seed=seed),
        "false_alarm_when_the_world_is_luce": power.curve(
            _UP, detector, power.pairs(SOURCES) + power.triples(SOURCES),
            item_counts=counts, replicates=replicates, seed=seed),
    }

    def best(name: str) -> float:
        return max(p["power"] or 0 for p in curves[name]["points"])

    from_pairs = best("spot_misspecification_from_pairs")
    with_triples = best("spot_misspecification_with_triples")
    false_alarms = best("false_alarm_when_the_world_is_luce")
    checks = [
        _ok("power rises with the number of items",
            _monotone(curves["recovery"]["points"]),
            "a curve that does not is a broken simulation, not a finding"),
        _ok("a misspecification invisible in pairs becomes visible with triples",
            with_triples > from_pairs + 0.2,
            f"best power {from_pairs:.2f} from pairs at any size, {with_triples:.2f} "
            f"once triples are in the design"),
        _ok("and the detector does not cry wolf on a world that really is Luce",
            false_alarms <= 0.15,
            f"false alarms {false_alarms:.2f} against a nominal 0.05"),
    ]
    return {"power": curves,
            "detectability": {"from_pairs": from_pairs, "with_triples": with_triples,
                              "false_alarm_rate": false_alarms}}, checks


def _families(seed: int) -> tuple[dict[str, Any], list]:
    """The alternatives to Plackett-Luce, each asked to find a world built to need it."""
    split = ladder.load_ladder()
    pairs, _ = ladder.stage_compositions(split["stages"][0])
    slice_train, _ = ladder.stage_compositions(split["stages"][1])
    comparable = [tuple(c) for c in split["comparable_triples"]["sets"]]

    # Two computations sharing no line: one integral for independent errors, and the orthant.
    means = [PROBIT_MEANS[s] for s in SOURCES]
    gaps = {1: 0.0, 2: 0.0}
    for size in (2, 3, 4, 5):
        for comp in itertools.combinations(range(len(SOURCES)), size):
            m = [means[i] for i in comp]
            ones = [[0.0 if a == b else 1.0 for b in comp] for a in comp]
            gap = max(abs(x - y) for x, y in zip(families.probabilities(m),
                                                  families.probabilities(m, ones)))
            gaps[1 if size <= 3 else 2] = max(gaps[1 if size <= 3 else 2], gap)

    train = sim.simulate(PROBIT_TRUTH, slice_train, items=1500, repeats=1, seed=seed)
    held = sim.simulate(PROBIT_TRUTH, comparable, items=500, repeats=1, seed=seed + 1)
    refused = None
    try:
        models.fit(train.with_compositions(pairs), "probit_position")
    except models.FitError as exc:
        refused = str(exc)
    fits = {n: models.fit(train, n)
            for n in ("probit_position", "thurstone_position", "luce_position")}
    got, want = fits["probit_position"].reading(), PROBIT_TRUTH.reading()
    vario_error = got["variogram"]["S3-S5"] - want["variogram"]["S3-S5"]
    mean_error = max(abs(got["means"][s] - want["means"][s]) for s in SOURCES)
    against = {n: score.bootstrap(fits["probit_position"], fits[n], held, draws=200, seed=seed)
               for n in ("thurstone_position", "luce_position")}

    comps = pairs + [tuple(c) for c in power.triples(SOURCES)]
    worlds = {"context": CONTEXT_TRUTH, "luce": sim.LogitTruth(PLANTED, later=0.5),
              "probit": PROBIT_TRUTH}
    flagged = {name: regularity.check(sim.simulate(t, comps, items=300, repeats=1, seed=seed),
                                      draws=200, seed=seed)["violations"]
               for name, t in worlds.items()}
    planted_only = bool(flagged["context"]) and all(
        v["option"] == "S1" and "S5" in v["to"] and "S5" not in v["from"]
        for v in flagged["context"])
    ctx_train = sim.simulate(CONTEXT_TRUTH, slice_train, items=600, repeats=1, seed=seed)
    ctx_held = sim.simulate(CONTEXT_TRUTH, comparable, items=300, repeats=1, seed=seed + 1)
    caught = score.bootstrap(models.fit(ctx_train, "context_position"),
                             models.fit(ctx_train, "luce_position"), ctx_held,
                             draws=200, seed=seed)

    checks = [
        _ok("Thurstone and the probit agree where the errors are independent",
            gaps[1] < 1e-12 and gaps[2] < 1e-4,
            f"one integral against the orthant: {gaps[1]:.1e} on pairs and triples, "
            f"{gaps[2]:.1e} on four- and five-way sets, where the orthant is quasi-Monte Carlo"),
        _ok("the correlated probit is refused on pairs, and the stage-two slice identifies it",
            bool(refused) and "not identified" in refused and fits["probit_position"].converged,
            "pairs pin 10 of its 13 means and covariances; ten pairs and four triples pin all"),
        _ok("and it recovers a planted correlation from that slice",
            abs(vario_error) < 0.08 and mean_error < 0.1,
            f"S3-S5 variogram planted {want['variogram']['S3-S5']:.3f}, recovered "
            f"{got['variogram']['S3-S5']:.3f}; worst mean off by {mean_error:.3f}"),
        _ok("a correlation invisible in pairs is caught once triples are in",
            all(b["lo"] > 0 for b in against.values()),
            "probit_position beats " + ", ".join(
                f"{n} by {b['difference']:+.4f} [{b['lo']:+.4f}, {b['hi']:+.4f}]"
                for n, b in against.items()) + " on the six comparable triples"),
        _ok("regularity catches a planted context effect and no random-utility world",
            planted_only and not flagged["luce"] and not flagged["probit"],
            f"{len(flagged['context'])} violation(s), all S1 rising when S5 joins; "
            f"{len(flagged['luce'])} in a Luce world, {len(flagged['probit'])} in a probit world"),
        _ok("and the context model finds the pull that broke it",
            caught["lo"] > 0,
            f"context_position beats luce_position by {caught['difference']:+.4f} "
            f"[{caught['lo']:+.4f}, {caught['hi']:+.4f}] on the six comparable triples"),
    ]
    return {"families": {"independent_agreement": gaps, "refused_on_pairs": refused,
                         "planted": want, "recovered": got, "against": against,
                         "regularity_flags": {k: len(v) for k, v in flagged.items()},
                         "context_against_luce": caught}}, checks


def _capacity(seed: int) -> tuple[dict[str, Any], list]:
    """Tiers two apart are obeyed 0.995 of the time, neighbours 0.9: R(0.95) is 3 of 6."""
    def obey(winner: int, loser: int) -> float:
        return 0.995 if abs(winner - loser) >= 2 else 0.9

    pairs = list(itertools.combinations(range(1, 7), 2))
    rich = capacity.capacity(capacity.simulate_tiers(obey, pairs, items=800, spread=0.5,
                                                     seed=seed), 0.95, tiers=range(1, 7))
    thin = capacity.capacity(capacity.simulate_tiers(obey, pairs, items=40, spread=0.5,
                                                     seed=seed), 0.95, tiers=range(1, 7))
    checks = [
        _ok("capacity certifies a planted separation from both sides",
            rich["lower"] == rich["upper"] == 3,
            f"R(0.95) at least {rich['lower']} and at most {rich['upper']}, planted 3, "
            f"e.g. tiers {rich['lower_witness']}"),
        _ok("and says so when the data are too thin to certify anything",
            thin["design_ceiling"] <= 1 and thin["verdict"].startswith("no capacity claim"),
            f"40 items per pair: {thin['verdict']}"),
    ]
    return {"capacity": {"rich": rich, "thin": thin}}, checks


def _random_effects(seed: int) -> tuple[dict[str, Any], list]:
    """Item tastes the design balances but cannot cancel, and a spread between models."""
    means = {s: 0.4 * i for i, s in enumerate(SOURCES)}
    comps = power.pairs(SOURCES) + power.triples(SOURCES)
    train = sim.simulate_tastes(means, comps, items=160, sigma_item=1.0, later=1.0, seed=seed)
    held = sim.simulate_tastes(means, [SOURCES], items=160, sigma_item=1.0, later=1.0,
                               seed=seed + 1)
    mixed_fit = models.fit(train, "mixed_position")
    gain = score.bootstrap(mixed_fit, models.fit(train, "luce_position"), held, draws=200,
                           seed=seed)

    rng = random.Random(seed)
    runs, of_model, of_harness = {}, {}, {}
    for r in range(6):
        spread = {s: rng.gauss(0.0, 0.8) for s in SOURCES}
        shift = {(g, s): spread[s] for g in ("fmt", "tool", "path", "ord") for s in SOURCES}
        runs[f"run{r}"] = sim.simulate_tastes(means, power.pairs(SOURCES), items=80,
                                              sigma_item=0.0, shift=shift, later=1.0,
                                              seed=seed + 10 + r)
        of_model[f"run{r}"], of_harness[f"run{r}"] = f"model{r}", ("a" if r < 3 else "b")
    pooled_fit, info = pooled.pool(runs, of_model, of_harness)
    checks = [
        _ok("the mixed model finds planted item tastes and carries them to an item's larger sets",
            mixed_fit.sigmas["item"] > 0.6 and gain["lo"] > 0,
            f"sd of a taste planted 1.0, found {mixed_fit.sigmas['item']:.2f} (Laplace errs low); "
            f"on the same items' five-way sets it beats luce_position by "
            f"{gain['difference']:+.4f} [{gain['lo']:+.4f}, {gain['hi']:+.4f}]"),
        _ok("pooling finds a spread between models, and leaves out a harness it cannot separate",
            pooled_fit.sigmas["model"] > 0.3 and info["harness_effect"].startswith("not fitted"),
            f"sd of a model's shift planted 0.8, found {pooled_fit.sigmas['model']:.2f}; harness "
            f"{info['harness_effect'][:60]}"),
    ]
    return {"random_effects": {"item_sd": mixed_fit.sigmas["item"], "gain": gain,
                               "model_sd": pooled_fit.sigmas["model"],
                               "harness": info["harness_effect"]}}, checks


def run(*, full: bool = False, seed: int = 20260915,
        replicates: Optional[int] = None,
        item_counts: Optional[Sequence[int]] = None) -> dict[str, Any]:
    """Every check, in the order a reader should meet them, with a verdict.

    `replicates` and `item_counts` are overridable so the suite can run the whole
    gate in a second against the same thresholds."""
    replicates = replicates if replicates is not None else (40 if full else 20)
    item_counts = item_counts if item_counts is not None else (
        (25, 50, 100, 200, 400, 800) if full else (25, 100, 400))

    out: dict[str, Any] = {"planted": PLANTED, "tolerance": TOLERANCE,
                           "replicates": replicates}
    checks: list[dict[str, Any]] = []
    for results, found in (_theorem(), _recovery(seed), _cross_check(seed),
                           _confound(seed), _identification(seed),
                           _misspecification(seed),
                           _power(replicates, item_counts, full, seed),
                           _families(seed), _capacity(seed), _random_effects(seed)):
        out.update(results)
        checks.extend(found)

    out["checks"] = checks
    out["passed"] = all(c["passed"] for c in checks)
    out["silent_about"] = SILENT_ABOUT
    return out


def _monotone(points: Sequence[Mapping[str, Any]]) -> bool:
    values = [p["power"] for p in points if p["power"] is not None]
    return all(b >= a - 0.12 for a, b in zip(values, values[1:]))


# --- Printing ---


def render(out: Mapping[str, Any]) -> None:
    ce, ins = out["counterexample"], out["insufficiency"]
    print("PHASE 1 -- THE STRENGTHS FIT AND THE SIMULATION THAT GATES IT")
    print("Everything below is simulated. No model was called and no run was read;\n"
          "the composition test on real data is `scripts/strengths.sh <run>`.")

    print("\nCAN PAIRWISE DATA PIN A THREE-WAY ANSWER?  (it cannot, and here is why)")
    print(f"  two worlds, pairwise {', '.join(f'{k} {v}' for k, v in ce['pairwise'].items())}"
          "  -- identical, as fractions")
    for name, w in sorted(ins["worlds"].items()):
        print(f"    {name:20s} true triple "
              + " ".join(f"{k} {v:.3f}" for k, v in sorted(w['true_triple'].items()))
              + f"  -> {w['true_winner']}")
    any_world = next(iter(ins["worlds"].values()))
    print("    a pair-only fit predicts  "
          + " ".join(f"{k} {v:.3f}"
                     for k, v in sorted(any_world['predicted_triple'].items()))
          + f"  -> {any_world['predicted_winner']}  (for BOTH)")
    print(f"  cost of being wrong: {ins['worst_cost_in_nats_per_draw']:.4f} nats "
          f"per draw, and no amount of")
    print("  pairwise data reduces it, because the two worlds agree in the limit.")

    print("\nDOES THE STRENGTHS FIT FIND A TRUTH THAT IS THERE?")
    r = out["recovery"]
    print(f"  {r['draws']} draws over {r['items']} items, arrangement {r['arrangement']}")
    print("    source    planted  recovered")
    for s in sorted(r["planted"]):
        print(f"    {s:8s}  {r['planted'][s]:7.4f}  {r['recovered'][s]:9.4f}")
    print(f"  max error {r['max_abs_error']:.4f}, tolerance {out['tolerance']}")
    rp = out["recovery_with_position"]
    print(f"  with a real position effect: later planted {rp['planted_later']}, "
          f"recovered {rp['recovered_later']:.3f}")
    print(f"  Newton vs minorize-maximize: {out['cross_check']['max_difference']:.2e}")

    print("\nWOULD IT NOTICE A TRUTH THAT IS NOT THERE?")
    c = out["confound"]
    print(f"  planted: every source equally strong, position effect "
          f"{c['planted_later']}")
    for arrangement in ("balanced", "sorted"):
        cell = c[arrangement]
        print(f"    {arrangement:9s} strengths "
              + " ".join(f"{k} {v:.3f}" for k, v in sorted(cell["recovered"].items()))
              + f"   spread {cell['spread']:.4f}")
    print(f"  {c['verdict']}.")
    print("  That is the first run's design, and it is why pairwise-balanced exists.")

    print("\nWHAT DOES EXTRAPOLATING FROM PAIRS COST?  (exact, not sampled)")
    for name, m in sorted(out["misspecification"].items()):
        print(f"  {name:24s} ceiling {m['ceiling']:+.4f}  pair-fit "
              f"{m['expected_log_score']:+.4f}  cost {m['cost_in_nats_per_draw']:.5f}")

    print("\nHOW MANY ITEMS IS ENOUGH?  (for THIS planted effect and no other)")
    order = ("recovery", "spot_misspecification_from_pairs",
             "spot_misspecification_with_triples",
             "false_alarm_when_the_world_is_luce")
    for name in order:
        curve = out["power"].get(name)
        if not curve:
            continue
        print(f"  {name}:")
        for p in curve["points"]:
            bar = "#" * int(round((p["power"] or 0) * 20))
            print(f"    {p['items']:5d} items  {p['power']:.2f} {bar}")
        print(f"    80% at {curve['enough_for_80']}, 90% at {curve['enough_for_90']}")
    d = out["detectability"]
    print(f"  READ THOSE THREE TOGETHER. The planted mixture is exactly flat "
          f"Plackett-Luce")
    print(f"  on every PAIR, so from pairwise data it is undetectable at any size "
          f"({d['from_pairs']:.2f}")
    print(f"  at best). Put triples in the design and it reaches "
          f"{d['with_triples']:.2f}. The same detector")
    print(f"  raises a false alarm {d['false_alarm_rate']:.2f} of the time on a "
          f"world that really is Luce.")

    fam = out["families"]
    print("\nDO THE ALTERNATIVES FIND THE WORLDS BUILT TO NEED THEM?")
    print("  a probit world where S3 and S5 move together, fitted on ten pairs and four triples:")
    for key in ("planted", "recovered"):
        print(f"    {key:9s} " + "  ".join(f"{k} {v:.2f}" for k, v in
                                        fam[key]["variogram"].items() if k.startswith("S3")))
    for name, b in fam["against"].items():
        print(f"    probit_position against {name} on held-out triples: "
              f"{b['difference']:+.4f} [{b['lo']:+.4f}, {b['hi']:+.4f}]")
    print(f"  regularity violations: {fam['regularity_flags']}")
    cap = out["capacity"]
    print(f"  capacity, six tiers, planted R(0.95) = 3: {cap['rich']['verdict']}")

    print("\nTHE GATE")
    for c in out["checks"]:
        print(f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['check']}")
        print(f"         {c['detail']}")
    print(f"\n  {'PASS' if out['passed'] else 'FAIL'} -- "
          f"{sum(c['passed'] for c in out['checks'])} of {len(out['checks'])} checks")
    print("\n  AND SILENT ABOUT, WHICH IS PART OF THE ANSWER:")
    for item in out["silent_about"]:
        print(f"    - {item}")
    print("  Phase 2 is not released by this alone.")


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m whowins.stats.phase1",
        description="The phase-1 gate: does the strengths fit recover a truth, "
                    "and does the pipeline detect the counterexample?")
    parser.add_argument("--full", action="store_true",
                        help="more replicates and more sizes: slower, same checks")
    parser.add_argument("--seed", type=int, default=20260915,
                        help="the simulation seed (default: 20260915)")
    parser.add_argument("--json", metavar="PATH", default=None,
                        help="also write every number to this file")
    add_arguments(parser, progress=False)
    args = parser.parse_args(argv)
    written = from_arguments("phase1", args)

    log.info("running the phase 1 gate, full=%s seed=%d", args.full, args.seed)
    out = run(full=args.full, seed=args.seed)
    render(out)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, sort_keys=False, default=str)
            fh.write("\n")
        print(f"\nwritten: {args.json}")
    if written:
        log.info("this run's log: %s", written)
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(_main())
