"""Random-utility families with normal errors: independent Thurstone and the correlated probit.
An option's utility is mean[source] + later * rank + a normal error, and the highest wins.
Thurstone draws the errors independently; the probit lets every pair of sources co-vary,
which pairs cannot identify and triples can (2510.15839). Both model decided draws only.
"""

from __future__ import annotations

import collections
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from . import normal
from .choice import Choice, Dataset
from .models import FitError, Fitted, _order_rank, _refuse_unfittable

FAMILIES = ("thurstone", "thurstone_position", "probit", "probit_position")

# Independent errors: one trapezoid over z, exact to ~1e-15 for these smooth, Gaussian-weighted integrands.
_Z_STEP = 0.1
_Z_NODES = tuple(-10.0 + _Z_STEP * i for i in range(201))
_Z_WEIGHTS = tuple(_Z_STEP * normal.pdf(z) for z in _Z_NODES)
_SQRT2 = math.sqrt(2.0)
_FLOOR = 1e-300

# How a Jacobian's column counts as independent, relative to the largest one.
_RANK_TOL = 1e-6

# A normalised variogram below this is two sources whose errors have merged.
BOUNDARY = 0.01


def probabilities(means: Sequence[float],
                  variogram: Optional[Sequence[Sequence[float]]] = None) -> list[float]:
    """P(each option has the highest utility), in the order given.
    `variogram[a][b]` is Var(error_a - error_b). None means independent errors with every such
    variance 1, so P(a beats b) = Phi(mean_a - mean_b) and one integral over z is exact."""
    n = len(means)
    if variogram is None:
        if n == 2:
            p = normal.cdf(means[0] - means[1])
            return [p, 1.0 - p]
        out = []
        for j in range(n):
            shifts = [_SQRT2 * (means[j] - means[k]) for k in range(n) if k != j]
            out.append(sum(w * math.prod(normal.cdf(z + s) for s in shifts)
                           for z, w in zip(_Z_NODES, _Z_WEIGHTS)))
    else:
        out = []
        for j in range(n):
            others = [k for k in range(n) if k != j]
            # j wins when error_k - error_j < mean_j - mean_k for every other k.
            cov = [[(variogram[k][j] + variogram[m][j] - variogram[k][m]) / 2.0
                    for m in others] for k in others]
            out.append(normal.orthant([means[j] - means[k] for k in others], cov))
    total = sum(out)
    return [p / total for p in out]


@dataclass(frozen=True)
class _Spec:
    """Which family, and how its parameter vector is laid out.
    Means for every source but the first; `later`; then the Cholesky factor of the errors'
    covariance differenced against the first source, its top corner fixed at 1 for scale."""
    family: str
    position: bool
    sources: tuple[str, ...]

    @property
    def cells(self) -> list[tuple[int, int]]:
        m = len(self.sources) - 1
        return [(r, c) for r in range(m) for c in range(r + 1) if (r, c) != (0, 0)] \
            if self.family == "probit" else []

    @property
    def names(self) -> list[str]:
        out = [f"mean[{s}]" for s in self.sources[1:]]
        if self.position:
            out.append("later")
        return out + [f"cholesky[{r},{c}]" for r, c in self.cells]

    def start(self, means: Sequence[float] = (), later: float = 0.0) -> list[float]:
        """Independent errors, which the probit starts from: every Var(e_a - e_b) is 1."""
        m = len(self.sources) - 1
        theta = list(means) or [0.0] * m
        if self.position:
            theta.append(later)
        chol = normal.cholesky([[1.0 if r == c else 0.5 for c in range(m)] for r in range(m)])
        return theta + [math.log(chol[r][c]) if r == c else chol[r][c] for r, c in self.cells]

    def unpack(self, theta: Sequence[float]):
        """(means by source index, later, variogram or None)."""
        n = len(self.sources)
        means = [0.0] + list(theta[:n - 1])
        at = n - 1
        later = 0.0
        if self.position:
            later, at = theta[at], at + 1
        if self.family != "probit":
            return means, later, None
        m = n - 1
        chol = [[0.0] * m for _ in range(m)]
        chol[0][0] = 1.0
        for (r, c), value in zip(self.cells, theta[at:]):
            chol[r][c] = math.exp(value) if r == c else value
        omega = [[sum(chol[r][t] * chol[c][t] for t in range(m)) for c in range(m)]
                 for r in range(m)]
        vario = [[0.0] * n for _ in range(n)]
        for a in range(1, n):
            vario[0][a] = vario[a][0] = omega[a - 1][a - 1]
            for b in range(1, n):
                if a != b:
                    vario[a][b] = omega[a - 1][a - 1] + omega[b - 1][b - 1] - 2 * omega[a - 1][b - 1]
        return means, later, vario


# A pattern: the source indices competing, in increasing order, and each one's rank.
Pattern = tuple[tuple[int, ...], tuple[float, ...]]


def _key(choice: Choice, index: dict[str, int], position: bool) -> Optional[Pattern]:
    ranks = _order_rank(choice) if position else None
    if position and ranks is None:
        return None
    cells = sorted((index[o.source], ranks[o.option_id] if position else 0.0)
                   for o in choice.options)
    return tuple(i for i, _ in cells), tuple(r for _, r in cells)


def _pattern_probs(unpacked, pattern: Pattern) -> list[float]:
    """The pattern's probabilities, from `_Spec.unpack` of the parameters."""
    means, later, vario = unpacked
    srcs, ranks = pattern
    m = [means[s] + later * r for s, r in zip(srcs, ranks)]
    sub = None if vario is None else [[vario[a][b] for b in srcs] for a in srcs]
    return probabilities(m, sub)


def _jacobian_rank(spec: _Spec, theta: Sequence[float], patterns: Sequence[Pattern]) -> int:
    """How many parameters these patterns pin at `theta`: the rank of d(probabilities)/d(theta).
    Local identification is exactly a full-rank information matrix (Rothenberg 1971)."""
    def values(t: Sequence[float]) -> list[float]:
        unpacked = spec.unpack(t)
        return [p for pat in patterns for p in _pattern_probs(unpacked, pat)[:-1]]

    columns = []
    for i in range(len(theta)):
        h = 1e-5 * max(1.0, abs(theta[i]))
        up, down = list(theta), list(theta)
        up[i] += h
        down[i] -= h
        columns.append([(a - b) / (2 * h) for a, b in zip(values(up), values(down))])
    # Modified Gram-Schmidt: a column left with nothing after projection adds no information.
    scale = max(math.sqrt(sum(x * x for x in col)) for col in columns) or 1.0
    basis: list[list[float]] = []
    for col in columns:
        v = list(col)
        for _ in range(2):
            for q in basis:
                dot = sum(a * b for a, b in zip(v, q))
                v = [a - dot * b for a, b in zip(v, q)]
        norm = math.sqrt(sum(x * x for x in v))
        if norm > _RANK_TOL * scale:
            basis.append([x / norm for x in v])
    return len(basis)


def _generic(spec: _Spec, seed: int = 20260928) -> list[float]:
    """A point with no special structure, where a rank means what it means everywhere else."""
    rng = random.Random(seed)
    theta = spec.start()
    return [t + rng.uniform(-0.3, 0.3) + (0.7 if name == "later" else 0.0)
            for t, name in zip(theta, spec.names)]


def _unidentified(spec: _Spec, patterns: Sequence[Pattern]) -> Optional[str]:
    """Why these patterns cannot pin this model, or None when they can.
    Checked twice. The compositions alone must pin every mean and every covariance: with a
    position term, pairs alone reach full rank, but only by assuming one recency effect for
    every pair, which the within-message pairs already break. Then the whole model."""
    bare = _Spec(spec.family, False, spec.sources)
    compositions = sorted({(srcs, tuple(0.0 for _ in srcs)) for srcs, _ in patterns})
    have = _jacobian_rank(bare, _generic(bare), compositions)
    if have < len(bare.names):
        if spec.family == "probit":
            return (f"not identified by these compositions: they pin {have} of its "
                    f"{len(bare.names)} means and covariances, so its error correlations are "
                    f"not identified: pairs never pin them (2510.15839), and a set above a pair does")
        return (f"not identified by these compositions: they pin {have} of its "
                f"{len(bare.names)} means")
    have = _jacobian_rank(spec, _generic(spec), patterns)
    if have < len(spec.names):
        return (f"not identified: the data pin {have} of its {len(spec.names)} parameters; "
                f"a position term needs a composition seen in more than one order")
    return None


# --- Optimisation ---


def _minimise(f: Callable[[Sequence[float]], float], x0: Sequence[float], *,
              max_iter: int = 300, gtol: float = 1e-8
              ) -> tuple[list[float], float, bool, int, list[str]]:
    """BFGS with central-difference gradients and a backtracking line search.
    `f` is a PER-DRAW objective, so `gtol` means the same at any sample size. Returns
    (x, f(x), converged, iterations, notes)."""
    def grad(x: Sequence[float]) -> list[float]:
        out = []
        for i in range(len(x)):
            h = 1e-6 * max(1.0, abs(x[i]))
            up, down = list(x), list(x)
            up[i] += h
            down[i] -= h
            out.append((f(up) - f(down)) / (2 * h))
        return out

    n = len(x0)
    x, fx = list(x0), f(x0)
    g = grad(x)
    inv = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    notes: list[str] = []
    for iteration in range(1, max_iter + 1):
        if max(abs(v) for v in g) < gtol:
            return x, fx, True, iteration - 1, notes
        step = [-sum(inv[i][j] * g[j] for j in range(n)) for i in range(n)]
        slope = sum(s * v for s, v in zip(step, g))
        if slope >= 0:
            # The curvature estimate went bad; steepest descent is always a descent direction.
            inv = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
            step, slope = [-v for v in g], -sum(v * v for v in g)
        t = 1.0
        while t > 1e-12:
            trial = [a + t * s for a, s in zip(x, step)]
            ft = f(trial)
            if ft <= fx + 1e-4 * t * slope:
                break
            t /= 2.0
        else:
            notes.append("the line search stalled before the gradient reached zero")
            return x, fx, True, iteration, notes
        g_new = grad(trial)
        s = [t * v for v in step]
        y = [a - b for a, b in zip(g_new, g)]
        sy = sum(a * b for a, b in zip(s, y))
        x, fx, g = trial, ft, g_new
        if sy > 1e-12 * math.sqrt(sum(a * a for a in s) * sum(b * b for b in y)):
            if iteration == 1:
                # Nocedal and Wright (6.20): size the first curvature guess from the first step taken.
                gamma = sy / sum(b * b for b in y)
                inv = [[gamma * v for v in row] for row in inv]
            hy = [sum(inv[i][j] * y[j] for j in range(n)) for i in range(n)]
            yhy = sum(a * b for a, b in zip(y, hy))
            for i in range(n):
                for j in range(n):
                    inv[i][j] += ((sy + yhy) * s[i] * s[j] / (sy * sy)
                                  - (hy[i] * s[j] + s[i] * hy[j]) / sy)
    notes.append(f"did not converge in {max_iter} iterations")
    return x, fx, False, max_iter, notes


# --- The fitted object ---


@dataclass
class RumFitted(Fitted):
    """A fitted Thurstone or probit. Reports means and `later` on the scale where the average
    Var(e_a - e_b) is 1, so a probit with independent errors reads exactly as Thurstone."""
    _spec: Optional[_Spec] = None
    _theta: tuple[float, ...] = ()
    _cache: dict = field(default_factory=dict, repr=False)

    def predict(self, choice: Choice) -> Optional[dict[Optional[str], float]]:
        index = {s: i for i, s in enumerate(self.sources)}
        if any(o.source not in index for o in choice.options):
            return None
        key = _key(choice, index, self._spec.position)
        if key is None:
            return None
        probs = self._cache.get(key)
        if probs is None:
            probs = self._cache[key] = _pattern_probs(self._spec.unpack(self._theta), key)
        by_index = dict(zip(key[0], probs))
        return {o.option_id: by_index[index[o.source]] for o in choice.options}

    def strengths(self) -> dict[str, float]:
        raise FitError(f"{self.name} has means on a normal scale, not Plackett-Luce strengths")

    def reading(self) -> dict[str, Any]:
        """Means, `later` and the variogram, normalised so the variogram averages 1."""
        means, later, vario = self._spec.unpack(self._theta)
        n = len(self.sources)
        pairs = [(a, b) for a in range(n) for b in range(a + 1, n)]
        scale = 1.0 if vario is None else sum(vario[a][b] for a, b in pairs) / len(pairs)
        root = math.sqrt(scale)
        out: dict[str, Any] = {"means": {s: means[i] / root for i, s in enumerate(self.sources)}}
        if self._spec.position:
            out["later"] = later / root
        if vario is not None:
            out["variogram"] = {f"{self.sources[a]}-{self.sources[b]}": vario[a][b] / scale
                                for a, b in pairs}
        return out

    def as_dict(self) -> dict[str, Any]:
        return {**super().as_dict(), **self.reading()}


# --- Fitting ---


def fit(dataset: Dataset, model: str, *, max_iter: int = 300) -> RumFitted:
    """Fit Thurstone or the probit, with or without a position term, on decided draws.
    Refuses rather than guesses: abstentions (a separate process here), a source that never
    won, a disconnected design, and parameters the compositions cannot pin."""
    if model not in FAMILIES:
        raise FitError(f"no family called {model!r}; have {list(FAMILIES)}")
    family, position = model.split("_")[0], model.endswith("_position")
    if dataset.abstentions():
        raise FitError(
            f"{model} models which option won when one did: pass decided draws only. "
            f"{dataset.abstentions()} draws have no winner, and abstaining is a separate "
            f"process that cancels out of a comparison between families fitted alike")
    sources = dataset.sources
    if len(sources) < 2:
        raise FitError("fewer than two sources: there is nothing to compare")
    if family == "probit" and max(dataset.sizes) > 3:
        raise FitError("the probit is fitted on sets of up to three, where its likelihood is "
                       "exact; larger sets are predicted, never fitted")
    _refuse_unfittable(dataset, per_source=True, shrunk=False)
    spec = _Spec(family, position, sources)
    index = {s: i for i, s in enumerate(sources)}
    counts: dict[Pattern, collections.Counter] = collections.defaultdict(collections.Counter)
    skipped = 0
    for c in dataset:
        key = _key(c, index, position)
        if key is None:
            skipped += c.weight
            continue
        counts[key][index[c.winning_source()]] += c.weight
    if not counts:
        raise FitError(f"{model}: no usable choice -- every one is missing a recorded position")
    why = _unidentified(spec, list(counts))
    if why:
        raise FitError(why)

    patterns = [(key, [cell.get(s, 0) for s in key[0]]) for key, cell in sorted(counts.items())]
    n_draws = sum(sum(w) for _, w in patterns)

    def negloglik(theta: Sequence[float]) -> float:
        """Per draw. A step that overflows is infinitely bad, so the line search backs off."""
        try:
            unpacked = spec.unpack(theta)
            return -sum(w * math.log(max(p, _FLOOR))
                        for key, ws in patterns
                        for p, w in zip(_pattern_probs(unpacked, key), ws) if w) / n_draws
        except (OverflowError, normal.NormalError):
            return math.inf

    notes = [f"{skipped} draws unusable for this model and left out"] if skipped else []
    start = spec.start()
    if family == "probit":
        # Start where the errors are independent, from the Thurstone fit of the same data.
        seed = fit(dataset, "thurstone_position" if position else "thurstone", max_iter=max_iter)
        start = spec.start(seed._theta[:len(sources) - 1],
                           seed._theta[len(sources) - 1] if position else 0.0)
    theta, value, converged, iterations, more = _minimise(negloglik, start, max_iter=max_iter)
    fitted = RumFitted(
        name=model, sources=sources, coefficients=dict(zip(spec.names, theta)),
        models_abstention=False, converged=converged, iterations=iterations,
        loglik=-value * n_draws, n_parameters=len(theta), n_draws=int(n_draws),
        notes=notes + more, _spec=spec, _theta=tuple(theta))
    note = boundary_note(fitted)
    if note:
        fitted.notes.append(note)
    return fitted


def boundary_note(fitted: RumFitted) -> Optional[str]:
    """Say so when a probit's errors have merged: its variogram then reads 0.00 and the fit
    stalls, because the likelihood rises toward a limit rather than to a peak."""
    merged = [k for k, v in (fitted.reading().get("variogram") or {}).items() if v < BOUNDARY]
    if not merged:
        return None
    return (f"a boundary fit: the errors of {', '.join(merged)} move as one (variogram below "
            f"{BOUNDARY}), so within them only the means and position decide")
