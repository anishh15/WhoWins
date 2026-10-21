"""A world with a known answer, and data drawn from it.
An estimator never asked to find an answer somebody knew tells you nothing when it
returns one. `arrangement` is part of the truth: balanced is what pairwise-balanced
does, sorted is the first run's design and is kept as a planted fault.
"""

from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

from .choice import Choice, Dataset, Option
from .models import ABSTAIN
from .rankings import RankingWorld

ARRANGEMENTS = ("balanced", "random", "sorted")


class SimulationError(ValueError):
    """A world that cannot generate the data asked for."""


# --- Truths ---


@dataclass
class LogitTruth:
    """Strengths, and optionally a real position effect, as the data-generator.
    `later` is the coefficient on the same 0-to-1 rank the estimators use, so a planted
    1.0 is a number the fit is entitled to find. `abstain` gives simulated data the
    "no option won" outcome real replies have."""
    strengths: Mapping[str, float]
    later: float = 0.0
    abstain: Optional[float] = None

    def __post_init__(self) -> None:
        if len(self.strengths) < 2:
            raise SimulationError("a truth needs at least two sources")
        for k, v in self.strengths.items():
            if v <= 0:
                raise SimulationError(f"strength {v} for {k}: must be positive")

    @property
    def alternatives(self) -> tuple[str, ...]:
        return tuple(sorted(self.strengths))

    def utilities(self, options: Sequence[Option]) -> list[float]:
        span = len(options) - 1
        order = sorted(options, key=lambda o: (o.position, o.option_id))
        rank = {o.option_id: (i / span if span else 0.0) for i, o in enumerate(order)}
        return [math.log(self.strengths[o.source]) + self.later * rank[o.option_id]
                for o in options]

    def probabilities(self, options: Sequence[Option]) -> dict[Optional[str], float]:
        utilities = self.utilities(options)
        keys: list[Optional[str]] = [o.option_id for o in options]
        if self.abstain is not None:
            utilities.append(self.abstain)
            keys.append(ABSTAIN)
        top = max(utilities)
        weights = [math.exp(u - top) for u in utilities]
        total = sum(weights)
        return {k: w / total for k, w in zip(keys, weights)}

    def as_dict(self) -> dict[str, Any]:
        total = sum(self.strengths.values())
        return {"kind": "logit",
                "strengths": {k: v / total for k, v in sorted(self.strengths.items())},
                "later": self.later, "abstain": self.abstain}


@dataclass
class ContextTruth(LogitTruth):
    """A logit whose options pull on each other: an option's utility gains `pulls[(z, a)]`
    whenever z competes with a (Seshadri et al. 2019). Not a random-utility model, so it can
    break regularity, which is what the gate plants it for."""
    pulls: Mapping[tuple[str, str], float] = field(default_factory=dict)

    def utilities(self, options: Sequence[Option]) -> list[float]:
        present = {o.source for o in options}
        return [u + sum(self.pulls.get((z, o.source), 0.0) for z in present if z != o.source)
                for u, o in zip(super().utilities(options), options)]

    def as_dict(self) -> dict[str, Any]:
        return {**super().as_dict(), "kind": "context",
                "pulls": {f"{z} on {a}": v for (z, a), v in sorted(self.pulls.items())}}


@dataclass
class WorldTruth:
    """A distribution over rankings as the data-generator.
    Position is ignored deliberately: these worlds say something about composition, and
    a position effect too would make a failed Luce fit ambiguous between two causes."""
    world: RankingWorld

    @property
    def alternatives(self) -> tuple[str, ...]:
        return self.world.alternatives

    def probabilities(self, options: Sequence[Option]) -> dict[Optional[str], float]:
        by_source = {o.source: o.option_id for o in options}
        probs = self.world.choice_probs(sorted(by_source))
        return {by_source[s]: float(p) for s, p in probs.items()}

    def as_dict(self) -> dict[str, Any]:
        return {"kind": "world", **self.world.as_dict()}


@dataclass
class ProbitTruth:
    """Normal random utilities, correlated across sources, as the data-generator.
    Errors have unit variance and `correlation[(a, b)]` between two sources, zero if unnamed;
    `later` shifts utility by the estimators' 0-to-1 rank. `reading()` is on the scale a fit
    reports, so a planted world and a recovered one compare directly."""
    means: Mapping[str, float]
    correlation: Mapping[tuple[str, str], float] = field(default_factory=dict)
    later: float = 0.0

    def __post_init__(self) -> None:
        from . import normal

        if len(self.means) < 2:
            raise SimulationError("a truth needs at least two sources")
        names = self.alternatives
        try:
            normal.cholesky([[self._rho(a, b) for b in names] for a in names])
        except normal.NormalError as exc:
            raise SimulationError(f"correlations {dict(self.correlation)}: {exc}") from exc
        self._cache: dict = {}

    @property
    def alternatives(self) -> tuple[str, ...]:
        return tuple(sorted(self.means))

    def _rho(self, a: str, b: str) -> float:
        if a == b:
            return 1.0
        return self.correlation.get((a, b), self.correlation.get((b, a), 0.0))

    def probabilities(self, options: Sequence[Option]) -> dict[Optional[str], float]:
        from .families import probabilities

        span = len(options) - 1
        order = sorted(options, key=lambda o: (o.position, o.option_id))
        rank = {o.option_id: (i / span if span else 0.0) for i, o in enumerate(order)}
        key = tuple((o.source, rank[o.option_id]) for o in options)
        if key not in self._cache:
            means = [self.means[s] + self.later * r for s, r in key]
            vario = [[2.0 - 2.0 * self._rho(a, b) for b, _ in key] for a, _ in key]
            self._cache[key] = probabilities(means, vario)
        return dict(zip((o.option_id for o in options), self._cache[key]))

    def reading(self) -> dict[str, Any]:
        names = self.alternatives
        pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
        scale = sum(2.0 - 2.0 * self._rho(a, b) for a, b in pairs) / len(pairs)
        root = math.sqrt(scale)
        return {"means": {s: (self.means[s] - self.means[names[0]]) / root for s in names},
                "later": self.later / root,
                "variogram": {f"{a}-{b}": (2.0 - 2.0 * self._rho(a, b)) / scale
                              for a, b in pairs}}

    def as_dict(self) -> dict[str, Any]:
        return {"kind": "probit", **self.reading()}


@dataclass
class MixtureTruth:
    """Two regimes, mixed. A world that is not any Plackett-Luce model.
    This is item heterogeneity, not a pathology invented to make the method fail -- both
    runs found the format family behaving unlike the other four. The exact proof is
    `rankings.WORLDS` at three alternatives; this is the demonstration at five."""
    parts: Sequence[Any]
    weights: Sequence[float]

    def __post_init__(self) -> None:
        if len(self.parts) != len(self.weights) or not self.parts:
            raise SimulationError("a mixture needs a weight for every part")
        if any(w < 0 for w in self.weights) or not sum(self.weights):
            raise SimulationError(f"mixture weights {list(self.weights)}")
        alts = {tuple(p.alternatives) for p in self.parts}
        if len(alts) != 1:
            raise SimulationError("every part of a mixture needs the same alternatives")

    @property
    def alternatives(self) -> tuple[str, ...]:
        return tuple(self.parts[0].alternatives)

    def probabilities(self, options: Sequence[Option]) -> dict[Optional[str], float]:
        total = sum(self.weights)
        out: dict[Optional[str], float] = {}
        for part, weight in zip(self.parts, self.weights):
            for key, p in part.probabilities(options).items():
                out[key] = out.get(key, 0.0) + p * weight / total
        return out

    def as_dict(self) -> dict[str, Any]:
        return {"kind": "mixture",
                "weights": [w / sum(self.weights) for w in self.weights],
                "parts": [p.as_dict() for p in self.parts]}


# --- Drawing ---


def _positions(composition: Sequence[str], arrangement: str, index: int,
               rng: random.Random) -> dict[str, int]:
    order = list(composition)
    if arrangement == "sorted":
        order = sorted(order)
    elif arrangement == "random":
        rng.shuffle(order)
    elif arrangement == "balanced":
        every = sorted(itertools.permutations(sorted(composition)))
        order = list(every[index % len(every)])
    else:
        raise SimulationError(
            f"{arrangement!r} is not an arrangement; have {ARRANGEMENTS}")
    return {s: i for i, s in enumerate(order)}


def _pick(probabilities: Mapping[Optional[str], float],
          rng: random.Random) -> Optional[str]:
    roll, seen = rng.random(), 0.0
    items = sorted(probabilities.items(), key=lambda kv: (kv[0] is None, kv[0] or ""))
    for key, p in items:
        seen += p
        if roll < seen:
            return key
    return items[-1][0]


def simulate(truth, compositions: Iterable[Sequence[str]], *, items: int = 200,
             repeats: int = 3, arrangement: str = "balanced",
             seed: int = 20260915) -> Dataset:
    """Draw a dataset the shape of a real run.
    Every item is asked every composition `repeats` times, which is what the runner
    sends, so a power curve here is a statement about item counts a run can be set to."""
    comps = [tuple(sorted(c)) for c in compositions]
    if not comps:
        raise SimulationError("no composition to simulate")
    unknown = {s for c in comps for s in c} - set(truth.alternatives)
    if unknown:
        raise SimulationError(f"{sorted(unknown)} are not in this truth")
    rng = random.Random(seed)
    out = []
    for i in range(items):
        item = f"sim-{i:04d}"
        for c_index, comp in enumerate(comps):
            for r in range(repeats):
                slots = _positions(comp, arrangement, i * repeats + r, rng)
                options = tuple(
                    Option(option_id=f"{item}:{s}", source=s, position=slots[s])
                    for s in comp)
                won = _pick(truth.probabilities(options), rng)
                out.append(Choice(item=item, options=options, won=won))
    return Dataset(out)


def simulate_tastes(means: Mapping[str, float], compositions: Iterable[Sequence[str]], *,
                    items: int, sigma_item: float, shift: Optional[Mapping] = None,
                    later: float = 0.0, families: Sequence[str] = ("fmt", "tool", "path", "ord"),
                    seed: int = 20260915) -> Dataset:
    """A run where each item has its own taste for each of its five options, and a family
    shifts a source by `shift[(family, source)]`. Options rotate across sources as the design
    deals them, so content and source part. Tastes are seeded by item, so a second call over
    the same items, for a held-out set, meets the same tastes."""
    comps = [tuple(c) for c in compositions]
    rng = random.Random(seed)
    out = []
    for i in range(items):
        family = families[i % len(families)]
        item = f"{family}-{i:04d}"
        taste = {f"o{k}": random.Random(f"taste {item} {k}").gauss(0.0, sigma_item)
                 for k in range(1, 6)}
        for ci, comp in enumerate(comps):
            order = list(comp)
            rng.shuffle(order)
            options = tuple(Option(f"o{(ci + j + i) % 5 + 1}", s, position=order.index(s))
                            for j, s in enumerate(comp))
            span = max(1, len(comp) - 1)
            u = [means[o.source] + (shift or {}).get((family, o.source), 0.0)
                 + taste[o.option_id] + later * o.position / span for o in options]
            top = max(u)
            weights = [math.exp(x - top) for x in u]
            won = _pick(dict(zip((o.option_id for o in options),
                                 (w / sum(weights) for w in weights))), rng)
            out.append(Choice(item=item, options=options, won=won))
    return Dataset(out)


# --- Recovery ---


def _normalised(strengths: Mapping[str, float]) -> dict[str, float]:
    total = sum(strengths.values())
    return {k: v / total for k, v in sorted(strengths.items())}


def recover(truth: LogitTruth, compositions: Iterable[Sequence[str]], *,
            model: str = "luce", items: int = 200, repeats: int = 3,
            arrangement: str = "balanced", seed: int = 20260915) -> dict[str, Any]:
    """Plant a truth, draw from it, fit it back, and say how far off it is.
    Error is over strengths NORMALISED to sum to one, the only scale they are defined
    on: a planted 2.0 recovered as 4.0 may be no error at all."""
    from . import models

    data = simulate(truth, compositions, items=items, repeats=repeats,
                    arrangement=arrangement, seed=seed)
    fitted = models.fit(data, model)
    planted = _normalised(dict(truth.strengths))
    got = fitted.strengths() if "luce" in model else {}
    errors = {s: got[s] - planted[s] for s in planted} if got else {}
    out = {
        "model": model, "arrangement": arrangement, "items": items,
        "repeats": repeats, "draws": data.n_draws,
        "planted": planted, "recovered": got,
        "max_abs_error": max((abs(e) for e in errors.values()), default=None),
        "converged": fitted.converged,
        "planted_later": truth.later,
    }
    if "later" in fitted.coefficients:
        out["recovered_later"] = fitted.coefficients["later"]
        out["later_error"] = fitted.coefficients["later"] - truth.later
    return out


def confounded(truth: LogitTruth, compositions: Iterable[Sequence[str]], *,
               items: int = 200, repeats: int = 3,
               seed: int = 20260915) -> dict[str, Any]:
    """What a sorted arrangement does to a strength, measured rather than warned about.
    Plants a real position effect and NO source effect. Balanced returns flat strengths,
    which is the truth; sorted returns an ordered ladder, which is not, and nothing in
    the fit says so."""
    out = {}
    for arrangement in ("balanced", "sorted"):
        got = recover(truth, compositions, model="luce", items=items,
                      repeats=repeats, arrangement=arrangement, seed=seed)
        spread = (max(got["recovered"].values()) - min(got["recovered"].values())
                  if got["recovered"] else None)
        out[arrangement] = {"recovered": got["recovered"], "spread": spread,
                            "max_abs_error": got["max_abs_error"]}
    out["planted_strength_spread"] = (
        max(_normalised(dict(truth.strengths)).values())
        - min(_normalised(dict(truth.strengths)).values()))
    out["planted_later"] = truth.later
    out["verdict"] = (
        "a sorted arrangement turns a pure position effect into a strength "
        "ordering that is not there"
        if (out["sorted"]["spread"] or 0) > 3 * (out["balanced"]["spread"] or 1e-9)
        else "the two arrangements agree on this truth")
    return out
