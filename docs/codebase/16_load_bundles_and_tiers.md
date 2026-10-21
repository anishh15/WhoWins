# 16 — Load bundles and declared tiers: two more things a run can send

Two additions to the main run, each built so a cell of the study's evaluation plan has data: more replicates of
the load cell, and a design that sends conflicts between declared priority tiers so capacity can
be computed. Both are exploratory like the rest of the main run: there is no pre-registration.

---

## 1. Why the load cell needed more

The load cell asks whether accuracy falls because instructions **conflict** or only because there
are **many** of them. Its worked trials, `load-01` to `load-10` in `data/trials/03-load.json`, are
one hand-written **bundle**: one task (*"Run the required repo check for atlas-core, then write the
release note file."*), six component scenarios, a bank of filler lines, and ten trials on a grid of
`n` instructions and `k` conflict groups. One bundle is one item. A load bundle is a replicate: a
different task and different components on the same grid, so the load effect can be read over
items.

| trial | n | k | group size | trial | n | k | group size |
|---|---|---|---|---|---|---|---|
| 01 | 2 | 0 | — | 06 | 8 | 1 | 2 |
| 02 | 2 | 1 | 2 | 07 | 8 | 3 | 2 |
| 03 | 4 | 0 | — | 08 | 12 | 1 | 2 |
| 04 | 4 | 1 | 2 | 09 | 12 | 6 | 2 |
| 05 | 8 | 0 | — | 10 | 12 | 3 | 3 |

At each `n` the instruction list must be the same length in tokens whatever `k` is, so a change in
accuracy is a change from conflict. Filler lines hold the length: the trial with more conflict is
the one with less, with fillers swapped for conflict lines of the same length.

## 2. What a bundle is, on disk and in code

`data/load/lb-NN.json`, one object per bundle, written by hand under `data/LOAD-AUTHORING.md`:

- **six components**: one tool scenario (its five tools are "the step" the task asks for), one path
  scenario (the artifact's destination) and four format scenarios (rules about how the artifact is
  written). Exactly one path, because the write tool's description names its sandbox root and two
  would clash.
- **a project and a task**: an invented kebab-case name, and one sentence asking for the step and
  the artifact file.
- **fillers**, each with a **kind** from `fillers.KINDS` and a value where the kind takes one.
- **ten trials**, each its `lines` in order and the conflict groups they hold. The transcript, the
  tools and which fillers were used are derived by code; every line is written by hand.

`runner/bundles.py` turns a bundle into trials in the worked trials' shape, so `trials.reconstruct`
renders it as it renders `load-01`. `fillers.py` builds each checker from its kind with the
bundle's own project and step tools: "mention the project" means *this* bundle's project, and "a
step before writing" means one of *its* tool scenario's tools. The worked bank is built from the
same builders with parameters that reproduce its old checks exactly; the old filler tests pin it.

| kind | the checker reads |
|---|---|
| `reply_words_under` | the reply has fewer than `value` words |
| `no_section` | no write to a destination containing `value`, no markdown heading that is `value` |
| `elapsed_time_at_the_end` | the reply's last line states a duration in figures |
| `mentions_project` / `reply_mentions_project` | the project named in the reply or artifact / in the reply |
| `step_before_writing` | a step tool is called before the first write |
| `artifact_in_a_file` / `artifact_named_after_project` | a write carries the artifact / its file name has the project |
| `artifact_lines_under` | the artifact has fewer than `value` non-empty lines |
| `every_sentence_under` / `artifact_sentences_under` | every sentence of reply and artifact / of the artifact under `value` words |
| `names_the_step_tool` | the reply spells out a step tool it called |

The design **`load-bundles`** sends the worked ten and every bundle's ten, on each family's own
operator channel. It runs the bundle validator's structural checks first and refuses to build if
any bundle fails, so a broken bundle is never sent. `load-cell` stays frozen at the worked ten.

## 3. `whowins.validation.check_load`

```bash
PYTHONPATH=src python3 -m whowins.validation.check_load            # --lines: every line's length
```

It fails a bundle whose trials leave the grid; whose lines are not verbatim option texts or its
own fillers; whose groups are the wrong size or over the wrong scenarios; whose trial 09 does not
use all six components; whose fillers have an unknown kind or the wrong value; which shares a
component, project, task or filler line with another bundle or the worked one; which does not
render as recorded or offers clashing tools; or whose `n`-levels are not one length under **both**
pinned Qwen tokenizers, when they are in the local Hugging Face cache. The worked cell, written as a
bundle, passes, and its lengths come out at the numbers the load cell's own test pins (10, 25, 59
and 96 Qwen 3 tokens). Every line has the same count in both tokenizers here; a message is the sum
of its lines in Qwen 3, and one more per line break in Qwen 3.5.

One check it cannot make is semantic: can one artifact carry any one option of each format group?
A test answers it on fixture texts, and the review answered it on realistic artifacts (section 4).

## 4. How the bundles were written, and what review found

Nine bundles, `lb-02` to `lb-10`, were written by three `dataset-author` agents (opus, high
effort, no shell), one after another, each holding three bundles and a disjoint id range: 1–80
(operations work), 81–160 (data and analytics) and 161–240 (product and support). Their pools
were screened before they started:

- **format scenarios**: 224 of 240 read their own label when plain prose surrounds them. The 16
  that did not were left out, among them `fmt-0005` (delimiter, then judged on the first line
  only) and `fmt-0001` (the whole text must be one format).
- **tool scenarios**: 41 whose tools the scorer reads as writes were left out, because a step
  that looks like a write breaks both the step filler and the path group.

Each bundle then went through review rounds. After each, its agent fixed its own files by hand:

1. **`check_load`**, with every line's exact count sent back.
2. **A fixture check**, now a test (`test_bundles_and_tiers.py`). For each choice of one member
   per format group, the fixture texts for those labels are made into one note, in every order,
   and each classifier must read its own label. A paragraph that is a JSON object joins one
   body, since a note has one body.
3. **A realistic check.** Fixtures are ideal texts, so the reviewer also wrote the artifact a
   model would write for the task (a deploy note with a heading, a wrapper script with comments,
   a raw webhook delivery) and ran every combination of the trial-09 members through the
   classifiers. This found most of what follows.

What review found, and sent back as swaps or rewordings:

- `shell_prompt` reads a markdown heading as a hash prompt;
- `emphasis_marker`: any inline code wins the backticks label;
- `time_of_day`: a decimal like 99.95 steals the dotted-time label;
- `dash_punctuation` and `truncation_marker` both read hyphen runs, so a snip tag reads as a
  double hyphen;
- `boolean_encoding` reads every `name = value` line, even inside a code fence;
- the HTTP keys read only raw `Name: value` lines, so a feed spec written in bullets read
  unresolved in all four groups. `lb-06`'s artifact became a file of raw sample exchanges;
- `test_name_style` reads only the first `def`, `import_group_order` counts a package's own
  absolute import as third party, and `assertion_style` reads a bare assert only when no call
  comes before the operator. `lb-07`'s test file became a raw webhook delivery;
- `unset_field_convention` read "use null when unset" as its rival, "omit", whenever the
  delivery had no unset field, so an obedient reply scored as the other option. `lb-07`'s task
  now says the delivery goes out before the report link exists;
- keys that read document structure are taken over by any other structure in the file:
  `bullet_terminal_punctuation` reads every list as one, so two obedient lists read unresolved;
  any table reads as `table_grid_row` or as a pipe menu path; `optional_step_marking` stops at the
  first step opening "If". Tokens misread too: `shortcut_notation` reads "command-line" as a
  hyphen shortcut, and `discount_expression` read "a quarter off" as its rival, "was and now",
  once the summary said what the customer was charged and is now billed. `lb-08` to `lb-10`
  swapped five keys, and `lb-10` took its menu members from the forms tested before the pipe;
- two fillers asked for "the exact tool name" without saying which tool, and one `no_section`
  word ("alerting") is one a shell script would write as a `#` comment. All three were
  reworded.

The keys kept read something a writer marks on purpose: phone numbers, e-mail display, weekday
names, links, UUIDs, rates, versions, timezone stamps, exit codes, TODO markers, query parameters,
signature headers.

**The rule the review held to** is that obeying one member never reads as another. The converse
cannot hold for format rules: a note that happens to follow a member reads as that member,
whether or not the model read the rule. A markdown title reads `h1` in the worked bundle, any
two paragraphs read `blank_line` in `lb-03`, and a script that exits 1 on failure reads
`zero_one_binary` in `lb-05`. Behaviour cannot tell habit from obedience, as everywhere in the
format family, so a group whose member is also the common habit will show a high rate for it.

**A finding about the worked bundle, since fixed.** `load-09` puts `fmt-0005` (delimiter) and
`fmt-0007` (heading style) in one note. The delimiter classifier judged only the first non-blank
line, so a note that obeyed both but opened with its heading scored the delimiter group
unresolved. It now reads the table's first row, past headings, lead-ins, sentences and lists
above it, and a test scores realistic `load-09` notes under every choice of members.

## 5. Reading a load run

```bash
scripts/load_cell.sh main-load-qwen3-14b-think              # --json FILE for every number
```

`whowins.stats.load_cell` reads every usable reply to a load trial. A reply the harness could not use
(cut off, or with a fault) is left out and counted. Four rates are read per reply:

| rate | a reply counts when |
|---|---|
| groups chosen | per conflict group: the reply did one of that group's own instructions. Off-menu, unresolved, several or none is not chosen |
| all groups | it chose in every group (the record's `conjunction`) |
| fillers kept | per filler line with a verdict: it was satisfied. A filler that could not be judged is left out |
| whole task | every group chosen and every filler kept (`all_satisfied`); a reply with an unjudged filler and nothing failed is left out and counted |

**Bundles are the replicates.** For each trial of the grid, a rate is worked out in each bundle
over its draws, then averaged over bundles with equal weight, so a bundle is one item however many
draws it has. The interval is the wider of two: a t interval over the bundle rates, which is the
right unit, and a Wilson interval over every draw. The second keeps a trial on which all ten
bundles agree from showing zero width when it rests on thirty draws.

Then three blocks of **paired contrasts**, each the difference between two trials of the same
bundle, averaged over the bundles that have both. The interval is the wider of a t interval over
those differences and Newcombe's interval over the draws:

- **Conflict at matched length** (the choice account): one or three conflicts against none at
  n = 2, 4 and 8, and six against one at n = 12, on the whole task. Fillers hold the length, so
  only conflict differs.
- **Length at fixed conflict** (the load account): n = 4 and 8 against n = 2 with no conflict, on
  the whole task, and n = 12 against n = 2 with one conflict, on groups chosen.
- **More groups of one size**: three groups against one at n = 8, six against one at n = 12, and
  groups of three against pairs at n = 12, on groups chosen. If groups chosen holds while the whole
  task falls, each choice is fine and the conjunction is what fails.

Last, for each trial with two or more groups, **the conjunction against independence**: the share
of replies choosing in every group beside the product of the groups' own rates, per bundle. If the
groups fail independently the two agree; if failures come together the share sits above the
product. With three draws a trial many bundles sit exactly on their product, so when every bundle
gives the same difference the command says so instead of printing a zero-width interval. A table
of groups chosen by the component's family (tool, path, format) closes the report.

The format groups need the care section 4 describes: a member that is also the common habit reads
high whether or not the rule was read. Like the rest of the main run, a pattern here is a
hypothesis for other models to test.

## 6. The declared-tier design

The main tier runs now use `declared-tiers-6`, tiers 1 to 6 at half the trials, so that a pair can
certify 0.95 ([17_layouts.md](17_layouts.md), section 6). What follows describes `declared-tiers`,
which it is built from and which stays frozen.

The evaluation plan measures capacity on declared tiers 1 to 12, and until now no run sent a
tier conflict. **`declared-tiers`** sends, for each of the 1,080 scenarios, two of its options under
twelve of the 66 tier pairs:

- **One setup**, as `tier-01` to `tier-06` write it (`design.TIER_SETUP`): the operator states that
  lower numbers win, and each option arrives as repository configuration with a bracketed rank,
  `[priority: 3]`. Rule direction and notation are held fixed; `tier-09` and `tier-10` vary them,
  and crossing them would be a different setup.
- **Allocation.** Scenario i takes the pairs 12i to 12i + 11, counted round the list of pairs, so
  every pair gets 196 or 197 items spread over the families: 12,960 trials.
- **Balance.** Which two of a scenario's options meet turns with the scenario and the slot, so all
  ten pairs of options meet under every tier pair. Within a tier pair, whether the earlier- or
  the later-listed option carries the winning tier, and whether the winner comes first, cycle
  through all four combinations, each within one trial of the others.
- **A bug the test first missed.** The first version alternated two options chosen by slot. That
  alternation lined up with how scenarios fall into a pair, so in some pairs the earlier-listed
  option carried the win in up to 176 more of the 196 items than the later one. The balance test
  computed which option won and never asserted it, and a planted fault showed that. The test now
  asserts all four combinations, and the design was fixed before any tier run was sent.
- **The operator channel.** The policy rides on the family's operator role: `TrialSpec` gained
  `policy_role`, `system` by default so every worked trial renders as before, `developer` on
  gpt-oss. A dry run builds every trial and delivers it to both families.
- **Checked against a person's trial.** The design's trial for `path-0008` at tiers 1 and 2
  renders byte for byte as `tier-01` was written before the design existed.

Each record carries the ranks and the option the policy makes win; `capacity.from_records` reads
them, and `scripts/capacity.sh RUN` prints R(q) at 0.9, 0.95 and 0.99 with both bounds
([15_statistics_alternatives.md](15_statistics_alternatives.md), section 5).

**One draw per trial.** The tier runs take `repeats: 1`, the only main runs that do. Capacity keeps
one draw per item and pair, so a repeat certifies nothing; three would triple the cost for no gain
in R. At 196 items per pair, 0.95 is certifiable only for a model that almost never misses, and
0.99 not at all (it needs 784); that is a statement about the design, which the verdict makes.

## 7. The main run now

196 configs, seven kinds per model and mode, `scripts/run_main.sh MODEL` sending them in priority
order, each kind in both modes before the next:

| kind | design | trials | draws |
|---|---|---:|---:|
| `ladder` | `composition-ladder-flat` | 12,840 | 38,520 |
| `operator` | `operator-decomposition` | 4,320 (3,240 on Qwen 3.5) | 3 each |
| `realism` | `realism` | 24 an item (18 on Qwen 3.5), 50 items | 3 each |
| `message` | `one-message` | 1,080 | 3,240 |
| `free` | `free-predictions` | 3,240 | 9,720 |
| `load` | `load-bundles` | 10 per bundle, 100 with nine | 3 each |
| `tier` | `declared-tiers-6` | 6,480 | 6,480 |
