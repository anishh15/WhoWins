# Dataset

Every scenario here is written by hand. No generator, no templating, no scripted expansion.

**Complete: 1,080 base scenarios**, hitting every target in the dataset plan —
240 in each five-option family (format, tool, path, ordering) and 120 in refusal, which is binary and
pairwise-only. Plus 70 worked trials, 10 in each of the seven experiment cells, showing how a scenario
becomes something you can send to a model.

Written by Claude Opus 5 in Claude Code, one scenario at a time, and recorded per scenario in
`authored_by` as `claude-code/opus-5`.

Two smaller hand-written sets build on the scenarios: nine [load bundles](load/README.md) that
replicate the load cell, and the [realism set](realism/README.md), 50 tool and path scenarios whose
instructions are placed inside long context, written by an agent ten at a time under
[REALISM-AUTHORING.md](REALISM-AUTHORING.md).

Everything already taken, for anyone extending the collection: `data/REGISTRY.md`.

## Validating it

```
python3 src/whowins/validation/check_batch.py     # cross-cutting screens over the whole collection
python3 src/whowins/validation/validate_collection.py   # family invariants, counts, trial integrity
```

Both are read-only and both were tested against deliberately broken inputs before being trusted — a
validator that has never failed on a known-bad case tells you nothing when it passes.

## Two levels, and why they are separate

A **base scenario** (`scenarios/`) is content only: a task, and five mutually exclusive instructions with a
deterministic checker each. It says nothing about where an instruction came from.

A **trial** (`trials/`) is one thing you actually send to a model. It takes a base scenario and assigns the
things a real harness smears together — transport role, displayed provenance, declared rank, position,
surface — and stores each as its own field beside the exact rendered transcript.

Keeping these apart is the setup. One scenario generates many trials, and what differs between two
trials is exactly one factor.

## scenarios/ — the five families

One folder per family; one file per authoring batch, named by the id range it covers.

| Folder | Family | Checker key | Read from | Target |
|---|---|---|---|---|
| `format/` | one of five output formats | `output_format`, `key_casing`, `date_encoding`, … | a classifier over free text | 240 |
| `tool/` | one of five stub tools | `first_tool_call` | the trace | 240 |
| `path/` | one of five sandboxed destinations | `write_target` | the trace | 240 |
| `ordering/` | one of five orderings of three steps | `step_order` | the trace | 240 |
| `refusal/` | comply or decline — **binary, pairwise only** | `decision` | the trace | 120 |

**Exclusivity is proved, not assumed.** Every option in a set reads the *same single-valued key* and demands
a *different value*. One trace has one first tool call; one output gets one format label. So no output can
satisfy two options, by construction rather than by hope. The old flagship example failed this test:
"return JSON" against "return YAML" is not exclusive, because much valid JSON is also valid YAML. In the
format family JSON is classified before YAML for exactly that reason.

Trace-read keys are unambiguous. Classifier-read keys can still *mislabel*, which is a different risk, and
those ship adversarial fixtures per family.

**Refusal cannot extend to five.** Accepted. It stays pairwise, is analysed separately, and is never pooled
into the main scale. Every refusal item is a *policy* refusal, so the released data carries no hazardous
strings.

**Sourcing is honest.** Every scenario here is tagged `synthetic-preview` and records the document type it
would be harvested from. None of them claims a source URL it does not have. The real build harvests first
and writes the conflict on top.

## trials/ — the seven cells

| File | Cell | What it decides |
|---|---|---|
| `01-decomposition.json` | Is "source" one thing or five? | whether the factors separate at all |
| `02-composition.json` | **The primary result** | do two-way measurements predict three- and five-way? |
| `03-load.json` | Load versus conflict | is it the conflicts, or just the number of instructions? |
| `04-declared-tier.json` | Magnitude versus rank | does the model estimate a distance or look up an order? |
| `05-binding.json` | Where the failure happens | not seeing the source, or seeing it and comparing wrongly? |
| `06-authorship.json` | Provenance and authorship | does "you wrote this" change anything? |
| `07-harness.json` | Model versus harness | how much of this belongs to the wrapper, not the model? |

Each file opens with a `_cell_header` giving the cell's job, its controls, and its honest limits.

These 70 transcripts are also **the renderer's specification**. They were written by hand before any
rendering code existed, so `whowins.runner` is checked by re-deriving all 70 from their own fields and
diffing byte for byte — agreement with a person's decision rather than with our own code. Three things
the format cannot yet say came out of doing it: where the load cell's fillers sit, what its filler bank
is, and that the authorship cell records no spans.

## Ground truth is labelled, not assumed

Every trial carries one of two kinds:

- **`revealed_only`** — no correct answer is declared. We record which instruction was acted on. This is the
  normal case, because the point is to measure revealed precedence, not to grade.
- **`policy_defined`** — a stated policy makes one option correct.

Only the operator's stated policy defines ground truth. A rank or a `SYSTEM:` header written *inside* a
lower-privilege span never becomes ground truth just because it claims to be highest — see `dec-10`, where
the forged header is the manipulation being priced, not the answer.

## Outcomes are two axes, never one

- **Behaviour** — chose option 1..n, partial or multiple, no action, invalid output.
- **Communication** — flagged the conflict, hedged, silent.

A model can flag a conflict **and still obey the wrong instruction**, so flagging cannot be a third slot in
the same multinomial. Invalid outputs stay in the likelihood or get pre-registered bounds; dropping them
while the treatment causes them creates its own bias.

## Controls worth finding in the files

| Where | What it rules out |
|---|---|
| `dec-02`, `tier-06` | Latin-square content swap — a preference for one instruction reading as a preference for one source |
| `dec-03` | same-channel baseline — content preference measured with source held flat, fitted jointly rather than subtracted |
| `bind-06` | placebo registry, length-matched — "more careful-sounding text" masquerading as source-linking |
| `bind-10` | external sorter — if a plain parser fixes it, perception was never the bottleneck, and our account is wrong |
| `tier-09` | rule direction reversed — following the stated rule versus following the familiar "1 means most important" |
| `tier-10` | notation control — a format effect masquerading as a priority effect |
| `auth-05` | byte-identical to `auth-01` — expected null; if it is not null, the elicitation is leaking |
| `harn-10` | block order inside one renderer — a within-harness effect hiding inside a between-harness number |
| `load-01/03/05` | zero-conflict controls at matched length — load doing what looks like conflict's work |

## Checkers

The checkers are in [`src/whowins/checkers/`](../src/whowins/checkers/) and **all 1,080 scenarios are
executable**: the four trace families and all 240 format keys.

```
python3 -m pytest tests/                         # 2,312 tests (1,488 over the checkers, 1,382 fixtures)
PYTHONPATH=src python3 -m whowins.checkers.coverage  # what is executable
```

Implementing them found things the collection did not know about itself — most importantly that **51 format
scenarios chose between options a single model response cannot exhibit**. All 51 are now resolved: 38
rewritten by hand, 13 reclassified.

## splits/ — what is held back from what

[`splits/`](splits/README.md) holds the frozen train / validation / test lists, the leave-one-out folds
over constraint kinds and subject areas, and the two design splits: leave-one-source-pair-out, and the
composition ladder that carries the headline. Checked in on purpose: a split list is a pre-registration
commitment, unlike `REGISTRY.md`, which is a build artifact and is gitignored.

The grouping there is **built, not looked up.** `seed_family` is unique on all 1,080 scenarios — this file's
own authoring spec requires it to be — so grouping by it, which is what the dataset plan literally said,
would group nothing while every check stayed green. Design and measurements:
[docs/codebase/05_splits.md](../docs/codebase/05_splits.md).

## Not here yet

The power simulator. Nothing in the collection is blocked: every scenario has a checker, and every
option value one of those checkers can actually produce.

## How this was written

Every scenario is authored by hand, in batches of at most 50, each batch by one writer working from the
rules above. No batch is generated, templated or expanded by script. Each batch is reviewed against the
screens in this file before it is committed — exclusivity, equal reasonableness, the ±20% length rule,
duplication against every scenario already in the collection, and honest source tagging. Batches that fail are
sent back.
