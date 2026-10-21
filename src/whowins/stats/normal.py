"""The normal distribution, to the accuracy a likelihood needs, in the standard library.
`orthant(b, cov)` is P(Z <= b) for Z ~ N(0, cov): exact to double precision in one and
two dimensions, and by randomized quasi-Monte Carlo above that, where it only predicts.
Checked against scipy and against independent integrals; see docs/codebase/11_statistics.md.
"""

from __future__ import annotations

import math
import operator
import random
from statistics import NormalDist
from typing import Sequence

_STD = NormalDist()
_SQRT2 = math.sqrt(2.0)
_TWO_PI = 2.0 * math.pi

# Gauss-Legendre weights and negative nodes on [-1, 1], as Genz tabulates them for BVND.
_GL = {
    6: ((0.1713244923791705, 0.3607615730481384, 0.4679139345726904),
        (-0.9324695142031522, -0.6612093864662647, -0.2386191860831970)),
    12: ((0.04717533638651177, 0.1069393259953183, 0.1600783285433464,
          0.2031674267230659, 0.2334925365383547, 0.2491470458134029),
         (-0.9815606342467191, -0.9041172563704750, -0.7699026741943050,
          -0.5873179542866171, -0.3678314989981802, -0.1252334085114692)),
    20: ((0.01761400713915212, 0.04060142980038694, 0.06267204833410906,
          0.08327674157670475, 0.1019301198172404, 0.1181945319615184,
          0.1316886384491766, 0.1420961093183820, 0.1491729864726037,
          0.1527533871307258),
         (-0.9931285991850949, -0.9639719272779138, -0.9122344282513259,
          -0.8391169718222188, -0.7463319064601508, -0.6360536807265150,
          -0.5108670019508271, -0.3737060887154195, -0.2277858511416451,
          -0.07652652113349733)),
}

# Quasi-Monte Carlo: lattice size, random shifts, and the seed that makes a prediction repeatable.
QMC_POINTS = 1024
QMC_SHIFTS = 8
QMC_SEED = 20260928
_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)


class NormalError(ValueError):
    """A covariance that is not one."""


def cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / _SQRT2)


def pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(_TWO_PI)


def ppf(p: float) -> float:
    return _STD.inv_cdf(min(max(p, 1e-300), 1.0 - 1e-16))


def bvn_upper(h: float, k: float, r: float) -> float:
    """P(X > h, Y > k) for standard normals with correlation r.
    Genz's BVND (Drezner and Wesolowsky, as revised by Genz 2004), line for line."""
    r = max(-1.0, min(1.0, r))
    w, x = _GL[6] if abs(r) < 0.3 else _GL[12] if abs(r) < 0.75 else _GL[20]
    hk = h * k
    bvn = 0.0
    if abs(r) < 0.925:
        hs = (h * h + k * k) / 2.0
        asr = math.asin(r)
        for wi, xi in zip(w, x):
            for node in (xi, -xi):
                sn = math.sin(asr * (node + 1.0) / 2.0)
                bvn += wi * math.exp((sn * hk - hs) / (1.0 - sn * sn))
        return bvn * asr / (2.0 * _TWO_PI) + cdf(-h) * cdf(-k)
    if r < 0:
        k, hk = -k, -hk
    if abs(r) < 1.0:
        as_ = (1.0 - r) * (1.0 + r)
        a = math.sqrt(as_)
        bs = (h - k) ** 2
        c = (4.0 - hk) / 8.0
        d = (12.0 - hk) / 16.0
        bvn = a * math.exp(-(bs / as_ + hk) / 2.0) * (
            1.0 - c * (bs - as_) * (1.0 - d * bs / 5.0) / 3.0 + c * d * as_ * as_ / 5.0)
        if hk > -160.0:
            b = math.sqrt(bs)
            bvn -= (math.exp(-hk / 2.0) * math.sqrt(_TWO_PI) * cdf(-b / a) * b
                    * (1.0 - c * bs * (1.0 - d * bs / 5.0) / 3.0))
        a /= 2.0
        for wi, xi in zip(w, x):
            xs = (a * (xi + 1.0)) ** 2
            rs = math.sqrt(1.0 - xs)
            bvn += a * wi * (math.exp(-bs / (2.0 * xs) - hk / (1.0 + rs)) / rs
                             - math.exp(-(bs / xs + hk) / 2.0) * (1.0 + c * xs * (1.0 + d * xs)))
            xs = as_ * (1.0 - xi) ** 2 / 4.0
            rs = math.sqrt(1.0 - xs)
            bvn += a * wi * math.exp(-(bs / xs + hk) / 2.0) * (
                math.exp(-hk * xs / (2.0 * (1.0 + rs) ** 2)) / rs - (1.0 + c * xs * (1.0 + d * xs)))
        bvn = -bvn / _TWO_PI
    if r > 0:
        return bvn + cdf(-max(h, k))
    bvn = -bvn
    if k > h:
        bvn += cdf(k) - cdf(h) if h < 0 else cdf(-h) - cdf(-k)
    return bvn


def cholesky(cov: Sequence[Sequence[float]], *,
             degenerate: bool = False) -> list[list[float]]:
    """Lower-triangular L with L L' = cov. A pivot that vanishes is refused, or, with
    `degenerate`, kept as a zero column: that variable is fixed by the ones before it."""
    n = len(cov)
    out = [[0.0] * n for _ in range(n)]
    # Round-off after near-zero pivots grows with the whole matrix's scale, not this entry's.
    slack = 1e-8 * max([1.0] + [abs(cov[i][i]) for i in range(n)])
    for i in range(n):
        for j in range(i + 1):
            s = cov[i][j] - sum(out[i][t] * out[j][t] for t in range(j))
            if i == j:
                tol = 1e-14 * max(1.0, abs(cov[i][i]))
                if s > tol:
                    out[i][i] = math.sqrt(s)
                elif not degenerate or s < -slack:
                    raise NormalError("the covariance is not positive definite")
            else:
                out[i][j] = s / out[j][j] if out[j][j] else 0.0
    return out


def orthant(b: Sequence[float], cov: Sequence[Sequence[float]]) -> float:
    """P(Z_i <= b_i for every i), Z ~ N(0, cov).
    One and two dimensions are exact; three and more use Genz's separation of variables over
    a shifted lattice, repeatable because the shifts are seeded."""
    keep = [i for i in range(len(b)) if cov[i][i] > 0.0]
    if len(keep) < len(b):
        # A variable with no variance is a certainty, not a dimension.
        if any(b[i] < 0.0 for i in range(len(b)) if cov[i][i] <= 0.0):
            return 0.0
        if not keep:
            return 1.0
        b, cov = [b[i] for i in keep], [[cov[i][j] for j in keep] for i in keep]
    d = len(b)
    if d == 1:
        return cdf(b[0] / math.sqrt(cov[0][0]))
    if d == 2:
        s1, s2 = math.sqrt(cov[0][0]), math.sqrt(cov[1][1])
        return min(1.0, max(0.0, bvn_upper(-b[0] / s1, -b[1] / s2, cov[0][1] / (s1 * s2))))
    return _orthant_qmc(b, cov)


def _orthant_qmc(b: Sequence[float], cov: Sequence[Sequence[float]]) -> float:
    """Genz (1992) separation of variables, most restrictive variable first, on a Richtmyer
    lattice with the tent transform and antithetic points."""
    d = len(b)
    order = sorted(range(d), key=lambda i: b[i] / math.sqrt(cov[i][i]))
    bb = [b[i] for i in order]
    # A near-singular covariance is a real fit at a boundary, so a vanishing pivot becomes a step.
    c = cholesky([[cov[i][j] for j in order] for i in order], degenerate=True)
    first = cdf(bb[0] / c[0][0]) if c[0][0] else float(bb[0] >= 0.0)
    if first <= 0.0:
        return 0.0
    # Row i: its bound, its Cholesky row left of the diagonal, and the diagonal times sqrt(2).
    rows = [(bb[i], c[i][:i], c[i][i] * _SQRT2) for i in range(1, d)]
    alpha = [math.sqrt(p) % 1.0 for p in _PRIMES[:d - 1]]
    rng = random.Random(QMC_SEED)
    inv, erfc, mul = _STD.inv_cdf, math.erfc, operator.mul
    total = 0.0
    for _ in range(QMC_SHIFTS):
        shift = [rng.random() for _ in range(d - 1)]
        for n in range(1, QMC_POINTS + 1):
            tent = [abs(2.0 * ((n * a + s) % 1.0) - 1.0) for a, s in zip(alpha, shift)]
            for flip in (False, True):
                f = e = first
                y: list[float] = []
                for (bound, left, diag), w in zip(rows, tent):
                    # Draw the previous variable inside its allowed range, then the chance the next one fits.
                    u = (1.0 - w if flip else w) * e
                    y.append(inv(min(max(u, 1e-300), 1.0 - 1e-16)))
                    known = sum(map(mul, left, y))
                    e = 0.5 * erfc((known - bound) / diag) if diag else float(known <= bound)
                    f *= e
                    if f <= 0.0:
                        break
                total += f
    return min(1.0, max(0.0, total / (2 * QMC_SHIFTS * QMC_POINTS)))
