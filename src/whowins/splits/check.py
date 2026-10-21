"""Verify the frozen split lists on disk. READ-ONLY.
Every rule that built a split is checked back against the file, so a hand-edited list or a
changed threshold fails rather than quietly shipping. It never writes."""

from __future__ import annotations

import argparse
import collections
import itertools
import os
import sys
from typing import Sequence

from ..data import ROOT, DataFileError, read_json
from .axes import axis_of
from .build import OUT_DIR, PROPORTIONS, STAGE_TWO_SLICE_ANCHOR, fingerprints
from .grouping import build_groups, load_collection
from .sources import covering_slice, load_sources

OVERALL_TOLERANCE_PP = 1.0
"""Overall share may drift this far from target, in percentage points. The build
achieves 0.00; 1.0 leaves room for a future collection without hiding a real
problem."""

FAMILY_TOLERANCE_PP = 3.0
"""Per-family share tolerance. Also 0.00 today. Looser than the overall figure
because a family with few groups is lumpier -- refusal has the fewest."""

fails: list[str] = []
notes: list[str] = []


def fail(code: str, msg: str) -> None:
    fails.append(f"{code}: {msg}")


def note(msg: str) -> None:
    notes.append(msg)


def _load(name: str) -> dict | None:
    path = os.path.join(OUT_DIR, f"{name}.json")
    if not os.path.exists(path):
        fail("SPLIT-1", f"{os.path.relpath(path, ROOT)} does not exist -- "
                        f"run `python3 -m whowins.splits.build`")
        return None
    try:
        return read_json(path)
    except DataFileError as exc:
        fail("SPLIT-1", f"{exc}")
        return None


# --------------------------------------------------------------------- checks


def check_fingerprint(split: dict, current: dict) -> None:
    """SPLIT-2/3 -- is this split still about this collection?"""
    stored = split.get("collection_fingerprint", {})
    if stored.get("content") != current["content"]:
        fail("SPLIT-2",
             f"{split['split_id']}: the collection has changed in a way that moves "
             f"scenarios. Stored {stored.get('content', '?')[:23]}…, "
             f"current {current['content'][:23]}…. This split is stale: rebuild it "
             f"and record the re-freeze, or restore the collection.")
    elif stored.get("full") != current["full"]:
        note(f"{split['split_id']}: prose in the collection has changed (a note or "
             f"an exclusivity argument) but nothing that moves a scenario. The "
             f"split stands.")


def check_partition(split: dict, ids: Sequence[str], sides: dict[str, list[str]],
                    what: str) -> None:
    """SPLIT-4 -- every scenario in exactly one place, and nothing invented."""
    seen: collections.Counter = collections.Counter()
    for side, members in sides.items():
        seen.update(members)

    known = set(ids)
    unknown = sorted(set(seen) - known)
    missing = sorted(known - set(seen))
    repeated = sorted(k for k, n in seen.items() if n > 1)

    if unknown:
        fail("SPLIT-4", f"{split['split_id']}/{what}: {len(unknown)} ids are not in "
                        f"the collection, e.g. {unknown[:5]}")
    if missing:
        fail("SPLIT-4", f"{split['split_id']}/{what}: {len(missing)} scenarios "
                        f"appear nowhere, e.g. {missing[:5]}")
    if repeated:
        fail("SPLIT-4", f"{split['split_id']}/{what}: {len(repeated)} scenarios "
                        f"appear more than once, e.g. {repeated[:5]}")


def check_groups_whole(split: dict) -> None:
    """SPLIT-5 -- a group must never straddle two sides. The point of grouping."""
    where = {}
    for side, ids in split["assignment"].items():
        for sid in ids:
            where[sid] = side
    for gid, members in split["groups"].items():
        sides = {where.get(sid) for sid in members}
        if len(sides) > 1:
            fail("SPLIT-5", f"group {gid} ({len(members)} scenarios) is split across "
                            f"{sorted(s for s in sides if s)} -- near-duplicate "
                            f"scenarios on both sides of the split is the exact "
                            f"leakage this grouping exists to prevent")


def check_grouping_reproduces(split: dict, collection) -> None:
    """SPLIT-6 -- do the current rules still produce the recorded groups?
    Catches a hand-edited list and a changed threshold with one comparison."""
    fresh, _ = build_groups(collection)
    stored = {gid: sorted(ids) for gid, ids in split["groups"].items()}
    if fresh != stored:
        only_fresh = set(map(tuple, fresh.values())) - set(map(tuple, stored.values()))
        fail("SPLIT-6",
             f"the recorded groups do not match a fresh run of the link rules "
             f"({len(stored)} recorded, {len(fresh)} rebuilt, "
             f"{len(only_fresh)} groups differ). Either the file was edited or "
             f"grouping.py changed; re-freeze on purpose.")


def check_grouping_is_real(split: dict) -> None:
    """SPLIT-7 -- the anti-trap check.
    A grouping where every group holds one scenario has grouped nothing, which is what
    following the dataset plan literally would produce, because the field it names is unique
    per scenario."""
    groups = split["groups"]
    n_groups, n_items = len(groups), sum(len(v) for v in groups.values())
    grouped = sum(len(v) for v in groups.values() if len(v) > 1)

    if n_groups >= n_items:
        fail("SPLIT-7",
             f"every group holds exactly one scenario ({n_groups} groups over "
             f"{n_items} scenarios), so nothing is grouped and this is a random "
             f"split under a grouped split's name. This is what grouping by "
             f"`seed_family` produces -- that field is unique on all 1,080 "
             f"scenarios. Build the groups from measured similarity instead; see "
             f"whowins/splits/grouping.py.")
        return

    note(f"grouping holds {grouped} scenarios in {sum(1 for v in groups.values() if len(v) > 1)} "
         f"multi-scenario groups (largest {max(len(v) for v in groups.values())}); "
         f"the rest are singletons, which is expected for a hand-written collection.")


def check_proportions(split: dict, collection) -> None:
    """SPLIT-8/9 -- overall and per-family shares within tolerance."""
    sides = split["assignment"]
    total = sum(len(v) for v in sides.values())

    for side, target in PROPORTIONS.items():
        got = len(sides.get(side, [])) / total
        drift = abs(got - target) * 100
        if drift > OVERALL_TOLERANCE_PP:
            fail("SPLIT-8", f"{side} holds {got:.1%}, target {target:.0%} "
                            f"({drift:.2f} pp off, tolerance {OVERALL_TOLERANCE_PP})")

    family = {s["scenario_id"]: s["family"] for s in collection}
    per: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for side, ids in sides.items():
        for sid in ids:
            per[family[sid]][side] += 1

    for fam, counts in sorted(per.items()):
        n = sum(counts.values())
        for side, target in PROPORTIONS.items():
            drift = abs(counts[side] / n - target) * 100
            if drift > FAMILY_TOLERANCE_PP:
                fail("SPLIT-9",
                     f"family {fam}: {side} holds {counts[side]}/{n} "
                     f"({counts[side]/n:.1%}), target {target:.0%}, "
                     f"{drift:.2f} pp off. refusal is pairwise-only and analysed "
                     f"separately, so starving a side of one family removes a whole "
                     f"analysis rather than a few items.")


def check_dry_run(split: dict) -> None:
    """SPLIT-10 -- the dry run must draw from train and nowhere else."""
    train = set(split["assignment"]["train"])
    leaked = sorted(set(split["dry_run"]["scenario_ids"]) - train)
    if leaked:
        fail("SPLIT-10",
             f"{len(leaked)} dry-run scenarios are not in train, e.g. {leaked[:5]}. "
             f"Phase 2 reads these items closely; anything it touches outside train "
             f"stops being held out.")


def check_marks(split: dict, collection) -> None:
    """SPLIT-11 -- recorded marks still match the collection."""
    actual = sorted(s["scenario_id"] for s in collection
                    if s.get("cross_family_confound"))
    stored = split["marks"]["cross_family_confound"]["scenario_ids"]
    if actual != stored:
        fail("SPLIT-11", f"cross_family_confound marks are stale: file lists "
                         f"{stored}, collection has {actual}")


def check_folds(split: dict, collection, derive) -> None:
    """SPLIT-12 -- fold membership must still match the collection."""
    ids = [s["scenario_id"] for s in collection]
    check_partition(split, ids, {f["fold"]: f["test"] for f in split["folds"]},
                    "folds")

    current = derive()
    stored = {sid: f["fold"] for f in split["folds"] for sid in f["test"]}
    drifted = sorted(k for k in stored if current.get(k) != stored[k])
    if drifted:
        fail("SPLIT-12",
             f"{split['split_id']}: {len(drifted)} scenarios have moved fold since "
             f"the split was frozen, e.g. "
             f"{[(k, stored[k], current.get(k)) for k in drifted[:3]]}")



def check_domain_names(collection) -> None:
    """SPLIT-12 -- no real domain may be called `other`, the name the pooled small ones share."""
    named = sorted(s["scenario_id"] for s in collection if s.get("domain") == "other")
    if named:
        fail("SPLIT-12",
             f"{len(named)} scenario(s) have the domain 'other', which is the fold the small "
             f"domains are pooled into, so they would join it without a word, e.g. {named[:3]}")


def check_source_inventory(split: dict) -> None:
    """SPLIT-13 -- the five sources still match the worked trials."""
    stored = [(s["source_id"], s["transport_role"], s["displayed_provenance"])
              for s in split["sources"]]
    actual = [(s.source_id, s.transport_role, s.displayed_provenance)
              for s in load_sources()]
    if stored != actual:
        fail("SPLIT-13",
             f"{split['split_id']}: the source inventory has drifted from the "
             f"composition trials. File: {stored}. Trials: {actual}.")


def check_pair_folds(split: dict) -> None:
    """SPLIT-14 -- every pair held out exactly once, and every fold identifiable.
    A fold whose training pairs leave the source graph disconnected is not a hard test but an
    unanswerable one: two components slide apart freely."""
    ids = [s["source_id"] for s in split["sources"]]
    want = {tuple(p) for p in itertools.combinations(ids, 2)}

    held = collections.Counter()
    for fold in split["folds"]:
        for pair in fold["test"]:
            held[tuple(pair)] += 1
    if set(held) != want or any(n != 1 for n in held.values()):
        fail("SPLIT-14",
             f"pairs held out {dict(held)}; every one of {len(want)} must be held "
             f"out exactly once")

    for fold in split["folds"]:
        train = {tuple(p) for p in fold["train"]}
        test = {tuple(p) for p in fold["test"]}
        if train | test != want or train & test:
            fail("SPLIT-14", f"fold {fold['fold']}: train and test do not "
                             f"partition the {len(want)} pairs")
        health = fold["identifiability"]
        if not health["connected"]:
            fail("SPLIT-14",
                 f"fold {fold['fold']}: the training pairs leave the source graph "
                 f"disconnected, so the scale is not identified and the held-out "
                 f"pair has no prediction to be wrong about")


def check_set_stages(split: dict) -> None:
    """SPLIT-15 -- nothing predicted was fitted, and the slice really covers.
    The second half is the one that matters: a pair covered by no triple is a correlation stage
    two cannot estimate, and the stage would look like it ran."""
    ids = [s["source_id"] for s in split["sources"]]
    all_pairs = {frozenset(p) for p in itertools.combinations(ids, 2)}

    for stage in split["stages"]:
        train = {tuple(s) for s in stage["train"]}
        test = {tuple(s) for group in stage["test_by_size"].values() for s in group}
        overlap = train & test
        if overlap:
            fail("SPLIT-15",
                 f"stage {stage['stage']}: {len(overlap)} sets are both fitted and "
                 f"predicted, e.g. {sorted(overlap)[:3]} -- that is not a held-out "
                 f"prediction")
        if any(len(s) != 2 for s in train) and stage["stage"] == "one":
            fail("SPLIT-15", "stage one must fit pairs only; it is the claim that "
                             "nothing above a pair was seen")

    slice_ = [tuple(t) for t in split["stage_two_slice"]["triples"]]
    covered: set = set()
    for triple in slice_:
        covered |= {frozenset(p) for p in itertools.combinations(triple, 2)}
    missing = all_pairs - covered
    if missing:
        fail("SPLIT-15",
             f"the stage-two slice leaves {len(missing)} source pairs in no triple "
             f"({[sorted(m) for m in missing]}). Three-way data is what identifies "
             f"a correlation, so those are unestimable and stage two is not "
             f"identified.")
    if tuple(STAGE_TWO_SLICE_ANCHOR) not in slice_:
        fail("SPLIT-15",
             f"the stage-two slice does not contain {list(STAGE_TWO_SLICE_ANCHOR)}, "
             f"which comp-07 declares to be in it")
    fresh = covering_slice(load_sources(), must_include=[STAGE_TWO_SLICE_ANCHOR])
    if slice_ != fresh:
        fail("SPLIT-15", f"the recorded slice {slice_} is not what the rule "
                         f"produces now ({fresh}); re-freeze on purpose")


def check_free_predictions(split: dict) -> None:
    """SPLIT-16 -- free predictions are never fitted, and the worked ones are there."""
    free = split["free_predictions"]["compositions"]
    fitted = {tuple(s) for stage in split["stages"] for s in stage["train"]}

    for entry in free:
        groups = [tuple(g) for g in entry["groups"]]
        if len(groups) != 2 or not all(groups):
            fail("SPLIT-16", f"{entry['sources']}: a free prediction is two action "
                             f"groups, got {groups}")
        flat = sorted(x for g in groups for x in g)
        if flat != sorted(entry["sources"]) or len(set(flat)) != len(flat):
            fail("SPLIT-16", f"{entry['sources']}: groups do not partition the "
                             f"sources")
        if tuple(entry["sources"]) in fitted and len(entry["sources"]) == 2:
            fail("SPLIT-16", f"{entry['sources']} is fitted elsewhere")

    shapes = {(tuple(e["sources"]), tuple(tuple(g) for g in e["groups"]))
              for e in free}
    for sources, groups, name in (
        (("S1", "S3", "S5"), (("S1",), ("S3", "S5")), "comp-09"),
        (("S1", "S2", "S3", "S5"), (("S1",), ("S2", "S3", "S5")), "comp-10"),
    ):
        if (sources, groups) not in shapes:
            fail("SPLIT-16",
                 f"{name}'s composition {list(sources)} split "
                 f"{[list(g) for g in groups]} is missing from the enumeration, so "
                 f"a worked trial has no entry in the split it belongs to")


# ------------------------------------------------------------------ exclusion


def report_exclusion(item: dict, collection, drop: Sequence[str]) -> None:
    """What a proposed exclusion does to the frozen splits.

    Not a pass/fail on the split as frozen -- it is a question about a change
    somebody is considering."""
    family = {s["scenario_id"]: s["family"] for s in collection}
    known = set(family)
    unknown = sorted(set(drop) - known)
    drop = sorted(set(drop) & known)

    print(f"\n--- proposed exclusion: {len(drop)} scenarios ---")
    if unknown:
        print(f"  ignored, not in the collection: {unknown[:5]}"
              f"{' …' if len(unknown) > 5 else ''}")
    if not drop:
        print("  nothing to do")
        return

    sides = item["assignment"]
    total_before = sum(len(v) for v in sides.values())
    total_after = total_before - len(drop)
    dropped_side = collections.Counter()
    for side, ids in sides.items():
        dropped_side[side] = len(set(ids) & set(drop))

    print(f"  {'side':7}{'before':>8}{'after':>8}{'share':>9}{'target':>9}{'drift':>9}")
    worst = 0.0
    for side, target in sorted(PROPORTIONS.items()):
        before = len(sides[side])
        after = before - dropped_side[side]
        share = after / total_after if total_after else 0.0
        drift = (share - target) * 100
        worst = max(worst, abs(drift))
        print(f"  {side:7}{before:>8}{after:>8}{share:>8.1%}{target:>9.0%}"
              f"{drift:>+8.2f}pp")

    by_family: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter)
    for side, ids in sides.items():
        for sid in set(ids) & set(drop):
            by_family[family[sid]][side] += 1
    if by_family:
        print("  removed by family: " + ", ".join(
            f"{fam} ({', '.join(f'{s} {n}' for s, n in sorted(c.items()))})"
            for fam, c in sorted(by_family.items())))

    if worst > OVERALL_TOLERANCE_PP:
        print(f"\n  WARNING: worst drift {worst:.2f} pp exceeds the "
              f"{OVERALL_TOLERANCE_PP} pp tolerance. Applying this exclusion "
              f"changes what the held-out set measures. Either drop a matched "
              f"number from the other sides, or re-freeze the split and record it.")
    else:
        print(f"\n  worst drift {worst:.2f} pp — within the "
              f"{OVERALL_TOLERANCE_PP} pp tolerance; the splits survive this "
              f"exclusion.")


# ---------------------------------------------------------------------- main


def run(drop: Sequence[str] = ()) -> int:
    # Cleared per run: module-level so every check can reach them, so a second call in one process would inherit the first's verdict.
    fails.clear()
    notes.clear()

    collection = load_collection()
    current_fp = fingerprints(collection)
    ids = [s["scenario_id"] for s in collection]

    item = _load("item")
    axis = _load("axis")
    domain = _load("domain")
    source_pair = _load("source_pair")
    sets = _load("set")

    if item:
        check_fingerprint(item, current_fp)
        check_partition(item, ids, item["assignment"], "assignment")
        check_groups_whole(item)
        check_grouping_reproduces(item, collection)
        check_grouping_is_real(item)
        check_proportions(item, collection)
        check_dry_run(item)
        check_marks(item, collection)

    if axis:
        check_fingerprint(axis, current_fp)
        check_folds(axis, collection, lambda: axis_of(collection))

    if domain:
        check_fingerprint(domain, current_fp)
        check_domain_names(collection)
        big = {f["fold"] for f in domain["folds"]} - {"other"}
        check_folds(domain, collection,
                    lambda: {s["scenario_id"]:
                             (s["domain"] if s["domain"] in big else "other")
                             for s in collection})

    if source_pair:
        check_fingerprint(source_pair, current_fp)
        check_source_inventory(source_pair)
        check_pair_folds(source_pair)

    if sets:
        check_fingerprint(sets, current_fp)
        check_source_inventory(sets)
        check_set_stages(sets)
        check_free_predictions(sets)

    print(f"{len(ids)} scenarios | {len(fails)} FAIL | {len(notes)} note")
    for m in fails:
        print("  FAIL " + m)
    for m in notes:
        print("  note " + m)

    if item and drop:
        report_exclusion(item, collection, drop)

    return 1 if fails else 0


def main() -> None:
    from ..logs import add_arguments, from_arguments, get_logger

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exclude", nargs="*", default=[], metavar="ID",
                    help="scenario ids a proposed exclusion would remove; "
                         "prints the balance that would be left")
    ap.add_argument("--exclude-file", metavar="PATH",
                    help="file of scenario ids, one per line, added to --exclude")
    add_arguments(ap, progress=False)
    args = ap.parse_args()
    from_arguments("splits-check", args)
    log = get_logger(__name__)

    drop = list(args.exclude)
    if args.exclude_file:
        with open(args.exclude_file, encoding="utf-8") as fh:
            drop += [ln.strip() for ln in fh if ln.strip()]
    if drop:
        log.info("checking the frozen lists with %d scenario(s) excluded", len(drop))

    status = run(drop)
    (log.error if status else log.info)(
        "split check %s", "FAILED" if status else "passed")
    sys.exit(status)


if __name__ == "__main__":
    main()
