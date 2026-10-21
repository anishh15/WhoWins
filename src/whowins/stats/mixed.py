"""Random effects: a conditional logit whose items and groups differ at random.
utility = strengths (+ later x rank) + a[item, option] + sum of g[level, source] over grouping
factors. a is an item's own taste for each option, the content term the study's method says balancing
cannot cancel; a factor is the item's family in one run, or the model across runs."""

from __future__ import annotations

import collections
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

from .choice import Choice, Dataset
from .models import DESIGNS, FitError, Fitted, _refuse_unfittable, logsumexp, solve

MIXED = ("mixed", "mixed_position")
DRAWS = 200         # Monte Carlo draws for a prediction that integrates over an effect
SEED = 20260929
FLOOR = 1e-3        # a standard deviation this small is an effect that is not there

Factor = tuple[str, Callable[[str], str]]
"""(name, item -> level): a random shift of every source's strength, one per level."""


def family_of(item: str) -> str:
    """A scenario's family from its id: `fmt-0012` is `fmt`."""
    return item.split("-", 1)[0]


# --- Small dense algebra: an item block is five options at most ---


def _inverse(m: Sequence[Sequence[float]]) -> list[list[float]]:
    n = len(m)
    cols = [solve(m, [1.0 if i == j else 0.0 for i in range(n)]) for j in range(n)]
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def _logdet(m: Sequence[Sequence[float]]) -> float:
    """log |m| for a positive definite m, by Cholesky."""
    n = len(m)
    low = [[0.0] * n for _ in range(n)]
    total = 0.0
    for i in range(n):
        for j in range(i + 1):
            s = m[i][j] - sum(low[i][t] * low[j][t] for t in range(j))
            if i == j:
                if s <= 0.0:
                    raise FitError("a random-effect information matrix is not positive definite")
                low[i][i] = math.sqrt(s)
                total += 2.0 * math.log(low[i][i])
            else:
                low[i][j] = s / low[j][j]
    return total


# --- The problem, laid out once ---


@dataclass
class _Row:
    options: list[tuple[list[tuple[int, float]], int]]   # (global columns, item column or -1)
    won: int
    weight: float


@dataclass
class _Layout:
    names: list[str]                    # strengths (+ later), then each factor's shifts
    n_fixed: int
    factors: list[tuple[str, list[str], list[int]]]    # (name, levels, global indices)
    sources: tuple[str, ...]
    blocks: list[list[_Row]]
    block_items: list[str]
    block_options: list[list[str]]


def _layout(data: Dataset, position: bool, factors: Sequence[Factor], items: bool) -> _Layout:
    design = DESIGNS["luce_position" if position else "luce"]
    sources = data.sources
    names = list(design.names(sources))
    n_fixed = len(names)
    s_index = {s: i for i, s in enumerate(sources)}
    laid: list[tuple[str, list[str], list[int]]] = []
    for name, level_of in factors:
        levels = sorted({level_of(c.item) for c in data})
        start = len(names)
        names += [f"{name}[{lv},{s}]" for lv in levels for s in sources]
        laid.append((name, levels, list(range(start, len(names)))))
    level_index = [{lv: i for i, lv in enumerate(levels)} for _, levels, _ in laid]
    rows_by_item: dict[str, dict[tuple, float]] = collections.defaultdict(
        lambda: collections.defaultdict(float))
    kept: dict[tuple, Choice] = {}
    for c in data:
        key = (tuple((o.option_id, o.source, o.position) for o in c.options), c.won)
        rows_by_item[c.item][key] += c.weight
        kept[(c.item, key)] = c
    blocks, block_items, block_options = [], [], []
    for item in sorted(rows_by_item):
        options = sorted({o.option_id for key in rows_by_item[item]
                          for o in kept[(item, key)].options}) if items else []
        col = {o: i for i, o in enumerate(options)}
        offsets = [span[0] + index[level_of(item)] * len(sources)
                   for (_, _, span), index, (_, level_of) in zip(laid, level_index, factors)]
        rows = []
        for key, weight in sorted(rows_by_item[item].items(), key=lambda kv: repr(kv[0])):
            choice = kept[(item, key)]
            feats = design.build(choice, sources)
            if feats is None:
                continue
            opts = []
            for o, x in zip(choice.options, feats):
                cols = [(j, v) for j, v in enumerate(x) if v]
                cols += [(off + s_index[o.source], 1.0) for off in offsets]
                opts.append((cols, col.get(o.option_id, -1)))
            won = [o.option_id for o in choice.options].index(choice.won)
            rows.append(_Row(opts, won, weight))
        if rows:
            blocks.append(rows)
            block_items.append(item)
            block_options.append(options)
    return _Layout(names, n_fixed, laid, sources, blocks, block_items, block_options)


# --- One pass over every block, and the joint mode ---


def _pass(lay: _Layout, beta: list[float], a: list[list[float]], prec_a: float,
          prec_g: Sequence[float]) -> dict[str, Any]:
    """Penalised log-likelihood, gradient and the blocks of the negative Hessian at (beta, a).
    `prec_g` is the prior precision of each global parameter, zero for the fixed ones."""
    n = len(beta)
    gg = [0.0] * n
    hgg = [[0.0] * n for _ in range(n)]
    blocks = []
    loglik = 0.0
    for rows, ab in zip(lay.blocks, a):
        k = len(ab)
        gb = [0.0] * k
        hbb = [[0.0] * k for _ in range(k)]
        hgb: dict[int, list[float]] = collections.defaultdict(lambda: [0.0] * k)
        for row in rows:
            u = [sum(beta[j] * v for j, v in cols) + (ab[col] if col >= 0 else 0.0)
                 for cols, col in row.options]
            top = logsumexp(u)
            p = [math.exp(x - top) for x in u]
            w = row.weight
            loglik += w * (u[row.won] - top)
            mean_g: dict[int, float] = collections.defaultdict(float)
            mean_b = [0.0] * k
            for (cols, col), pj in zip(row.options, p):
                for j, v in cols:
                    mean_g[j] += pj * v
                if col >= 0:
                    mean_b[col] += pj
            cols_won, col_won = row.options[row.won]
            for j, v in cols_won:
                gg[j] += w * v
            if col_won >= 0:
                gb[col_won] += w
            for j, v in mean_g.items():
                gg[j] -= w * v
            for c in range(k):
                gb[c] -= w * mean_b[c]
            for (cols, col), pj in zip(row.options, p):
                for j, v in cols:
                    for jj, vv in cols:
                        hgg[j][jj] += w * pj * v * vv
                    if col >= 0:
                        hgb[j][col] += w * pj * v
                if col >= 0:
                    hbb[col][col] += w * pj
            for j, v in mean_g.items():
                for jj, vv in mean_g.items():
                    hgg[j][jj] -= w * v * vv
                for c in range(k):
                    hgb[j][c] -= w * v * mean_b[c]
            for c in range(k):
                for cc in range(k):
                    hbb[c][cc] -= w * mean_b[c] * mean_b[cc]
        for c in range(k):
            gb[c] -= prec_a * ab[c]
            hbb[c][c] += prec_a
        blocks.append((gb, hbb, dict(hgb)))
    for j in range(n):
        gg[j] -= prec_g[j] * beta[j]
        hgg[j][j] += prec_g[j]
    penalty = 0.5 * prec_a * sum(x * x for ab in a for x in ab) + \
        0.5 * sum(pj * b * b for pj, b in zip(prec_g, beta))
    return {"loglik": loglik, "objective": loglik - penalty, "gg": gg, "hgg": hgg,
            "blocks": blocks}


def _schur(state: Mapping[str, Any]) -> tuple[list[list[float]], list[float], list]:
    """The global system with every item block eliminated, and each block's inverse."""
    s = [row[:] for row in state["hgg"]]
    rhs = list(state["gg"])
    inverses = []
    for gb, hbb, hgb in state["blocks"]:
        inv = _inverse(hbb)
        inverses.append(inv)
        k = len(gb)
        proj = {j: [sum(row[c] * inv[c][cc] for c in range(k)) for cc in range(k)]
                for j, row in hgb.items()}
        for j, pj in proj.items():
            rhs[j] -= sum(pj[c] * gb[c] for c in range(k))
            for jj, row in hgb.items():
                s[j][jj] -= sum(pj[c] * row[c] for c in range(k))
    return s, rhs, inverses


def _mode(lay: _Layout, beta: list[float], a: list[list[float]], prec_a: float,
          prec_g: Sequence[float], *, max_iter: int = 50, tol: float = 1e-8) -> tuple:
    """The joint mode of the penalised likelihood, by block Newton with step halving."""
    state = _pass(lay, beta, a, prec_a, prec_g)
    for _ in range(max_iter):
        s, rhs, inverses = _schur(state)
        step_g = solve(s, rhs)
        steps_b = []
        for (gb, hbb, hgb), inv in zip(state["blocks"], inverses):
            k = len(gb)
            r = [gb[c] - sum(row[c] * step_g[j] for j, row in hgb.items()) for c in range(k)]
            steps_b.append([sum(inv[c][cc] * r[cc] for cc in range(k)) for c in range(k)])
        scale = 1.0
        while scale > 1e-10:
            trial_b = [bj + scale * d for bj, d in zip(beta, step_g)]
            trial_a = [[x + scale * d for x, d in zip(ab, sb)] for ab, sb in zip(a, steps_b)]
            trial = _pass(lay, trial_b, trial_a, prec_a, prec_g)
            if trial["objective"] >= state["objective"] - 1e-12:
                break
            scale /= 2.0
        else:
            return beta, a, state, False
        moved = max([abs(scale * d) for d in step_g] +
                    [abs(scale * d) for sb in steps_b for d in sb] + [0.0])
        beta, a, state = trial_b, trial_a, trial
        if moved < tol:
            return beta, a, state, True
    return beta, a, state, False


# --- The fitted object ---


@dataclass
class MixedFitted(Fitted):
    """A fitted mixed logit. An item it saw is predicted from that item's own estimated tastes,
    integrating over what is still uncertain; a level it never saw, from the population."""
    sigmas: dict = field(default_factory=dict)
    _layout: Optional[_Layout] = None
    _beta: tuple[float, ...] = ()
    _tastes: dict = field(default_factory=dict, repr=False)
    _levels_of: tuple = ()
    _cache: dict = field(default_factory=dict, repr=False)

    def predict(self, choice: Choice) -> Optional[dict[Optional[str], float]]:
        lay = self._layout
        design = DESIGNS["luce_position" if "position" in self.name else "luce"]
        if any(o.source not in lay.sources for o in choice.options):
            return None
        feats = design.build(choice, lay.sources)
        if feats is None:
            return None
        tastes = self._tastes.get(choice.item, {})
        levels = tuple(level_of(choice.item) for _, level_of in self._levels_of)
        key = (choice.item if tastes else None, levels,
               tuple((o.option_id if tastes else None, o.source, tuple(x))
                     for o, x in zip(choice.options, feats)))
        if key not in self._cache:
            self._cache[key] = self._integrate(choice, feats, levels, tastes)
        return dict(zip((o.option_id for o in choice.options), self._cache[key]))

    def _integrate(self, choice, feats, levels, tastes) -> list[float]:
        """Average the choice probabilities over every effect not pinned by the data."""
        lay = self._layout
        s_index = {s: i for i, s in enumerate(lay.sources)}
        base, spread = [], []
        for o, x in zip(choice.options, feats):
            u = sum(b * v for b, v in zip(self._beta, x))
            unseen = 0.0
            for (name, known, span), level in zip(lay.factors, levels):
                if level in known:
                    u += self._beta[span[known.index(level) * len(lay.sources) + s_index[o.source]]]
                else:
                    unseen += self.sigmas[name] ** 2
            base.append(u)
            spread.append(math.sqrt(unseen))
        rng = random.Random(SEED)
        total = [0.0] * len(base)
        for _ in range(DRAWS):
            u = []
            for o, b, sd_g in zip(choice.options, base, spread):
                mean, sd = tastes.get(o.option_id, (0.0, self.sigmas.get("item", 0.0)))
                u.append(b + mean + sd * rng.gauss(0.0, 1.0) + sd_g * rng.gauss(0.0, 1.0))
            top = logsumexp(u)
            for i, x in enumerate(u):
                total[i] += math.exp(x - top)
        return [t / DRAWS for t in total]

    def strengths(self) -> dict[str, float]:
        raw = {s: math.exp(self.coefficients.get(f"strength[{s}]", 0.0)) for s in self.sources}
        norm = sum(raw.values())
        return {s: v / norm for s, v in sorted(raw.items())}

    def shifts(self) -> dict[str, dict[str, dict[str, float]]]:
        """factor -> level -> source -> its estimated shift of that source's log strength."""
        lay = self._layout
        return {name: {lv: {s: self._beta[span[i * len(lay.sources) + j]]
                            for j, s in enumerate(lay.sources)} for i, lv in enumerate(levels)}
                for name, levels, span in lay.factors}

    def as_dict(self) -> dict[str, Any]:
        return {**super().as_dict(), "strengths": self.strengths(), "sigmas": dict(self.sigmas),
                "shifts": self.shifts(), "items_with_tastes": len(self._tastes)}


# --- Fitting ---


def fit_mixed(dataset: Dataset, *, position: bool, factors: Sequence[Factor] = (),
              items: bool = True, name: str = "mixed", max_rounds: int = 60,
              tol: float = 1e-3) -> MixedFitted:
    """Fit on decided draws. Each variance comes from Schall's fixed point on the Laplace
    marginal: the mean square of its effects plus their posterior variance, the joint mode
    refitted, until none moves by more than `tol` relative or 0.001 absolute. Laplace errs low
    when an effect has few draws behind it, so read a variance as a floor on the truth."""
    if dataset.abstentions():
        raise FitError(f"{name} models which option won when one did: pass decided draws only")
    if len(dataset.sources) < 2:
        raise FitError("fewer than two sources: there is nothing to compare")
    _refuse_unfittable(dataset, per_source=True, shrunk=False)
    lay = _layout(dataset, position, factors, items)
    if not lay.blocks:
        raise FitError(f"{name}: no usable choice -- every one is missing a recorded position")
    beta = [0.0] * len(lay.names)
    a = [[0.0] * len(opts) for opts in lay.block_options]
    sigmas = {n: 0.5 for n, _, _ in lay.factors}
    if items:
        sigmas["item"] = 0.5

    def precisions() -> tuple[float, list[float]]:
        prec_g = [0.0] * len(beta)
        for fname, _, span in lay.factors:
            for j in span:
                prec_g[j] = 1.0 / sigmas[fname] ** 2
        return (1.0 / sigmas["item"] ** 2 if items else 0.0), prec_g

    notes: list[str] = []
    converged = False
    rounds = 0
    for rounds in range(1, max_rounds + 1):
        prec_a, prec_g = precisions()
        beta, a, state, ok = _mode(lay, beta, a, prec_a, prec_g)
        if not ok:
            notes.append("the joint mode stopped improving before it converged")
        s, _, inverses = _schur(state)
        new = {}
        if items:
            n_a = sum(len(ab) for ab in a)
            new["item"] = math.sqrt((sum(x * x for ab in a for x in ab)
                                     + sum(inv[c][c] for inv in inverses for c in range(len(inv))))
                                    / n_a)
        random_idx = [j for _, _, span in lay.factors for j in span]
        if random_idx:
            cov = _inverse([[s[i][j] for j in random_idx] for i in random_idx])
            at = {j: i for i, j in enumerate(random_idx)}
            for fname, _, span in lay.factors:
                new[fname] = math.sqrt(sum(beta[j] ** 2 + cov[at[j]][at[j]] for j in span)
                                       / len(span))
        new = {k: max(v, FLOOR) for k, v in new.items()}
        done = all(abs(new[k] - sigmas[k]) <= max(tol * sigmas[k], 1e-3) for k in new)
        sigmas.update(new)
        if done:
            converged = True
            break
    prec_a, prec_g = precisions()
    beta, a, state, _ = _mode(lay, beta, a, prec_a, prec_g)
    if not converged:
        notes.append(f"the variances were still moving after {max_rounds} rounds")
    at_floor = [k for k, v in sigmas.items() if v <= FLOOR]
    if at_floor:
        notes.append(f"{', '.join(at_floor)} at the floor: no variance there the data can see")
    _, _, inverses = _schur(state)
    tastes = {item: {o: (ab[c], math.sqrt(inv[c][c])) for c, o in enumerate(opts)}
              for item, opts, ab, inv in zip(lay.block_items, lay.block_options, a, inverses)
              if opts}
    coefficients = dict(zip(lay.names, beta))
    coefficients.setdefault(f"strength[{lay.sources[0]}]", 0.0)
    return MixedFitted(
        name=name, sources=lay.sources, coefficients=coefficients, models_abstention=False,
        converged=converged, iterations=rounds, loglik=state["loglik"],
        n_parameters=len(beta), n_draws=int(sum(r.weight for rows in lay.blocks for r in rows)),
        notes=notes, sigmas=sigmas, _layout=lay, _beta=tuple(beta), _tastes=tastes,
        _levels_of=tuple(factors))


def fit(dataset: Dataset, model: str) -> MixedFitted:
    """One run's mixed model: item tastes, and a shift of each source by the item's family."""
    if model not in MIXED:
        raise FitError(f"no mixed model called {model!r}; have {list(MIXED)}")
    return fit_mixed(dataset, position=model == "mixed_position",
                     factors=(("family", family_of),), name=model)
