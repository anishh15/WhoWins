// Get-started steps. Every command is copied from the README; the ones that need no GPU were run on a
// fresh checkout before this page was published.

export const STEPS = [
  {
    id: 'install',
    title: 'Install',
    text: 'WhoWins needs Python 3.10 or newer and nothing outside the standard library. Install it from source; the data is read from the checkout, so keep the install editable.',
    code: `git clone https://github.com/anishh15/WhoWins.git
cd WhoWins
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # dev adds pytest`,
    note: 'Two optional extras exist: `download` (huggingface_hub, to fetch the pinned weights) and `tokenizers` (token lengths of the load bundles). Tests that need PyYAML, Jinja2 or tokenizers skip when those are not installed.',
  },
  {
    id: 'validate',
    title: 'Check the data and the code',
    text: 'These need no GPU and no network.',
    code: `python3 -m whowins.validation.validate_collection    # counts, family rules, the worked trials
python3 -m whowins.validation.check_batch            # screens over every scenario
python3 -m whowins.checkers.coverage                 # every scenario has a working checker
python3 -m whowins.splits.check                      # the frozen held-out lists still match the data
python3 -m whowins.runner.serving check              # models, machines, policies and runs agree
python3 -m whowins.runner.design main-ladder-qwen3-8b-nothink   # what a Ladder run sends
python3 -m pytest -q                                 # the test suite, a few minutes`,
  },
  {
    id: 'score',
    title: 'Build Box 1 and score a reply',
    text: 'The Python API builds every trial of a run, renders the messages a model receives, and scores a reply with the same checkers the study used.',
    lang: 'python',
    code: `from whowins.checkers import Response, ToolCall, check
from whowins.runner.design import trials_for_run
from whowins.runner.rendering import render_dicts
from whowins.runner.serving import load_run
from whowins.runner.trials import load_scenarios

scenarios = load_scenarios()                     # every base scenario, by id
run = load_run("main-ladder-qwen3-8b-nothink")   # a run config from configs/runs/
trials = trials_for_run(run, scenarios)          # every trial this run sends, in order
box1 = next(t for t in trials if t.trial_id == "fmt-0002@S1-S2-S3-S4-S5")
for message in render_dicts(box1, scenarios):    # the messages the model receives
    print(message["role"], "|", message["content"])

reply = Response(text='{"ACCOUNT_ID": "acc_1042", "OWNER_NAME": "Ada"}')
print(check(scenarios["fmt-0002"], reply))
# Outcome(behaviour='chose', label='screaming_snake', winning_option='o5', ...)

first_call = Response(tool_calls=[ToolCall("check_types")])
print(check(scenarios["tool-0001"], first_call).winning_option)   # o2: "Call check_types first."`,
    note: 'In this trial the tool result carries option `o5`, so the reply above is scored as a win for [[S4]].',
  },
  {
    id: 'pairs',
    title: 'See why pairs are not enough',
    text: 'The simulation gate plants a known truth, fits it back, and shows two worlds that agree on every pair but not on the winner of a triple. It takes about a minute and needs no GPU.',
    code: 'scripts/phase1.sh',
  },
  {
    id: 'run',
    title: 'Run the study on a GPU machine',
    text: 'Sending trials needs a machine with vLLM. `runbook.md` has every command and every flag, and `configs/README.md` says why each setting is what it is. For one model:',
    code: `scripts/create_env.sh                          # list the machine environments; then --print ENV shows the conda commands
scripts/download_models.sh qwen3-8b            # the pinned weights, into the Hugging Face cache
scripts/serve.sh qwen3-8b                      # vLLM with the model's pinned serve file (port 8000)
scripts/preflight.sh qwen3-8b                  # is the server serving what the runs expect?
scripts/run_main.sh qwen3-8b --dry-run         # build and check every run; send nothing
scripts/run_main.sh qwen3-8b --concurrency 16 --timeout 1800   # all seven kinds, both thinking modes; resumes`,
    note: 'Each reply is appended to `results/<run>/records.jsonl`, which git ignores.',
    gpu: true,
  },
  {
    id: 'read',
    title: 'Score again and read a run',
    text: 'Reading a run needs no GPU. A checker corrected after a run is applied again to the replies already on disk, and the stored records are never changed.',
    code: `scripts/rescore.sh main-ladder-qwen3-8b-think --write    # score again with today's checkers
scripts/analyse.sh main-ladder-qwen3-8b-think            # what the run did, from its records
scripts/strengths.sh main-ladder-qwen3-8b-think          # fit the pairs, forecast the larger sets
scripts/layouts.sh main-operator-qwen3-8b-think          # Operator, Boundary or Context layouts
scripts/capacity.sh main-tier-qwen3-8b-think             # declared tiers`,
    note: 'These read the records of a finished run. The scored replies of the study will be released separately as a dataset.',
  },
]

export const TREE = `WhoWins/
├── src/whowins/
│   ├── checkers/       a reply to one label: 4 trace checkers and 240 format classifiers
│   ├── runner/         build a run's trials, render the messages, send them, score the replies
│   ├── stats/          the choice models, the forecast of larger sets, capacity, the simulation gate
│   ├── splits/         the frozen held-out lists and their checks
│   └── validation/     screens over the scenario collection
├── data/               scenarios, worked trials, load bundles, the Context set, splits
├── configs/            models, machines, vLLM serve files, decoding policies, every run
├── scripts/            shell entry points for serving, running and reading runs
├── tests/              the test suite
├── docs/codebase/      how the code works, file by file
├── runbook.md          every command in order, with every flag
└── website/            this site`
