"""A world: a distribution over rankings, and the choice it induces on any subset.
One object answers every composition, so the sizes cannot disagree with each other.
`WORLDS` holds the exact pairwise-insufficiency counterexample (2510.15839) and
`verify()` re-derives it.
"""

from __future__ import annotations

import itertools
from fractions import Fraction
from typing import Any, Mapping, Optional, Sequence, Union

Number = Union[Fraction, float, int]


class WorldError(ValueError):
    """A distribution that is not one."""


class RankingWorld:
    """A distribution over rankings of `alternatives`, exact or floating.
    `probs` maps a ranking, best first, to its probability; unnamed rankings are zero."""

    def __init__(self, alternatives: Sequence[str],
                 probs: Mapping[Sequence[str], Number], *, name: str = ""):
        self.alternatives = tuple(alternatives)
        self.name = name
        if len(set(self.alternatives)) != len(self.alternatives):
            raise WorldError(f"repeated alternative in {self.alternatives}")
        table: dict[tuple[str, ...], Number] = {}
        for ranking, p in probs.items():
            key = tuple(ranking)
            if sorted(key) != sorted(self.alternatives):
                raise WorldError(
                    f"{key} is not a ranking of {self.alternatives}: a world has "
                    f"to answer for every alternative or it cannot be restricted")
            if p < 0:
                raise WorldError(f"{key} has probability {p}")
            table[key] = table.get(key, 0) + p
        total = sum(table.values())
        if not _close(total, 1):
            raise WorldError(f"probabilities sum to {total}, not 1")
        self.probs = table

    def __repr__(self) -> str:
        return (f"RankingWorld({self.name or 'unnamed'}, "
                f"{len(self.alternatives)} alternatives, "
                f"{len(self.probs)} rankings with weight)")

    # ---------------------------------------------------------------- reading

    def choice_probs(self, subset: Sequence[str]) -> dict[str, Number]:
        """P(x wins | only `subset` competes), for every x in the subset.
        Restrict each ranking to the subset; whichever survivor comes first wins. That is
        what makes one world answer for every composition at once."""
        keep = list(subset)
        unknown = [s for s in keep if s not in self.alternatives]
        if unknown:
            raise WorldError(f"{unknown} not in this world")
        if len(set(keep)) != len(keep):
            raise WorldError(f"repeated alternative in subset {keep}")
        if len(keep) < 1:
            raise WorldError("an empty subset has no winner")
        wanted = set(keep)
        out: dict[str, Number] = {s: Fraction(0) if self.exact else 0.0 for s in keep}
        for ranking, p in self.probs.items():
            for a in ranking:
                if a in wanted:
                    out[a] = out[a] + p
                    break
        return out

    def pairwise(self) -> dict[tuple[str, str], Number]:
        """P(a beats b) for every ordered pair a < b, by name."""
        out = {}
        for a, b in itertools.combinations(sorted(self.alternatives), 2):
            out[(a, b)] = self.choice_probs([a, b])[a]
        return out

    def top_choice(self, subset: Optional[Sequence[str]] = None) -> dict[str, Number]:
        return self.choice_probs(subset if subset is not None else self.alternatives)

    @property
    def exact(self) -> bool:
        return all(isinstance(p, Fraction) for p in self.probs.values())

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "alternatives": list(self.alternatives),
                "rankings": {" ".join(k): str(v) for k, v in
                             sorted(self.probs.items())}}


def _close(a: Number, b: Number, tol: float = 1e-12) -> bool:
    if isinstance(a, Fraction) and isinstance(b, (Fraction, int)):
        return a == b
    return abs(float(a) - float(b)) <= tol


# --- Worlds that are a particular model, so an estimator can be asked to find it ---


def luce_world(strengths: Mapping[str, float], *, name: str = "luce") -> RankingWorld:
    """The ranking world a Plackett-Luce model with these strengths generates.
    Its choice probability on ANY subset is w_i / sum over it -- what lets Plackett-Luce
    extrapolate from pairs, and what the counterexample worlds lack."""
    names = sorted(strengths)
    if len(names) < 2:
        raise WorldError("a world needs at least two alternatives")
    for n in names:
        if strengths[n] <= 0:
            raise WorldError(f"strength {strengths[n]} for {n}: must be positive")

    probs: dict[tuple[str, ...], float] = {}
    for ranking in itertools.permutations(names):
        p = 1.0
        remaining = list(ranking)
        while len(remaining) > 1:
            total = sum(strengths[r] for r in remaining)
            p *= strengths[remaining[0]] / total
            remaining.pop(0)
        probs[ranking] = p
    return RankingWorld(names, probs, name=name)


# --- The counterexample ---

F = Fraction

# Two worlds agreeing on every pair and disagreeing about who wins the triple. Derived, not guessed: `verify()` re-derives it.
WORLDS: dict[str, RankingWorld] = {
    "a_wins_the_triple": RankingWorld(
        ("A", "B", "C"),
        {("A", "B", "C"): F(1, 2), ("B", "A", "C"): F(1, 5), ("C", "B", "A"): F(3, 10)},
        name="a_wins_the_triple"),
    "b_wins_the_triple": RankingWorld(
        ("A", "B", "C"),
        {("A", "B", "C"): F(1, 5), ("B", "A", "C"): F(1, 2), ("C", "A", "B"): F(3, 10)},
        name="b_wins_the_triple"),
}


def verify() -> dict[str, Any]:
    """Re-derive the counterexample from the worlds themselves.
    Run as a test, so a world edited without its prose fails rather than quietly
    making this package's central claim untrue."""
    a, b = WORLDS["a_wins_the_triple"], WORLDS["b_wins_the_triple"]
    pa, pb = a.pairwise(), b.pairwise()
    ta, tb = a.top_choice(), b.top_choice()
    winner_a = max(sorted(ta), key=lambda k: ta[k])
    winner_b = max(sorted(tb), key=lambda k: tb[k])
    return {
        "exact": a.exact and b.exact,
        "pairwise_identical": pa == pb,
        "pairwise": {f"{x}>{y}": str(v) for (x, y), v in sorted(pa.items())},
        "top_choice": {a.name: {k: str(v) for k, v in sorted(ta.items())},
                       b.name: {k: str(v) for k, v in sorted(tb.items())}},
        "triple_winner": {a.name: winner_a, b.name: winner_b},
        "winner_differs": winner_a != winner_b,
        "total_variation_on_the_triple": str(
            sum(abs(ta[k] - tb[k]) for k in ta) / 2),
    }


def counterexample_holds() -> bool:
    """The one-line form of `verify`, for a gate to read."""
    v = verify()
    return bool(v["exact"] and v["pairwise_identical"] and v["winner_differs"])


def subsets(alternatives: Sequence[str], size: int) -> list[tuple[str, ...]]:
    return [tuple(c) for c in itertools.combinations(sorted(alternatives), size)]


