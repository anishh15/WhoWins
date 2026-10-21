# Splits

Which base scenarios may be fitted on, and which are held back.

**These files are checked in on purpose.** A split list is a pre-registration commitment, not a build
artifact: it is built once, frozen, and published with the results so a reader can tell that the held-out
set really was held out. That is the opposite of `data/REGISTRY.md`, which is gitignored because a
checked-in summary of the collection can only drift out of date. Do not add this directory to `.gitignore`.

Design, thresholds and the measurements behind them: [docs/codebase/05_splits.md](../../docs/codebase/05_splits.md).

| File | Over | Shape | Question it answers |
|---|---|---|---|
| `item.json` | scenarios | train 648 / val 162 / test 270 | Does a scale fitted here hold on scenarios it never saw? |
| `axis.json` | scenarios | 13 leave-one-out folds | Does it transfer from one kind of constraint to another? |
| `domain.json` | scenarios | 6 leave-one-out folds | Does it transfer from one subject area to another? |
| `source_pair.json` | sources | 10 leave-one-out folds | Does it predict a source pair it never saw? |
| `set.json` | compositions | two stages | **The headline.** Do pairs predict triples, and pairs-plus-triples predict five-way? |

Five separate lists, applied **one at a time**. They are not five columns of one assignment and must never
be merged into a single random split — reviewers were explicit that doing so answers every question weakly.

The first three are properties of the **collection**: which scenarios may be fitted on. The last two are
properties of the **design**: which source pairs and which compositions. All five are frozen together, so a
change to the collection invalidates all five at once and `check` says so.

## Working with them

```bash
PYTHONPATH=src python3 -m whowins.splits.check                     # verify what is on disk
PYTHONPATH=src python3 -m whowins.splits.check --exclude-file ids.txt   # what would dropping these do?
PYTHONPATH=src python3 -m whowins.splits.build                     # rebuild (see the warning below)
python3 -m pytest tests/test_splits.py                         # 43 tests
```

**Rebuilding after data collection has started moves the goalposts.** Every file records the parameters and
a fingerprint of the collection it was built from, and `check` fails if the collection has since changed in
any way that could move a scenario. If you need to re-freeze, do it deliberately and record why.

## Things worth knowing before using them

**`item.json` groups scenarios, and the grouping is built rather than looked up.** `seed_family` is unique
on all 1,080 items, so grouping by it — which is what the dataset plan literally says — groups nothing.
The checker refuses such a split by name.

**The dry-run subset in `item.json` comes from `train` only**, so phase 2 cannot inform what validation or
test measure. It is a proposal at 99 scenarios, not a commitment.

**Model-class selection happens once, on `item`'s validation set.** The chosen class is then fixed across
every fold of `axis` and `domain`.

**`axis.json` has one weak fold.** `structural` is grouped by needing a parser, not by subject. Report it
separately.

**`domain.json`'s folds are uneven, and so is family coverage inside them** — `web` holds out no `path`
scenarios at all. Each fold records what it removes per family; read it.

**`set.json` carries the headline.** Stage one fits the ten pairs and predicts every triple with nothing
refitted; stage two adds four preselected triples — the fewest that put every source pair in some triple —
and predicts the five-way. A pair in no triple would be a correlation stage two cannot estimate, so that
covering property is checked rather than assumed.

**The five sources are derived from the worked trials**, not written down twice. There is no sixth: the
"ten sources" three documents once computed over was pre-reframe wreckage, corrected in commit `4a8d2c4`.

Two further splits — renderer and model family — name run conditions rather than items and are fixed at
pre-registration.
