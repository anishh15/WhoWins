"""Build the frozen split lists. WRITES ONLY to data/splits/.
Run once and committed. Rebuilding to suit a result is the failure this whole directory
exists to prevent, so every file records the fingerprint of the collection it was built
from and `check.py` refuses a mismatch."""

from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import os
import random
from typing import Sequence

from ..data import ROOT
from .axes import WEAK_AXES, axis_level, axis_of
from .sources import (
    COMPOSITION_TRIALS,
    DECLARED_LADDER,
    Source,
    covering_slice,
    load_sources,
    subsets,
    two_action_partitions,
)
from .grouping import (
    FRAME_MIN_SHARE,
    SHARED_SUFFIX_MIN,
    SHARED_VALUES_MIN,
    TASK_TAU,
    build_groups,
    load_collection,
    singleton_share,
)

OUT_DIR = os.path.join(ROOT, "data", "splits")

SEED = 20260909
"""Fixed and published. The split is a commitment, so the seed is part of it."""

PROPORTIONS = {"train": 0.60, "val": 0.15, "test": 0.25}
"""Held back: 25%, so the benchmark survives being fitted against. Validation:
15%, enough to choose among roughly six model classes without touching test.
These are pre-registration decisions, not tuning knobs -- change them here and
re-freeze deliberately, and record why."""

DOMAIN_FOLD_MIN = 50
"""A subject area gets its own fold at this many scenarios or more. Below it the
fold would be too small to say anything, so the tail is pooled into `other`."""

STAGE_TWO_SLICE_ANCHOR = ("S1", "S2", "S4")
"""The triple comp-07 already declares to be in the stage-two fit slice.

All ten minimum covering slices are isomorphic -- nine pairs once, one pair three
times -- so nothing in the data chooses between them. This anchor is the only
non-arbitrary constraint available: a worked trial written by hand says this
triple is in the slice, so the slice contains it.
"""

DRY_RUN_N = 100
"""Target size, the top of the planned 50-100 range.
Per-family rounding can land a scenario or two short of it; the achieved count is
recorded in the file. Drawn from `train` only, so the dry run can never inform
what val or test measure."""


# ------------------------------------------------------------- fingerprints


def _content_fields(s: dict) -> tuple:
    """The parts of a scenario that decide where it lands.
    Task wording drives the grouping, family and domain drive the folds, and the checker
    strings identify the item. Prose fields are deliberately absent."""
    return (
        s["scenario_id"], s["family"], s["domain"], s["difficulty"],
        s["task"], s["checker_key"],
        tuple(o["checker"] for o in s["options"]),
    )


def fingerprints(collection: Sequence[dict]) -> dict[str, str]:
    """Two hashes, because two kinds of edit deserve two responses.
    `content` covers what the split was computed from: if it moves, the split is invalid and
    `check.py` fails. `full` covers everything else, where an edit is recorded but harmless."""
    def h(items):
        return "sha256:" + hashlib.sha256(
            json.dumps(items, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    content = sorted(_content_fields(s) for s in collection)
    full = sorted(
        ({k: v for k, v in s.items() if not k.startswith("_")} for s in collection),
        key=lambda s: s["scenario_id"],
    )
    return {"content": h(content), "full": h(full), "n_scenarios": len(collection)}


# ---------------------------------------------------------------- assignment


def assign_groups(
    groups: dict[str, list[str]],
    family_of: dict[str, str],
    proportions: dict[str, float],
    seed: int,
) -> dict[str, str]:
    """Whole groups to sides, balanced inside every family.
    Every group sits in one family -- all three link rules are within-family -- so assigning
    family by family gives per-family balance for free."""
    by_family: dict[str, list[str]] = collections.defaultdict(list)
    for gid, ids in groups.items():
        by_family[family_of[ids[0]]].append(gid)

    rng = random.Random(seed)
    assignment = {}

    for family in sorted(by_family):
        gids = sorted(by_family[family])
        rng.shuffle(gids)
        gids.sort(key=lambda g: -len(groups[g]))

        total = sum(len(groups[g]) for g in gids)
        quota = {side: p * total for side, p in proportions.items()}
        placed = {side: 0 for side in proportions}

        for gid in gids:
            side = max(sorted(placed), key=lambda x: quota[x] - placed[x])
            assignment[gid] = side
            placed[side] += len(groups[gid])

    return assignment


def _balance(collection, ids_by_side, field):
    """Achieved share of `field`'s values on each side, for the record.
    Reported rather than enforced: forcing domain balance on top of family balance would
    over-constrain a greedy assignment over 1,038 groups."""
    by_id = {s["scenario_id"]: s for s in collection}
    out = {}
    for side, ids in ids_by_side.items():
        counts = collections.Counter(by_id[i][field] for i in ids)
        out[side] = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    return out


# -------------------------------------------------------------------- builds


def build_item_split(collection, groups, links) -> dict:
    family_of = {s["scenario_id"]: s["family"] for s in collection}
    assignment = assign_groups(groups, family_of, PROPORTIONS, SEED)

    sides: dict[str, list[str]] = {side: [] for side in PROPORTIONS}
    for gid, side in assignment.items():
        sides[side].extend(groups[gid])
    sides = {side: sorted(ids) for side, ids in sides.items()}

    # The dry run draws from train, stratified by family, so phase 2 cannot inform what val or test measure.
    rng = random.Random(SEED + 1)
    train_by_family: dict[str, list[str]] = collections.defaultdict(list)
    for sid in sides["train"]:
        train_by_family[family_of[sid]].append(sid)
    n_total = len(collection)
    dry_run: list[str] = []
    for family in sorted(train_by_family):
        want = round(DRY_RUN_N * sum(1 for s in collection if s["family"] == family) / n_total)
        pool = sorted(train_by_family[family])
        rng.shuffle(pool)
        dry_run.extend(sorted(pool[:want]))

    confounded = sorted(
        s["scenario_id"] for s in collection if s.get("cross_family_confound")
    )

    return {
        "split_id": "item",
        "schema_version": 1,
        "question": "Does a scale fitted on these base scenarios hold on scenarios "
                    "it never saw?",
        "unit": "base scenario",
        "shape": "train / val / test",
        "grouping": {
            "why": "seed_family is unique on all 1080 scenarios, so grouping by it "
                   "would group nothing. Groups are built from three measured link "
                   "rules; see whowins/splits/grouping.py.",
            "n_groups": len(groups),
            "largest_group": max(len(v) for v in groups.values()),
            "singleton_share": round(singleton_share(groups), 4),
            "links_by_rule": dict(
                sorted(collections.Counter(l["rule"] for l in links).items())
            ),
            "links": links,
        },
        "counts": {side: len(ids) for side, ids in sorted(sides.items())},
        "target_proportions": PROPORTIONS,
        "achieved_proportions": {
            side: round(len(ids) / len(collection), 4)
            for side, ids in sorted(sides.items())
        },
        "balance": {
            "family": _balance(collection, sides, "family"),
            "difficulty": _balance(collection, sides, "difficulty"),
            "domain": _balance(collection, sides, "domain"),
        },
        "dry_run": {
            "note": "Drawn from train only, stratified by family. Regenerable: "
                    "this is a proposal, not a commitment, and phase 2 may pick a "
                    "different size or over-sample format for checker coverage.",
            "n": len(dry_run),
            "scenario_ids": sorted(dry_run),
        },
        "marks": {
            "cross_family_confound": {
                "note": "Excluded from the pure path estimate by their own notes, "
                        "not from the split. Listed so an analysis cannot forget "
                        "them.",
                "scenario_ids": confounded,
            },
        },
        "groups": groups,
        "assignment": {side: ids for side, ids in sorted(sides.items())},
    }


def _pair_graph_health(sources, train_pairs) -> dict:
    """Can the source positions still be identified from these pairs?
    A scale over sources is identified only where the pair graph is connected: two components
    can be slid apart without changing any within-component comparison."""
    ids = [s.source_id for s in sources]
    degree = {i: 0 for i in ids}
    adjacency = {i: set() for i in ids}
    for a, b in train_pairs:
        degree[a] += 1
        degree[b] += 1
        adjacency[a].add(b)
        adjacency[b].add(a)

    seen, stack = set(), [ids[0]]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adjacency[node] - seen)

    return {
        "connected": len(seen) == len(ids),
        "min_degree": min(degree.values()),
        "degrees": {i: degree[i] for i in ids},
    }


def build_source_pair_split(sources: list[Source]) -> dict:
    """Leave one whole source pair out at a time.
    Holding out TRIALS while every pair appears in training tests repeated observation of known
    pairs -- not the claim the scale makes, which is about a pair it has never seen."""
    pairs = subsets(sources, 2)
    folds = []
    for held in pairs:
        train = [p for p in pairs if p != held]
        folds.append({
            "fold": "|".join(held),
            "test": [list(held)],
            "n_train_pairs": len(train),
            "identifiability": _pair_graph_health(sources, train),
            "train": [list(p) for p in train],
        })
    return {
        "split_id": "source_pair",
        "schema_version": 1,
        "question": "Does the fitted scale predict a source pair it never saw?",
        "unit": "source pair",
        "shape": f"leave-one-pair-out, {len(folds)} folds",
        "why_whole_pairs":
            "A saturated per-pair model has a parameter for each pair and cannot "
            "predict one it never saw. Holding out trials instead would compare "
            "the two models on repeated observations of known pairs, which is not "
            "the claim being tested.",
        "sources": [s.as_dict() for s in sources],
        "n_pairs": len(pairs),
        "n_folds": len(folds),
        "folds": folds,
    }


def build_set_split(sources: list[Source]) -> dict:
    """The composition ladder, and the headline.
    Stage one fits pairs only and predicts every untouched larger set, refitting nothing. Stage
    two adds a preselected slice of triples, because pairwise data cannot identify a correlated
    model and three-way data can."""
    pairs = subsets(sources, 2)
    triples = subsets(sources, 3)
    fours = subsets(sources, 4)
    fives = subsets(sources, 5)

    slice_ = covering_slice(sources, must_include=[STAGE_TWO_SLICE_ANCHOR])
    remaining = [t for t in triples if t not in slice_]

    def by_size(sets_):
        out: dict[str, list] = {}
        for s in sets_:
            out.setdefault(str(len(s)), []).append(list(s))
        return out

    stage_one_test = triples + fives
    stage_two_test = remaining + fives

    free = []
    for size in (3, 4, 5):
        for subset in subsets(sources, size):
            for groups in two_action_partitions(subset):
                free.append({
                    "sources": list(subset),
                    "groups": [list(g) for g in groups],
                    "group_sizes": sorted((len(g) for g in groups), reverse=True),
                    "n_sources": len(subset),
                    "n_distinct_actions": 2,
                })

    return {
        "split_id": "set",
        "schema_version": 1,
        "question": "Do pairwise measurements predict what happens when three or "
                    "five sources compete?",
        "unit": "composition — which sources compete, and what each demands",
        "shape": "two stages; every set above pairs is predicted, never fitted, "
                 "except the preselected triple slice in stage two",
        "sources": [s.as_dict() for s in sources],
        "declared_ladder": list(DECLARED_LADDER),
        "stages": [
            {
                "stage": "one",
                "carries": "the high-risk headline: pairs only, nothing refitted",
                "train": [list(p) for p in pairs],
                "n_train": len(pairs),
                "test_by_size": by_size(stage_one_test),
                "n_test": len(stage_one_test),
            },
            {
                "stage": "two",
                "carries": "the robust headline: identified, because three-way "
                           "data is what pins the correlation",
                "train": [list(s) for s in pairs + slice_],
                "n_train": len(pairs) + len(slice_),
                "test_by_size": by_size(stage_two_test),
                "n_test": len(stage_two_test),
            },
        ],
        "stage_two_slice": {
            "triples": [list(t) for t in slice_],
            "anchor": list(STAGE_TWO_SLICE_ANCHOR),
            "why_these":
                "The fewest triples covering every source pair at least once: a "
                "pair in no triple is a correlation stage two cannot estimate. "
                "All ten minimum slices are isomorphic (nine pairs once, one pair "
                "three times), so the choice carries no information; it contains "
                "the triple comp-07 declares and is otherwise first in sorted "
                "order. Not chosen by expected closeness — #16 records that "
                "adjacent pairs are unknown before fitting.",
        },
        "comparable_triples": {
            "note": "Predicted out of sample by BOTH stages, so stage one and "
                    "stage two can be compared like for like. The other four are "
                    "stage-two training.",
            "sets": [list(t) for t in remaining],
        },
        "not_in_declared_ladder": {
            "note": "Four-way bijective sets. dataset-plan.md declares n = 2, 3, 5, "
                    "so these are enumerated but not committed to; adding them is "
                    "a scope decision, and they would be extra out-of-sample points "
                    "for both stages.",
            "sets": [list(f) for f in fours],
        },
        "free_predictions": {
            "note": "Several sources demanding the SAME action. An independent-draw "
                    "account and a consensus account predict different things here, "
                    "and the pair-only fit commits to one in advance with no new "
                    "parameters. Never fitted on. Groups are not labelled repetition "
                    "or agreement because which is which depends on the fitted "
                    "ordering, unknown in advance (#16). comp-09 is the {S1}|{S3,S5} "
                    "entry and comp-10 the {S1}|{S2,S3,S5} entry.",
            "n": len(free),
            "compositions": free,
        },
    }


def build_axis_split(collection) -> dict:
    axis = axis_of(collection)
    members: dict[str, list[str]] = collections.defaultdict(list)
    for sid, ax in axis.items():
        members[ax].append(sid)

    folds = [
        {
            "fold": ax,
            "level": axis_level(ax),
            "n_test": len(ids),
            "n_train": len(collection) - len(ids),
            "test": sorted(ids),
        }
        for ax, ids in sorted(members.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    ]

    return {
        "split_id": "axis",
        "schema_version": 1,
        "question": "Does the scale transfer from one kind of constraint to another?",
        "unit": "constraint kind",
        "shape": "leave-one-out folds; train is everything not in `test`",
        "how_axes_were_derived":
            "Format scenarios take their classifier module, which fmt/__init__.py "
            "describes as the axis it reads; the four trace families have one "
            "checker key each, so the family is the axis. checker_key cannot be "
            "used -- it is unique across all 240 format scenarios.",
        "caveat":
            "The `structural` fold is grouped by needing a parser rather than by "
            "subject, and holds 29% of the format family. Report it separately; if "
            "it behaves unlike the other eight, hand-label its 70 keys.",
        "weak_folds": sorted(WEAK_AXES),
        "n_folds": len(folds),
        "folds": folds,
    }


def build_domain_split(collection) -> dict:
    counts = collections.Counter(s["domain"] for s in collection)
    if "other" in counts:
        raise ValueError("a domain is named 'other', which is the fold the small domains are "
                         "pooled into; rename it")
    big = {d for d, n in counts.items() if n >= DOMAIN_FOLD_MIN}
    pooled = sorted(d for d in counts if d not in big)

    members: dict[str, list[str]] = collections.defaultdict(list)
    for s in collection:
        key = s["domain"] if s["domain"] in big else "other"
        members[key].append(s["scenario_id"])

    folds = []
    family_of = {s["scenario_id"]: s["family"] for s in collection}
    for name, ids in sorted(members.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        by_family = collections.Counter(family_of[i] for i in ids)
        folds.append({
            "fold": name,
            "n_test": len(ids),
            "n_train": len(collection) - len(ids),
            "families_held_out": dict(sorted(by_family.items())),
            "pooled_domains": pooled if name == "other" else [],
            "test": sorted(ids),
        })

    return {
        "split_id": "domain",
        "schema_version": 1,
        "question": "Does the scale transfer from one subject area to another?",
        "unit": "domain",
        "shape": "leave-one-out folds; train is everything not in `test`",
        "fold_minimum": DOMAIN_FOLD_MIN,
        "caveat":
            "The folds are lopsided by design, because the collection is. Five "
            "domains carry 84% of it, and a held-out domain does not hold out every "
            "family evenly -- `web` contains no path scenarios at all. Per-fold "
            "family coverage is recorded on each fold and must be read with it, "
            "never averaged into one transfer number.",
        "n_folds": len(folds),
        "folds": folds,
    }


# ---------------------------------------------------------------------- main


def build_all() -> dict[str, dict]:
    collection = load_collection()
    groups, links = build_groups(collection)
    fp = fingerprints(collection)

    sources = load_sources()
    built = {
        "item": build_item_split(collection, groups, links),
        "axis": build_axis_split(collection),
        "domain": build_domain_split(collection),
        "source_pair": build_source_pair_split(sources),
        "set": build_set_split(sources),
    }

    stamp = {
        "built_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
        "builder": "whowins.splits.build",
        "seed": SEED,
        "collection_fingerprint": fp,
        "parameters": {
            "frame_min_share": FRAME_MIN_SHARE,
            "task_tau": TASK_TAU,
            "shared_values_min": SHARED_VALUES_MIN,
            "shared_suffix_min": SHARED_SUFFIX_MIN,
            "proportions": PROPORTIONS,
            "domain_fold_min": DOMAIN_FOLD_MIN,
            "dry_run_n": DRY_RUN_N,
            "stage_two_slice_anchor": list(STAGE_TWO_SLICE_ANCHOR),
            "source_inventory_from": COMPOSITION_TRIALS,
        },
    }
    for split in built.values():
        split.update(stamp)
    return built


def summarise(built: dict[str, dict]) -> None:
    item = built["item"]
    print("item     " + "  ".join(
        f"{side} {n}" for side, n in item["counts"].items()))
    print(f"         {item['grouping']['n_groups']} groups, largest "
          f"{item['grouping']['largest_group']}, "
          f"{item['grouping']['singleton_share']:.1%} singletons, "
          f"links {item['grouping']['links_by_rule']}")
    print(f"         dry run {item['dry_run']['n']} from train")
    for name in ("axis", "domain"):
        s = built[name]
        sizes = ", ".join(f"{f['fold']} {f['n_test']}" for f in s["folds"][:6])
        print(f"{name:9}{s['n_folds']} folds — {sizes}"
              + (", …" if len(s["folds"]) > 6 else ""))
    sp = built["source_pair"]
    print(f"src pair {sp['n_folds']} folds over {sp['n_pairs']} pairs of "
          f"{len(sp['sources'])} sources; every fold connected: "
          f"{all(f['identifiability']['connected'] for f in sp['folds'])}")
    st = built["set"]
    for stage in st["stages"]:
        sizes = ", ".join(f"n={k}:{len(v)}" for k, v in sorted(stage["test_by_size"].items()))
        print(f"set      stage {stage['stage']}: fit {stage['n_train']}, predict "
              f"{stage['n_test']} ({sizes})")
    print(f"         slice {[''.join(t).replace('S','') for t in st['stage_two_slice']['triples']]}"
          f"; free predictions {st['free_predictions']['n']}")


def main() -> None:
    from ..logs import add_arguments, from_arguments, get_logger

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the summary and write nothing. A split list is a "
                         "pre-registration commitment, so the default writes over "
                         "five frozen files -- read the summary first")
    add_arguments(ap, progress=False)
    args = ap.parse_args()
    from_arguments("splits-build", args)
    log = get_logger(__name__)

    built = build_all()
    summarise(built)

    if args.dry_run:
        log.info("--dry-run: nothing written")
        print("\n--dry-run: nothing written")
        return

    log.warning("rewriting the five frozen split lists in %s; if data collection "
                "has begun this moves the goalposts and belongs in changes.md",
                OUT_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, split in built.items():
        path = os.path.join(OUT_DIR, f"{name}.json")
        with open(path, "w") as fh:
            json.dump(split, fh, indent=2, sort_keys=False)
            fh.write("\n")
        print(f"wrote {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()
