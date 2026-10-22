# 11 — `src/whowins/stats/`: the fit, the nulls, the ladder, the gate

This is phase 1 of the plan, and the plan defines it as a **gate** rather than a task: *write the
strengths model, the alternatives and the capacity definition; simulate the whole pipeline, and
confirm it recovers known parameters and detects the published pairwise-insufficiency
counterexample.*

**It uses the standard library only.** Five sources give 120 rankings, and `fractions.Fraction`
makes "identical pairwise rates" exactly equal instead of approximately equal. This file covers
the first half; the alternatives the composition test is judged against, capacity and random
effects are in [15_statistics_alternatives.md](15_statistics_alternatives.md).

```
choice.py     ── what a measurement IS, with no chat templates in it
models.py     ── one conditional logit with several feature maps, + a second fitter as a cross-check
score.py      ── held-out log score, Brier, calibration, item-clustered bootstrap
rankings.py   ── RankingWorld; the exact counterexample; luce_world()
simulate.py   ── planted truths, and data drawn from them
power.py      ── power curves from simulation
ladder.py     ── the two-stage composition test, read off data/splits/set.json
strengths.py  ── fits a REAL run, and runs the composition test when the run allows it
phase1.py     ── the gate: 23 checks, PASS or FAIL
```

---

## 1. `choice.py`: the measurement, without the study around it

```python
Option(option_id, source, position)     # position is None when the design recorded none,
                                        # which is NOT slot 0 and must never be filled in as one
Choice(item, options, won, weight, tags)
Dataset(choices)
```

A `Choice` is not a trial. It has no chat templates, tool calls, repeats or checkers, so the same
code reads a simulated world and a real log. `won=None` is an **outcome** (nobody won), not a
missing value. The resampling unit is the **item**.

A `Choice` rejects anything that is not a measurement: fewer than two options (one option is a
solo trial, which measures ability and not precedence), a repeated option, **two options from the
same source** (a composition is a set of distinct sources), or a winner that did not compete.

```python
from_records(rows)   # a run's records -> a Dataset. CONFLICT ARM ONLY.
```

Position is carried across, and it has to be: runs 2 and 3 found the later instruction winning
0.83 and 0.89 of the time, so a strength fitted without a position term would measure the
**arrangement**.

`from_records` builds one `Option` per `(source, option)` entry of `meta["carries"]`. In a free
prediction, where two sources demand the same option, that gives two `Option`s with the same id,
and `Choice` raises `ChoiceError: the same option twice`. Nothing catches it, so `strengths.sh`
would stop on the whole run. So `from_records` reads only trials where every source carries a
different option, and `free_from_records` reads the rest: each source is its own `Option`, named
`option@source`, and the option it stands for is in `tags["actions"]` (finding Y of
the code audit). `predict_actions(fitted, choice)` gives an option the summed
chance of the sources that demand it. That is the independent-draw reading, and the one a
pair-only fit commits to without a new parameter. Both read usable replies only: a truncated or
faulty one measured nothing ([09](09_runner_execution.md), section 3), and until 2026-10-09 they
read its win.

### `kinds(dataset)`: which compositions can be read

```python
# FREE means EVERY PAIR OF SOURCES INSIDE the composition is seen both ways round.
```

At two sources that is a single test. Above two it is the only correct test. The version written
for pairs called a triple free whenever its order varied at all, including when the operator block
was always first, so *"being an operator"* and *"being early"* stayed the same column. **Ten of the
fourteen compositions it called free had a source that could never sit later than another**, the
five-way set among them. The fit showed the damage: with a position coefficient of +3.93 to
explain, the strengths gave the always-first operator the **highest** strength of the five.

After the fix, four compositions are free: `S3-S4`, `S3-S5`, `S4-S5` and `S3-S4-S5`.

## 2. `models.py`: the estimators

There are five feature maps over one numerical routine, plus a saturated model:

| Model | Parameters | Predicts a composition it never saw? |
|---|---|---|
| `uniform` | none | yes, every option equally likely |
| `position` | 1: `later` on a 0-to-1 rank | yes |
| `luce` | one strength per source (Bradley-Terry / Plackett-Luce) | yes |
| `luce_position` | strengths + `later` | yes |
| `luce_position_size` | + `later × (size − 2)` | **only if fitted on data with sets above a pair** |
| `context`, `context_position` | + a pull of every source on every other | yes; see doc 15 |
| `saturated` | one free distribution per composition | **no**, because it has no parameters for an unseen composition |

`fit()` also routes `saturated`, the normal-error families and the mixed models to their own
fitters, so one call fits any model by name.

`_order_rank(choice)` gives 0 to the earliest option and 1 to the latest, so one parameter covers
the whole position effect, and for a pair it is exactly *"did the later one win"*. It returns
`None` when any competing option has no recorded slot, and `_rows_for` then skips that choice and
reports how many it skipped.

`luce_position_size` turns the published result into code. Its extra feature is identically zero
on pairs, so data with pairs only leaves the information matrix singular, and `solve()` rejects the
fit by name. `phase1` asserts exactly that: rejected on pairs, fitted with triples.

`fit()` is Newton's method with step halving, and it is careful about three things:

```python
# gradient test PER DRAW, not summed: at ten thousand draws float64 cannot get a summed
# gradient below 1e-10 however well converged the fit is
if max(abs(g) for g in gradient) < tol * max(1.0, total_weight): converged = True

# the second stopping rule: Newton is quadratic near the optimum, so the parameters
# stop moving a step before the gradient test passes
if max(abs(scale * d) for d in step) < step_tol: converged = True

# and when halving stops improving the likelihood, that is recorded separately
# ("Newton stalled") and not reported as convergence
```

`_refuse_unfittable` raises instead of returning a guess when:

- the comparison graph over sources is **not connected**, because two groups can slide apart
  freely and any difference between them only reflects where the optimiser stopped;
- a source **competed and never won**, because the likelihood is maximised at a strength of zero
  and no finite number is the answer. A `ridge` gives a finite one on purpose, and the report says
  so.

`strengths()` returns `exp(coefficient)` per source, normalised to sum to one, which is the only
scale a Plackett-Luce strength is defined on. A single strength means nothing on its own; ratios
between strengths do.

`fit_mm` is a second, independent Plackett-Luce fitter (minorize-maximize, Hunter 2004) that
**shares no line of code** with `fit`. It exists only to disagree with `fit`, because there is no
reference implementation to check a fitter against. Features and abstentions are left out of its
scope, so that it cannot develop the bug it exists to find. The gate requires the two fitters to
agree to 1e-7.

## 3. `score.py`: how well did a model predict data it never saw?

Held-out **log score** is the primary measure, because R² over aggregates is unstable. Brier, MAE
and calibration are reported alongside it.

```python
evaluate(fitted, dataset)   # n_scored, n_declined, coverage, log_score, brier, mae,
                            # surprises, calibration, calibration_error
```

Three properties matter:

- **Coverage is part of the score.** A model that declines half the test set can look excellent
  on the half it kept. `compare()` refuses to rank models with unequal coverage unless asked to,
  and says why.
- **A zero is counted, never averaged away.** A probability of 0 for what actually happened is
  floored at 1e-12 and counted as a `surprise`.
- **Brier is computed over the whole predicted simplex**, so a model that spreads the rest of its
  mass badly pays for it. Calibration bins **every (choice, outcome) pair**, because the realised
  outcome occurred every time by definition, and binning only that outcome would measure nothing.

```python
bootstrap(a, b, dataset, draws=1000)   # resamples ITEMS, never draws
```

Three draws of one scenario measure one thing. Treating them as independent looks about 1.7 times
more certain than the data are.

## 4. `rankings.py`: the counterexample, re-derived every run

```python
WORLDS = {
 "a_wins_the_triple": {ABC: 1/2, BAC: 1/5, CBA: 3/10},
 "b_wins_the_triple": {ABC: 1/5, BAC: 1/2, CAB: 3/10},
}
```

A `RankingWorld` is a distribution over **rankings**. `choice_probs(subset)` restricts each ranking
to the subset and gives the win to whichever remaining option comes first. That is how one world
answers for **every** composition at once, so the different set sizes cannot disagree with each
other.

`verify()` re-derives the claim instead of asserting it:

```
 pairwise          A>B 1/2   A>C 7/10   B>C 7/10      IDENTICAL, as exact fractions
 triple winner     world a: A            world b: B    DIFFERENT
```

`luce_world(strengths)` builds the ranking world that a Plackett-Luce model generates, whose choice
probability on *any* subset is `w_i / Σ`. That property is what lets Plackett-Luce extrapolate from
pairs, and it is what the counterexample worlds lack.

## 5. `simulate.py`: planting a truth

```python
LogitTruth(strengths, later=0.0, abstain=None)   # strengths, and optionally a REAL position effect
WorldTruth(world)                                # a ranking world as the generator
MixtureTruth(parts, weights)                     # two regimes mixed: item heterogeneity
```

`arrangement` is part of the truth:

| `arrangement` | What it is |
|---|---|
| `balanced` | what `pairwise-balanced` does: every permutation in turn |
| `random` | shuffled |
| `sorted` | **the first run's design, kept as a planted fault** |

`confounded(truth, …)` plants a **flat** truth with a real position effect and fits it under both
arrangements. The balanced arrangement returns flat strengths, which is the truth. The sorted
arrangement returns an ordered ladder, which is false, and **nothing in the fit indicates it**.
That reproduces the first run's precedence table on demand, and it is why `pairwise-balanced`
exists.

## 6. `ladder.py`: the two-stage composition test

The stages are **read from `data/splits/set.json`** instead of being restated in code, so the split
file and the analysis cannot drift apart.

```python
two_stage(data) -> {stages: [stage one, stage two], on_the_comparable_triples: …}
```

Each stage fits every model on its training compositions and scores it on the compositions it
predicts, with an item-clustered interval against `luce`. **A rejected fit is a result**:
`luce_position_size` is rejected in stage one because pairs cannot identify it, which is the reason
the project exists.

```python
empirical_ceiling(data)   # the best in-sample log score for a model that sees
                          # COMPOSITION *and* ORDER
```

A saturated model is **not** that ceiling. It is saturated over compositions but blind to
arrangement, so `position` beats it (−1.19 against −1.30 on the ladder run). The ceiling is fitted
on the same data it scores, so no model scored out of sample can beat it, and `headroom()` reports
how many nats short each model is. It also gives the ceiling's top-1 accuracy, and each model's
share of the way from the fitted `uniform` model (0) to the ceiling (1): on the 14B ladder test run
`position` recovers 62% in stage one. `score.evaluate` reports `top1`, the share of draws whose
winner the prediction rated highest, a tie sharing the credit. Both are for a reader; the log
score stays the measure.

```python
insufficiency()   # the counterexample, end to end
```

It fits **exact** pairwise data from both worlds (integer weights proportional to the true
probabilities, so it is the *population* fit and the result cannot be put down to luck), predicts
the triple, and prices being wrong. `wrong_in_at_least_one_world` follows from logic and not from a
measurement: one prediction cannot equal two different truths, so no tolerance decides the central
claim.

```python
misspecification(truth, train, test, model="luce")
```

It prices extrapolating from pairs, exactly, against the exact ceiling. The result is a property of
the **world and the model**, not of a sample.

## 7. `power.py`: how many items are enough

Plant a truth, draw a run of a given size, ask the study's question, and repeat. Power is the
fraction of repetitions that answer yes. A question returns `None` when it could not be asked at
all, and that is counted separately from a "no", because *unanswerable* and *answered no* are
different facts.

```python
recovers(truth, tolerance)              # did the fit land within tolerance of every strength?
beats(a, b, train=…, test=…)            # did a beat b out of sample, interval clear of zero?
beats_on_held_out_items(a, b)           # a="saturated", b="luce" DETECTS MISSPECIFICATION:
                                        # the saturated model can only win if Luce's structure is wrong
```

`_first_at(points, target)` returns the smallest size that clears the bar **and whose larger sizes
all clear it too**, because a curve estimated from finitely many replicates can clear the bar once
by luck.

**Every curve is conditional on the planted effect.** The module says so, and so does the printed
output.

## 8. `strengths.py`: fitting a real run

```bash
scripts/strengths.sh ladder-qwen3-14b
scripts/strengths.sh balanced-qwen3-1.7b --log results/balanced-qwen3-1.7b/rescored.jsonl
```

`analyse_run(run_id, log_path)` reads the log with `runner.analyse.read_records`, turns the
conflict rows into a `Dataset` with `from_records`, and sorts the compositions with `kinds`. It
sets `can_run_the_composition_test` to true when the data contain a set above a pair.

It prints **three fits that assume different things, and never pools them**:

| Fit (key in `--json`) | Assumes |
|---|---|
| free pairs only (`free_pairs_only`) | nothing. Only sources that appear in a free composition get a strength |
| whole design (`whole_design`) | that being first means the same thing where the operator is pinned as where it is not |
| within-message only (`within_message_only`) | nothing, but it is a **different effect** (primacy) pointing the other way |

On a run with triples the first two blocks include them: the ladder's free block holds S3-S4-S5
along with the three free pairs, and the whole-design block holds every size.

Each block also refits on **half the items** and scores on the other half. `_held_out_items`
shuffles the item list first, because scenario ids start with the family prefix, and cutting a
*sorted* list would train on format and ordering and test on path, refusal and tool: a family split
presented as an item split.

When `can_run_the_composition_test` is true, it also runs `ladder.two_stage` and prints THE
COMPOSITION TEST block. The closing "HOW TO READ THIS" section depends on the same flag. On a run
with sets above a pair it says that the first two fits pool every size and only the composition test
fits pairs alone and predicts unseen sets. On a pairs-only run it prints a `PAIRS ONLY` banner under
WHAT IS IN IT and says the run cannot answer the study's question, pointing at `phase1`. The header
line reads "a strength per source, from conflict data" in both cases. Until September 2026 the
footer was printed unconditionally and denied that the test could run, a few lines after its
results (finding B of the code audit).

### What it says about the ladder run

These are the numbers from `records.jsonl`, i.e. from the verdicts recorded at run time:

```
 FREE PAIRS ONLY  (S3-S4, S3-S5, S4-S5, S3-S4-S5)      ladder-qwen3-14b
   luce           S3 0.372  S4 0.320  S5 0.308
   luce_position  S3 0.411  S4 0.305  S5 0.284   later +2.488
   on held-out items:  position −0.734  >  luce −1.099 ≈ uniform −1.094

 THE COMPOSITION TEST — stage one: fit 10 pairs, predict 11 compositions
   position            −1.1909      ceiling −0.9400 over 36 (composition, order) cells
   luce_position       −1.2150      best model is 0.251 nats short
   luce                −1.3740
   uniform             −1.6082
   luce_position_size  REFUSED: the information matrix is singular
```

**A model that knows only where an instruction sat predicts three- and five-way outcomes better
than one that knows which source it came from.** It also beats the two combined, so the fitted
strengths make the prediction worse when they are extrapolated. Against the ceiling, `position`
leaves 0.251 nats and `uniform` leaves 0.668, so pairwise measurements carry roughly **62%** of
what is predictable about larger sets. Composition is therefore useful, but what carries over from
pairs is **position**, not provenance.

Rescored with the checkers installed at the end of September 2026 (the fmt-0190 fix, finding H),
stage one reads −1.1900, −1.2135, −1.3724 and −1.6074 with a ceiling of −0.9386, and `position` is
still 0.251 nats short. On the free compositions `luce` minus `uniform` moves from +0.0053
[−0.0130, +0.0215] to +0.0047 [−0.0139, +0.0209].

### The families

When the composition test can run, `ladder.families` runs it again with every model family fitted alike on decided draws, and adds the regularity check. It prints as THE FAMILIES; [15_statistics_alternatives.md](15_statistics_alternatives.md) says what each family is and what the block showed on the ladder run.

### Free predictions

`free_predictions(run_id, free_log)` fits every model on the pairs of a ladder run and scores the
free-prediction run of the same model and mode with `score.evaluate_free`: the log score of what
won, and, where one option is demanded by more sources than the other, how often it was predicted
to win against how often it did, among draws where an option won. Winning more often than
predicted is a consensus effect; less often means the sources discount each other. Draws with no
winner are left out of that comparison on both sides. A fit's outside option has one utility, so
it predicts fewer no-winner replies as sources are added; the Qwen 3 runs show a flat rate, and
until 2026-10-09 that gap pushed the predicted shared wins up and read as discounting. The log
score still counts a no-winner reply as an outcome.

```bash
scripts/strengths.sh main-ladder-qwen3-14b-think --free results/main-free-qwen3-14b-think/records.jsonl
```

## 9. `phase1.py`: the gate

```bash
scripts/phase1.sh            # ~50 s, exits non-zero if any check fails
scripts/phase1.sh --full     # more replicates and sizes, exactly the same checks, ~5 min
```

Everything is simulated, and no run is read. The planted truth is
`{S1: 0.5, S2: 1.0, S3: 2.0, S4: 4.0, S5: 8.0}`. The strengths are an octave apart on purpose,
because an easy truth produces an encouraging curve that means nothing.

```
 [PASS] the counterexample is exact                          two worlds agree on every pair
 [PASS] their three-way winners differ
 [PASS] a pair-only fit cannot tell the two worlds apart     identical fit, identical prediction
 [PASS] so it is wrong in at least one of them               0.1118 nats/draw, unrecoverable
 [PASS] the strengths model recovers a planted truth         max error 0.0035 at 400 items
 [PASS] and recovers them with a position effect present     later planted 1.5, recovered 1.479
 [PASS] two independent algorithms agree                     Newton vs MM: 2.4e-12
 [PASS] a sorted arrangement is caught inventing an order    spread 0.007 balanced, 0.602 sorted
 [PASS] a parameter pairs cannot identify is refused, and triples fit it
 [PASS] a correctly specified world costs almost nothing to extrapolate   0.00002 nats
 [PASS] power rises with the number of items
 [PASS] a misspecification invisible in pairs becomes visible with triples
 [PASS] the detector does not cry wolf on a world that really is Luce
 ... and ten more, on the families, capacity and random effects
 PASS -- 23 of 23
```

The middle power curve makes the case for three-way data. The planted mixture is **exactly flat
Plackett-Luce on every pair** and is not flat on any triple, so from pairwise data it is
undetectable at any size, while with triples in the design it becomes detectable. Measured, power
is 0.00 from pairs at any size. With triples it is 0.25 at 100 items in the default gate (20
replicates), and 0.40 at 100, 0.90 at 200 and 1.00 at 400 under `--full` (40 replicates).

The last ten checks plant worlds built to need the alternatives, and are listed in
[15_statistics_alternatives.md](15_statistics_alternatives.md).

The opening banner says "Everything below is simulated. No model was called and no run was read;
the composition test on real data is `scripts/strengths.sh <run>`." At the end the gate prints
**what it does not cover**, because that is part of the answer:

```
 - a pre-registration -- there is none, by the owner's decision, so every result is exploratory
 - a harness effect on real data -- every model is served on one machine, so a harness cannot be
   told from its models until one model is served on both
 - capacity on real data -- this gate checks capacity on simulated tiers only;
   `scripts/capacity.sh RUN` reads an observed tier run
 - any real composition above a pair -- the gate is simulated; `scripts/strengths.sh <run>`
   runs the composition test on a real run
```

The list is `phase1.SILENT_ABOUT`, and
`tests/test_stats.py::test_the_gate_says_what_it_is_silent_about` checks that it still names
the pre-registration, the harness, capacity on real data and compositions above a pair, and that
it no longer calls the probit deferred. The capacity item says what the gate covers, simulated tiers,
and where an observed tier run is read: `scripts/capacity.sh RUN`.
