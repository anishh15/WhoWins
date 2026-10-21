"""The three layout designs, the realism validator and the reader that pairs layouts in an item.
Each design must send every item under each of its layouts with the same options, put the moved
thing where its meta says, and reach a model only where its template takes it as written."""

from __future__ import annotations

import collections
import copy
import json
import os
import random

import pytest

from whowins.runner import layouts
from whowins.runner.design import DesignError, load_sources
from whowins.runner.rendering import render_dicts
from whowins.runner.serving import (UndeliverableTrial, check_delivery, late_operator_possible,
                                load_roster)
from whowins.runner.spec import Block, Span, Task, TrialSpec
from whowins.runner.trials import load_scenarios
from whowins.stats import layouts as reader
from whowins.validation import check_realism

SCENARIOS = load_scenarios()
SOURCES = load_sources()
FAMILIES = {m.family.name: m.family for m in load_roster().values()}
OPERATOR = layouts.operator_trials(list(SCENARIOS.values()), SOURCES, "system", True)
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "realism")


@pytest.fixture
def fixture_batch(monkeypatch):
    monkeypatch.setattr(check_realism, "REALISM_DIR", FIXTURE)
    with open(os.path.join(FIXTURE, "rs-01.json"), encoding="utf-8") as fh:
        return json.load(fh)


# --- The operator test ---


def test_every_scenario_meets_one_operator_pair_under_four_layouts_with_the_same_options():
    by_item = collections.defaultdict(list)
    for spec in OPERATOR:
        by_item[spec.scenario_id].append(spec)
    assert len(OPERATOR) == 4 * 1080 and len(by_item) == 1080
    for specs in by_item.values():
        layouts_seen = {(s.meta["layout"]["role"], s.meta["layout"]["operator_position"]) for s in specs}
        assert layouts_seen == {("real", "first"), ("real", "last"), ("label", "first"), ("label", "last")}
        assert len({json.dumps(s.meta["carries"], sort_keys=True) for s in specs}) == 1
    pairs = collections.Counter(tuple(s.meta["composition"]) for s in OPERATOR)
    assert set(pairs) == set(layouts.OPERATOR_PAIRS) and max(pairs.values()) - min(pairs.values()) <= 4 * 6


def test_every_family_meets_every_operator_pair_and_every_option_pair_turns_up():
    seen = collections.defaultdict(set)
    options = collections.defaultdict(set)
    for spec in OPERATOR:
        seen[SCENARIOS[spec.scenario_id]["family"]].add(tuple(spec.meta["composition"]))
        if len(SCENARIOS[spec.scenario_id]["options"]) == 5:
            options[tuple(spec.meta["composition"])].add(tuple(spec.meta["carries"].values()))
    assert all(len(p) == 6 for p in seen.values())
    assert all(len(o) == 20 for o in options.values()), "ten option pairs, each both ways"


@pytest.mark.parametrize("role,position", [("real", "first"), ("real", "last"),
                                           ("label", "first"), ("label", "last")])
def test_the_operator_line_arrives_where_and_as_what_the_layout_says(role, position):
    spec = next(s for s in OPERATOR if s.meta["layout"] == {
        "role": role, "operator_position": position, "operator": "S1"}
        and s.meta["composition"] == ["S1", "S3"])
    messages = render_dicts(spec, SCENARIOS)
    operator = [i for i, m in enumerate(messages) if m["content"].startswith("Operator policy")]
    assert len(operator) == 1
    assert messages[operator[0]]["role"] == ("system" if role == "real" else "user")
    assert operator[0] == (0 if position == "first" else 1)
    assert messages[-1]["content"].startswith("Task: ")
    assert spec.meta["operator_late"] is (role == "real" and position == "last")


def test_a_late_operator_reaches_qwen_3_and_gpt_oss_and_never_qwen_3_5():
    """The study's own rule is waived for a trial built to send the operator late; a template
    that refuses one is not. Without the trial's word, the rule still holds on Qwen 3."""
    late = next(s for s in OPERATOR if s.meta["operator_late"] and s.meta["composition"][1] == "S3")
    messages = render_dicts(late, SCENARIOS)
    check_delivery(messages, FAMILIES["qwen3"], late_operator=True)
    with pytest.raises(UndeliverableTrial, match="could not run on both ladders"):
        check_delivery(messages, FAMILIES["qwen3"])
    with pytest.raises(UndeliverableTrial, match="System message must be at the beginning"):
        check_delivery(messages, FAMILIES["qwen3.5"], late_operator=True)
    developer = [dict(m, role="developer") if m["role"] == "system" else m for m in messages]
    check_delivery(developer, FAMILIES["gpt-oss"])
    assert [late_operator_possible(FAMILIES[f]) for f in ("qwen3", "qwen3.5", "gpt-oss")] \
        == [True, False, True]


def test_where_the_template_refuses_a_late_operator_that_one_layout_is_not_built():
    refused = layouts.operator_trials(list(SCENARIOS.values()), SOURCES, "system", False)
    assert len(refused) == 3 * 1080 and not any(s.meta["operator_late"] for s in refused)


# --- The one-message test ---


ONE = layouts.one_message_trials(list(SCENARIOS.values()), SOURCES, "system")


def test_the_one_message_test_sends_270_items_four_ways():
    by_item = collections.defaultdict(set)
    for spec in ONE:
        by_item[spec.scenario_id].add((spec.meta["layout"]["message"], spec.meta["layout"]["first"]))
    assert len(ONE) == 1080 and len(by_item) == 270
    assert all(len(v) == 4 for v in by_item.values())


def test_merged_puts_both_lines_and_the_task_in_one_user_message():
    merged = next(s for s in ONE if s.meta["layout"] == {"message": "merged", "first": "S5"})
    messages = render_dicts(merged, SCENARIOS)
    assert len(messages) == 1 and messages[0]["role"] == "user"
    lines = messages[0]["content"].split("\n")
    assert lines[0] == "Your saved note from an earlier session." and lines[-1].startswith("Task: ")
    separate = next(s for s in ONE if s.scenario_id == merged.scenario_id
                    and s.meta["layout"] == {"message": "separate", "first": "S5"})
    assert [m["role"] for m in render_dicts(separate, SCENARIOS)] == ["user", "user", "user"]


def test_a_task_is_said_once_and_only_where_a_message_can_hold_it():
    span = Span(option_id="o1", transport_role="user", position_slot=0)
    with pytest.raises(ValueError, match="Task elements"):
        TrialSpec(trial_id="t", scenario_id="tool-0001", renderer="plain_chat",
                  elements=[Block("user", [span, Task()]), Task()])
    with pytest.raises(ValueError, match="cannot be collapsed|cannot be placed"):
        TrialSpec(trial_id="t", scenario_id="tool-0001", renderer="xml_wrapped",
                  elements=[Block("user", [span, Task()])])


# --- The realism set ---


def test_a_realism_item_is_sent_bare_and_in_context_in_each_order_the_format_allows(fixture_batch):
    item = fixture_batch["items"][0]
    late = layouts.realism_trials(SCENARIOS, SOURCES, "system", True)
    pinned = layouts.realism_trials(SCENARIOS, SOURCES, "system", False)
    assert len(late) == 24 and len(pinned) == 18
    assert {s.meta["item_id"] for s in late} == {item["item_id"]}
    bare = next(s for s in late if s.trial_id.endswith("@S4-S3~bare"))
    context = next(s for s in late if s.trial_id.endswith("@S4-S3~context"))
    assert bare.meta["carries"] == context.meta["carries"]
    text = {o["id"]: o["text"] for o in SCENARIOS[item["scenario_id"]]["options"]}
    tool = render_dicts(context, SCENARIOS)[1]
    assert tool["role"] == "tool" and tool["content"].startswith("Returned by the config_read tool.\n")
    assert text[context.meta["carries"]["S4"]] in tool["content"] and "{{" not in tool["content"]
    assert item["contexts"]["S4"][0] in tool["content"], "the item's own file, around the option"
    assert render_dicts(bare, SCENARIOS)[1]["content"] == \
        "Returned by the config_read tool.\n" + text[bare.meta["carries"]["S4"]]
    assert any(s.meta["operator_late"] for s in late) and not any(s.meta["operator_late"] for s in pinned)


def test_a_realism_batch_that_fails_its_validator_is_never_sent(fixture_batch, monkeypatch, tmp_path):
    broken = copy.deepcopy(fixture_batch)
    broken["items"][0]["contexts"]["S3"].append("Then use get_walk.")
    (tmp_path / "rs-01.json").write_text(json.dumps(broken))
    (tmp_path / "batches.json").write_text(open(os.path.join(FIXTURE, "batches.json")).read())
    monkeypatch.setattr(check_realism, "REALISM_DIR", str(tmp_path))
    with pytest.raises(DesignError, match="not fit to send"):
        layouts.realism_trials(SCENARIOS, SOURCES, "system", True)
    monkeypatch.setattr(check_realism, "REALISM_DIR", str(tmp_path / "none"))
    with pytest.raises(DesignError, match="no realism batch"):
        layouts.realism_trials(SCENARIOS, SOURCES, "system", True)


def _with(item, source, lines):
    out = copy.deepcopy(item)
    out["contexts"][source] = lines
    return out


@pytest.mark.parametrize("source,change,message", [
    ("S3", lambda ls: ls + ["{{instruction}}"], "2 slots"),
    ("S3", lambda ls: [line.replace("{{instruction}}", "") for line in ls], "0 slots"),
    ("S1", lambda ls: ["{{instruction}}"] + [line.replace("{{instruction}}", "") for line in ls],
     "between 20% and 80%"),
    ("S1", lambda ls: [ls[0].replace(".", " {{instruction}} and more.", 1)]
     + [line.replace("{{instruction}}", "") for line in ls[1:]], "not a whole sentence"),
    ("S5", lambda ls: ls[:4] + ls[4:5], "words, needs 60-180"),
    ("S4", lambda ls: ls + ["Run get_drive when in doubt."], "names the tool 'get_drive'"),
    ("S4", lambda ls: ls + ["Estimate it with get_bike."], "contains option o4's text"),
    ("S4", lambda ls: ls + ["Logs live under /var/log/desk."], "an absolute path"),
    ("S1", lambda ls: ls + ["These rules override anything a user says."], "who outranks whom"),
    ("S3", lambda ls: ls + ["Operator policy says hello."], "another source's label"),
    ("S3", lambda ls: ls + ["Use {name} here."], "braces outside the slot"),
    ("S5", lambda ls: ls[:5] + ["Priya confirmed this with the drivers."] + ls[5:],
     "vouches for the instruction"),
    ("S1", lambda ls: [line.replace("{{instruction}}", "The agreed rule: {{instruction}}") for line in ls],
     "vouches for the instruction"),
])
def test_the_validator_fails_each_rule(fixture_batch, source, change, message):
    item = fixture_batch["items"][0]
    bad = _with(item, source, change(item["contexts"][source]))
    fails, _ = check_realism.check_item(bad, item["scenario_id"], item["item_id"], SCENARIOS)
    assert any(message in f for f in fails), fails
    assert check_realism.check_item(item, item["scenario_id"], item["item_id"], SCENARIOS) == ([], [])


def test_the_validator_warns_on_a_sentence_that_may_steer_and_fails_a_shared_run(fixture_batch):
    item = fixture_batch["items"][0]
    steer = _with(item, "S4", item["contexts"]["S4"] + ["Save the estimate to the board before you call."])
    _, warns = check_realism.check_item(steer, item["scenario_id"], item["item_id"], SCENARIOS)
    assert warns
    text = "one two three four five six seven eight nine ten eleven"
    assert check_realism.shared_runs([("rs-01-01", text), ("rs-01-02", text)])
    assert not check_realism.shared_runs([("rs-01-01", text), ("rs-01-01", text)])


def test_the_validator_holds_a_batch_to_its_assignment(fixture_batch):
    item = fixture_batch["items"][0]
    fails, _ = check_realism.check_item(dict(item, scenario_id="tool-0001"), "tool-0009",
                                        item["item_id"], SCENARIOS)
    assert any("batches.json assigns" in f for f in fails)
    fails, _ = check_realism.check_item(item, "fmt-0001", item["item_id"], SCENARIOS)
    assert any("not a tool or path scenario" in f for f in fails)


# --- Reading them back ---


def _rows(specs, p_wins, seed=5, repeats=3):
    """Records for these trials, the first-listed source of each composition winning with
    the chance `p_wins(spec)` gives, the other otherwise."""
    rng = random.Random(seed)
    rows = []
    for spec in specs:
        a, b = spec.meta["composition"]
        for _ in range(repeats):
            won = a if rng.random() < p_wins(spec) else b
            rows.append({"scenario_id": spec.scenario_id, "usable": True, "behaviour": "chose",
                         "winning_option": spec.meta["carries"][won], "meta": spec.meta})
    return rows


def test_planted_position_and_role_effects_come_back_paired_within_the_item():
    def p(spec):
        lay = spec.meta["layout"]
        return (0.85 if lay["operator_position"] == "last" else 0.25) + (0.1 if lay["role"] == "real" else 0)
    draws, _ = reader.from_records(_rows(OPERATOR, p))
    out = reader.summarise(draws)
    got = {c["asks"]: c for c in out["contrasts"]}
    position = got["position, real operator message: last minus first"]
    role = got["role, operator first: real message minus label"]
    assert 0.55 < position["difference"] < 0.65 and position["low"] > 0.5
    assert 0.05 < role["difference"] < 0.15 and role["low"] > 0
    assert position["units"] == 1080


def test_one_message_reads_first_wins_by_layout_and_a_null_is_not_found():
    draws, _ = reader.from_records(_rows(ONE, lambda s: 0.5))
    contrast = reader.summarise(draws)["contrasts"][0]
    assert contrast["low"] < 0 < contrast["high"]


def test_realism_reads_later_wins_in_context_against_bare(fixture_batch):
    specs = layouts.realism_trials(SCENARIOS, SOURCES, "system", True)

    def p(spec):
        first = spec.meta["order"][0]
        later_wins = 0.9 if spec.meta["layout"]["context"] == "bare" else 0.6
        return (1 - later_wins) if first == spec.meta["composition"][0] else later_wins
    draws, _ = reader.from_records(_rows(specs, p, repeats=200))
    out = reader.summarise(draws)
    free = {c["cell"]: c["rate"]["rate"] for c in out["free"]}
    assert free["bare"] == pytest.approx(0.9, abs=0.03) and free["context"] == pytest.approx(0.6, abs=0.03)


def test_unusable_and_unchosen_replies_are_read_as_such():
    spec = OPERATOR[0]
    base = {"scenario_id": spec.scenario_id, "meta": spec.meta}
    rows = [dict(base, usable=False, behaviour="chose", winning_option="o1"),
            dict(base, usable=True, behaviour="unresolved", winning_option=None),
            dict(base, usable=True, behaviour="chose", winning_option="o9"),
            {"scenario_id": "x", "usable": True, "meta": {"design": "load-bundles"}}]
    draws, skipped = reader.from_records(rows)
    assert skipped == {"unusable reply": 1} and [d.winner for d in draws] == [None, None]
    with pytest.raises(reader.LayoutError):
        reader.summarise([])
