"""The load bundles and the declared-tier design: what they build, and what they refuse.
The worked trials are the reference twice over: the worked load cell, written as a bundle, must
pass the bundle validator, and a tier trial the design builds must render as tier-01 was written."""

from __future__ import annotations

import collections
import copy
import importlib
import itertools
import json

import pytest

from whowins.checkers import check
from whowins.checkers.core import Response
from whowins.runner import bundles, design
from whowins.runner.fillers import BANK
from whowins.runner.rendering import render_dicts
from whowins.runner.trials import load_cell_headers, load_scenarios, load_trials
from whowins.stats import capacity
from whowins.validation.check_load import check_all, check_bundle, pinned_tokenizers

SCENARIOS = load_scenarios()
KIND = {"F1": ("reply_words_under", 200), "F5": ("no_section", "changelog"),
        "F8": ("elapsed_time_at_the_end", None), "F13": ("mentions_project", None),
        "F14": ("step_before_writing", None), "F15": ("every_sentence_under", 40),
        "F16": ("artifact_in_a_file", None), "F17": ("artifact_named_after_project", None),
        "F18": ("artifact_lines_under", 10), "F19": ("artifact_sentences_under", 40),
        "F20": ("reply_mentions_project", None), "F21": ("step_before_writing", None),
        "F22": ("names_the_step_tool", None), "F23": ("step_before_writing", None)}
FREE = (set(), set())
"""No reservation: the worked bundle written as a bundle may reuse its own components and lines."""


def worked_bundle() -> dict:
    """load-01 to load-10, written in the bundle format."""
    head = load_cell_headers()["load_vs_conflict"]
    fillers = [{"id": f.filler_id, "kind": KIND[f.filler_id][0], "text": f.text,
                **({"value": KIND[f.filler_id][1]} if KIND[f.filler_id][1] is not None else {})}
               for f in BANK]
    trials = [t for t in load_trials() if t.get("cell") == "load_vs_conflict"]
    return {"bundle_id": "lb-01", "authored_by": "worked", "project": "atlas-core",
            "task": head["task"], "component_scenarios": head["component_scenarios"],
            "rationale": "the worked bundle", "fillers": fillers,
            "trials": [{"trial_id": f"lb-01-{i:02d}", "n_instructions": t["n_instructions"],
                        "k_conflict_groups": t["k_conflict_groups"],
                        "group_size": t["group_size"],
                        "lines": t["messages"][0]["content"].split("\n"),
                        "conflict_groups": [{k: g[k] for k in ("group", "scenario_id", "members")}
                                            for g in t["conflict_groups"]]}
                       for i, t in enumerate(trials, start=1)]}


# --- Load bundles ---


def test_the_worked_load_cell_passes_as_a_bundle():
    """Every structural rule the validator holds a new bundle to, met by the cell it replicates."""
    fails, _ = check_bundle(worked_bundle(), SCENARIOS, reserved=FREE)
    assert fails == []


def test_and_its_token_lengths_are_the_ones_the_load_cell_pins():
    """The validator counts tokens the way the load cell's own test does, or it checks nothing."""
    toks = pinned_tokenizers()
    if len(toks) < 2:
        pytest.skip("the pinned tokenizers are not in the local Hugging Face cache")
    fails, info = check_bundle(worked_bundle(), SCENARIOS, tokenizers=toks, reserved=FREE)
    assert fails == []
    assert {n: set(c.values()) for n, c in info["tokens"]["qwen3"].items()} == \
        {2: {10}, 4: {25}, 8: {59}, 12: {96}}
    assert {n: set(c.values()) for n, c in info["tokens"]["qwen3.5"].items()} == \
        {2: {11}, 4: {28}, 8: {66}, 12: {107}}


def _broken(change) -> list[str]:
    bundle = worked_bundle()
    change(bundle)
    fails, _ = check_bundle(bundle, SCENARIOS, tokenizers=pinned_tokenizers(), reserved=FREE)
    return fails


@pytest.mark.parametrize("name,change,expect", [
    ("a trial off the grid", lambda b: b["trials"].pop(), "not the grid"),
    ("a line that is nobody's",
     lambda b: b["trials"][0]["lines"].__setitem__(0, "Hum while you work."), "neither"),
    ("an option edited", lambda b: b["trials"][1]["lines"].__setitem__(
        b["trials"][1]["lines"].index("Call check_style first."), "Call check_style at once."),
     "is not one of the lines"),
    ("a filler of no known kind", lambda b: b["fillers"][0].__setitem__("kind", "be_nice"),
     "is not one of"),
    ("a kind given the wrong value", lambda b: b["fillers"][0].__setitem__("value", "many"),
     "whole-number value"),
    ("a group too big", lambda b: b["trials"][1]["conflict_groups"][0]["members"].append("o3"),
     "members"),
    ("a line said twice", lambda b: b["trials"][2]["lines"].__setitem__(1, b["trials"][2]["lines"][0]),
     "distinct"),
    ("the project missing from the task", lambda b: b.__setitem__("task", "Write the note."),
     "name the project"),
])
def test_a_bundle_that_breaks_a_rule_is_refused_by_name(name, change, expect):
    fails = _broken(change)
    assert any(expect in f for f in fails), (name, fails)


def test_a_length_that_moves_with_k_is_refused():
    """The cell exists to hold length while conflict varies. A longer stand-in breaks that."""
    toks = pinned_tokenizers()
    if not toks:
        pytest.skip("no pinned tokenizer in the local Hugging Face cache")

    def longer(b):
        b["fillers"].append({"id": "F99", "kind": "mentions_project",
                             "text": "Mention atlas-core by its full name in the reply."})
        b["trials"][0]["lines"][0] = "Mention atlas-core by its full name in the reply."
    assert any("tokens differ at n = 2" in f for f in _broken(longer))


def test_two_bundles_may_not_share_a_component_a_project_or_a_line():
    one, two = worked_bundle(), worked_bundle()
    two["bundle_id"] = "lb-02"
    fails, _ = check_bundle(two, SCENARIOS, others=[one], reserved=FREE)
    assert any("shares" in f for f in fails)
    assert any("already another bundle's line" in f for f in fails)


def test_the_worked_bundle_is_reserved_against_every_new_one():
    fails, _ = check_bundle(worked_bundle(), SCENARIOS)
    assert any("with the worked bundle" in f for f in fails)


def test_a_bundle_filler_reads_its_own_project_and_its_own_step_tools():
    """A filler kind is checked against the bundle it belongs to, not against atlas-core."""
    from whowins.checkers.core import Response, ToolCall
    bundle = worked_bundle()
    bundle["project"] = "orbit-api"
    bank = bundles.bank_of(bundle, SCENARIOS)
    mention, step = bank["Mention atlas-core."].check, bank["Check before you write."].check
    assert mention(Response(text="Done for orbit-api.")) is True
    assert mention(Response(text="Done for atlas-core.")) is False
    wrote = ToolCall("write_file", {"path": "/scratch/a/n.md", "content": "x"})
    assert step(Response(tool_calls=[ToolCall("check_types", {}), wrote])) is True
    assert step(Response(tool_calls=[ToolCall("check_lint", {}), wrote])) is False, \
        "a tool the bundle never offered is not its step"


def test_the_load_bundles_design_refuses_a_bundle_unfit_to_send(monkeypatch, tmp_path):
    """A bundle that fails the validator never becomes a trial."""
    path = tmp_path / "lb-01.json"
    path.write_text(json.dumps(worked_bundle()))
    monkeypatch.setattr(bundles, "bundle_files", lambda: [str(path)])
    with pytest.raises(design.DesignError, match="not fit to send"):
        design.load_bundle_trials(SCENARIOS, "system")


def test_with_no_bundles_the_design_sends_the_worked_ten(monkeypatch):
    monkeypatch.setattr(bundles, "bundle_files", lambda: [])
    out = design.load_bundle_trials(SCENARIOS, "developer")
    assert [s.trial_id for s in out] == [f"load-{i:02d}" for i in range(1, 11)]
    assert all(s.meta["design"] == "load-bundles" for s in out)
    assert render_dicts(out[0], SCENARIOS)[0]["role"] == "developer"


def test_every_bundle_on_disk_is_fit_to_send():
    """Structure always, and the lengths under whichever pinned tokenizers are cached here."""
    fails, _ = check_all()
    assert fails == []


def _fixture_texts() -> dict:
    """(checker key, label) -> a fixture text that reads as that label."""
    out = {}
    for mod in ("structural", "prose", "surface", "tooling", "values", "wire_editorial_syntax",
                "domain"):
        for key, label, text in importlib.import_module(f"fixtures.{mod}").FIXTURES:
            out.setdefault((key, label), text)
    return out


def _one_note(parts) -> str:
    """Fixture texts as one note: their paragraphs in order, except that every paragraph that is
    a JSON object joins one body at the end, since a note has one body."""
    body, rest = {}, []
    for para in (p for part in parts for p in part.split("\n\n")):
        try:
            value = json.loads(para)
        except ValueError:
            value = None
        if isinstance(value, dict):
            body.update(value)
        else:
            rest.append(para)
    return "\n\n".join(rest + ([json.dumps(body, indent=2)] if body else []))


def _clashes(groups, texts) -> list:
    """The choices of one member per format group that no order of their fixtures, made into
    one note, lets every classifier read."""
    def label(sid, oid):
        return next(o["checker"].split("==", 1)[1] for o in SCENARIOS[sid]["options"]
                    if o["id"] == oid)
    out = []
    for combo in itertools.product(*[[(sid, m) for m in members] for sid, members in groups]):
        parts = [texts.get((SCENARIOS[s]["checker_key"], label(s, m))) for s, m in combo]
        if None in parts or not any(
                all(check(SCENARIOS[s], Response(text=_one_note([parts[i] for i in order])))
                    .winning_option == m for s, m in combo)
                for order in itertools.permutations(range(len(combo)))):
            out.append(combo)
    return out


def test_one_note_can_obey_any_choice_among_a_bundle_trials_format_groups():
    """A trial that asks for two formats in one note must not make obeying both impossible."""
    texts = _fixture_texts()
    for bundle in bundles.load_bundles():
        for trial in bundle["trials"]:
            groups = [(g["scenario_id"], g["members"]) for g in trial["conflict_groups"]
                      if SCENARIOS[g["scenario_id"]]["family"] == "format"]
            if len(groups) > 1:
                assert _clashes(groups, texts) == [], trial["trial_id"]


def test_and_that_check_finds_a_clash_the_review_found():
    """A markdown heading reads as a hash prompt, so a dollar prompt under an h1 cannot be read."""
    clashes = _clashes([("fmt-0047", ["o1", "o2"]), ("fmt-0007", ["o1", "o2"])], _fixture_texts())
    assert (("fmt-0047", "o1"), ("fmt-0007", "o1")) in clashes


# --- Declared tiers ---


TIERS = design.tier_trials(list(SCENARIOS.values()), "system")


def test_a_tier_trial_renders_as_tier_01_was_written():
    """The design reproduces, byte for byte, a trial a person wrote before it existed."""
    worked = next(t for t in load_trials() if t["trial_id"] == "tier-01")
    spec = design.build_tier_trial(SCENARIOS["path-0008"], (1, 2), "o1", "o2",
                                   winner_first=True, operator_role="system")
    assert [dict(m) for m in render_dicts(spec, SCENARIOS)] == worked["messages"]


def test_on_gpt_oss_the_policy_rides_on_the_developer_channel():
    spec = design.build_tier_trial(SCENARIOS["path-0008"], (1, 2), "o1", "o2",
                                   winner_first=False, operator_role="developer")
    roles = [m["role"] for m in render_dicts(spec, SCENARIOS)]
    assert roles == ["developer", "user", "user", "user"]


def test_every_pair_gets_its_share_of_items_and_every_scenario_twelve_pairs():
    per_pair = collections.Counter(tuple(t.meta["rank_pair"]) for t in TIERS)
    assert len(per_pair) == 66 and set(per_pair.values()) <= {196, 197}
    per_scenario = collections.defaultdict(set)
    for t in TIERS:
        per_scenario[t.scenario_id].add(tuple(t.meta["rank_pair"]))
    assert len(per_scenario) == 1080 and all(len(p) == 12 for p in per_scenario.values())
    assert len({t.trial_id for t in TIERS}) == len(TIERS) == 12_960


def test_within_a_pair_position_and_content_are_balanced():
    """Whether the earlier- or later-listed option carries the winning tier, and whether it comes
    first, cycle through all four in every pair, and every two options of a scenario meet there."""
    cells = collections.defaultdict(collections.Counter)
    met = collections.defaultdict(set)
    for t in TIERS:
        ids = [o["id"] for o in SCENARIOS[t.scenario_id]["options"]]
        winner = t.meta["policy_winner"]
        loser = next(o for o in t.meta["order"] if o != winner)
        pair = tuple(t.meta["rank_pair"])
        cells[pair][(ids.index(winner) < ids.index(loser), t.meta["winner_first"])] += 1
        if len(ids) == 5:
            met[pair].add(frozenset((winner, loser)))
    for counts in cells.values():
        assert len(counts) == 4 and max(counts.values()) - min(counts.values()) <= 1
    assert all(len(options) == 10 for options in met.values())
    assert all(t.meta["ranks"][t.meta["policy_winner"]] == min(t.meta["rank_pair"]) for t in TIERS)


TIERS_6 = design.tier_trials(list(SCENARIOS.values()), "system", design.TIERS_6)


def test_tiers_1_to_6_give_15_pairs_of_432_items_at_half_the_trials():
    per_pair = collections.Counter(tuple(t.meta["rank_pair"]) for t in TIERS_6)
    assert len(per_pair) == 15 and set(per_pair.values()) == {432}
    per_scenario = collections.Counter(t.scenario_id for t in TIERS_6)
    assert len(per_scenario) == 1080 and set(per_scenario.values()) == {6}
    assert len({t.trial_id for t in TIERS_6}) == len(TIERS_6) == 6_480
    assert {t.meta["design"] for t in TIERS_6} == {"declared-tiers-6"}


def test_in_tiers_1_to_6_every_pair_meets_every_two_options_and_the_winner_side_is_exact():
    """At six pairs a scenario the old dealing left some tier pairs meeting 4 of 10 option
    pairs; each tier pair now takes them in turn."""
    cells = collections.defaultdict(collections.Counter)
    met = collections.defaultdict(collections.Counter)
    for t in TIERS_6:
        ids = [o["id"] for o in SCENARIOS[t.scenario_id]["options"]]
        winner = t.meta["policy_winner"]
        loser = next(o for o in t.meta["order"] if o != winner)
        pair = tuple(t.meta["rank_pair"])
        cells[pair][(ids.index(winner) < ids.index(loser), t.meta["winner_first"])] += 1
        if len(ids) == 5:
            met[pair][frozenset((winner, loser))] += 1
    assert all(len(c) == 4 and len(set(c.values())) == 1 for c in cells.values())
    assert all(len(m) == 10 and min(m.values()) >= 30 for m in met.values())


def test_capacity_is_read_over_the_tiers_a_run_measured(tmp_path):
    """A tier no trial used counts as never ruled out, so over 1 to 12 a 1-to-6 run's upper
    bound would read 12."""
    rows = []
    for spec in TIERS_6[:1500]:
        winner = spec.meta["policy_winner"]
        rows.append({"line": "record", "trial_id": spec.trial_id, "scenario_id": spec.scenario_id,
                     "repeat": 0, "usable": True, "behaviour": "chose",
                     "winning_option": winner, "meta": spec.meta})
    log = tmp_path / "records.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = capacity.run_capacity("main-tier-qwen3-8b-nothink", str(log), qs=(0.9,))
    assert out["tiers"] == [1, 2, 3, 4, 5, 6] and out["by_q"]["0.9"]["upper"] <= 6


@pytest.mark.parametrize("run_id", ["main-load-qwen3-8b-nothink", "main-tier-gpt-oss-120b-think"])
def test_the_design_report_reads_the_load_and_tier_runs(run_id, capsys):
    """Operators read `--balance` before a run, and it once assumed every trial set sources."""
    assert design._main([run_id, "--balance", "--show", "1", "--no-log-file", "--quiet"]) == 0
    out = capsys.readouterr().out
    assert ("most two of the four differ within a pair is 0" in out if "tier" in run_id
            else "trials per (n, k)" in out)


def test_a_rank_needs_a_policy_on_an_operator_channel():
    from whowins.runner.spec import TrialSpec
    spec = design.build_tier_trial(SCENARIOS["path-0008"], (3, 9), "o1", "o2",
                                   winner_first=True, operator_role="system")
    with pytest.raises(ValueError, match="operator channel"):
        TrialSpec(trial_id="x", scenario_id="path-0008", renderer="plain_chat",
                  elements=spec.elements, policy_scheme="ordinal_1_12",
                  policy_direction="lower_wins", policy_role="user")


def test_capacity_reads_a_tier_run_as_the_policy_scores_it():
    spec = TIERS[0]
    winner = spec.meta["policy_winner"]
    loser = next(o for o in spec.meta["order"] if o != winner)
    base = {"trial_id": spec.trial_id, "scenario_id": spec.scenario_id, "repeat": 0,
            "usable": True, "behaviour": "chose", "meta": copy.deepcopy(spec.meta)}
    rows = [dict(base, winning_option=winner), dict(base, winning_option=loser),
            dict(base, behaviour="no_action", winning_option=None),
            dict(base, usable=False, winning_option=winner),
            dict(base, meta={"arm": "pair"}, winning_option=winner)]
    draws, skipped = capacity.from_records(rows)
    assert [d.correct for d in draws] == [True, False, False]
    assert skipped == {"unusable reply": 1}
    assert {(d.winner, d.loser) for d in draws} == {tuple(spec.meta["rank_pair"])}
