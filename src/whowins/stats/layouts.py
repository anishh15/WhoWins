"""The three layout designs read back: what moving one thing did, paired within the item.
The operator test asks what the operator's role and its position each add; the one-message
test whether the first line wins inside a message as it does inside a system message; the
realism set whether "the later instruction wins" survives the text around real instructions."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from . import paired

OPERATOR, ONE_MESSAGE, REALISM = "operator-decomposition", "one-message", "realism"
DESIGNS = (OPERATOR, ONE_MESSAGE, REALISM)


class LayoutError(ValueError):
    """Records that cannot answer a layout design's questions."""


@dataclass(frozen=True)
class LayoutDraw:
    """One usable reply to a layout trial. `unit` is the item the layouts are paired within;
    `order` the two sources in send order; `winner` the source whose option the reply chose,
    or None when it chose neither (abstained, both, unresolved or off the menu)."""
    design: str
    unit: str
    order: tuple[str, str]
    layout: tuple[tuple[str, Any], ...]
    winner: Optional[str]

    def get(self, key: str) -> Any:
        return dict(self.layout).get(key)


def from_records(rows: Iterable[Mapping[str, Any]]) -> tuple[list[LayoutDraw], dict[str, int]]:
    """A run's layout trials as draws, and what was left out and why."""
    out, skipped = [], {}
    for row in rows:
        meta = row.get("meta") or {}
        if meta.get("design") not in DESIGNS:
            continue
        if row.get("usable") is False:
            skipped["unusable reply"] = skipped.get("unusable reply", 0) + 1
            continue
        carries = meta["carries"]
        chosen = row.get("winning_option") if row.get("behaviour") == "chose" else None
        winner = next((s for s, o in carries.items() if o == chosen), None)
        order = tuple(s for s in meta["order"] if s != "task")
        out.append(LayoutDraw(meta["design"], str(meta.get("item_id") or row["scenario_id"]),
                              order, tuple(sorted(meta["layout"].items())), winner))
    return out, skipped


Keep = Callable[[LayoutDraw], bool]


def _counts(draws: Sequence[LayoutDraw], keep: Keep, won: Keep) -> dict[str, tuple[int, int]]:
    """unit -> (draws where `won`, decided draws), over the decided draws `keep` selects."""
    out: dict[str, tuple[int, int]] = {}
    for d in draws:
        if d.winner is not None and keep(d):
            k, t = out.get(d.unit, (0, 0))
            out[d.unit] = (k + bool(won(d)), t + 1)
    return out


def _decided(draws: Sequence[LayoutDraw], keep: Keep) -> Optional[float]:
    mine = [d for d in draws if keep(d)]
    return sum(d.winner is not None for d in mine) / len(mine) if mine else None


def _cell(draws: Sequence[LayoutDraw], name: str, keep: Keep, won: Keep,
          alpha: float) -> dict[str, Any]:
    return {"cell": name, "decided": _decided(draws, keep),
            "rate": paired.rate(_counts(draws, keep, won), alpha)}


def _contrast(draws: Sequence[LayoutDraw], asks: str, a: Keep, b: Keep, won: Keep,
              alpha: float) -> dict[str, Any]:
    return {"asks": asks, **(paired.difference(_counts(draws, a, won), _counts(draws, b, won),
                                               alpha) or {"difference": None})}


def _operator(draws: Sequence[LayoutDraw], alpha: float) -> dict[str, Any]:
    def at(role: str, position: str, other: Optional[str] = None) -> Keep:
        return lambda d: d.get("role") == role and d.get("operator_position") == position \
            and (other is None or other in d.order)

    def won(d: LayoutDraw) -> bool:
        return d.winner == d.get("operator")

    cells = [_cell(draws, f"{role}, {position}", at(role, position), won, alpha)
             for role in ("real", "label") for position in ("first", "last")]
    by_other = {other: [_cell(draws, f"{role}, {position}", at(role, position, other), won, alpha)
                        for role in ("real", "label") for position in ("first", "last")]
                for other in ("S3", "S4", "S5")}
    contrasts = [
        _contrast(draws, "position, real operator message: last minus first",
                  at("real", "last"), at("real", "first"), won, alpha),
        _contrast(draws, "position, label in a user message: last minus first",
                  at("label", "last"), at("label", "first"), won, alpha),
        _contrast(draws, "role, operator first: real message minus label",
                  at("real", "first"), at("label", "first"), won, alpha),
        _contrast(draws, "role, operator last: real message minus label",
                  at("real", "last"), at("label", "last"), won, alpha),
    ]
    return {"measure": "the operator's line won", "cells": cells, "by_other": by_other,
            "contrasts": contrasts}


def _one_message(draws: Sequence[LayoutDraw], alpha: float) -> dict[str, Any]:
    def at(message: str) -> Keep:
        return lambda d: d.get("message") == message

    def won(d: LayoutDraw) -> bool:
        return d.winner == d.order[0]

    return {"measure": "the first-listed line won",
            "cells": [_cell(draws, m, at(m), won, alpha) for m in ("separate", "merged")],
            "contrasts": [_contrast(draws, "inside the task's message minus separate messages",
                                    at("merged"), at("separate"), won, alpha)]}


def _realism(draws: Sequence[LayoutDraw], alpha: float) -> dict[str, Any]:
    def free(context: str) -> Keep:
        return lambda d: "S1" not in d.order and d.get("context") == context

    def operator(context: str, position: str) -> Keep:
        index = 0 if position == "first" else 1
        return lambda d: d.order[index] == "S1" and d.get("context") == context

    def later(d: LayoutDraw) -> bool:
        return d.winner == d.order[1]

    def op(d: LayoutDraw) -> bool:
        return d.winner == "S1"

    return {
        "measure": "free pairs: the later line won; operator pairs: the operator won",
        "free": [_cell(draws, c, free(c), later, alpha) for c in ("bare", "context")],
        "operator": [_cell(draws, f"{c}, {p}", operator(c, p), op, alpha)
                     for c in ("bare", "context") for p in ("first", "last")],
        "contrasts": [
            _contrast(draws, "free pairs, later wins: in context minus bare",
                      free("context"), free("bare"), later, alpha),
            _contrast(draws, "operator first, operator wins: in context minus bare",
                      operator("context", "first"), operator("bare", "first"), op, alpha),
            _contrast(draws, "operator, bare: last minus first",
                      operator("bare", "last"), operator("bare", "first"), op, alpha),
            _contrast(draws, "operator, in context: last minus first",
                      operator("context", "last"), operator("context", "first"), op, alpha),
        ],
    }


READERS = {OPERATOR: _operator, ONE_MESSAGE: _one_message, REALISM: _realism}


def summarise(draws: Sequence[LayoutDraw], alpha: float = 0.05) -> dict[str, Any]:
    """Every number the run's layout design reports, from its draws."""
    designs = sorted({d.design for d in draws})
    if len(designs) != 1:
        raise LayoutError(f"one layout design per run, found {designs or 'none'}")
    return {"design": designs[0], "draws": len(draws), "units": len({d.unit for d in draws}),
            "alpha": alpha, **READERS[designs[0]](draws, alpha)}


def run_layouts(run_id: str, log_path: Optional[str] = None, *,
                alpha: float = 0.05) -> dict[str, Any]:
    from ..runner.analyse import read_records
    from ..runner.batch import default_log, log_file

    path = log_path or default_log(run_id)
    if log_file(path) is None:
        raise LayoutError(f"{path}: no log to read")
    draws, skipped = from_records(read_records(path))
    if not draws:
        raise LayoutError(f"{run_id}: no operator, one-message or realism trial in that log")
    return {"run_id": run_id, "left_out": skipped, **summarise(draws, alpha)}


def _rate(cell: Mapping[str, Any]) -> str:
    r = cell["rate"]
    shown = "-" if r is None else f"{r['rate']:.2f} [{r['low']:.2f}, {r['high']:.2f}]"
    decided = "" if cell["decided"] is None else f"  (decided {cell['decided']:.2f})"
    return f"{cell['cell']:<16} {shown:<20}{decided}"


def render(out: Mapping[str, Any]) -> None:
    level = round(100 * (1 - out["alpha"]))
    print(f"{out['run_id']}  --  {out['design']}, {out['draws']} usable draws over "
          f"{out['units']} items" + (f"; left out {out['left_out']}" if out["left_out"] else ""))
    print(f"\n  {out['measure'].upper()}, among the draws where one of the two lines won. "
          f"Each rate is a mean over items, [{level}% interval]")
    for block in ("cells", "free", "operator"):
        if block in out:
            if block != "cells":
                print(f"  {block}:")
            for cell in out[block]:
                print(f"    {_rate(cell)}")
    for other, cells in (out.get("by_other") or {}).items():
        print(f"  against {other}:")
        for cell in cells:
            print(f"    {_rate(cell)}")
    print("\n  PAIRED WITHIN THE ITEM")
    for c in out["contrasts"]:
        shown = "-" if c["difference"] is None else (
            f"{c['difference']:+.2f} [{c['low']:+.2f}, {c['high']:+.2f}] over {c['units']} items")
        print(f"    {c['asks']:<56} {shown}")
    print("\n  Intervals are the wider of items as replicates and every draw as independent. A")
    print("  layout no draw reached shows '-': a template that refuses a late operator message")
    print("  leaves 'last' empty. Exploratory, like the rest of the main run.")


def _main(argv: Optional[Sequence[str]] = None) -> int:
    from ..logs import add_arguments, from_arguments, get_logger

    log = get_logger(__name__)
    parser = argparse.ArgumentParser(
        prog="python3 -m whowins.stats.layouts",
        description="The operator test, the one-message test or the realism set, from a run.")
    parser.add_argument("run_id", help="a run whose design is operator-decomposition, "
                                       "one-message or realism")
    parser.add_argument("--log", metavar="PATH",
                        help="the records log to read (default: results/<run_id>/records.jsonl)")
    parser.add_argument("--alpha", type=float, default=0.05,
                        help="one minus the coverage of every interval (default: 0.05)")
    parser.add_argument("--json", metavar="PATH", default=None,
                        help="also write every number to this file")
    add_arguments(parser, progress=False)
    args = parser.parse_args(argv)
    written = from_arguments("layouts", args, args.run_id)
    try:
        out = run_layouts(args.run_id, args.log, alpha=args.alpha)
    except (LayoutError, OSError) as exc:
        log.error("layout error: %s", exc)
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
