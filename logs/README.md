# logs/

What a command in this repository did, kept after the terminal that ran it has gone.

Every command that calls `whowins.logs.setup` — `whowins.runner.batch`, `whowins.runner.rescore`,
`whowins.runner.design`, `whowins.runner.preflight`, `whowins.splits.build`, `whowins.splits.check` — writes one
file here per invocation:

```
logs/run-balanced-qwen3-1.7b-20260914T031500.log
logs/rescore-initial-qwen3-1.7b-20260914T094512.log
logs/preflight-qwen3-1.7b-20260914T030200.log
```

**The file always holds DEBUG**, whatever the terminal was set to show. A run takes hours over
ssh, and when it ends badly the question is what happened at 03:40 — which used to be answerable
only from whatever scrollback survived. `-v` changes what the *terminal* prints and nothing else;
`--log-file PATH` puts the file somewhere else; `--no-log-file` writes none.

## This directory is gitignored, and that is the point

A log is a record of what *this checkout* did. What the *study* did lives in two other places, and
neither of them is here:

| | |
|---|---|
| `results/<run>/records.jsonl` | every reply the server gave, one JSON line per attempt. Kept outside git and released separately. **This is the evidence.** |
| `results/<run>/summary.json` | where a run stands, derived from the log above and nothing else |

If a log ever seems worth keeping, the thing worth keeping is in it — a number, a failure, a
timing — and it belongs in the project's decision record or in the run's own notes, written down
by a person. Committing the file instead would put a machine's transcript where a decision should be.

Nothing here is read by any code. Delete the lot whenever you like.
