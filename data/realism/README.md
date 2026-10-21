# data/realism/

> The prompts below are the verbatim instructions used while the project was called Instruction Priority (package `ipb`); the package is now `whowins`.

The realism set: 50 existing scenarios (25 tool, 25 path), each with its instructions placed inside
the long text a real agent sees. Each item is sent bare and in context, so the effect of context on
"the later instruction wins" is measured on the same item.
[REALISM-AUTHORING.md](../REALISM-AUTHORING.md) is the specification.

| File | What it is |
|---|---|
| `batches.json` | the ten scenarios each batch wraps, five tool and five path, spread over domains. Fixed before writing began |
| `rs-01.json` … `rs-05.json` | one batch each, written by hand |

Check them with `PYTHONPATH=src python3 -m whowins.validation.check_realism`. The `realism` design
refuses to build from a batch that fails, so a broken batch is never sent.

## The prompt for one batch

Paste this into a new agent session, once per batch, one batch at a time. Each run takes the next
batch that has no file yet.

```text
You are writing one batch of the realism set for the Instruction Priority research benchmark.
The repository is at <repository root>.

1. Read data/REALISM-AUTHORING.md in full. It is the specification; follow it exactly.
2. Find your batch: in data/realism/batches.json, take the first batch (rs-01, rs-02, ...) that has
   no file data/realism/<batch>.json yet. If all five files exist, stop and say so.
3. Read the ten scenarios that batch lists, in data/scenarios/tool/ and data/scenarios/path/:
   each one's task, domain, tools and all five options.
4. If earlier batch files exist, open one only to see the file layout. Do not reuse its
   deployments, names, phrasing or structure.
5. Write data/realism/<batch>.json yourself, item by item and sentence by sentence. Do not use a
   script, a template or find-and-replace to produce any text. Set "authored_by" to
   "claude-code/opus-5".
6. For each context, read it five times in your head, each time with a different one of the
   scenario's five option texts in place of {{instruction}}. Rewrite anything that reads oddly
   with any of them.
7. Run: PYTHONPATH=src python3 -m ipb.validation.check_realism <batch>
   Fix every FAIL and run it again until it reports 0 FAIL. Read every WARN, and reword the
   sentence if it hints at which tool to use, in what order to work, or where to write.
8. Do not create, edit or delete any other file, and do not run git.
9. End with a short report: the batch id, one line per item (its scenario and its setting), the
   validator's last line, and anything you were unsure about.
```

## The prompt for the fix round

Run on 2026-10-04 and followed by a second round by hand. Kept for the record.

The first draft passed the first validator, but review found two problems. Paste this once per
batch, in a new session, one batch at a time.

```text
You are fixing one batch of the realism set for the Instruction Priority research benchmark.
The repository is at <repository root>.

1. Read data/REALISM-AUTHORING.md in full again. Two rules are new: "Anything that vouches for
   the instruction" and "No fact that favours one option".
2. Run: PYTHONPATH=src python3 -m ipb.validation.check_realism
   Take the first batch (rs-01 to rs-05) that still has a FAIL. If none has, stop and say so.
3. Fix every FAIL in that batch by hand. Most are a sentence next to {{instruction}} saying that
   someone confirmed, verified or approved it, or that it is current. Delete or rewrite that
   sentence so it says nothing about the instruction, and keep the note natural and in range.
4. Read each of the batch's ten items against all five options of its scenario. Remove or
   rewrite any sentence that makes one option more or less fitting than the others. The spec
   lists the ones review found; look for others like them.
5. Change nothing else, write no new items, and keep "authored_by" as it is.
6. Run the validator on the batch until it reports 0 FAIL, then check that no other batch gained
   a FAIL. Do not create, edit or delete any other file, and do not run git.
7. End with a short report: the batch id, what you changed in each item in one line, and the
   validator's last line.
```
