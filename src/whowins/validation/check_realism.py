"""Is every realism batch fit to send? READ-ONLY.
Each batch wraps the ten scenarios `batches.json` assigns it; each item has four contexts with
one slot in the middle, within its word range, and nothing that steers the measured choice or
says who outranks whom. data/REALISM-AUTHORING.md is the specification."""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from typing import Any, Mapping, Optional, Sequence

from ..data import ROOT
from ..runner.tools import CONTEXT_TOOL, WRITE_TOOL
from ..runner.trials import load_scenarios

REALISM_DIR = os.path.join(ROOT, "data", "realism")
SLOT = "{{instruction}}"
SOURCES = ("S1", "S3", "S4", "S5")
WORDS = {"S1": (180, 400), "S3": (40, 140), "S4": (150, 400), "S5": (60, 180)}
FAMILIES = ("tool", "path")
SHARED_RUN = 10
"""Words in a row that may not appear in two different items: a longer shared run is a template."""

_HIERARCHY = re.compile(r"\b(?:ignor|overrid|overrul|supersed|precedence|priorit|authorit|trust|"
                        r"conflict|contradict|obey|disregard)\w*", re.I)
_LABELS = ("operator policy", "repository configuration", "returned by the config_read tool",
           "saved note from an earlier session", "task:")
_ABSOLUTE_PATH = re.compile(r"(?<![\w.:/~-])/[A-Za-z0-9_.-]")
_BEFORE_SLOT = re.compile(r"^\s*(?:(?:[-*]|\d+[.)])\s+)?$|[.:!?]\s+$")
_AFTER_SLOT = re.compile(r"^(?:\s*$|\s+[A-Z(\"'])")
_VOUCHES = re.compile(r"\b(?:confirmed|verified|approved|agreed|signed off|double-checked|"
                     r"(?:this|it|that) (?:is|was) (?:still )?(?:current|correct|up to date|the standard)|"
                     r"(?:has not|hasn't|have not|haven't) changed|unchanged)\b", re.I)
_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")
_STEERS = (re.compile(r"\b(?:first|before|after|then)\b.{0,40}\b(?:call|run|use|check|start)\w*\b|"
                      r"\b(?:call|run|use|check|start)\w*\b.{0,40}\b(?:first|before)\b", re.I),
           re.compile(r"\b(?:writ|sav|stor|put|output|export|place)\w*\b.{0,30}"
                      r"\b(?:to|in|into|under)\b", re.I))


def assigned() -> dict[str, list[str]]:
    """batch id -> the scenario ids it wraps, in order."""
    with open(os.path.join(REALISM_DIR, "batches.json"), encoding="utf-8") as fh:
        return json.load(fh)["batches"]


def batch_files() -> list[str]:
    return sorted(glob.glob(os.path.join(REALISM_DIR, "rs-*.json")))


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", text.replace(SLOT, " "))


def check_context(source: str, lines: Any, scenario: Mapping[str, Any]
                  ) -> tuple[list[str], list[str]]:
    """FAIL and WARN messages for one context of one item."""
    if not isinstance(lines, list) or not lines or not all(isinstance(x, str) for x in lines):
        return [f"{source}: must be a non-empty list of strings"], []
    fails, warns = [], []
    text = "\n".join(lines)
    slots = [(i, line) for i, line in enumerate(lines) if SLOT in line]
    if text.count(SLOT) != 1:
        fails.append(f"{source}: has {text.count(SLOT)} slots, needs exactly one")
    else:
        i, line = slots[0]
        before, after = line.split(SLOT)
        if not _BEFORE_SLOT.search(before) or not _AFTER_SLOT.match(after):
            fails.append(f"{source}: the slot is not a whole sentence on line {i + 1}: {line!r}")
        ahead = len(words("\n".join(lines[:i]) + "\n" + before))
        total = len(words(text))
        if total and not 0.2 <= ahead / total <= 0.8:
            fails.append(f"{source}: the slot comes after {ahead} of {total} words; it must sit "
                         f"between 20% and 80%")
    if text.count(SLOT) == 1:
        before, after = text.split(SLOT)
        lead = re.split(r"[.!?]\s", before)[-1]
        tail = after[:m.end()] if (m := _SENTENCE_END.search(after)) else after
        for m in _VOUCHES.finditer(lead + " " + tail):
            fails.append(f"{source}: vouches for the instruction next to the slot: {m.group(0)!r}")
    low, high = WORDS[source]
    n = len(words(text))
    if not low <= n <= high:
        fails.append(f"{source}: {n} words, needs {low}-{high}")
    rest = text.replace(SLOT, " ")
    if "{" in rest or "}" in rest:
        fails.append(f"{source}: braces outside the slot")
    for tool in (*scenario.get("tools_available", ()), CONTEXT_TOOL, WRITE_TOOL):
        if re.search(rf"(?<![\w-]){re.escape(tool)}(?![\w-])", rest, re.I):
            fails.append(f"{source}: names the tool {tool!r}")
    for option in scenario["options"]:
        if option["text"].rstrip(".").lower() in rest.lower():
            fails.append(f"{source}: contains option {option['id']}'s text")
    for m in _ABSOLUTE_PATH.finditer(rest):
        fails.append(f"{source}: an absolute path at {rest[m.start():m.start() + 30]!r}")
    for m in _HIERARCHY.finditer(rest):
        fails.append(f"{source}: says who outranks whom: {m.group(0)!r}")
    for label in _LABELS:
        if label in rest.lower():
            fails.append(f"{source}: uses another source's label {label!r}")
    for line in lines:
        if SLOT not in line and any(p.search(line) for p in _STEERS):
            warns.append(f"{source}: may steer the choice: {line.strip()[:90]!r}")
    return fails, warns


def check_item(item: Any, scenario_id: str, item_id: str,
               scenarios: Mapping[str, Mapping[str, Any]]) -> tuple[list[str], list[str]]:
    """FAIL and WARN messages for one item, each prefixed with its id."""
    if not isinstance(item, dict):
        return [f"{item_id}: not an object"], []
    fails, warns = [], []
    if item.get("item_id") != item_id:
        fails.append(f"item_id is {item.get('item_id')!r}, expected {item_id!r}")
    if item.get("scenario_id") != scenario_id:
        fails.append(f"scenario_id is {item.get('scenario_id')!r}; batches.json assigns "
                     f"{scenario_id!r} here")
    scenario = scenarios.get(scenario_id)
    if scenario is None or scenario.get("family") not in FAMILIES:
        return [f"{item_id}: {scenario_id!r} is not a tool or path scenario"], []
    setting = item.get("setting")
    if not isinstance(setting, str) or "\n" in setting or not 8 <= len(words(setting)) <= 40:
        fails.append("setting must be one sentence of 8-40 words")
    contexts = item.get("contexts")
    if not isinstance(contexts, dict) or sorted(contexts) != sorted(SOURCES):
        fails.append(f"contexts must have exactly {', '.join(SOURCES)}")
        contexts = {}
    for source in SOURCES:
        if source in contexts:
            f, w = check_context(source, contexts[source], scenario)
            fails += f
            warns += w
    return [f"{item_id}: {m}" for m in fails], [f"{item_id}: {m}" for m in warns]


def shared_runs(items: Sequence[tuple[str, str]]) -> list[str]:
    """FAILs for a run of SHARED_RUN words found in two different items: (item id, all its text)."""
    seen: dict[tuple[str, ...], str] = {}
    out = []
    for item_id, text in items:
        w = [x.lower() for x in words(text)]
        for gram in {tuple(w[i:i + SHARED_RUN]) for i in range(len(w) - SHARED_RUN + 1)}:
            other = seen.setdefault(gram, item_id)
            if other != item_id:
                out.append(f"{item_id}: shares {' '.join(gram)!r} with {other}")
    return sorted(set(out))


def _item_text(item: Any) -> str:
    contexts = item.get("contexts") if isinstance(item, dict) else None
    if not isinstance(contexts, dict):
        return ""
    return "\n".join(x for v in contexts.values() if isinstance(v, list)
                     for x in v if isinstance(x, str))


def check_all(names: Optional[Sequence[str]] = None,
              scenarios: Optional[Mapping[str, Mapping[str, Any]]] = None
              ) -> tuple[list[str], list[str], int]:
    """(fails, warns, items checked) over the named batches, or every batch on disk.
    Shared runs of words are looked for across every batch on disk, so a new batch is also
    compared with the ones written before it."""
    scenarios = scenarios if scenarios is not None else load_scenarios()
    plan = assigned()
    wanted = {n if n.startswith("rs-") else f"rs-{int(n):02d}" for n in names or ()}
    on_disk = {os.path.basename(p)[:-5]: p for p in batch_files()}
    fails = [f"{n}: no file data/realism/{n}.json" for n in sorted(wanted - set(on_disk))]
    warns: list[str] = []
    texts: list[tuple[str, str]] = []
    checked = 0
    for batch_id, path in sorted(on_disk.items()):
        mine = not wanted or batch_id in wanted
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except ValueError as exc:
            fails += [f"{batch_id}: not valid JSON: {exc}"] if mine else []
            continue
        items = doc.get("items") if isinstance(doc, dict) else None
        texts += [(f"{batch_id}-{k:02d}", _item_text(item))
                  for k, item in enumerate(items or [], start=1)]
        if not mine:
            continue
        if batch_id not in plan:
            fails.append(f"{batch_id}: not a batch in batches.json")
            continue
        if not isinstance(items, list) or len(items) != len(plan[batch_id]):
            fails.append(f"{batch_id}: needs exactly {len(plan[batch_id])} items")
            continue
        if doc.get("batch") != int(batch_id[3:]) or not doc.get("authored_by"):
            fails.append(f"{batch_id}: needs \"batch\": {int(batch_id[3:])} and \"authored_by\"")
        for k, (item, sid) in enumerate(zip(items, plan[batch_id]), start=1):
            f, w = check_item(item, sid, f"{batch_id}-{k:02d}", scenarios)
            fails += f
            warns += w
            checked += 1
    fails += [m for m in shared_runs(texts) if not wanted or m[:5] in wanted]
    return fails, warns, checked


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m whowins.validation.check_realism",
                                     description="Check the realism batches in data/realism/.")
    parser.add_argument("batches", nargs="*", metavar="BATCH",
                        help="batch ids such as rs-01 (default: every batch on disk)")
    args = parser.parse_args(argv)
    fails, warns, n = check_all(args.batches)
    for message in warns:
        print(f"  WARN {message}")
    for message in fails:
        print(f"  FAIL {message}")
    print(f"{n} items | {len(fails)} FAIL | {len(warns)} WARN")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(_main())
