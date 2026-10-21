# 12 — `tests/`: what is pinned, and how it is trusted

```bash
python3 -m pytest -q tests/        # 2,387 collected: 2,383 pass, 4 skipped, ~2.5 min
```

`conftest.py` puts `src/` on the path, so no install and no `PYTHONPATH` are needed. Nothing calls
a model. The serve script runs against a fake `vllm` that prints what it was given and a fake
`nvidia-smi` that prints made-up cards, and preflight talks to a stub server on localhost.

| File | Tests | Covers |
|---|---:|---|
| `test_checkers.py` | 1,491 | the checkers and their 1,382 adversarial fixtures |
| `test_serving.py` | 216 | the roster, the two machines, serve files, delivery, policies, GPUs, scripts, preflight |
| `test_runner.py` | 190 | the renderer, the response side, composite trials, fillers |
| `test_batch.py` | 118 | the trial design and the run loop, against a stub HTTP server |
| `test_logs.py` | 85 | the progress bar, the logging, and the flag reference in `runbook.md` |
| `test_splits.py` | 44 | the frozen split lists |
| `test_stats.py` | 47 | the counterexample, the estimators, scoring, power, the gate, the `strengths` reading guide |
| `test_families.py` | 39 | Thurstone, the correlated probit, the context model, regularity, capacity, the normal integrals |
| `test_bundles_and_tiers.py` | 30 | the load bundles, their validator, and the declared-tier designs |
| `test_load_cell.py` | 11 | the load cell's reading: per trial, the contrasts, independence |
| `test_layouts.py` | 32 | the operator, one-message and realism designs, the realism validator, and their reader |
| `test_validation.py` | 39 | the validation scripts and the one data reader |
| `test_analyse.py` | 25 | the run report, and the scoring fingerprint |
| `test_compare.py` | 12 | the comparison across runs |
| `test_random_effects.py` | 8 | the mixed model and pooling across runs |

The four skips read the test runs' records, which are not part of this repository: one in
`test_batch.py`, two in `test_analyse.py` and one in `test_stats.py`. With those records under
`results/`, they run.

---

## 1. The rule this directory follows

A validator that has never failed on a known-bad case tells you nothing when it passes.

So the suite plants faults, confirms that they are detected, and puts the code back. The rule has
found real problems several times, and each case is recorded:

- When the planted-fault tests were first written, the **path-resolver fault passed the whole
  suite**. The nine prefix-collision cases all happen to work under a naive longest-prefix matcher,
  so the suite looked thorough without being able to tell the two apart. A case nobody would have
  thought to write (a write that *extends* a declared destination without a separator) was needed
  to detect it.
- `test_every_declared_option_is_reachable_by_some_fixture` replaced a weaker test that only asked
  whether a key had *some* fixture. The weaker test passed while **thirteen declared option values
  across ten scenarios had never been produced by any output at all**.
- **A planted fault that is secretly a no-op gives a false negative.** One "fault" changed a
  threshold from 2 to 1 where the value can never be 1, so nothing changed and the suite appeared to
  miss it. The first fault planted against the write-tool coupling renamed `write_file` to
  `emit_artifact`, and **nothing failed**, because `emit` is itself one of the checker's write
  verbs. Confirm that a fault changes behaviour *before* concluding anything from a passing suite.
  This mistake has cost time here three times.
- **A restored fault can keep running.** Python checks a cached `.pyc` against the source's size and
  its modification time in whole seconds. A fault the same length as the line it replaced, restored
  within the same second, went on running from the cache, and eleven tests failed on a clean file.
  Delete `__pycache__` (or touch the file) after restoring one.

Planted faults by area: 34 for the first September audit fixes (one per fix), 23 in the serving
code and scripts, 15 for the four rewritten message scenarios, 29 for the wider talk gate and six
classifiers, 14 in a copy of the collection for `validate_collection`, 10 damaged split files, 4 in
the `splits/` source, 9 for the refusal tools, 34 damaged configs, 4 damaged policy files, 10 in
the second half of the statistics (`test_families.py`) and 15 in the random effects, pooling, the
tier design, the bundle fillers, the bundle validator and the capacity reader.

One of those 15 first went unnoticed: always giving the win to the same side of a tier pair
passed every test. The balance test computed which option won and never asserted it. Fixing the
test showed that the design itself was unbalanced
([16_load_bundles_and_tiers.md](16_load_bundles_and_tiers.md), section 6), so a fault that passes
can point at the code as well as at the test.

The fixes made at the end of September 2026 (findings A to Y of
the code audit) follow the same rule. Each has a test or fixtures that were run
against the old code and failed there:

| Finding | Test | Fails on the old code with |
|---|---|---|
| A | `test_analyse.py::test_the_fingerprint_moves_with_anything_that_decides_a_verdict` | the planted `_WRAP_UP` change leaving the hash unchanged |
| B/C | `test_stats.py::test_the_strengths_caveat_follows_the_data_it_is_printed_under` | the footer's text on both a pairs-only and a ladder-shaped report |
| D | `test_compare.py::test_a_run_with_no_solo_arm_is_left_out_of_the_solo_intersection` | an empty intersection |
| E | `test_analyse.py::test_an_unlabelled_reply_is_read_on_the_turn_that_was_scored` | `no_artifact` instead of `artifact_shaped` |
| H | 11 fixtures in `fixtures/prose.py` and `fixtures/surface.py` | 8 of the 11 |
| I | 3 `key_casing` fixtures in `fixtures/surface.py` | 2 of the 3 |
| K | `test_batch.py::test_a_kill_inside_a_character_costs_one_trial_not_the_run` | `UnicodeDecodeError` |
| L | `test_validation.py::test_a_scenario_missing_a_field_is_reported_rather_than_raised` (11 cases) | a `KeyError` in 3 cases for `validate_collection` and 5 for `check_batch` |
| F | `test_batch.py::test_reasoning_this_package_splits_off_is_not_echoed_into_the_next_turn` | the `<think>` block in the next request |
| M | `test_batch.py::test_a_turn_that_cannot_be_sent_as_recorded_costs_its_trial_not_the_run` | `UndeliverableTrial` out of `run_batch` |
| N | `test_batch.py::test_a_server_that_will_not_say_its_version_is_not_recorded_as_the_pinned_one` | exit 0 and the pinned version recorded |
| P | `test_batch.py::test_a_second_process_on_the_same_log_is_refused_before_it_sends_anything` | both trials sent while another process held the log |
| R | `test_batch.py::test_a_verdict_names_which_options_a_reply_gave_and_whether_it_flagged` | a change of `alternatives` or `communication` compared equal |
| X | `test_batch.py::test_a_trial_id_that_now_names_a_different_trial_is_not_rescored` | the swapped row scored instead of skipped |
| Y | `test_analyse.py::test_a_win_several_sources_demanded_is_not_credited_to_one_of_them` | the first of two sources credited |
| U | `test_splits.py::test_a_domain_named_other_is_not_pooled_without_a_word` | no error from the build, and none from the check |
| V | `test_validation.py::test_a_copy_without_the_collection_says_so_rather_than_reading_nothing` | an empty list instead of an error |
| dead code | `test_batch.py::test_a_run_names_the_scenarios_it_will_score_from_prose_before_sending` | no warning, because nothing on the run path called `weak_scoring` |
| J | `test_checkers.py::test_an_instruction_said_again_without_quotes_wins_nothing`, `…_said_again_and_then_done_still_counts_as_done`, `…_only_shares_words_with_an_instruction_is_kept` | 74 of the 1,200 option texts winning, 55 of 1,270 restate-then-do cases losing their label, and the restated line kept |
| fmt-0200 | 2 `number_word_threshold` fixtures in `fixtures/prose.py` | both |
| W | `test_batch.py::test_a_finished_log_can_be_read_compressed`; analyse's report compared byte for byte before and after | a compressed log not found |
| Y | `test_stats.py::test_a_free_prediction_is_not_read_as_a_choice_between_distinct_options` | `ChoiceError: the same option twice` |
| G | `test_batch.py::test_in_the_flat_ladder_every_source_carries_every_option_equally` and `…_no_option_is_tied_to_a_position` | the old ladder, measured by the same code: a gap of 16 trials and 50 points, which the tests pin |

The fixes from the first read of the Qwen 3 main run (October 2026) were each run against the old
code too:

| Fix | Test | Fails on the old code with |
|---|---|---|
| resume by repeat | `test_batch.py::test_a_draw_that_landed_before_an_earlier_one_is_not_sent_again` | repeat 1 sent again and repeat 0 never |
| a draw logged twice | `test_batch.py::test_a_draw_logged_twice_is_read_once_and_its_first_record_kept` | both records read |
| docstring-only fingerprint | `test_analyse.py::test_a_fingerprint_moved_only_by_a_docstring_is_the_same_instrument`, `test_compare.py::test_runs_whose_fingerprints_differ_by_a_docstring_alone_are_comparable` | "NO" for both |
| unusable replies | `test_analyse.py::test_an_unusable_reply_is_counted_in_hygiene_and_never_read_as_behaviour`, `test_stats.py::test_an_unusable_reply_is_never_read_as_a_choice` | the truncated reply's win counted |
| the shared option | `test_stats.py::test_the_shared_option_is_read_among_draws_where_an_option_won` | the no-winner draw counted and the predicted share not renormalised |
| round-off in `cholesky` | `test_families.py::test_round_off_after_near_zero_pivots_is_a_step_and_not_a_crash` | `NormalError: the covariance is not positive definite` |
| a bare path name | `test_checkers.py::test_bare_name_scores_the_option_it_names`, `…_resolves_wherever_it_names_one_destination` | `off_menu` for `ap4` |

## 2. `test_checkers.py`: organised around properties, not modules

| Group | What it pins |
|---|---|
| Safety properties | sentinels are not option values anywhere; an unimplemented key raises; **no response that answers nothing wins anything**; at most one option can match |
| Format classifiers | 1,382 fixtures; every classifier's label set is **exactly** the value set the collection declares; **every one of the 1,200 declared option values is reached by some fixture** |
| Trace checkers | the four keys, the nine prefix-collision cases, a bare name scoring the one destination it names, every ordering permutation reachable, write detection by *word*, the common destination argument names |
| Communication axis | flagging a conflict and obeying the wrong instruction are **independent** |
| Coverage bookkeeping | all 1,080 scenarios executable, per family, asserted and not only reported |
| Talk is not an artifact | 47 realistic non-answers win nothing; a reply quoting both sides and asking wins nothing; framing never swaps a correct label for another option's; a plain statement gets a label only in the eight scenarios where prose *is* the artifact, pinned by name |
| Two answers in one reply | a second fenced block, an "Or"/"Alternatively" paragraph, or one answer per heading gives `multiple`, pinned at 2,383–2,392 of 2,400 constructed replies per style; no single answer with an explanation beside it is read as two |
| What the first run found | four checker holes found in real replies: an artifact in inline code, a heading in capitals with a colon, one answer per source under its own header, and `hedged` matching a courtesy sign-off |
| Refusal | a question is not a decision; a reply that flags decides only in the first person; the gated action decides comply, and *saying* it was done is not doing it |
| Planted faults | a reordered rule list, a naive prefix match, a guessing classifier, a bare name shared by two destinations guessed |

`test_fixture` is parametrized over every fixture, which is why the file has more tests than any
other.

### `fixtures/`: `(checker_key, expected_label, output_text)` triples

There is one file per source module, with 1,382 fixtures over 240 keys.

| File | Keys | Fixtures |
|---|---:|---:|
| `structural.py` | 70 | 383 |
| `wire_editorial_syntax.py` | 51 | 281 |
| `prose.py` | 29 | 199 |
| `surface.py` | 30 | 192 |
| `tooling.py` | 27 | 149 |
| `domain.py` | 22 | 119 |
| `values.py` | 11 | 59 |

The fixtures are written **from the `exclusivity` field** of each scenario. Those fields were
written to be testable, and each names the exact edge case its author closed: *"JSON is tested
before YAML, so text that is valid JSON is never labelled yaml_mapping"* translates directly into a
fixture. One positive case per label is the minimum. The bugs are all in the hard cases: nesting,
absence, prose, hedging, `\b` boundaries, `\s` crossing lines, framing, and rules that fire on a
single word (see [04_checkers.md](04_checkers.md) §5).

## 3. `test_runner.py`: the acceptance test

| Group | What it pins |
|---|---|
| Acceptance | all **70 hand-written trials re-render byte for byte** |
| Derived share | how much of each cell the vocabulary produced instead of quoting, with four cells at 100%. **The byte comparison alone can be passed by quoting**, and a wrong header is detected here and nowhere else |
| Vocabulary | an undemonstrated combination raises; every wording is used by some trial; the two policy tables stay in step |
| Spec invariants | duplicate slots, element order vs slot order, a rank with no policy, a Block in a collapsed renderer |
| End to end | **every option of all 1,080 scenarios**, from tool schema or fixture text through the envelope and parser to the score it aimed at: 5,040 pairs |
| Couplings | the write tool's name still matches the checker's verb list, and its argument still matches the checker's target names |
| Composite trials | scored per conflict group; the same six tools in all ten load trials; the note read from `write_file`'s content; every filler checked by code; **every n-level the same length in tokens under both pinned Qwen tokenizers** (10/25/59/96 and 11/28/66/107) |
| Planted faults | a broken header, a dropped task line, a changed JSON indent, reversed span order, a guessing parser, a filtered tool call |

It also calls `tools.weak_scoring` and asserts the list is empty. `test_batch.py` checks that a
run names a scenario it would score from prose before it sends anything.

## 4. `test_batch.py` and `test_serving.py`

`test_batch.py` runs a real HTTP stub that answers, refuses, returns 500 or hangs up **on
demand**. It pins:

- the design: a Latin square over source pairs and option pairs, 108 scenarios for every source
  pair, and the same config always building the same list;
- what is sent: every trial reaches **both** Qwen families as recorded;
- the ladder: every source in every slot equally often at every size, every arrangement used the
  same number of times, and a solo arm whose ids cannot collide with a pair's, on both ladders; and
  for the flat ladder, every source carrying every option to within one trial, no option tied to a
  position, and every option set in every composition;
- the client: a 4xx is not retried, and a retried draw keeps its seed;
- resuming: a line cut off by a kill costs one trial and not the run, whether it is cut on an ASCII
  boundary or one byte into an em dash, and `report()` reads a log in either state.

`test_serving.py` pins the fifteen models **in the test as well as in the roster**, so an edit to
only one of them fails. It also pins the two machines and what each can and cannot do, and 37
damaged configs and 4 damaged policy files, each rejected on load. The 32B's `-sm80` run configs
and serve file are read against their DGX-1 twins: the same trials, seeds and first request, and
no difference the machine does not force, with a planted one caught. The most involved part checks
**what reaches Qwen behind vLLM 0.28.0's own rewrite, reproduced from its source**, using the three
real chat templates. It confirms that a `developer` message is rewritten by 0.28.0 and **dropped
without an error by Qwen 3's template on 0.8.5**, so both are rejected, and that a late system
message fails the Qwen 3.5 template and is rejected on Qwen 3 as well, so one trial runs on both
ladders.

## 5. `test_logs.py`: the output contract

It pins that neither the bar nor a log record ever reaches stdout, that `serving shell KEY` still
prints nothing but shell assignments (a script runs `eval` on it), that importing the package
installs no handler anywhere, that the bar's fields are dropped in a stated order so the line never
wraps, and that the estimate is withheld until there is enough data for it. It also pins that
**a command started with `python3 -m` actually logs**. `__name__` is `"__main__"` in that case,
which is not under `whowins`, so every module logger in a running command once reached no handler while
every other test passed.

It also reads the argument parsers and the shell scripts and checks that `runbook.md`'s flag
reference documents **every long flag of every command**, so the reference cannot fall behind.

## 6. `test_analyse.py`: built on synthetic records on purpose

The file's docstring gives the reason: "a report that only ever ran on one model's log would be
tuned to that log without anyone deciding to."

It pins the pair-kind separation (two labelled lines of one message are **not** pooled with two
separate turns), that the report names no source or model, that a Wilson interval stays on the
scale at 0 and 1, that `later` means *later in the prompt* and not *nearer the task line* (the two
differ because the task's slot is balanced), and that solo ability is compared **per option** and
never per trial. It also holds the fingerprint tests: the hash is stable, the `scoring` section
gives three different answers for current, older and unstamped records, and the hash moves with
every module that decides a verdict.

`test_compare.py` builds synthetic `analyse --json` reports in the same way.

## 7. The newest files: bundles, tiers and random effects

`test_bundles_and_tiers.py` treats two hand-made things as the reference. The worked load cell,
written in the bundle format, must pass the bundle validator, with the lengths the load cell's own
test pins. A tier trial the design builds must render byte for byte as `tier-01` was written by
hand. Around those it pins every refusal of the validator, the data on disk, and the tier design's
balance. Two of its checks read real classifiers:

- **one note can obey any choice of format members.** For every bundle trial with two or more
  format groups, fixture texts for each choice of members are made into one note, in every order,
  and each classifier must read its own label. JSON paragraphs merge into one body; without that,
  three keys reading one webhook body failed on fixtures although a real delivery read correctly.
- **the check can fail.** A dollar prompt under an `h1` heading, a clash the review found, must be
  reported.

The review also checked each bundle on realistic artifacts, which found more than fixtures did
([16_load_bundles_and_tiers.md](16_load_bundles_and_tiers.md), section 4). Those probes are not in
the suite: each is one reviewer's picture of what a model would write.

`test_random_effects.py` works on simulated worlds, as `test_families.py` does. `test_serving.py`
now also sends every load-bundle trial and every 97th tier trial through the three real Qwen
templates.

## 8. Where the suite could be stronger

Three gaps are known:

- for the frozen designs, `--balance`'s option columns are printed but not bounded; only the flat
  ladder's are (finding G);
- the composite, filler and `all_satisfied` path is now sent by the main load configs and reaches
  the real templates in the suite, but no run has sent it yet (finding S);
- the realistic-artifact probes that shaped the bundles are a reviewer's judgement and are not
  pinned.
