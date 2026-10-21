# 15 — `src/whowins/stats/`: the alternatives, capacity and random effects

The second half of the statistics. [11_statistics.md](11_statistics.md) covers the strengths fit,
the nulls, the ladder and the gate; this file covers what the composition test is judged against,
the regularity check, capacity on declared tiers, and random effects. All of it is standard
library only. Its numerical results were checked against scipy on this machine; scipy is not a
dependency.

```
normal.py     ── the normal CDF, the bivariate normal (exact), orthants above two dimensions
families.py   ── independent Thurstone and the correlated probit: normal errors
models.py     ── the context model, a conditional logit with pulls between sources
regularity.py ── does adding a competitor ever raise an option's share?
capacity.py   ── R(q) on declared tiers, a lower and an upper bound; reads a tier run
mixed.py      ── random effects: item tastes and grouping factors (family, model, harness)
pooled.py     ── one fit across runs, with a random shift per model and, where separable, harness
```

`load_cell.py`, which reads a load run, is described beside the load bundles, in
[16_load_bundles_and_tiers.md](16_load_bundles_and_tiers.md), section 5.

---

## 1. `normal.py`: the normal distribution, in the standard library

The probit's likelihood is a set of orthant probabilities: the chance that a normal vector lies
below a bound in every coordinate. `orthant(b, cov)` computes them.

| Dimensions | Where it is needed | How |
|---|---|---|
| 1 | a pair | `erfc`, exact |
| 2 | a triple | Genz's `BVND` (Drezner and Wesolowsky, revised by Genz 2004), line for line, exact to double precision |
| 3 and 4 | predicting a four- or five-way set | Genz's separation of variables over a shifted Richtmyer lattice, with the tent transform and antithetic points, seeded so a prediction repeats |

A probit is only ever *fitted* on pairs and triples, where the likelihood is exact, so the
optimiser never sees Monte Carlo noise. `bvn_upper` matches `scipy.stats.multivariate_normal.cdf`
to 2.2e-16 over 3,000 random `(h, k, r)`, and Sheppard's formula to 1e-14 on both sides of every
branch it takes. The lattice is within 3.8e-5 of scipy over 80 random three- and four-dimensional
covariances, and within 4.3e-6 of the one-dimensional integral an equicorrelated orthant reduces
to, in about 18 ms. A variable with no variance left is a certainty, not a dimension: it becomes a
step, which is what a probit at a boundary (below) produces. After near-zero pivots, round-off
grows with the matrix's scale, so `cholesky(..., degenerate=True)` takes a pivot as zero down to
-1e-8 times the largest variance. The bound was -1e-11 times that pivot's own variance until
2026-10-09, when a singular covariance from the Qwen 3 0.6B ladder fit (three sources' errors
merged) gave a last pivot of -1e-9 and stopped `strengths.sh`.

## 2. `families.py`: independent Thurstone and the correlated probit

Both are random-utility models with normal errors: an option's utility is
`mean[source] + later × rank + error`, and the highest wins.

| Model | Errors | Parameters at five sources | Identified by pairs? |
|---|---|---|---|
| `thurstone`, `thurstone_position` | independent | 4 means (+ `later`) | yes |
| `probit`, `probit_position` | any covariance between sources | 4 means + 9 covariances (+ `later`) | **no**, and it refuses |

**The scale.** Choice depends only on differences of errors, so what is identified is the
*variogram*, `Var(error_a − error_b)` for every pair. Means, `later` and variogram are reported
normalised so the variogram averages 1. Under independent errors every entry is 1 and
`P(a beats b) = Φ(mean_a − mean_b)`, so a probit whose errors are independent reads exactly as
Thurstone. An entry below 1 means the two sources' errors move together.

**Two computations that agree.** Thurstone's probabilities are one integral over z; the probit's
go through `orthant`. With every variogram entry set to 1 they agree to 3.3e-16 on pairs and
triples and 7e-6 on four- and five-way sets. A second test simulates correlated normal utilities,
takes the highest and counts, using none of the orthant code.

**Fitting.** BFGS with central-difference gradients on the per-draw negative log-likelihood, from
the Thurstone fit of the same data, so the probit can only fit better in sample. A source that
never won and a disconnected design are refused as they are for `luce`.

**Decided draws only.** These families model which option won when one did. If every family
shared one model of abstaining, it would add the same amount to each family's log score and cancel
from every difference, so the families are compared on decided draws. With abstention as an extra
option instead, its rate would identify the probit's correlations from pairs, as an artefact of
how abstention was modelled.

**Identification is judged on the compositions.** `_unidentified` computes the rank of the
Jacobian of every choice probability at a generic point (local identification, Rothenberg 1971),
first for the model without a position term on the compositions alone, then for the whole model.
Ten pairs pin **10 of the 13** means and covariances, as 2510.15839 proves; the four-triple slice
of stage two pins all **13**, which is what `set.json` chose it for. The first check exists
because a position term would otherwise identify the probit from pairs: ten pairs in both orders
reach 14 of 14, but only by assuming the recency effect is the same size in every pair, and the
within-message pair already breaks that. So stage one refuses the probit by name.

**Boundary fits.** Sometimes the fit merges some sources' errors, their variogram going to 0.
Within them only the means and position decide, and the likelihood rises toward a limit instead of
a peak. `boundary_note` says so whenever a normalised entry is below 0.01, so a 0.00 is read as a
limit the fit ran into, not a measurement.

**Recovery.** From the stage-two slice at 1,500 items, a planted S3-S5 correlation of 0.8
(variogram 0.217) comes back at 0.217, every mean within about 0.04. On held-out comparable
triples the probit then beats `thurstone_position` and `luce_position` by about 0.018 nats a draw,
interval clear of zero. A probit **without** a position term, fitted to data with a real position
effect, soaks recency into its correlations and predicts worse out of sample than Thurstone,
although it fits better in sample. That is why every family has a `_position` form.

## 3. The context model (`models.py`)

Seshadri, Peysakhovich and Ugander (2019): an option's utility gains a *pull* from every other
source present, `context[z on a]`. It is still a conditional logit, fitted by `fit`'s Newton routine.

- On a pair only a pull's difference is seen, which makes it a **pair-interaction** model:
  Plackett-Luce plus a deviation for every pair. A triple shows more of the pulls.
- The ridge shrinks only the pulls, never the strengths (`Design.penalised`), so the largest
  penalty is Plackett-Luce, and a source that never won is still refused.
- With no `ridge` given, the per-draw penalty comes from `CONTEXT_PENALTIES` by 5-fold
  cross-validation over **items**, on the training data only. A tie goes to the larger penalty.
- It is fitted on `canonical` data, one weighted row per (sources, order, winner): a speed change
  only, which a test pins to 1e-9.

## 4. `regularity.py`: can adding a competitor help?

Every random-utility model, Plackett-Luce, Thurstone and the probit included, obeys
**regularity**: adding a competitor never raises an option's chance of winning. A real rise is a
context effect none of them can fit. `check(data)` compares an option's share of decided draws in
every larger set T with its share in every smaller set S, `a ∈ S ⊂ T`: 110 tests on the ladder,
each one-sided at `alpha / 110` with errors from resampling items. A pair's two orders and a
triple's six do not put an option at the same ranks, so each row also carries `reference_rise`,
what `luce_position` fitted to the same draws predicts. A rise position alone predicts is not a
context effect.

## 5. `capacity.py`: R(q) on declared tiers

The study's method defines R(q, D, H, S, V) as the largest subset of declared tiers 1 to 12 whose every
required pair clears q with a simultaneous lower bound, for one setup. `capacity(draws, q)`
computes it with the matching upper bound; `scripts/capacity.sh RUN` reads a `declared-tiers-6` or
`declared-tiers` run over the tiers that run measured ([16_load_bundles_and_tiers.md](16_load_bundles_and_tiers.md)
and [17_layouts.md](17_layouts.md), section 6, describe the designs).

- **The input** is one `TierDraw` per reply: the item, the tier the stated policy makes win, the
  other tier, whether the reply did what the winner asked (abstaining is not), and the draw's name.
  `from_records` builds them from a run, leaving out replies the harness could not use.
- **The unit is the item.** One draw per item and pair is kept, chosen by a hash of names, never of
  outcomes, so the Clopper-Pearson bounds are exact whatever the dependence within an item. When an
  item's repeats move together, counting every draw certified a pair whose true rate was exactly q
  13% of the time, against 1.25% for one draw per item (nominal 2.5%).
- **Simultaneous, both sides.** Each bound is at `alpha / (2 × pairs measured)`, so the lower and
  upper R hold together with probability at least 1 − alpha. **Lower R** is the largest subset
  whose every pair is certified; **upper R** the largest none of whose pairs is ruled out. All
  4,096 subsets are enumerated, because a useful subset may skip tiers.
- **Thin data is said so.** `design_ceiling` is the largest R the items could certify if every
  draw were obeyed; at 1 the verdict is "no capacity claim" and names the items needed.

`items_needed` gives the method's numbers: one bound at 95% needs 59 clean items to clear 0.95 and
299 to clear 0.99. Held over all 66 tier pairs on both sides it is 154 and 784. The design gives
each pair 196 or 197 items, so a model obeying 99.8% of the time certifies about six tiers at 0.95
(two or three misses pull a pair's bound under it), and nothing at 0.99.

## 6. `mixed.py`: random effects for items and families

The method fits "item, item family, model and harness random effects". The mixed logit is

```
utility = strengths (+ later x rank) + a[item, option] + g[level, source] for each grouping factor
```

- **`a`, an item's taste for each of its options**, normal with its own variance. It is the
  content term the method says balancing cannot cancel: averaging sigmoid(d + b) and sigmoid(d − b)
  is not sigmoid(d), so a fit that ignores it shrinks every effect toward zero.
- **A grouping factor shifts each source's log strength per level.** In one run the factor is the
  item's family (`fmt`, `tool`, …): `mixed` and `mixed_position` in THE FAMILIES.
- **Fitting.** The joint mode by Newton, each item's block eliminated through a Schur complement,
  so the cost grows with items, not with their square. Each variance comes from Schall's fixed
  point on the Laplace marginal: the mean square of its effects plus their posterior variance,
  refitted until it settles. Laplace errs low with few draws per effect, so read a variance as a
  floor on the truth.
- **Prediction.** An item seen in training is predicted from its own estimated tastes, integrating
  over what is still uncertain by 200 seeded draws; an item never seen, from the population.

On a planted world with tastes of sd 1.0, the fit finds 0.84 to 0.89, restores the strengths
`luce_position` shrinks (S5: 1.62 against 1.41, planted 1.6), and predicts the same items'
five-way sets better by about 0.2 nats a draw. A test recomputes the gradient at the fitted mode
from scratch and finds it zero.

## 7. `pooled.py`: model and harness effects across runs

`scripts/pool.sh RUN RUN ...` fits the pairs of several runs at once: strengths they share, a
random shift of each source per **model** (the run's checkpoint and decoding policy), and a shift
per **harness** (its serving environment) only when the design can tell a harness from its
models. `harness_separable` requires two harnesses and at least one model served in more than one.
The main run serves each model on one machine, so there a harness is its models, and the fit says
so instead of fitting it. Serving one Qwen 3 rung on both machines, as the plan suggests, is what
would make it separable.

## 8. THE FAMILIES on the ladder run

`strengths.sh` prints THE FAMILIES when the composition test can run: every family above fitted
alike on decided draws in both stages, then regularity. Its log scores are per decided draw, so
they are not comparable with THE COMPOSITION TEST's. It takes about a minute of an 80-second
report on the ladder run; `--no-families` skips it.

On `ladder-qwen3-14b` (7,539 decided draws, 1,461 with no winner left out):

```
 stage one (pairs -> triples and the five-way)       stage two (+ four triples)
   position             -0.8668                        probit_position      -0.8553
   luce_position        -0.9134                        position             -0.8954
   context_position     -0.9134                        luce_position        -0.9942
   mixed_position       -0.9284                        context_position     -0.9942
   thurstone_position   -0.9386                        thurstone_position   -1.0323
   probit, probit_position  REFUSED                    mixed_position       -1.0478
```

- In stage one nothing beats `position`. The context model's cross-validation chose the largest
  penalty, so on these pairs it is Plackett-Luce: no pair interaction was worth its parameters.
- In stage two the probit is identified and does best. Its fit is on a boundary: the errors of
  S3, S4 and S5 (user, tool result and memory) merge and `later` goes to about zero, so among
  those three position decides sharply and elsewhere it hardly matters. In effect it fits a
  position effect that differs by pair, which one `later` coefficient cannot.
- `mixed_position` finds large item tastes (sd about 1.6) yet predicts the held-out sets a little
  worse than `luce_position`. A likely reason, not yet checked: this run asks each item only about
  three trials, so few items' tastes are seen in training before their triples are predicted. The
  flat ladder asks each item about twelve.
- Regularity: 110 tests, no violation. The largest rise is S1's share going from 0.023 to 0.175
  when S5 joins S1-S4 (se 0.048), where position alone predicts a fall.

This run used the old `composition-ladder`, where the operator sources always come first, so being
an operator and being early are one column. It shows the families working on real data; the main
run's flat ladder asks the question.

## 9. The gate's ten newer checks

`scripts/phase1.sh` plants a world for each alternative, and each must find it:

```
 [PASS] Thurstone and the probit agree where the errors are independent   3.3e-16, 5.7e-06
 [PASS] the correlated probit is refused on pairs, and the stage-two slice identifies it
 [PASS] and it recovers a planted correlation from that slice    S3-S5 0.217 planted, 0.217 back
 [PASS] a correlation invisible in pairs is caught once triples are in    +0.018 [+0.013, +0.024]
 [PASS] regularity catches a planted context effect and no random-utility world
 [PASS] and the context model finds the pull that broke it      +0.033 [+0.021, +0.044]
 [PASS] capacity certifies a planted separation from both sides   R(0.95) from 3 to 3, planted 3
 [PASS] and says so when the data are too thin to certify anything
 [PASS] the mixed model finds planted item tastes and carries them to an item's larger sets
 [PASS] pooling finds a spread between models, and leaves out a harness it cannot separate
```

The worlds: a probit where S3 and S5 (user and memory, one transport) move together; a context
world where S5 pulls S1 up; six tiers where tiers two apart are obeyed 0.995 of the time and
neighbours 0.9, so R(0.95) is 3; item tastes of sd 1.0; and six runs whose models shift the
strengths with sd 0.8, served on two machines that no model shares. The first eight thresholds
pass at the default seed and at eight others.
