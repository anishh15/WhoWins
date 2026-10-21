# 03 — `src/whowins/validation/`: screening the collection

There are three standalone scripts. Two only read the collection, and one writes a build artifact.
They import only the standard library (not even `whowins.data`), so screening the collection can never
depend on how it is scored.

```bash
python3 src/whowins/validation/check_batch.py             # or: PYTHONPATH=src python3 -m whowins.validation.check_batch
python3 src/whowins/validation/check_batch.py fmt-0211-0240.json   # focus one batch's report
python3 src/whowins/validation/validate_collection.py
python3 src/whowins/validation/build_registry.py
```

The validators exit with `1` on any FAIL and `0` otherwise. A batch is committed only when both
report no FAIL.

---

## 1. `check_batch.py`: the cross-cutting screens

```
main(argv)
 ├── reset()                 empties the module-level fails/warns lists
 ├── load()                  every data/scenarios/*/*.json; an unparseable file is a FAIL, not a crash
 ├── check_all(scenarios)
 │    ├── check_one(s)       for each scenario
 │    └── check_collection(whole)   pairwise screens, over the scenarios that have every field
 └── report(whole, focus)    prints, returns 1 if any FAIL
```

`fails` and `warns` are module-level lists so that every screen can append to them. That is why
`reset()` exists and is called first: without it, a second run in the same process (a test, for
example) would inherit the first run's failures and report problems that were already fixed.
`tests/test_validation.py::test_check_batch_main_starts_from_empty_verdicts` pins this.

`check_all` returns the scenarios that carry all twelve `REQUIRED` fields. A scenario missing one
gets a FAIL per missing field from `check_one`, which then stops screening it, and it is left out of
`check_collection` and `report`. Those later screens index the fields directly, so an incomplete
scenario used to end the run with a `KeyError` instead of the FAIL already recorded.
`tests/test_validation.py::test_a_scenario_missing_a_field_is_reported_rather_than_raised` removes
each required field in turn (except `scenario_id`, which `load()` requires) and runs both
validators.

### Per-scenario screens (`check_one`)

| # | Screen | Verdict |
|---|---|---|
| 1 | all 12 required fields present; if one is missing, no further screen runs on that scenario | FAIL |
| 2 | exclusivity by construction: one key across all options, `checker_key` matches it, no repeated value | FAIL |
| 2b | `exclusivity` prose under 60 characters | warn |
| 3 | option word-length spread ≤ 20% of the mean | FAIL |
| 4 | the *task* singles out exactly one option (shared tokens stripped) | warn |
| 5 | real product / company names | FAIL (65 vendor names) or warn (19 ambiguous words) |
| 6 | honest sourcing: `status == "synthetic-preview"`, `url is null` | FAIL |
| 6b | anything reachable: a URL, `github.com`, an email, a scheme naming a dotted host, a public domain | FAIL; an IP-shaped string warns |
| 8 | option count = 2 (binary/refusal) or 5 | FAIL |
| 9 | a format task that asks the model to *decide* instead of to *produce* | warn |
| — | `difficulty` in easy/medium/hard, `authored_by` matches `<pipeline>/<model>` | FAIL |

Two details were bugs once:

- **Never use `\b` against an identifier.** `\bdatadog\b` cannot see the `datadog` inside
  `export_datadog`, because underscore is a word character. The real-name screen uses explicit
  lookarounds instead: `(?<![a-z0-9])name(?![a-z0-9])`.
- **`NAME_EXEMPT`** lists the few scenarios where a vendor name is the *setting* of the scenario and
  not one of the choices (`pypi://`, `mvn://`, a Helm chart path). Each entry is a reviewed
  exception with a comment.

Screen 9's `DELIBERATES` regex (`^(decide|say|choose|pick|settle|determine|work out|agree|figure)`)
applies to the **format family only**. The other four families are scored from a trace, where
"Work out what changed in payments.py" is answered by calling a tool, and the call is the
measurement. The 21 items it flags chose an option in 11% of trials against 25% for the rest. The
screen warns instead of failing, because the solo arm decides whether an item works, and a keyword
cannot.

### Collection-wide screens (`check_collection`)

| Screen | What repeats is a FAIL |
|---|---|
| duplicate `scenario_id` | exact |
| duplicate `seed_family` | exact |
| duplicate content key | `(checker_key, {values})`, or for ordering `{steps}`; refusal is exempt |
| near-duplicate value set | same key, all but one value shared |
| shared option texts | ≥ max(2, n−1) identical option texts between two scenarios |
| near-duplicate tasks | word-level Jaccard ≥ 0.80 |
| suffix-set reuse | tool/path only: identical distinguishing-token sets |
| templating skeleton | same shared-word core across options (≥3 words); refusal/ordering/tool/path exempt |
| one-word option pairs | every option pair differs by ≤2 words → warn |

The refusal family is exempt from the content-key screen because every refusal item has the values
`{comply, decline}`. What makes two refusal items different is the situation and the two option
texts.

Three of these screens run `itertools.combinations` over all 1,080 scenarios, which is 582,660
pairs each. The whole script still finishes in a few seconds, and it only runs at review time.

## 2. `validate_collection.py`: per-family invariants

It has the same skeleton (`reset` / `load` / `check` / `check_collection` / `main`) and asks
different questions.

```python
FAMILY_SPEC = {
    "format":   dict(prefix="fmt",  n=5, key=None,              src="classifier"),
    "tool":     dict(prefix="tool", n=5, key="first_tool_call", src="trace"),
    "path":     dict(prefix="path", n=5, key="write_target",    src="trace"),
    "ordering": dict(prefix="ord",  n=5, key="step_order",      src="trace"),
    "refusal":  dict(prefix="ref",  n=2, key="decision",        src="trace"),
}
TARGET = {"format": 240, "tool": 240, "path": 240, "ordering": 240, "refusal": 120}
```

For each scenario, `check` verifies that the family matches the directory, the id prefix matches
the family, and `key_source` matches. The option count and the ids (`o1..oN`) must be exact, the
checker key must be the family's, and `task`, `exclusivity`, `seed_family` and every option `text`
must be non-empty.

Family rules:

- **refusal**: values exactly `{comply, decline}`; `binary: true` (a warning if missing); an
  `action_tool` naming a snake_case tool of two words or more (**FAIL if absent**, because all 120
  once lacked one and had to be scored from prose); and no other family may carry an
  `action_tool`.
- **ordering**: every value bracketed, exactly three steps, all five options permutations of one
  step set, no repeated permutation, and `dropped_permutation` naming the sixth permutation the
  options leave out. Both sides are normalised before the comparison, because
  `dropped_permutation` is written `a, b, c` while option values are written `[a,b,c]`.
- **path**: every target inside `sandbox_root`.
- **tool**: `tools_available` equals the option values.

Across the collection, `check_collection` verifies that the per-family counts reach `TARGET`, that
ids are contiguous `1..target`, that every `action_tool` is named once, and that **every worked
trial still points at a real scenario whose checker string matches the trial's own copy**. The last
check fails when a scenario is edited after a trial quoted it.

`check` and `check_collection` read `task`, `family` and `options` with `.get`, so a scenario that
lacks one is reported by the per-family checks (an empty task, a family that does not match its
directory, zero options) and does not raise. A worked trial that names such a scenario's options is
then reported as pointing at an option that does not exist.

The "GIVEAWAY" warnings (55 today) apply the same idea as screen 4 after removing a stopword list.
They are triaged, and the equal-reasonableness screen, where a model's actual solo behaviour
decides, gets the final say.

## 3. `build_registry.py`: the one script that writes

It regenerates `data/REGISTRY.md`: every `seed_family` already taken and, per family, a table of
every five-value set, step triple or refusal situation already used. Authors read it before
writing a batch so that nothing collides.

It has two intended behaviours:

- A file that does not parse is **skipped with a message**, the incomplete registry is still
  written, and the script exits with `SystemExit` telling you not to hand the registry out. An
  author may be in the middle of writing a file, and a registry that is missing a batch without
  saying so would be worse.
- The registry is **gitignored**. A checked-in summary of the collection could only drift, and the
  collection is the source of truth. `tests/test_validation.py::test_importing_build_registry_opens_no_file`
  pins that importing the module opens no file.

## 3b. `check_load.py`: the load bundles

A read-only check over every bundle in `data/load/`: the ten trials on the worked cell's grid,
every line a verbatim option text or one of the bundle's own fillers, every filler of a known kind
with the right value, no component, project, task or line shared with another bundle, each trial
rendering as recorded with tools that do not clash, and each `n`-level one length in tokens under
both pinned Qwen tokenizers when they are cached. The `load-bundles` design runs the structural
part before it builds anything. Tested against the worked cell written as a bundle, which passes
with the lengths the load cell's own test pins, and against eight planted faults.
[16_load_bundles_and_tiers.md](16_load_bundles_and_tiers.md), section 3.

## 4. How these are trusted

A validator that has never failed on a known-bad case tells you nothing when it passes.

`validate_collection.py` was run against a copy of the collection with **fourteen planted faults**
and reported all fourteen. A clean pass had hidden real bugs in both screens: the `\b` problem
above, and a giveaway check that stripped no shared prefix and so matched all five options at once.

`tests/test_validation.py` has 38 tests. They cover screen 6 against reachable and synthetic
destinations, the refusal `action_tool` rules, a clean second run in one process, a file that does
not parse being *named*, the format-task screen matching exactly the 21 items that were read
manually, and a scenario missing each required field being reported by both validators.
