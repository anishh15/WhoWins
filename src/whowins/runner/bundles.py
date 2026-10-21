"""Load bundles: the load cell's hand-written replicates, one task and one filler bank each.
A bundle is written by hand under data/LOAD-AUTHORING.md: six component scenarios, a task,
fillers and ten trials on the worked bundle's grid of n and k. This reads them into the
worked trials' shape; `whowins.validation.check_load` says whether one is fit to send."""

from __future__ import annotations

import functools
import glob
import os
from typing import Any, Mapping, Optional

from ..data import ROOT, read_json
from .fillers import KINDS, Filler, build_check
from .vocabulary import task_line

BUNDLE_DIR = os.path.join(ROOT, "data", "load")
LOAD_CELL = "load_vs_conflict"

GRID = ((2, 0, None), (2, 1, 2), (4, 0, None), (4, 1, 2), (8, 0, None), (8, 1, 2),
        (8, 3, 2), (12, 1, 2), (12, 6, 2), (12, 3, 3))
"""(n instructions, k conflict groups, group size) for each of a bundle's ten trials, in order:
the worked bundle's grid, load-01 to load-10, so a bundle is a replicate of it."""


def bundle_files() -> list[str]:
    return sorted(glob.glob(os.path.join(BUNDLE_DIR, "lb-*.json")))


def load_bundles() -> list[dict]:
    return [read_json(path) for path in bundle_files()]


@functools.lru_cache(maxsize=None)
def by_id(bundle_id: str) -> dict:
    for path in bundle_files():
        doc = read_json(path)
        if doc.get("bundle_id") == bundle_id:
            return doc
    raise KeyError(f"no load bundle {bundle_id!r} in {BUNDLE_DIR}")


def step_tools(bundle: Mapping[str, Any], scenarios: Mapping[str, Mapping[str, Any]]
               ) -> tuple[str, ...]:
    """The tools of the bundle's tool scenario: the step its task asks for before writing."""
    for sid in bundle["component_scenarios"]:
        scenario = scenarios.get(sid)
        if scenario and scenario.get("family") == "tool":
            return tuple(scenario.get("tools_available") or ())
    return ()


def filler_id(bundle_id: str, local: str) -> str:
    return f"{bundle_id}/{local}"


def bank_of(bundle: Mapping[str, Any], scenarios: Mapping[str, Mapping[str, Any]]
            ) -> dict[str, Filler]:
    """text -> Filler, each with the checker its kind builds for this bundle."""
    steps = step_tools(bundle, scenarios)
    out = {}
    for f in bundle["fillers"]:
        check = build_check(f["kind"], f.get("value"), bundle["project"], steps) \
            if f.get("kind") in KINDS else None
        out[f["text"]] = Filler(filler_id(bundle["bundle_id"], f["id"]), f["text"], check,
                                None if check else f"unknown kind {f.get('kind')!r}")
    return out


@functools.lru_cache(maxsize=None)
def bank(bundle_id: str) -> dict[str, Filler]:
    from .trials import load_scenarios
    return bank_of(by_id(bundle_id), load_scenarios())


def header(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """What `trials.reconstruct` reads from a load cell's header: the tools come from here."""
    return {"cell": LOAD_CELL, "bundle": bundle["bundle_id"], "task": bundle["task"],
            "component_scenarios": list(bundle["component_scenarios"])}


def as_trials(bundle: Mapping[str, Any]) -> list[dict]:
    """Each trial in the worked trials' shape: the lines are one system message, the task
    the user turn after it. Rendering is by code; every line was written by hand."""
    fillers = {f["text"]: filler_id(bundle["bundle_id"], f["id"]) for f in bundle["fillers"]}
    out = []
    for trial in bundle["trials"]:
        k = trial["k_conflict_groups"]
        out.append({
            "trial_id": trial["trial_id"], "cell": LOAD_CELL, "bundle": bundle["bundle_id"],
            "n_instructions": trial["n_instructions"], "k_conflict_groups": k,
            "group_size": trial.get("group_size"), "renderer": "plain_chat",
            "messages": [{"role": "system", "content": "\n".join(trial["lines"])},
                         {"role": "user", "content": task_line(bundle["task"])}],
            "conflict_groups": [dict(g) for g in trial["conflict_groups"]],
            "filler_used": [fillers[line] for line in trial["lines"] if line in fillers],
            "ground_truth": ground_truth(k),
            "notes": trial.get("notes", ""),
        })
    return out


def ground_truth(k: int) -> dict[str, Optional[str]]:
    if k == 0:
        return {"kind": "policy_defined", "intended_winner": "all_instructions_satisfiable",
                "policy": "Nothing conflicts. Every instruction can be obeyed at once."}
    return {"kind": "revealed_only", "intended_winner": None,
            "policy": "Same source for every line, so no policy picks a winner. Each group is "
                      "scored separately, and the conjunction too."}
