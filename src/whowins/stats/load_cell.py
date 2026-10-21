"""The load cell: does accuracy fall with conflict or with the number of instructions?
Each rate is read per trial of the grid (n instructions, k conflict groups), as a mean over
bundles, the replicates. Contrasts pair the two trials of one bundle. Exploratory, as the
whole main run is; docs/codebase/16_load_bundles_and_tiers.md says what each block answers."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from statistics import mean
from typing import Any, Iterable, Mapping, Optional, Sequence

from . import paired

LOAD_CELL = "load_vs_conflict"
WORKED = "worked"                   # the bundle of load-01 to load-10, whose trials name none
FAMILIES = {"tool": "tool", "path": "path", "fmt": "format"}
MEASURES = ("groups", "conjunction", "fillers", "all_satisfied")
Cell = tuple[int, int, Optional[int]]  # (n instructions, k conflict groups, group size)

CONTRASTS: tuple[tuple[str, str, str, Cell, Cell], ...] = (
    ("conflict", "all_satisfied", "n=2: one conflict against none", (2, 1, 2), (2, 0, None)),
    ("conflict", "all_satisfied", "n=4: one conflict against none", (4, 1, 2), (4, 0, None)),
    ("conflict", "all_satisfied", "n=8: one conflict against none", (8, 1, 2), (8, 0, None)),
    ("conflict", "all_satisfied", "n=8: three conflicts against none", (8, 3, 2), (8, 0, None)),
    ("conflict", "all_satisfied", "n=12: six conflicts against one", (12, 6, 2), (12, 1, 2)),
    ("load", "all_satisfied", "k=0: n=4 against n=2", (4, 0, None), (2, 0, None)),
    ("load", "all_satisfied", "k=0: n=8 against n=2", (8, 0, None), (2, 0, None)),
    ("load", "groups", "k=1: n=12 against n=2", (12, 1, 2), (2, 1, 2)),
    ("choice", "groups", "n=8: three groups against one", (8, 3, 2), (8, 1, 2)),
    ("choice", "groups", "n=12: six groups against one", (12, 6, 2), (12, 1, 2)),
    ("choice", "groups", "n=12: groups of three against pairs", (12, 3, 3), (12, 6, 2)),
)
"""(block, measure, what it asks, the trial, the trial it is set against), on the bundles'
grid. Conflict at matched length is the choice account; length at fixed conflict is the load
account; more groups of one size tells a failure per choice from a failure of the conjunction."""


class LoadError(ValueError):
    """Records that cannot answer the load cell's questions as asked."""


@dataclass(frozen=True)
class LoadDraw:
    """One usable reply to one load trial.
    `groups` is (group id, family, chose one of its own members) per conflict group;
    `fillers` is whether each judged filler line was kept, a filler with no verdict left out;
    `all_satisfied` is the record's whole-task verdict, None where a filler went unjudged."""
    bundle: str
    cell: Cell
    groups: tuple[tuple[str, str, bool], ...]
    fillers: tuple[bool, ...]
    all_satisfied: Optional[bool]


def from_records(rows: Iterable[Mapping[str, Any]]) -> tuple[list[LoadDraw], dict[str, int]]:
    """A run's load trials as draws, and what was left out and why.
    A group counts as chosen only when the reply did one of that group's own instructions;
    off-menu, unresolved, several or none is not. An unusable reply says nothing of the model."""
    out, skipped = [], {}
    for row in rows:
        meta = row.get("meta") or {}
        if meta.get("cell") != LOAD_CELL:
            continue
        if row.get("usable") is False:
            skipped["unusable reply"] = skipped.get("unusable reply", 0) + 1
            continue
        groups = tuple((g["group_id"], FAMILIES.get(str(g["scenario_id"]).split("-")[0], "other"),
                        g.get("behaviour") == "chose") for g in row.get("groups") or ())
        fillers = tuple(f["result"] == "satisfied" for f in row.get("fillers") or ()
                        if f.get("result") in ("satisfied", "violated"))
        out.append(LoadDraw(bundle=meta.get("bundle") or WORKED,
                            cell=(int(meta["n_instructions"]), int(meta["k_conflict_groups"]),
                                  meta.get("group_size")),
                            groups=groups, fillers=fillers,
                            all_satisfied=row.get("all_satisfied")))
    return out, skipped


def counts(draw: LoadDraw, measure: str) -> tuple[int, int]:
    """(kept, out of) for one draw: groups chosen of k, all groups chosen, fillers kept of
    those judged, or the whole task. (0, 0) where the draw says nothing on that measure."""
    if measure == "groups":
        return sum(c for _, _, c in draw.groups), len(draw.groups)
    if measure == "conjunction":
        return (int(all(c for _, _, c in draw.groups)), 1) if draw.groups else (0, 0)
    if measure == "fillers":
        return sum(draw.fillers), len(draw.fillers)
    if measure == "all_satisfied":
        return (0, 0) if draw.all_satisfied is None else (int(draw.all_satisfied), 1)
    raise LoadError(f"no measure {measure!r}; the measures are {', '.join(MEASURES)}")


def _per_bundle(draws: Iterable[LoadDraw], measure: str) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for d in draws:
        kept, total = counts(d, measure)
        if total:
            k0, t0 = out.get(d.bundle, (0, 0))
            out[d.bundle] = (k0 + kept, t0 + total)
    return out


def _bundles(result: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if result is not None:
        result["bundles"] = result.pop("units")
    return result


def estimate(draws: Sequence[LoadDraw], measure: str, alpha: float = 0.05
             ) -> Optional[dict[str, Any]]:
    """A rate as the mean over bundles, each bundle weighted equally, or None if no draw has it.
    The interval is the wider of a t interval over bundles and a Wilson interval over every
    draw, so a trial on which every bundle agrees still shows the noise of a few draws."""
    return _bundles(paired.rate(_per_bundle(draws, measure), alpha))


def contrast(draws: Sequence[LoadDraw], measure: str, cell: Cell, against: Cell,
             alpha: float = 0.05) -> Optional[dict[str, Any]]:
    """The rate on `cell` minus the rate on `against`, paired within each bundle that has both.
    The interval is the wider of a t interval over the bundles' differences and Newcombe's
    interval over every draw, for the reason `estimate` gives."""
    return _bundles(paired.difference(_per_bundle((d for d in draws if d.cell == cell), measure),
                                      _per_bundle((d for d in draws if d.cell == against), measure),
                                      alpha))


def against_independence(draws: Sequence[LoadDraw], cell: Cell, alpha: float = 0.05
                         ) -> Optional[dict[str, Any]]:
    """How far the share of replies choosing in every group sits above the product of the
    groups' own rates, per bundle, then averaged. Near zero, the groups fail independently;
    above it, failures come together. None for a trial with fewer than two groups."""
    observed, product = [], []
    for bundle in sorted({d.bundle for d in draws if d.cell == cell}):
        mine = [d for d in draws if d.cell == cell and d.bundle == bundle]
        if len(mine[0].groups) < 2:
            return None
        chosen: dict[str, list[bool]] = {}
        for d in mine:
            for gid, _, c in d.groups:
                chosen.setdefault(gid, []).append(c)
        observed.append(mean(all(c for _, _, c in d.groups) for d in mine))
        product.append(math.prod(sum(v) / len(v) for v in chosen.values()))
    if not observed:
        return None
    diffs = [o - p for o, p in zip(observed, product)]
    # With three draws a trial every bundle may sit on its product; zero width would overclaim.
    spread = paired.over_units(diffs, alpha) if len(set(diffs)) > 1 else None
    return {"observed": mean(observed), "product": mean(product), "difference": mean(diffs),
            "low": spread[0] if spread else None, "high": spread[1] if spread else None,
            "bundles": len(diffs)}


def by_family(draws: Sequence[LoadDraw], alpha: float = 0.05) -> dict[str, Any]:
    """The share of groups chosen, per family of the scenario the group came from."""
    out = {}
    for family in sorted({f for d in draws for _, f, _ in d.groups}):
        only = [LoadDraw(d.bundle, d.cell,
                         tuple(g for g in d.groups if g[1] == family), d.fillers,
                         d.all_satisfied) for d in draws]
        out[family] = estimate(only, "groups", alpha)
    return out


def summarise(draws: Sequence[LoadDraw], alpha: float = 0.05) -> dict[str, Any]:
    """Every number the load cell reports, from its draws."""
    if not draws:
        raise LoadError("no load trial among these records")
    cells = sorted({d.cell for d in draws}, key=lambda c: (c[0], c[1], c[2] or 0))
    trials = []
    for cell in cells:
        mine = [d for d in draws if d.cell == cell]
        trials.append({"n": cell[0], "k": cell[1], "size": cell[2], "draws": len(mine),
                       "unjudged": sum(d.all_satisfied is None for d in mine),
                       **{m: estimate(mine, m, alpha) for m in MEASURES},
                       "independence": against_independence(draws, cell, alpha)})
    contrasts = []
    for block, measure, asks, cell, against in CONTRASTS:
        c = contrast(draws, measure, cell, against, alpha)
        if c is not None:
            contrasts.append({"block": block, "measure": measure, "asks": asks, **c})
    return {"bundles": sorted({d.bundle for d in draws}), "draws": len(draws), "alpha": alpha,
            "trials": trials, "contrasts": contrasts, "families": by_family(draws, alpha)}


def run_load_cell(run_id: str, log_path: Optional[str] = None, *,
                  alpha: float = 0.05) -> dict[str, Any]:
    """The load cell of one run, from its records."""
    from ..runner.analyse import read_records
    from ..runner.batch import default_log, log_file

    path = log_path or default_log(run_id)
    if log_file(path) is None:
        raise LoadError(f"{path}: no log to read")
    draws, skipped = from_records(read_records(path))
    if not draws:
        raise LoadError(f"{run_id}: no load trial in that log")
    return {"run_id": run_id, "left_out": skipped, **summarise(draws, alpha)}


def _rate(e: Optional[Mapping[str, Any]]) -> str:
    return "-" if e is None else f"{e['rate']:.2f} [{e['low']:.2f}, {e['high']:.2f}]"


def _diff(e: Mapping[str, Any]) -> str:
    if e["low"] is None:
        return f"{e['difference']:+.2f} (no spread over bundles)"
    return f"{e['difference']:+.2f} [{e['low']:+.2f}, {e['high']:+.2f}]"


BLOCKS = {
    "conflict": "CONFLICT AT MATCHED LENGTH: the choice account says the whole task falls with k",
    "load": "LENGTH AT FIXED CONFLICT: the load account says it falls with n",
    "choice": "MORE GROUPS OF ONE SIZE: does each choice fail, or only the conjunction?",
}


def render(out: Mapping[str, Any]) -> None:
    level = round(100 * (1 - out["alpha"]))
    print(f"{out['run_id']}  --  load versus conflict, over {len(out['bundles'])} bundles")
    print(f"  {out['draws']} usable draws" + (f"; left out {out['left_out']}"
                                              if out["left_out"] else ""))
    if len(out["bundles"]) < 2:
        print("  One bundle only: every interval treats each draw as independent.")
    print(f"\n  BY TRIAL: each rate is a mean over bundles, [{level}% interval]")
    print(f"    {'n':>3} {'k':>2} {'size':>4} {'draws':>5}  {'groups chosen':<20} "
          f"{'all groups':<20} {'fillers kept':<20} whole task")
    for t in out["trials"]:
        size = "-" if t["size"] is None else str(t["size"])
        note = f"  ({t['unjudged']} unjudged)" if t["unjudged"] else ""
        print(f"    {t['n']:>3} {t['k']:>2} {size:>4} {t['draws']:>5}  "
              f"{_rate(t['groups']):<20} {_rate(t['conjunction']):<20} "
              f"{_rate(t['fillers']):<20} {_rate(t['all_satisfied'])}{note}")
    for block, title in BLOCKS.items():
        rows = [c for c in out["contrasts"] if c["block"] == block]
        if not rows:
            continue
        print(f"\n  {title}")
        for c in rows:
            what = "whole task" if c["measure"] == "all_satisfied" else "groups chosen"
            print(f"    {what + ', ' + c['asks']:<53} {_diff(c)}  over {c['bundles']} bundles")
    ind = [t for t in out["trials"] if t["independence"]]
    if ind:
        print("\n  ALL GROUPS AGAINST INDEPENDENCE: the share choosing in every group, and the "
              "product of\n  the groups' own rates")
        for t in ind:
            e = t["independence"]
            print(f"    n={t['n']:<2} k={t['k']}: observed {e['observed']:.2f}, product "
                  f"{e['product']:.2f}, difference {_diff(e)}  over {e['bundles']} bundles")
    print("\n  GROUPS CHOSEN BY FAMILY, every trial with a conflict")
    for family, e in out["families"].items():
        print(f"    {family:<8} {_rate(e)}")
    print("\n  HOW TO READ THIS")
    print("    A group is chosen when the reply did one of its own instructions; the whole task "
          "is every\n    group chosen and every filler kept. Intervals are the wider of bundles "
          "as replicates and\n    every draw as independent. A format group whose member is "
          "also the common habit reads\n    high whether or not the rule was read "
          "(doc 16, section 4). Exploratory: a pattern here is a\n    hypothesis for other "
          "models to test.")


def _main(argv: Optional[Sequence[str]] = None) -> int:
    from ..logs import add_arguments, from_arguments, get_logger

    log = get_logger(__name__)
    parser = argparse.ArgumentParser(
        prog="python3 -m whowins.stats.load_cell",
        description="The load cell, from a load-bundles or load-cell run.")
    parser.add_argument("run_id", help="a run in configs/runs/ that sent load trials")
    parser.add_argument("--log", metavar="PATH",
                        help="the records log to read (default: results/<run_id>/records.jsonl)")
    parser.add_argument("--alpha", type=float, default=0.05,
                        help="one minus the coverage of every interval (default: 0.05)")
    parser.add_argument("--json", metavar="PATH", default=None,
                        help="also write every number to this file")
    add_arguments(parser, progress=False)
    args = parser.parse_args(argv)
    written = from_arguments("load_cell", args, args.run_id)
    try:
        out = run_load_cell(args.run_id, args.log, alpha=args.alpha)
    except (LoadError, OSError) as exc:
        log.error("load cell error: %s", exc)
        return 2
    render(out)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)
            fh.write("\n")
        print(f"\nwritten: {args.json}")
    if written:
        log.info("this reading's log: %s", written)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
