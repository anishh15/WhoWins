"""Two runs read side by side. Everything here is synthetic.
The question is about the COLLECTION rather than any model, and a suite built on two real
Qwen 3 logs would be answering it for Qwen 3. The load-bearing tests are the two that
refuse."""

from __future__ import annotations

import json

import pytest

from whowins.runner import compare
from whowins.runner.compare import CompareError


FP_A = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
FP_B = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def report(run_id, *, model="m", fingerprint=FP_A, unknown=False,
           never_labelled=None, never_solo=(), families=None, solo_arm=True, **extra):
    """One `analyse --json` report, with only the fields compare reads."""
    named = never_labelled or {}
    fam = dict(families or {})
    for sid in list(named) + list(never_solo):
        fam.setdefault(sid, "format")
    return {
        "run_id": run_id, "model": model, "environment": "env",
        "design": "pairwise-balanced",
        "scoring": {"today": FP_A, "in_the_log": {} if unknown else {fingerprint: 9},
                    "unstamped": 9 if unknown else 0,
                    "agrees": not unknown and fingerprint == FP_A,
                    "unknown": unknown},
        "items": {"scenarios": 10, "never_labelled": named,
                  "never_labelled_by_family": {}, "never_solo": sorted(never_solo),
                  "never_solo_by_family": {}, "family_of": fam},
        "solo": {"has_solo_arm": solo_arm},
        **extra,
    }


def written(tmp_path, *reports):
    paths = []
    for rep in reports:
        path = tmp_path / f"{rep['run_id']}.json"
        path.write_text(json.dumps(rep), encoding="utf-8")
        paths.append(str(path))
    return paths


def item(draws=9, shaped=0, family="format", key="output_format"):
    return {"family": family, "key": key, "draws": draws,
            "artifact_shaped": shaped, "no_artifact": draws - shaped}


# --- Is the comparison legal at all ---


def test_two_runs_scored_by_different_checkers_are_not_comparable(tmp_path, capsys):
    """Not hypothetical: the 1.7B was scored before two checker holes were closed and the 14B after.
    It was caught by a person asking the right question, which is not a method that survives
    fifteen models."""
    paths = written(tmp_path,
                    report("old", fingerprint=FP_A),
                    report("new", fingerprint=FP_B))
    out = compare.compare(paths)
    assert out["instruments"]["comparable"] is False
    assert set(out["instruments"]["fingerprints"]) == {FP_A, FP_B}

    assert compare._main(paths) == 1, "a shell script has to be able to see this"
    printed = capsys.readouterr().out
    assert "*** NO." in printed
    assert "rescore" in printed, "it says how to fix it, not just that it is wrong"


def test_runs_whose_fingerprints_differ_by_a_docstring_alone_are_comparable(tmp_path, monkeypatch):
    """The other half of the rule: two fingerprints analyse knows to score alike are one."""
    from whowins.runner import analyse

    monkeypatch.setitem(analyse.SAME_SCORING, FP_B, FP_A)
    out = compare.compare(written(tmp_path, report("old", fingerprint=FP_B), report("new")))
    assert out["instruments"]["comparable"] is True


def test_a_run_with_no_fingerprint_is_unknown_and_not_assumed_equal(tmp_path):
    """Records written before the fingerprint existed cannot be checked. Silence
    is the one answer that must not read as agreement."""
    out = compare.compare(written(tmp_path,
                                  report("stamped"),
                                  report("older", unknown=True)))
    assert out["instruments"]["unknown"] == ["older"]
    assert out["instruments"]["comparable"] is False


def test_the_same_instrument_on_both_runs_compares(tmp_path, capsys):
    out = compare.compare(written(tmp_path, report("a"), report("b")))
    assert out["instruments"]["comparable"] is True
    assert compare._main(written(tmp_path, report("a"), report("b"))) == 0
    assert "yes -- every run carries" in capsys.readouterr().out


# --- What no run could do ---


def test_an_item_is_only_the_collection_s_fault_if_every_run_failed_it(tmp_path):
    """The whole point.
    `solo` reported 165 and 112 without saying which, so the intersection could only be taken
    with a throwaway script over two 40 MB logs -- and a count derived that way could not be
    reproduced the next day."""
    a = report("a", never_labelled={"both": item(), "only_a": item()},
               never_solo=("both", "only_a"))
    b = report("b", never_labelled={"both": item(), "only_b": item()},
               never_solo=("both", "only_b"))
    out = compare.compare(written(tmp_path, a, b))

    assert out["never_labelled_everywhere"] == ["both"]
    assert out["never_solo_everywhere"] == ["both"]
    assert out["never_labelled_per_run"] == {"a": 2, "b": 2}, \
        "per run it is two each, and that is exactly the misleading number"
    assert out["never_labelled_by_family"] == {"format": 1}


def test_a_run_with_no_solo_arm_is_left_out_of_the_solo_intersection(tmp_path, capsys):
    """The ladder sends no solo trial, so it names no scenario as never done solo, and
    intersecting it in printed "on EVERY run: 0" as if that were a finding."""
    a = report("a", never_solo=("both", "only_a"))
    b = report("b", never_solo=("both", "only_b"))
    ladder = report("ladder", solo_arm=False)
    out = compare.compare(written(tmp_path, a, b, ladder))
    assert out["never_solo_everywhere"] == ["both"]
    assert out["never_solo_measured_by"] == ["a", "b"]
    assert out["never_solo_per_run"] == {"a": 2, "b": 2, "ladder": None}

    compare._main(written(tmp_path, a, ladder))
    printed = capsys.readouterr().out
    assert "only 1 run has a solo arm" in printed
    assert "on EVERY run with a solo arm" not in printed


def test_an_artifact_on_every_run_is_ours_and_silence_everywhere_is_the_model_s(tmp_path):
    """The split that decides who has work to do.
    Nothing artifact-shaped is the model declining to produce one, which is a model result.
    Artifact-shaped and still unlabelled is a classifier that cannot read what it was handed."""
    a = report("a", never_labelled={"ours": item(shaped=8), "theirs": item(shaped=0),
                                    "mixed": item(shaped=8)})
    b = report("b", never_labelled={"ours": item(shaped=9), "theirs": item(shaped=1),
                                    "mixed": item(shaped=0)})
    out = compare.compare(written(tmp_path, a, b))

    assert out["artifact_shaped_everywhere"] == ["ours"]
    assert "theirs" in out["never_labelled_everywhere"]
    assert "mixed" not in out["artifact_shaped_everywhere"], \
        "shaped on one run and not the other decides nothing"


def test_the_side_by_side_derives_no_number_of_its_own(tmp_path):
    """Every row is a value analyse already computed. A quantity that exists in
    two places drifts in one of them, and the drifted one wins an argument
    sooner or later."""
    cell = {"hits": 8, "n": 10, "rate": 0.8, "lo": 0.5, "hi": 0.95}
    a = report("a", position={"later_wins_free": cell})
    b = report("b", position={"later_wins_free": dict(cell, rate=0.9)})
    out = compare.compare(written(tmp_path, a, b))
    row = next(r for r in out["side_by_side"] if r["label"] == "later wins, order free")
    assert [c["rate"] for c in row["cells"]] == [0.8, 0.9]
    # a section a run did not produce is dropped, not invented
    assert not any(r["label"] == "draws agree" for r in out["side_by_side"])


# --- Refusals ---


def test_one_report_compares_with_nothing(tmp_path):
    assert compare._main(written(tmp_path, report("a"))) == 2


def test_the_same_run_twice_is_refused(tmp_path):
    paths = written(tmp_path, report("a"))
    with pytest.raises(CompareError, match="the same run twice"):
        compare.compare(paths * 2)


def test_a_report_from_an_older_analyse_says_what_to_re_run(tmp_path):
    """A report without `items` is not a report this can read, and guessing an
    empty intersection from it would print "nothing failed everywhere" -- which
    is the most reassuring possible way to be wrong."""
    stale = report("a")
    stale.pop("items")
    with pytest.raises(CompareError, match="older analyse"):
        compare.compare(written(tmp_path, stale, report("b")))


def test_a_file_that_is_not_a_report_says_so(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{\"nope\": 1}", encoding="utf-8")
    with pytest.raises(CompareError, match="not a report"):
        compare.compare([str(bad), str(bad)])
    worse = tmp_path / "worse.json"
    worse.write_text("not json at all", encoding="utf-8")
    with pytest.raises(CompareError, match="not JSON"):
        compare.compare([str(worse), str(worse)])
    with pytest.raises(CompareError, match="no such report"):
        compare.compare([str(tmp_path / "absent.json"), str(bad)])
