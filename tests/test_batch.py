"""The design and the run loop: what gets sent, and what happens when it fails.
Two properties carry it: the trial list is a function of the run config, and a run that
dies mid-way resumes where it stopped. Nothing here calls a model -- the client talks to a
stub server that answers, refuses, hangs up or 500s to order."""

from __future__ import annotations

import collections
import fcntl
import http.server
import json
import logging
import math
import os
import threading
import time

import pytest

from whowins.checkers import fingerprint as checkers_fingerprint, option_values
from whowins.checkers.trace import parse_sequence
from whowins.runner import batch, rescore
from whowins.runner.batch import (
    TransportError,
    append_line,
    one_draw,
    pending,
    post_completion,
    read_log,
    report,
    run_batch,
)
from whowins.runner.design import (
    DesignError,
    arrangement_count,
    arrangement_for,
    assignments,
    build_balanced_trial,
    build_trial,
    load_sources,
    option_pairs,
    source_pairs,
    trials_for_run,
)
from whowins.runner.rendering import render_dicts
from whowins.runner.run import score
from whowins.runner.response import completion_from
from whowins.runner.serving import (
    ConfigError,
    UndeliverableTrial,
    check_delivery,
    load_policies,
    load_roster,
    load_run,
    stack_for,
)
from whowins.runner.tools import CONTEXT_TOOL, tools_for_trial
from whowins.runner.trials import load_scenarios

RUN = load_run("initial-qwen3-1.7b")
SCENARIOS = load_scenarios()
SOURCES = load_sources()
SPECS = trials_for_run(RUN, SCENARIOS)
BALANCED_RUN = load_run("balanced-qwen3-1.7b")
BALANCED = trials_for_run(BALANCED_RUN, SCENARIOS)
ROSTER = load_roster()
QWEN3 = ROSTER["qwen3-1.7b"].family
QWEN35 = ROSTER["qwen3.5-2b"].family


def _instruction_order(spec):
    """The sources of a trial, in the order the model reads them."""
    return [name for name in spec.meta["order"] if name != "task"]


# --- The design ---


def test_the_run_sends_every_scenario_once():
    assert len(SPECS) == len(SCENARIOS) == RUN.scenario_count == 1080
    assert len({s.trial_id for s in SPECS}) == len(SPECS)
    assert sorted(s.scenario_id for s in SPECS) == sorted(SCENARIOS)


def test_the_five_sources_are_the_ones_the_split_froze():
    assert sorted(SOURCES) == ["S1", "S2", "S3", "S4", "S5"]
    assert [(s.transport_role, s.displayed_provenance) for s in SOURCES.values()] == [
        ("system", "operator_policy"), ("developer", "repo_config"),
        ("user", "user_message"), ("tool", "tool_result"), ("user", "memory")]


def test_every_source_pair_is_seen_equally_often():
    pairs = collections.Counter(tuple(s.meta["source_pair"]) for s in SPECS)
    assert len(pairs) == 10
    assert set(pairs.values()) == {108}


def test_the_rotation_is_a_latin_square_inside_each_family():
    """Over each hundred scenarios every source pair meets every option pair
    once, so neither is confounded with the other -- or with the family."""
    combos = collections.Counter()
    for scenario, pair, options, _ in assignments(list(SCENARIOS.values()),
                                                  source_pairs(SOURCES)):
        if scenario["family"] == "format":  # 240 scenarios, five options
            combos[(pair, options)] += 1
    assert len(combos) == 100, "a 10 x 10 square is not being covered"
    assert set(combos.values()) <= {2, 3}


def test_which_source_carries_which_option_is_balanced():
    flipped = collections.Counter(s.meta["flipped"] for s in SPECS)
    assert flipped[True] > 400 and flipped[False] > 400


def test_the_same_config_builds_the_same_trials():
    """No randomness and no state: the list is a function of the config, so two
    people running the same command send the same thing."""
    again = trials_for_run(RUN, SCENARIOS)
    assert [s.trial_id for s in again] == [s.trial_id for s in SPECS]
    assert [render_dicts(s, SCENARIOS) for s in again[:50]] == \
        [render_dicts(s, SCENARIOS) for s in SPECS[:50]]


@pytest.mark.parametrize("family", ["qwen3", "qwen3.5"])
def test_every_trial_reaches_both_ladders_as_the_record_says(family):
    """The whole point of one operator message, first: the same list runs on
    either family without being rebuilt."""
    fam = {"qwen3": QWEN3, "qwen3.5": QWEN35}[family]
    for spec in SPECS:
        check_delivery(render_dicts(spec, SCENARIOS), fam)


def test_two_operator_sources_share_one_message_and_are_told_apart_by_label():
    """A second system message is refused, so an operator policy and a repo
    config arrive as two labelled lines in one -- which is exactly the level the
    study says they are."""
    spec = next(s for s in SPECS if s.meta["source_pair"] == ["S1", "S2"])
    messages = render_dicts(spec, SCENARIOS)
    assert [m["role"] for m in messages].count("system") == 1
    body = messages[0]["content"]
    assert "Operator policy for this deployment." in body
    assert "Repository configuration for this workspace." in body
    assert [s.position_slot for s in spec.spans] == [0, 1]


def test_a_tool_result_answers_a_call_the_transcript_shows():
    spec = next(s for s in SPECS if "S4" in s.meta["source_pair"])
    messages = render_dicts(spec, SCENARIOS)
    call = next(m for m in messages if m["role"] == "assistant")
    result = next(m for m in messages if m["role"] == "tool")
    assert call["tool_calls"][0]["function"]["name"] == CONTEXT_TOOL
    assert result["tool_call_id"] == call["tool_calls"][0]["id"]
    assert CONTEXT_TOOL in result["content"], "the result names the tool it came from"
    offered = [t["function"]["name"] for t in tools_for_trial(spec, SCENARIOS)]
    assert CONTEXT_TOOL in offered, "a call to a tool the model was never offered"


def test_no_other_trial_is_given_the_context_tool():
    """It is the price of the tool channel, and only that channel pays it."""
    for spec in SPECS:
        offered = [t["function"]["name"] for t in tools_for_trial(spec, SCENARIOS)]
        assert (CONTEXT_TOOL in offered) == ("S4" in spec.meta["source_pair"]), spec.trial_id


def test_two_user_sources_arrive_as_two_turns_with_their_own_labels():
    spec = next(s for s in SPECS if s.meta["source_pair"] == ["S3", "S5"])
    messages = render_dicts(spec, SCENARIOS)
    assert [m["role"] for m in messages] == ["user", "user", "user"]
    assert "Your saved note from an earlier session." in messages[1]["content"]


def test_a_trial_shows_exactly_the_two_options_it_is_scored_against():
    for spec in SPECS:
        shown = {s.option_id for s in spec.spans}
        assert len(shown) == 2
        assert set(spec.options_in_play) == shown
        assert set(spec.meta["carries"].values()) == shown


def test_a_design_the_run_does_not_name_is_refused():
    broken = type(RUN)(**{**RUN.__dict__, "design": "whatever-we-feel-like"})
    with pytest.raises(DesignError, match="unknown design"):
        trials_for_run(broken, SCENARIOS)


def test_a_run_asking_for_an_arm_no_design_builds_is_refused():
    """`composition_sizes` used to be read as a wish rather than a contract.
    A run configured for [1, 2, 3] passed every check, built no three-source trial and recorded
    in its own summary that it had asked for them. A missing arm that looks like a sent one is
    worse than a refused config."""
    for sizes in ((1, 2, 3), (3,), (2, 5)):
        run = type(BALANCED_RUN)(**{**BALANCED_RUN.__dict__,
                                    "composition_sizes": sizes,
                                    "composition_max_sources": max(sizes)})
        with pytest.raises(DesignError, match="does not build one"):
            trials_for_run(run, SCENARIOS)
    # The two that are built are untouched.
    assert len(trials_for_run(BALANCED_RUN, SCENARIOS)) == 3240


@pytest.mark.parametrize("design", ["composition-ladder", "composition-ladder-flat"])
def test_the_ladder_builds_the_declared_sizes_and_refuses_the_rest(design):
    """The dataset plan declares n = 2, 3, 5. Four-way sets are enumerated in
    data/splits/set.json under `not_in_declared_ladder` on purpose, so the ladder
    refuses them by name rather than building them because nothing stopped it --
    adding a rung is a scope decision somebody makes."""
    def ladder(sizes):
        return type(BALANCED_RUN)(**{**BALANCED_RUN.__dict__, "design": design,
                                     "composition_sizes": sizes,
                                     "composition_max_sources": max(max(sizes), 2)})

    for sizes in ((4,), (2, 4), (1, 2, 3, 4, 5)):
        with pytest.raises(DesignError, match="not_in_declared_ladder"):
            trials_for_run(ladder(sizes), SCENARIOS)
    with pytest.raises(DesignError, match="nothing for it to control"):
        trials_for_run(ladder((1,)), SCENARIOS)

    # And the sizes it does build, with the counts a run config has to budget for.
    assert len(trials_for_run(ladder((1, 2)), SCENARIOS)) == 3240
    assert len(trials_for_run(ladder((2, 3, 5)), SCENARIOS)) == 1080 + 960 + 960


# --- The composition ladder: these check the properties that make a set above a pair worth sending, not merely possible to send ---


def _ladder(sizes, run=None, design="composition-ladder"):
    base = run or BALANCED_RUN
    return type(base)(**{**base.__dict__, "design": design,
                         "composition_sizes": tuple(sizes),
                         "composition_max_sources": 5})


def _by_composition(specs):
    out = {}
    for spec in specs:
        if spec.meta.get("arm") != "pair":
            continue
        out.setdefault("-".join(spec.meta["composition"]), []).append(spec)
    return out


def _spread(counter):
    """The worst relative gap between the most and least frequent cell."""
    worst = 0.0
    for key in {k for k, _ in counter}:
        values = [v for (k, _), v in counter.items() if k == key]
        worst = max(worst, (max(values) - min(values)) / max(values))
    return worst


LADDER_SPECS = trials_for_run(_ladder((2, 3, 5)), SCENARIOS)
FLAT_SPECS = trials_for_run(_ladder((2, 3, 5), design="composition-ladder-flat"), SCENARIOS)
BOTH_LADDERS = pytest.mark.parametrize("specs", [LADDER_SPECS, FLAT_SPECS],
                                       ids=["composition-ladder", "composition-ladder-flat"])


@BOTH_LADDERS
def test_every_source_sits_in_every_slot_equally_at_every_size(specs):
    """THE TEST THIS DESIGN EXISTS FOR, and it caught two real faults.
    A source sitting early more often than late has its strength confounded with position,
    which is what the first run's headline turned out to be. Both faults -- the nested
    arrangement counter and all n! permutations -- were found by counting slots here."""
    for name, group in sorted(_by_composition(specs).items()):
        slots = collections.Counter()
        for spec in group:
            for key, value in spec.meta["slots"].items():
                if key != "task":
                    slots[(key, value)] += 1
        assert _spread(slots) == 0.0, (
            f"{name}: a source sits in some slots more than others -- "
            f"{sorted(slots.items())}")


@BOTH_LADDERS
def test_every_arrangement_of_every_composition_is_used_the_same_number_of_times(specs):
    from whowins.runner.design import arrangement_count

    for name, group in sorted(_by_composition(specs).items()):
        size = len(group[0].meta["composition"])
        pinned = len(group[0].meta["operator_pinned"])
        total = arrangement_count(pinned, size - pinned)
        used = collections.Counter(spec.meta["arrangement"] for spec in group)
        assert len(used) == total, f"{name}: {len(used)} of {total} arrangements"
        assert len(set(used.values())) == 1, f"{name}: {sorted(used.items())}"


def test_the_option_assignment_is_a_latin_square_and_is_flipped_at_two_sources():
    """Each source carries each option once over `size` consecutive indices --
    the content rotation the study's method asks for, so a content preference cannot
    masquerade as a source effect. All n! permutations were tried instead and
    spread the data so thin that the arrangement counter under-covered."""
    from whowins.runner.design import permutation_for

    for size in (2, 3, 5):
        seen = [permutation_for(i, size) for i in range(size)]
        for position in range(size):
            assert sorted(p[position] for p in seen) == list(range(size)), size
    assert permutation_for(0, 2) == (0, 1) and permutation_for(1, 2) == (1, 0), (
        "at two sources the square is exactly pairwise-balanced's `flipped`")


@BOTH_LADDERS
def test_a_trial_shows_exactly_the_options_it_is_scored_against_at_every_size(specs):
    for spec in specs:
        shown = {s.option_id for s in spec.spans}
        size = spec.meta["n_competing"]
        assert len(shown) == size, spec.trial_id
        assert set(spec.options_in_play) == shown, spec.trial_id
        assert set(spec.meta["carries"].values()) == shown, spec.trial_id


def test_a_family_with_too_few_options_is_left_out_above_a_pair():
    """Read off the scenario, never off the family name.
    A set of n sources needs n mutually exclusive options; refusal has two, because the dataset
    plan says it is binary by nature and pairwise only. A family that gained an option would
    join with no edit to the code."""
    from whowins.runner.design import eligible_for

    scenarios = list(SCENARIOS.values())
    assert eligible_for(scenarios, 2)[1] == {}, "every family can carry a pair"
    for size in (3, 5):
        keep, dropped = eligible_for(scenarios, size)
        assert dropped == {"refusal": 120}, (size, dropped)
        assert len(keep) == 960
    by_size = collections.Counter(s.meta["composition_size"] for s in LADDER_SPECS)
    assert by_size == {2: 1080, 3: 960, 5: 960}

    families = {s.meta["composition_size"]:
                {SCENARIOS[x.scenario_id]["family"] for x in LADDER_SPECS
                 if x.meta["composition_size"] == s.meta["composition_size"]}
                for s in LADDER_SPECS}
    assert "refusal" in families[2] and "refusal" not in families[3]


def test_the_ladder_sends_the_same_conflicts_as_pairwise_balanced_at_two_sources():
    """A generalisation, not a replacement.
    Scenario, composition and option set come from the same Latin square, so a ladder run's pair
    arm asks what runs 2 and 3 asked. The LAYOUT differs deliberately, which is why the ladder
    is a new design name."""
    pairs_only = {s.trial_id: s for s in trials_for_run(_ladder((2,)), SCENARIOS)}
    balanced = {s.trial_id: s for s in BALANCED if s.meta["arm"] == "pair"}
    assert set(pairs_only) == set(balanced), "the same trials, by id"
    for tid, spec in pairs_only.items():
        assert set(spec.options_in_play) == set(balanced[tid].options_in_play), tid
        assert spec.meta["composition"] == balanced[tid].meta["source_pair"], tid


def test_a_solo_arm_of_a_larger_set_does_not_collide_with_a_pair_s():
    """A scenario appears in a pair, a triple and the five-way, so `scenario@S1`
    would be three different trials -- different option, different arrangement --
    wearing one id. A run resumes by id."""
    specs = trials_for_run(_ladder((1, 2, 3)), SCENARIOS)
    ids = [s.trial_id for s in specs]
    assert len(set(ids)) == len(ids)
    solo = next(s for s in specs if s.meta["arm"] == "solo"
                and s.meta["composition_size"] == 3)
    assert "~" in solo.trial_id and "-".join(solo.meta["composition"]) in solo.trial_id
    assert solo.meta["n_competing"] == 1 and len(solo.options_in_play) == 1


@BOTH_LADDERS
@pytest.mark.parametrize("family", ["qwen3", "qwen3.5"])
def test_every_ladder_trial_reaches_both_ladders_as_the_record_says(family, specs):
    """The standing rule, at every size: a request either engine would rewrite is
    refused before it exists. A five-way trial is the longest conversation this
    study builds and is where a template would break first."""
    fam = {"qwen3": QWEN3, "qwen3.5": QWEN35}[family]
    for size in (2, 3, 5):
        for spec in [s for s in specs if s.meta["composition_size"] == size][:120]:
            check_delivery(render_dicts(spec, SCENARIOS), fam)


def test_every_option_of_a_larger_set_can_actually_win_it():
    """A set nothing can be scored against is not a measurement.
    For each option the trial shows, sends a reply doing exactly that and requires the checker
    to name it; then sends one the trial does not show and requires off-menu."""
    from whowins.checkers import option_values

    stack = stack_for(BALANCED_RUN.deployment, gpu_count=1)
    for size in (3, 5):
        spec = next(s for s in LADDER_SPECS
                    if s.meta["composition_size"] == size
                    and s.scenario_id.startswith("path-"))
        scenario = SCENARIOS[spec.scenario_id]
        values = option_values(scenario)
        for option in spec.options_in_play:
            record = score(spec, SCENARIOS, [completion_from(tool_calls=[
                {"name": "write_file",
                 "arguments": {"path": f"{values[option]}/report.txt"}}])], stack)
            assert record.outcome.winning_option == option, (spec.trial_id, option)
        spare = next((o["id"] for o in scenario["options"]
                      if o["id"] not in spec.options_in_play), None)
        if spare is None:
            # The five-way shows every option the scenario has, so there is no sixth answer to be off the menu.
            assert size == 5 and len(spec.options_in_play) == len(scenario["options"])
            continue
        record = score(spec, SCENARIOS, [completion_from(tool_calls=[
            {"name": "write_file",
             "arguments": {"path": f"{values[spare]}/report.txt"}}])], stack)
        assert record.outcome.behaviour == "off_menu", spec.trial_id


def _option_gap(specs):
    """The worst gap, in trials, between the sources of one composition carrying one option."""
    worst = 0
    for name, group in _by_composition(specs).items():
        carried = collections.Counter((s, o) for spec in group
                                      for s, o in spec.meta["carries"].items())
        for option in {o for _, o in carried}:
            counts = [carried[(s, option)] for s in group[0].meta["composition"]]
            worst = max(worst, max(counts) - min(counts))
    return worst


def test_in_the_flat_ladder_every_source_carries_every_option_equally():
    """Options are not equally easy: alone, the 14B produced o1 0.85 of the time and o3 0.77.
    In the old ladder's S3-S4-S5, S5 carried o4 8 times where S3 and S4 carried it 24, so a
    source could look weak for the options it was handed. Flat means within one trial."""
    assert _option_gap(FLAT_SPECS) <= 1
    assert _option_gap(LADDER_SPECS) == 16, "the gap this design exists to close"


def _last_share_error(specs):
    """The worst distance, over compositions and options, from sitting last 1/size of the time."""
    worst = 0.0
    for name, group in _by_composition(specs).items():
        size = len(group[0].meta["composition"])
        last = collections.Counter()
        seen = collections.Counter()
        for spec in group:
            final = max(spec.meta["composition"], key=lambda s: spec.meta["slots"][s])
            for source, option in spec.meta["carries"].items():
                seen[option] += 1
                last[option] += source == final
        worst = max(worst, max(abs(last[o] / seen[o] - 1 / size) for o in seen))
    return worst


def test_in_the_flat_ladder_no_option_is_tied_to_a_position():
    """The later instruction wins about nine times in ten, so an option that sits last more
    often gains a win it did not earn. In the old ladder's S1-S2, o1 was always the first
    line and o5 always the second."""
    assert _last_share_error(FLAT_SPECS) < 0.07
    assert _last_share_error(LADDER_SPECS) == 0.5


def test_the_flat_ladder_sends_the_same_trials_with_every_option_set_in_every_composition():
    """The same scenario in the same composition and arrangement, so switching a run to the
    flat ladder changes which option each source carries and nothing else."""
    old = {s.trial_id: s for s in LADDER_SPECS}
    assert {s.trial_id for s in FLAT_SPECS} == set(old)
    for spec in FLAT_SPECS:
        assert spec.meta["design"] == "composition-ladder-flat"
        assert spec.meta["arrangement"] == old[spec.trial_id].meta["arrangement"]
        assert set(spec.meta["offsets"]) and 0 <= spec.meta["rotation"] < 5
    for name, group in _by_composition(FLAT_SPECS).items():
        size = len(group[0].meta["composition"])
        sets = {frozenset(s.meta["carries"].values()) for s in group
                if len(SCENARIOS[s.scenario_id]["options"]) == 5}
        assert len(sets) == math.comb(5, size), name


@BOTH_LADDERS
def test_the_five_way_is_one_composition_and_every_source_carries_every_option(specs):
    five = [s for s in specs if s.meta["composition_size"] == 5]
    assert len({tuple(s.meta["composition"]) for s in five}) == 1
    carried = collections.Counter()
    for spec in five:
        for source, option in spec.meta["carries"].items():
            carried[(source, option)] += 1
    assert len(carried) == 25, "five sources by five options"
    assert len(set(carried.values())) == 1, sorted(carried.items())


FREE_SPECS = trials_for_run(type(BALANCED_RUN)(**{
    **BALANCED_RUN.__dict__, "design": "free-predictions", "composition_sizes": (3, 4, 5),
    "composition_max_sources": 5}), SCENARIOS)


def test_every_free_prediction_is_sent_with_its_groups_sharing_an_option():
    """The 80 sets of data/splits/set.json where several sources demand the same option: each
    scenario once per size, every group carrying one option, and the groups dealt options as
    evenly as the flat ladder deals sources."""
    from whowins.runner.design import free_groupings

    assert collections.Counter(s.meta["composition_size"] for s in FREE_SPECS) == \
        {3: 1080, 4: 1080, 5: 1080}
    assert len({s.trial_id for s in FREE_SPECS}) == len(FREE_SPECS)
    assert not {s.trial_id for s in FREE_SPECS} & {s.trial_id for s in LADDER_SPECS}
    assert {tuple(tuple(g) for g in s.meta["groups"]) for s in FREE_SPECS} == \
        {tuple(tuple(sorted(g)) for g in grouping) for grouping in free_groupings()}
    carried = collections.defaultdict(collections.Counter)
    for spec in FREE_SPECS:
        groups = spec.meta["groups"]
        assert sorted(sum(groups, [])) == sorted(spec.meta["composition"])
        options = [{spec.meta["carries"][s] for s in g} for g in groups]
        assert all(len(o) == 1 for o in options) and len(set.union(*options)) == len(groups)
        for group, option in zip(groups, options):
            carried[spec.trial_id.split("@")[1]][("+".join(group), option.pop())] += 1
    for grouping, counts in carried.items():
        for option in {o for _, o in counts}:
            per_group = [counts[(g, option)] for g in {g for g, _ in counts}]
            assert max(per_group) - min(per_group) <= 2, (grouping, option)


def test_a_shared_win_is_scored_and_credited_to_no_single_source():
    from whowins.checkers import option_values
    from whowins.runner.analyse import _winner

    spec = next(s for s in FREE_SPECS if s.scenario_id.startswith("path-")
                and s.meta["composition_size"] == 4)
    stack = stack_for(BALANCED_RUN.deployment, gpu_count=1)
    values = option_values(SCENARIOS[spec.scenario_id])
    for option in set(spec.options_in_play):
        record = score(spec, SCENARIOS, [completion_from(tool_calls=[{
            "name": "write_file", "arguments": {"path": f"{values[option]}/report.txt"}}])],
            stack)
        assert record.outcome.winning_option == option
        sharers = [s for s, o in spec.meta["carries"].items() if o == option]
        row = {**record.as_dict(), "meta": spec.meta}
        assert _winner(row) == (sharers[0] if len(sharers) == 1 else None)


@pytest.mark.parametrize("family", ["qwen3", "qwen3.5"])
def test_free_predictions_the_load_trials_and_the_tiers_reach_both_qwen_families(family):
    fam = {"qwen3": QWEN3, "qwen3.5": QWEN35}[family]

    def built(design):
        return trials_for_run(type(BALANCED_RUN)(**{
            **BALANCED_RUN.__dict__, "design": design, "composition_sizes": (2,)}), SCENARIOS)
    for spec in [*FREE_SPECS[::27], *built("load-cell"), *built("load-bundles"),
                 *built("declared-tiers")[::97]]:
        check_delivery(render_dicts(spec, SCENARIOS), fam)


def test_the_load_cell_sends_its_ten_trials_on_each_family_s_operator_channel():
    """The worked load trials put every instruction in one system message, which gpt-oss
    would not receive as written: its operator channel is the developer message."""
    oss = ROSTER["gpt-oss-120b"]
    for family, role in ((QWEN3, "system"), (oss.family, "developer")):
        run = type(BALANCED_RUN)(**{**BALANCED_RUN.__dict__, "design": "load-cell",
                                    "composition_sizes": (2,)})
        if role == "developer":
            run = type(run)(**{**run.__dict__, "deployment": oss.deployment,
                               "policy": load_policies()["study-think-gpt-oss"]})
        specs = trials_for_run(run, SCENARIOS)
        assert sorted(s.trial_id for s in specs) == [f"load-{i:02d}" for i in range(1, 11)]
        for spec in specs:
            messages = render_dicts(spec, SCENARIOS)
            assert messages[0]["role"] == role and spec.meta["design"] == "load-cell"
            check_delivery(messages, family)


def test_run_main_names_what_it_cannot_find():
    import subprocess

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    done = subprocess.run([os.path.join(root, "scripts", "run_main.sh"), "no-such-model"],
                          capture_output=True, text=True)
    assert done.returncode == 2 and "no main run" in done.stderr


def test_run_main_sends_the_kinds_in_priority_order_and_refuses_one_it_does_not_know():
    """Each kind finishes in both modes before the next starts, so a run cut short holds whole
    experiments, most important first."""
    import re
    import subprocess

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(root, "scripts", "run_main.sh")
    kinds = re.search(r'^kinds="([^"]+)"', open(script).read(), re.M).group(1).split()
    assert kinds == ["ladder", "operator", "realism", "message", "free", "load", "tier"]
    runs = {r.split("-")[1] for r in os.listdir(os.path.join(root, "configs", "runs"))
            if r.startswith("main-")}
    assert runs == set(kinds)
    done = subprocess.run([script, "qwen3-8b", "--only", "ladder,bogus"],
                          capture_output=True, text=True)
    assert done.returncode == 2 and "unknown kind: bogus" in done.stderr


def test_a_run_that_would_put_one_source_in_play_is_refused():
    lonely = type(RUN)(**{**RUN.__dict__, "composition_max_sources": 1})
    with pytest.raises(DesignError, match="two sources"):
        trials_for_run(lonely, SCENARIOS)


def test_a_run_whose_count_disagrees_with_its_scenarios_is_refused():
    """A run that sent a different number than it recorded could not be
    reproduced from its config."""
    half = dict(list(SCENARIOS.items())[:500])
    with pytest.raises(DesignError, match="scenarios"):
        trials_for_run(RUN, half)


def test_a_scenario_with_one_option_conflicts_with_nothing():
    with pytest.raises(DesignError, match="conflicts with nothing"):
        option_pairs({"scenario_id": "x", "options": [{"id": "o1"}]})


def test_a_trial_takes_two_sources_and_two_options():
    scenario = SCENARIOS["path-0001"]
    with pytest.raises(DesignError, match="two sources and two options"):
        build_trial(scenario, SOURCES, ["S1"], ["o1", "o2"], flipped=False,
                    operator_role="system")


def test_an_operator_source_rides_the_channel_its_family_has():
    """S2 declares developer, which no Qwen carries and gpt-oss uses for
    everything operator. It rides whichever channel the family has."""
    assert SOURCES["S2"].rides_on("system") == "system"
    assert SOURCES["S1"].rides_on("developer") == "developer"
    assert SOURCES["S3"].rides_on("developer") == "user"
    assert SOURCES["S4"].rides_on("system") == "tool"


# --- The stub server ---


class _Handler(http.server.BaseHTTPRequestHandler):
    behaviour: dict = {}

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        if self.path == "/version" and not self.behaviour.get("no_version"):
            self._send(200, {"version": "0.8.5.post1"})
        else:
            self._send(404, {})

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        self.behaviour.setdefault("seen", []).append(body)
        code = self.behaviour.get("code", 200)
        if code != 200:
            self._send(code, {"error": {"message": "no"}})
            return
        text = self.behaviour.get("text", "Done.")
        self._send(200, completion_from(text=text))

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    behaviour: dict = {}
    handler = type("H", (_Handler,), {"behaviour": behaviour})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", behaviour
    httpd.shutdown()
    httpd.server_close()


def _small_run(tmp_path, monkeypatch, count=6):
    """The real run config over a handful of scenarios, so a whole pass is quick."""
    ids = sorted(SCENARIOS)[:count]
    scenarios = {i: SCENARIOS[i] for i in ids}
    run = type(RUN)(**{**RUN.__dict__, "scenario_count": len(scenarios)})
    return run, scenarios, str(tmp_path / "records.jsonl")


# --- The client ---


def test_the_client_posts_a_completion_and_reads_the_reply(server):
    url, behaviour = server
    behaviour["text"] = "Staged in /scratch/a."
    payload = post_completion(url, {"model": "m", "messages": []}, timeout=5)
    assert payload["choices"][0]["message"]["content"] == "Staged in /scratch/a."
    assert behaviour["seen"][0]["model"] == "m"


def test_a_refused_request_is_our_mistake_and_is_not_retried(server):
    url, behaviour = server
    behaviour["code"] = 400
    with pytest.raises(ConfigError, match="refused the request"):
        post_completion(url, {"model": "m"}, timeout=5)


@pytest.mark.parametrize("code", sorted(batch.RETRYABLE_STATUS))
def test_a_server_saying_it_is_busy_is_a_transport_error_not_a_bad_request(server, code):
    """429 and 408 sit in the 4xx range and are not about the request.
    They say the server has more work than it can take, and they arrive exactly when a run is at
    its most concurrent. Read as ConfigError they would kill the run."""
    url, behaviour = server
    behaviour["code"] = code
    with pytest.raises(TransportError, match=f"HTTP {code}"):
        post_completion(url, {"model": "m"}, timeout=5)


def test_a_busy_server_is_retried_and_the_run_carries_on(server, tmp_path, monkeypatch):
    url, behaviour = server
    run, scenarios, log = _small_run(tmp_path, monkeypatch, count=2)
    behaviour["code"] = 429
    summary = run_batch(run, scenarios, url, log, retries=2, sleep=lambda s: None)
    assert (summary["scored"], summary["failed"]) == (0, 2), "not fatal, and not silent"
    assert all(json.loads(line)["line"] == "failure" for line in open(log))
    behaviour["code"] = 200
    assert run_batch(run, scenarios, url, log)["scored"] == 2


def test_a_server_error_or_a_closed_port_is_a_transport_error(server):
    url, behaviour = server
    behaviour["code"] = 503
    with pytest.raises(TransportError, match="HTTP 503"):
        post_completion(url, {"model": "m"}, timeout=5)
    with pytest.raises(TransportError):
        post_completion("http://127.0.0.1:1", {"model": "m"}, timeout=2)


def test_a_draw_is_retried_on_transport_errors_and_keeps_its_seed(tmp_path, monkeypatch):
    run, scenarios, _ = _small_run(tmp_path, monkeypatch)
    spec = trials_for_run(run, scenarios)[0]
    stack = stack_for(run.deployment, gpu_count=1)
    tries: list = []
    waits: list = []

    def flaky(base_url, body, timeout=None, api_key=None):
        tries.append(body["seed"])
        if len(tries) < 3:
            raise TransportError("connection reset")
        return completion_from(text="Done.")

    record, errors = one_draw(spec, 0, run, scenarios, stack, "http://x",
                              timeout=1, retries=3, api_key=None, post=flaky,
                              sleep=waits.append)
    assert record is not None and record.attempt == 3
    assert len(set(tries)) == 1, "a retry asks for the same draw, so the same seed"
    assert tries[0] == run.decoding(spec.trial_id, 0).seed
    assert errors == ["connection reset", "connection reset"]
    assert waits == [2.0, 4.0]


def test_a_draw_that_never_comes_back_is_reported_not_invented(tmp_path, monkeypatch):
    run, scenarios, _ = _small_run(tmp_path, monkeypatch)
    spec = trials_for_run(run, scenarios)[0]
    stack = stack_for(run.deployment, gpu_count=1)

    def dead(*a, **k):
        raise TransportError("timed out")

    record, errors = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                              retries=2, api_key=None, post=dead, sleep=lambda s: None)
    assert record is None and errors == ["timed out", "timed out"]


def test_a_malformed_tool_call_header_is_the_models_reply_with_a_fault(tmp_path, monkeypatch):
    run, scenarios, _ = _small_run(tmp_path, monkeypatch)
    spec = trials_for_run(run, scenarios)[0]
    stack = stack_for(run.deployment, gpu_count=1)
    bad = ('HTTP 500: {"error":{"message":"unexpected tokens remaining in message header: '
           'Some(\\"to=functions.dump_core <|constrain|>???\\")"}}')

    def garbled(*a, **k):
        raise TransportError(bad)

    record, errors = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                              retries=3, api_key=None, post=garbled, sleep=lambda s: None)
    assert record is not None and record.attempt == 3
    assert record.stopped_by == "malformed_tool_call"
    assert not record.usable and any("tool-call header" in f for f in record.faults)
    assert errors == [bad] * 3


def test_a_malformed_header_that_clears_on_a_retry_is_an_ordinary_answer(tmp_path, monkeypatch):
    run, scenarios, _ = _small_run(tmp_path, monkeypatch)
    spec = trials_for_run(run, scenarios)[0]
    stack = stack_for(run.deployment, gpu_count=1)
    tries: list = []

    def once(*a, **k):
        tries.append(1)
        if len(tries) == 1:
            raise TransportError("HTTP 500: unexpected tokens remaining in message header")
        return completion_from(text="Done.")

    record, _ = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                         retries=3, api_key=None, post=once, sleep=lambda s: None)
    assert record is not None and record.stopped_by != "malformed_tool_call"
    assert not any("tool-call header" in f for f in record.faults)


# --- The run loop, the log, and resuming ---


def test_a_whole_small_run_lands_one_line_per_trial(server, tmp_path, monkeypatch):
    url, _ = server
    run, scenarios, log = _small_run(tmp_path, monkeypatch)
    summary = run_batch(run, scenarios, url, log, gpu="Tesla V100-SXM2-32GB",
                        engine_version="0.8.5.post1")
    assert (summary["sent"], summary["scored"], summary["failed"]) == (6, 6, 0)
    rows = [json.loads(line) for line in open(log)]
    assert len(rows) == 6
    assert {r["run_id"] for r in rows} == {run.run_id}
    assert all(r["line"] == "record" for r in rows)
    assert all(r["serving_stack"]["environment"] == "v100-vllm085" for r in rows)
    assert all(r["decoding"]["temperature"] == 0.7 for r in rows)
    assert all(r["messages"] for r in rows)


def test_a_server_that_will_not_say_its_version_is_not_recorded_as_the_pinned_one(
        server, tmp_path):
    """Only reachable with --skip-preflight, which is when it matters: `stack_for` fell back to
    the pinned version, so the record presented a config value as something the server said."""
    url, behaviour = server
    behaviour["no_version"] = True
    log = str(tmp_path / "records.jsonl")
    argv = ["initial-qwen3-1.7b", "--base-url", url, "--skip-preflight", "--out", log,
            "--limit", "1", "--no-log-file", "--progress", "none", "--quiet"]
    assert batch._main(argv) == 2
    assert read_log(log) == ({}, 0), "nothing is sent under a version nobody reported"
    assert batch._main([*argv, "--allow-unpinned-engine"]) == 0
    row = next(batch.read_records(log))
    assert row["serving_stack"]["vllm_version"] == "unreported"


def test_running_the_same_command_again_sends_nothing_new(server, tmp_path, monkeypatch):
    url, behaviour = server
    run, scenarios, log = _small_run(tmp_path, monkeypatch)
    run_batch(run, scenarios, url, log)
    first = len(behaviour["seen"])
    summary = run_batch(run, scenarios, url, log)
    assert (summary["sent"], summary["scored"]) == (0, 0)
    assert len(behaviour["seen"]) == first, "a trial already answered was sent again"
    assert len(list(open(log))) == 6


def test_a_run_that_stopped_half_way_carries_on_from_where_it_was(server, tmp_path, monkeypatch):
    url, behaviour = server
    run, scenarios, log = _small_run(tmp_path, monkeypatch)
    run_batch(run, scenarios, url, log, limit=2)
    assert len(list(open(log))) == 2
    summary = run_batch(run, scenarios, url, log)
    assert summary["already_answered"] == 2 and summary["sent"] == 4
    ids = [json.loads(line)["trial_id"] for line in open(log)]
    assert len(ids) == len(set(ids)) == 6


def test_a_line_cut_off_by_the_kill_costs_one_trial_not_the_run(server, tmp_path, monkeypatch):
    """And costs exactly one: appending onto a half-written line would glue the
    fragment to the next record and lose that one as well."""
    url, _ = server
    run, scenarios, log = _small_run(tmp_path, monkeypatch)
    run_batch(run, scenarios, url, log, limit=3)
    with open(log) as fh:
        lines = fh.readlines()
    with open(log, "w") as fh:  # as a kill mid-write leaves it
        fh.writelines(lines[:-1])
        fh.write(lines[-1][:60])
    answered, broken = read_log(log)
    assert len(answered) == 2 and broken == 1
    summary = run_batch(run, scenarios, url, log)
    assert summary["sent"] == 4
    assert len({json.loads(l)["trial_id"] for l in open(log) if '"line": "record"' in l}) == 6


def test_a_kill_inside_a_character_costs_one_trial_not_the_run(server, tmp_path, monkeypatch):
    """Records keep non-ASCII text as UTF-8, so a kill can cut an em dash in half. The log
    was read as text, and resume, the report, analyse and rescore all raised on it."""
    url, _ = server
    run, scenarios, log = _small_run(tmp_path, monkeypatch)
    run_batch(run, scenarios, url, log, limit=3)
    with open(log, "rb") as fh:
        lines = fh.readlines()
    last = dict(json.loads(lines[-1]), note="em\u2014dash")
    cut = json.dumps(last, ensure_ascii=False).encode("utf-8")
    with open(log, "wb") as fh:  # one byte into the three the dash takes
        fh.writelines(lines[:-1])
        fh.write(cut[:cut.index("\u2014".encode("utf-8")) + 1])
    answered, broken = read_log(log)
    assert len(answered) == 2 and broken == 1
    assert len(list(batch.read_records(log))) == 2
    assert report(run, scenarios, log)["answered"] == 2
    summary = run_batch(run, scenarios, url, log)
    assert summary["sent"] == 4
    assert len({row["trial_id"] for row in batch.read_records(log)}) == 6


def test_a_second_process_on_the_same_log_is_refused_before_it_sends_anything(tmp_path):
    """What is pending is read once at start-up, so two `run_trials.sh` on one run would each
    send every trial the other was sending, and the log would hold both."""
    run, scenarios, log = _small_run(tmp_path, None, count=2)
    post = _scripted(completion_from(text="Done."))
    refused = None
    with open(log, "ab") as first:  # held as the first process holds it
        fcntl.flock(first, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            run_batch(run, scenarios, "http://x", log, post=post, sleep=lambda s: None)
        except RuntimeError as exc:
            refused = exc
    assert post.sent == [] and read_log(log) == ({}, 0), "sent beside a run holding the log"
    assert isinstance(refused, batch.LogInUse) and "another process" in str(refused)
    assert run_batch(run, scenarios, "http://x", log, post=post,
                     sleep=lambda s: None)["scored"] == 2, "released when the holder is done"


def test_a_finished_log_can_be_read_compressed(tmp_path):
    """A thinking run's log can pass GitHub's 100 MB limit, and gzip takes a log to about a
    fifteenth. Every reader takes `records.jsonl.gz` where `records.jsonl` is not there."""
    import gzip

    run, scenarios, log = _small_run(tmp_path, None, count=2)
    run_batch(run, scenarios, "http://x", log, post=_scripted(completion_from(text="Done.")),
              sleep=lambda s: None)
    with open(log, "rb") as src, gzip.open(log + ".gz", "wb") as dst:
        dst.write(src.read())
    os.remove(log)
    assert read_log(log) == ({s.trial_id: {0} for s in trials_for_run(run, scenarios)}, 0)
    assert len(rescore.rescore(run.run_id, log, scenarios, run=run)["rows"]) == 2


def test_a_slow_trial_does_not_hold_back_the_ones_that_finished_behind_it(
        tmp_path, monkeypatch):
    """The fsync promise at the top of the module, under concurrency.
    `pool.map` yields in submission order, so one slow trial kept every trial behind it in memory
    and unwritten -- and a run killed then lost all of them."""
    run, scenarios, log = _small_run(tmp_path, monkeypatch, count=4)
    held = threading.Event()
    first = threading.Event()
    seen = []

    def post(base_url, body, timeout=None, api_key=None):
        mine = len(seen)
        seen.append(mine)
        if mine == 0:
            first.set()
            assert held.wait(10), "the test's own release never came"
        return completion_from(text="Done.")

    out = {}
    runner = threading.Thread(
        target=lambda: out.update(run_batch(run, scenarios, "http://x", log,
                                            concurrency=4, post=post,
                                            sleep=lambda s: None)))
    runner.start()
    assert first.wait(10), "the first request never went out"
    deadline = time.time() + 10
    landed = 0
    while time.time() < deadline:
        if os.path.exists(log):
            landed = sum(1 for _ in open(log))
            if landed >= 3:
                break
        time.sleep(0.01)
    assert landed >= 3, (
        f"only {landed} records reached disk while one trial was still in "
        f"flight; they were being held in memory")
    held.set()
    runner.join(20)
    assert not runner.is_alive()
    assert out["scored"] == 4
    assert len({json.loads(line)["trial_id"] for line in open(log)}) == 4


def test_concurrency_sends_each_trial_once_and_records_what_it_used(
        server, tmp_path, monkeypatch):
    url, behaviour = server
    run, scenarios, log = _small_run(tmp_path, monkeypatch, count=6)
    summary = run_batch(run, scenarios, url, log, concurrency=4)
    rows = [json.loads(line) for line in open(log)]
    assert summary["scored"] == 6 and len(rows) == 6
    assert len({r["trial_id"] for r in rows}) == 6
    assert {r["concurrency"] for r in rows} == {4}
    assert run_batch(run, scenarios, url, log, concurrency=4)["sent"] == 0


def test_a_transport_failure_is_logged_and_tried_again_next_time(server, tmp_path, monkeypatch):
    url, behaviour = server
    run, scenarios, log = _small_run(tmp_path, monkeypatch, count=2)
    behaviour["code"] = 503
    summary = run_batch(run, scenarios, url, log, retries=2, sleep=lambda s: None)
    assert (summary["scored"], summary["failed"]) == (0, 2)
    rows = [json.loads(line) for line in open(log)]
    assert all(r["line"] == "failure" and "503" in r["error"] for r in rows)

    behaviour["code"] = 200
    again = run_batch(run, scenarios, url, log)
    assert again["sent"] == 2 and again["scored"] == 2
    assert again["past_failures"] == 2


def test_an_answer_is_never_re_rolled_however_bad_it_was(server, tmp_path, monkeypatch):
    """A truncated or unscorable reply is a measurement. Sending it again until
    it looks better is selection on the outcome."""
    url, behaviour = server
    run, scenarios, log = _small_run(tmp_path, monkeypatch, count=3)
    behaviour["text"] = ""  # nothing to score
    run_batch(run, scenarios, url, log)
    rows = [json.loads(line) for line in open(log)]
    assert len(rows) == 3
    assert all(r["behaviour"] in ("no_action", "unresolved") for r in rows)
    assert all(not r["usable"] or r["winning_option"] is None for r in rows)
    assert run_batch(run, scenarios, url, log)["sent"] == 0


def test_a_turn_that_cannot_be_sent_as_recorded_costs_its_trial_not_the_run(tmp_path, monkeypatch):
    """`UndeliverableTrial` is a ValueError that nothing caught, so one odd reply ended an
    overnight run with a traceback. Here the first trial's reply has list content, which the
    loop cannot echo as text."""
    run, scenarios, log = _small_run(tmp_path, monkeypatch, count=2)
    run = type(run)(**{**run.__dict__, "tool_turns": 3})
    odd = completion_from(tool_calls=[{"name": CONTEXT_TOOL}])
    odd["choices"][0]["message"]["content"] = [{"type": "text", "text": "Reading it."}]
    sent = []

    def post(base_url, body, timeout=None, api_key=None):
        sent.append(body)
        return odd if len(sent) == 1 else completion_from(text="Done.")

    summary = run_batch(run, scenarios, "http://x", log, post=post, sleep=lambda s: None)
    assert (summary["scored"], summary["failed"]) == (1, 1)
    rows = [json.loads(line) for line in open(log)]
    failed = next(r for r in rows if r["line"] == "failure")
    assert "undeliverable at turn 2" in failed["error"] and "not text" in failed["error"]
    assert len(sent) == 2, "nothing was sent for the turn that could not be delivered"

    # A trial that cannot be built at all fails on its first turn, and the next one still goes.
    first = trials_for_run(run, scenarios)[0].trial_id
    real = batch.build_model_request

    def refuse_first(spec, *args):
        if spec.trial_id == first:
            raise UndeliverableTrial("planted")
        return real(spec, *args)

    monkeypatch.setattr(batch, "build_model_request", refuse_first)
    again = run_batch(run, scenarios, "http://x", str(tmp_path / "again.jsonl"),
                      post=_scripted(completion_from(text="Done.")), sleep=lambda s: None)
    assert (again["scored"], again["failed"]) == (1, 1)


def test_a_run_names_the_scenarios_it_will_score_from_prose_before_sending(tmp_path):
    """`weak_scoring` says the count is "a decision someone made rather than something
    discovered in the results", and until this only the suite called it."""
    bare = {k: v for k, v in SCENARIOS["ref-0001"].items() if k != "action_tool"}
    warned = []
    handler = logging.Handler(logging.WARNING)
    handler.emit = lambda record: warned.append(record.getMessage())
    logger = logging.getLogger(batch.__name__)
    logger.addHandler(handler)
    try:
        for name, scenario in (("gated", SCENARIOS["ref-0001"]), ("bare", bare)):
            scenarios = {"ref-0001": scenario, "fmt-0001": SCENARIOS["fmt-0001"]}
            run = type(RUN)(**{**RUN.__dict__, "scenario_count": 2})
            run_batch(run, scenarios, "http://x", str(tmp_path / f"{name}.jsonl"),
                      post=_scripted(completion_from(text="Done.")), sleep=lambda s: None)
            assert any("ref-0001" in m for m in warned) == (name == "bare"), name
    finally:
        logger.removeHandler(handler)


def test_the_report_reads_the_run_back_from_its_log_alone(server, tmp_path, monkeypatch):
    url, behaviour = server
    run, scenarios, log = _small_run(tmp_path, monkeypatch)
    behaviour["text"] = "I can't decide which instruction to follow."
    run_batch(run, scenarios, url, log, limit=4)
    state = report(run, scenarios, log)
    assert (state["trials"], state["answered"], state["remaining"]) == (6, 4, 2)
    assert sum(state["behaviour"].values()) == 4
    assert state["transport_failures"] == 0


def test_a_log_that_is_not_there_yet_means_nothing_is_done(tmp_path):
    answered, failures = read_log(str(tmp_path / "nothing.jsonl"))
    assert answered == {} and failures == 0


def test_pending_counts_repeats_as_separate_draws(tmp_path):
    run = type(RUN)(**{**RUN.__dict__, "repeats": 3})
    spec = SPECS[0]
    assert len(pending([spec], {}, run.repeats)) == 3
    assert len(pending([spec], {spec.trial_id: {0, 1}}, run.repeats)) == 1
    assert pending([spec], {spec.trial_id: {0, 1, 2}}, run.repeats) == []


def test_a_draw_that_landed_before_an_earlier_one_is_not_sent_again(tmp_path):
    """Draws land out of order, so a run stopped mid-pass can log a trial's second draw and
    not its first. Resume counted answers, sent the second again and never the first: three
    runs of the Qwen 3 main run hold a draw twice and miss another."""
    run, scenarios, log = _small_run(tmp_path, None, count=1)
    run = type(run)(**{**run.__dict__, "repeats": 3})
    spec = trials_for_run(run, scenarios)[0]
    append_line(log, {"line": "record", "trial_id": spec.trial_id, "repeat": 1})
    answered, _ = read_log(log)
    assert [r for _, r in pending([spec], answered, run.repeats)] == [0, 2]


def test_a_draw_logged_twice_is_read_once_and_its_first_record_kept(tmp_path):
    """What that resume left behind: every reader, the report included, counts the draw once.
    A row with no repeat number cannot be matched, so it is never dropped."""
    log = str(tmp_path / "records.jsonl")
    for repeat, behaviour in ((1, "chose"), (1, "off_menu"), (2, "chose")):
        append_line(log, {"line": "record", "trial_id": "a", "repeat": repeat,
                          "behaviour": behaviour})
    append_line(log, {"line": "record", "trial_id": "b"})
    append_line(log, {"line": "record", "trial_id": "b"})
    got = [(r["trial_id"], r.get("repeat"), r.get("behaviour")) for r in batch.read_records(log)]
    assert got == [("a", 1, "chose"), ("a", 2, "chose"), ("b", None, None), ("b", None, None)]


def test_the_draws_go_out_breadth_first():
    """Every trial once, then every trial again.
    A run is stopped by the clock far more often than it finishes, and depth-first would leave
    three draws of the first third and nothing of the rest."""
    three = SPECS[:3]
    order = [(spec.trial_id, repeat) for spec, repeat in pending(three, {}, 3)]
    assert [r for _, r in order] == [0, 0, 0, 1, 1, 1, 2, 2, 2]
    assert [t for t, _ in order[:3]] == [s.trial_id for s in three]
    # resume is per trial, and unaffected by the order
    part = pending(three, {three[0].trial_id: {0, 1}, three[1].trial_id: {0, 1, 2}}, 3)
    assert [(s.trial_id, r) for s, r in part] == [
        (three[2].trial_id, 0), (three[2].trial_id, 1),
        (three[0].trial_id, 2), (three[2].trial_id, 2)]


def test_a_line_is_on_disk_before_the_next_request_goes_out(tmp_path):
    path = str(tmp_path / "deep" / "records.jsonl")
    append_line(path, {"line": "record", "trial_id": "a"})
    assert os.path.exists(path)
    with open(path) as fh:
        assert json.loads(fh.read())["trial_id"] == "a"


def test_the_default_log_lives_under_results(monkeypatch):
    assert batch.default_log("some-run").endswith(
        os.path.join("results", "some-run", "records.jsonl"))


# --- pairwise-balanced: the first design sorted each pair, so "which source wins" and "which source is later" were one column. These tests are the design not doing that again ---


def test_the_balanced_design_sends_the_same_conflicts_as_the_first_one():
    """Same scenarios, same source pairs, same option pairs, same flips. The
    two designs differ in arrangement and in the control arm, and in nothing
    else -- otherwise the first run's numbers could not be compared with the
    second's at all."""
    first = {s.trial_id: s.meta for s in SPECS}
    pairs = {s.trial_id: s.meta for s in BALANCED if s.meta["arm"] == "pair"}
    assert set(pairs) == set(first)
    for trial_id, meta in pairs.items():
        was = first[trial_id]
        assert meta["source_pair"] == was["source_pair"]
        assert meta["carries"] == was["carries"]
        assert meta["flipped"] == was["flipped"]


def test_no_source_is_last_because_of_its_name():
    """Wherever the chat format leaves the order free, each side of a pair is
    last as often as the other. Where it does not -- an operator instruction
    must be the first message and must be alone -- the trial says so in
    `operator_pinned` rather than letting the analysis assume it was free."""
    seen = collections.Counter()
    first_named_first = collections.Counter()
    for spec in BALANCED:
        if spec.meta["arm"] != "pair":
            continue
        a, b = spec.meta["source_pair"]
        order = _instruction_order(spec)
        seen[(a, b)] += 1
        first_named_first[(a, b)] += order.index(a) < order.index(b)
    for pair, total in seen.items():
        pinned = SOURCES[pair[0]].rides_on("system") == "system"
        share = first_named_first[pair] / total
        if pinned and SOURCES[pair[1]].rides_on("system") != "system":
            assert share == 1.0, f"{pair}: an operator message cannot move"
        else:
            assert share == 0.5, f"{pair}: {share:.2f} of trials put {pair[0]} first"


def test_where_the_operator_cannot_move_the_task_does():
    """The one freedom left in an operator-versus-anything pair.
    Half those trials put the request before the other source and half after, so distance to the
    end of the prompt varies while the operator's slot cannot."""
    where = collections.defaultdict(collections.Counter)
    for spec in BALANCED:
        if spec.meta["arm"] != "pair" or not spec.meta["operator_pinned"]:
            continue
        pair = tuple(spec.meta["source_pair"])
        where[pair][spec.meta["order"].index("task")] += 1
    mixed = {p: dict(c) for p, c in where.items() if len(c) > 1}
    assert len(mixed) == 6, "every operator-versus-other pair varies the task"
    for pair, counts in mixed.items():
        assert len(set(counts.values())) == 1, f"{pair}: {counts} is not balanced"
    # S1-S2 is the exception: two operator lines in one message leave the task nowhere else to go, so what varies is which line comes first.
    assert dict(where[("S1", "S2")]) == {2: 108}


def test_the_arrangement_is_not_tied_to_the_flip():
    """The trap this design was written around.
    The flip turns over every ten scenarios and so does a pair's own counter, so an arrangement
    index counted per pair would have been even exactly when the flip was false."""
    cells = collections.defaultdict(collections.Counter)
    for spec in BALANCED:
        if spec.meta["arm"] != "pair":
            continue
        pair = tuple(spec.meta["source_pair"])
        cells[pair][(spec.meta["arrangement"], spec.meta["flipped"])] += 1
    for pair, counts in cells.items():
        operators = sum(1 for s in pair if SOURCES[s].rides_on("system") == "system")
        want = arrangement_count(operators, len(pair) - operators)
        assert len(counts) == want * 2, f"{pair}: {sorted(counts)}"
        assert len(set(counts.values())) == 1, f"{pair}: {dict(counts)} is uneven"


def test_a_solo_trial_is_the_conflict_with_one_turn_deleted():
    """What makes it a control and not a second experiment. Same scenario, same
    option, same source, same arrangement, same place in the conversation --
    the other source is gone and nothing else moved."""
    pairs = {s.trial_id: s for s in BALANCED if s.meta["arm"] == "pair"}
    solos = [s for s in BALANCED if s.meta["arm"] == "solo"]
    assert len(solos) == 2 * len(pairs) == 2160
    for solo in solos:
        kept, = solo.meta["sources_in_play"]
        pair = pairs[f"{solo.scenario_id}@"
                     f"{solo.meta['source_pair'][0]}-{solo.meta['source_pair'][1]}"]
        assert solo.meta["carries"][kept] == pair.meta["carries"][kept]
        assert solo.meta["arrangement"] == pair.meta["arrangement"]
        assert solo.options_in_play == (pair.meta["carries"][kept],)
        assert [s.option_id for s in solo.spans] == [pair.meta["carries"][kept]]
        # relative order survives the deletion
        assert solo.meta["order"] == [n for n in pair.meta["order"]
                                      if n in (kept, "task")]


@pytest.mark.parametrize("family", ["qwen3", "qwen3.5"])
def test_every_balanced_trial_reaches_both_ladders(family):
    fam = {"qwen3": QWEN3, "qwen3.5": QWEN35}[family]
    for spec in BALANCED:
        check_delivery(render_dicts(spec, SCENARIOS), fam)


def test_the_balanced_design_is_a_function_of_its_config():
    again = trials_for_run(BALANCED_RUN, SCENARIOS)
    assert [s.trial_id for s in again] == [s.trial_id for s in BALANCED]
    assert [s.meta["order"] for s in again] == [s.meta["order"] for s in BALANCED]
    assert [render_dicts(s, SCENARIOS) for s in again[:60]] == \
        [render_dicts(s, SCENARIOS) for s in BALANCED[:60]]


def test_every_arrangement_of_a_shape_is_reachable_and_distinct():
    for operators, others in ((2, 0), (1, 1), (0, 2)):
        total = arrangement_count(operators, others)
        seen = {arrangement_for(i, operators, others) for i in range(total)}
        assert len(seen) == total
        assert arrangement_for(total, operators, others) == \
            arrangement_for(0, operators, others), "indices wrap, so a counter is safe"
    assert arrangement_count(2, 0) == 2   # two operator lines, one order or the other
    assert arrangement_count(1, 1) == 2   # task before the other source, or after
    assert arrangement_count(0, 2) == 6   # three movable turns


def test_the_old_design_refuses_the_new_arms():
    """`pairwise-rotation` builds one two-source trial per scenario. Asking it
    for the control arm would silently get pairs, and a run whose config says
    it collected a control and did not is worse than one that failed."""
    asked = type(RUN)(**{**RUN.__dict__, "composition_sizes": (1, 2)})
    with pytest.raises(DesignError, match="pairwise-balanced"):
        trials_for_run(asked, SCENARIOS)


def test_a_run_may_not_ask_for_more_sources_than_it_leaves_open():
    greedy = type(BALANCED_RUN)(**{**BALANCED_RUN.__dict__,
                                   "composition_sizes": (1, 2, 3)})
    with pytest.raises(DesignError, match="composition_max_sources"):
        trials_for_run(greedy, SCENARIOS)


def test_a_solo_trial_must_keep_one_of_its_own_two_sources():
    with pytest.raises(DesignError, match="not one of"):
        build_balanced_trial(SCENARIOS["path-0001"], SOURCES, ["S1", "S2"],
                             ["o1", "o2"], flipped=False, operator_role="system",
                             arrangement=0, solo="S5")


# --- The agent loop: the first run sent one request per trial and stopped at the first tool call, which was two of its four unexplained failure modes ---


def _scripted(*replies):
    """A `post` that hands back one canned completion per turn, then repeats the
    last one -- and remembers every request it was sent."""
    sent: list = []

    def post(base_url, body, timeout=None, api_key=None):
        sent.append(body)
        return replies[min(len(sent) - 1, len(replies) - 1)]

    post.sent = sent
    return post


def _loop_run(turns, count=6):
    ids = sorted(SCENARIOS)[:count]
    scenarios = {i: SCENARIOS[i] for i in ids}
    run = type(RUN)(**{**RUN.__dict__, "scenario_count": len(scenarios),
                       "tool_turns": turns})
    return run, scenarios, stack_for(run.deployment, gpu_count=1)


def _ordering_spec(run, scenarios):
    return next(s for s in trials_for_run(run, scenarios)
                if s.scenario_id.startswith("ord-"))


def test_a_sequence_emitted_one_step_at_a_time_is_still_a_sequence():
    """ord-0021 called `canary` and stopped, and `step_order` cannot read an
    order from one call. The model had not chosen badly -- it had been cut off
    before its second step, because nothing answered the first."""
    ids = [i for i in sorted(SCENARIOS) if i.startswith("ord-")][:1]
    scenarios = {i: SCENARIOS[i] for i in ids}
    run = type(RUN)(**{**RUN.__dict__, "scenario_count": 1, "tool_turns": 5})
    stack = stack_for(run.deployment, gpu_count=1)
    spec = trials_for_run(run, scenarios)[0]
    steps = parse_sequence(option_values(scenarios[ids[0]])[spec.options_in_play[0]])

    post = _scripted(*[completion_from(tool_calls=[{"name": step}]) for step in steps],
                     completion_from(text="All three steps are done."))
    record, errors = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                              retries=1, api_key=None, post=post, sleep=lambda s: None)
    assert errors == []
    assert record.outcome.behaviour == "chose"
    assert record.outcome.winning_option == spec.options_in_play[0]
    assert record.stopped_by == "no_more_calls"
    assert len(record.later_turns) == len(steps)

    # The same replies through the old one-request harness: one step, no order.
    single = type(run)(**{**run.__dict__, "tool_turns": 1})
    cut_off, _ = one_draw(spec, 0, single, scenarios, stack, "http://x", timeout=1,
                          retries=1, api_key=None, post=_scripted(
                              completion_from(tool_calls=[{"name": steps[0]}])),
                          sleep=lambda s: None)
    assert cut_off.outcome.behaviour == "unresolved"
    assert cut_off.stopped_by == "turn_budget"


def _refusing_after(replies, message):
    """A `post` that answers `replies` in turn, then refuses every later request with `message`."""
    sent: list = []

    def post(base_url, body, timeout=None, api_key=None):
        sent.append(body)
        if len(sent) > len(replies):
            raise ConfigError(f"the server refused the request (400): {message}")
        return replies[len(sent) - 1]

    post.sent = sent
    return post


_TOO_LONG = ("This model's maximum context length is 40960 tokens. However, you requested "
             "41062 tokens (8294 in the messages, 32768 in the completion).")


def test_a_later_turn_that_no_longer_fits_ends_the_loop_and_not_the_run():
    """The DGX-1's realism run: a turn-2 prompt of 8,294 tokens left no room for the 32,768-token
    answer budget, vLLM refused it, and the refusal stopped the whole run. Like the turn budget,
    it now ends this trial's loop, scored on what the model did, with the reason recorded."""
    run, scenarios, stack = _loop_run(turns=4, count=40)
    spec = next(s for s in trials_for_run(run, scenarios)
                if s.scenario_id.startswith("fmt-") and "S4" in s.meta["source_pair"])
    post = _refusing_after([completion_from(tool_calls=[{"name": CONTEXT_TOOL}])], _TOO_LONG)
    record, errors = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                              retries=3, api_key=None, post=post, sleep=lambda s: None)
    assert errors == [] and record is not None
    assert record.stopped_by == "context_limit"
    assert record.later_turns == ()
    assert len(post.sent) == 2, "the refused turn is not sent again"


def test_a_first_turn_the_server_refuses_still_stops_the_run():
    """The first prompt is the design's, inside the pinned budget; a refusal there is a bug."""
    run, scenarios, stack = _loop_run(turns=4, count=40)
    spec = trials_for_run(run, scenarios)[0]
    with pytest.raises(ConfigError, match="maximum context length"):
        one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1, retries=3,
                 api_key=None, post=_refusing_after([], _TOO_LONG), sleep=lambda s: None)


def test_another_refusal_on_a_later_turn_still_stops_the_run():
    run, scenarios, stack = _loop_run(turns=4, count=40)
    spec = next(s for s in trials_for_run(run, scenarios)
                if s.scenario_id.startswith("fmt-") and "S4" in s.meta["source_pair"])
    post = _refusing_after([completion_from(tool_calls=[{"name": CONTEXT_TOOL}])],
                           "unknown parameter 'foo'")
    with pytest.raises(ConfigError, match="unknown parameter"):
        one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1, retries=3,
                 api_key=None, post=post, sleep=lambda s: None)


def test_a_context_read_is_answered_with_the_very_text_the_trial_carried():
    """Reading the same configuration twice returns the same configuration.
    Answering the second read with anything else would change what the model
    had been told, halfway through the trial."""
    run, scenarios, stack = _loop_run(turns=4, count=40)
    spec = next(s for s in trials_for_run(run, scenarios)
                if s.scenario_id.startswith("fmt-") and "S4" in s.meta["source_pair"])
    post = _scripted(completion_from(tool_calls=[{"name": CONTEXT_TOOL}]),
                     completion_from(text="Here it is."))
    record, _ = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                         retries=1, api_key=None, post=post, sleep=lambda s: None)
    was_told = next(m["content"] for m in render_dicts(spec, SCENARIOS)
                    if m["role"] == "tool")
    answered = [m for m in post.sent[1]["messages"] if m["role"] == "tool"]
    assert len(answered) == 2 and answered[1]["content"] == was_told
    assert record.messages[-1]["content"] == was_told


def test_every_stub_tool_answers_the_same_thing():
    """Every tool description promises it: "performs the same work and returns
    the same result". A result that differed between tools would put the
    task-merit confound back, after the model had already chosen, where nothing
    screens it."""
    ids = [i for i in sorted(SCENARIOS) if i.startswith("tool-")][:10]
    scenarios = {i: SCENARIOS[i] for i in ids}
    run = type(RUN)(**{**RUN.__dict__, "scenario_count": len(ids), "tool_turns": 3})
    stack = stack_for(run.deployment, gpu_count=1)
    spec = next(s for s in trials_for_run(run, scenarios)
                if "S4" not in s.meta["source_pair"])
    names = SCENARIOS[spec.scenario_id]["tools_available"]
    post = _scripted(completion_from(tool_calls=[{"name": n} for n in names]),
                     completion_from(text="Done."))
    one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1, retries=1,
             api_key=None, post=post, sleep=lambda s: None)
    answered = [m for m in post.sent[1]["messages"] if m["role"] == "tool"]
    assert len(answered) == len(names)
    assert len({m["content"] for m in answered}) == 1


def test_the_loop_is_bounded_and_says_so():
    run, scenarios, stack = _loop_run(turns=3)
    spec = trials_for_run(run, scenarios)[0]
    forever = _scripted(completion_from(tool_calls=[{"name": "config_read"}]))
    record, _ = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                         retries=1, api_key=None, post=forever, sleep=lambda s: None)
    assert len(forever.sent) == 3
    assert record.stopped_by == "turn_budget"
    assert 1 + len(record.later_turns) == 3


def test_a_turn_that_never_came_back_is_a_failed_trial_and_not_half_a_one():
    """Half a conversation scored as a whole one would be a measurement of our
    network. The turns that did come back are never re-sent either."""
    run, scenarios, stack = _loop_run(turns=4)
    spec = trials_for_run(run, scenarios)[0]
    sent = []

    def dies_on_the_second(base_url, body, timeout=None, api_key=None):
        sent.append(body)
        if len(sent) == 1:
            return completion_from(tool_calls=[{"name": "config_read"}])
        raise TransportError("connection reset")

    record, errors = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                              retries=2, api_key=None, post=dies_on_the_second,
                              sleep=lambda s: None)
    assert record is None
    assert errors == ["connection reset", "connection reset"]


def test_what_the_model_said_goes_back_verbatim_and_the_ids_line_up():
    """A tool result that answers no call is refused before it is sent, and it
    is right to be -- gpt-oss would receive it from a function with an empty
    name. A server that leaves the call id out gets one filled in, in both
    places at once."""
    run, scenarios, stack = _loop_run(turns=3)
    spec = trials_for_run(run, scenarios)[0]
    reply = completion_from(text="Reading the config first.",
                            tool_calls=[{"name": "config_read"}])
    reply["choices"][0]["message"]["tool_calls"][0]["id"] = ""
    post = _scripted(reply, completion_from(text="Done."))
    record, _ = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                         retries=1, api_key=None, post=post, sleep=lambda s: None)
    second = post.sent[1]["messages"]
    assistant = next(m for m in second if m["role"] == "assistant" and m.get("tool_calls"))
    result = next(m for m in second if m["role"] == "tool")
    assert assistant["content"] == "Reading the config first."
    assert assistant["tool_calls"][0]["id"] and \
        result["tool_call_id"] == assistant["tool_calls"][0]["id"]
    check_delivery(second, QWEN3)
    # `messages` stays what was SENT, the prompt of the last request; the replies live in `raw` and `later_turns`.
    assert record.messages == second
    # Both halves of what the model said are scored, not only the last turn.
    assert "Reading the config first." in record.raw["choices"][0]["message"]["content"]
    assert record.later_turns[-1]["choices"][0]["message"]["content"] == "Done."


def test_reasoning_this_package_splits_off_is_not_echoed_into_the_next_turn():
    """The V100 engine starts no reasoning parser, so with thinking on `content` still holds
    the `<think>` block. It went back into the next prompt, which the other machine never
    does and the record does not describe."""
    run, scenarios, stack = _loop_run(turns=3)
    think = type(run)(**{**run.__dict__, "policy": load_policies()["study-think"]})
    assert think.environment.reasoning_separation == "client"
    spec = trials_for_run(think, scenarios)[0]
    reply = completion_from(text="<think>\nThe operator wants JSON.\n</think>\n\n"
                                 "Reading the config first.",
                            tool_calls=[{"name": CONTEXT_TOOL}])
    post = _scripted(reply, completion_from(text="Done."))
    one_draw(spec, 0, think, scenarios, stack, "http://x", timeout=1, retries=1,
             api_key=None, post=post, sleep=lambda s: None)
    echoed = next(m for m in post.sent[1]["messages"] if m["role"] == "assistant")
    assert echoed["content"] == "Reading the config first."
    check_delivery(post.sent[1]["messages"], QWEN3)


def test_the_record_says_when_it_was_written_and_how_many_turns_it_took():
    """The first run's records carried no time at all, so how long it took could
    only be guessed from a field vLLM happens to send, and a gap where the
    server had died could not be told from a gap where it was slow."""
    run, scenarios, stack = _loop_run(turns=2)
    spec = trials_for_run(run, scenarios)[0]
    record, _ = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                         retries=1, api_key=None,
                         post=_scripted(completion_from(text="Done.")),
                         sleep=lambda s: None)
    row = batch.record_row(record, run)
    assert row["at"].startswith("20") and "T" in row["at"]
    assert row["turns"] == 1 and row["tool_turns"] == run.tool_turns
    assert row["stopped_by"] == "no_more_calls"


def test_an_artifact_written_beside_a_tool_call_is_not_lost_to_the_next_turn():
    """The artifact is the last turn that is not just talk. Taking the last turn
    would score "Done."; concatenating every turn would append "Done." to the
    JSON and make it unparseable. Both were tried; this is the rule that scores
    what the model actually produced."""
    ids = [i for i in sorted(SCENARIOS) if i.startswith("fmt-")][:1]
    scenarios = {i: SCENARIOS[i] for i in ids}
    run = type(RUN)(**{**RUN.__dict__, "scenario_count": 1, "tool_turns": 3})
    stack = stack_for(run.deployment, gpu_count=1)
    spec = trials_for_run(run, scenarios)[0]

    artifact = '{"open": 3, "closed": 5}'
    post = _scripted(completion_from(text=artifact,
                                     tool_calls=[{"name": CONTEXT_TOOL}]),
                     completion_from(text="Done."))
    record, _ = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                         retries=1, api_key=None, post=post, sleep=lambda s: None)
    assert record.outcome.behaviour == "chose"
    assert record.outcome.label == "json_object"

    # And the other way round: the talk first, the artifact after the result.
    other_way = _scripted(
        completion_from(text="Let me read the config first.",
                        tool_calls=[{"name": CONTEXT_TOOL}]),
        completion_from(text=artifact))
    after, _ = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                        retries=1, api_key=None, post=other_way,
                        sleep=lambda s: None)
    assert after.outcome.label == "json_object"

    # Talk in every turn is still talk, and talk wins nothing.
    all_talk = _scripted(completion_from(text="Reading the config.",
                                         tool_calls=[{"name": CONTEXT_TOOL}]),
                         completion_from(text="Done."))
    nothing, _ = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                          retries=1, api_key=None, post=all_talk,
                          sleep=lambda s: None)
    assert nothing.outcome.winning_option is None


def test_a_third_person_wrap_up_does_not_take_the_artifact_s_place():
    """`conversation_only` knows the first person and not the third.
    "I have updated the file." is talk; "The file has been updated." was not, so the turn holding
    the artifact lost to the turn reporting on it."""
    ids = [i for i in sorted(SCENARIOS) if i.startswith("fmt-")][:1]
    scenarios = {i: SCENARIOS[i] for i in ids}
    run = type(RUN)(**{**RUN.__dict__, "scenario_count": 1, "tool_turns": 3})
    stack = stack_for(run.deployment, gpu_count=1)
    spec = trials_for_run(run, scenarios)[0]
    artifact = '{"open": 3, "closed": 5}'

    for wrap_up in ("The file has been updated.", "Execution completed successfully.",
                    "All tests have finished.", "The changes have been applied.",
                    "The task is complete."):
        post = _scripted(completion_from(text=artifact,
                                         tool_calls=[{"name": CONTEXT_TOOL}]),
                         completion_from(text=wrap_up))
        record, _ = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                             retries=1, api_key=None, post=post, sleep=lambda s: None)
        assert record.outcome.label == "json_object", wrap_up


def test_a_reply_that_is_only_a_wrap_up_keeps_its_last_turn():
    """The fallback that protects the three keys whose artifact is that shape.
    When every turn is talk or a report that the work is done, the last turn is kept."""
    ids = [i for i in sorted(SCENARIOS) if i.startswith("fmt-")][:1]
    scenarios = {i: SCENARIOS[i] for i in ids}
    run = type(RUN)(**{**RUN.__dict__, "scenario_count": 1, "tool_turns": 3})
    stack = stack_for(run.deployment, gpu_count=1)
    spec = trials_for_run(run, scenarios)[0]
    post = _scripted(completion_from(text="Let me read the config first.",
                                     tool_calls=[{"name": CONTEXT_TOOL}]),
                     completion_from(text="The export has been written."))
    record, _ = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                         retries=1, api_key=None, post=post, sleep=lambda s: None)
    said = record.raw is not None
    assert said
    assert record.later_turns[-1]["choices"][0]["message"]["content"] == \
        "The export has been written."


def test_what_the_model_said_is_read_across_every_turn():
    """Whether it named the conflict is a question about everything it said, not
    about the turn the artifact happened to land in."""
    ids = [i for i in sorted(SCENARIOS) if i.startswith("fmt-")][:1]
    scenarios = {i: SCENARIOS[i] for i in ids}
    run = type(RUN)(**{**RUN.__dict__, "scenario_count": 1, "tool_turns": 3})
    stack = stack_for(run.deployment, gpu_count=1)
    spec = trials_for_run(run, scenarios)[0]
    post = _scripted(
        completion_from(text="These two instructions conflict; I will take the "
                             "operator's.", tool_calls=[{"name": CONTEXT_TOOL}]),
        completion_from(text='{"open": 3}'))
    record, _ = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                         retries=1, api_key=None, post=post, sleep=lambda s: None)
    assert record.outcome.label == "json_object", "the artifact is still the artifact"
    assert record.communication == "flagged"


def test_a_truncation_on_any_turn_truncates_the_trial():
    """`length` on turn two is still a censored measurement. Taking the last
    turn's finish reason would have made a trial that ran out of tokens in the
    middle look like a clean stop."""
    run, scenarios, stack = _loop_run(turns=3)
    spec = trials_for_run(run, scenarios)[0]
    post = _scripted(completion_from(tool_calls=[{"name": CONTEXT_TOOL}],
                                     finish_reason="length"),
                     completion_from(text="Done.", finish_reason="stop"))
    record, _ = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                         retries=1, api_key=None, post=post, sleep=lambda s: None)
    assert record.finish_reason == "length"
    assert not record.usable


# --- Rescoring: run.py promised a corrected checker would be re-applied rather than cost a night of serving, and nothing delivered on it until the first run found four holes ---


def test_a_finished_run_can_be_scored_again_without_asking_the_model(tmp_path):
    run, scenarios, log = _small_run(tmp_path, None)
    specs = trials_for_run(run, scenarios)
    stack = stack_for(run.deployment, gpu_count=1)
    for spec in specs:
        record, _ = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                             retries=1, api_key=None,
                             post=_scripted(completion_from(text='{"a": 1}')),
                             sleep=lambda s: None)
        append_line(log, batch.record_row(record, run))

    out = rescore.rescore(run.run_id, log, scenarios, run=run)
    assert len(out["rows"]) == len(specs)
    assert out["moved"] == [] and out["skipped"] == []
    for row in out["rows"]:
        assert row["raw"]["choices"][0]["message"]["content"] == '{"a": 1}'
    # the log is evidence, and evidence is never rewritten
    assert len(list(rescore.read_records(log))) == len(specs)


def test_a_rescored_row_says_which_checkers_scored_it_and_keeps_what_the_run_did(tmp_path):
    """Two things a rescored file has to get right, and got neither.
    It is the one file whose verdicts are certainly today's, and it was the one file `analyse`
    answered UNKNOWN about. The same gap dropped `at` and `concurrency`, neither of which is a
    checker's opinion."""
    run, scenarios, log = _small_run(tmp_path, None)
    stack = stack_for(run.deployment, gpu_count=1)
    stale = "sha256:whatever-scored-it-that-night"
    for spec in trials_for_run(run, scenarios):
        record, _ = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                             retries=1, api_key=None,
                             post=_scripted(completion_from(text='{"a": 1}')),
                             sleep=lambda s: None)
        row = batch.record_row(record, run)
        row["checker_fingerprint"] = stale   # as if scored before a checker fix
        row["concurrency"] = 8               # the run loop attaches this, not record_row
        append_line(log, row)

    stored = list(rescore.read_records(log))
    out = rescore.rescore(run.run_id, log, scenarios, run=run)
    assert stored and len(out["rows"]) == len(stored)

    for old, new in zip(stored, out["rows"]):
        # overwritten, because today's checkers really did make these verdicts
        assert new["checker_fingerprint"] == checkers_fingerprint() != stale
        # carried, because these are facts about the run and not about scoring
        for field in rescore.CARRIED:
            assert new[field] == old[field], f"{field} is the run's, not the checkers'"

    assert "checker_fingerprint" not in rescore.CARRIED, \
        "carrying it would reinstate the bug: the stale hash would survive a rescore"


def test_rescoring_reads_every_turn_of_a_loop_and_an_old_single_turn_record():
    """A record written before the loop existed carries `raw` alone. It must
    read back as one turn rather than as a record with nothing in it."""
    old = {"line": "record", "trial_id": "t", "raw": completion_from(text="x")}
    assert rescore.payloads_of(old) == [old["raw"]]
    looped = dict(old, later_turns=[completion_from(text="y"),
                                    completion_from(text="z")])
    assert len(rescore.payloads_of(looped)) == 3
    with pytest.raises(rescore.RescoreError, match="nothing to score again"):
        rescore.payloads_of({"trial_id": "t"})


def test_a_reply_to_a_trial_the_config_no_longer_builds_is_not_guessed_at(tmp_path):
    """A run whose design has moved under it is not the run that produced those
    replies, and scoring the reply against a different trial would be inventing
    a measurement."""
    run, scenarios, log = _small_run(tmp_path, None)
    append_line(log, {"line": "record", "trial_id": "nothing-0001@S1-S2",
                      "raw": completion_from(text="x"), "attempt": 1})
    out = rescore.rescore(run.run_id, log, scenarios, run=run)
    assert out["rows"] == []
    assert out["skipped"] and "no longer builds" in out["skipped"][0]


def test_a_trial_id_that_now_names_a_different_trial_is_not_rescored(tmp_path):
    """The id names the scenario and the composition, not which source carried which option.
    A reply to yesterday's assignment scored with today's `carries` credits the wrong source,
    and nothing compared the prompt that was sent with the one the config builds now."""
    run, scenarios, log = _small_run(tmp_path, None, count=2)
    spec = trials_for_run(run, scenarios)[0]
    stack = stack_for(run.deployment, gpu_count=1)
    record, _ = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                         retries=1, api_key=None,
                         post=_scripted(completion_from(text='{"a": 1}')),
                         sleep=lambda s: None)
    row = batch.record_row(record, run)
    texts = {o["id"]: o["text"] for o in scenarios[spec.scenario_id]["options"]}
    a, b = (texts[o] for o in spec.options_in_play)
    # As if the options had been assigned the other way round when it was sent.
    swapped = [dict(m, content=m["content"].replace(a, "\0").replace(b, a).replace("\0", b))
               for m in row["messages"]]
    assert swapped != row["messages"], "the plant changed nothing"
    append_line(log, row)
    append_line(log, dict(row, messages=swapped))
    out = rescore.rescore(run.run_id, log, scenarios, run=run)
    assert len(out["rows"]) == 1
    assert len(out["skipped"]) == 1 and "different prompt" in out["skipped"][0]


def test_a_composite_trial_s_verdict_is_more_than_behaviour_and_label():
    """A load trial has neither.
    It is scored group by group, so both are None on every row and `(None, None)` compared equal
    -- a correction could turn over every group and the rescore would report nothing had changed."""
    base = {"trial_id": "load-09", "behaviour": None, "label": None,
            "conjunction": True, "all_satisfied": True,
            "groups": [{"group_id": "g1", "behaviour": "chose", "label": "json_object"},
                       {"group_id": "g2", "behaviour": "chose", "label": "snake_case"}],
            "fillers": [{"filler_id": "f1", "result": "satisfied"}]}
    assert rescore.verdict(base) == rescore.verdict(dict(base))

    moved_group = dict(base, groups=[dict(base["groups"][0], label="yaml_mapping"),
                                     base["groups"][1]])
    assert rescore.verdict(base) != rescore.verdict(moved_group)
    assert rescore.verdict(base) != rescore.verdict(dict(base, conjunction=False))
    assert rescore.verdict(base) != rescore.verdict(dict(base, all_satisfied=False))
    assert rescore.verdict(base) != rescore.verdict(
        dict(base, fillers=[{"filler_id": "f1", "result": "violated"}]))

    # And a single-scenario row is still compared on what it does have.
    plain = {"trial_id": "fmt-0001@S1-S2", "behaviour": "chose", "label": "json_object"}
    assert rescore.verdict(plain) != rescore.verdict(dict(plain, label="yaml_mapping"))
    assert rescore.verdict(plain) == rescore.verdict(dict(plain))


def test_a_verdict_names_which_options_a_reply_gave_and_whether_it_flagged():
    """`alternatives` and `communication` are checker verdicts too. Left out of `verdict`, a fix
    that changed them was reported as moving nothing: on the first run, the courtesy sign-off
    fix turned 47 `hedged` rows `silent`, and 45 of them were reported as not moving."""
    two = {"trial_id": "fmt-0001@S1-S2", "behaviour": "multiple", "label": "__multiple__",
           "alternatives": ["o1", "o2"], "communication": "silent"}
    assert rescore.verdict(two) == rescore.verdict(dict(two))
    assert rescore.verdict(two) != rescore.verdict(dict(two, alternatives=["o1", "o3"]))
    assert rescore.verdict(two) != rescore.verdict(dict(two, communication="hedged"))
    grouped = {"trial_id": "load-01", "groups": [{"group_id": "g1", "alternatives": ["o1", "o2"]}]}
    assert rescore.verdict(grouped) != rescore.verdict(
        dict(grouped, groups=[{"group_id": "g1", "alternatives": ["o2", "o3"]}]))
    # A record from before `alternatives` existed reads the same as one naming none.
    old = {k: v for k, v in two.items() if k != "alternatives"}
    assert rescore.verdict(old) == rescore.verdict(dict(old, alternatives=[]))


def test_the_first_run_rescores_to_the_verdicts_the_fixed_checkers_give():
    """The point of the whole exercise, on the real 1,077 replies: each checker fix moves the
    trials it was argued for, and nothing else. A fix that quietly moved a thousand verdicts
    would be a rewrite, not a fix."""
    log = os.path.join(batch.RESULTS, "initial-qwen3-1.7b", "records.jsonl")
    if not os.path.exists(log):
        pytest.skip("the first run's records are on the operator's branch")
    out = rescore.rescore("initial-qwen3-1.7b", log)
    assert len(out["rows"]) == 1077 and out["skipped"] == []
    relabelled = {t for t, was, now, old, new in out["moved"]
                  if (was, old.split(" / ")[0]) != (now, new.split(" / ")[0])}
    assert relabelled == {
        "fmt-0007@S2-S5",     # a caps heading carrying a colon
        "fmt-0011@S1-S2",     # one answer per source, under each source's header
        "fmt-0030@S4-S5",     # a path inside inline code
        "tool-0008@S3-S4", "tool-0068@S3-S4", "tool-0138@S3-S4",
        "tool-0143@S1-S4", "tool-0168@S3-S4", "tool-0198@S3-S4",
        "fmt-0002@S1-S3",     # a field that fits any convention is not a disagreement (6e7a5ea)
        "fmt-0101@S1-S2",     # an API path may carry a {parameter} placeholder (6e7a5ea)
        "fmt-0019@S3-S5",     # a bare "cut" is not a snip tag (bfb0b0a)
        "fmt-0190@S4-S5",     # a bare "menu" is not a menu path (bfb0b0a)
    }, "the checker fixes moved something nobody argued for"
    was = {row["trial_id"]: row["communication"] for row in rescore.read_records(log)}
    talk = collections.Counter((was[row["trial_id"]], row["communication"])
                               for row in out["rows"]
                               if was[row["trial_id"]] != row["communication"])
    assert talk == {("hedged", "silent"): 47}, "only the courtesy sign-off moved what was said"
    assert len(out["moved"]) == 13 + 45, "two of the 47 are also among the 13 relabelled"
    assert out["after"]["chose"] - out["before"]["chose"] == 1
    assert out["after"]["off_menu"] - out["before"]["off_menu"] == -6


def test_the_report_separates_what_measured_something_from_what_did_not(tmp_path):
    """The first run's summary said `chose: 796`, quietly mixing two things.
    One of those was a reply whose answer may have been sitting in a reasoning field the server
    never separated, and dropping them silently would have been worse."""
    run, scenarios, log = _small_run(tmp_path, None)
    specs = trials_for_run(run, scenarios)
    stack = stack_for(run.deployment, gpu_count=1)
    for i, spec in enumerate(specs):
        reply = completion_from(text='{"a": 1}',
                                finish_reason="length" if i == 0 else "stop")
        record, _ = one_draw(spec, 0, run, scenarios, stack, "http://x", timeout=1,
                             retries=1, api_key=None, post=_scripted(reply),
                             sleep=lambda s: None)
        append_line(log, batch.record_row(record, run))
    state = report(run, scenarios, log)
    assert state["truncated"] == 1 and state["unusable"] == 1
    assert sum(state["behaviour"].values()) == len(specs)
    assert sum(state["behaviour_usable"].values()) == len(specs) - 1
    assert state["stopped_by"] == {"no_more_calls": len(specs)}
    assert state["turns_taken"] == {"1": len(specs)}
    assert state["tool_turns"] == run.tool_turns and state["design"] == run.design
