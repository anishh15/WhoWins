# 17 — The layout designs, the realism set and tiers 1 to 6

Built in October 2026, after an outside review of the study's plan, which these files do not
include. Three new
designs each move one thing the ladder holds fixed, and every item is sent under each of its
layouts, so a difference between layouts is read within the item. The tier design shrinks to
tiers 1 to 6. Like the rest of the main run, all of it is exploratory.

```
runner/layouts.py            the three designs: operator-decomposition, one-message, realism
validation/check_realism.py  is every realism batch fit to send?
stats/layouts.py             reads a run of any of the three, paired within the item
stats/paired.py              a rate over units and a paired difference; shared with load_cell
data/realism/                the hand-written items, written by an agent from a fixed prompt
```

---

## 1. A late operator message, and who will take one

In the ladder the operator's lines (S1, and S2 in the same message) always come first, so
"being the operator" cannot be told from "being early". Whether a later operator message can be
sent depends on the family:

| Family | A system or developer message after the first | Read from |
|---|---|---|
| Qwen 3 on vLLM 0.8.5 | rendered as its own turn | `configs/chat-templates/qwen3.jinja` line 31; vLLM 0.8.5 hands every message to the template in order and unchanged (`entrypoints/chat_utils.py`) |
| Qwen 3.5 on vLLM 0.28.0 | refused: "System message must be at the beginning." | the template |
| gpt-oss on vLLM 0.28.0 | rendered where it sits as a harmony developer message | vLLM lifts only a leading system or developer message into the preamble (`renderers/online_renderer.py`, `extract_instructions_from_messages`); the roster pins `VLLM_GPT_OSS_HARMONY_SYSTEM_INSTRUCTIONS=0` |

On Qwen 3 the operator-first rule is ours (`one-operator-message-per-trial`), kept so one trial
runs on both ladders. `serving.LATE_OPERATOR_WAIVABLE` names that reason, and
`late_operator_possible(family)` says whether a late operator can reach a family. A trial built
to send the operator late says so in `meta["operator_late"]`, and only then does
`check_delivery(..., late_operator=True)` waive the rule; a template's refusal is never waived.
The batch loop passes the same flag on every later turn.

## 2. `operator-decomposition`

Each of the 1,080 scenarios meets one of six operator pairs (S1 or S2 against S3, S4 or S5),
taken in turn within each family, so each family meets all six. Each item is sent four ways,
with the same two options each time:

| | operator first | operator last |
|---|---|---|
| real operator message | as in the ladder | the late operator |
| the operator's label in a user message | the label alone | the label alone, late |

The task comes last in all four. Which two options a pair carries, and which way round, turns
with a counter per pair, so every two of a scenario's five options meet both ways. On Qwen 3.5
"real, last" is not built: 3,240 trials instead of 4,320.

It gives, per model: what the role adds with position fixed, what position adds with the role
fixed, and what a late policy buys. Seen in both orders, S1 and S2 are free pairs here, so the
strengths fit can give the operator a strength that is not also "being first".

## 3. `one-message`

The user's line (S3) against the memory note (S5), in a quarter of the scenarios (every fourth by
id, 270 items), four ways: each in its own user message, or both inside the task's message, in
each order. A `Block` may now hold a `Task`, which renders the task line inside the message; a
trial still says its task once, and the collapsed renderers refuse a block as before.

The test runs found the later of two messages winning and the first line of one system message
winning. The ladder puts every source in its own message, so "the message is the unit" is built in
there. Here it is measured: the share of replies following the first-listed line, merged against
separate, paired within the item.

## 4. The realism set

The later instruction usually wins, but every trial so far was a few one-line commands. The
realism set places the instruction inside the text a real agent sees and sends each item both
ways.

- **Items.** 50 scenarios (25 tool, 25 path), picked once by domain and fixed in
  `data/realism/batches.json`, five batches of ten. Tool and path scenarios are scored from the
  trace (the first call, the write target), so the text around an instruction cannot leak into
  the verdict. Each item has four hand-written contexts (an operator prompt, a user message, a
  file returned by `config_read`, saved notes), each holding the slot `{{instruction}}` once.
  [data/REALISM-AUTHORING.md](../../data/REALISM-AUTHORING.md) is the specification, and
  [data/realism/README.md](../../data/realism/README.md) the prompt an agent is given per batch.
- **The validator.** `check_realism` fails a slot that is not a whole sentence or not in the middle
  60% of the context's words, a context outside its word range, and any tool name the scenario
  offers, option text, absolute path, another source's label, brace, or word about who outranks
  whom, and a sentence next to the slot that vouches for the instruction ("confirmed", "is
  current"). A run of ten words shared by two items fails as a template. A sentence that may steer the
  choice is a WARN for a person to read.
- **The design.** Each item under six pairs of its sources (S3-S4, S3-S5, S4-S5, and S1 against
  each), in both orders where the chat format allows (S1 last only where a late operator is
  possible), bare and in context, with the same options for all four. In context, the span's text
  is the source's context with the option's own text in the slot, after the source's usual label.
  24 trials an item, 18 on Qwen 3.5. The design runs the validator first and refuses to build from
  a failing batch, or before any batch exists.

## 5. Reading them: `scripts/layouts.sh RUN`

`whowins.stats.layouts` reads a run of any of the three. A reply counts for the source whose option it
chose; a reply that chose neither of the two is left out of the rates, and each layout's share of
replies that chose one is printed beside it.

| design | rate | contrasts, paired within the item |
|---|---|---|
| operator | the operator's line won, per layout, overall and against each other source | last minus first at each role; real minus label at each position |
| one-message | the first-listed line won, separate and merged | merged minus separate |
| realism | free pairs: the later line won; operator pairs: the operator won | context minus bare; last minus first, bare and in context |

The unit is the item. A rate is the mean of the items' rates; its interval is the wider of a t
interval over items and a Wilson interval over every draw, and a contrast's the wider of a t
interval over the items' differences and Newcombe's interval. That arithmetic now lives in
`stats/paired.py`, which the load-cell reader also uses.

## 6. Declared tiers 1 to 6

At 196 items for each of 66 tier pairs, one miss in a pair already fails 0.95, so a model that
obeys 99% of the time certifies nothing. `declared-tiers-6` uses tiers 1 to 6: 15 pairs, six a
scenario, 6,480 trials (half of `declared-tiers`), 432 items a pair. A pair then certifies 0.95
with up to nine misses; 0.99 needs 637 items and stays out of reach. Each tier pair takes every
two of a scenario's options in turn (36 to 40 times each), which the twelve-pair dealing left to
chance at six pairs a scenario, and the four winner cases fall exactly evenly. `declared-tiers` is
unchanged and frozen; every main tier config now names `declared-tiers-6`.

`capacity.run_capacity` reads a run over the tiers it measured. Over 1 to 12, a tier no trial used
counts as never ruled out and would lift the upper bound to 12.

## 7. Two smaller changes

- **Readable numbers.** `score.evaluate` reports `top1`, the share of draws whose winner the
  prediction rated highest (a tie shares the credit), and `ladder.headroom` the ceiling's own
  top-1 and each fit's share of the way from the `uniform` model to the empirical ceiling. On the
  14B ladder test run, `position` recovers 62% in stage one, with top-1 0.684, which is also the
  ceiling's.
- **Flagged, and still followed the later line.** `analyse`'s communication section splits silent,
  hedged and flagged by which instruction won: the later or an earlier one, and on a tier run the
  policy's winner or not.

`scripts/run_main.sh` sends the kinds in priority order, each in both modes before the next:
ladder, operator, realism, message, free, load, tier. `--only` and `--skip` choose kinds.
