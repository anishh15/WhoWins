"""Fit a strength per source to a finished run's conflict data.
A run with a set above a pair also gets the composition test, and THE FAMILIES asks it
again of every model family. Three fits are printed and never pooled: free pairs
(assumes nothing), the whole design (assumes pinning is the same), within-message.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Mapping, Optional, Sequence

from ..logs import add_arguments, from_arguments, get_logger
from . import ladder, models, score
from .choice import Dataset, free_from_records, from_records, kinds

log = get_logger(__name__)

FITS = ("uniform", "position", "luce", "luce_position", "saturated")


class StrengthsError(ValueError):
    """A run whose data cannot carry a fit."""


def _records(run_id: str, log_path: Optional[str]) -> list:
    from ..runner.analyse import read_records
    from ..runner.batch import default_log, log_file

    path = log_path or default_log(run_id)
    if log_file(path) is None:
        raise StrengthsError(f"{path}: no log to read")
    return list(read_records(path))


def _fit_all(data: Dataset) -> tuple[dict, dict]:
    fits, refused = {}, {}
    for name in FITS:
        try:
            fits[name] = (models.fit_saturated(data) if name == "saturated"
                          else models.fit(data, name))
        except models.FitError as exc:
            refused[name] = str(exc)
    return fits, refused


def _held_out_items(data: Dataset, holdout: float = 0.5,
                    seed: int = 20260915) -> tuple[Dataset, Dataset]:
    """Split on ITEMS, never on draws, and shuffle first.
    Scenario ids carry the family as a prefix, so cutting a SORTED list trains on format
    and ordering and tests on path, refusal and tool -- a family split wearing an item
    split's name, which is what this did until the numbers were read carefully."""
    import random as _random

    items = sorted(data.items)
    _random.Random(seed).shuffle(items)
    cut = max(1, int(len(items) * (1 - holdout)))
    train, test = set(items[:cut]), set(items[cut:])
    return (data.filter(lambda c: c.item in train),
            data.filter(lambda c: c.item in test))


def analyse_run(run_id: str, log_path: Optional[str] = None, *,
                bootstrap_draws: int = 400, seed: int = 20260915,
                with_families: bool = True) -> dict[str, Any]:
    rows = _records(run_id, log_path)
    data = from_records(rows)
    if not len(data):
        raise StrengthsError(f"{run_id}: no conflict trial in that log")
    groups = kinds(data)
    out: dict[str, Any] = {
        "run_id": run_id,
        "data": data.summary(),
        "kinds": {k: ["-".join(c) for c in v] for k, v in groups.items()},
        "sizes_present": data.sizes,
        "can_run_the_composition_test": any(s > 2 for s in data.sizes),
        "fits": {},
    }

    def block(name: str, subset: Dataset, note: str) -> None:
        if not len(subset):
            out["fits"][name] = {"skipped": "no draw of that kind in this run"}
            return
        fits, refused = _fit_all(subset)
        train, test = _held_out_items(subset, seed=seed)
        held: dict[str, Any] = {}
        if len(train) and len(test):
            trained, _ = _fit_all(train)
            held = score.compare(trained, test, allow_unequal_coverage=True)
            if "luce" in trained:
                for other, fitted in trained.items():
                    if other == "luce":
                        continue
                    try:
                        held.setdefault("intervals", {})[other] = score.bootstrap(
                            fitted, trained["luce"], test,
                            draws=bootstrap_draws, seed=seed)
                    except score.ScoreError as exc:
                        held.setdefault("intervals", {})[other] = {"error": str(exc)}
        out["fits"][name] = {
            "note": note,
            "draws": subset.n_draws, "items": len(subset.items),
            "compositions": ["-".join(c) for c in subset.compositions],
            "abstentions": subset.abstentions(),
            "fitted": {k: v.as_dict() for k, v in fits.items()},
            "refused": refused,
            "held_out_items": held,
        }

    # The composition test, once a run has a set above a pair to predict.
    if out["can_run_the_composition_test"]:
        try:
            out["ladder"] = ladder.two_stage(data, bootstrap_draws=bootstrap_draws,
                                             seed=seed)
        except (ladder.LadderError, models.FitError) as exc:
            out["ladder"] = {"error": str(exc)}
        if with_families:
            try:
                out["families"] = ladder.families(data, bootstrap_draws=bootstrap_draws,
                                                  seed=seed)
            except (ladder.LadderError, models.FitError) as exc:
                out["families"] = {"error": str(exc)}

    free = data.with_compositions(groups["free"])
    block("free_pairs_only", free,
          "the order really varied, so nothing is assumed. Only the sources that "
          "appear in a free pair get a strength")
    without_within = data.with_compositions(groups["free"] + groups["pinned"])
    block("whole_design", without_within,
          "all five sources. The position coefficient comes from the free pairs "
          "and is carried into the pinned ones, which is an ASSUMPTION: it holds "
          "only if being first means the same thing in both")
    block("within_message_only", data.with_compositions(groups["within_message"]),
          "one system message, two labelled lines. Both runs found the FIRST line "
          "winning here, so this is primacy and points the other way")
    return out


# --- Printing ---


def free_predictions(run_id: str, free_log: str, log_path: Optional[str] = None
                     ) -> dict[str, Any]:
    """Fit on the pairs of `run_id` and score the free predictions in `free_log`.
    The free-prediction run sends no bijective set to fit on, so the fit comes from the
    ladder run of the same model and mode. Pairs only, as in stage one: nothing is refitted."""
    from ..runner.analyse import read_records
    from ..runner.batch import log_file

    if log_file(free_log) is None:
        raise StrengthsError(f"{free_log}: no log to read")

    pairs = from_records(_records(run_id, log_path)).filter(lambda c: c.size == 2)
    free = free_from_records(read_records(free_log))
    if not len(pairs) or not len(free):
        raise StrengthsError(f"{run_id} has {len(pairs)} pair choices and {free_log} "
                             f"{len(free)} free predictions; both are needed")
    fits, refused = _fit_all(pairs)
    return {"fitted_on": f"the pairs of {run_id}", "free_log": free_log, "n": len(free),
            "rows": {name: score.evaluate_free(fit, free) for name, fit in fits.items()},
            "refused": refused}


def _render_free(out: Mapping[str, Any]) -> None:
    print(f"\nFREE PREDICTIONS  ({out['n']} draws, fitted on {out['fitted_on']})")
    print("  shared: how often the option more sources demanded won, predicted by adding its "
          "sources' chances, and observed")
    for name, row in out["rows"].items():
        if row["log_score"] is None:
            print(f"    {name:14s} declined all {row['n_declined']}")
            continue
        shared = row["shared"]
        both = (f"{shared['predicted']:.3f} predicted, {shared['observed']:.3f} observed"
                if shared["n"] else "no trial has one")
        print(f"    {name:14s} log {row['log_score']:.4f}  cov {row['coverage']:.2f}   "
              f"shared {both}")


def _render_families(fam: Optional[Mapping[str, Any]]) -> None:
    if not fam:
        return
    if "error" in fam:
        print(f"\nTHE FAMILIES could not run: {fam['error']}")
        return
    print(f"\nTHE FAMILIES  (every family fitted alike on {fam['decided_draws']} decided draws; "
          f"{fam['left_out']} with no winner left out)")
    for stage in fam["stages"]:
        rows, intervals = stage["scores"]["rows"], stage.get("intervals") or {}
        print(f"  stage {stage['stage']}: {len(stage['train'])} train -> {len(stage['test'])} "
              f"held-out compositions, log score per decided draw")
        for name in sorted((n for n in rows if rows[n]["log_score"] is not None),
                           key=lambda n: -rows[n]["log_score"]):
            iv = intervals.get(name) or {}
            extra = (f"   vs luce {iv['difference']:+.4f} [{iv['lo']:+.4f},{iv['hi']:+.4f}]"
                     if "difference" in iv else "")
            print(f"    {name:20s} log {rows[name]['log_score']:+.4f}  "
                  f"cov {rows[name]['coverage']:.2f}{extra}")
        for name, why in (stage.get("refused") or {}).items():
            print(f"    {name:20s} REFUSED: {why.splitlines()[0][:70]}")
        vario = (stage["fitted"].get("probit_position") or {}).get("variogram")
        if vario:
            print("    probit_position variogram (1 is the average pair; below 1, the two "
                  "sources' errors move together):")
            print("      " + "  ".join(f"{k} {v:.2f}" for k, v in vario.items()))
        sigmas = (stage["fitted"].get("mixed_position") or {}).get("sigmas")
        if sigmas:
            print("    mixed_position: sd of an item's taste for an option "
                  f"{sigmas.get('item', 0):.2f}, of a family's shift of a source "
                  f"{sigmas.get('family', 0):.2f} (log-odds; Laplace errs low)")
    reg = fam["regularity"]
    print(f"  REGULARITY: {reg['tests']} tests of an added competitor raising a share, "
          f"{len(reg['violations'])} violation(s) with all held at {reg['alpha']}")
    for row in (reg["violations"] or reg["largest"])[:5]:
        ref = row.get("reference_rise")
        print(f"    {row['option']} from {row['from']} to {row['to']}: {row['share_before']:.3f} "
              f"-> {row['share_after']:.3f} (se {row['se']:.3f})"
              + (f"; position alone gives {ref:+.3f}" if ref is not None else ""))


def render(out: Mapping[str, Any]) -> None:
    d = out["data"]
    print(f"{out['run_id']}  --  a strength per source, from conflict data")
    print(f"\nWHAT IS IN IT")
    print(f"  {d['draws']} conflict draws over {d['items']} items, "
          f"{len(d['compositions'])} compositions")
    print(f"  sizes present: {out['sizes_present']}   "
          f"no option won in {d['abstentions']} of them")
    if not out["can_run_the_composition_test"]:
        print("  *** PAIRS ONLY. The composition test cannot run on this data: ***")
        print("  *** there is no three-way or five-way set to predict.         ***")

    print("\nWHAT THE DESIGN LETS YOU ASK")
    for kind, label in (("free", "order varied -- strength and position separate"),
                        ("pinned", "operator always first -- confounded here"),
                        ("within_message", "one message, two lines -- PRIMACY")):
        comps = out["kinds"].get(kind) or []
        print(f"  {kind:15s} {', '.join(comps) if comps else '(none)':38s} {label}")

    for name, block in out["fits"].items():
        print(f"\n{name.replace('_', ' ').upper()}")
        if "skipped" in block:
            print(f"  skipped: {block['skipped']}")
            continue
        print(f"  {block['note']}")
        print(f"  {block['draws']} draws, {block['items']} items, "
              f"{len(block['compositions'])} compositions")
        for model_name in ("luce", "luce_position"):
            fitted = block["fitted"].get(model_name)
            if not fitted or "strengths" not in fitted:
                continue
            row = "  ".join(f"{k} {v:.3f}" for k, v in fitted["strengths"].items())
            later = fitted["coefficients"].get("later")
            extra = f"   later {later:+.3f}" if later is not None else ""
            print(f"    {model_name:16s} {row}{extra}")
            if fitted.get("notes"):
                for note in fitted["notes"]:
                    print(f"                     note: {note}")
        for model_name, why in (block.get("refused") or {}).items():
            print(f"    {model_name:16s} REFUSED: {why.splitlines()[0][:70]}")
        held = block.get("held_out_items") or {}
        rows = held.get("rows") or {}
        if rows:
            print("  on held-out ITEMS (same compositions both sides):")
            ordered = sorted(rows, key=lambda n: -(rows[n]["log_score"]
                                                   if rows[n]["log_score"] is not None
                                                   else -99))
            for n in ordered:
                ls = rows[n]["log_score"]
                interval = (held.get("intervals") or {}).get(n) or {}
                extra = (f"  vs luce {interval['difference']:+.4f} "
                         f"[{interval['lo']:+.4f},{interval['hi']:+.4f}]"
                         if "difference" in interval else "")
                shown = f"{ls:+.4f}" if ls is not None else "  ----- "
                print(f"    {n:16s} log {shown}  cov {rows[n]['coverage']:.2f}{extra}")

    lad = out.get("ladder")
    if lad and "error" not in lad:
        print("\nTHE COMPOSITION TEST")
        for stage in lad["stages"]:
            rows = stage["scores"]["rows"]
            best = sorted((n for n in rows if rows[n]["log_score"] is not None),
                          key=lambda n: -rows[n]["log_score"])
            print(f"  stage {stage['stage']}: {len(stage['train'])} train -> "
                  f"{len(stage['test'])} held-out compositions")
            head = stage.get("headroom") or {}
            share = head.get("share_recovered") or {}
            for name in best[:4]:
                top1 = rows[name].get("top1")
                print(f"    {name:20s} log {rows[name]['log_score']:+.4f}  "
                      f"cov {rows[name]['coverage']:.2f}"
                      + (f"  top-1 {top1:.3f}" if top1 is not None else "")
                      + (f"  recovers {share[name]:.0%}" if share.get(name) is not None else ""))
            for name, why in (stage.get("refused") or {}).items():
                print(f"    {name:20s} REFUSED: {why.splitlines()[0][:60]}")
            if head.get("ceiling") is not None:
                print(f"    ceiling {head['ceiling']:+.4f} over {head['cells']} "
                      f"(composition, order) cells; best model is "
                      f"{min(v for v in head['short_by'].values() if v is not None):.3f}"
                      f" nats short")
                if head.get("uniform") is not None:
                    print(f"    top-1 at the ceiling {head['top1_ceiling']:.3f}; 'recovers' is the "
                          f"share of the way from uniform ({head['uniform']:+.4f}) to it")
    elif lad:
        print(f"\nTHE COMPOSITION TEST could not run: {lad['error']}")
    _render_families(out.get("families"))

    print("\nHOW TO READ THIS, AND HOW NOT TO")
    if out["can_run_the_composition_test"]:
        print("  The first two fits pool every size in the run. Only the composition test")
        print("  fits pairs alone and predicts the larger sets it never saw, which is")
        print("  the study's question.")
        if out.get("families"):
            print("  The families block asks it again of every model family, on decided draws")
            print("  only, so its log scores are not comparable with the block above it.")
    else:
        print("  A strength here describes which source won a PAIR. Whether those")
        print("  strengths predict a three-way set is the study's question, and this")
        print("  run cannot answer it -- run `python3 -m whowins.stats.phase1` to see what")
        print("  pairwise data provably cannot settle.")
    print("  The free-pairs fit assumes nothing. The whole-design fit assumes the")
    print("  position effect is the same where the operator is pinned. The")
    print("  within-message pair points the other way and is never pooled with them.")


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m whowins.stats.strengths",
        description="Fit a strength per source to a finished run's conflict data.")
    parser.add_argument("run_id", help="a run in configs/runs/")
    parser.add_argument("--log", metavar="PATH",
                        help="the records log to read (default: "
                             "results/<run_id>/records.jsonl)")
    parser.add_argument("--json", metavar="PATH", default=None,
                        help="also write every number to this file")
    parser.add_argument("--seed", type=int, default=20260915,
                        help="the bootstrap seed (default: 20260915)")
    parser.add_argument("--free", metavar="PATH", default=None,
                        help="also score the free predictions in this records log "
                             "(a free-predictions run of the same model and mode) "
                             "with fits made on this run's pairs")
    parser.add_argument("--no-families", action="store_true",
                        help="skip THE FAMILIES block (Thurstone, the correlated probit, the "
                             "context model and regularity), the slow part of the report")
    add_arguments(parser, progress=False)
    args = parser.parse_args(argv)
    written = from_arguments("strengths", args, args.run_id)

    try:
        out = analyse_run(args.run_id, args.log, seed=args.seed,
                          with_families=not args.no_families)
        if args.free:
            out["free_predictions"] = free_predictions(args.run_id, args.free, args.log)
    except (StrengthsError, models.FitError, OSError) as exc:
        log.error("strengths error: %s", exc)
        return 2

    render(out)
    if args.free:
        _render_free(out["free_predictions"])
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, sort_keys=False, default=str)
            fh.write("\n")
        print(f"\nwritten: {args.json}")
    if written:
        log.info("this fit's log: %s", written)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
