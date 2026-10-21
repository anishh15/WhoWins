# Runbook

Every command, in order. Reasons: [configs/README.md](configs/README.md).

Two machines, one model served at a time. **DGX-1 (`v100-vllm085`)** runs Qwen 3 on vLLM
0.8.5.post1 in float16; **80 GB cards (`sm80-vllm0280`)** run Qwen 3.5 and gpt-oss on vLLM
0.28.0 in bfloat16, and a copy of each of the Qwen 3 32B's main runs (section 7a).

## 0. Once per machine

**Its own conda environment**, never a share of another project's: an upgrade made for something
else would silently become a different serving snapshot. Pins: `configs/environments.json`.

```bash
git clone <repo> && cd "WhoWins"

scripts/create_env.sh --print v100-vllm085   # the exact commands, run nothing
scripts/create_env.sh v100-vllm085           # build it (DGX-1). 80 GB cards: sm80-vllm0280
conda activate ipb-v100                      # or: ipb-sm80
```

That is `python=3.10.18` plus `vllm==0.8.5.post1 torch==2.6.0 transformers==4.57.1 pytest`.
transformers is pinned because vLLM 0.8.5 asks only for `>=4.51.1`, and a fresh install would pull
a 5.x it was never built against. Nothing here touches `slmjury`.

```bash
python3 -m pytest -q tests/                  # 2,383 pass, 4 skipped
PYTHONPATH=src python3 -m whowins.runner.serving check   # 15 models, 16 deployments, 10 policies, 214 runs

scripts/download_models.sh --print all       # what it would fetch
scripts/download_models.sh qwen3-1.7b        # or: all
export HF_HUB_OFFLINE=1                      # after downloading, so nothing is fetched mid-run
```

## 1. Serve the model

```bash
scripts/serve.sh --print qwen3-1.7b          # the exact command, run nothing
scripts/serve.sh qwen3-1.7b                  # picks free GPUs, port 8000
```

On a shared machine it takes free cards and refuses to start beside another job (exit 4).

```bash
scripts/serve.sh --gpus 2,3 --tp 2 qwen3-14b        # the cards you want
scripts/serve.sh --gpu-mem 0.85 --max-seqs 32 qwen3-8b   # headroom; requests in flight
scripts/serve.sh --any-gpu qwen3-1.7b               # skip the free-card check
CUDA_VISIBLE_DEVICES=5 scripts/serve.sh qwen3-1.7b  # already set? it is left alone
scripts/serve.sh qwen3-1.7b --port 8001             # anything else goes to vllm serve
```

`--tp`, `--gpu-mem` and `--max-seqs` override the serve file. vLLM takes the command line over the
config, so that is a **different serving snapshot**: the script says so loudly, and it belongs in
the run's notes. On 32 GB V100s: 0.6B–8B one card, 14B two, 32B four.

## 2. Check the server

```bash
scripts/preflight.sh qwen3-1.7b              # on the same host as the server
```

Exit 0 all good, 1 wrong, 3 something could not be checked from here (usually the chat-template
hash, if the cache is elsewhere). It reads `/version` and `/v1/models` only.

## 3. Run the trials

**`balanced-qwen3-1.7b` is the run to send.** `initial-qwen3-1.7b` is done and kept; its design
decided which source came last by the source's name, so its numbers cannot separate precedence
from position.

```bash
scripts/run_trials.sh balanced-qwen3-1.7b --dry-run    # build all 3,240, send none
scripts/run_trials.sh balanced-qwen3-1.7b --limit 20   # a smoke test
scripts/run_trials.sh balanced-qwen3-1.7b              # the whole run
```

3,240 trials — 1,080 conflicts and the 2,160 solo controls, one per side — at 3 draws each, so
9,720 requests, plus whatever the agent loop adds.

**Set `--concurrency`, and do not expect the server to do it for you.** It defaults to 1: one
request in flight, the next sent only once that reply is complete. `--max-num-seqs` on the server
is a *ceiling* on what vLLM may batch and cannot create work — with a client sending one at a time
you see `Running: 1 reqs, Pending: 0` however high the ceiling is, and one stream decoding a 1.7B
on a V100 runs around 28 tokens/s because the whole weight set is read out of memory for every
token. Several streams read it once and advance together, so the aggregate rate climbs nearly
linearly until the KV cache fills.

```bash
scripts/run_trials.sh balanced-qwen3-1.7b --concurrency 8 --timeout 1800
```

Start at 8, watch `Running:` climb to 8 and keep an eye on `GPU KV cache usage`, then raise it if
there is room; keep it at or under `--max-num-seqs` so the ceiling never binds. **Raise `--timeout`
with it**: each stream is slower when they share the card, so a long reply that finished inside
600 s alone can cross it under concurrency, and a crossed timeout is a transport failure that costs
three attempts.

`--concurrency` above 1 changes vLLM's batch mix, which moves numerics slightly. The number used is
on every row, so a run that changed it half way is still analysable — which is the reason to keep
the rows already on disk rather than start again.

**The same command resumes.** Every answer is appended to `results/balanced-qwen3-1.7b/records.jsonl`
and fsynced before the next request leaves, so a trial already answered is never sent again. Ctrl-C,
run the same line, it carries on. A line cut off mid-write costs that one trial. Draws go out
breadth first — every trial once, then every trial again — so a run stopped early is a whole
single-draw dataset rather than a third of one. A run holds its log while it sends, so a second
`run_trials.sh` on the same run is refused before it sends anything; use `--concurrency` instead.

```bash
scripts/run_trials.sh balanced-qwen3-1.7b --report          # where it stands
scripts/run_trials.sh balanced-qwen3-1.7b --base-url http://gpu-box:8000 --timeout 900
```

Only transport failures retry — refused, timeout, 5xx, and the two 4xx codes that describe the
server's load rather than the request (429 too many requests, 408 request timeout). Each is logged
as its own line. **An answer is never re-rolled**: a truncated or unscorable reply is a
measurement, and sending it again until it looks better is selection on the outcome.

**While it runs it says so.** A bar on stderr carrying the count, the rate and an estimate; retries,
truncations and failures as warnings above it; and all of it at DEBUG in
`logs/run-<run>-<when>.log` whatever the terminal was asked to show. Redirect the output and the bar
becomes whole lines instead of one enormous one. Every flag: [the flag reference](#the-flags).

## 4. After the run

```bash
cat results/balanced-qwen3-1.7b/summary.json          # written after every pass
```

Code, configs and data live in git; run records stay outside it (`results/` is ignored).

`summary.json` reports `behaviour` and `behaviour_usable` separately — the second leaves out
truncations and replies whose reasoning the server never separated. Neither is dropped, because
the treatment can cause them. `stopped_by` is worth a look before anything else: a run heavy with
`turn_budget` has a `tool_turns` too small, and that is a harness fact, not a model one.

## 5. Scoring again, later

A checker corrected after a run is re-applied to the replies already on disk. No GPU, no server.

```bash
scripts/rescore.sh balanced-qwen3-1.7b                # what today's checkers say
scripts/rescore.sh balanced-qwen3-1.7b --changed 20   # the trials whose verdict moved
scripts/rescore.sh balanced-qwen3-1.7b --write        # writes rescored.jsonl beside the log
```

`records.jsonl` is never touched: it is what came back from the server.

## 6. Reading it

```bash
scripts/analyse.sh balanced-qwen3-1.7b                       every section
scripts/analyse.sh balanced-qwen3-1.7b --section position solo
scripts/analyse.sh balanced-qwen3-1.7b --json report.json    the same numbers, to a file
```

Descriptive counts and Wilson intervals over what came back. **It fits nothing and predicts
nothing** — the strengths fit and the composition test are `scripts/strengths.sh`, the power
simulation is `scripts/phase1.sh`, and this is not them.

Read the sections in this order, because the later ones are worthless if an earlier one is wrong:

| Section | The question |
|---|---|
| `scoring` | Were these verdicts made by the checkers installed **now**? Two runs scored either side of a checker fix were scored by two different instruments, and comparing them reads the instrument's change as the model's. Free: every record carries `whowins.checkers.fingerprint()`, a hash of the checkers and of the runner modules that also decide a verdict. |
| `hygiene` | Is this **one** run? One serving snapshot, one concurrency, how much was truncated or faulted. Everything below is void if this says no. |
| `outcomes` | What the model did, per family and per arm. **The two arms are not comparable per trial** — a solo trial shows one option of five and a conflict shows two, so the conflict arm scores `chose` more for a purely arithmetic reason. |
| `position` | Does the later instruction win? Split three ways: pairs whose order was free, pairs the chat format pins, and two labelled lines of one message — which point opposite ways and must never be pooled. |
| `sources` | Does the source matter once position is held fixed? The overall column is what a sorted design reports and is worth little; the matched one is the comparison. |
| `solo` | What the model can do with nobody disagreeing, compared **per option**, and how well that predicts winning a conflict. The three-row table is a **mix**: where both options are always producible exactly one wins, so that cell is pinned near 0.5 by construction and a better model puts more of its conflicts there — dragging its own `always` row down as it improves. Compare runs on the cross-tabulation below it. |
| `unresolved` | Why a reply could not be labelled: empty, truncated, only talk, or artifact-shaped and unlabelled. **The last bucket is the only one that can be our fault** — read it first after a run. |
| `items` | **Which scenarios measured nothing here, by name**, split into the ones where no artifact was produced (the model) and the ones that were artifact-shaped on most draws and still unlabelled (ours). Names rather than counts, because a count cannot be intersected with the next run's. |
| `repeats` | How much of the outcome was the draw rather than the item. |
| `communication` | Whether the model ever said the instructions disagreed. |

**Write the JSON for every run.** Two rungs of the ladder compared by two hand-written scripts are
not comparable; compared by the same command they are.

## 7. Two runs side by side

```bash
scripts/analyse.sh balanced-qwen3-1.7b --json a.json
scripts/analyse.sh balanced-qwen3-14b  --json b.json
scripts/compare.sh a.json b.json                  # add --json out.json to keep it
```

Some questions cannot be asked of one run at all. *"This model could not produce that option
unopposed"* is about the model; *"no model can"* is about the item, and only the second is grounds
to go and read the scenario. `compare` intersects the named lists from each run's `items` section
and lines up the numbers `analyse` already computed.

**It exits non-zero if the runs were scored by different checkers**, because then every column
mixes the instrument with the model. Put them on one instrument first:

```bash
scripts/rescore.sh <run_id> --write
scripts/analyse.sh <run_id> --log results/<run_id>/rescored.jsonl --json <run_id>.json
```

It fits nothing and **tests nothing**: whether two intervals overlap is not a result, and the
strengths fit that could say so does not exist yet. What it produces is a reading list.

## 7a. The main run

Every model has its own configs, `configs/runs/main-<kind>-<model>-<mode>.json`: 13 Qwen models
with thinking off and on, and the two gpt-oss models with thinking on only, which is all gpt-oss
has. Each (model, mode) has seven kinds of run, listed in the order they are sent, most
important first:

| Kind | Design | Trials | Draws |
|---|---|---:|---:|
| `ladder` | `composition-ladder-flat`, sizes 1, 2, 3, 5 | 12,840 | 38,520 |
| `operator` | `operator-decomposition`: the operator's line first or last, as a real operator message or its label in a user message | 4,320 (3,240 on Qwen 3.5) | 12,960 (9,720) |
| `realism` | `realism`: the hand-written items of `data/realism/`, bare and in context | 24 an item (18 on Qwen 3.5) | 3,600 with 50 items (2,700) |
| `message` | `one-message`: the user's line and the memory note in their own messages or inside the task's | 1,080 | 3,240 |
| `free` | `free-predictions`, the 80 sets where sources share an option | 3,240 | 9,720 |
| `load` | `load-bundles`: the ten worked load trials and ten from every bundle in `data/load/` | 100 with nine bundles | 300 |
| `tier` | `declared-tiers-6`: two options under declared tiers 1 to 6, six pairs a scenario | 6,480 | 6,480, one each |

The `realism` design builds only from batches that pass `check_realism`, and refuses to build
before any is written; `--skip realism` leaves it for later.

The tier runs take one draw a trial, the only main runs that do: capacity keeps one draw per item
and pair, so a repeat would certify nothing.

Thinking off samples with `study-nothink` and thinking on with `study-think`; gpt-oss uses
`study-think-gpt-oss`, the same numbers at high reasoning effort. Start the model's server, then
send every one of its runs in turn; the same command resumes, and flags go to every run:

```bash
scripts/serve.sh qwen3.5-27b
scripts/run_main.sh qwen3.5-27b --dry-run                      # build and check every run
scripts/run_main.sh qwen3.5-27b --concurrency 16 --timeout 1800
scripts/run_main.sh qwen3.5-27b --only ladder                  # one kind, both modes
```

`run_main.sh` sends each kind in both modes before the next kind starts. To finish one kind on
every model before starting the next, run it per kind: serve a model, `--only` that kind, stop
the server, next model.

Reading a free-prediction run needs the ladder run of the same model and mode, because nothing in
it is fitted:

```bash
scripts/strengths.sh main-ladder-qwen3.5-27b-think \
    --free results/main-free-qwen3.5-27b-think/records.jsonl
scripts/capacity.sh main-tier-qwen3.5-27b-think                # R(q) on declared tiers
scripts/load_cell.sh main-load-qwen3.5-27b-think               # load versus conflict
scripts/layouts.sh main-operator-qwen3.5-27b-think             # operator, message or realism
scripts/pool.sh main-ladder-qwen3.5-9b-think main-ladder-qwen3.5-27b-think   # across models
```

**The Qwen 3 32B on the 80 GB cards.** Every 32B run has a copy for the 80 GB cards,
`main-<kind>-qwen3-32b-<mode>-sm80`, with the same settings and seed as the DGX-1's. Since
2026-10-11 those copies are the ones to use for the 32B. The DGX-1 keeps running its own copies,
which are kept only to show how much the serving software moves a result. A Qwen 3 size trend
that includes the 32B mixes vLLM 0.28.0 and bfloat16 into its top rung and has to say so.

```bash
scripts/serve.sh --env sm80-vllm0280 qwen3-32b                 # two 80 GB cards
scripts/preflight.sh qwen3-32b --environment sm80-vllm0280
scripts/run_trials.sh main-tier-qwen3-32b-think-sm80 --dry-run
```

Every main config says `"confirmatory": false`: there is no pre-registration (decided 2026-09-29),
so every result is exploratory. Records stay outside git.

## 7b. Sending a set bigger than a pair

Every run so far sent pairs. `composition-ladder` sends triples and the five-way
set too, which is the data the study's headline needs and has never had. A new run
names `composition-ladder-flat` instead: the same trials, with every source carrying
every option equally often and no option tied to a position. `--balance` shows both
in its `option spread` and `option last` columns.

```bash
scripts/design.sh ladder-qwen3-14b --balance              # READ THIS FIRST
scripts/run_trials.sh ladder-qwen3-14b --dry-run          # build 3,000, send none
scripts/run_trials.sh ladder-qwen3-14b --concurrency 16 --timeout 900
```

**`--concurrency` is not optional here either.** It defaults to 1 — one request in
flight — and the five-way trials are the longest conversations this study builds, on
a model that generates about a fifth as fast per stream as the 1.7B. Runs 2 and 3 did
9,720 draws in about two and a quarter hours at 16; at 1 the same work takes most of a
day. Stopping and restarting costs nothing: the log is the checkpoint, so a resume
sends only the draws that have no answer.

| | |
|---|---|
| What it sends | 1,080 pairs + 960 triples + 960 five-way = 3,000 trials, 9,000 draws at 3 repeats — the same size as `balanced-qwen3-14b`. |
| Sizes | 2, 3 and 5. The dataset plan declares that ladder; four-way sets are enumerated in `data/splits/set.json` under `not_in_declared_ladder` and are refused by name, because adding a rung is a scope decision. |
| Refusal is not in it above a pair | A set of n sources needs n mutually exclusive options and refusal has two, comply and decline. That is why sizes 3 and 5 carry 960 scenarios and not 1,080, and the command says so as it builds. |
| No solo arm | `composition_sizes` leaves 1 out. Adding it emits a matched solo for every source of every composition — ten more trials per scenario — and quadruples the run. Solo ability for the pairs is already measured on this model by run 3. |

**`--balance` is not optional reading.** It prints, per composition, how many of
its arrangements are used and how evenly each source sits in each slot. A
non-zero slot spread means a source's strength is confounded with its position,
and that is what the first run's headline turned out to be. It should be 0%
everywhere.

## 8. The statistics

Phase 1 of the plan, and it is a **gate** rather than a task: *"Simulate the whole
pipeline; confirm it recovers known parameters and detects the published
pairwise-insufficiency counterexamples. Power from simulation."*

```bash
scripts/phase1.sh                       # the gate, about 50 s; non-zero if a check fails
scripts/phase1.sh --full                # more replicates and sizes, same checks, about 5 min
scripts/strengths.sh balanced-qwen3-14b # a strength per source, from a real run
```

`phase1` is **entirely simulated**. It plants a truth, draws data, fits it back, and
asks whether the answer came out — plus the thing the project turns on: two worlds
with *identical* pairwise win rates whose three-way winner is a different option. A
fit that saw only pairs returns the same answer for both, so it is wrong in at least
one, and the command prices that in nats rather than asserting it.

`strengths` fits a real run. On a run with a set above a pair — `ladder-qwen3-14b` — it
also runs **the composition test**: fit the pairs, predict the triples and the five-way set
it never saw. On a pairs-only run (`balanced-*`) it says the test cannot run. Either way it
prints three fits that assume different things and never pools them:

| Fit | What it assumes |
|---|---|
| free pairs only | Nothing. The order really varied, so a strength and a position effect come apart. Only the sources appearing in a free pair get one. |
| whole design | That being first means the same thing where the operator is pinned as where it is not. Gets all five sources at that price. |
| within-message pair | Nothing, but it is a **different effect**: two labelled lines of one system message, where both runs found the *first* line winning. Pooling it with the others averages primacy with recency. |

On a run with a set above a pair it then prints **THE FAMILIES**: the composition test again,
with every model family fitted the same way on the draws where some option won.

| Family | What it adds to Plackett-Luce |
|---|---|
| `thurstone` | normal errors instead of Gumbel ones, drawn independently. Fits pairs; predicts larger sets differently |
| `probit` | lets every pair of sources' errors move together. Pairs cannot identify that, so stage one refuses it by name; the four triples of stage two can |
| `context` | each source pulls on the others it competes with. On pairs it is a pair-interaction model; the pulls are shrunk by an amount chosen by cross-validation over items |
| `mixed` | random effects: each item's own taste for each of its options, and a family's shift of each source. An item seen in training is predicted from its own tastes; variances by Laplace, which errs low |

Each also has a `_position` form. The block ends with **regularity**: every one of those families
says adding a competitor never raises an option's share, so a real rise is something only a
context model can fit. Read the block this way:

- Its log scores are per *decided* draw, so they are not comparable with THE COMPOSITION TEST above
  it, which also scores the draws where no option won.
- A family that says REFUSED could not be identified from that stage's data, and the reason is printed.
- A probit note saying "a boundary fit" means some sources' errors merged; their variogram of 0.00
  is a limit the fit ran into, not a measurement.
- A regularity row also shows what `luce_position` predicts for the same rise. If position alone
  predicts it, it is not a context effect.

**Capacity** comes from a `declared-tiers-6` run: `scripts/capacity.sh main-tier-<model>-<mode>`
prints R(q) at 0.9, 0.95 and 0.99 with a lower and an upper bound. **Model effects** come from
pooling runs: `scripts/pool.sh RUN RUN ...` fits strengths the runs share and how far each model
shifts them, and fits a harness effect only when some model was served on more than one machine.
**The load cell** comes from a `load-bundles` run: `scripts/load_cell.sh main-load-<model>-<mode>`
prints, for each trial of the grid, the share of conflict groups chosen, of replies choosing in
every group, of filler lines kept and of whole tasks done, each a mean over bundles; then the
paired contrasts that set conflict against length, and the conjunction against independence.
**The operator test, the one-message test and the realism set** come from their own runs:
`scripts/layouts.sh main-<kind>-<model>-<mode>` prints each layout's rate among the replies that
chose one of the two lines, and the contrasts that pair two layouts of one item: what the
operator's position and its real role each add, whether the first line wins inside a user
message, and whether "the later instruction wins" survives realistic context. In THE COMPOSITION
TEST each fit's log score now has its top-1 accuracy beside it, and the share of the way from the
`uniform` model to the empirical ceiling that it recovers.

## Inspecting the design

```bash
PYTHONPATH=src python3 -m whowins.runner.design balanced-qwen3-1.7b           # counts and balance
PYTHONPATH=src python3 -m whowins.runner.design balanced-qwen3-1.7b --show 3  # rendered trials
```

Three trials per scenario: one conflict between two of the five sources, and the same conflict
twice more with one side deleted. Every source pair gets 108 scenarios, and within each pair the
arrangement cycles, so nothing arrives last because of its name. Nothing is random — the same
config builds the same list.

## When something is wrong

| Symptom | What it means |
|---|---|
| `serve.sh` exit 3 | This Python's vLLM is not the version this machine pins — usually the wrong environment. It prints the `conda activate` line to run. |
| `serve.sh` exit 4 | Not enough free cards. Name others with `--gpus`, wait, or `--any-gpu`. |
| preflight exit 1 | The server is not serving what the run expects — wrong model, context length or template. |
| `config error:` from the runner | The request is wrong; not retried. Read the message. |
| Many `failure` lines | The server died. Restart it, run the same command. |
| Many `truncated` in the summary | Replies hitting 32,768 tokens — small-model repetition. Report it before changing anything. |
| Many `turn_budget` in `stopped_by` | The agent loop ran out of turns with the model still calling tools. `tool_turns` in the run config is too small — but say so before changing it, because the budget is part of the harness the study measures. |
| The server logs `Running: 1 reqs, Pending: 0` | The client is sending one request at a time. `--max-num-seqs` is a ceiling and cannot create work; pass `--concurrency`. |
| `429` or `408` in the failure lines | The server or a proxy in front of it is saturated. These are retried, not fatal. If they are constant, lower `--concurrency`. |
| Nothing on screen while it runs | `--progress none`, `-q`, or stderr is redirected somewhere you are not reading. The file under `logs/` has everything either way. |

## The checks, any time

```bash
python3 -m pytest -q tests/
PYTHONPATH=src python3 -m whowins.validation.check_batch
PYTHONPATH=src python3 -m whowins.validation.validate_collection
PYTHONPATH=src python3 -m whowins.splits.check
PYTHONPATH=src python3 -m whowins.runner.serving check
```

---

## The flags

Every flag every command here takes, with its default. The shell scripts in `scripts/` pass their
arguments straight through, so `scripts/run_trials.sh RUN --limit 20` is
`python3 -m whowins.runner.batch RUN --limit 20`.

### Output flags, on every command

`whowins.runner.batch`, `whowins.runner.rescore`, `whowins.runner.design`, `whowins.runner.preflight`,
`whowins.splits.build` and `whowins.splits.check` all take these, and they mean the same thing in each.
Knowing one command is knowing all of them; `tests/test_logs.py` fails if one drops them.

| Flag | Type | Default | What it does |
|---|---|---|---|
| `-v`, `--verbose` | switch | off | DEBUG on stderr — every request, turn and retry. **The file always holds DEBUG whatever this is set to**; this changes only what the terminal shows. |
| `-q`, `--quiet` | switch | off | Warnings and errors only on stderr. The report a command prints to *stdout* is never suppressed. |
| `--log-file PATH` | path | `logs/<tool>-<subject>-<when>.log` | Where the DEBUG file goes. |
| `--no-log-file` | switch | off | Write no file. stderr only. |
| `--progress {auto,plain,none}` | choice | `auto` | `auto`: a redrawn bar on a terminal, whole lines when redirected. `plain`: always whole lines. `none`: nothing. Only on `batch` and `rescore`, the two that take long enough to need it. |

Nothing above ever writes to stdout. That is deliberate and load-bearing: `serving shell KEY` is
`eval`'d by `scripts/serve.sh`, `serving gpus` is substituted into a command line, and
`batch --report` prints JSON — a status line on stdout would corrupt all three.

### `scripts/run_trials.sh` — `python3 -m whowins.runner.batch RUN_ID`

Send a run's trials to a server that is already up and score every reply. The same command resumes.

| Flag | Type | Default | What it does |
|---|---|---|---|
| `RUN_ID` | positional, required | — | A run in `configs/runs/`: `initial-qwen3-1.7b`, `balanced-qwen3-1.7b`. |
| `--base-url URL` | url | `http://localhost:8000` | The vLLM server to send to. |
| `--out PATH` | path | `results/<run_id>/records.jsonl` | The records log to append to *and resume from*. Point it elsewhere and the run no longer knows what is already answered. |
| `--concurrency N` | int | `1` | Requests in flight. 1 keeps every draw in its own batch; anything higher is much faster and changes vLLM's batch mix, which moves numerics slightly. Recorded on every row. See [§3](#3-run-the-trials). |
| `--timeout SECONDS` | float | `600.0` | How long one request may take before it counts as a transport failure. **Raise it when you raise `--concurrency`.** |
| `--retries N` | int | `3` | Attempts per turn after a transport failure, backing off 2 s, 4 s, … capped at 30 s. Only transport failures are retried; an answer is never re-rolled. |
| `--limit N` | int | all | Send at most this many pending draws, then stop. The smoke test before the whole run. |
| `--api-key KEY` | string | `$VLLM_API_KEY` | Bearer token, if the server wants one. |
| `--dry-run` | switch | off | Build and check every request; send none. Catches a config or delivery problem in seconds instead of an hour in. |
| `--report` | switch | off | Read the log and print where the run stands as JSON. Sends nothing. |
| `--skip-preflight` | switch | off | Send without first checking the server's version, served model, context length and chat template. |
| `--allow-unpinned-engine` | switch | off | Record a server whose engine version is not the pinned one. The records then describe a different serving snapshot, and say so. A server that does not answer `/version` is recorded as `unreported`, and only with this flag. |

Exit status: `0` everything scored, `1` at least one trial failed, `2` the config is wrong,
`130` interrupted (every answer so far is on disk; the same command carries on).

### `scripts/rescore.sh` — `python3 -m whowins.runner.rescore RUN_ID`

Score a finished run again with today's checkers, from the replies already on disk. No GPU, no
server. **`records.jsonl` is never written to.**

| Flag | Type | Default | What it does |
|---|---|---|---|
| `RUN_ID` | positional, required | — | A run in `configs/runs/`. |
| `--log PATH` | path | `results/<run_id>/records.jsonl` | The records log to read. |
| `--write` | switch | off | Also write `rescored.jsonl` beside the log. |
| `--changed N` | int | `0` | Print the first N trials whose verdict moved. `0` prints the count alone. |

Exit status: `0`, or `2` if the log and the run config do not describe the same run.

### `scripts/analyse.sh` — `python3 -m whowins.runner.analyse RUN_ID`

Report what a finished run did, from the replies on disk. No GPU, no server, writes nothing unless
asked.

| Flag | Type | Default | What it does |
|---|---|---|---|
| `RUN_ID` | positional, required | — | A run in `configs/runs/`. |
| `--log PATH` | path | `results/<run_id>/records.jsonl` | The records log to read. |
| `--section NAME…` | choice, repeatable | all | Which sections to print: `scoring`, `hygiene`, `outcomes`, `position`, `sources`, `solo`, `unresolved`, `items`, `repeats`, `communication`. |
| `--json PATH` | path | none | Also write every number to this file, so two runs can be compared without re-deriving anything. |

Exit status: `0`, or `2` if the log and the run config do not describe the same run.

### `scripts/compare.sh` — `python3 -m whowins.runner.compare REPORT.json REPORT.json [...]`

| Flag | Type | Default | What it does |
|---|---|---|---|
| *(positional)* | two or more paths | — | reports written by `scripts/analyse.sh --json`. One report compares with nothing and exits 2. |
| `--json` | path | none | also write every number and **every named scenario** to this file. |

Exit codes: `0` comparable, `1` the runs were scored by different checkers (or one carries no
fingerprint), `2` a report could not be read. Plus the output flags above.

### `scripts/phase1.sh` — `python3 -m whowins.stats.phase1`

| Flag | Type | Default | What it does |
|---|---|---|---|
| `--full` | flag | off | more replicates and more item counts. Slower, and exactly the same checks against exactly the same thresholds. |
| `--seed` | int | `20260915` | the simulation seed. Every draw here is pseudo-random and reproducible from it. |
| `--json` | path | none | also write every number, including each check's verdict, to this file. |

Exit `0` if every check passed, `1` if any failed. Plus the output flags above.

### `scripts/strengths.sh` — `python3 -m whowins.stats.strengths RUN_ID`

| Flag | Type | Default | What it does |
|---|---|---|---|
| *(positional)* | run id | — | a run in `configs/runs/`. |
| `--log` | path | `results/<run_id>/records.jsonl` | which records to read. Point it at `rescored.jsonl` to fit today's verdicts. |
| `--seed` | int | `20260915` | seeds the item hold-out split and the clustered bootstrap. |
| `--json` | path | none | also write every number to this file. |
| `--free` | path | none | also score the free predictions in this records log (a `main-free-…` run of the same model and mode) with fits made on this run's pairs. |
| `--no-families` | flag | off | skip THE FAMILIES block (Thurstone, the correlated probit, the context model, the mixed model, regularity). It is the slow part: about a minute of an 80-second report on the ladder run. |

### `scripts/capacity.sh` — `python3 -m whowins.stats.capacity RUN_ID`

Capacity on declared tiers, from a finished `declared-tiers-6` or `declared-tiers` run, over the
tiers the run measured. Calls no model.

| Flag | Type | Default | What it does |
|---|---|---|---|
| *(positional)* | run id | — | a run whose design is `declared-tiers-6` or `declared-tiers`. |
| `--log` | path | `results/<run_id>/records.jsonl` | which records to read. |
| `--q` | numbers | `0.9 0.95 0.99` | the reliabilities to certify, R(q) at each. |
| `--alpha` | number | `0.05` | the error the lower and upper bounds share, held over every pair measured. |
| `--unit` | `item` or `draw` | `item` | `item` keeps one draw per item and pair, exact under any dependence; `draw` counts every draw as independent, a sensitivity reading only. |
| `--json` | path | none | also write every number to this file. |

### `scripts/load_cell.sh` — `python3 -m whowins.stats.load_cell RUN_ID`

The load cell, from a finished `load-bundles` or `load-cell` run. Calls no model.

| Flag | Type | Default | What it does |
|---|---|---|---|
| *(positional)* | run id | — | a run that sent load trials. |
| `--log` | path | `results/<run_id>/records.jsonl` | which records to read. Point it at `rescored.jsonl` to read today's verdicts. |
| `--alpha` | number | `0.05` | one minus the coverage of every interval. |
| `--json` | path | none | also write every number to this file. |

### `scripts/layouts.sh` — `python3 -m whowins.stats.layouts RUN_ID`

The operator test, the one-message test or the realism set, from a finished run of that design.
Every rate is a mean over items and every contrast pairs two layouts of one item. Calls no model.

| Flag | Type | Default | What it does |
|---|---|---|---|
| *(positional)* | run id | — | a run whose design is `operator-decomposition`, `one-message` or `realism`. |
| `--log` | path | `results/<run_id>/records.jsonl` | which records to read. |
| `--alpha` | number | `0.05` | one minus the coverage of every interval. |
| `--json` | path | none | also write every number to this file. |

### `scripts/run_main.sh MODEL`

Every main run of one model, against a server that is already up. The kinds go in priority order,
each in both thinking modes: ladder, operator, realism, message, free, load, tier.

| Flag | Type | Default | What it does |
|---|---|---|---|
| `--only` | kinds | all | only these kinds, comma-separated, still in priority order. |
| `--skip` | kinds | none | every kind but these. |
| *(anything else)* | | | passed to every `scripts/run_trials.sh`, `--dry-run` and `--concurrency` among them. |

### `python3 -m whowins.validation.check_realism [BATCH ...]`

Checks the realism batches in `data/realism/` against [data/REALISM-AUTHORING.md](data/REALISM-AUTHORING.md):
each batch's ten assigned scenarios in order, one slot per context in the middle 60% of its words,
each context within its word range, and no tool name, option text, absolute path, another source's
label or word about who outranks whom, and no sentence next to the slot that vouches for the
instruction. Any run of ten words in two items fails as a template. A WARN marks a sentence that
may steer the choice. Exit 1 on any FAIL.

### `scripts/pool.sh` — `python3 -m whowins.stats.pooled RUN_ID [RUN_ID ...]`

One fit across two or more finished runs: strengths they share, a random shift of each source per
model, and per harness where some model was served in more than one.

| Flag | Type | Default | What it does |
|---|---|---|---|
| *(positional)* | run ids | — | two or more runs, read from `results/<run_id>/records.jsonl`. |
| `--json` | path | none | also write every number to this file. |

### `scripts/preflight.sh` — `python3 -m whowins.runner.preflight MODEL`

Check a running server against the pins of the environment it belongs to. Reads `/version` and
`/v1/models` and the chat template in this machine's Hugging Face cache. Runs the model on nothing.

| Flag | Type | Default | What it does |
|---|---|---|---|
| `MODEL` | positional, required | — | A model key from `configs/models.json`. |
| `--environment KEY` | string | the model's first | Which environment's server this is, for a model served in more than one (the 32B on the 80 GB cards: `sm80-vllm0280`). |
| `--base-url URL` | url | `http://localhost:8000` | The server to check. |
| `--cache-dir PATH` | path | `$HF_HUB_CACHE`, else `$HF_HOME/hub` | Where to look for the chat template. |
| `--timeout SECONDS` | float | `10.0` | How long to wait for the two endpoints. |

Exit status: `0` everything passed, `1` something failed, `3` nothing failed but a check could not
be made from here — usually the template, when the cache is on another machine.

### `scripts/design.sh` — `python3 -m whowins.runner.design RUN_ID`

What a run would send, and how it balances. Builds nothing that is sent.

| Flag | Type | Default | What it does |
|---|---|---|---|
| `RUN_ID` | positional, required | — | A run in `configs/runs/`. |
| `--show N` | int | `0` | Print the first N trials fully rendered, as the model would receive them. `0` prints the counts and the composition balance only. |
| `--balance` | flag | off | Per composition: how many of its arrangements are used, and how evenly each source sits in each slot and carries each option. **Read it before a run, not after.** A non-zero slot spread means a source's strength is confounded with its position — which is what the first run's headline turned out to be. For a tier run it prints each tier pair's items, how evenly the four winner cases fall and which options meet; for a load run, the trials per bundle and per (n, k). |

### `scripts/serve.sh MODEL` and `scripts/create_env.sh` / `scripts/download_models.sh`

Shell, not Python, and the only commands here that start or fetch anything.

| Command | Flag | Default | What it does |
|---|---|---|---|
| `serve.sh` | `MODEL` | required | A model key. Anything after it goes to `vllm serve` unchanged — `--port 8001`, say. |
| | `--print` | off | Print the exact command and run nothing. |
| | `--env KEY` | the model's first | Which environment to serve it in. The 32B is served in two: `--env sm80-vllm0280` for its 80 GB copy. |
| | `--gpus 0,1` | free cards | Serve on the cards you name, checked for being free. |
| | `--tp N` | the serve file's | Tensor-parallel size. **An override is a different serving snapshot** and is printed loudly. |
| | `--gpu-mem F` | the serve file's | Fraction of each card's *total* memory. Same warning. |
| | `--max-seqs N` | vLLM's own (256) | Ceiling on sequences batched at once. Same warning. It is a ceiling, not a target: what fills it is the client's `--concurrency`. |
| | `--any-gpu` | off | Skip the free-card check. |
| `create_env.sh` | `ENVIRONMENT` | lists them | `v100-vllm085` or `sm80-vllm0280`. Builds that machine's conda environment. |
| | `--print` | off | Print the commands and run nothing. |
| `download_models.sh` | `MODEL…` or `all` | required | Fetch the pinned weights into the Hugging Face cache. |
| | `--print` | off | Print what would be fetched and fetch nothing. |

Exit status for `serve.sh`: `3` this Python's vLLM is not the pinned version, `4` not enough free
cards.

### `python3 -m whowins.runner.serving SUBCOMMAND`

The configs, read back. **Its stdout is machine-readable and is consumed by the shell scripts.**

| Subcommand | What it prints |
|---|---|
| `check` | Whether the models, machines, policies and runs agree with each other and with the study's rules. The one to run after editing any config. |
| `keys` | Every model key, one per line. |
| `env [ENVIRONMENT]` | With no argument, every environment and who runs it. With one, the conda commands that build it — what `create_env.sh --print` shows. |
| `shell KEY [ENVIRONMENT]` | Shell variable assignments for that deployment. **`serve.sh` runs `eval` on this.** |
| `gpus KEY [ENVIRONMENT] [--need N] [--want 0,1]` | Which GPU indices to use, comma-separated. |
| `download [--print] KEY… \| all` | Fetch the pinned weights, or print what would be fetched. |

### The collection and the splits

| Command | Flag | Default | What it does |
|---|---|---|---|
| `whowins.validation.check_batch` | `[BATCH_FILE]` | whole collection | Cross-cutting screens. A batch file focuses the per-scenario report; duplication is always screened against everything. Exit `1` on any FAIL. |
| `whowins.validation.validate_collection` | — | — | Family invariants, counts, trial integrity. Exit `1` on any FAIL. |
| `whowins.validation.build_registry` | — | — | Regenerate `data/REGISTRY.md`. The one validation script that writes. |
| `whowins.validation.check_load` | `--lines` | off | Every load bundle in `data/load/`: the grid, verbatim lines, scorable fillers, rendering, and one token length per n-level under both pinned Qwen tokenizers. `--lines` prints every line's length. Exit `1` on any FAIL. |
| `whowins.checkers.coverage` | — | — | How many scenarios are executable, by family. |
| `whowins.splits.check` | `--exclude ID…` | none | Scenario ids a proposed exclusion would remove; prints the balance left. |
| | `--exclude-file PATH` | none | The same ids from a file, one per line, added to `--exclude`. |
| `whowins.splits.build` | `--dry-run` | off | Print the summary and write nothing. **Without it this rewrites five frozen pre-registration files** — read the summary first, and record why a re-freeze was needed. |

Those three validation scripts run either way, `python3 src/whowins/validation/check_batch.py` or
`PYTHONPATH=src python3 -m whowins.validation.check_batch`. They print a report to stdout and take
none of the output flags: a report is not a log.
