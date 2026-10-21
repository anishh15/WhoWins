"""Which kind of constraint each scenario measures.
The `axis` split holds out one kind at a time, so it needs a level above the checker key.
That level is not a field and cannot be invented here, so it is derived from where each
key's implementation lives -- the source is the only record of it."""

from __future__ import annotations

import importlib
import inspect
import re
from typing import Sequence

FORMAT_MODULES = (
    "surface", "wire", "editorial", "syntax", "values",
    "tooling", "prose", "domain", "structural",
)

TRACE_FAMILIES = ("tool", "path", "ordering", "refusal")

WEAK_AXES = frozenset({"structural"})
"""Axes grouped by how the artifact is read rather than by what it is about.
Reported alongside their results so a reader can discount them."""


class AxisResolutionError(RuntimeError):
    """A format key did not resolve to exactly one classifier module."""


def format_key_modules() -> dict[str, str]:
    """checker key -> the module whose source defines it.
    Raises rather than guessing: a key found in two modules or in none means the search has
    gone stale, and a stale mapping silently corrupts the folds."""
    from ..checkers.fmt._lib import SPEC_LABELS

    sources = {
        name: inspect.getsource(importlib.import_module(f"..checkers.fmt.{name}", __package__))
        for name in FORMAT_MODULES
    }

    owner, unresolved = {}, {}
    for key in SPEC_LABELS:
        pattern = re.compile(r"[\"']" + re.escape(key) + r"[\"']")
        hits = [name for name, src in sources.items() if pattern.search(src)]
        if len(hits) == 1:
            owner[key] = hits[0]
        else:
            unresolved[key] = hits

    if unresolved:
        raise AxisResolutionError(
            f"{len(unresolved)} format keys did not resolve to one module: "
            f"{dict(list(unresolved.items())[:5])}. The source search in "
            f"axes.format_key_modules() has gone stale; fix it rather than "
            f"letting scenarios fall into the wrong fold."
        )
    return owner


def axis_of(collection: Sequence[dict]) -> dict[str, str]:
    """scenario id -> its constraint axis.

    Format scenarios take their classifier module; the four trace families each
    have one checker key, so the family *is* the axis there."""
    modules = format_key_modules()
    out = {}
    for s in collection:
        if s["family"] == "format":
            out[s["scenario_id"]] = modules[s["checker_key"]]
        else:
            out[s["scenario_id"]] = s["family"]
    return out


def axis_level(axis: str) -> str:
    """Which granularity a fold sits at.
    The two are not comparable in size -- `values` is 11 scenarios and `tool` is 240 -- so
    results are reported per fold with the level attached, never pooled."""
    return "family" if axis in TRACE_FAMILIES else "format-module"
