"""The estimators: one conditional logit with several feature maps, plus a cross-check.
uniform, position, luce, luce_position, luce_position_size and the context models share
one numerical routine; saturated fits anything and extrapolates to nothing; the normal-error
families live in `families`. `predict` may return None, meaning "I cannot predict this set"."""

from __future__ import annotations

import collections
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

from .choice import Choice, Dataset, canonical

ABSTAIN: None = None
OUTSIDE = "__none__"        # the pseudo-option standing for "no option won"

# The per-draw penalties the context models choose among, and the folds they choose with.
CONTEXT_PENALTIES = (1e-5, 1e-4, 1e-3, 1e-2, 1e-1, 1.0)
CONTEXT_FOLDS = 5


class FitError(ValueError):
    """The data cannot identify this model, and a number would be a guess."""


# --- Features ---


@dataclass(frozen=True)
class Design:
    """A feature map: what each option in a choice looks like to the model.
    `penalised` names the parameters a ridge shrinks; None means all of them."""
    name: str
    build: Callable[[Choice, Sequence[str]], "list[list[float]]"]
    names: Callable[[Sequence[str]], "list[str]"]
    needs_position: bool = False
    penalised: Optional[Callable[[str], bool]] = None


def _order_rank(choice: Choice) -> Optional[dict[str, float]]:
    """Where each option sat, as 0 for the earliest and 1 for the latest.
    One parameter for the whole position effect; for a pair it is exactly "did the later
    one win". Returns None when any competing option has no recorded slot -- a missing
    position is not position zero."""
    positions = [o.position for o in choice.options]
    if any(p is None for p in positions):
        return None
    order = sorted(choice.options, key=lambda o: (o.position, o.option_id))
    span = len(order) - 1
    if span <= 0:
        return None
    ranks: dict[str, float] = {}
    for i, o in enumerate(order):
        ranks[o.option_id] = i / span
    return ranks


def _uniform_build(choice, sources):
    return [[] for _ in choice.options]


def _luce_build(choice, sources):
    index = {s: i for i, s in enumerate(sources[1:])}      # sources[0] is reference
    rows = []
    for o in choice.options:
        row = [0.0] * len(index)
        if o.source in index:
            row[index[o.source]] = 1.0
        rows.append(row)
    return rows


def _position_build(choice, sources):
    ranks = _order_rank(choice)
    if ranks is None:
        return None
    return [[ranks[o.option_id]] for o in choice.options]


def _luce_position_build(choice, sources):
    a = _luce_build(choice, sources)
    b = _position_build(choice, sources)
    if b is None:
        return None
    return [x + y for x, y in zip(a, b)]


def _luce_position_size_build(choice, sources):
    """`luce_position`, plus a position effect that grows with the set size.
    The extra feature is rank * (size - 2), identically zero on pairs, so pairs-only data
    leaves the information matrix singular and `solve` refuses it by name. The published
    result, made mechanical."""
    base = _luce_position_build(choice, sources)
    if base is None:
        return None
    ranks = _order_rank(choice)
    extra = len(choice.options) - 2
    return [row + [ranks[o.option_id] * extra]
            for row, o in zip(base, choice.options)]


def _context_pairs(sources: Sequence[str]) -> list[tuple[str, str]]:
    """Every (z, a) with z != a: the pull z exerts on a when both compete."""
    return [(z, a) for a in sources for z in sources if z != a]


def _with_context(base, choice, sources):
    """Append the context columns (Seshadri et al. 2019): an option's utility gains the pull of
    every other source present. On a pair only a pull's difference is seen; a triple shows more."""
    if base is None:
        return None
    present = {o.source for o in choice.options}
    pairs = _context_pairs(sources)
    return [row + [1.0 if a == o.source and z in present else 0.0 for z, a in pairs]
            for row, o in zip(base, choice.options)]


def _context_names(sources: Sequence[str]) -> list[str]:
    return [f"context[{z} on {a}]" for z, a in _context_pairs(sources)]


def _is_context(name: str) -> bool:
    return name.startswith("context[")


DESIGNS: dict[str, Design] = {
    "uniform": Design("uniform", _uniform_build, lambda s: []),
    "luce": Design("luce", _luce_build, lambda s: [f"strength[{x}]" for x in s[1:]]),
    "position": Design("position", _position_build, lambda s: ["later"],
                       needs_position=True),
    "luce_position": Design(
        "luce_position", _luce_position_build,
        lambda s: [f"strength[{x}]" for x in s[1:]] + ["later"],
        needs_position=True),
    "luce_position_size": Design(
        "luce_position_size", _luce_position_size_build,
        lambda s: [f"strength[{x}]" for x in s[1:]] + ["later", "later_x_size"],
        needs_position=True),
    "context": Design(
        "context", lambda c, s: _with_context(_luce_build(c, s), c, s),
        lambda s: [f"strength[{x}]" for x in s[1:]] + _context_names(s),
        penalised=_is_context),
    "context_position": Design(
        "context_position", lambda c, s: _with_context(_luce_position_build(c, s), c, s),
        lambda s: [f"strength[{x}]" for x in s[1:]] + ["later"] + _context_names(s),
        needs_position=True, penalised=_is_context),
}


def _has_strengths(names: Sequence[str]) -> bool:
    return any(n.startswith("strength[") for n in names)


# --- Small dense linear algebra, because eight parameters do not need a library ---


def solve(matrix: Sequence[Sequence[float]], rhs: Sequence[float]) -> list[float]:
    """Solve `matrix x = rhs` by Gaussian elimination with partial pivoting."""
    n = len(rhs)
    a = [list(row) + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-14:
            raise FitError(
                "the information matrix is singular: some parameter is not "
                "identified by this data. A source that never appears, a feature "
                "that never varies, or two features that are the same column.")
        a[col], a[pivot] = a[pivot], a[col]
        for r in range(n):
            if r == col:
                continue
            factor = a[r][col] / a[col][col]
            if factor:
                for c in range(col, n + 1):
                    a[r][c] -= factor * a[col][c]
    return [a[i][n] / a[i][i] for i in range(n)]


def logsumexp(values: Sequence[float]) -> float:
    top = max(values)
    if top == float("-inf"):
        return top
    return top + math.log(sum(math.exp(v - top) for v in values))


# --- The fitted object ---


@dataclass
class Fitted:
    """What a fit produced, and everything needed to doubt it."""
    name: str
    sources: tuple[str, ...]
    coefficients: dict[str, float] = field(default_factory=dict)
    models_abstention: bool = False
    converged: bool = True
    iterations: int = 0
    loglik: float = 0.0
    n_parameters: int = 0
    n_draws: int = 0
    notes: list[str] = field(default_factory=list)
    _design: Optional[Design] = None
    _beta: tuple[float, ...] = ()
    _table: Mapping[tuple[str, ...], Mapping[str, float]] = field(default_factory=dict)

    # ------------------------------------------------------------ prediction

    def predict(self, choice: Choice) -> Optional[dict[Optional[str], float]]:
        """A distribution over this choice's options, and None if it abstains.

        Returns None -- the whole thing -- when this model has nothing to say
        about this choice."""
        if self._design is None:
            return self._predict_saturated(choice)
        rows = self._design.build(choice, self.sources)
        if rows is None:
            return None
        unknown = [o.source for o in choice.options if o.source not in self.sources]
        if unknown:
            return None
        utilities = [sum(b * x for b, x in zip(self._beta, row)) for row in rows]
        keys: list[Optional[str]] = [o.option_id for o in choice.options]
        if self.models_abstention:
            utilities.append(self.coefficients.get("abstain", 0.0))
            keys.append(ABSTAIN)
        total = logsumexp(utilities)
        return {k: math.exp(u - total) for k, u in zip(keys, utilities)}

    def _predict_saturated(self, choice: Choice) -> Optional[dict[Optional[str], float]]:
        cell = self._table.get(choice.sources)
        if cell is None:
            return None
        by_source = {o.source: o.option_id for o in choice.options}
        out: dict[Optional[str], float] = {}
        for source, p in cell.items():
            if source == OUTSIDE:
                out[ABSTAIN] = p
            elif source in by_source:
                out[by_source[source]] = p
            else:
                return None
        return out

    # --------------------------------------------------------------- reading

    def strengths(self) -> dict[str, float]:
        """exp(coefficient) per source, normalised to sum to one.
        The only scale a Plackett-Luce strength is defined on: they are fixed up to a positive
        multiple, so a single number is meaningless and a ratio is not."""
        raw = {s: math.exp(self.coefficients.get(f"strength[{s}]", 0.0))
               for s in self.sources}
        total = sum(raw.values())
        return {s: v / total for s, v in sorted(raw.items())}

    def as_dict(self) -> dict[str, Any]:
        out = {
            "model": self.name, "sources": list(self.sources),
            "coefficients": dict(sorted(self.coefficients.items())),
            "models_abstention": self.models_abstention,
            "converged": self.converged, "iterations": self.iterations,
            "loglik": self.loglik, "n_parameters": self.n_parameters,
            "n_draws": self.n_draws, "notes": list(self.notes),
        }
        if self._design is not None and _has_strengths(self._design.names(self.sources)):
            out["strengths"] = self.strengths()
        return out


# --- Fitting ---


def _rows_for(dataset: Dataset, design: Design, sources: Sequence[str],
              abstention: bool) -> tuple[list, int]:
    """Every choice as (features per option, index of what happened, weight)."""
    prepared = []
    skipped = 0
    n_params = len(design.names(sources))
    for c in dataset:
        rows = design.build(c, sources)
        if rows is None:
            skipped += c.weight
            continue
        rows = [list(r) for r in rows]
        keys: list[Optional[str]] = [o.option_id for o in c.options]
        if abstention:
            rows = [r + [0.0] for r in rows]
            rows.append([0.0] * n_params + [1.0])
            keys.append(ABSTAIN)
        elif c.won is None:
            skipped += c.weight
            continue
        try:
            outcome = keys.index(c.won)
        except ValueError:
            skipped += c.weight
            continue
        prepared.append((rows, outcome, c.weight))
    return prepared, skipped


def _loglik(prepared, beta) -> float:
    total = 0.0
    for rows, outcome, weight in prepared:
        utilities = [sum(b * x for b, x in zip(beta, row)) for row in rows]
        total += weight * (utilities[outcome] - logsumexp(utilities))
    return total


def _refuse_unfittable(dataset: Dataset, *, per_source: bool, shrunk: bool) -> None:
    """Raise when the data cannot identify this model, rather than return a guess.
    `per_source`: the model has a strength per source; `shrunk`: a ridge holds them finite."""
    if not dataset.connected():
        raise FitError(
            "the comparison graph over sources is not connected, so two groups of "
            "sources have no measurement linking them and their strengths slide "
            "apart freely. Any difference between them would be whatever the "
            "optimiser stopped at.")
    if not per_source or shrunk:
        return
    wins, seen = dataset.wins_by_source(), dataset.appearances_by_source()
    dead = [s for s in dataset.sources if seen.get(s, 0) and not wins.get(s, 0)]
    if dead:
        raise FitError(
            f"{', '.join(dead)} competed and never won, so the likelihood is "
            f"maximised at a strength of zero and no finite number is the answer. "
            f"Give ridge=... to get a finite one on purpose, and say so in the report.")


def fit(dataset: Dataset, model: str = "luce", *, ridge: float = 0.0,
        max_iter: int = 100, tol: float = 1e-10,
        step_tol: float = 1e-12) -> Fitted:
    """Fit one of the conditional-logit models by Newton with step halving.
    `saturated` and the normal-error families are routed to their own fitters; a context
    model with no `ridge` chooses its penalty by cross-validation over items."""
    from . import families, mixed

    if model == "saturated":
        return fit_saturated(dataset)
    if model in families.FAMILIES or model in mixed.MIXED:
        if ridge:
            raise FitError(f"{model} takes no ridge")
        return (families if model in families.FAMILIES else mixed).fit(dataset, model)
    if model not in DESIGNS:
        raise FitError(f"no model called {model!r}; have {sorted(DESIGNS)}, "
                       f"{', '.join(families.FAMILIES + mixed.MIXED)} and 'saturated'")
    design = DESIGNS[model]
    if design.penalised is not None and not ridge:
        return _fit_context(dataset, model)
    sources = dataset.sources
    if len(sources) < 2:
        raise FitError("fewer than two sources: there is nothing to compare")
    abstention = dataset.abstentions() > 0
    names = design.names(sources) + (["abstain"] if abstention else [])
    prepared, skipped = _rows_for(dataset, design, sources, abstention)
    if not prepared:
        raise FitError(
            f"{model}: no usable choice in {len(dataset)} rows"
            + (" -- every choice is missing a recorded position"
               if design.needs_position else ""))

    # Which parameters the ridge shrinks: every one, unless the design names some.
    mask = ([1.0 if design.penalised(name) else 0.0 for name in names]
            if design.penalised is not None else None)

    def penalty(b: Sequence[float]) -> float:
        if mask is None:
            return ridge * sum(x * x for x in b)
        return ridge * sum(m * x * x for m, x in zip(mask, b))

    strengths_shrunk = bool(ridge) and (mask is None or any(
        m for m, name in zip(mask, names) if name.startswith("strength[")))
    _refuse_unfittable(dataset, per_source=_has_strengths(names), shrunk=strengths_shrunk)
    notes: list[str] = []
    if skipped:
        notes.append(f"{skipped} draws unusable for this model and left out")
    total_weight = sum(w for _, _, w in prepared)
    n = len(names)
    beta = [0.0] * n
    current = _loglik(prepared, beta) - penalty(beta)
    # A model with no parameters is already fitted; `uniform` is that model.
    converged, iterations = n == 0, 0
    for iterations in range(1, max_iter + 1 if n else 1):
        gradient = [0.0] * n
        hessian = [[0.0] * n for _ in range(n)]
        for rows, outcome, weight in prepared:
            utilities = [sum(b * x for b, x in zip(beta, row)) for row in rows]
            total = logsumexp(utilities)
            probs = [math.exp(u - total) for u in utilities]
            mean = [sum(p * row[k] for p, row in zip(probs, rows)) for k in range(n)]
            for k in range(n):
                gradient[k] += weight * (rows[outcome][k] - mean[k])
            for k in range(n):
                for j in range(k, n):
                    second = sum(p * row[k] * row[j] for p, row in zip(probs, rows))
                    value = weight * (second - mean[k] * mean[j])
                    hessian[k][j] += value
                    if j != k:
                        hessian[j][k] += value
        for k in range(n):
            shrink = mask[k] if mask is not None else 1.0
            gradient[k] -= 2 * ridge * beta[k] * shrink
            hessian[k][k] += 2 * ridge * shrink
        # PER DRAW, NOT SUMMED: at ten thousand draws float64 cannot get a summed gradient below 1e-10 however well converged the fit is.
        if max(abs(g) for g in gradient) < tol * max(1.0, float(total_weight)):
            converged = True
            break
        # `hessian` is the NEGATIVE second derivative, positive definite because the likelihood is concave, so this is always an ascent direction.
        step = solve(hessian, gradient)
        scale, improved = 1.0, False
        while scale >= 1e-12:
            trial = [b + scale * d for b, d in zip(beta, step)]
            value = _loglik(prepared, trial) - penalty(trial)
            if value >= current - 1e-15:
                beta, current, improved = trial, value, True
                break
            scale /= 2.0
        if not improved:
            # Stationary to the precision the arithmetic has left, which is not a gradient of zero and is recorded as its own thing.
            notes.append("Newton stalled: halving the step stopped improving the "
                         "likelihood before the gradient reached zero")
            converged = True
            break
        # The other honest stopping rule: Newton is quadratic near the optimum, so the parameters stop moving a step before the gradient test.
        if max(abs(scale * d) for d in step) < step_tol:
            converged = True
            break
    if not converged and iterations >= max_iter:
        notes.append(f"did not converge in {max_iter} iterations")

    coefficients = dict(zip(names, beta))
    if _has_strengths(names):
        # The reference source, written down rather than inferred from which key is missing.
        coefficients.setdefault(f"strength[{sources[0]}]", 0.0)
    return Fitted(
        name=model, sources=sources, coefficients=coefficients,
        models_abstention=abstention, converged=converged, iterations=iterations,
        loglik=_loglik(prepared, beta), n_parameters=n,
        n_draws=sum(w for _, _, w in prepared), notes=notes,
        _design=design, _beta=tuple(beta))


def _fit_context(dataset: Dataset, model: str, *, seed: int = 20260915) -> Fitted:
    """A context model, its penalty chosen by K-fold cross-validation over ITEMS.
    The pulls are shrunk and the strengths are not, so the largest penalty is Plackett-Luce
    and the data decide how far to move from it. Fitted on `canonical` data, for speed only."""
    items = sorted(dataset.items)
    if len(items) < CONTEXT_FOLDS:
        raise FitError(f"{model}: {len(items)} items cannot make {CONTEXT_FOLDS} folds")
    random.Random(seed).shuffle(items)
    folds = [set(items[k::CONTEXT_FOLDS]) for k in range(CONTEXT_FOLDS)]
    scores: dict[float, float] = {}
    for per_draw in CONTEXT_PENALTIES:
        total = 0.0
        try:
            for fold in folds:
                train = canonical(dataset.filter(lambda c: c.item not in fold))
                fitted = fit(train, model, ridge=per_draw * train.n_draws)
                for c in canonical(dataset.filter(lambda c: c.item in fold)):
                    predicted = fitted.predict(c)
                    if predicted is None:
                        raise FitError(f"{model} declined a held-out choice")
                    total += c.weight * math.log(max(predicted.get(c.won, 0.0), 1e-300))
        except FitError:
            continue
        scores[per_draw] = total
    if not scores:
        raise FitError(f"{model}: no penalty in {list(CONTEXT_PENALTIES)} could be fitted "
                       f"on every fold")
    # A tie goes to the larger penalty, the model closer to Plackett-Luce.
    best = max(scores, key=lambda p: (scores[p], p))
    fitted = fit(canonical(dataset), model, ridge=best * dataset.n_draws)
    fitted.notes.append(f"context terms shrunk by {best:g} per draw, chosen by "
                        f"{CONTEXT_FOLDS}-fold cross-validation over items")
    return fitted


def fit_saturated(dataset: Dataset) -> Fitted:
    """One free distribution per composition, straight off the counts.
    Fits any data and extrapolates to nothing -- review #9 asked for it by name: the
    comparison that means something is held-out whole compositions, where it must decline."""
    counts: dict[tuple[str, ...], collections.Counter] = collections.defaultdict(
        collections.Counter)
    for c in dataset:
        winner = c.winning_source()
        counts[c.sources][winner if winner is not None else OUTSIDE] += c.weight
    table = {}
    for comp, cell in counts.items():
        total = sum(cell.values())
        table[comp] = {k: v / total for k, v in cell.items()}
    draws = sum(sum(c.values()) for c in counts.values())
    return Fitted(
        name="saturated", sources=dataset.sources,
        models_abstention=dataset.abstentions() > 0,
        converged=True, iterations=0,
        loglik=sum(v * math.log(table[comp][k])
                   for comp, cell in counts.items()
                   for k, v in cell.items() if table[comp][k] > 0),
        n_parameters=sum(len(c) - 1 for c in counts.values()),
        n_draws=draws,
        notes=["predicts only the compositions it was fitted on, by construction"],
        _table=table)


# --- The second algorithm ---


def fit_mm(dataset: Dataset, *, max_iter: int = 10_000,
           tol: float = 1e-12) -> dict[str, float]:
    """Plackett-Luce strengths by minorize-maximize (Hunter 2004).
    Exists ONLY to disagree with `fit`: there is no reference implementation to check a
    fitter against, so a second one is written that shares no line of code. Features and
    abstentions are out of scope so it cannot grow the bug it exists to find."""
    usable = [c for c in dataset if c.won is not None]
    if not usable:
        raise FitError("no decided choice to fit")
    sources = dataset.sources
    wins: collections.Counter = collections.Counter()
    for c in usable:
        wins[c.winning_source()] += c.weight
    dead = [s for s in sources if not wins.get(s)]
    if dead:
        raise FitError(f"{', '.join(dead)} never won: no finite strength")

    w = {s: 1.0 for s in sources}
    for _ in range(max_iter):
        denominator: dict[str, float] = {s: 0.0 for s in sources}
        for c in usable:
            total = sum(w[o.source] for o in c.options)
            for o in c.options:
                denominator[o.source] += c.weight / total
        updated = {s: wins[s] / denominator[s] for s in sources}
        scale = sum(updated.values())
        updated = {s: v / scale for s, v in updated.items()}
        shift = max(abs(updated[s] - w[s]) for s in sources)
        w = updated
        if shift < tol:
            break
    return dict(sorted(w.items()))
