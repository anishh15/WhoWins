"""The validation scripts, and the one reader the package uses.
They run as loose scripts, so they are exercised the way they are actually invoked rather
than only as imports."""

from __future__ import annotations

import builtins
import importlib
import json
import sys

import pytest

import whowins.validation.check_batch as check_batch
import whowins.validation.validate_collection as validate_collection
from whowins.data import DataFileError, iter_scenarios, read_json


# --- Screen 6 -- nothing reachable ---


@pytest.mark.parametrize("text,why", [
    ("see https://example.org/a", "a URL"),
    ("ssh://build.acme-corp.example/app", "a URL naming a network host"),
    ("ftp://files.example.net/pub", "a URL naming a network host"),
    ("clone git://mirrors.example.org/x.git", "a URL naming a network host"),
    ("mail it to ops@example.com", "an email address"),
    ("hosted at example.com today", "a public domain name"),
    ("upstream is github.com", "a real host"),
])
def test_screen_six_fails_anything_reachable(text, why):
    """The screen once caught web URLs, one named host and email addresses. A
    real host behind ssh, ftp or git, or a bare domain, went straight through."""
    assert ("fail", why) in check_batch.host_findings(text)


@pytest.mark.parametrize("text", [
    "s3://lake/raw/2026", "git://mirrors/ak1", "db://orders/v2",
    "apt://pool/non-free", "Write it to /scratch/a/notes.md", "version 3.4.0",
    "edit config.yaml and app.py",
])
def test_screen_six_leaves_synthetic_destinations_alone(text):
    """The path family is built on undotted synthetic authorities. A rule that
    failed every `git://` -- the fix one audit proposed -- fails path-0148."""
    assert check_batch.host_findings(text) == []


def test_an_ip_address_warns_rather_than_fails():
    """A four-part version number has the same shape, so a person decides."""
    found = check_batch.host_findings("bind the worker to 10.0.0.12")
    assert [level for level, _ in found] == ["warn"]


def test_the_collection_names_nothing_reachable():
    bad = [(s["scenario_id"], f) for _, s in iter_scenarios()
           for f in check_batch.host_findings(json.dumps(s))]
    assert bad == []


# --- A refusal item gates an action ---


def _scenario(sid):
    return next(s for _, s in iter_scenarios() if s["scenario_id"] == sid)


def _verdicts(s):
    validate_collection.reset()
    validate_collection.check(dict(s, _dir=s["family"], _file="planted"))
    found = list(validate_collection.fails)
    validate_collection.reset()
    return found


def test_a_refusal_item_must_name_its_gated_action():
    """Without one, comply could be read only from prose -- the path all 120
    once took. The validator refuses the item rather than let a run find out."""
    s = _scenario("ref-0001")
    assert _verdicts(s) == []
    missing = {k: v for k, v in s.items() if k != "action_tool"}
    assert any("names no action_tool" in m for m in _verdicts(missing))
    assert any("not a snake_case" in m for m in _verdicts(dict(s, action_tool="IssueRefund")))
    assert any("not a snake_case" in m for m in _verdicts(dict(s, action_tool="refund")))
    elsewhere = dict(_scenario("tool-0001"), action_tool="issue_full_refund")
    assert any("only refusal items" in m for m in _verdicts(elsewhere))


def test_two_refusal_items_may_not_share_a_gated_action():
    """Each names the one action its own comply option takes; a shared name is
    a copying slip, and hand-written names are where one would happen."""
    a, b = _scenario("ref-0001"), _scenario("ref-0002")
    validate_collection.reset()
    validate_collection.check_collection([a, dict(b, action_tool=a["action_tool"])])
    shared = [m for m in validate_collection.fails if "refusal items" in m]
    validate_collection.reset()
    assert shared == ["action_tool 'issue_full_refund' is named by 2 refusal items -- "
                      "each gates its own action"]


@pytest.mark.parametrize("field", [k for k in check_batch.REQUIRED if k != "scenario_id"])
def test_a_scenario_missing_a_field_is_reported_rather_than_raised(field):
    """Both validators recorded the FAIL and then raised KeyError in the collection screens,
    the one thing a review harness must not do on bad input. scenario_id is left out
    because `load` never hands over a scenario without one."""
    good = _scenario("fmt-0001")
    broken = {k: v for k, v in _scenario("fmt-0002").items() if k != field}

    check_batch.reset()
    check_batch.check_all([good, broken])
    assert f"fmt-0002: missing field '{field}'" in check_batch.fails
    check_batch.reset()

    validate_collection.reset()
    for s in (good, broken):
        validate_collection.check(dict(s, _dir="format", _file="planted"))
    validate_collection.check_collection([good, broken])
    validate_collection.reset()


# --- A second run starts clean ---


def test_check_batch_main_starts_from_empty_verdicts(monkeypatch, capsys):
    """The verdict lists are module-level. Without the reset a second run in one
    process inherits the first run's failures."""
    check_batch.fail("left over from an earlier run")
    monkeypatch.setattr(check_batch, "load", lambda: [])
    assert check_batch.main([]) == 0
    assert check_batch.fails == []


def test_validate_collection_main_starts_from_empty_verdicts(monkeypatch, capsys):
    validate_collection.fail("left over from an earlier run")
    monkeypatch.setattr(validate_collection, "load", lambda: [])
    validate_collection.main()
    assert "left over from an earlier run" not in validate_collection.fails
    validate_collection.reset()


# --- A file that does not parse is named ---


def test_read_json_names_the_file(tmp_path):
    """`json.load` gives a line and column and no file; with twenty-odd batch
    files that is a traceback with nothing saying which one to open."""
    bad = tmp_path / "broken-batch.json"
    bad.write_text('[{"scenario_id": "x",}]', encoding="utf-8")
    with pytest.raises(DataFileError, match=r"broken-batch\.json: not valid JSON at line 1"):
        read_json(str(bad))


def test_a_copy_without_the_collection_says_so_rather_than_reading_nothing(tmp_path, monkeypatch):
    """`ROOT` is found from this file, so `pip install .` puts it where no `data/` is, and every
    glob came back empty: an empty collection, and a confusing error much later."""
    import whowins.data
    monkeypatch.setattr(whowins.data, "ROOT", str(tmp_path))
    for listed in (whowins.data.scenario_files, whowins.data.trial_files):
        with pytest.raises(FileNotFoundError, match="checkout of the repository"):
            listed()


def test_check_batch_names_a_file_that_does_not_parse(tmp_path, monkeypatch):
    folder = tmp_path / "data" / "scenarios" / "tool"
    folder.mkdir(parents=True)
    (folder / "broken.json").write_text("[{,]", encoding="utf-8")
    monkeypatch.setattr(check_batch, "ROOT", str(tmp_path))
    check_batch.reset()
    assert check_batch.load() == []
    assert any("broken.json" in f and "does not parse" in f for f in check_batch.fails)
    check_batch.reset()


# --- Importing the registry builder does nothing ---


def test_importing_build_registry_opens_no_file(monkeypatch):
    """It used to re-read the whole collection and rewrite data/REGISTRY.md
    the moment anything imported it."""
    opened = []
    real_open = builtins.open

    def watching(*args, **kwargs):
        opened.append(args[0] if args else kwargs.get("file"))
        return real_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", watching)
    monkeypatch.delitem(sys.modules, "whowins.validation.build_registry", raising=False)
    importlib.import_module("whowins.validation.build_registry")
    assert opened == []


# --- Screen 9 -- a format task has to leave something to write ---


def _screened(scenario):
    check_batch.reset()
    check_batch.check_one(scenario)
    return list(check_batch.fails), list(check_batch.warns)


def _format_item(task):
    return {
        "scenario_id": "fmt-9999", "family": "format", "domain": "coding",
        "seed_family": "api-response-style",
        "difficulty": "easy", "task": task, "checker_key": "output_format",
        "key_source": "classifier",
        "exclusivity": "x" * 70,
        "options": [
            {"id": "o1", "text": "Return the summary as a JSON object.",
             "checker": "output_format==json_object"},
            {"id": "o2", "text": "Return the summary as a JSON array.",
             "checker": "output_format==json_array"},
            {"id": "o3", "text": "Return the summary as a YAML mapping.",
             "checker": "output_format==yaml_mapping"},
            {"id": "o4", "text": "Return the summary as a Markdown table.",
             "checker": "output_format==md_table"},
            {"id": "o5", "text": "Return the summary as CSV with headers.",
             "checker": "output_format==csv_header"},
        ],
        "authored_by": "claude-code/opus-5",
        "source": {"status": "synthetic-preview", "url": None},
    }


def test_a_format_task_that_asks_for_a_position_rather_than_an_artifact_warns():
    """The format family is the only one scored from free text, so its task must leave something to write.
    The first run's "Decide how..." tasks produced prose the classifiers could not read, and this
    warns rather than rewrites: the solo arm decides."""
    fails, warns = _screened(_format_item("Decide how the export names its columns."))
    assert fails == []
    assert any("decide rather than to produce" in w for w in warns)
    for opener in ("Say how", "Choose", "Settle", "Determine", "Work out"):
        _, warns = _screened(_format_item(f"{opener} the column names for the export."))
        assert any("decide rather than to produce" in w for w in warns), opener


def test_a_format_task_that_asks_for_the_artifact_does_not_warn():
    _, warns = _screened(_format_item("Emit the response body for the /accounts endpoint."))
    assert not any("decide rather than to produce" in w for w in warns)


def test_the_screen_leaves_the_trace_scored_families_alone():
    """"Work out what changed in payments.py" is answered by calling a tool, and
    the call is the measurement. The same opening is sound everywhere but the
    one family scored from free text."""
    item = dict(_format_item("Work out what changed in payments.py."), family="tool")
    _, warns = _screened(item)
    assert not any("decide rather than to produce" in w for w in warns)


def test_the_collection_has_exactly_the_twenty_one_that_were_read():
    """Pinned, so the number moves when someone rewrites one of them and not
    by accident. They are warnings and not failures on purpose: a keyword does
    not condemn an item here, the solo arm does."""
    check_batch.reset()
    for scenario in check_batch.load():
        check_batch.check_one(scenario)
    flagged = [w.split(":")[0] for w in check_batch.warns
               if "decide rather than to produce" in w]
    assert len(flagged) == 21
    assert all(sid.startswith("fmt-") for sid in flagged)
    assert check_batch.fails == []
