"""The load cell's reading, on worlds with a known answer and on records the scorer writes.
Bundles are the replicates, so the tests plant effects per bundle and check that a planted
effect is found, a null is not, and a trial every bundle agrees on still has width."""

from __future__ import annotations

import json
import random

import pytest

from whowins.runner.design import load_bundle_trials
from whowins.runner.response import completion_from
from whowins.runner.run import ServingStack, score
from whowins.runner.tools import WRITE_TOOL
from whowins.runner.trials import load_scenarios
from whowins.stats import load_cell
from whowins.stats.load_cell import CONTRASTS, WORKED, contrast, estimate, from_records, summarise
from whowins.stats.paired import PairedError, t_quantile

GRID = ((2, 0, None), (2, 1, 2), (4, 0, None), (4, 1, 2), (8, 0, None), (8, 1, 2),
        (8, 3, 2), (12, 1, 2), (12, 6, 2), (12, 3, 3))
FILLERS_LEFT = {(2, 0): 2, (2, 1): 0, (4, 0): 4, (4, 1): 2, (8, 0): 8, (8, 1): 6, (8, 3): 2,
                (12, 1): 10, (12, 6): 0, (12, 3): 3}


def _row(bundle, n, k, size, chosen, kept, *, usable=True, trial="t"):
    """One record as `run.score` writes it, reduced to what the load cell reads."""
    sids = ("tool-0001", "path-0008", "fmt-0009")
    groups = [{"group_id": f"G{i + 1}", "scenario_id": sids[i % 3],
               "behaviour": "chose" if c else "unresolved"} for i, c in enumerate(chosen)]
    fillers = [{"filler_id": f"F{i}", "result": "satisfied" if f else "violated"}
               for i, f in enumerate(kept)]
    return {"line": "record", "trial_id": trial, "usable": usable, "groups": groups,
            "fillers": fillers, "conjunction": all(chosen) if chosen else None,
            "all_satisfied": all(chosen) and all(kept) if (chosen or kept) else None,
            "meta": {"cell": "load_vs_conflict", "bundle": bundle, "n_instructions": n,
                     "k_conflict_groups": k, "group_size": size}}


def _world(group, filler, *, bundles=10, repeats=3, seed=7, shared=False):
    """Rows for every bundle and trial of the grid. `group(cell)` and `filler(cell)` give the
    chance a group is chosen and a filler kept; `shared` makes a draw's groups succeed together."""
    rng = random.Random(seed)
    rows = []
    for b in range(bundles):
        for n, k, size in GRID:
            for _ in range(repeats):
                p = group((n, k, size))
                together = rng.random() < p
                chosen = [together if shared else rng.random() < p for _ in range(k)]
                kept = [rng.random() < filler((n, k, size)) for _ in range(FILLERS_LEFT[n, k])]
                rows.append(_row(f"lb-{b:02d}", n, k, size, chosen, kept))
    return rows


def _contrast(out, asks):
    return next(c for c in out["contrasts"] if c["asks"] == asks)


def test_the_t_quantile_matches_published_tables():
    for df, want in ((1, 12.7062), (2, 4.3027), (9, 2.2622), (30, 2.0423)):
        assert t_quantile(0.975, df) == pytest.approx(want, abs=1e-4)
    assert t_quantile(0.995, 9) == pytest.approx(3.2498, abs=1e-4)
    assert t_quantile(0.025, 9) == pytest.approx(-2.2622, abs=1e-4)
    with pytest.raises(PairedError):
        t_quantile(0.975, 0)


def test_only_usable_replies_to_load_trials_are_read():
    """A tier or pair row is another design, and an unusable reply says nothing of the model.
    A filler with no verdict is left out rather than counted as broken."""
    rows = [_row("lb-02", 4, 1, 2, [True], [True, False]),
            _row("lb-02", 4, 1, 2, [False], [True, True], usable=False),
            {"trial_id": "x", "usable": True, "meta": {"arm": "tier"}},
            {**_row(None, 2, 0, None, [], [True, True]), "trial_id": "load-01"}]
    rows[3]["fillers"].append({"filler_id": "F9", "result": "no_answer"})
    rows.append(_row("lb-03", 8, 3, 2, [True, True, True], []))
    for group, behaviour in zip(rows[-1]["groups"], ("off_menu", "multiple", "chose")):
        group["behaviour"] = behaviour
    draws, skipped = from_records(rows)
    assert skipped == {"unusable reply": 1}
    assert [(d.bundle, d.cell) for d in draws] == \
        [("lb-02", (4, 1, 2)), (WORKED, (2, 0, None)), ("lb-03", (8, 3, 2))]
    assert draws[0].groups == (("G1", "tool", True),) and draws[0].fillers == (True, False)
    assert draws[1].fillers == (True, True)
    assert [c for _, _, c in draws[2].groups] == [False, False, True], "only its own member counts"


def test_each_bundle_weighs_the_same_however_many_draws_it_has():
    rows = [_row("lb-02", 2, 1, 2, [True], [])] * 3 + [_row("lb-03", 2, 1, 2, [False], [])] * 30
    draws, _ = from_records(rows)
    e = estimate(draws, "groups")
    assert e["rate"] == pytest.approx(0.5) and e["bundles"] == 2 and (e["kept"], e["of"]) == (3, 33)


def test_a_trial_every_bundle_agrees_on_still_has_width():
    """Ten bundles all at 1.0 have no spread, but thirty draws do not certify 1.0."""
    draws, _ = from_records(_row(f"lb-{b:02d}", 8, 3, 2, [True] * 3, [True, True])
                            for b in range(10) for _ in range(3))
    e = estimate(draws, "all_satisfied")
    assert e["rate"] == 1.0 and e["high"] == 1.0 and 0.85 < e["low"] < 0.9
    ind = summarise(draws)["trials"][0]["independence"]
    assert (ind["observed"], ind["product"], ind["low"]) == (1.0, 1.0, None)


def test_a_planted_conflict_effect_is_found_and_a_null_load_effect_is_not():
    out = summarise(from_records(_world(lambda c: 0.5, lambda c: 1.0))[0])
    conflict = _contrast(out, "n=8: three conflicts against none")
    assert conflict["high"] < 0 and conflict["difference"] < -0.5
    load = _contrast(out, "k=0: n=8 against n=2")
    assert load["low"] < 0 < load["high"]
    assert len(out["contrasts"]) == len(CONTRASTS)


def test_a_planted_load_effect_is_found_with_conflict_held_fixed():
    out = summarise(from_records(_world(lambda c: 0.99 - 0.06 * c[0], lambda c: 0.98))[0])
    load = _contrast(out, "k=1: n=12 against n=2")
    assert load["measure"] == "groups" and load["high"] < 0


def test_a_contrast_pairs_the_two_trials_of_one_bundle():
    """A bundle with only one of the two trials says nothing about their difference."""
    rows = ([_row("lb-02", 8, 1, 2, [True], [True] * 6)] * 5
            + [_row("lb-02", 8, 0, None, [], [True] * 8)] * 5
            + [_row("lb-03", 8, 1, 2, [False], [True] * 6)] * 5
            + [_row("lb-03", 8, 0, None, [], [True] * 8)] * 5
            + [_row("lb-04", 8, 1, 2, [False], [False] * 6)] * 5)
    c = contrast(from_records(rows)[0], "all_satisfied", (8, 1, 2), (8, 0, None))
    assert c["bundles"] == 2 and c["difference"] == pytest.approx(-0.5)
    assert c["low"] <= -0.5 <= c["high"]


def test_independent_groups_sit_on_the_product_and_shared_failure_above_it():
    keep = (lambda c: 0.7, lambda c: 1.0)
    alone = summarise(from_records(_world(*keep, repeats=40))[0])
    together = summarise(from_records(_world(*keep, repeats=40, shared=True))[0])
    for out, planted in ((alone, False), (together, True)):
        six = next(t for t in out["trials"] if (t["n"], t["k"]) == (12, 6))["independence"]
        assert six["bundles"] == 10
        if planted:
            assert six["low"] > 0.3, "0.7 together against 0.7 ** 6 apart"
        else:
            assert six["low"] < 0 < six["high"]
    assert all(t["independence"] is None for t in alone["trials"] if t["k"] < 2)


def test_groups_are_read_per_family():
    rows = [_row(f"lb-{b:02d}", 12, 3, 3, [True, False, True], []) for b in range(4)]
    out = summarise(from_records(rows)[0])
    assert {f: e["rate"] for f, e in out["families"].items()} == \
        {"tool": 1.0, "path": 0.0, "format": 1.0}


def test_records_the_scorer_writes_are_read_whole():
    """Every trial the load-bundles design sends, scored as the run loop scores it, reads back
    as a draw on its own bundle and cell, and every planned contrast can be made."""
    scenarios = load_scenarios()
    stack = ServingStack(model="m", dtype="bfloat16", vllm_version="0", tensor_parallel_size=1,
                         gpu="g", gpu_count=1)
    reply = completion_from(text="Done.", tool_calls=[
        {"name": WRITE_TOOL, "arguments": {"path": "/tmp/note.md", "content": "- one\n- two"}}])
    rows = []
    for spec in load_bundle_trials(scenarios, "system"):
        rows.append(score(spec, scenarios, reply, stack).as_dict())
    draws, skipped = from_records(rows)
    assert skipped == {} and len(draws) == 100
    assert {d.bundle for d in draws} == {WORKED} | {f"lb-{i:02d}" for i in range(2, 11)}
    assert sorted({d.cell for d in draws}, key=str) == sorted(GRID, key=str)
    out = summarise(draws)
    assert len(out["contrasts"]) == len(CONTRASTS)
    assert all(c["bundles"] == 10 for c in out["contrasts"])


def test_the_command_reads_a_log_and_refuses_one_with_no_load_trial(tmp_path, capsys):
    log = tmp_path / "records.jsonl"
    log.write_text("".join(json.dumps(r) + "\n"
                           for r in _world(lambda c: 0.9, lambda c: 0.95)), encoding="utf-8")
    out = tmp_path / "load.json"
    assert load_cell._main(["main-load-qwen3-8b-nothink", "--log", str(log),
                            "--json", str(out), "--no-log-file"]) == 0
    text = capsys.readouterr().out
    for title in ("BY TRIAL", "CONFLICT AT MATCHED LENGTH", "LENGTH AT FIXED CONFLICT",
                  "MORE GROUPS OF ONE SIZE", "AGAINST INDEPENDENCE", "BY FAMILY"):
        assert title in text
    assert len(json.loads(out.read_text())["trials"]) == len(GRID)
    other = tmp_path / "tier.jsonl"
    other.write_text(json.dumps({"line": "record", "trial_id": "x", "meta": {"arm": "tier"}})
                     + "\n", encoding="utf-8")
    assert load_cell._main(["main-tier-qwen3-8b-nothink", "--log", str(other),
                            "--no-log-file"]) == 2
