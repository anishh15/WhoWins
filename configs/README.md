# Serving the models

Everything needed to serve the study's fifteen models on the two machines that run them, and to make
sure each model sees exactly what the record says it saw. Nothing in this repository runs a model.
The scripts are for the GPU servers.

| Path | What it is |
|---|---|
| `environments.json` | The two machines: engine, version, GPU class, number format, the conda environment each runs in, who runs each |
| `models.json` | The fifteen models, each pinned to one commit, and where each one is served |
| `vllm/<key>.yaml` | The exact `vllm serve` settings for one model on one machine |
| `decoding.json` | The sampling settings a request carries, by name |
| `runs/initial-qwen3-1.7b.json` | The first run, done: Qwen 3 1.7B over every scenario, `pairwise-rotation`. Kept so it can be rebuilt, not to be repeated |
| `runs/balanced-qwen3-1.7b.json` | The second run, done: the same conflicts under `pairwise-balanced`, each side also asked alone, three draws each, a six-turn agent loop |
| `runs/balanced-qwen3-14b.json` | The third run, done: the second run on Qwen 3 14B, with only the weights and the seed changed |
| `runs/ladder-qwen3-14b.json` | The fourth run, done: `composition-ladder` on Qwen 3 14B, pairs, triples and the five-way set, three draws each |
| `runs/main-<kind>-<model>-<mode>.json` | The main run, 196 configs: seven kinds, `ladder` (`composition-ladder-flat`, sizes 1, 2, 3, 5), `operator` (`operator-decomposition`), `realism`, `message` (`one-message`), `free` (`free-predictions`), `load` (`load-bundles`) and `tier` (`declared-tiers-6`), for every Qwen model with thinking `nothink` and `think`, and for gpt-oss with `think` only. They differ only in model, mode and seed; see runbook.md, section 7a |
| `runs/main-<kind>-qwen3-32b-<mode>-sm80.json` | Fourteen copies of the Qwen 3 32B's main runs, served on the 80 GB cards. Each matches its DGX-1 twin in every field but `environment`, `run_id` and `_about`, the seed included. These are the copies to use for the 32B |
| `chat-templates/` | Copies of the three Qwen chat templates, for the tests |

The scripts are in [`../scripts/`](../scripts/). The code that reads all of this, and refuses to go
on when any two files disagree, is [`src/whowins/runner/serving.py`](../src/whowins/runner/serving.py).

A run config carries three settings the first run did not have. **`design`** names how the trials
are laid out; `pairwise-rotation` sorted every source pair, so which source arrived last was
decided by its name, and `pairwise-balanced` replaces it. Sets above a pair need a ladder, and a
new run names `composition-ladder-flat`, which deals every option to every source equally often.
**`composition_sizes`** says how many
sources compete: `1` is the control arm, the same conflict with the other source's turn deleted
and nothing else touched. **`tool_turns`** bounds the agent loop — `1` is a single request, which
is what cut 29 ordering trials off after their first step. All three are recorded on every row,
because all three are part of the harness the study is separately measuring.

## Two machines

The DGX-1 cannot run Qwen 3.5: vLLM dropped Volta after 0.19, and RHEL 7.9's glibc 2.17
stops any newer PyTorch or vLLM installing, so the newest vLLM that runs there is 0.8.5 — which
predates Qwen 3.5. Qwen 3 it runs today, and has. So the study runs two ladders, one on each machine.

| | `v100-vllm085` | `sm80-vllm0280` |
|---|---|---|
| Machine | DGX-1, 8 × Tesla V100-SXM2 32 GB (compute 7.0) | 80 GB cards, compute 8.0 or newer |
| Engine | vLLM 0.8.5.post1, V0 engine, XFormers attention | vLLM 0.28.0, V1 engine |
| Environment | `ipb-v100`: python 3.10.18, torch 2.6.0, transformers 4.57.1 | `ipb-sm80`: python 3.12, openai-harmony 0.0.8 |
| Number format | float16 | bfloat16 |
| Models | Qwen 3: 0.6B, 1.7B, 4B, 8B, 14B, 32B | Qwen 3.5: 0.8B–122B-A10B; gpt-oss 20b, 120b; a copy of each of the Qwen 3 32B's fourteen main runs |
| Thinking split by | this package (`reasoning_separation: client`) | the server's qwen3 parser |
| GPUs | shared, so `serve.sh` takes free ones and refuses to share a card | exclusive |

**float16, not bfloat16.** vLLM refuses bfloat16 below compute capability 8.0 — *"Bfloat16 is only
supported on GPUs with compute capability of at least 8.0"* (`vllm/worker/worker.py`). The
checkpoints ship bfloat16 and are cast on load. That is a real difference between the ladders and it
is recorded in every run.

**V0, and said so.** vLLM 0.8.5's V1 engine needs compute 8.0 (*"Need at least Ampere for now"*,
`vllm/engine/arg_utils.py`), so it falls back to V0 on a V100. `VLLM_USE_V1=0` states the choice
rather than leaving it to a fallback that a later version might change.

**A shared machine.** vLLM takes a fraction of each card's *total* memory, not of what is free, so
starting beside another job either fails at startup or starves it. `scripts/serve.sh` asks
`whowins.runner.serving` for free GPUs, exports `CUDA_VISIBLE_DEVICES`, and exits 4 if there are not
enough.

## The models

| Key | Hugging Face id | Commit | Kind | Size | Machine | GPUs |
|---|---|---|---|---|---|---:|
| `qwen3-0.6b` | `Qwen/Qwen3-0.6B` | `c1899de2` | dense | 0.6B | V100 | 1 |
| `qwen3-1.7b` | `Qwen/Qwen3-1.7B` | `70d244cc` | dense | 1.7B | V100 | 1 |
| `qwen3-4b` | `Qwen/Qwen3-4B` | `1cfa9a72` | dense | 4B | V100 | 1 |
| `qwen3-8b` | `Qwen/Qwen3-8B` | `b968826d` | dense | 8B | V100 | 1 |
| `qwen3-14b` | `Qwen/Qwen3-14B` | `40c06982` | dense | 14B | V100 | 2 |
| `qwen3-32b` | `Qwen/Qwen3-32B` | `9216db57` | dense | 32B | V100; also 80 GB | 4; 2 |
| `qwen3.5-0.8b` | `Qwen/Qwen3.5-0.8B` | `2fc06364` | dense | 0.8B | 80 GB | 1 |
| `qwen3.5-2b` | `Qwen/Qwen3.5-2B` | `15852e8c` | dense | 2B | 80 GB | 1 |
| `qwen3.5-4b` | `Qwen/Qwen3.5-4B` | `851bf6e8` | dense | 4B | 80 GB | 1 |
| `qwen3.5-9b` | `Qwen/Qwen3.5-9B` | `c2022362` | dense | 9B | 80 GB | 1 |
| `qwen3.5-27b` | `Qwen/Qwen3.5-27B` | `fc05daec` | dense | 27B | 80 GB | 2 |
| `qwen3.5-35b-a3b` | `Qwen/Qwen3.5-35B-A3B` | `59d61f3c` | mixture of experts | 35B, 3B active | 80 GB | 2 |
| `qwen3.5-122b-a10b` | `Qwen/Qwen3.5-122B-A10B` | `dc4d3484` | mixture of experts | 122B, 10B active | 80 GB | 8 |
| `gpt-oss-20b` | `openai/gpt-oss-20b` | `6cee5e81` | mixture of experts | 21B, 3.6B active | 80 GB | 1 |
| `gpt-oss-120b` | `openai/gpt-oss-120b` | `b5c939de` | mixture of experts | 117B, 5.1B active | 80 GB | 1 |

Every id was checked on the Hugging Face Hub on 2026-09-12, and each is pinned to the commit the Hub
reported that day; full commits are in `models.json`. The Qwen models are the chat-trained ones, not
base models. The V100 GPU counts are for float16 weights on 32 GB cards: 14B needs two, 32B four.

Two families are compared across recipes at matched size — 122B-A10B with gpt-oss-120b on total
size, 35B-A3B with gpt-oss-20b on active size, both mixtures of experts on both sides. The two Qwen
ladders are also matched rung by rung (`generation_pairs` in `models.json`), but **that comparison is
confounded**: different engine, different GPU, different number format. What separates them is a
bridge — serving one Qwen 3 model on the 80 GB machine as well, which needs only a second entry
under that model's `deployments`. The 32B has had one since 2026-10-10, but as a stand-in, not a
bridge: each of its runs is used from whichever machine finishes it first, so no run is analysed
from both ([below](#the-qwen-3-32b-on-both-machines)).

## On a server, step by step

1. **Build this machine's environment**: `scripts/create_env.sh v100-vllm085`, then
   `conda activate ipb-v100`. The study gets **its own** conda environment on each machine, never a
   share of another project's: it pins an engine and a transformers version, and an upgrade made for
   something else would silently become a different serving snapshot, so a run weeks apart would not
   be comparable with one before it. The pins are `conda` in `environments.json` and nowhere else --
   `create_env.sh --print` shows the exact commands, and loading the configs checks those pins
   against the engine version, the harmony version and whatever `libraries` says the machine
   reports. Keep `pip freeze` with each run.
2. **Download** the weights your machine serves, at the pinned commit:
   `scripts/download_models.sh qwen3-1.7b`, or `all`. `--print` shows what it would fetch without
   fetching.
3. **Serve**: `scripts/serve.sh qwen3-1.7b`. It checks the engine version, picks free GPUs where the
   machine is shared, sets the environment, and runs `vllm serve --config configs/vllm/qwen3-1.7b.yaml`.
   `--print` shows the command without running it. Extra flags are passed on; any but `--host`,
   `--port` and `--api-key` change something measured, so record them.
4. **Check the server**: `scripts/preflight.sh qwen3-1.7b`, on the same machine. It reads `/version`
   and `/v1/models`, which do not run the model, and checks the hash of the chat template the engine
   loaded. It exits 0 when all is well, 1 when something is wrong, and 3 when a check could not be
   made from where it ran.
5. **Record the hardware.** `stack_for()` in `whowins.runner.serving` takes the deployment and what the
   server reported, and builds the stack every record carries.

`PYTHONPATH=src python3 -m whowins.runner.serving check` checks every file here against every other.

After downloading, `HF_HUB_OFFLINE=1` stops anything being fetched mid-run. gpt-oss also needs the
harmony vocabulary; on a server without internet, pre-download the tiktoken files and set
`TIKTOKEN_ENCODINGS_BASE`, as vLLM's gpt-oss recipe says.

## What each serve setting is for

Both engines' sources were read for each of these.

| Setting | Why |
|---|---|
| `revision`, `tokenizer-revision` | The exact commit, so the weights, tokenizer and chat template cannot change under us. |
| `generation-config: "vllm"` | Left at its default, vLLM fills every sampling setting a request leaves out from the model's own file. Qwen 3 ships temperature 0.6, top-p 0.95, top-k 20 on every rung; Qwen 3.5 27B and 122B ship 0.6, 35B ships 1.0, the rest ship none. |
| `no-enable-prefix-caching: true` | A cached prefix was computed inside another batch, and caching for Qwen 3.5's linear-attention layers is still experimental. Off everywhere. Written this way because `enable-prefix-caching: false` is silently dropped if the flag is ever renamed, which would leave caching on. |
| `dtype`, `kv-cache-dtype: "auto"` | Stated, not inferred, and equal to the machine's: float16 on the V100, bfloat16 on the 80 GB cards. gpt-oss's config names no dtype at all. |
| `gpu-memory-utilization: 0.9` | vLLM's own default, stated. It is a fraction of each card's total memory, which is why a shared machine needs a free card rather than a spare few GB. |
| `seed: 0` | The engine's seed. Each request also carries its own. |
| V100: `no-enable-chunked-prefill: true` | vLLM 0.8.5 turns chunked prefill on by itself above 32K tokens of context. On the V100s its prefill path compiles a Triton kernel that fails (`LLVM ERROR: Failed to compute parent layout for slice layout`), and the first chunked prompt kills the engine. With it off, each prompt is prefilled whole, and vLLM's memory profile runs one 40,960-token prompt, which leaves a little less room for the KV cache. The 80 GB cards run vLLM's V1 engine, which always chunks, so their files carry no such line. |
| `max-model-len: 40960` | Room for a 32,768-token answer plus an 8,192-token prompt. vLLM does not refuse a prompt that leaves too little room; it quietly shortens the answer's budget, so where an answer got cut off would depend on the prompt's length. It is also Qwen 3's whole native context. The longest worked-trial prompt is 737 tokens on Qwen and 437 on gpt-oss. |
| `tensor-parallel-size` | Set for the machine's cards. Change it for yours, then keep it fixed: it changes the numerics, and it is recorded. |
| Qwen 3: `tool-call-parser: "hermes"` | What Qwen's own documentation prescribes for Qwen 3, and what vLLM 0.8.5 has — there is no `qwen3_coder` in that version, and the Qwen 3 template emits hermes-style `<tool_call>` JSON. The 32B's file for the 80 GB cards keeps it: vLLM 0.28.0 has `hermes`, and its `qwen3_coder` reads Qwen 3.5's XML calls. |
| Qwen 3 on the 80 GB cards: `reasoning-parser: "qwen3"` | That machine splits the thinking on the server. vLLM 0.28.0's `qwen3` parser reads the request's `enable_thinking`: off, the whole reply is the answer; on, everything up to `</think>` is reasoning. |
| Qwen 3.5: `tool-call-parser: "qwen3_coder"`, `reasoning-parser: "qwen3"` | What the model cards and vLLM's recipes prescribe. The reasoning parser keeps the model's thinking out of the answer that gets scored. |
| Qwen 3.5, and Qwen 3 on the 80 GB cards: `default-chat-template-kwargs: {"enable_thinking": false}` | A safety net. vLLM's Qwen parser assumes thinking is on when a request does not say, while the 0.8B and 2B templates assume it is off. Every request says anyway. The flag does not exist in vLLM 0.8.5, so the V100 files carry none. |
| gpt-oss: `tool-call-parser: "openai"` | What vLLM's gpt-oss recipe prescribes; naming a parser is also what makes vLLM read the reply through its harmony parser. |
| both families: `enable-auto-tool-choice: true` | Tools offered with `tool_choice: auto` need it, and it needs a tool parser. |
| V100: `VLLM_USE_V1=0` | The engine core, stated rather than left to a fallback. |
| gpt-oss: `VLLM_SYSTEM_START_DATE=2026-09-11` | Without it, vLLM writes the current date into every gpt-oss prompt, so the same trial is a different prompt on a different day. `serve.sh` sets it. |
| gpt-oss: `VLLM_GPT_OSS_HARMONY_SYSTEM_INSTRUCTIONS=0` | The default, stated. Turned on, vLLM moves a conversation's first instruction into the harmony system message even when it was sent as developer, so the role would depend on position. |
| 80 GB machine: `VLLM_USE_RUST_FRONTEND=0` | The default, stated. The Rust front end builds prompts with different code from the code that was read. |

Left out on purpose, and refused by `whowins.runner.serving` if a serve file adds them: speculative
decoding, which changes the draws; `--language-model-only`, a second code path;
`--trust-remote-code`, since none of these repositories ships custom code; any chat-template
override; and, on vLLM 0.8.5 only, `--reasoning-parser`, `--enable-reasoning` and
`--default-chat-template-kwargs`, for the reasons below.

## Who splits the thinking, and why it differs

A thinking model writes its reasoning and then its answer. Only the answer is scored, so something
has to separate them.

On the 80 GB machine the server does it: vLLM 0.28.0's `qwen3` reasoning parser reads the request's
`enable_thinking` and splits accordingly.

**On the V100 machine no parser can.** vLLM 0.8.5 has no `qwen3` parser, and the one it does have,
`deepseek_r1`, returns *the whole reply as reasoning and nothing as content* whenever the reply
contains no `</think>` — which is every reply with thinking off, because the template closes the
block inside the prompt. Qwen's own documentation says so: *"As of vLLM 0.8.5,
`enable_thinking=False` is not compatible with this feature."* Every format scenario and every
decline would have scored as no answer.

So that environment starts no reasoning parser, records `reasoning_separation: client`, and
`whowins.runner.response.split_reasoning` does the split from the raw text. It is the only piece of this
pipeline the server does not do, and it is tested against both shapes a reply takes:

- Told to think, a **Qwen 3.5** prompt ends with `<think>` already open, so the reply carries only
  the closing tag.
- Told to think, a **Qwen 3** prompt ends after `assistant` with nothing prefilled, so the model
  writes its own opening tag — and a Qwen 3 reply with no tag at all is an *answer*, not thinking.
  That difference is recorded per family as `thinking_prefills_open_block`, and checked against the
  templates themselves.

A reply that opened a block and never closed it holds no answer, and is recorded as such rather than
scored — the opposite of what the 0.8.5 parser would have done with the same text. One cost is
carried and named: without a reasoning parser, the engine's tool parser reads the whole reply, so a
`<tool_call>` the model only *considered* inside its thinking would be reported as a call it made.
That is recorded as a fault on the attempt, and it cannot arise at all with thinking off, which is
the initial run's mode.

## The Qwen 3 32B on both machines

Since 2026-10-10 the 32B is deployed on the 80 GB cards as well, with `vllm/qwen3-32b-sm80.yaml`, so
that its main runs can be sent there. Since 2026-10-11 all fourteen are, every kind with thinking off
and on, and these copies are the ones to use for the 32B, so the whole 32B runs on one machine. The
DGX-1 keeps running its own 32B copies, which are kept only to show how much the serving software
moves a result.

The serve file is the DGX-1's with what the machine forces changed: bfloat16, no chunked-prefill
line, the `qwen3` reasoning parser, the same server default as the Qwen 3.5 files, and
tensor-parallel size 2, because about 65 GB of weights on one 80 GB card would leave too little KV
cache for a single 40,960-token conversation. The run configs, `main-<kind>-qwen3-32b-<mode>-sm80`,
keep their twin's seed, so both copies build the same trials and ask for the same seed on every
draw.

Commands for this deployment name its environment: `scripts/serve.sh --env sm80-vllm0280
qwen3-32b` and `scripts/preflight.sh qwen3-32b --environment sm80-vllm0280`. Without it they mean
the first deployment listed, the DGX-1's, which is what the DGX-1's scripts rely on.

One reading differs between the two: a Qwen 3 thinking reply with no tag at all is an answer to the
DGX-1's client split and reasoning to vLLM 0.28.0's parser. None turned up in 70,504 DGX-1
thinking turns read.

## What every request carries

`decoding.json` names ten policies. Every setting is sent with every request, so nothing is left to
the server.

**Two study policies, one per mode.** Every Qwen model of either generation runs at one of these.

| Policy | Thinking | Temperature | top-p | top-k | min-p | penalties |
|---|---|---:|---:|---:|---:|---|
| `study-nothink` | off | 0.7 | 0.8 | 20 | 0 | none |
| `study-think` | on | 0.6 | 0.95 | 20 | 0 | none |

Both are a recommended setting on **every** Qwen card in the study:

- Non-thinking is what all six Qwen 3 cards give for `enable_thinking=False` (*"Temperature=0.7,
  TopP=0.8, TopK=20, and MinP=0"*), and what the Qwen 3.5 4B-and-larger cards give as *"Instruct (or
  non-thinking) mode for general tasks"*.
- Thinking is what all six Qwen 3 cards give for `enable_thinking=True` (*"Temperature=0.6,
  TopP=0.95, TopK=20, and MinP=0"*), and exactly what every Qwen 3.5 card gives for *"Thinking mode
  for VL or precise coding (e.g., WebDev) tasks"* — presence penalty 0.0 included. That is the row
  whose task type this study's scenarios are: output checked exactly, by code.

One setting per mode matters because the cards disagree *within* a ladder: Qwen 3.5 0.8B and 2B ask
for temperature 1.0 where every larger rung asks for 0.7. Following each card would put a settings
change exactly where a size effect is measured.

**The presence penalty is 0.** It lowers the chance of every token already written, so it pushes
against answers that repeat tokens — list markers, JSON quotes, the tool-call tags themselves — and
would favour some options over others for a reason the instructions do not give. For Qwen 3 that is
the card's own position: those cards name no value and offer 0–2 as an adjustment against
repetition. For Qwen 3.5 it is a departure from 1.5 or 2.0, and the four `card-*` policies exist to
price it: about a tenth of the trials per Qwen 3.5 model, rerun under that card's own numbers. There
are none for Qwen 3, because the study setting already **is** the Qwen 3 cards' setting in both
modes. If small models turn out to repeat themselves to the token limit, the fix is one more named
policy with the cards' suggested penalty, and the initial run measures how often that happens.

**gpt-oss** has no non-thinking mode — it reasons on every reply — so it runs only in the thinking
arm. Its study policy, `study-think-gpt-oss`, samples exactly as `study-think` does (temperature
0.6, top-p 0.95, top-k 20) at high reasoning effort, so every thinking run in the study is sampled
one way. That departs on purpose from the gpt-oss README's temperature 1.0 and top-p 1.0, which
`gpt-oss-low`, `-medium` and `-high` keep as effort conditions.

All ten policies: min-p 0, frequency penalty 0, repetition penalty 1.0, and at most 32,768 tokens,
which both card families call the right output length for most queries, kept the same everywhere so
that a cut-off answer means the same thing everywhere.

**Seeds.** Each draw gets `request_seed(base_seed, trial_id, repeat)`. The same inputs always give
the same seed, and repeats get different ones, so they are separate draws. A retry of the same draw
reuses its seed. vLLM does not promise the same output across different mixes of requests in a
batch, so a seed makes a draw repeatable in principle, not bit for bit.

**The initial run** is Qwen 3 1.7B over all 1,080 scenarios at `study-nothink`, on the DGX-1. It is
exploratory: it shakes the checkers out on real replies and is never used as confirmatory evidence.
Composition sets of three or more sources stay closed on it, because stage one predicts them from
pairs alone, and no scenario is ever dropped because of how a model did on it.

## What can reach each model

Both engines change some conversations before the model sees them, and raise no error when they do.
`build_model_request` refuses those, so what the record says is always what the model saw.

| Message | Qwen 3 (vLLM 0.8.5) | Qwen 3.5 (vLLM 0.28.0) | gpt-oss |
|---|---|---|---|
| `system` | one, and only first | one, and only first. A later one fails the request | refused: vLLM delivers it as `developer` |
| `developer` | refused: 0.8.5 renames nothing, and the template renders only system, user, assistant and tool, so the instruction **vanishes with no error** | refused: vLLM renames it `system` and merges every system message at the top | carried, anywhere |
| `user`, `assistant` | carried | carried | carried |
| `tool` | only as the answer to an earlier assistant tool call, by id | the same | the same; otherwise the tool's name reaches the model empty |

So each family has one channel for operator instructions: Qwen's `system` and gpt-oss's `developer`.

The one place the two Qwen templates differ is a later system message: Qwen 3 would render it as its
own turn, Qwen 3.5 refuses the request. The study allows one operator message, first, on both — a
trial built with two could not run on both ladders. That is why the two families refuse it for
different stated reasons.

The worked trials were written for a wider set of roles: 48 of the 70 reach either Qwen family as
written, and 10 reach gpt-oss. The trial builder, the next piece of work, has to put each trial into
a shape its model can carry.

## Adding a model, a family, or a machine

- **A model whose family and machine already exist**: one entry in `models.json` (key, Hugging Face
  id, commit, family, facts, `deployments`) and one serve file. Nothing else. `serving check` then
  verifies the two agree.
- **A model in a second place**: add another entry to its `deployments` and another serve file. The
  same weights under two stacks is what the harness cell needs, and the only way to separate the two
  ladders from the two machines. List it after the first: a command that names no environment
  serves a model at its first deployment. If the family was never served on that engine, read the
  engine's source first and add the family's flags to its profile, as was done for Qwen 3 on vLLM
  0.28.0.
- **A new family**: a block in `families` — where operator instructions go, which roles the template
  carries, which it refuses and why, what its template prefills for thinking, where its template
  lives and its hash — plus a vendored copy of the template, and its serve flags under the engine
  profile in `whowins.runner.serving.ENGINE_PROFILES`. Those flags live in code because each one was read
  out of that engine's source; a config file would let someone declare a behaviour nobody checked.
- **A new machine**: an entry in `environments.json`, including the `conda` block that builds its
  environment. If it runs an engine version no profile covers,
  read that version's source for the same four questions — what it does to roles the template cannot
  carry, which flags exist, what the sampling defaults are, and whether its reasoning parser can be
  trusted — and add a profile.

## Known limits

- **The two ladders are confounded with the two machines.** Engine, GPU and number format all differ.
  Within-model results (does pairwise predict n-way?) are unaffected; between-ladder comparisons are
  not clean until a bridge model is served on both.
- **The 32B's `-sm80` runs mix the machine into the Qwen 3 ladder.** A Qwen 3 size trend that uses
  one compares its top rung on a different engine, number format and GPU from the rest. Every
  analysis that uses one says so; each record's stack names its environment.
- **float16 on Volta.** Qwen ships bfloat16 and warns that float16 can overflow on some Qwen models.
  The DGX-1 has no choice, and float32 does not fit for the larger rungs. The initial run is where
  that shows up if it is real: a NaN-producing model returns empty or garbage replies, which the
  runner records as faults rather than behaviour.
- **gpt-oss and the load cell.** The cell keeps every n-level one length in tokens. Measured with
  both pinned tokenizers, that holds exactly: 10, 25, 59 and 96 tokens under Qwen 3's, and 11, 28,
  66 and 107 under Qwen 3.5's larger vocabulary. It does not hold under gpt-oss's, where levels are
  off by 1 to 3 tokens. Whether to re-choose the fillers for gpt-oss is left open.
- **Harmony's fallback.** When vLLM's harmony parser cannot finish a gpt-oss reply, it hands back the
  raw text as the answer and logs a warning. A reply still carrying harmony's channel tokens is
  recorded with a fault; one without them cannot be told apart.
- **Batches.** vLLM does not guarantee identical output across different batch mixes, so two runs of
  the same seeded request can differ slightly.
