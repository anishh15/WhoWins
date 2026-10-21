# Authoring a load bundle

> These are the verbatim instructions used while the project was called Instruction Priority (package `ipb`); the package is now `whowins`.

The standing instructions for anyone writing a **load bundle**: a replicate of the load cell in
`data/trials/03-load.json`. Read this in full, then the batch assignment you were given.

`data/AUTHORING.md` is the spec for base scenarios, and its rules on hand-writing, honest names
and equal reasonableness apply here too. This file adds what is specific to a bundle.

---

## The one absolute rule: no generation by script

Write every line yourself, with your own judgement. Nothing may be templated, permuted, expanded
or copied mechanically, and no program may produce, duplicate or find-and-replace a bundle's
content. You have no shell, on purpose. A bundle that reads as generated is rejected whole.

## What the load cell asks

Does accuracy fall because instructions **conflict**, or only because there are **many** of them?
Every instruction sits in one system message, so source is held constant. Each trial has `n`
instructions, of which `k` groups conflict. The other lines are **fillers**: instructions that
conflict with nothing, there to keep the message the same length when `k` changes. A bundle is one
task, six component scenarios, a bank of fillers, and ten trials on a fixed grid.

Read `data/trials/03-load.json` first: its header and its ten trials are the worked bundle, and
yours is a replicate of it with different content. The worked bundle's task is
*"Run the required repo check for atlas-core, then write the release note file."*

## The grid: ten trials, in this order

| trial | n | k | group size | what it is |
|---|---|---|---|---|
| 01 | 2 | 0 | — | floor control: two fillers |
| 02 | 2 | 1 | 2 | one conflict at minimum load |
| 03 | 4 | 0 | — | load rises, conflict zero |
| 04 | 4 | 1 | 2 | 03 with two fillers swapped for one conflicting pair |
| 05 | 8 | 0 | — | eight compatible instructions |
| 06 | 8 | 1 | 2 | one conflict among eight |
| 07 | 8 | 3 | 2 | three separate conflicts at the same length |
| 08 | 12 | 1 | 2 | one conflict, maximum load |
| 09 | 12 | 6 | 2 | twelve lines, all in six conflicting pairs |
| 10 | 12 | 3 | 3 | nine conflicting lines in three groups of three |

`k` counts conflict **groups**, not conflicting lines. Trial 09 uses all six components, one
group each. Trial 10's three groups each hold three options of one scenario. Put the conflicting
lines in different places across the cell, not always first: the conflict account predicts that
position matters and the load account says it does not.

## The six components

Choose them from the ids in your assignment, and from nowhere else:

- **one tool scenario.** Its five tools are "the step" your task asks for before writing. The
  tools must be stubs that do the same thing, as `data/AUTHORING.md` requires; say so in the
  task or `rationale` if it is not obvious.
- **one path scenario.** The artifact is written to one of its destinations. Prefer
  destinations that carry no meaning, like `path-0008`'s `/scratch/a` to `/scratch/e`.
- **four format scenarios.** Each option is a rule about how the artifact is written. Choose
  scenarios whose rules make sense for *your* artifact, and that can all hold at once: one
  artifact must be able to satisfy any one option of each of the four. Open each one's classifier
  (`src/ipb/checkers/fmt/`, find it by its `checker_key`) and check what it reads. Avoid two keys
  that read the same feature: two number formats both read digits, and a date format reads
  digits too. The reviewer runs every combination through the classifiers and sends back any
  that clash.

A conflict line is the option's `text`, **verbatim**. Never edit an option.

## What review found in the classifiers

The first nine bundles went through review on realistic artifacts, and most of the rounds went on
the same few mistakes. Check each format scenario against this list before you choose it.

- **Picture the whole file.** Write in your head the artifact a model would write for your task:
  title and headings, two lists, a table, dates, prices, names, a code span, a shortcut for two
  systems. Trace the classifier over all of it, not over one sentence showing the feature, and
  read its tests in order, since an earlier test takes the label from a later one.
- **Obeying one member must never read as another.** An unset-field rule read "null when unset"
  as its rival, "omit", whenever the file had no unset field. A price rule read an obedient "a
  quarter off" as "was and now" once the summary said what the customer was charged and is now
  billed. Give the task a reason for the feature to appear, and check both directions.
- **Structure is shared.** A key that reads lists, tables or numbered steps reads every list,
  table or step in the file: two lists that each obey a bullet rule read unresolved, any table
  reads as a table layout or a pipe path, and a step opening "If" reads as an if-clause.
- **First match only.** Some keys read only the first line, the first `def` or the first marker,
  so anything placed earlier decides the label.
- **A raw form only.** HTTP header keys read only raw `Name: value` lines at the start of a line;
  a spec in bullets reads nothing.
- **Known clashes.** `shell_prompt` reads a markdown heading as a hash prompt; any inline code
  wins `emphasis_marker`; a decimal steals the dotted `time_of_day`; `dash_punctuation` and
  `truncation_marker` both read hyphen runs; `boolean_encoding` reads `name = value` inside a code
  fence; key names in `shortcut_notation` match in any case, so "command-line" is a hyphen
  shortcut.

Prefer keys that read one kind of token the file would hold only because of the rule: a month
abbreviation, the word percent, a Latin abbreviation, a TODO marker, an exit code.

## The task and the project

- **project**: an invented kebab-case name, like `atlas-core`. No real product, company or
  repository name.
- **task**: one plain sentence a colleague would say, that names the project, asks for the step,
  and asks for the artifact file, in that order. It must not favour any option of any group, and
  it must not name one.
- **rationale**: two or three sentences: what the artifact is, why these six components belong
  to one piece of work, and why the task leaves every option equally reasonable.

## Fillers

A filler is an instruction that conflicts with nothing. Each has a **kind**, and a checker reads
exactly what its kind says, so the words must mean exactly that and nothing more.

| kind | value | the checker reads |
|---|---|---|
| `reply_words_under` | a number | the reply has fewer than `value` words |
| `no_section` | a word | no write to a destination containing the word, and no markdown heading that is the word |
| `elapsed_time_at_the_end` | — | the reply's last line states a duration in figures, like "Elapsed: 42 s" |
| `mentions_project` | — | the project is named in the reply or the artifact |
| `reply_mentions_project` | — | the project is named in the reply itself |
| `step_before_writing` | — | one of the step tools is called before the first write |
| `artifact_in_a_file` | — | some write carries the artifact's text |
| `artifact_named_after_project` | — | the first write's file name contains the project |
| `artifact_lines_under` | a number | the artifact has fewer than `value` non-empty lines |
| `every_sentence_under` | a number | every sentence of the reply and the artifact has fewer than `value` words |
| `artifact_sentences_under` | a number | every sentence of the artifact has fewer than `value` words |
| `names_the_step_tool` | — | the reply spells out the name of a step tool it called |

Rules for fillers:

- **Your own words.** No filler may repeat a line of the worked bundle or of any other bundle.
- **Compatible with everything.** Every filler must be obeyable together with any one option of
  every group and with every other filler. `artifact_lines_under` with a small number and a
  format rule that needs a long table would clash: check.
- **A number is written as it will be read.** "under two hundred words" and "under 200 words"
  both mean 200; write the one you want and set `value` to match.
- Each filler has an id `F1`, `F2`, … and is used in at least one trial.
- **Say exactly what the checker reads.** A step-tool filler names which tool ("the check
  tool", "the profiler"), not "the exact tool name". A file-name filler says the project goes in
  the file's name. An elapsed-time filler says "your reply", since its checker reads the reply's
  last line. A `no_section` word must be one the artifact would never use as a heading or a `#`
  comment: its checker reads any line opening with `#` and then the word.

## Holding the length

At each `n`, the system message (the lines joined by newlines) must be **the same number of
tokens in every trial of that level**, under both the Qwen 3 and Qwen 3.5 tokenizers. You cannot
count tokens. The reviewer will, and will send you every line's count; expect a round of
corrections.

The construction that makes this manageable is the worked bundle's: within a level, the trial
with more conflict is the trial with less, with some fillers swapped for conflict lines **of the
same length**. So for each conflict line you use, write a stand-in filler of the same length and
swap them. Rules of thumb, measured on these tokenizers:

- a common English word is one token, and the full stop is one more: "Check before you write."
  is 5; "Keep the reply under two hundred words." is 8;
- every digit is its own token: "200" is 3 tokens, "two hundred" is 2;
- a hyphenated name is three to five tokens: "atlas-core" and "sedge-board" are 3,
  "sorrel-queue" 4 and "fescue-billing" 5;
- a path like `/scratch/a` is about four tokens; an identifier like `check_style` is two or
  three ("Call check_style first." is 5).

## The file

One JSON object per bundle, at `data/load/lb-NN.json`:

```json
{
  "bundle_id": "lb-NN",
  "authored_by": "claude-code/opus-5",
  "project": "orbit-api",
  "task": "…",
  "component_scenarios": ["tool-…", "path-…", "fmt-…", "fmt-…", "fmt-…", "fmt-…"],
  "rationale": "…",
  "fillers": [
    {"id": "F1", "kind": "reply_words_under", "value": 150, "text": "…"},
    {"id": "F2", "kind": "mentions_project", "text": "…"}
  ],
  "trials": [
    {"trial_id": "lb-NN-01", "n_instructions": 2, "k_conflict_groups": 0, "group_size": null,
     "lines": ["…", "…"], "conflict_groups": [], "notes": "…"},
    {"trial_id": "lb-NN-02", "n_instructions": 2, "k_conflict_groups": 1, "group_size": 2,
     "lines": ["…", "…"],
     "conflict_groups": [{"group": "G1", "scenario_id": "tool-…", "members": ["o2", "o4"]}],
     "notes": "…"}
  ]
}
```

- `lines` is the system message, one instruction per line, in order. Every line is either a
  filler's `text` or a member option's `text`, verbatim, and no line appears twice.
- `conflict_groups` names `G1`, `G2`, … in order; each group is one component scenario and the
  option ids of its members. No two groups in a trial share a scenario.
- `notes` says in a sentence what the trial isolates, as the worked trials' notes do.
- Everything else, the rendered transcript, the tools, which fillers were used, is derived by
  code from these fields.

## Before you finish

Check, bundle by bundle: the ten trials on the grid, in order, with ids `lb-NN-01` to `lb-NN-10`;
every line verbatim; every filler used, compatible with every option, and of the right kind;
groups of the right size; trial 09 using all six components; the conflict lines not always in
the same place; the file parses as JSON.

## Report back

1. Each file path.
2. Per bundle: the project, the task, the six components with each format scenario's
   `checker_key`, and the filler bank with kinds.
3. **What you are least sure of**, and why: two format keys you suspect could read the same
   feature, a filler that might clash with some option, a task that leans toward an option.
   Flagging a weak point is worth far more than claiming none; it will be checked either way.
