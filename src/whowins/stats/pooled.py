"""Model and harness random effects: one fit across several runs, each source's strength
shifted at random by the run's model and, where the design can tell them apart, its harness.
The pairs of each run, as the composition test's stage one fits them, on decided draws."""

from __future__ import annotations

import argparse
import json
from typing import Any, Mapping, Optional, Sequence

from ..logs import add_arguments, from_arguments, get_logger
from . import mixed
from .choice import Choice, Dataset, Option, canonical, from_records

log = get_logger(__name__)


class PoolError(ValueError):
    """Runs that cannot be pooled as asked."""


def harness_separable(models: Mapping[str, str], harnesses: Mapping[str, str]) -> Optional[str]:
    """Why a harness effect cannot be told from a model effect here, or None when it can.
    It can when at least two harnesses appear and some model was served in more than one: that
    model's runs compare harnesses with the model held fixed."""
    if len(set(harnesses.values())) < 2:
        return "every run was served in one harness"
    served: dict[str, set] = {}
    for run, model in models.items():
        served.setdefault(model, set()).add(harnesses[run])
    if not any(len(h) > 1 for h in served.values()):
        return ("no model was served in more than one harness, so a harness is its models: every "
                "difference between harnesses is also a difference between the models each served")
    return None


def pool(runs: Mapping[str, Dataset], models: Mapping[str, str],
         harnesses: Mapping[str, str], *, position: bool = True) -> tuple[Any, dict[str, Any]]:
    """Fit strengths shared by every run, with a shift per (model, source) and, when separable,
    per (harness, source). `runs` are each run's decided pair choices."""
    if len(runs) < 2:
        raise PoolError("pooling needs at least two runs")
    rows = []
    for run_id, data in sorted(runs.items()):
        for c in canonical(data.filter(lambda c: c.won is not None and c.size == 2)):
            rows.append(Choice(item=f"{run_id}|*", options=tuple(
                Option(o.option_id, o.source, position=o.position) for o in c.options),
                won=c.won, weight=c.weight))
    data = Dataset(rows)

    def run_of(item: str) -> str:
        return item.split("|", 1)[0]

    factors: list[mixed.Factor] = [("model", lambda item: models[run_of(item)])]
    why_not = harness_separable({r: models[r] for r in runs}, {r: harnesses[r] for r in runs})
    if why_not is None:
        factors.append(("harness", lambda item: harnesses[run_of(item)]))
    fitted = mixed.fit_mixed(data, position=position, factors=factors, items=False,
                             name="pooled_position" if position else "pooled")
    return fitted, {"runs": sorted(runs), "models": sorted(set(models[r] for r in runs)),
                    "harnesses": sorted(set(harnesses[r] for r in runs)),
                    "harness_effect": "fitted" if why_not is None else f"not fitted: {why_not}"}


def pool_runs(run_ids: Sequence[str]) -> dict[str, Any]:
    """Read each run's records and config, and pool them."""
    from ..runner.analyse import read_records
    from ..runner.batch import default_log, log_file
    from ..runner.serving import load_run

    runs, models, harnesses = {}, {}, {}
    for run_id in run_ids:
        path = default_log(run_id)
        if log_file(path) is None:
            raise PoolError(f"{path}: no log to read")
        run = load_run(run_id)
        runs[run_id] = from_records(read_records(path))
        models[run_id] = f"{run.model.key}/{run.policy.name}"
        harnesses[run_id] = run.environment.key
    fitted, info = pool(runs, models, harnesses)
    return {**info, "fit": fitted.as_dict()}


def render(out: Mapping[str, Any]) -> None:
    fit = out["fit"]
    print(f"POOLED  {len(out['runs'])} runs, {len(out['models'])} models, harness effect "
          f"{out['harness_effect']}")
    print("  shared strengths: " + "  ".join(f"{k} {v:.3f}" for k, v in fit["strengths"].items())
          + (f"   later {fit['coefficients']['later']:+.3f}" if "later" in fit["coefficients"] else ""))
    for name, sigma in fit["sigmas"].items():
        print(f"  sd of the {name} shift of a log strength: {sigma:.3f}")
    for name, levels in fit["shifts"].items():
        print(f"  {name} shifts:")
        for level, by_source in levels.items():
            print(f"    {level:40s} " + "  ".join(f"{s} {v:+.2f}" for s, v in by_source.items()))
    for note in fit.get("notes") or []:
        print(f"  note: {note}")


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m whowins.stats.pooled",
        description="One fit across runs: shared strengths, a random shift per model and, "
                    "where separable, per harness.")
    parser.add_argument("run_ids", nargs="+", metavar="RUN_ID", help="two or more runs")
    parser.add_argument("--json", metavar="PATH", default=None,
                        help="also write every number to this file")
    add_arguments(parser, progress=False)
    args = parser.parse_args(argv)
    written = from_arguments("pooled", args, "-".join(args.run_ids[:2]))
    try:
        out = pool_runs(args.run_ids)
    except (PoolError, mixed.FitError, OSError) as exc:
        log.error("pooled error: %s", exc)
        return 2
    render(out)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, default=str)
            fh.write("\n")
        print(f"\nwritten: {args.json}")
    if written:
        log.info("this fit's log: %s", written)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
