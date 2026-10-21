"""Score a finished run again, from what the model actually said.
It decides something: a checker fix costs no GPU time, so corrections are not under
pressure from the serving bill. It NEVER touches records.jsonl, and a row whose trial
the config no longer builds is reported and skipped rather than guessed at."""

from __future__ import annotations

import argparse
import collections
import json
import os
from typing import Any, Iterator, Mapping, Optional, Sequence

from ..checkers import fingerprint as checkers_fingerprint
from ..logs import add_arguments, from_arguments, get_logger
from ..progress import Progress
from .batch import RECORD, default_log, log_file, read_records as batch_read_records
from .rendering import Scenarios, render_dicts
from .run import Decoding, RunRecord, ServingStack, score
from .serving import ConfigError, load_run
from .trials import load_scenarios


log = get_logger(__name__)


class RescoreError(ValueError):
    """The log and the run config do not describe the same run."""


# What the RUN recorded, as against what the CHECKERS decided: a rescore replaces the second and must not lose the first. `checker_fingerprint` is deliberately absent -- it is the one field a rescore overwrites.
CARRIED = ("at", "concurrency", "tool_turns")


def read_records(path: str) -> Iterator[dict[str, Any]]:
    """The run loop's own reader, with a message naming what could not be read."""
    if log_file(path) is None:
        raise RescoreError(f"{path}: no log to rescore")
    return batch_read_records(path)


def payloads_of(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Every completion the trial produced: the first, then the loop's.

    A record written before the loop existed carries `raw` alone, which is one
    turn and reads back as one turn."""
    raw = row.get("raw")
    if raw is None:
        raise RescoreError(f"{row.get('trial_id')}: the record kept no reply, so "
                           f"there is nothing to score again")
    return [raw, *(row.get("later_turns") or [])]


def _stack(row: Mapping[str, Any]) -> ServingStack:
    fields = dict(row.get("serving_stack") or {})
    known = {f for f in ServingStack.__dataclass_fields__}
    return ServingStack(**{k: v for k, v in fields.items() if k in known})


def _decoding(row: Mapping[str, Any]) -> Decoding:
    fields = dict(row.get("decoding") or {})
    known = {f for f in Decoding.__dataclass_fields__}
    out = {k: v for k, v in fields.items() if k in known}
    if isinstance(out.get("stop"), list):
        out["stop"] = tuple(out["stop"])
    return Decoding(**out)


def rescore_row(row: Mapping[str, Any], specs: Mapping[str, Any],
                scenarios: Scenarios, *, family: Any = None) -> RunRecord:
    """One row, scored again by today's checkers against yesterday's reply.
    The id names a scenario and a composition, not which source carried which option, so the
    stored prompt must open with today's render or the row is skipped."""
    trial_id = row.get("trial_id")
    spec = specs.get(trial_id)
    if spec is None:
        raise RescoreError(
            f"{trial_id}: this run's config no longer builds that trial, so the "
            f"reply cannot be scored against what it was asked"
        )
    sent = row.get("messages")
    fresh = render_dicts(spec, scenarios)
    if sent is not None and list(sent[:len(fresh)]) != fresh:
        raise RescoreError(
            f"{trial_id}: this run's config now renders a different prompt from the "
            f"one sent, so the reply cannot be scored against today's trial"
        )
    stack = _stack(row)
    decoding = _decoding(row)
    opened = bool(getattr(family, "thinking_prefills_open_block", False)) \
        and bool(decoding.enable_thinking)
    return score(spec, scenarios, payloads_of(row), stack, decoding,
                 attempt=row.get("attempt", 1), prompt_opened_thinking=opened,
                 messages=row.get("messages"), stopped_by=row.get("stopped_by"))


def verdict(row: Mapping[str, Any]) -> tuple:
    """Everything a checker fix could move, for one row.
    Not just (behaviour, label): a composite trial has neither, a `multiple` reply's options
    are in `alternatives`, and whether the model flagged the conflict is `communication`.
    Each was once left out, and a fix that moved it was reported as moving nothing."""
    return (
        row.get("behaviour"),
        row.get("label"),
        tuple(row.get("alternatives") or ()),
        row.get("communication"),
        row.get("conjunction"),
        row.get("all_satisfied"),
        tuple((g.get("group_id"), g.get("behaviour"), g.get("label"),
               tuple(g.get("alternatives") or ()))
              for g in row.get("groups") or ()),
        tuple((f.get("filler_id"), f.get("result")) for f in row.get("fillers") or ()),
    )


def _shown(row: Mapping[str, Any]) -> str:
    """The part of a verdict worth printing on one line."""
    if row.get("label") is not None or not (row.get("groups") or ()):
        shown = str(row.get("label"))
    else:
        shown = " ".join(f"{g.get('group_id')}={g.get('label')}" for g in row["groups"])
    if row.get("alternatives"):
        shown += f" ({', '.join(row['alternatives'])})"
    return f"{shown} / {row.get('communication')}"


def rescore(run_id: str, log_path: Optional[str] = None,
            scenarios: Optional[Scenarios] = None,
            run: Optional[Any] = None, progress: str = "none") -> dict[str, Any]:
    """Every scored row of a run, read again. Returns the rows and what moved.
    `run` and `scenarios` are for the suite; a real rescore reads the config, because the
    trials have to be the ones actually sent."""
    run = run if run is not None else load_run(run_id)
    scenarios = scenarios if scenarios is not None else load_scenarios()
    from .design import trials_for_run
    specs = {s.trial_id: s for s in trials_for_run(run, scenarios)}
    path = log_path or default_log(run_id)

    rows: list[dict[str, Any]] = []
    moved: list[tuple[str, str, str, str, str]] = []
    before: collections.Counter = collections.Counter()
    after: collections.Counter = collections.Counter()
    skipped: list[str] = []
    log.info("rescoring %s from %s against %d built trials",
             run_id, path, len(specs))
    stored = list(read_records(path))
    bar = Progress(len(stored), label="Rescore", unit="records",
                   mode=progress)
    for row in stored:
        bar.advance(note=str(row.get("trial_id") or ""))
        try:
            record = rescore_row(row, specs, scenarios, family=run.model.family)
        except RescoreError as exc:
            skipped.append(str(exc))
            log.warning("skipped: %s", exc)
            continue
        new = record.as_dict()
        new["line"] = RECORD
        new["run_id"] = run_id
        new["repeat"] = row.get("repeat", 0)
        for field in CARRIED:
            if field in row:
                new[field] = row[field]
        # Today's checkers really did make these verdicts, so the row says so; without it the one file that can answer for free answers UNKNOWN.
        new["checker_fingerprint"] = checkers_fingerprint()
        rows.append(new)
        before[row.get("behaviour")] += 1
        after[new["behaviour"]] += 1
        if verdict(row) != verdict(new):
            moved.append((row.get("trial_id"), row.get("behaviour"), new["behaviour"],
                          _shown(row), _shown(new)))
    bar.close()
    (log.warning if skipped else log.info)(
        "%d records rescored, %d verdicts moved, %d skipped",
        len(rows), len(moved), len(skipped))
    return {"run_id": run_id, "log": path, "rows": rows, "moved": moved,
            "before": dict(before), "after": dict(after), "skipped": skipped}


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m whowins.runner.rescore",
        description="Score a finished run again with today's checkers.")
    parser.add_argument("run_id", help="a run in configs/runs/")
    parser.add_argument("--log", metavar="PATH",
                        help="the records log to read (default: "
                             "results/<run_id>/records.jsonl)")
    parser.add_argument("--write", action="store_true",
                        help="also write rescored.jsonl beside the log. "
                             "records.jsonl is never touched: it is what came "
                             "back from the server")
    parser.add_argument("--changed", type=int, default=0, metavar="N",
                        help="print the first N trials whose verdict moved "
                             "(default: %(default)s, the count alone)")
    add_arguments(parser)
    args = parser.parse_args(argv)
    written = from_arguments("rescore", args, args.run_id)

    try:
        out = rescore(args.run_id, args.log, progress=args.progress)
    except (ConfigError, RescoreError, KeyError, OSError) as exc:
        # OSError included: a run id with no config file raised FileNotFoundError past this handler and printed a bare traceback.
        log.error("rescore error: %s", exc)
        return 2

    keys = sorted(set(out["before"]) | set(out["after"]),
                  key=lambda k: -out["after"].get(k, 0))
    print(f"{len(out['rows'])} records rescored from {out['log']}")
    print(f"{'behaviour':14s}{'was':>8s}{'now':>8s}{'move':>8s}")
    for key in keys:
        was, now = out["before"].get(key, 0), out["after"].get(key, 0)
        print(f"{str(key):14s}{was:8d}{now:8d}{now - was:+8d}")
    print(f"\n{len(out['moved'])} trials changed verdict")
    for trial_id, was, now, old_label, new_label in out["moved"][:args.changed]:
        print(f"  {trial_id:24s} {was} -> {now}   {old_label} -> {new_label}")

    if args.write:
        path = os.path.join(os.path.dirname(out["log"]) or ".", "rescored.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for row in out["rows"]:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        log.info("wrote %s", path)
        print(f"\nwritten: {path}")
    if written:
        log.info("this rescore's log: %s", written)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
