# 14 — Glossary

These are the terms this repository uses in its own way, in plain language. Where a word means
something narrower here than in general use, the narrower meaning is given.

---

## The data

**Base scenario.** Content only: a task plus five (or two) mutually exclusive instructions, each
with a deterministic checker. It says **nothing** about where an instruction came from. Base
scenarios are in `data/scenarios/`.

**Trial.** One thing you actually send to a model: a base scenario plus a claim about where each
instruction came from and where it sat. Trials are built by `whowins.runner.design`, and one scenario
produces many of them.

**Option.** One of a scenario's instructions, identified as `o1`…`o5`, with a `checker` string of
the form `key==value`.

**Family.** One of five kinds of scenario: `format`, `tool`, `path`, `ordering`, `refusal`. The
format family is scored by a classifier over free text, and the other four are scored from a
structured trace.

**Checker key.** The single-valued property that every option in a scenario reads:
`first_tool_call`, `write_target`, `step_order`, `decision`, or one of the 240 format keys.

**Exclusivity.** The argument that no single reply can satisfy two of a scenario's options. It is
both a prose field on every scenario and a property the code enforces, because every option reads
the same key and demands a different value.

**Seed family.** The idea behind a scenario, used to stop authors repeating each other. It is unique
on all 1,080 items, which is why it **cannot** be used to group them for a split.

**Cell.** One of the seven experiment designs that the worked trials demonstrate: decomposition,
composition, load vs conflict, declared tier, binding, authorship, harness vs model.

**Worked trial.** One of the 70 hand-written trials in `data/trials/`. They were written before the
renderer, so when the renderer reproduces them byte for byte it agrees with a person's decision.

## Sources and positions

**Source.** A place an instruction can claim to come from: a transport role plus a displayed
provenance. There are exactly five (`S1`…`S5`), derived from the composition cell's spans.

**Transport role.** The chat role the message actually arrives as: `system`, `developer`, `user`,
`tool` or `assistant`.

**Displayed provenance.** What the text *claims* about its origin: operator policy, repository
config, a user message, a tool result, a memory note. It is a claim made in prose, not a role.

**Declared rank.** An explicit priority number written into a span, such as `[priority: 3]`. It is a
**covariate and not a source**: a number attached to a span that already has a provenance.

**Surface.** How the instruction text is dressed: `plain`, `emphasis` ("IMPORTANT — … This is
mandatory."), or `fake_header` (a forged `SYSTEM:` prefix). `fake_header` is a *manipulation whose
effect is measured*, and it confers no authority.

**Position slot.** Where a span sits in the conversation, as an index. The analysis reads slot order
as position, which is why two spans may never share a slot.

**Arrangement.** One of the layouts a composition can take: whether the two operator lines are
reversed, and the order in which the non-operator sources and the task line appear. Arrangements are
enumerated, indexed and recorded per trial.

**Composition.** The set of sources that compete in one trial. `S3-S4-S5` is a composition of size
3.

**Free / pinned / within-message.** The three kinds of composition, according to whether position
can be read at all:

| kind | meaning | what it shows |
|---|---|---|
| **free** | *every* pair of sources inside it is seen in both orders | recency: the later instruction wins |
| **pinned** | some source can never sit later than another | recency *plus* whatever being an operator costs |
| **within-message** | every source is in the operator block, i.e. lines of one message | **primacy**: the *first* line wins |

**Operator channel.** The one role that carries operator instructions for a family: `system` for
Qwen and `developer` for gpt-oss. The ladder sends it **first**. Only Qwen 3.5's template requires
that; the `operator-decomposition` design also sends it last on Qwen 3 and gpt-oss.

**Layout design.** A design that moves one thing the ladder holds fixed and sends every item under
each of its layouts, so a difference between layouts is read within the item:
`operator-decomposition`, `one-message` and `realism` ([17_layouts.md](17_layouts.md)).

**Realism set.** 50 scenarios whose instructions are placed inside hand-written context (a system
prompt, a user message, a file read through a tool, saved notes) and sent both bare and in context.
Its items are in `data/realism/`.

**Solo arm / solo trial.** The same conflict with the other sources' turns deleted and nothing else
changed. It measures whether the model can produce that option *at all*, so that "cannot produce it"
is not mistaken for "declined to take it". `ladder-qwen3-14b` has no solo arm.

**Arm.** `pair` (a conflict) or `solo` (a control), recorded in `meta["arm"]`.

## Scoring

**Behaviour axis.** What the model *did*: `chose`, `unresolved`, `off_menu`, `multiple` or
`no_action`.

**Communication axis.** What the model *said*: `flagged`, `hedged` or `silent`. It is separate from
behaviour, because a model can flag the conflict **and** obey the wrong instruction.

**`chose`.** Exactly one option's demanded value was produced.

**`unresolved`.** Something was produced, and no rule could label it.

**`off_menu`.** A clean label the checker read, for a value that **no option in this trial asked
for**. The model did something definite that was not on the menu, which is different from "we could
not tell".

**`multiple`.** The reply gave two or more of the options, for example a hedge offering both. Only a
classifier key can produce it, because a trace has exactly one first tool call.

**`no_action`.** The trace holds no action of the kind this key reads.

**Sentinel.** `__unresolved__`, `__no_action__` or `__multiple__`. A test checks that none of them is
a valid option value anywhere in the collection.

**Artifact.** The thing an option asked the model to produce; the opposite of **talk**.

**Talk.** Anything addressed to the person who set the task instead of being the artifact: a
question, "I'll use snake_case", "Sorry, I can't help", an acknowledgement, a sign-off. **A reply
that only talks wins nothing.**

**Absence label.** A label meaning "no marker was used" (`no_indent`, `variants_avoided`,
`no_prompt`, `unnumbered`…). It cannot be told apart from the model producing nothing, so it must
require **positive evidence that real output exists**.

**Relevance gate.** The positive-evidence requirement a classifier applies before it may award an
absence label, or before it reads a reply at all (`artifact_text`).

**Bare-word rule.** A classifier rule that fires on a word every honest answer or restatement
contains ("menu", "cut", "UTC") instead of on the form the option asks for. It awards false wins.
Three were rewritten in September 2026 (finding H of the code audit).

**Trace.** The structured record of what the model did: its tool calls, in order, with their
arguments. It is the strong scoring path.

**Classifier.** A rule set over free text, for the format family. A classifier can *mislabel* a
reply, which is a different risk from ambiguity, and that is why the classifiers have adversarial
fixtures.

**Scored turn.** In a multi-turn reply, the last turn that is neither talk nor a wrap-up report
(`run._joined`). `run.answer_text(row)` recovers it from a stored record, and `analyse` diagnoses
unlabelled replies on it.

**Context tool.** `config_read` or `memory_read`. A read-only tool that the **trial** offers, so
that an instruction arriving in a tool result has a call to answer. It answers no option, and
`first_tool_call` skips it.

**Gated action** (`action_tool`). On a refusal item, the tool whose call *is* complying. Its
counterpart is `decline_the_action`, so both options are a call.

**Filler.** A non-conflicting instruction line the load cell adds so that prompt length stays
matched while the number of conflicts varies. Every filler in the bank is scored by code.

**Fault.** Something that went wrong in the plumbing and not in the model: unparseable tool
arguments, reasoning markers left in the answer, a checker that raised. It is recorded on the row,
and a row with a fault is not `usable`.

**Usable.** `finish_reason != "length"` and no faults. Unusable rows stay in the log; they just do
not count as behaviour.

## Running

**Run.** One named configuration in `configs/runs/`: a model, a machine, a decoding policy, a
design, how many sources compete, how many draws, and a base seed.

**Design.** How a run's trials are laid out: `pairwise-rotation`, `pairwise-balanced`,
`composition-ladder` or `composition-ladder-flat`. A change in layout gets a **new name** and never
changes what an old name builds.

**Draw.** One attempt at one trial. `repeats: 3` means three draws per trial, each with its own
seed.

**Breadth first.** Every trial's first draw, then every trial's second. A run stopped by the clock
then leaves a complete single-draw dataset instead of a third of a three-draw one.

**Agent loop / `tool_turns`.** A trial is not one request. While the reply contains tool calls, the
loop answers each call with a neutral stub result and asks again, up to `tool_turns` times. Every
completion is kept, and they are scored together.

**`stopped_by`.** Why the loop ended: `no_more_calls`; `turn_budget` when the model was still
calling tools when the budget ran out; `context_limit` when the server refused a later turn for its
length; `malformed_tool_call` when vLLM could not parse a gpt-oss tool-call header on any retry.
Many `turn_budget` rows mean the budget is too small, which is a fact about the **harness**.

**Stub result.** `{"ok": true}`, the same for every tool. A result that differed between tools would
give one option a task-merit advantage after the model had chosen.

**Serving stack / serving snapshot.** Everything that can move the numerics while the weights stay
the same: engine version, dtype, GPU, tensor-parallel size, chat template hash, attention backend.
It is hashed into `serving_fingerprint`. A vLLM upgrade or a different GPU starts a **new** snapshot.

**Environment.** One serving snapshot with a key: `v100-vllm085` or `sm80-vllm0280`.

**Deployment.** One model in one environment, with the serve file that starts it.

**Engine profile.** The rules of one engine *version*, read from that version's source and kept
**in code**, so that nobody can declare a behaviour in a config file that was never checked.

**Delivery guard** (`check_delivery`). Rejects messages that a chat format would change without
reporting it, so that what the model sees is what the record says.

**Checker fingerprint.** A hash recorded on every row as `checker_fingerprint`. It covers the source
of `src/whowins/checkers/` and of the four runner modules that also decide verdicts
(`checkers.SCORING_MODULES`: `response.py`, `run.py`, `fillers.py`, `tools.py`). Two runs scored on
either side of a change to any of them were scored by two different instruments.

**Rescore.** Applying today's checkers to replies already on disk. It costs no GPU time, can write
`rescored.jsonl`, and never writes to `records.jsonl`.

## Statistics

**Choice.** One measurement: some options competed, and one of them won, or none did. A choice is
not a trial (it has no templates, tools or repeats), so the same code reads a simulated world and a
real log.

**Abstention.** `won is None`. It is an outcome, not a missing value.

**Item.** The resampling unit, in practice the base scenario. Three draws of one scenario measure
one thing.

**Strength.** A source's Plackett-Luce / Bradley-Terry weight. It is defined only up to a positive
multiple, so it is always reported **normalised to sum to one**. A single strength means nothing on
its own; ratios between strengths do.

**Plackett-Luce / Bradley-Terry.** The model in which the chance that an option wins is its strength
divided by the sum over whichever options are competing. That property lets the model extrapolate
from pairs, and the counterexample worlds lack it.

**`luce`, `position`, `luce_position`, `luce_position_size`, `uniform`, `saturated`.** The six
estimators. `uniform` is the floor. `saturated` fits any data and **predicts nothing it has not
seen**, which makes it a useful null on held-out *items* and useless on held-out *compositions*.

**Held-out log score.** The average log probability the model gave to what actually happened, on data
it was not fitted on. Higher (closer to zero) is better. It is reported in **nats**.

**Nat.** The unit of a natural-log score. A gap of 0.1 nats per draw means one model assigns about
`e^0.1 ≈ 1.11×` the probability that the other does to what actually happened.

**Ceiling / headroom.** The best score any model could get on this data. `empirical_ceiling` is the
empirical distribution per **(composition, order)** cell, and headroom is how many nats short of it
each model falls. A saturated model is **not** the ceiling, because it is blind to arrangement.

**Coverage.** The share of a test set a model makes a prediction for. It is part of the score,
because a model that declines half the test set can look excellent on the half it kept.

**Clustered bootstrap.** Resampling **items**, never draws. Treating three draws of one scenario as
independent looks about 1.7 times more certain than the data are.

**Wilson interval.** A binomial confidence interval that stays inside [0, 1]. It is used because
several cells are close to 0 or 1, where the normal approximation runs off the scale.

**Identified / unidentified.** A parameter is identified when the data can pin it down. A
disconnected comparison graph, or a feature that is identically zero on the data, leaves parameters
unidentified, and the fitter **raises** instead of returning a number.

**Stage one / stage two.** The two stages of the composition test. Stage one fits the 10 pairs and
predicts every larger set without refitting anything; it is the high-risk test and the interesting
one. Stage two adds a four-triple slice and predicts the rest; the model is identified there, which
makes it the more robust result.

**Covering slice.** The fewest triples such that every source pair appears in at least one of them.
A pair covered by no triple is a correlation that stage two cannot estimate.

**Free prediction.** A composition where several sources demand the **same** action. An
independent-draw account and a consensus account predict different outcomes there, and a pair-only
fit commits to one of them in advance with no new parameters. Free predictions are never fitted on
and have not been sent yet; the statistics code cannot read them yet (finding Y).

**Pairwise insufficiency.** The fact that two distributions over rankings can have identical
pairwise win rates and a different three-way winner. More data does not help, because the two worlds
agree in the limit.

**Misspecification.** The world does not have the shape the model assumes. `ladder.misspecification`
prices it exactly, as a property of the world and the model and not of a sample.

**Power.** The fraction of simulated studies that answer a question correctly at a given size.
**Every curve is conditional on the planted effect**, and the code says so in its own output.

**Confounded.** Two things that this data cannot tell apart. The first run confounded *which source
wins* with *which source is later*, because the design sorted the sources by name.

**Confirmatory.** A run whose result may be used as evidence for a registered claim. Every run in
this repository declares `"confirmatory": false`, and there is no pre-registration, by the owner's
decision (2026-09-29): results are read and framed afterwards and tested on further models.

**Load bundle.** A hand-written replicate of the load cell (`data/load/lb-NN.json`): one task, six
component scenarios, a filler bank and ten trials on the worked cell's grid of `n` and `k`.

**Filler kind.** What a bundle's filler asks, from `fillers.KINDS` (`reply_words_under`,
`step_before_writing`, …). Its checker is built with the bundle's own project and step tools.

**Tier setup.** The one setup the `declared-tiers` design measures capacity in: the operator
states that lower numbers win, and two options arrive as repository configuration with a bracketed
rank. Rule direction and notation are held fixed.

**Item taste.** In the mixed model, an item's own preference for one of its options, `a[item,
option]`: the content term that balancing cannot cancel.

**Grouping factor.** A random shift of every source's log strength per level: the item's family in
one run; the model, and the harness where separable, across runs (`pooled.py`).

**Harness separability.** Whether a harness effect can be told from a model effect: only when some
model was served in more than one harness. The main run serves each model on one machine, so it
cannot.

## Process

**Planted fault.** A bug introduced on purpose to confirm that a test detects it. A planted fault
that is secretly a no-op gives a false negative, and that has cost time here three times.

**Frozen / re-freeze.** A split list is built once and committed. Rebuilding it is a
pre-registration decision that has to be recorded, and `splits.check` fails a list that no
longer matches the collection it was built from.

**Collection fingerprint.** Two hashes over the scenarios. `content` covers what the split was
computed from, and if it moves the split is invalid. `full` covers everything else, and an edit to
it is recorded but does no harm.

**Giveaway.** A warning that the task's own words single out one option, so a model could answer
without reference to any source. Giveaways are triaged, and the solo arm decides whether an item
works, not a keyword.

**ARBITER.** A proposed defence mechanism, demoted to an appendix and scheduled for phase 5. It has
no code.

**Capacity `R(q, D, H, S, V)`.** The largest ordered subset of declared tiers 1–12 for which every
required pair has a simultaneous lower confidence bound above `q`, for a given task distribution,
renderer, decoding policy and snapshot. It is an **operational** quantity, never a universal
constant. `stats/capacity.py` computes it with an upper bound too; no run sends tier conflicts yet.

**Variogram.** For the correlated probit, `Var(error_a − error_b)` for each pair of sources, which is
all of the error covariance that choices can reveal. Normalised to average 1; below 1, the two
sources' errors move together, and 0 means they have merged (a boundary fit).

**Regularity.** Adding a competitor never raises an option's chance of winning. Every random-utility
model obeys it, so a real violation is a context effect only a context model can fit.

**Decided draws.** The draws in which some option won. The families are compared on these, because
a shared model of abstaining would add the same amount to every family's log score.
