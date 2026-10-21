"""Two or more finished runs, read side by side.
For the questions that are about the COLLECTION rather than a run: "this model could
not" is about the model, "no model can" is about the item. It decides nothing, drops
nothing, and refuses to be quiet when the runs were scored by different checkers."""

from __future__ import annotations

import argparse
import collections
import json
import os
from typing import Any, Mapping, Optional, Sequence

from ..logs import add_arguments, from_arguments, get_logger
from .analyse import scored_as

log = get_logger(__name__)


class CompareError(ValueError):
    """These files are not reports `analyse --json` wrote."""


# Each row is a number `analyse` already computed: a quantity that exists in two places drifts in one of them.
ROWS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("later wins, order free", ("position", "later_wins_free")),
    ("later wins, order pinned", ("position", "later_wins_pinned")),
    ("2nd line wins, one message", ("position", "second_line_wins_within_message")),
    ("conflict chose", ("outcomes", "pair", "ALL", "chose")),
    ("conflict chose, 2 sources", ("outcomes", "by_size", "2", "chose")),
    ("conflict chose, 3 sources", ("outcomes", "by_size", "3", "chose")),
    ("conflict chose, 5 sources", ("outcomes", "by_size", "5", "chose")),
    ("draws agree", ("repeats", "unanimous")),
    ("always beats never", ("solo", "conflict_win_by_both_abilities", "always vs never")),
    ("always beats sometimes",
     ("solo", "conflict_win_by_both_abilities", "always vs sometimes")),
    ("always vs always (~0.5 by construction)",
     ("solo", "conflict_win_by_both_abilities", "always vs always")),
)


def _dig(report: Mapping[str, Any], path: Sequence[str]) -> Any:
    node: Any = report
    for step in path:
        if not isinstance(node, Mapping) or step not in node:
            return None
        node = node[step]
    return node


def load_report(path: str) -> dict[str, Any]:
    """One `analyse --json` report, checked for the fields this reads."""
    if not os.path.exists(path):
        raise CompareError(f"{path}: no such report")
    try:
        with open(path, encoding="utf-8") as fh:
            report = json.load(fh)
    except ValueError as exc:
        raise CompareError(f"{path}: not JSON ({exc})") from exc
    if not isinstance(report, dict) or "run_id" not in report:
        raise CompareError(f"{path}: not a report from `analyse --json`")
    missing = [n for n in ("items", "scoring", "solo") if n not in report]
    if missing:
        raise CompareError(
            f"{path}: written by an older analyse -- no {', '.join(missing)} "
            f"section. Re-run: scripts/analyse.sh {report['run_id']} --json {path}")
    return report


def instruments(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Whether every run was scored by the same checkers. Read this first."""
    seen: dict[str, set] = {}
    unknown = []
    for rep in reports:
        s = rep.get("scoring") or {}
        if s.get("unknown"):
            unknown.append(rep["run_id"])
        for fp in (s.get("in_the_log") or {}):
            seen.setdefault(scored_as(fp), set()).add(rep["run_id"])
    return {
        "fingerprints": {fp: sorted(runs) for fp, runs in seen.items()},
        "unknown": unknown,
        "comparable": len(seen) <= 1 and not unknown,
    }


def _intersect(reports: Sequence[Mapping[str, Any]], field: str) -> list[str]:
    """Scenarios named by that field in EVERY report."""
    sets = []
    for rep in reports:
        named = _dig(rep, ("items", field)) or {}
        sets.append(set(named if isinstance(named, dict) else named))
    return sorted(set.intersection(*sets)) if sets else []


def families(reports: Sequence[Mapping[str, Any]], ids: Sequence[str]) -> dict[str, int]:
    """What family each named scenario is in, from whichever report says."""
    known: dict[str, str] = {}
    for rep in reports:
        known.update(_dig(rep, ("items", "family_of")) or {})
        for sid, v in (_dig(rep, ("items", "never_labelled")) or {}).items():
            known.setdefault(sid, v.get("family", "?"))
    return dict(collections.Counter(known.get(s, "?") for s in ids))


def compare(paths: Sequence[str]) -> dict[str, Any]:
    reports = [load_report(p) for p in paths]
    if len({r["run_id"] for r in reports}) != len(reports):
        raise CompareError("the same run twice: nothing is intersected by that")

    # A run with no solo arm names no scenario as never done solo, and intersecting it in would empty the list.
    solo_runs = [r for r in reports if _dig(r, ("solo", "has_solo_arm"))]
    never_solo = _intersect(solo_runs, "never_solo") if len(solo_runs) > 1 else []
    never_labelled = _intersect(reports, "never_labelled")

    # Of the items nothing could label anywhere, the ones where every model DID write artifact-shaped text on most draws -- ours to fix rather than the model's.
    shaped = []
    for sid in never_labelled:
        per_run = []
        for rep in reports:
            v = (_dig(rep, ("items", "never_labelled")) or {}).get(sid) or {}
            draws = v.get("draws") or 0
            per_run.append(draws and v.get("artifact_shaped", 0) * 2 >= draws)
        if per_run and all(per_run):
            shaped.append(sid)

    rows = []
    for label, path in ROWS:
        cells = [_dig(rep, path) for rep in reports]
        if all(c is None for c in cells):
            continue
        rows.append({"label": label, "cells": cells})

    return {
        "runs": [{"run_id": r["run_id"], "model": r.get("model"),
                  "environment": r.get("environment"), "design": r.get("design")}
                 for r in reports],
        "instruments": instruments(reports),
        "never_solo_measured_by": [r["run_id"] for r in solo_runs],
        "never_solo_everywhere": never_solo,
        "never_solo_by_family": families(reports, never_solo),
        "never_solo_per_run": {r["run_id"]: len(_dig(r, ("items", "never_solo")) or [])
                               if r in solo_runs else None for r in reports},
        "never_labelled_everywhere": never_labelled,
        "never_labelled_by_family": families(reports, never_labelled),
        "never_labelled_per_run": {
            r["run_id"]: len(_dig(r, ("items", "never_labelled")) or {})
            for r in reports},
        "artifact_shaped_everywhere": shaped,
        "artifact_shaped_by_family": families(reports, shaped),
        "side_by_side": rows,
    }


# --- Printing ---


def _cell(value: Any, width: int = 20) -> str:
    if value is None:
        return "-".rjust(width)
    if isinstance(value, Mapping) and "rate" in value:
        if not value.get("n"):
            return "-".rjust(width)
        return (f"{value['rate']:.3f} [{value['lo']:.2f},{value['hi']:.2f}]"
                ).rjust(width)
    if isinstance(value, float):
        return f"{value:.3f}".rjust(width)
    return str(value).rjust(width)


def render(out: Mapping[str, Any]) -> None:
    names = [r["run_id"] for r in out["runs"]]
    print("COMPARING")
    for r in out["runs"]:
        print(f"  {r['run_id']:<28s} {r['model']} at {r['environment']}, "
              f"design {r['design']}")

    inst = out["instruments"]
    print("\nWERE THEY SCORED BY THE SAME CHECKERS?")
    if inst["comparable"]:
        fp = next(iter(inst["fingerprints"]), "?")
        print(f"  yes -- every run carries {fp}")
    else:
        print("  *** NO. Every number below mixes the instrument with the model. ***")
        for fp, runs in inst["fingerprints"].items():
            print(f"    {fp}  {', '.join(runs)}")
        if inst["unknown"]:
            print(f"    no fingerprint at all: {', '.join(inst['unknown'])}")
        print("  Put them on one instrument before reading further:")
        print("      scripts/rescore.sh <run_id> --write")
        print("      scripts/analyse.sh <run_id> "
              "--log results/<run_id>/rescored.jsonl --json <run_id>.json")

    print("\nSIDE BY SIDE  (numbers analyse already computed; no test is done here)")
    print(f"  {'':40s}" + "".join(n[:20].rjust(21) for n in names))
    for row in out["side_by_side"]:
        print(f"  {row['label']:40s}" + "".join(_cell(c) + " " for c in row["cells"]))
    print("  Overlapping intervals are not a test and disjoint ones are not a")
    print("  result. The strengths fit, scripts/strengths.sh, is what can say so.")

    print("\nWHAT NO RUN COULD DO  (this is the part that is about the collection)")
    per_solo = ", ".join(f"{k} {'-' if v is None else v}"
                         for k, v in out["never_solo_per_run"].items())
    per_lab = ", ".join(f"{k} {v}" for k, v in out["never_labelled_per_run"].items())
    print(f"  never produced unopposed, per run:  {per_solo}")
    measured = out["never_solo_measured_by"]
    if len(measured) > 1:
        print(f"    ... on EVERY run with a solo arm:   {len(out['never_solo_everywhere']):4d}  "
              f"{out['never_solo_by_family']}")
    else:
        print(f"    ... only {len(measured)} run has a solo arm, so there is nothing to "
              f"intersect ('-' is a run with none)")
    print(f"  never labelled at all, per run:     {per_lab}")
    print(f"    ... on EVERY run:   {len(out['never_labelled_everywhere']):4d}  "
          f"{out['never_labelled_by_family']}")
    shaped = out["artifact_shaped_everywhere"]
    print(f"\n  OF THOSE, ARTIFACT-SHAPED ON MOST DRAWS OF EVERY RUN: {len(shaped)}  "
          f"{out['artifact_shaped_by_family']}")
    print("  Every model wrote something the format gate calls an artifact and no")
    print("  classifier would label it. That is a classifier that cannot read what")
    print("  it is handed, or a task whose honest answer is prose -- ours either way.")
    for sid in shaped[:20]:
        print(f"    {sid}")
    if len(shaped) > 20:
        print(f"    ... and {len(shaped) - 20} more; --json has every one")
    rest = len(out["never_labelled_everywhere"]) - len(shaped)
    print(f"\n  The other {rest} never produced an artifact anywhere, which is a")
    print("  model result and not a defect in the item.")
    print("\n  NOTHING HERE IS DROPPED OR REWRITTEN. It is a reading list. Two rungs")
    print("  of one family is also not 'every model': every run on disk is Qwen 3")
    print("  on one machine, so a third family is what would settle it.")


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m whowins.runner.compare",
        description="Two or more run reports side by side. Fits nothing, "
                    "tests nothing, drops nothing.")
    parser.add_argument("reports", nargs="+", metavar="REPORT.json",
                        help="reports written by `analyse --json`, two or more")
    parser.add_argument("--json", metavar="PATH", default=None,
                        help="also write every number and every named scenario "
                             "to this file")
    add_arguments(parser, progress=False)
    args = parser.parse_args(argv)
    written = from_arguments("compare", args)

    if len(args.reports) < 2:
        log.error("compare error: one report compares with nothing")
        return 2
    try:
        out = compare(args.reports)
    except (CompareError, OSError) as exc:
        log.error("compare error: %s", exc)
        return 2

    render(out)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, sort_keys=False)
            fh.write("\n")
        log.info("wrote %s", args.json)
        print(f"\nwritten: {args.json}")
    if written:
        log.info("this comparison's log: %s", written)
    return 0 if out["instruments"]["comparable"] else 1


if __name__ == "__main__":
    raise SystemExit(_main())
