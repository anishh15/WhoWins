"""The split-list suite.
Structured around the one property that matters: a grouped split must actually group. A
grouping of all singletons has grouped nothing and would leak near-duplicates across the
boundary while looking correct."""

from __future__ import annotations

import collections
import copy
import itertools
import json
import random

import pytest

from whowins.splits import check as splitcheck
from whowins.splits.axes import (
    FORMAT_MODULES,
    TRACE_FAMILIES,
    AxisResolutionError,
    axis_level,
    axis_of,
    format_key_modules,
)
from whowins.splits.build import (DOMAIN_FOLD_MIN, OUT_DIR, PROPORTIONS, build_all,
                              build_domain_split, fingerprints)
from whowins.splits.sources import load_sources
from whowins.splits.grouping import (
    SHARED_VALUES_MIN,
    build_groups,
    content_words,
    family_frames,
    link_reason,
    load_collection,
    singleton_share,
)

COLLECTION = load_collection()
GROUPS, LINKS = build_groups(COLLECTION)


def _disk(name: str) -> dict:
    with open(f"{OUT_DIR}/{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


# --- The premise: the plan's grouping key does not group ---


def test_the_fields_the_plan_says_to_group_by_are_unique():
    """The plan says to keep variants of one seed scenario together. There are none.
    This collection was hand-written under a rule against scripted variants, so following the
    plan literally would group nothing."""
    seeds = [s["seed_family"] for s in COLLECTION]
    assert len(set(seeds)) == len(seeds) == 1080, (
        "seed_family is no longer unique; the grouping design assumed it was"
    )

    fmt_keys = [s["checker_key"] for s in COLLECTION if s["family"] == "format"]
    assert len(set(fmt_keys)) == len(fmt_keys) == 240, (
        "format checker_key is no longer unique; same assumption"
    )


def test_grouping_by_seed_family_would_group_nothing():
    """The trap, made concrete. Not a hypothetical: this is what an
    implementation that followed the plan literally would produce."""
    naive = {"g-" + s["seed_family"]: [s["scenario_id"]] for s in COLLECTION}
    assert len(naive) == len(COLLECTION)
    assert singleton_share(naive) == 1.0

    assert singleton_share(GROUPS) < 1.0, "the real grouping must group something"
    assert len(GROUPS) < len(COLLECTION)


# --- The link rules ---


def test_every_link_rule_can_fire():
    """A rule that cannot fire is a guard reporting a false negative forever.
    Two of the three fire on the collection as it stands; the third is checked against
    constructed input so it is known to work when it is needed."""
    fired = collections.Counter(l["rule"] for l in LINKS)
    assert fired["task"] > 0, "the task rule fires on the real collection"
    assert fired["suffix"] > 0, "the suffix rule fires on the real collection"
    assert fired["values"] == 0, (
        "the values rule now fires on the collection -- that is not a failure, but "
        "grouping.py's docstring says it fires zero times and must be updated"
    )

    frames = family_frames(COLLECTION)
    a = {"family": "tool", "checker_key": "first_tool_call",
         "task": "Alpha bravo charlie delta echo.",
         "options": [{"checker": f"first_tool_call==t{i}"} for i in range(5)]}
    b = {"family": "tool", "checker_key": "first_tool_call",
         "task": "Foxtrot golf hotel india juliet.",
         "options": [{"checker": f"first_tool_call==t{i}"} for i in (0, 1, 2, 7, 8)]}
    assert len({f"t{i}" for i in range(5)} & {f"t{i}" for i in (0, 1, 2, 7, 8)}) \
        == SHARED_VALUES_MIN
    assert link_reason(a, b, frames) == "values"


def test_link_rules_are_symmetric():
    """Order must not decide whether two scenarios are joined."""
    frames = family_frames(COLLECTION)
    rng = random.Random(11)
    for _ in range(400):
        a, b = rng.sample(COLLECTION, 2)
        assert link_reason(a, b, frames) == link_reason(b, a, frames)


def test_frame_stripping_is_load_bearing():
    """Without it the grouping collapses, which is why it exists.
    The path family's tasks share a sentence frame by design, so raw task similarity would put
    the whole family in one group."""
    frames = family_frames(COLLECTION)
    assert frames["path"], "the path family must have a detected frame"

    def jac(x, y):
        u = x | y
        return len(x & y) / len(u) if u else 0.0

    def largest_component(words_of):
        """Transitive closure is what makes this bite: individually reasonable
        links chain until a seventh of the collection is one indivisible block."""
        path = [s for s in COLLECTION if s["family"] == "path"]
        parent = list(range(len(path)))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for i, a in enumerate(path):
            for j in range(i + 1, len(path)):
                if jac(words_of(a), words_of(path[j])) >= 0.5:
                    ra, rb = find(i), find(j)
                    if ra != rb:
                        parent[ra] = rb
        return max(collections.Counter(find(i) for i in range(len(path))).values())

    raw = largest_component(lambda s: set(s["task"].lower().split()))
    stripped = largest_component(lambda s: content_words(s, frames))

    assert raw >= 50, (
        f"raw task similarity should chain the path family into one large block "
        f"(measured 86 when this was written, got {raw})"
    )
    assert stripped <= 20, (
        f"frame-stripped similarity should leave groups small enough to balance "
        f"(got {stripped})"
    )


# --- Groups ---


def test_groups_partition_the_collection():
    seen = [sid for ids in GROUPS.values() for sid in ids]
    assert sorted(seen) == sorted(s["scenario_id"] for s in COLLECTION)
    assert len(seen) == len(set(seen))


def test_no_group_spans_two_families():
    """All three link rules are within-family, so this must hold. It is what lets
    the assignment balance each family independently."""
    family = {s["scenario_id"]: s["family"] for s in COLLECTION}
    for gid, ids in GROUPS.items():
        assert len({family[i] for i in ids}) == 1, f"{gid} spans families"


def test_grouping_does_not_depend_on_file_order():
    """Group names come from the lowest member, so a shuffled collection must
    produce the identical grouping. Otherwise the frozen split would depend on
    the order scenarios happen to sit in their batch files."""
    shuffled = copy.deepcopy(COLLECTION)
    random.Random(5).shuffle(shuffled)
    again, _ = build_groups(shuffled)
    assert again == GROUPS


# --- Axes ---


def test_every_format_key_resolves_to_exactly_one_module():
    """Pins the source search in axes.py. If a key stops resolving, scenarios
    would silently land in the wrong fold, so this must fail rather than the
    fold quietly changing."""
    modules = format_key_modules()
    assert len(modules) == 240
    assert set(modules.values()) <= set(FORMAT_MODULES)


def test_axes_cover_the_collection_at_two_levels():
    axis = axis_of(COLLECTION)
    assert len(axis) == len(COLLECTION)
    counts = collections.Counter(axis.values())
    assert len(counts) == len(FORMAT_MODULES) + len(TRACE_FAMILIES) == 13
    for family in TRACE_FAMILIES:
        assert axis_level(family) == "family"
    for module in FORMAT_MODULES:
        assert axis_level(module) == "format-module"


# --- The built files ---


def test_the_files_on_disk_are_current_and_valid():
    """The whole checker, against what is actually committed."""
    assert splitcheck.run() == 0, splitcheck.fails


def test_build_is_deterministic():
    """A frozen artifact that changes when rebuilt was never frozen."""
    a, b = build_all(), build_all()
    assert a["item"]["assignment"] == b["item"]["assignment"]
    assert a["item"]["dry_run"] == b["item"]["dry_run"]
    assert a["axis"]["folds"] == b["axis"]["folds"]


def test_disk_matches_a_fresh_build():
    """Catches a file edited by hand, and a build never re-run after a change."""
    fresh = build_all()
    for name in ("item", "axis", "domain"):
        on_disk = _disk(name)
        for field in ("assignment", "folds", "groups"):
            if field in on_disk:
                assert on_disk[field] == fresh[name][field], f"{name}.{field} is stale"


def test_proportions_hold_within_every_family():
    """refusal is pairwise-only and analysed separately, so a side starved of it
    loses a whole analysis rather than a few items."""
    item = _disk("item")
    family = {s["scenario_id"]: s["family"] for s in COLLECTION}
    per: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for side, ids in item["assignment"].items():
        for sid in ids:
            per[family[sid]][side] += 1
    for fam, counts in per.items():
        n = sum(counts.values())
        for side, target in PROPORTIONS.items():
            assert abs(counts[side] / n - target) * 100 <= splitcheck.FAMILY_TOLERANCE_PP, \
                f"{fam}/{side} is off target"


def test_dry_run_comes_only_from_train():
    item = _disk("item")
    assert set(item["dry_run"]["scenario_ids"]) <= set(item["assignment"]["train"])
    assert 50 <= item["dry_run"]["n"] <= 100, "phase 2 specifies 50-100 scenarios"


def test_fingerprints_separate_content_from_prose():
    """An edited exclusivity argument must not invalidate a frozen split; an
    edited task must."""
    base = fingerprints(COLLECTION)

    prose = copy.deepcopy(COLLECTION)
    prose[0]["exclusivity"] += " One more sentence."
    changed = fingerprints(prose)
    assert changed["content"] == base["content"]
    assert changed["full"] != base["full"]

    real = copy.deepcopy(COLLECTION)
    real[0]["task"] = "Something else entirely."
    assert fingerprints(real)["content"] != base["content"]


# --- Planted faults -- prove the checker fails on known-bad splits ---


@pytest.fixture
def broken(tmp_path, monkeypatch):
    """Give the checker a scratch copy of data/splits it may be handed damage in."""
    import shutil
    dest = tmp_path / "splits"
    shutil.copytree(OUT_DIR, dest)
    monkeypatch.setattr(splitcheck, "OUT_DIR", str(dest))

    def edit(name, mutate):
        path = dest / f"{name}.json"
        doc = json.loads(path.read_text())
        mutate(doc)
        path.write_text(json.dumps(doc, indent=2))
        splitcheck.run()
        return [f.split(":")[0] for f in splitcheck.fails]

    return edit


def test_planted_fault_seed_family_grouping_is_caught(broken):
    """THE one. Replace the grouping with what the plan literally describes and
    the checker must refuse it by name."""
    def mutate(doc):
        ids = sorted(sum(doc["assignment"].values(), []))
        doc["groups"] = {"g-" + i: [i] for i in ids}

    codes = broken("item", mutate)
    assert "SPLIT-7" in codes, f"the seed_family trap was not caught: {codes}"


def test_planted_fault_group_split_across_sides_is_caught(broken):
    def mutate(doc):
        gid, members = max(doc["groups"].items(), key=lambda kv: len(kv[1]))
        assert len(members) > 1
        move = members[0]
        for side in doc["assignment"]:
            if move in doc["assignment"][side]:
                doc["assignment"][side].remove(move)
                other = next(s for s in doc["assignment"] if s != side)
                doc["assignment"][other].append(move)
                return
    assert "SPLIT-5" in broken("item", mutate)


def test_planted_fault_missing_scenario_is_caught(broken):
    assert "SPLIT-4" in broken("item", lambda d: d["assignment"]["test"].pop())


def test_planted_fault_unbalanced_family_is_caught(broken):
    def mutate(doc):
        ref = [i for i in doc["assignment"]["test"] if i.startswith("ref-")]
        doc["assignment"]["test"] = [
            i for i in doc["assignment"]["test"] if not i.startswith("ref-")
        ]
        doc["assignment"]["train"] += ref
    assert "SPLIT-9" in broken("item", mutate)


def test_planted_fault_dry_run_leak_is_caught(broken):
    def mutate(doc):
        doc["dry_run"]["scenario_ids"].append(doc["assignment"]["test"][0])
    assert "SPLIT-10" in broken("item", mutate)


def test_planted_fault_fold_drift_is_caught(broken):
    def mutate(doc):
        doc["folds"][1]["test"].append(doc["folds"][0]["test"].pop())
    assert "SPLIT-12" in broken("domain", mutate)


def test_a_domain_named_other_is_not_pooled_without_a_word(monkeypatch):
    """`other` is the fold the small domains share. A real domain of that name, big or small,
    would have joined it, and neither the build nor the check would have said so."""
    renamed = copy.deepcopy(COLLECTION)
    sizes = collections.Counter(s["domain"] for s in COLLECTION)
    small = next(s for s in renamed if sizes[s["domain"]] < DOMAIN_FOLD_MIN)
    small["domain"] = "other"
    with pytest.raises(ValueError, match="named 'other'"):
        build_domain_split(renamed)
    monkeypatch.setattr(splitcheck, "load_collection", lambda: renamed)
    splitcheck.run()
    assert any("domain 'other'" in f for f in splitcheck.fails), splitcheck.fails


def test_axis_resolution_raises_rather_than_guessing(monkeypatch):
    """An unresolvable key must stop the build, not fall into an arbitrary fold."""
    import whowins.splits.axes as axes
    monkeypatch.setattr(axes, "FORMAT_MODULES", ("values",))
    with pytest.raises(AxisResolutionError):
        axes.format_key_modules()


# --- The two design splits: source_pair and set ---

SOURCES = load_sources()
PAIR = _disk("source_pair")
SETS = _disk("set")


def test_the_source_inventory_is_derived_from_the_worked_trials():
    """Five sources, each a (transport, provenance), read off the composition
    cell rather than written down twice. Option ids are deliberately excluded:
    they rotate by Latin square, so comp-09 puts one action on two sources."""
    assert [s.source_id for s in SOURCES] == ["S1", "S2", "S3", "S4", "S5"]
    assert (SOURCES[2].transport_role == SOURCES[4].transport_role == "user"), \
        "S3 and S5 share a transport and differ only in label -- comp-03 exists " \
        "to ask whether they separate at all"
    assert len({(s.transport_role, s.displayed_provenance) for s in SOURCES}) == 5


def test_a_source_with_two_identities_raises(monkeypatch, tmp_path):
    """Guessing which reading is right would silently redefine the experiment."""
    import whowins.splits.sources as src
    trial = {"trial_id": "x", "spans": [
        {"source": "S1", "transport_role": "system", "displayed_provenance": "operator_policy"},
        {"source": "S1", "transport_role": "user", "displayed_provenance": "memory"}]}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([trial]))
    monkeypatch.setattr(src, "ROOT", str(tmp_path))
    monkeypatch.setattr(src, "COMPOSITION_TRIALS", "bad.json")
    with pytest.raises(src.SourceInventoryError, match="more than one identity"):
        src.load_sources()


def test_every_source_pair_is_held_out_exactly_once():
    ids = [s.source_id for s in SOURCES]
    want = {tuple(p) for p in itertools.combinations(ids, 2)}
    held = [tuple(p) for f in PAIR["folds"] for p in f["test"]]
    assert sorted(held) == sorted(want)
    assert len(held) == len(set(held)) == 10


def test_no_pair_fold_disconnects_the_source_graph():
    """A fold whose training pairs leave the graph disconnected is not a hard
    test but an unanswerable one: two components slide apart freely, so the
    held-out pair has no prediction to be wrong about."""
    for fold in PAIR["folds"]:
        assert fold["identifiability"]["connected"], fold["fold"]
        assert fold["identifiability"]["min_degree"] >= 2, fold["fold"]
        train = {tuple(p) for p in fold["train"]}
        test = {tuple(p) for p in fold["test"]}
        assert not (train & test) and len(train) == 9


def test_stage_one_fits_pairs_only():
    """The whole claim is that nothing above a pair was seen."""
    stage = SETS["stages"][0]
    assert stage["stage"] == "one"
    assert all(len(s) == 2 for s in stage["train"])
    assert len(stage["train"]) == 10
    assert all(len(s) >= 3 for group in stage["test_by_size"].values() for s in group)


def test_nothing_predicted_was_ever_fitted():
    for stage in SETS["stages"]:
        train = {tuple(s) for s in stage["train"]}
        test = {tuple(s) for g in stage["test_by_size"].values() for s in g}
        assert not (train & test), (stage["stage"], sorted(train & test))


def test_the_stage_two_slice_covers_every_pair():
    """A pair in no triple is a correlation stage two cannot estimate, and
    pairwise data provably cannot supply it. The stage would look like it ran
    while not being identified."""
    covered = set()
    for triple in SETS["stage_two_slice"]["triples"]:
        covered |= {frozenset(p) for p in itertools.combinations(triple, 2)}
    ids = [s.source_id for s in SOURCES]
    assert covered == {frozenset(p) for p in itertools.combinations(ids, 2)}
    assert len(SETS["stage_two_slice"]["triples"]) == 4, "the minimum is four"


def test_the_slice_is_minimal_and_the_choice_carries_no_information():
    """All ten minimum slices cover nine pairs once and one three times, so
    nothing in the data chooses between them. Asserted so that a future rule
    claiming to pick a *better* one has to explain what better means."""
    ids = [s.source_id for s in SOURCES]
    all_pairs = {frozenset(p) for p in itertools.combinations(ids, 2)}
    triples = list(itertools.combinations(ids, 3))

    def cover(sl):
        out = set()
        for t in sl:
            out |= {frozenset(p) for p in itertools.combinations(t, 2)}
        return out

    assert not any(cover(c) == all_pairs for c in itertools.combinations(triples, 3))
    minima = [c for c in itertools.combinations(triples, 4) if cover(c) == all_pairs]
    assert len(minima) == 10
    profiles = set()
    for c in minima:
        counts = collections.Counter()
        for t in c:
            counts.update(frozenset(p) for p in itertools.combinations(t, 2))
        profiles.add(tuple(sorted(collections.Counter(counts.values()).items())))
    assert profiles == {((1, 9), (3, 1))}, profiles


def test_the_slice_contains_the_triple_comp_07_declares():
    """comp-07 says in its own notes that it is part of the preselected slice.
    The split honours that rather than overruling a hand-written trial."""
    assert [ "S1", "S2", "S4" ] in SETS["stage_two_slice"]["triples"]
    assert SETS["stage_two_slice"]["anchor"] == ["S1", "S2", "S4"]


def test_both_stages_share_six_comparable_triples():
    """Stage one predicts all ten triples; stage two only the six outside its
    slice. Comparing 10 against 6 is not like for like, so the intersection is
    recorded for the comparison that is."""
    comparable = {tuple(t) for t in SETS["comparable_triples"]["sets"]}
    one = {tuple(s) for s in SETS["stages"][0]["test_by_size"]["3"]}
    two = {tuple(s) for s in SETS["stages"][1]["test_by_size"]["3"]}
    assert comparable == two == one - {tuple(t) for t in SETS["stage_two_slice"]["triples"]}
    assert len(comparable) == 6


def test_the_declared_ladder_is_two_three_five():
    """The dataset plan's cell table says n = 2, 3, 5. Four-way sets are
    enumerated separately because adding them is a scope decision."""
    assert SETS["declared_ladder"] == [2, 3, 5]
    sizes = {len(s) for stage in SETS["stages"]
             for group in stage["test_by_size"].values() for s in group}
    sizes |= {len(s) for stage in SETS["stages"] for s in stage["train"]}
    assert sizes == {2, 3, 5}
    assert all(len(s) == 4 for s in SETS["not_in_declared_ladder"]["sets"])
    assert len(SETS["not_in_declared_ladder"]["sets"]) == 5


def test_free_predictions_cover_both_worked_trials():
    """comp-09 is repetition, comp-10 agreement. Both must appear, or a worked
    trial has no entry in the split it belongs to."""
    shapes = {(tuple(e["sources"]), tuple(tuple(g) for g in e["groups"]))
              for e in SETS["free_predictions"]["compositions"]}
    assert (("S1", "S3", "S5"), (("S1",), ("S3", "S5"))) in shapes
    assert (("S1", "S2", "S3", "S5"), (("S1",), ("S2", "S3", "S5"))) in shapes
    assert SETS["free_predictions"]["n"] == 80 == len(shapes)


def test_free_predictions_are_two_groups_that_partition_their_sources():
    for entry in SETS["free_predictions"]["compositions"]:
        groups = entry["groups"]
        assert len(groups) == 2 and all(groups)
        flat = [x for g in groups for x in g]
        assert sorted(flat) == sorted(entry["sources"])
        assert len(set(flat)) == len(flat)
        assert entry["n_distinct_actions"] == 2


def test_free_predictions_are_not_labelled_repetition_or_agreement():
    """Which is which depends on whether the repeated action sits with the
    weaker sources -- the fitted ordering, unknown in advance (#16). Group sizes
    are recorded; the naming waits for the fit."""
    blob = json.dumps(SETS["free_predictions"]["compositions"])
    assert "repetition" not in blob and "agreement" not in blob
    for entry in SETS["free_predictions"]["compositions"]:
        assert entry["group_sizes"] == sorted(
            (len(g) for g in entry["groups"]), reverse=True)


@pytest.mark.parametrize("name", ["source_pair", "set"])
def test_the_design_splits_are_current(name):
    fresh = build_all()[name]
    on_disk = _disk(name)
    for field in ("sources", "folds", "stages", "stage_two_slice", "free_predictions"):
        if field in on_disk:
            assert on_disk[field] == fresh[field], f"{name}.{field} is stale"


def test_planted_fault_uncovered_slice_is_caught(broken):
    def mutate(doc):
        doc["stage_two_slice"]["triples"] = [["S1", "S2", "S3"], ["S1", "S2", "S4"],
                                             ["S1", "S2", "S5"]]
    assert "SPLIT-15" in broken("set", mutate)


def test_planted_fault_fitting_what_you_predict_is_caught(broken):
    def mutate(doc):
        doc["stages"][1]["train"].append(doc["stages"][1]["test_by_size"]["3"][0])
    assert "SPLIT-15" in broken("set", mutate)


def test_planted_fault_disconnected_pair_fold_is_caught(broken):
    def mutate(doc):
        fold = doc["folds"][0]
        fold["train"] = [p for p in fold["train"] if "S1" not in p]
        fold["identifiability"]["connected"] = False
    assert "SPLIT-14" in broken("source_pair", mutate)


def test_planted_fault_drifted_source_inventory_is_caught(broken):
    def mutate(doc):
        doc["sources"][2]["displayed_provenance"] = "retrieval"
    assert "SPLIT-13" in broken("set", mutate)
