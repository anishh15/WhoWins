"""The run report.
Built almost entirely on synthetic records: a report that only ever ran on one model's log
would be tuned to that log without anyone deciding to. The load-bearing test is the one
about pooling two labelled lines with two messages."""

from __future__ import annotations

import json
import os

import pytest

from whowins.runner import analyse
from whowins.runner.analyse import (
    AnalysisError,
    load_rows,
    pair_kinds,
    position,
    repeats,
    solo,
    sources,
    wilson,
)


def rec(trial, scenario, *, arm="pair", carries, slots, won=None, pinned=(),
        behaviour=None, repeat=0, **extra):
    """One record, with only the fields the report reads."""
    pair = tuple(sorted(carries)) if len(carries) > 1 else \
        tuple(extra.pop("source_pair", sorted(carries) * 2)[:2])
    return {
        "line": "record", "trial_id": trial, "scenario_id": scenario,
        "behaviour": behaviour or ("chose" if won else "unresolved"),
        "winning_option": won, "label": won or "__unresolved__",
        "communication": extra.pop("communication", "silent"),
        "usable": True, "finish_reason": "stop", "faults": [],
        "serving_stack": {}, "serving_fingerprint": "sha256:test",
        "concurrency": 1, "at": "2026-09-14T00:00:00", "turns": 1,
        "stopped_by": "no_more_calls", "repeat": repeat,
        "raw": {"choices": [{"message": {"content": "x"}}]}, "later_turns": [],
        "meta": {"arm": arm, "n_competing": len(carries),
                 "source_pair": list(pair), "carries": dict(carries),
                 "slots": dict(slots), "operator_pinned": list(pinned)},
        **extra,
    }


def wrap(records):
    return [{"row": r, "meta": r["meta"], "family": "format", "key": "output_format",
             "arm": r["meta"]["arm"], "pair": tuple(r["meta"]["source_pair"]),
             "slots": r["meta"]["slots"], "carries": r["meta"]["carries"],
             "pinned": tuple(r["meta"]["operator_pinned"]),
             "winner": analyse._winner(r)} for r in records]


def test_a_flag_is_split_by_whether_the_later_or_the_earlier_line_won():
    """Flagging the conflict and still following the later line is the report's question for
    thinking on against off; the split needs which instruction won, by position."""
    carries, slots = {"S3": "o1", "S4": "o2"}, {"S3": 0, "S4": 1, "task": 2}
    rows = wrap([rec("a", "fmt-0001", carries=carries, slots=slots, won="o2", communication="flagged"),
                 rec("b", "fmt-0001", carries=carries, slots=slots, won="o1", communication="silent"),
                 rec("c", "fmt-0001", carries=carries, slots=slots, communication="hedged")])
    out = analyse.communication(rows)["pair"]
    assert out["by_winner"] == {"earlier": {"silent": 1, "hedged": 0, "flagged": 0},
                                "later": {"silent": 0, "hedged": 0, "flagged": 1}}
    assert out["flagged"]["count"] == 1 and out["hedged"]["count"] == 1


# --- Which pairs can be read ---


def test_two_lines_of_one_message_are_not_pooled_with_two_messages():
    """The bug this file exists for.
    S1 and S2 are both operator sources, so the chat format puts them in ONE message. Asking
    only "did the order vary" calls that pair free and then averages a primacy effect with a
    recency one -- 0.834 and 0.260 into 0.716."""
    rows = []
    for i in range(10):                      # one message, two labelled lines
        rows.append(rec(f"a{i}", "s1", carries={"S1": "o1", "S2": "o2"},
                        slots={"S1": i % 2, "S2": 1 - i % 2, "task": 2},
                        pinned=("S1", "S2"), won="o1"))
    for i in range(10):                      # operator pinned first, other after
        rows.append(rec(f"b{i}", "s2", carries={"S1": "o1", "S3": "o2"},
                        slots={"S1": 0, "S3": 1, "task": 2},
                        pinned=("S1",), won="o2"))
    for i in range(10):                      # two ordinary turns, order varies
        rows.append(rec(f"c{i}", "s3", carries={"S3": "o1", "S4": "o2"},
                        slots={"S3": i % 2, "S4": 1 - i % 2, "task": 2},
                        pinned=(), won="o2"))
    kinds = pair_kinds(wrap(rows))
    assert kinds["within_message"] == {("S1", "S2")}
    assert kinds["free"] == {("S3", "S4")}
    assert kinds["pinned"] == {("S1", "S3")}

    p = position(wrap(rows))
    assert p["later_wins_free"]["n"] == 10
    assert p["second_line_wins_within_message"]["n"] == 10
    assert p["later_wins_pinned"]["n"] == 10
    assert (p["later_wins_free"]["n"] + p["later_wins_pinned"]["n"]
            + p["second_line_wins_within_message"]["n"]) == 30, "no pair counted twice"


def test_the_report_names_no_source_and_no_model():
    """A different family pins a different channel. Nothing here may care."""
    rows = [rec(f"x{i}", "s1", carries={"DEV": "o1", "CHAT": "o2"},
                slots={"DEV": 0, "CHAT": 1, "task": 2},
                pinned=("DEV",), won="o2") for i in range(6)]
    rows += [rec(f"y{i}", "s2", carries={"CHAT": "o1", "NOTE": "o2"},
                 slots={"CHAT": i % 2, "NOTE": 1 - i % 2, "task": 2},
                 pinned=(), won="o1") for i in range(6)]
    kinds = pair_kinds(wrap(rows))
    assert kinds["pinned"] == {("CHAT", "DEV")} or kinds["pinned"] == {("DEV", "CHAT")}
    assert kinds["free"] == {("CHAT", "NOTE")}
    assert sources(wrap(rows))["matched_position"], "a matched table was still built"


def test_a_pair_whose_order_never_varied_is_never_called_free():
    rows = [rec(f"x{i}", "s1", carries={"S3": "o1", "S4": "o2"},
                slots={"S3": 0, "S4": 1, "task": 2}, pinned=(), won="o2")
            for i in range(8)]
    assert pair_kinds(wrap(rows))["free"] == set()
    assert pair_kinds(wrap(rows))["pinned"] == {("S3", "S4")}


# --- The numbers ---


def test_a_wilson_interval_stays_on_the_scale():
    """Several cells here sit at 0 or 1, which is where the normal
    approximation runs off the end and the reader most needs it not to."""
    for hits, n in ((0, 40), (40, 40), (1, 3), (621, 745)):
        lo, hi = wilson(hits, n)
        assert 0.0 <= lo <= hi <= 1.0, (hits, n, lo, hi)
    assert wilson(0, 0) == (0.0, 0.0)
    lo, hi = wilson(621, 745)
    assert lo == pytest.approx(0.805, abs=0.002) and hi == pytest.approx(0.859, abs=0.002)


def test_position_reads_the_later_source_and_not_the_nearer_one():
    """`later` must mean later in the prompt, not nearer the task line.
    Where the task sits is balanced in a free pair, so the two come apart and the report has to
    follow the one it names."""
    rows = []
    for i in range(20):      # task LAST: the later source is the NEARER one
        first, last = ("S3", "S4") if i % 2 else ("S4", "S3")
        rows.append(rec(f"a{i}", "s1", carries={"S3": "o1", "S4": "o2"},
                        slots={first: 0, last: 1, "task": 2}, pinned=(),
                        won={"S3": "o1", "S4": "o2"}[last]))
    for i in range(20):      # task FIRST: the later source is the FURTHER one
        first, last = ("S3", "S4") if i % 2 else ("S4", "S3")
        rows.append(rec(f"b{i}", "s2", carries={"S3": "o1", "S4": "o2"},
                        slots={"task": 0, first: 1, last: 2}, pinned=(),
                        won={"S3": "o1", "S4": "o2"}[last]))
    p = position(wrap(rows))
    assert p["later_wins_free"]["rate"] == 1.0, "the later source always won"
    by = p["later_wins_by_task_slot"]
    assert by["0"]["rate"] == 1.0 and by["2"]["rate"] == 1.0, (
        "a report measuring distance to the task would give 0.0 on one of these")


def test_the_source_table_is_split_by_position_because_the_overall_one_is_not_safe():
    """A source that always arrives last wins a lot; that is the position."""
    rows = [rec(f"x{i}", "s1", carries={"S3": "o1", "S4": "o2"},
                slots={"S3": 0, "S4": 1, "task": 2}, pinned=(), won="o2")
            for i in range(20)]
    s = sources(wrap(rows))
    assert s["overall"]["S4"]["rate"] == 1.0 and s["overall"]["S3"]["rate"] == 0.0
    assert s["matched_position"] == {}, (
        "the pair never varied its order, so there is no matched comparison to make")


def test_solo_ability_is_compared_per_option_and_never_per_trial():
    """A solo trial shows one option of five and a conflict shows two, so the
    conflict arm scores `chose` more often for a purely arithmetic reason. The
    per-option table is the one that means something."""
    rows = []
    for i in range(3):   # o1 always produced alone
        rows.append(rec(f"s1r{i}", "sc1", arm="solo", carries={"S3": "o1"},
                        slots={"S3": 0, "task": 1}, won="o1", repeat=i,
                        source_pair=["S3", "S4"]))
    for i in range(3):   # o2 never produced alone
        rows.append(rec(f"s2r{i}", "sc1", arm="solo", carries={"S4": "o2"},
                        slots={"S4": 0, "task": 1}, won=None, repeat=i,
                        source_pair=["S3", "S4"]))
    for i in range(3):   # and in conflict o1 wins
        rows.append(rec(f"cr{i}", "sc1", carries={"S3": "o1", "S4": "o2"},
                        slots={"S3": 0, "S4": 1, "task": 2}, won="o1", repeat=i))
    out = solo(wrap(rows))
    assert out["conflict_win_by_solo_ability"]["always"]["rate"] == 1.0
    assert out["conflict_win_by_solo_ability"]["never"]["rate"] == 0.0
    assert out["never_solo"] == 0, "the scenario itself was produced, by o1"


def test_solo_says_so_when_a_run_has_no_solo_arm():
    """The ladder run asked for sizes 2, 3 and 5 and no solo control.
    The section used to divide by `or 1` and print "n=1, chose 0.000" -- a number
    describing nothing, in the one place a reader looks for a model's ability."""
    rows = [rec(f"c{i}", "sc1", carries={"S3": "o1", "S4": "o2"},
                slots={"S3": 0, "S4": 1, "task": 2}, won="o1", repeat=i)
            for i in range(6)]
    out = solo(wrap(rows))
    assert out["has_solo_arm"] is False
    assert out["options_measured"] == 0
    assert out["conflict_where_solo_always"] is None, (
        "no solo arm means no such subset, not a subset of size one")


def test_the_source_table_splits_by_size_and_position_reads_only_pairs():
    """Two properties the ladder run needed and the pair runs never exercised.
    Pooling win rates across sizes mixes a one-in-two chance level with a one-in-five
    one; and `matched_position` asks which of TWO sources came later, which has no
    answer for a triple."""
    rows = []
    for i in range(8):
        rows.append(rec(f"p{i}", "sc1", carries={"S3": "o1", "S4": "o2"},
                        slots={"S3": i % 2, "S4": 1 - i % 2, "task": 2}, won="o1"))
        rows.append(rec(f"t{i}", "sc2", carries={"S3": "o1", "S4": "o2", "S5": "o3"},
                        slots={"S3": i % 3, "S4": (i + 1) % 3, "S5": (i + 2) % 3,
                               "task": 3}, won="o1", source_pair=["S3", "S4"]))
    wrapped = wrap(rows)
    out = sources(wrapped)
    assert set(out["overall_by_size"]) == {"2", "3"}
    assert out["overall_by_size"]["2"]["S3"]["n"] == 8
    assert out["overall_by_size"]["3"]["S3"]["n"] == 8
    assert all(len(p) == 2 for p in analyse.free_pairs(wrapped)), (
        "a larger composition must never reach the matched-position table, which "
        "takes an arbitrary loser as `other`")


def test_repeats_report_what_the_extra_draws_bought():
    rows = [rec("t1", "s1", carries={"S3": "o1", "S4": "o2"},
                slots={"S3": 0, "S4": 1, "task": 2}, won="o1", repeat=i)
            for i in range(3)]
    rows += [rec("t2", "s2", carries={"S3": "o1", "S4": "o2"},
                 slots={"S3": 0, "S4": 1, "task": 2},
                 won=("o1" if i == 0 else None), repeat=i) for i in range(3)]
    r = repeats(wrap(rows))
    assert r["trials_with_several_draws"] == 2
    assert r["unanimous"]["hits"] == 1
    assert r["single_draw_would_mislabel"] == pytest.approx(0.5)


def test_a_win_several_sources_demanded_is_not_credited_to_one_of_them():
    """A free prediction has two sources demanding the same option. `_winner` returned the
    first source it met, so the other's share of the win went to it without a word."""
    joint = rec("t", "s", carries={"S1": "o1", "S3": "o3", "S5": "o3"},
                slots={"S1": 0, "S3": 1, "S5": 2, "task": 3}, won="o3")
    assert analyse._winner(joint) is None
    alone = rec("t", "s", carries={"S1": "o1", "S3": "o3"},
                slots={"S1": 0, "S3": 1, "task": 2}, won="o3")
    assert analyse._winner(alone) == "S3"


# --- End to end ---


def test_a_log_that_is_not_there_says_so(tmp_path):
    with pytest.raises(AnalysisError, match="no log to read"):
        load_rows("nope", str(tmp_path / "missing.jsonl"), {})


def test_a_log_with_no_scored_rows_says_so(tmp_path):
    path = tmp_path / "records.jsonl"
    path.write_text('{"line": "failure", "trial_id": "t"}\n')
    with pytest.raises(AnalysisError, match="no scored records"):
        load_rows("nope", str(path), {})


def test_the_whole_report_runs_on_a_real_run():
    """Skipped when the operator's records are not in this checkout, which is
    where run records live. When they are, every section must build."""
    from whowins.runner.batch import RESULTS

    run_id = "balanced-qwen3-1.7b"
    log = os.path.join(RESULTS, run_id, "records.jsonl")
    if not os.path.exists(log):
        pytest.skip("this run's records are on the operator's branch")
    out = analyse.analyse(run_id, log)
    assert set(analyse.SECTIONS) <= set(out)
    assert out["hygiene"]["draws"] > 0
    assert out["position"]["later_wins_free"]["n"] > 0
    assert json.dumps(out), "the report must be JSON, so two runs can be diffed"


def test_an_unlabelled_reply_is_read_on_the_turn_that_was_scored():
    """Scoring reads the last turn that is not talk or a wrap-up; this read the last turn with
    any text, so an artifact followed by a sign-off counted as the model's miss, not ours."""
    from whowins.runner.response import completion_from
    from whowins.runner.trials import load_scenarios

    row = dict(rec("t", "fmt-0001", carries={"S3": "o1"}, slots={"S3": 0, "task": 1}),
               raw=completion_from(text="key_one: 1\nkey_two: 2"),
               later_turns=[completion_from(text="Let me know if you need anything else!")])
    shape = analyse.reply_shape(row, "output_format", load_scenarios()["fmt-0001"])
    assert shape == "artifact_shaped"


# --- Which checkers said so ---


def test_a_record_says_which_checkers_scored_it():
    """Two runs scored either side of a checker fix were scored by two different instruments.
    `balanced-qwen3-1.7b` ran before two holes were closed and the 14B after, and a table putting
    them side by side reads the instrument's change as the model's."""
    from whowins.checkers import fingerprint

    assert fingerprint() == fingerprint(), "it has to be stable to be worth recording"
    assert fingerprint().startswith("sha256:")


def test_the_fingerprint_moves_with_anything_that_decides_a_verdict(tmp_path):
    """It hashed checkers/ alone, while which turn is the artifact is decided in run.py, so
    a change there moved verdicts and every run still read as scored by one instrument."""
    import shutil

    import whowins
    from whowins.checkers import SCORING_MODULES, fingerprint

    copy = tmp_path / "whowins"
    shutil.copytree(os.path.dirname(whowins.__file__), copy,
                    ignore=shutil.ignore_patterns("__pycache__"))
    today = fingerprint(str(copy))
    assert today == fingerprint(), "a copy of the same source is the same instrument"

    def moved_by(module, edit):
        path = copy / module
        source = path.read_text(encoding="utf-8")
        path.write_text(edit(source), encoding="utf-8")
        moved = fingerprint(str(copy)) != today
        path.write_text(source, encoding="utf-8")
        return moved

    assert moved_by("runner/run.py", lambda s: s.replace("updated|created", "updatex|created")), \
        "a one-character change to _WRAP_UP"
    for module in ("checkers/core.py", *SCORING_MODULES):
        assert moved_by(module, lambda s: s + "\n"), module
    assert not moved_by("runner/analyse.py", lambda s: s + "\n"), "reading results is not scoring"


def test_the_report_says_when_the_verdicts_are_not_todays():
    """Three answers, and the third is the honest one rather than a guess."""
    from whowins.checkers import fingerprint
    from whowins.runner.analyse import staleness

    base = rec("t", "s", carries={"S3": "o1", "S4": "o2"},
               slots={"S3": 0, "S4": 1, "task": 2}, won="o1")

    current = wrap([dict(base, checker_fingerprint=fingerprint()) for _ in range(4)])
    out = staleness(current)
    assert out["agrees"] and not out["unknown"]

    older = wrap([dict(base, checker_fingerprint="sha256:somethingelse")
                  for _ in range(4)])
    out = staleness(older)
    assert not out["agrees"] and not out["unknown"]

    # Records written before the fingerprint existed: say so, do not guess.
    out = staleness(wrap([dict(base) for _ in range(4)]))
    assert not out["agrees"] and out["unknown"] and out["unstamped"] == 4


def test_a_fingerprint_moved_only_by_a_docstring_is_the_same_instrument(monkeypatch):
    """51e74e1 changed one docstring in runner/run.py, so half the Qwen 3 main run carried an
    older fingerprint and the report said "NO" over verdicts nothing had changed."""
    from whowins.checkers import fingerprint
    from whowins.runner.analyse import SAME_SCORING, scored_as, staleness

    assert scored_as("sha256:152b3fed8fd5ee855eaa318c005449e3") == \
        scored_as("sha256:948ddfa0cf2b279f859ee7af75d25645")
    monkeypatch.setitem(SAME_SCORING, "sha256:older", fingerprint())
    base = rec("t", "s", carries={"S3": "o1", "S4": "o2"},
               slots={"S3": 0, "S4": 1, "task": 2}, won="o1")
    mixed = wrap([dict(base, checker_fingerprint=f) for f in ("sha256:older", fingerprint())])
    assert staleness(mixed)["agrees"]
    assert not staleness(wrap([dict(base, checker_fingerprint="sha256:other")]))["agrees"]


def test_an_unusable_reply_is_counted_in_hygiene_and_never_read_as_behaviour(tmp_path):
    """A truncated or faulty reply measured nothing; position read its win as one."""
    from types import SimpleNamespace

    carries = {"S3": "o1", "S4": "o2"}
    rows = [rec("a", "fmt-0001", carries=carries, slots={"S3": 0, "S4": 1, "task": 2}, won="o2"),
            rec("b", "fmt-0001", carries=carries, slots={"S3": 1, "S4": 0, "task": 2}, won="o1"),
            rec("c", "fmt-0001", carries=carries, slots={"S3": 0, "S4": 1, "task": 2}, won="o1",
                usable=False, finish_reason="length")]
    log = tmp_path / "records.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    run = SimpleNamespace(model=SimpleNamespace(key="m", family=None),
                          environment=SimpleNamespace(key="e"), design="d")
    out = analyse.analyse("r", str(log), scenarios={}, run=run)
    assert out["hygiene"]["draws"] == 3 and out["hygiene"]["unusable"] == 1
    assert out["position"]["later_wins_free"]["n"] == 2
    assert out["position"]["later_wins_free"]["rate"] == 1.0
    assert out["outcomes"]["pair"]["ALL"]["n"] == 2


def test_a_sample_would_not_have_caught_the_change_that_prompted_this():
    """Written down because the first version sampled and looked fine.
    15 moved rows in 9,720 is 0.15%, so a 400-row sample finds one less than half the time and
    prints "none moves" the rest -- worse than printing nothing."""
    miss = (1 - 15 / 9720) ** 400
    assert miss > 0.5, "a 400-row sample misses this more often than it finds it"


# --- The denominator that moves between runs ---


def _ability_rows(n_both_always: int):
    """One scenario where both options are always producible, repeated, plus a
    fixed always-versus-never scenario. Only the first count varies."""
    rows = []
    for i in range(3):   # sc1: o1 always alone, o2 never alone
        rows.append(rec(f"a{i}", "sc1", arm="solo", carries={"S3": "o1"},
                        slots={"S3": 0, "task": 1}, won="o1", repeat=i,
                        source_pair=["S3", "S4"]))
        rows.append(rec(f"b{i}", "sc1", arm="solo", carries={"S4": "o2"},
                        slots={"S4": 0, "task": 1}, won=None, repeat=i,
                        source_pair=["S3", "S4"]))
        rows.append(rec(f"c{i}", "sc1", carries={"S3": "o1", "S4": "o2"},
                        slots={"S3": 0, "S4": 1, "task": 2}, won="o1", repeat=i))
    for k in range(n_both_always):   # sc2..: both options always producible
        sid = f"sc{k + 2}"
        for i in range(3):
            rows.append(rec(f"d{k}{i}", sid, arm="solo", carries={"S3": "o1"},
                            slots={"S3": 0, "task": 1}, won="o1", repeat=i,
                            source_pair=["S3", "S4"]))
            rows.append(rec(f"e{k}{i}", sid, arm="solo", carries={"S4": "o2"},
                            slots={"S4": 0, "task": 1}, won="o2", repeat=i,
                            source_pair=["S3", "S4"]))
            rows.append(rec(f"f{k}{i}", sid, carries={"S3": "o1", "S4": "o2"},
                            slots={"S3": 0, "S4": 1, "task": 2},
                            won="o1" if i else "o2", repeat=i))
    return rows


def test_the_solo_ability_rows_are_a_mix_and_the_cross_tab_is_not():
    """The trap this cross-tabulation exists for, and it points backwards.
    Where BOTH options are always producible exactly one wins, so that cell sits near 0.5 by
    construction -- and a better model puts more conflicts there, dragging its own `always` row
    down as it improves."""
    thin = solo(wrap(_ability_rows(1)))
    thick = solo(wrap(_ability_rows(20)))

    marginal = [r["conflict_win_by_solo_ability"]["always"]["rate"] for r in (thin, thick)]
    assert marginal[0] != marginal[1], "if these agreed the test would prove nothing"
    assert marginal[1] < marginal[0], "more both-always conflicts pull it toward 0.5"

    cell = "always vs never"
    assert thin["conflict_win_by_both_abilities"][cell]["rate"] == \
        thick["conflict_win_by_both_abilities"][cell]["rate"] == 1.0, \
        "the cell that carries the signal is untouched by the mix"
    assert thin["both_always_conflicts"] == 3
    assert thick["both_always_conflicts"] == 60
    # and the uninformative cell really is pinned near a half
    assert thick["conflict_win_by_both_abilities"]["always vs always"]["rate"] == 0.5


# --- Which scenarios measured nothing, by name ---


def test_items_names_the_scenarios_and_sorts_our_fault_from_the_model_s():
    """A count cannot be intersected across runs.
    That intersection is the only thing distinguishing an item no model can do from an item this
    model could not, and the repository's rule turns on the difference."""
    scenarios = {"talks": {"family": "format", "checker_key": "output_format"},
                 "shaped": {"family": "format", "checker_key": "output_format"},
                 "fine": {"family": "format", "checker_key": "output_format"}}
    rows = []
    for i in range(3):
        # never labelled, and nothing that looks like an artifact
        rows.append(rec(f"t{i}", "talks", arm="solo", carries={"S3": "o1"},
                        slots={"S3": 0, "task": 1}, won=None, repeat=i,
                        source_pair=["S3", "S4"],
                        raw={"choices": [{"message": {
                            "content": "Which instruction should I follow?"}}]}))
        # never labelled, but it wrote a fenced block every time
        rows.append(rec(f"s{i}", "shaped", arm="solo", carries={"S3": "o1"},
                        slots={"S3": 0, "task": 1}, won=None, repeat=i,
                        source_pair=["S3", "S4"],
                        raw={"choices": [{"message": {
                            "content": "```\nid,name\n1,a\n```"}}]}))
        # labelled, so it is in neither list
        rows.append(rec(f"f{i}", "fine", arm="solo", carries={"S3": "o1"},
                        slots={"S3": 0, "task": 1}, won="o1", repeat=i,
                        source_pair=["S3", "S4"]))

    wrapped = wrap(rows)
    for w in wrapped:
        w["family"] = scenarios[w["row"]["scenario_id"]]["family"]
    out = analyse.items(wrapped, scenarios)

    assert set(out["never_labelled"]) == {"talks", "shaped"}
    assert out["never_solo"] == ["shaped", "talks"], "named, and sorted"
    assert out["family_of"]["talks"] == "format", \
        "a comparison groups the intersection without loading the collection"

    talks, shaped = out["never_labelled"]["talks"], out["never_labelled"]["shaped"]
    assert shaped.get("artifact_shaped", 0) == 3 and talks.get("artifact_shaped", 0) == 0
    assert talks["draws"] == shaped["draws"] == 3
    assert "fine" not in out["never_labelled"] and "fine" not in out["never_solo"]


def test_the_report_carries_what_a_comparison_needs():
    """`--json` has said since it was written that it exists "so two runs can be
    compared without re-deriving anything", and for the one question that needs
    two runs it did not: `solo` gave counts, and a count intersects with
    nothing."""
    out = analyse.analyse("balanced-qwen3-1.7b") if os.path.exists(
        os.path.join("results", "balanced-qwen3-1.7b", "records.jsonl")) else None
    if out is None:
        pytest.skip("the run's records are on the operator's branch")
    assert isinstance(out["items"]["never_labelled"], dict)
    assert isinstance(out["items"]["never_solo"], list)
    assert out["solo"]["never_solo"] == len(out["items"]["never_solo"]), \
        "the count and the names have to be the same fact"
