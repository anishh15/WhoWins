# Tests

```bash
python3 -m pytest tests/          # 2,387 tests: 2,383 pass, 4 skipped
```

`conftest.py` puts `src/` on the path, so no install or `PYTHONPATH` is needed.

The four skips read the test runs' records, which are not part of this repository. With those
records under `results/`, they run. On a machine with
vLLM installed, one more skips: serve.sh then reads vLLM's version from its package metadata, so
the path that imports vllm cannot be reached.

## What is here

**`test_checkers.py`** — the suite. It is organised around the properties that matter rather
than around the modules, because a checker is only worth anything if it cannot be made to score
two options at once or to score a hole in our code as a model failure.

| Group | What it pins |
|---|---|
| Safety properties | Sentinels are not option values anywhere in the collection; an unimplemented key raises rather than scoring; **no response that answers nothing wins anything**; at most one option can match |
| Format classifiers | 1,382 fixtures; every classifier's label set is exactly the value set the collection declares; **every one of the 1,200 declared option values is reached by some fixture** |
| Trace checkers | The four trace keys, the nine prefix-collision cases, a bare name (`ap4`) scoring the one destination it names, and every ordering permutation being reachable. A write is found by a *word* of the tool name — `get_output_dir` is not a write because it contains `put` — and the common file-destination argument names are read |
| Communication axis | Flagging a conflict and obeying the wrong instruction are independent — the whole reason the two axes are separate |
| Coverage bookkeeping | All 1,080 scenarios executable, per family — asserted, not reported |
| Talk is not an artifact | Forty-seven realistic non-answers win nothing, and the one two-word reply an artifact could also be, "Conflict detected.", wins exactly three options, pinned. A reply quoting both sides of a conflict and asking wins nothing. Words talk is made of, inside real artifacts, are not talk. A lead-in on the artifact's own line is cut and costs one correct answer of 1,261; a fence, lead-in or sign-off never swaps a correct label for another option's. A plain statement with no artifact gets a label only in eight scenarios where prose is the artifact, pinned |
| Two answers in one reply | A second fenced block, a paragraph opening "Or" or "Alternatively", or — for a reply nothing else could label — one answer per heading, and two options make `multiple`: 2,383 to 2,392 of 2,400 constructed hedges per style, pinned. No single answer with an explanation beside it is read as two, and a reply that classifies cleanly keeps its label however many headings it has |
| What the first run found | The four checker holes read out of `results/initial-qwen3-1.7b`: an artifact in inline code, a caps heading with a colon, one answer per source under each source's own header, and `hedged` matching a courtesy sign-off. Each test names the reply that exposed it |
| Refusal | A question is not a decision; a reply that flags the conflict decides only in the first person; the gated action decides comply, and saying it was done is not doing it |
| Planted faults | Deliberately broken checkers that the suite must catch |

**`test_splits.py`** — 44 tests over the frozen split lists. Same shape: organised around the one
property that matters, which is that a grouped split must actually group.

| Group | What it pins |
|---|---|
| The premise | `seed_family` and format `checker_key` are unique across the collection, so the grouping the plan describes cannot be looked up and has to be built. If either stops being unique, this goes red and the design is revisited on purpose |
| Link rules | Each of the three can fire, including the one that fires zero times on the collection today; each is symmetric; frame stripping is load-bearing |
| Groups | Partition the collection, never span a family, and do not depend on the order scenarios sit in their batch files |
| Built files | On disk, current, deterministic, balanced inside every family, dry run drawn only from train |
| The design splits | The five sources are derived from the worked trials and a source with two identities raises; every source pair is held out exactly once; no fold disconnects the source graph; stage one fits pairs only; nothing predicted was ever fitted |
| The stage-two slice | Four triples, the minimum that puts every source pair in some triple — a pair covered by no triple is a correlation stage two cannot estimate. All ten minimum slices are isomorphic, so the choice carries no information, and the one used contains the triple comp-07 declares |
| Planted faults | Ten damaged splits the checker must reject — the first being the grouping replaced by `seed_family` singletons |

**`test_runner.py`** — 190 tests over the renderer and the response side.

| Group | What it pins |
|---|---|
| The acceptance test | All **70 hand-written trials re-render byte for byte**. They predate the renderer, so agreeing with them is agreeing with an independent decision |
| Derived share | How much of each cell the vocabulary produced rather than quoted, with four cells pinned at 100%. The byte-diff alone can be passed by quoting, and a wrong header is caught here and nowhere else |
| Vocabulary | An undemonstrated combination raises rather than inventing a plausible string; every wording is used by some trial; the two policy tables stay in step |
| Spec invariants | Duplicate slots, element order disagreeing with slot order, a rank with no stated policy, a Block in a collapsed renderer |
| End to end | Every option of all 1,080 scenarios, from tool schema or fixture text through the completion envelope and parser to the score it aimed at — **5,040 pairs** |
| Couplings | The write tool's name still matches the checker's verb list, and its argument still matches the checker's target names |
| Composite trials | The load cell scored per conflict group, each against its own members, with the conjunction over the groups; the same six tools in all ten load trials; a spec refusing groups that do not match the instructions shown; the release note read from `write_file`'s content when written there; every filler checked by code and each judged on what it names; the retired fillers in no trial; one conflict fewer swapping the tool pair for its two five-token stand-ins; every n-level one length in tokens under both pinned Qwen tokenizers, where they are cached -- 10, 25, 59 and 96 under Qwen 3's, 11, 28, 66 and 107 under Qwen 3.5's; `all_satisfied`, the whole-task score |
| Options in play | Doing an option the trial never showed is off-menu, with its label kept; an option shown inside quoted prose is still in play |
| The record | Every refusal scenario offers its own gated action, described as the action and not as a stub, and is scored from the trace; a bare scenario is refused by name; a checker that raises becomes a fault, not a crash or a choice; the raw reply is kept so a record can be rescored; the envelope escaper round-trips through a real JSON parser |
| Planted faults | A broken header, a dropped task line, a changed JSON indent, reversed span order, a guessing parser, a filtered tool call |

**`test_serving.py`** — 216 tests over the model configs, the two machines, and what reaches each
model. Nothing in it calls a model: the serve script runs against a fake `vllm` that prints what it
was given and a fake `nvidia-smi` that prints made-up cards, and preflight talks to a stub server on
this machine.

| Group | What it pins |
|---|---|
| The roster | The fifteen models the owner chose, in their order, each at the commit the Hub reported — written in the test as well as in the roster, so an edit to one alone goes red; two ladders and a comparison family; every Qwen 3 rung thinks by default and only Qwen 3.5's two smallest do not; both cross-family pairs are mixtures of experts |
| The two machines | Each has its own conda environment, which installs the engine version it claims to run and nothing that contradicts what the machine reports; each model is served somewhere, and each machine runs one ladder, the 32B being the one model served on both; the V100 machine serves float16 because it has no bfloat16, and states V0; it starts no reasoning parser, because the only one its engine has would return the whole answer as reasoning; each engine profile forbids what that version cannot do |
| Serve files | PyYAML reads each one exactly as the package's own reader does; each pins the commit, the tokenizer's commit, `generation-config vllm`, no prefix caching, its machine's dtype and memory fraction, the seed and the context, and each family has the parsers its engine has. **Thirty-seven damaged copies of the configs and four damaged policy files are each refused on load**, beside undamaged copies that load |
| What reaches Qwen | All three real templates, behind vLLM 0.28.0's own rewrite reproduced from its source: every worked trial the guard accepts, the same 48 of the 70 on either family, arrives unrewritten and without error, with every message's text and every turn. A developer message is rewritten by 0.28.0 and **silently dropped by Qwen 3's template on 0.8.5**, so both are refused; a late system message fails the Qwen 3.5 template and is refused on Qwen 3 too, so one trial runs on both ladders; every load-bundle trial and a spread of declared-tier trials arrive the same way; a tool result answering its call arrives as recorded; the prefill each family claims is what its template does |
| Delivery rules | How many worked trials each family carries as written, and why the rest do not; gpt-oss's developer channel; Qwen's one first system message; a tool result answers an earlier call by id |
| Policies and requests | Every policy states every setting of a draw; one study policy per thinking mode covers both Qwen generations; no study policy penalises a token for having been written, while each card policy carries that card's own numbers; the study settings are what every Qwen card recommends; a run may not borrow another family's card policy; a Qwen request says whether to think; the answer's budget leaves room for the prompt; the exact request the initial run sends |
| Seeds, stack, run | One seed per draw; the stack records the machine as well as the model, so the same weights on two machines are two fingerprints; an unpinned engine is recorded only on purpose; the initial run is the 1.7B over every scenario with the sets above a pair closed; no two runs share a seed except a 32B `-sm80` copy and its DGX-1 twin, and each copy matches its twin, and its serve file the DGX-1's, in everything the machine does not force, with a planted departure caught |
| The reply | Reasoning returned with thinking off is a fault, under either of vLLM's field names; markers in an answer the server should have split are a fault; where this package splits, the answer is what follows `</think>`, a reply that opened a block and never closed it holds no answer, a Qwen 3 reply with no tag at all is an answer, and a `<tool_call>` inside the thinking is recorded as a doubt — end to end through `score`, not only in the parser |
| Free GPUs | The lowest-numbered free cards are chosen, and a busy machine is refused rather than shared; the reader reads what `nvidia-smi` prints and refuses what it cannot |
| Scripts and preflight | Every script parses; `serve.sh` prints and starts the pinned command with the pinned environment, pins each machine to its own engine version, takes free GPUs on the shared one and refuses to start beside another job; the download fetches each model at its commit; preflight passes a matching server on either machine, reads Qwen 3's template out of `tokenizer_config.json` and Qwen 3.5's out of its own file, fails each kind of mismatch, and never counts a check it could not make as a pass |

**`test_batch.py`** — 118 tests over the trial design and the run loop. The HTTP client talks to a
stub server on this machine that answers, refuses, 500s or hangs up to order.

| Group | What it pins |
|---|---|
| The design | One trial per scenario, 1,080 of them, ids unique; the five sources are the ones the split froze; every source pair gets 108 scenarios; the rotation is a Latin square, so source pair and option pair are not confounded; the same config builds the same list |
| What is sent | Every trial reaches **both** Qwen families as recorded — which is what one operator message, first, buys; two operator sources share one message and are told apart by their labels; a tool result answers a call the transcript shows, to a tool the trial offers, and no other trial is given that tool; two user sources are two turns |
| Refusals | A design the run does not name, a run that would put one source in play, a run whose scenario count disagrees with the scenarios it was handed, a scenario with one option |
| The client | A completion is posted and read back; a 4xx is our mistake and is not retried; a 5xx, a closed port and a bad body are transport errors; a retried draw keeps its seed; a draw that never came back is reported and never invented; a gpt-oss tool-call header vLLM cannot parse on any retry is an unusable reply, `stopped_by: malformed_tool_call`, and one that clears on a retry is an ordinary answer |
| Resume | A whole small run writes one line per trial; the same command again sends nothing; a run stopped half way carries on; a line cut off by the kill costs one trial and not the run; a transport failure is logged and tried again next time; an answer is never re-rolled however bad it was |

**`test_logs.py`** — 85 tests over what a command says while it runs: the progress bar, the
logging, and the flag reference in runbook.md.

| Group | What it pins |
|---|---|
| stdout is a contract | Neither the bar nor a log record ever reaches stdout, and `serving shell KEY` still prints nothing but shell assignments — `scripts/serve.sh` runs `eval` on that output. Importing the package installs no handler anywhere |
| The bar | A terminal is redrawn in place, a redirected stream gets whole lines and no carriage returns, and a log record wipes the bar and puts it back rather than landing in the middle of one. Fields are given up in order as the terminal narrows — the trial id, then the rate, then the bar, then the estimate — so the line fits by construction and never wraps; a redirected stream has no width and keeps them all. The block characters fall back to `#` and `-` on a stream that cannot encode them, and the rate counts **trials**, not requests, because a trial is an agent loop |
| The estimate | Read off a sliding window, not the whole run — a run's first requests go out while the server is warming, and an average over those under-reports the rate for hours. Withheld entirely under twelve samples or fifteen seconds, and shown as `--:--:--` until then; that withholding is what carries the honesty, not the format |
| The logging | The file holds DEBUG whatever the terminal was asked to show; setting up twice does not double every line; a log file that cannot be written does not stop the job. **A command started with `python3 -m` actually logs** — `__name__` is `"__main__"` there, which is not under `whowins`, so every module logger in a running command reached no handler at all while every other test in this file stayed green |
| The flags | Every long flag of every command appears in runbook.md, read off the parsers rather than kept in step by hand, and the same for the shell scripts' own flags |

**`test_analyse.py`** — 23 tests over the run report, built almost entirely on synthetic records:
a report that only ever ran on one model's log would be tuned to that log without anyone deciding to.

| Group | What it pins |
|---|---|
| Which pairs can be read | Two labelled lines of ONE operator message are **not** pooled with two separate turns. Both have an order that varies, so a test asking only "did the order vary" called both free and averaged a primacy effect with a recency one — 0.834 and 0.260 into 0.716, a number describing nothing that happened. Whether both sources are pinned is what tells them apart, read off the record, so it holds for a family whose operator channel is a developer message |
| Model-agnostic | No source name, family, checker key or model appears anywhere. A run naming its sources DEV/CHAT/NOTE reports correctly |
| The numbers | A Wilson interval stays on the scale at 0 and 1, where the normal approximation does not; `later` means later in the prompt and not nearer the task line, which come apart because the task's slot is balanced; solo ability is compared per option and never per trial |

**`test_validation.py`** — 39 tests over the validation scripts and the one data reader.

| Group | What it pins |
|---|---|
| Refusal items | Each names a snake_case gated action, no other family has one, and no two share one |
| Screen 6 | A real host is failed whatever the scheme, and a bare public domain too, while the path family's undotted synthetic destinations (`s3://lake`, `git://mirrors`) pass. An IP-shaped string warns |
| Clean runs | A second run in one process does not inherit the first run's failures |
| Bad files | A file that does not parse is named, by `whowins.data.read_json` and by `check_batch` |
| No side effects | Importing `build_registry` opens no file |

**`test_stats.py`** — 45 tests over phase 1: the counterexample, the estimators, held-out scoring,
power, the gate, and the `strengths` reading guide, which must say what the data under it can
answer.

**`test_families.py`** — 38 tests over the second half of the statistics. Every number is checked
against one worked out another way.

| Group | What it pins |
|---|---|
| The normal distribution | Sheppard's formula on both sides of every branch of the bivariate routine; its edges at no and perfect correlation; the orthant above two dimensions against the one-dimensional integral an equicorrelated one reduces to; a variable with no variance as a step |
| Thurstone and the probit | The two ways of computing independent errors agree; the probit's probabilities match counting the winners of simulated correlated utilities; **pairs pin 10 of the probit's 13 means and covariances and the stage-two slice pins 13**, and with a position term pairs would pin all 14, which is why identification is judged on compositions; a planted correlation comes back; the probit fits at least as well as the Thurstone it nests; a boundary fit says so |
| The context model | A context column is one source's pull on another; the ridge shrinks pulls and never strengths, so a source that never won is still refused; with no ridge, cross-validation over items finds a planted pull and predicts unseen triples better than Plackett-Luce; `canonical` data fit exactly as the draws they came from |
| Regularity | The arithmetic on a hand-built set; a planted pull is flagged and a Luce or probit world is not |
| Capacity | Clopper-Pearson against values worked by hand and the method's 59 and 299; a certified subset that skips tiers; no claim from thin data; **one draw per item keeps its level when an item's repeats move together, and counting every draw certifies a false pair about 13% of the time** |
| The families block | Abstentions counted and left out, the probit refused in stage one and fitted in stage two, reusing each stage's fits changes no number; the report prints what it refused |

Ten faults were planted, one at a time, to check these tests: each failed the test written for it.

**`test_random_effects.py`** — 8 tests over the mixed model and pooling across runs, on
simulated worlds whose truth is known.

| Group | What it pins |
|---|---|
| Item tastes | Planted tastes are found, and an item's taste carries from its pairs to its larger sets; they undo the flattening a pooled fit suffers; a world with no tastes gets a small item variance |
| Family shifts | A planted shift comes back in its direction |
| The fit | The joint mode is where the gradient is zero; a mixed model refuses abstentions |
| Pooling | A harness can be told from a model only when some model was served in more than one harness; a planted spread between models is found, and the report says why it left harness out |

**`test_bundles_and_tiers.py`** — 30 tests over the load bundles and the declared-tier designs.

| Group | What it pins |
|---|---|
| The validator | The worked load cell, written as a bundle, passes, and its lengths are the numbers the load cell's own test pins; eight broken bundles are each refused by name; a length that moves with `k` is refused; two bundles may not share a component, a project or a line, and none may reuse the worked bundle's |
| On disk | Every bundle in `data/load/` passes the validator. In every trial with two or more format groups, one note can obey any choice of members: fixtures for each choice, made into one note in every order, with JSON paragraphs merged into one body, must each read their own label. The same check finds a clash the review found (a dollar prompt under an h1 heading) |
| Fillers | A bundle's filler reads its own project and its own step tools, not atlas-core's |
| The design | A bundle that fails the validator is refused before it becomes a trial; with no bundles the design sends the worked ten |
| Declared tiers | A trial the design builds renders byte for byte as `tier-01` was written by hand; on gpt-oss the policy rides on the developer channel; every pair gets its share of items and every scenario twelve pairs; within a pair, position and content are balanced; a rank needs a policy on an operator channel; capacity reads a tier run as the policy scores it; the design report prints a load run's and a tier run's own balance, where it once crashed |
| Tiers 1 to 6 | 15 pairs of 432 items, six a scenario, 6,480 trials; every tier pair meets every two options of a scenario and the four winner cases fall exactly evenly; capacity reads a run over the tiers it measured, so a 1-to-6 run's upper bound is never 12 |

**`test_load_cell.py`** — 11 tests over the load cell's reading, on worlds planted per bundle
and on the records the scorer writes.

| Group | What it pins |
|---|---|
| Reading records | Only usable replies to load trials are read; a group counts as chosen only when the reply did one of its own members; a filler with no verdict is left out; the worked trials are their own bundle |
| Bundles as replicates | Each bundle weighs the same however many draws it has; a trial every bundle agrees on still has the width of its draws; the t quantile matches published tables |
| Contrasts | A planted conflict effect is found and a null load effect is not; a planted load effect is found with conflict held fixed; a bundle with only one of the two trials is left out of their difference |
| Independence | Groups that fail independently sit on the product of their rates, and groups that fail together sit above it; a trial where every bundle sits on its product says so rather than printing a zero-width interval |
| End to end | Every trial `load-bundles` sends, scored as the run loop scores it, reads back on its own bundle and cell; the command reads a log, writes JSON, and refuses a log with no load trial |

Twelve faults were planted in the module, one at a time; each turned a test red.

**`test_layouts.py`** — 32 tests over the three layout designs, the realism validator and the
reader that pairs layouts within an item.

| Group | What it pins |
|---|---|
| The operator test | Every scenario meets one of the six operator pairs under four layouts with the same options; every family meets every pair, and every two options meet both ways; the operator's line arrives where and as what the layout says; a late operator reaches Qwen 3 only with the trial's word, gpt-oss always, Qwen 3.5 never; where the template refuses one, that layout is not built |
| The one-message test | 270 items, four layouts each; merged puts both lines and the task in one user message; a task is said once, and never inside a collapsed renderer |
| The realism set | An item is sent bare and in context in each order the format allows, the option's own text in its slot after the source's label; a failing batch, or none, is never sent; the validator fails each of its rules on a planted violation, warns on a steering sentence, fails a shared ten-word run, and holds a batch to its assignment |
| Reading them | Planted position and role effects come back paired within the item; a null is not found; later-wins in context against bare comes back; unusable and unchosen replies are read as such |

Eighteen faults were planted in the new code, one at a time; each turned a test red.

**`test_compare.py`** — 11 tests over the comparison across runs, on synthetic `analyse --json`
reports.

**`fixtures/`** — `(checker_key, expected_label, output_text)` triples, one file per source module
in `whowins/checkers/fmt/`. Each key has a fixture per label, plus the specific traps its scenario's
`exclusivity` field names.

| File | Keys | Fixtures |
|---|---:|---:|
| `surface.py` | 30 | 192 |
| `wire_editorial_syntax.py` | 51 | 281 |
| `values.py` | 11 | 59 |
| `tooling.py` | 27 | 149 |
| `prose.py` | 29 | 199 |
| `domain.py` | 22 | 119 |
| `structural.py` | 70 | 383 |

## Writing fixtures

Write them **from the `exclusivity` field** of the scenario. Those fields were authored to be
testable and they name the exact edge case the author closed — "JSON is tested before YAML, so
text that is valid JSON is never labelled yaml_mapping" is a fixture waiting to be typed out.

A positive case per label is the floor, not the job. The bugs are all in the traps:

- **Nesting.** One label's literal form inside another's: `{{host}}` contains `{host}`,
  `urn:uuid:…` contains a bare UUID, `1.78:1` contains `78:1`, `Mon` contains `Mo` contains `M`.
- **Absence.** A label meaning "no marker" must not be winnable by an empty response — and the collection no
  longer contains one, because all 51 such scenarios were rewritten.
- **Prose.** A model that refuses in a sentence has produced no artifact. Ten classifiers scored
  `"Sorry, I don't have enough information."` as a real format choice — a comma read as a delimited
  row, a standalone "I" as both a log level and a roman numeral. Every classifier needs a relevance
  gate: positive evidence the artifact is there, not evidence a marker is absent.
- **Hedging.** Mixed output — half snake_case, half camelCase — must resolve to neither.
- **Boundaries.** `\b` cannot match between two word characters, so it fails after a digit and
  before a letter, and on either side of an underscore. This has now bitten this repo three
  times, most recently in the September rename: `\bbank\b` could not see the `bank` inside
  `test_classifier_labels_match_the_bank_exactly`, and the stale name survived the pass.
- **Lines.** `\s` matches a newline. Inside anything that lives on one line — a name, a count,
  a command — use `[ \t]`. Three classifiers read across lines with `\s`: a count on the line
  after a colon, two single-name lines as one name, a sign-off as script arguments.
- **Talk and framing.** A model asks which instruction to follow, says it cannot help, quotes the
  conflict, or wraps the answer in a lead-in, a fence and a sign-off. Talk must win nothing and
  framing must never swap a label for another option's. Write the non-answer and the wrapped
  answer as fixtures too; the general tests are in `test_checkers.py` under "Talk is not an
  artifact".

## The rule this directory exists for

**A validator that has never failed on a known-bad case tells you nothing when it passes.**

The planted-fault tests at the bottom of `test_checkers.py` are not decoration. When they were
first written, the path-resolver fault *passed the whole suite* — the nine prefix-collision cases
all happen to work under a naive longest-prefix matcher, so the suite looked thorough and did
not discriminate. It took a case nobody would have thought to write (a write that extends a
declared destination without a separator) to catch it.

So: break the checker on purpose, confirm the suite goes red, put it back. Three faults are
pinned that way today — a reordered rule list, a naive prefix match, and a classifier that
guesses instead of returning `UNRESOLVED`.

The same rule applies to the suite's own contracts, and it has already paid out once more.
`test_every_declared_option_is_reachable_by_some_fixture` replaced a weaker test that asked only
whether a key had *some* fixture; the weaker form was green while thirteen declared option values
across ten scenarios had never been produced by any output at all.

One more trap, learned the hard way: **a planted fault that is secretly a no-op reports a false
negative.** One "fault" changed a threshold from 2 to 1 in a place where the value can never be 1,
so nothing changed and the suite looked like it had failed to discriminate. Confirm the fault
actually alters behaviour before drawing any conclusion about the test.

`src/whowins/validation/validate_collection.py` was trusted the same way, against fourteen planted faults
in a copy of the collection. That check still lives as a one-off and belongs here as a suite.

`whowins.splits.check` went further, because a split list fails silently in a way a checker does not: all
sixteen of its checks were confirmed against a planted fault, and then **four faults were planted in the
source** to confirm the tests are not themselves vacuous — deleting the anti-trap check, making a link
rule unable to fire, disabling the frame stripping, and making group naming order-dependent. Each turned
exactly the test meant to catch it red, and only that one.

The fixes for the September outside audit were held to the same rule: 34 faults, one per fix,
each planted back into a scratch copy and each turning its own test red, with the unbroken
baseline green. The audit's own proposed fixes were not taken on trust either — one of them would
have failed a correct scenario. The later rounds were held to it too, among them 15 faults for the
four rewritten message scenarios, 29 for the wider talk gate and the six classifiers, and 9 for the
refusal tools.

The runner suite paid the same rule out again, and immediately. The first fault planted against the
write-tool coupling renamed `write_file` to `emit_artifact` and **nothing failed** — because `emit` is
itself one of the checker's write verbs, so the fault was a no-op. Renaming it to a name carrying no
write verb turned three tests red. Confirm the fault changes behaviour *before* concluding anything
from the silence; that is the third time this exact trap has cost time here.

The serving suite was held to it too. Twenty-three faults were planted one at a time in scratch copies
of the code and scripts — a delivery rule switched off, a seed that ignores the repeat, a serve script
with no version gate, preflight counting a check it could not make as a pass — and each turned its own
test red, with the unbroken copy green. Eleven damaged configs are planted by the suite itself, and its
`_sub` helper refuses a plant whose text is not there, so a config fault cannot be a silent no-op.
