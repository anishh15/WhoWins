# 01 — The research design, as the code implements it

This is a condensed reading of the study's design documents, which are not part of this repository,
with pointers into the code, so that the rest of these files make sense. The code was built for a
broader design, and the paper reports the seven experiments listed in the [README](../../README.md).

---

## 1. The claim being tested

For one trial `r` and one candidate instruction `j`, each instruction is given a utility:

```
U[r,j] = transport_role[j] + provenance_label[j] + declared_rank[j]
       + position[j] + surface[j] + content_identity[j] + random effects + noise
```

The agent acts on the instruction with the highest utility. Abstaining, flagging the conflict and
producing nothing valid are recorded as **separate outcomes** instead of being dropped.

Nothing here is called "authority". These are predictors of *revealed precedence*. Whether a single
shared quantity spans them is a hypothesis (H1), and the design tests it instead of assuming it.

## 2. Why composition is the main question

Pairwise win rates constrain only the distribution of *differences*. Two different distributions
over rankings can have **identical** pairwise win rates and a **different** three-way winner. More
data does not help: the two worlds agree in the limit, so no amount of pairwise data separates
them.

The repository re-derives this every time the gate runs instead of citing it:

```
whowins.stats.rankings.WORLDS        two exact ranking worlds over {A, B, C}, as Fractions
whowins.stats.rankings.verify()      pairwise identical: 1/2, 7/10, 7/10; triple winners A vs B
whowins.stats.ladder.insufficiency() fits pairs in both, predicts the triple, prices being wrong
```

The two worlds give identical data, identical fits and identical predictions, but their truths
differ, so the pairwise fit is wrong in at least one of them by **0.1118 nats per draw**, and more
pairwise data never reduces that.

The design takes three consequences from this:

- Ranking data is collected **from the start**, instead of being added later if the simple model
  fails.
- Prediction runs in **two stages**. Stage one fits pairs only and predicts the triples and the
  five-way set; it is the high-risk test and the interesting one. Stage two adds a preselected
  slice of four triples and predicts the held-out sets; the model is identified there, which makes
  it the more robust result.
- Every competing model gets the **same information budget**. A model that saw triples is not a
  fair comparator for a forecast made from pairs alone.

## 3. The seven experiment cells, and where each one lives

`data/trials/` holds ten worked trials per cell. They were written manually before any renderer
existed, which makes them a specification for the renderer and not a regression fixture taken from
its output.

| File | Cell | What it varies | Hypothesis |
|---|---|---|---|
| `01-decomposition.json` | decomposition | transport role, provenance, rank, position, surface, one at a time | H1: is "source" one thing or five? |
| `02-composition.json` | composition | **which** sources compete and **how many** (n = 2, 3, 5) | H3/H4: composition, the main question |
| `03-load.json` | load vs conflict | total instructions and conflicting instructions, independently | load is not conflict |
| `04-declared-tier.json` | declared tier | an explicit priority number, its scheme and direction | H6: magnitude vs rank |
| `05-binding.json` | binding | correct information supplied in stages | where failure happens |
| `06-authorship.json` | authorship | the same string, different claimed author | H7 |
| `07-harness.json` | harness vs model | the same trial through three renderers | H8: variance split |

The composition cell is also where the five sources are defined.
`whowins.splits.sources.load_sources()` derives them from that file's spans and raises if any source
appears with two identities, so the source inventory cannot drift away from the trials that
demonstrate it.

## 4. Why the five families look the way they do

A scenario's options must be *provably* mutually exclusive. Every option reads the **same
single-valued key** and demands a **different value** of it. A trace has one first tool call, and
an output gets one format label, so no reply can satisfy two options, and that follows from how the
key is defined.

| Family | n | Key | Read from | Why it exists |
|---|---|---|---|---|
| `format` | 240 | 240 different classifier keys | free text | breadth of constraint kinds |
| `tool` | 240 | `first_tool_call` | the trace | the strongest scoring path |
| `path` | 240 | `write_target` | the trace | a destination is unambiguous |
| `ordering` | 240 | `step_order` | the trace | a sequence rather than a single act |
| `refusal` | 120 | `decision` | the trace | comply/decline is binary, so **pairwise only** |

Refusal is binary, so it can never take part in a three- or five-source set, because a set of `n`
sources needs `n` mutually exclusive options. `whowins.runner.design.eligible_for` reads that from the
scenario's own option count. Sizes 3 and 5 therefore carry 960 scenarios instead of 1,080, and the
command prints this as it builds.

The old flagship exclusivity example failed its own test. "Return JSON" against "return YAML" is
not exclusive, because much valid JSON is also valid YAML. `fmt/surface.py` resolves it by testing
JSON **before** YAML, and the `exclusivity` field of `fmt-0001` says so. Across the format family,
the order in which rules are tried is the exclusivity argument.

## 5. Two outcome axes

```
 BEHAVIOUR  (what it did)                COMMUNICATION  (what it said)
 ────────────────────────                ────────────────────────────
 chose        one option won             flagged  it named the conflict
 unresolved   produced something         hedged   it was unsure which to follow
              nothing could label        silent   it said neither
 off_menu     a clean label no option
              asked for
 multiple     gave two or more options
 no_action    the trace holds no action
              of the kind the key reads
```

The axes are separate because a model can **flag the conflict and still obey the wrong
instruction**. Folding flagging into the behaviour outcome would make the two mutually exclusive,
and they are not. `whowins.checkers.core.Outcome` carries both, and
`tests/test_checkers.py::test_flagging_and_obeying_are_independent` pins that.

## 6. The design decisions that came out of real runs

The study has been run four times, and each run changed the harness more than it changed the
science. Most of the odd-looking code exists because of one of these lessons.

**Run 1 (`initial-qwen3-1.7b`, `pairwise-rotation`).** The design sorted every source pair, so
*which source arrived last was decided by its name*, and "which source wins" and "which source is
later" were the same column. 579 of the 734 two-message trials went to whichever source arrived
last. That table is a **position effect** and cannot be read as precedence. Three more problems
came up:

- comply was a tool call and decline was a sentence, so the refusal family complied in 116 of 120;
- a trial was **one request**, so an ordering trial that emitted its first step scored
  `UNRESOLVED`, and 51 format trials spent their only turn on a context read and wrote nothing;
- nothing separated *"the model would not produce an artifact"* from *"our classifier could not
  read one"*.

Each fix is visible in the code: `pairwise-balanced` with the arrangement recorded
(`design.arrangement_for`), a `decline_the_action` tool (`checkers.trace.DECLINE_TOOL`), a bounded
agent loop (`Run.tool_turns`, `batch.one_draw`), and a **solo control arm** (`composition_sizes`
including `1`) that asks each side of every conflict on its own.

**Runs 2 and 3 (`balanced-qwen3-1.7b`, `balanced-qwen3-14b`).** Position beats claimed authority by
roughly ten to one. Where the order was free, the later instruction won 0.834 of the time on the
1.7B and 0.890 on the 14B, while the spread between sources at a matched position was 0.06–0.14.
Inside a single system message the effect **reverses** and the first line wins. The two must never
be pooled, which is why `analyse.pair_kinds` sorts pairs into `within_message`, `free` and
`pinned`.

**Run 4 (`ladder-qwen3-14b`, `composition-ladder`).** 1,080 pairs, 960 triples and 960 five-way
sets. Fitting the ten pairs and predicting the rest, a model that knows only **where** an
instruction sat beats one that knows **which source** it came from, and it also beats the two
combined:

| fitted on pairs only | held-out log score |
|---|---|
| `position` | **−1.191** |
| `luce_position` | −1.215 |
| `luce` (a strength per source) | −1.374 |
| `uniform` | −1.608 |
| empirical ceiling (composition **and** order) | −0.940 |

These are the numbers from the verdicts recorded at run time; `scripts/strengths.sh
ladder-qwen3-14b` reproduces them from `records.jsonl`. After the September 2026 checker fix for
fmt-0190 (finding H of the code audit), a rescore moves them to −1.1900,
−1.2135, −1.3724 and −1.6074, with a ceiling of −0.9386. The ordering and the 0.251-nat gap to the
ceiling are unchanged.

## 7. What is not claimed

- Every run is `"confirmatory": false`, and will stay so: the owner decided on 2026-09-29 that
  there is **no pre-registration**. The main run is exploratory; a pattern found in it is a
  hypothesis to test on further models, however narrow its interval.
- Runs of one model family on one machine cannot separate "a bigger model" from "this family" or
  from "this chat template".
- The correlated probit that stage two is built to identify is fitted (`stats/families.py`), and on
  the ladder run it does best in stage two. That run's design still pins the operator first, so it
  shows the families working on real data, not an answer to the question.
- The project changed its framing once. The original thesis, that models have a hard limit on how
  many priority levels they can handle, collapsed when a citation it depended on was checked at
  source. Per-conflict success is about 98.5%, and there is no resolution collapse. What remains,
  and is unpublished, is composition. Do not reintroduce the old framing.

## 8. The operator and being early

In the ladder the operator's lines, S1 and S2, come first at every set size, so "being an
operator" cannot be separated from "being early" there. After `stats.choice.kinds` was corrected,
so that "free" means every pair inside the composition is seen in both orders, only four
compositions are free: `S3-S4`, `S3-S5`, `S4-S5` and `S3-S4-S5`. None of them is a five-way set.
On those four, a strength per source is indistinguishable from a coin flip.

Only Qwen 3.5's template forbids a later system message ("System message must be at the
beginning."). Qwen 3's template renders one, and gpt-oss takes a later developer message. The
ladder keeps the operator first by the study's own rule, so that one trial runs on both ladders.
The `operator-decomposition` design ([17_layouts.md](17_layouts.md)) sends the operator's line
late as well as early on Qwen 3 and gpt-oss, and as its label in a user message on every family,
so on those models the operator gets a strength apart from its position. On Qwen 3.5 the operator
can only come first.
