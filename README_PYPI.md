# WhoWins

[![WhoWins: position, role or label? Five seats send five casings of one key, and the tool result wins](https://anishh15.github.io/WhoWins/og.png)](https://anishh15.github.io/WhoWins/)

[![PyPI](https://img.shields.io/pypi/v/whowins?style=flat-square&color=C9786E)](https://pypi.org/project/whowins/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-6F87A6?style=flat-square)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache_2.0-7A3B34?style=flat-square)](https://github.com/anishh15/WhoWins/blob/main/LICENSE)
[![Website](https://img.shields.io/badge/website-WhoWins-C9786E?style=flat-square)](https://anishh15.github.io/WhoWins/)

*Position, Role or Label? A Controlled Study of Instruction Conflicts in LLM Agents*

An LLM agent takes instructions from the operator's system prompt, the repository's configuration,
the user, tool results and its own saved notes, and these often disagree. A source sets three things
at once: the instruction's position, the chat role that carries it and the label that names it.
WhoWins keeps each instruction's text fixed and changes only how it is delivered. It has
1,080 scenarios in five task types, each with up to
five instructions that no reply can satisfy together, sent from
five seats, and seven experiments that each change one thing.
Code scores which instruction a reply followed; no LLM judge is used. The paper runs it on
14 open-weight models, 1,887,356 scored replies in all.

## Install

```bash
pip install whowins
```

Python 3.10 or newer; nothing outside the standard library. The package carries the scenarios and
the run configs, so it works without a checkout. The tests, the GPU scripts and the docs are in the
[repository](https://github.com/anishh15/WhoWins).

## Quick start

```bash
python -m whowins.validation.validate_collection    # counts, family rules, the worked trials
python -m whowins.checkers.coverage                 # every scenario has a working checker
python -m whowins.splits.check                      # the frozen held-out lists still match the data
python -m whowins.runner.design main-ladder-qwen3-8b-nothink   # what a Ladder run sends
```

Build the paper's Box 1, a trial in which every seat asks for a different casing, and score a reply:

```python
from whowins.checkers import Response, ToolCall, check
from whowins.runner.design import trials_for_run
from whowins.runner.rendering import render_dicts
from whowins.runner.serving import load_run
from whowins.runner.trials import load_scenarios

scenarios = load_scenarios()                     # every base scenario, by id
run = load_run("main-ladder-qwen3-8b-nothink")   # a run config the package carries
trials = trials_for_run(run, scenarios)          # every trial this run sends, in order
box1 = next(t for t in trials if t.trial_id == "fmt-0002@S1-S2-S3-S4-S5")
for m in render_dicts(box1, scenarios):          # the messages the model receives
    print(m["role"], repr(m["content"]), *(m[k] for k in ("tool_calls", "tool_call_id") if k in m))

reply = Response(text='{"ACCOUNT_ID": "acc_1042", "OWNER_NAME": "Ada"}')
print(check(scenarios["fmt-0002"], reply).winning_option)          # o5: the tool result's option
print(check(scenarios["tool-0001"], Response(tool_calls=[ToolCall("check_types")])).winning_option)  # o2
```

Logs and run records go to `logs/` and `results/` under the working directory.

## Links

- Website, with the findings and every result: <https://anishh15.github.io/WhoWins/>
- Repository, with the tests, the GPU scripts and the runbook: <https://github.com/anishh15/WhoWins>
- Issues: <https://github.com/anishh15/WhoWins/issues>
- Paper: coming soon

## Citation

```bibtex
@misc{laddha2026whowins,
  title  = {Position, Role or Label? A Controlled Study of Instruction Conflicts in LLM Agents},
  author = {Anish Laddha and Nitesh Pradhan and Gaurav Srivastava},
  year   = {2026},
  url    = {https://github.com/anishh15/WhoWins}
}
```

Apache License 2.0. Contact: [anshladdha15@gmail.com](mailto:anshladdha15@gmail.com),
[nitesh.pradhan@lnmiit.ac.in](mailto:nitesh.pradhan@lnmiit.ac.in), [gks@vt.edu](mailto:gks@vt.edu).
