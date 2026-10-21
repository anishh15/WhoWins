"""What a finished run did, read off its own records.
THIS FITS NOTHING AND PREDICTS NOTHING -- descriptive counts, proportions and Wilson
intervals, no model behind them. Nothing here names a source, family, checker key or
model, so it reads any run without a branch. It drops nothing."""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
from typing import Any, Iterator, Mapping, Optional, Sequence

from ..logs import add_arguments, from_arguments, get_logger
from .batch import default_log, log_file, read_records as batch_read_records
from .run import answer_text
from .serving import ConfigError, load_run
from .trials import load_scenarios

log = get_logger(__name__)

BEHAVIOURS = ("chose", "unresolved", "off_menu", "multiple", "no_action")

SECTIONS = ("scoring", "hygiene", "outcomes", "position", "sources", "solo",
            "unresolved", "items", "repeats", "communication")


class AnalysisError(ValueError):
    """The log cannot be read as the run its config describes."""


# --- Arithmetic ---


def wilson(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """A Wilson score interval.
    Wilson rather than the normal approximation because several cells sit near 0 or 1,
    where the normal interval runs off the end of the scale."""
    if total <= 0:
        return (0.0, 0.0)
    p = hits / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    # Clamped: floating point put wilson(0, 40) at -6.3e-18, which prints as a negative probability.
    lo, hi = (centre - half) / denom, (centre + half) / denom
    return (min(1.0, max(0.0, lo)), min(1.0, max(0.0, hi)))


def _rate(hits: int, total: int) -> dict[str, Any]:
    lo, hi = wilson(hits, total)
    return {"hits": hits, "n": total,
            "rate": (hits / total) if total else None,
            "lo": lo if total else None, "hi": hi if total else None}


def _fmt(cell: Mapping[str, Any], width: int = 26) -> str:
    if not cell["n"]:
        return "-".rjust(width)
    return (f"{cell['hits']:5d}/{cell['n']:<5d} {cell['rate']:.3f} "
            f"[{cell['lo']:.2f},{cell['hi']:.2f}]").rjust(width)


# --- Reading ---


def read_records(path: str) -> Iterator[dict[str, Any]]:
    """The run loop's own reader, with a message naming what could not be read."""
    if log_file(path) is None:
        raise AnalysisError(f"{path}: no log to read")
    return batch_read_records(path)


def _winner(row: Mapping[str, Any]) -> Optional[str]:
    """Which source carried the option this reply chose, if exactly one did.
    Where several demanded the same option (a free prediction) the win is theirs jointly,
    and naming the first would credit one source with the others' win."""
    won = row.get("winning_option")
    if row.get("behaviour") != "chose" or not won:
        return None
    carried = [s for s, o in (row.get("meta", {}).get("carries") or {}).items() if o == won]
    return carried[0] if len(carried) == 1 else None


#: Why a reply carries no label. Keys, not prose -- `_print_unresolved` says it.
SHAPES = ("empty", "truncated", "no_artifact", "artifact_shaped")


def reply_shape(row: Mapping[str, Any], key: Optional[str],
                scenario: Optional[Mapping[str, Any]], opened: bool = False) -> str:
    """One of SHAPES, by the same gate the format family scores with, on the turn it scored.
    It read the last turn with text, so "The file has been updated." after a real artifact
    made our miss read as the model's. `opened`: the family's prompt opens a thinking block."""
    from ..checkers.fmt._lib import artifact_text

    text = answer_text(row, prompt_opened_thinking=opened)
    if not text.strip():
        return "empty"
    if row.get("finish_reason") == "length":
        return "truncated"
    if key and scenario is not None and artifact_text(key, text, scenario) is not None:
        return "artifact_shaped"
    return "no_artifact"


HEAVY = ("raw", "later_turns", "messages")
"""What a record carries that only `reply_shape` reads. With thinking on, the reasoning makes
these most of a log, so each row's shape is read once as it loads and they are let go."""


def load_rows(run_id: str, log_path: Optional[str] = None,
              scenarios: Optional[Mapping[str, Any]] = None,
              opened: bool = False) -> list[dict[str, Any]]:
    """Every scored row, with the scenario's family, key and reply shape attached."""
    scenarios = scenarios if scenarios is not None else load_scenarios()
    path = log_path or default_log(run_id)
    rows = []
    for row in read_records(path):
        sid = row.get("scenario_id")
        scenario = scenarios.get(sid) if sid else None
        meta = row.get("meta") or {}
        key = (scenario or {}).get("checker_key")
        shape = reply_shape(row, key, scenario, opened)
        rows.append({
            "row": {k: v for k, v in row.items() if k not in HEAVY}, "meta": meta,
            "shape": shape,
            "family": (scenario or {}).get("family", "composite"),
            "key": key,
            "arm": meta.get("arm", "pair"),
            "pair": tuple(meta.get("source_pair") or ()),
            "slots": meta.get("slots") or {},
            "carries": meta.get("carries") or {},
            "pinned": tuple(meta.get("operator_pinned") or ()),
            "winner": _winner(row),
        })
    if not rows:
        raise AnalysisError(f"{path}: no scored records in it")
    return rows


def pair_kinds(rows: Sequence[Mapping[str, Any]]
               ) -> dict[str, set[tuple[str, ...]]]:
    """Sort the source pairs into the three kinds, from the run's own records.
    within_message (both pinned, so one message: PRIMACY), free (order varied: the only
    clean read), pinned (always first, confounded). Pooling the first two averaged 0.834
    recency with 0.260 primacy into 0.716, describing nothing that happened."""
    kinds: dict[str, set[tuple[str, ...]]] = {
        "within_message": set(), "free": set(), "pinned": set()}
    orders: dict[tuple[str, ...], set[bool]] = collections.defaultdict(set)
    pinned_in: dict[tuple[str, ...], tuple[str, ...]] = {}
    for r in rows:
        if r["arm"] != "pair" or len(r["pair"]) != 2:
            continue
        a, b = r["pair"]
        sa, sb = r["slots"].get(a), r["slots"].get(b)
        pinned_in[r["pair"]] = r["pinned"]
        if sa is None or sb is None or sa == sb:
            continue
        orders[r["pair"]].add(sa < sb)
    for pair, seen in orders.items():
        both = all(s in pinned_in.get(pair, ()) for s in pair)
        if both:
            kinds["within_message"].add(pair)
        elif len(seen) == 2:
            kinds["free"].add(pair)
        else:
            kinds["pinned"].add(pair)
    return kinds


def free_pairs(rows: Sequence[Mapping[str, Any]]) -> set[tuple[str, ...]]:
    """The pairs where position can be read: order varied, separate messages."""
    return pair_kinds(rows)["free"]


# --- The sections ---


# Fingerprints whose source scores exactly as a later one; here, outside what the hash covers.
SAME_SCORING = {
    # 51e74e1 changed one docstring in runner/run.py.
    "sha256:152b3fed8fd5ee855eaa318c005449e3": "sha256:948ddfa0cf2b279f859ee7af75d25645",
    # The public release renamed the package ipb to whowins and edited comments; no code changed.
    "sha256:804aaeebb4fa85279b75be39c9554994": "sha256:8f98cf36452919fd4269e4d8fbf098c3",
}


def scored_as(fp: Optional[str]) -> Optional[str]:
    """The fingerprint whose verdicts `fp`'s are: itself, or the later one in SAME_SCORING."""
    while fp in SAME_SCORING:
        fp = SAME_SCORING[fp]
    return fp


def staleness(rows) -> dict[str, Any]:
    """Whether these verdicts were made by the checkers installed now.
    Free: every record carries `whowins.checkers.fingerprint()`. A 400-row sample was tried
    and finds a 15-in-9,720 change less than half the time, printing "none moves" the
    rest. Records predating the fingerprint say UNKNOWN rather than guess."""
    from ..checkers import fingerprint

    today = fingerprint()
    seen = collections.Counter(r["row"].get("checker_fingerprint") for r in rows)
    unstamped = seen.pop(None, 0)
    return {"today": today, "in_the_log": dict(seen), "unstamped": unstamped,
            "agrees": (not unstamped) and {scored_as(f) for f in seen} == {scored_as(today)},
            "unknown": bool(unstamped)}


def hygiene(rows) -> dict[str, Any]:
    """Whether this run is one run. Read this before any other number."""
    fp = collections.Counter(r["row"].get("serving_fingerprint") for r in rows)
    conc = collections.Counter(r["row"].get("concurrency") for r in rows)
    at = sorted(r["row"].get("at") or "" for r in rows)
    out = {
        "draws": len(rows),
        "serving_fingerprints": dict(fp),
        "concurrency": {str(k): v for k, v in conc.items()},
        "first_record": at[0] if at else None,
        "last_record": at[-1] if at else None,
        "truncated": sum(1 for r in rows if r["row"].get("finish_reason") == "length"),
        "with_faults": sum(1 for r in rows if r["row"].get("faults")),
        "unusable": sum(1 for r in rows if not r["row"].get("usable")),
        "stopped_by": dict(collections.Counter(r["row"].get("stopped_by") for r in rows)),
        "turns": dict(sorted(collections.Counter(
            r["row"].get("turns", 1) for r in rows).items())),
    }
    out["one_snapshot"] = len(fp) == 1
    out["one_concurrency"] = len(conc) == 1
    return out


def outcomes(rows) -> dict[str, Any]:
    """The behaviour split, per family and per arm, and per composition size.

    THE TWO ARMS ARE NOT COMPARABLE PER TRIAL: a solo trial shows one option of
    five and a conflict shows two, so the solo arm scores off-menu more for a
    purely arithmetic reason. Sizes are split out because a ladder run puts two,
    three and five sources in one log and "pair" would be the wrong word for all.
    """
    out: dict[str, Any] = {}
    for arm in sorted({r["arm"] for r in rows}):
        per: dict[str, collections.Counter] = collections.defaultdict(
            collections.Counter)
        for r in rows:
            if r["arm"] != arm:
                continue
            per[r["family"]][r["row"].get("behaviour")] += 1
            per["ALL"][r["row"].get("behaviour")] += 1
        out[arm] = {
            family: {"n": sum(c.values()),
                     **{k: c.get(k, 0) / sum(c.values()) for k in BEHAVIOURS}}
            for family, c in sorted(per.items())}

    sizes: dict[int, collections.Counter] = collections.defaultdict(
        collections.Counter)
    for r in rows:
        sizes[len(r["carries"])][r["row"].get("behaviour")] += 1
    out["by_size"] = {
        str(size): {"n": sum(c.values()),
                    **{k: c.get(k, 0) / sum(c.values()) for k in BEHAVIOURS}}
        for size, c in sorted(sizes.items()) if size}
    return out


def position(rows) -> dict[str, Any]:
    """Does the later instruction win, and by how much.
    The question the balanced design was built for. Three ways, because they say
    different things: pairs whose order was free (clean), pairs the chat format pins
    (recency plus whatever being an operator costs), and by where the task line sits."""
    kinds = pair_kinds(rows)
    free = kinds["free"]
    # TWO SOURCES ONLY. "Which arrived later" has an answer for a pair and not a triple; this used to take an arbitrary loser.
    larger = sum(1 for r in rows if r["arm"] == "pair" and len(r["carries"]) > 2)
    decided = [r for r in rows if r["arm"] == "pair" and r["winner"]
               and len(r["carries"]) == 2]
    per_pair: dict[tuple, list[int]] = collections.defaultdict(lambda: [0, 0])
    same_message: list[int] = [0, 0]
    by_task: dict[Any, list[int]] = collections.defaultdict(lambda: [0, 0])
    by_source_pos: dict[tuple, list[int]] = collections.defaultdict(lambda: [0, 0])

    for r in decided:
        w = r["winner"]
        others = [s for s in r["carries"] if s != w]
        if not others:
            continue
        o = others[0]
        sw, so = r["slots"].get(w), r["slots"].get(o)
        if sw is None or so is None:
            continue
        if sw == so:
            same_message[1] += 1
            continue
        later = sw > so
        per_pair[r["pair"]][1] += 1
        per_pair[r["pair"]][0] += int(later)
        if r["pair"] in free:
            by_task[r["slots"].get("task")][1] += 1
            by_task[r["slots"].get("task")][0] += int(later)
            for s in r["carries"]:
                other = [x for x in r["carries"] if x != s][0]
                if r["slots"].get(s) is None or r["slots"].get(other) is None:
                    continue
                where = "last" if r["slots"][s] > r["slots"][other] else "first"
                by_source_pos[(s, where)][1] += 1
                by_source_pos[(s, where)][0] += int(s == w)

    def total(which: set) -> tuple[int, int]:
        return (sum(per_pair[p][0] for p in which if p in per_pair),
                sum(per_pair[p][1] for p in which if p in per_pair))
    return {
        "decided": len(decided),
        "larger_compositions_not_read_here": larger,
        "pair_kinds": {k: sorted("-".join(p) for p in v) for k, v in kinds.items()},
        "free_pairs": sorted("-".join(p) for p in free),
        "later_wins_free": _rate(*total(kinds["free"])),
        "later_wins_pinned": _rate(*total(kinds["pinned"])),
        "second_line_wins_within_message": _rate(*total(kinds["within_message"])),
        "later_wins_by_pair": {"-".join(p): _rate(*per_pair[p]) for p in sorted(per_pair)},
        "same_message_draws": same_message[1],
        "later_wins_by_task_slot": {str(k): _rate(*v) for k, v in sorted(
            by_task.items(), key=lambda kv: (kv[0] is None, kv[0]))},
        "source_by_position": {f"{s}|{w}": _rate(*by_source_pos[(s, w)])
                               for (s, w) in sorted(by_source_pos)},
    }


def sources(rows) -> dict[str, Any]:
    """Which source wins, overall and at a matched position.
    The overall column is what a sorted design reports and is worth little: if position
    moves the outcome and a source's position is fixed, it measures the position. The
    matched column separates them."""
    free = free_pairs(rows)
    overall: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    by_size: dict[tuple, list[int]] = collections.defaultdict(lambda: [0, 0])
    matched: dict[tuple, list[int]] = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        if r["arm"] != "pair" or not r["winner"]:
            continue
        for s in r["carries"]:
            overall[s][1] += 1
            overall[s][0] += int(s == r["winner"])
            by_size[(len(r["carries"]), s)][1] += 1
            by_size[(len(r["carries"]), s)][0] += int(s == r["winner"])
        # Two sources only. `free` holds pairs, so this was already true, but
        # `other` takes an arbitrary loser and would be wrong the moment it was not.
        if len(r["carries"]) != 2 or r["pair"] not in free:
            continue
        for s in r["carries"]:
            other = [x for x in r["carries"] if x != s][0]
            if r["slots"].get(s) is None or r["slots"].get(other) is None:
                continue
            where = "last" if r["slots"][s] > r["slots"][other] else "first"
            matched[(s, where)][1] += 1
            matched[(s, where)][0] += int(s == r["winner"])
    spread = {}
    for where in ("first", "last"):
        vals = [matched[(s, w)][0] / matched[(s, w)][1]
                for (s, w) in matched if w == where and matched[(s, w)][1]]
        spread[where] = (max(vals) - min(vals)) if len(vals) > 1 else None
    return {
        "overall": {s: _rate(*overall[s]) for s in sorted(overall)},
        # Pooled across sizes the chance level differs -- one in two against one in
        # five -- so an overall rate mixes "wins often" with "was in small sets".
        "overall_by_size": {
            str(size): {s: _rate(*by_size[(size, s)])
                        for (n, s) in sorted(by_size) if n == size}
            for size in sorted({n for n, _ in by_size})},
        "matched_position": {f"{s}|{w}": _rate(*matched[(s, w)])
                             for (s, w) in sorted(matched)},
        "spread_between_sources_at_matched_position": spread,
    }


def solo(rows) -> dict[str, Any]:
    """What the model can do with nobody disagreeing, and what that predicts.
    Per OPTION, not per trial. Nothing is dropped on the strength of it. The three-row
    table is a mix -- where both options are always producible exactly one wins, so a
    better model drags its own `always` row towards 0.5. Compare the cross-tabulation."""
    per_option: dict[tuple, list[int]] = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        if r["arm"] != "solo":
            continue
        opts = list(r["carries"].values())
        if len(opts) != 1:
            continue
        key = (r["row"].get("scenario_id"), opts[0])
        per_option[key][1] += 1
        per_option[key][0] += int(r["row"].get("winning_option") == opts[0])

    def tier_of(sid: Any, opt: Any) -> Optional[str]:
        hits, n = per_option.get((sid, opt), (0, 0))
        if not n:
            return None
        return "never" if hits == 0 else ("always" if hits == n else "sometimes")

    tiers: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    cells: dict[tuple[str, str], list[int]] = collections.defaultdict(lambda: [0, 0])
    both_always = 0
    for r in rows:
        if r["arm"] != "pair":
            continue
        sid = r["row"].get("scenario_id")
        carried = [(opt, tier_of(sid, opt)) for opt in r["carries"].values()]
        if len(carried) == 2 and all(t == "always" for _, t in carried):
            both_always += 1
        for i, (opt, tier) in enumerate(carried):
            if tier is None:
                continue
            won = int(r["row"].get("winning_option") == opt)
            tiers[tier][1] += 1
            tiers[tier][0] += won
            if len(carried) != 2:
                continue
            against = carried[1 - i][1]
            if against is not None:
                cells[(tier, against)][1] += 1
                cells[(tier, against)][0] += won

    by_scen: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    fam_of: dict[str, str] = {}
    for r in rows:
        if r["arm"] != "solo":
            continue
        sid = r["row"].get("scenario_id")
        fam_of[sid] = r["family"]
        by_scen[sid][1] += 1
        by_scen[sid][0] += int(r["row"].get("behaviour") == "chose")
    never = [s for s, (k, _) in by_scen.items() if k == 0]
    always = [s for s, (k, n) in by_scen.items() if k == n]

    restricted = [r for r in rows if r["arm"] == "pair"
                  and r["row"].get("scenario_id") in set(always)]
    rc = collections.Counter(r["row"].get("behaviour") for r in restricted)
    allc = collections.Counter(r["row"].get("behaviour")
                              for r in rows if r["arm"] == "pair")
    n_all = sum(allc.values()) or 1
    n_res = sum(rc.values())
    return {
        "has_solo_arm": bool(per_option),
        "options_measured": len(per_option),
        "conflict_win_by_solo_ability": {t: _rate(*tiers[t])
                                         for t in ("never", "sometimes", "always")},
        "conflict_win_by_both_abilities": {
            f"{t} vs {o}": _rate(*cells[(t, o)])
            for t in ("never", "sometimes", "always")
            for o in ("never", "sometimes", "always")
            if cells[(t, o)][1]},
        "both_always_conflicts": both_always,
        "scenarios": len(by_scen),
        "never_solo": len(never),
        "never_solo_by_family": dict(collections.Counter(fam_of[s] for s in never)),
        "always_solo": len(always),
        "conflict_all": {"n": n_all,
                         **{k: allc.get(k, 0) / n_all for k in
                            ("chose", "unresolved", "off_menu", "no_action")}},
        "conflict_where_solo_always": ({
            "n": n_res,
            **{k: rc.get(k, 0) / n_res for k in
               ("chose", "unresolved", "off_menu", "no_action")}}
            if n_res else None),
    }


def unresolved(rows, scenarios, opened: bool = False) -> dict[str, Any]:
    """Why a reply could not be labelled: the model, or us.

    `artifact_shaped` is the only bucket that can be OUR fault, and it is the one
    to read first after a run."""
    buckets: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    keys: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for r in rows:
        row = r["row"]
        if row.get("behaviour") != "unresolved":
            continue
        shape = r.get("shape") or reply_shape(
            row, r["key"], scenarios.get(row.get("scenario_id")), opened)
        buckets[r["family"]][shape] += 1
        if shape == "artifact_shaped":
            keys[r["family"]][r["key"]] += 1
    return {
        "by_family": {f: dict(c) for f, c in sorted(buckets.items())},
        "unlabelled_keys": {f: c.most_common(10) for f, c in sorted(keys.items())},
        "distinct_unlabelled_keys": {f: len(c) for f, c in sorted(keys.items())},
    }


def items(rows, scenarios, opened: bool = False) -> dict[str, Any]:
    """Which scenarios measured nothing here, named, with the evidence attached.
    Names and not counts: a count cannot be intersected with the next run's, and only the
    intersection separates "no model can" from "this model could not". Artifact-shaped
    but unlabelled is ours; nothing artifact-shaped is the model's. It drops nothing."""
    chose: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    solo_chose: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    shape: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    about: dict[str, tuple] = {}
    for r in rows:
        row = r["row"]
        sid = row.get("scenario_id")
        if not sid:
            continue
        about[sid] = (r["family"], r["key"])
        chose[sid][1] += 1
        chose[sid][0] += int(row.get("behaviour") == "chose")
        if r["arm"] == "solo":
            solo_chose[sid][1] += 1
            solo_chose[sid][0] += int(row.get("behaviour") == "chose")
        shape[sid][r.get("shape") or reply_shape(row, r["key"], scenarios.get(sid), opened)] += 1

    never_labelled = {
        sid: {"family": about[sid][0], "key": about[sid][1],
              "draws": chose[sid][1], **dict(shape[sid])}
        for sid, (hits, _) in sorted(chose.items()) if hits == 0}
    never_solo = sorted(sid for sid, (hits, n) in solo_chose.items()
                        if n and hits == 0)
    return {
        "scenarios": len(chose),
        # Every scenario this section names, with its family, so a comparison can group them without loading the collection.
        "family_of": {sid: about[sid][0]
                      for sid in sorted(set(never_labelled) | set(never_solo))},
        "never_labelled": never_labelled,
        "never_labelled_by_family": dict(collections.Counter(
            v["family"] for v in never_labelled.values())),
        "never_solo": never_solo,
        "never_solo_by_family": dict(collections.Counter(
            about[s][0] for s in never_solo)),
    }


def repeats(rows) -> dict[str, Any]:
    """How much of the outcome is the draw rather than the item.
    A trial whose draws disagree is one a single-draw run would have mislabelled."""
    per: dict[str, dict[int, str]] = collections.defaultdict(dict)
    for r in rows:
        per[r["row"]["trial_id"]][r["row"].get("repeat", 0)] = r["row"].get("behaviour")
    agree: collections.Counter = collections.Counter()
    drawn = 0
    for _, d in per.items():
        if len(d) < 2:
            continue
        drawn += 1
        agree["unanimous" if len(set(d.values())) == 1 else "split"] += 1
    total = sum(agree.values())
    return {"trials_with_several_draws": drawn,
            "unanimous": _rate(agree["unanimous"], total),
            "single_draw_would_mislabel": (agree["split"] / total) if total else None}


def _which_won(r: Mapping[str, Any]) -> Optional[str]:
    """`later` or `earlier` for a conflict won by the last- or an earlier-placed source,
    `policy` or `against` on a tier trial, None when nothing in play was chosen."""
    row, meta = r["row"], r["meta"]
    if meta.get("arm") == "tier":
        if row.get("behaviour") != "chose":
            return None
        return "policy" if row.get("winning_option") == meta.get("policy_winner") else "against"
    placed = {s: r["slots"][s] for s in r["carries"] if s in r["slots"]}
    if r["winner"] not in placed or len(placed) < 2:
        return None
    return "later" if placed[r["winner"]] == max(placed.values()) else "earlier"


def communication(rows) -> dict[str, Any]:
    """Whether the model ever said the instructions disagreed, and which one it then followed.
    A separate axis from behaviour: a model can flag the conflict and still obey the
    wrong instruction, so flagging is not a third slot in the same multinomial."""
    out = {}
    for arm in sorted({r["arm"] for r in rows}):
        sel = [r for r in rows if r["arm"] == arm]
        c = collections.Counter(r["row"].get("communication") for r in sel)
        by_winner: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for r in sel:
            won = _which_won(r)
            if won is not None:
                by_winner[won][r["row"].get("communication")] += 1
        out[arm] = {"n": len(sel),
                    **{k: {"count": c.get(k, 0), "rate": c.get(k, 0) / len(sel)}
                       for k in ("silent", "hedged", "flagged")},
                    "by_winner": {w: {k: n.get(k, 0) for k in ("silent", "hedged", "flagged")}
                                  for w, n in sorted(by_winner.items())}}
    return out


def analyse(run_id: str, log_path: Optional[str] = None,
            scenarios: Optional[Mapping[str, Any]] = None,
            run: Optional[Any] = None) -> dict[str, Any]:
    run = run if run is not None else load_run(run_id)
    scenarios = scenarios if scenarios is not None else load_scenarios()
    opened = bool(getattr(run.model.family, "thinking_prefills_open_block", False))
    rows = load_rows(run_id, log_path, scenarios, opened)
    log.info("%s: %d scored draws over %d trials", run_id, len(rows),
             len({r["row"]["trial_id"] for r in rows}))
    # An unusable reply is not behaviour; hygiene, scoring and the coverage sections read every row.
    usable = [r for r in rows if r["row"].get("usable") is not False]
    return {
        "run_id": run_id,
        "model": run.model.key,
        "environment": run.environment.key,
        "design": run.design,
        "hygiene": hygiene(rows),
        "scoring": staleness(rows),
        "outcomes": outcomes(usable),
        "position": position(usable),
        "sources": sources(usable),
        "solo": solo(usable),
        "unresolved": unresolved(rows, scenarios, opened),
        "items": items(rows, scenarios, opened),
        "repeats": repeats(usable),
        "communication": communication(usable),
    }


# --- Printing ---


def _print_scoring(s) -> None:
    if s["agrees"]:
        older = sorted(set(s["in_the_log"]) - {s["today"]})
        print(f"  yes -- every record carries {s['today']}, which is what is installed"
              + (f",\n  or {', '.join(older)}, which scores the same (SAME_SCORING)"
                 if older else ""))
        return
    if s["unknown"]:
        print(f"  UNKNOWN. {s['unstamped']} records predate the checker fingerprint,")
        print(f"  so this cannot be answered for free. Before comparing this run")
        print(f"  with another, settle it:")
    else:
        print(f"  *** NO. These verdicts were made by different checkers. ***")
        print(f"  in the log: {s['in_the_log']}")
        print(f"  installed:  {s['today']}")
        print(f"  Comparing this run with one scored under other rules would read")
        print(f"  the checkers' change as the model's. Rescore first:")
    print(f"      scripts/rescore.sh <run_id> --changed 10      # what would move")
    print(f"      scripts/rescore.sh <run_id> --write           # rescored.jsonl")
    print(f"      scripts/analyse.sh <run_id> --log results/<run_id>/rescored.jsonl")


def _print_hygiene(h) -> None:
    print(f"  draws {h['draws']}, {h['first_record']} .. {h['last_record']}")
    print(f"  one serving snapshot: {h['one_snapshot']}  {h['serving_fingerprints']}")
    print(f"  concurrency: {h['concurrency']}")
    print(f"  truncated {h['truncated']}, with faults {h['with_faults']}, "
          f"unusable {h['unusable']}")
    print(f"  stopped_by {h['stopped_by']}")
    print(f"  turns {h['turns']}")


def _print_outcomes(o) -> None:
    for arm in (k for k in o if k != "by_size"):
        print(f"  {arm}:")
        print(f"    {'family':10s} {'n':>6} {'chose':>8} {'unres':>8} "
              f"{'off_menu':>9} {'multiple':>9} {'no_act':>8}")
        for family, cell in o[arm].items():
            print(f"    {family:10s} {cell['n']:>6} {cell['chose']:>8.3f} "
                  f"{cell['unresolved']:>8.3f} {cell['off_menu']:>9.3f} "
                  f"{cell['multiple']:>9.3f} {cell['no_action']:>8.3f}")
    if len(o.get("by_size") or {}) > 1:
        print("  by how many sources competed:")
        print(f"    {'size':>4} {'n':>6} {'chose':>8} {'unres':>8} {'off_menu':>9} "
              f"{'multiple':>9} {'no_act':>8}")
        for size, cell in o["by_size"].items():
            print(f"    {size:>4} {cell['n']:>6} {cell['chose']:>8.3f} "
                  f"{cell['unresolved']:>8.3f} {cell['off_menu']:>9.3f} "
                  f"{cell['multiple']:>9.3f} {cell['no_action']:>8.3f}")


def _print_position(p) -> None:
    if p.get("larger_compositions_not_read_here"):
        print(f"  {p['larger_compositions_not_read_here']} draws had more than two "
              f"sources competing and are NOT in this section:")
        print("  \"which one arrived later\" has an answer for a pair and not for a "
              "triple.")
    print(f"  decided conflict draws: {p['decided']}")
    for kind, names in p["pair_kinds"].items():
        print(f"    {kind:15s} {', '.join(names) or 'none'}")
    print(f"  LATER SOURCE WINS, order free   {_fmt(p['later_wins_free'])}")
    print(f"  LATER SOURCE WINS, order pinned {_fmt(p['later_wins_pinned'])}")
    print(f"  SECOND LINE WINS, one message   "
          f"{_fmt(p['second_line_wins_within_message'])}  <- primacy, other way")
    print("  by pair:")
    for name, cell in p["later_wins_by_pair"].items():
        print(f"    {name:10s}{_fmt(cell)}")
    print("  by where the task line sits (free pairs only):")
    for slot, cell in p["later_wins_by_task_slot"].items():
        print(f"    task slot {slot:4s}{_fmt(cell)}")
    print("  each source, first vs last (free pairs only):")
    for name, cell in p["source_by_position"].items():
        print(f"    {name:10s}{_fmt(cell)}")


def _print_sources(s) -> None:
    by_size = s.get("overall_by_size") or {}
    if len(by_size) > 1:
        print("  overall win rate, per size -- pooled it would mix a one-in-two")
        print("  chance level with a one-in-five one:")
        for size, cells in by_size.items():
            print(f"    {size} sources competing:")
            for name, cell in cells.items():
                print(f"      {name:10s}{_fmt(cell)}")
    else:
        print("  overall win rate (confounded with position wherever a pair is pinned):")
        for name, cell in s["overall"].items():
            print(f"    {name:10s}{_fmt(cell)}")
    print("  at a matched position (free pairs only) -- this is the honest one:")
    for name, cell in s["matched_position"].items():
        print(f"    {name:10s}{_fmt(cell)}")
    sp = s["spread_between_sources_at_matched_position"]
    print(f"  spread between sources at the same position: "
          + ", ".join(f"{k}={v:.3f}" for k, v in sp.items() if v is not None))


def _print_solo(s) -> None:
    if not s.get("has_solo_arm"):
        print("  This run has no solo arm, so there is nothing to report here.")
        print("  `composition_sizes` did not ask for 1: solo ability is a property of")
        print("  (scenario, option) and has to be measured, not inferred from conflicts.")
        return
    print(f"  options with a solo arm: {s['options_measured']}")
    print("  how often an option wins its conflict, by whether the model can "
          "produce it alone:")
    for tier, cell in s["conflict_win_by_solo_ability"].items():
        print(f"    solo {tier:10s}{_fmt(cell)}")
    print("  ^ A MIX. Where both options are always producible exactly one wins,")
    print("    so that cell is pinned near 0.5 by construction -- and a better")
    print(f"    model puts more of its conflicts there ({s['both_always_conflicts']} "
          f"of {s['conflict_all']['n']} here), pulling")
    print("    the `always` row down as it improves. Compare runs on this instead:")
    for pairing, cell in s["conflict_win_by_both_abilities"].items():
        print(f"    {pairing:24s}{_fmt(cell)}")
    print(f"  scenarios: {s['scenarios']};  never done solo: {s['never_solo']} "
          f"{s['never_solo_by_family']};  always: {s['always_solo']}")
    a, b = s["conflict_all"], s["conflict_where_solo_always"]
    print(f"  conflict trials, all scenarios        n={a['n']:6d}  chose {a['chose']:.3f}")
    if b:
        print(f"  conflict trials, solo-always only     n={b['n']:6d}  "
              f"chose {b['chose']:.3f}")


SHAPE_PROSE = {
    "empty": "empty reply",
    "truncated": "truncated",
    "no_artifact": "no artifact: the reply is talk or framing",
    "artifact_shaped": "artifact-shaped, and no classifier would label it",
}


def _print_unresolved(u) -> None:
    for fam, buckets in u["by_family"].items():
        total = sum(buckets.values())
        print(f"  {fam} ({total}):")
        for name, n in sorted(buckets.items(), key=lambda kv: -kv[1]):
            print(f"     {n:6d} ({n/total:5.1%})  {SHAPE_PROSE.get(name, name)}")
        if u["distinct_unlabelled_keys"].get(fam):
            print(f"     ... the last bucket spans "
                  f"{u['distinct_unlabelled_keys'][fam]} checker keys; top: "
                  + ", ".join(f"{k}({n})" for k, n in u["unlabelled_keys"][fam][:6]))


def _print_items(i) -> None:
    nl, ns = i["never_labelled"], i["never_solo"]
    print(f"  scenarios: {i['scenarios']}")
    print(f"  never produced unopposed here:   {len(ns):4d}  {i['never_solo_by_family']}")
    print(f"  never labelled in ANY arm here:  {len(nl):4d}  "
          f"{i['never_labelled_by_family']}")
    if not nl:
        return
    ours = {s: v for s, v in nl.items()
            if v.get("artifact_shaped", 0) * 2 >= v["draws"]}
    print(f"  of those, artifact-shaped on most draws: {len(ours)} -- a classifier")
    print("  that cannot read what it is given, or a task whose honest answer is")
    print("  prose. The rest is the model declining to produce an artifact.")
    for sid, v in list(sorted(ours.items()))[:12]:
        print(f"    {sid:12s} {v['family']:9s} {str(v['key'])[:28]:28s} "
              f"shaped {v.get('artifact_shaped', 0)}/{v['draws']}")
    if len(ours) > 12:
        print(f"    ... and {len(ours) - 12} more; --json has every one of them")
    print("  NOTHING IS DROPPED ON THIS. One run says what THIS model could not do;")
    print("  only the same item failing on every run is a fact about the item:")
    print("      scripts/compare.sh a.json b.json     # after --json on each run")


def _print_repeats(r) -> None:
    print(f"  trials with several draws: {r['trials_with_several_draws']}")
    print(f"  every draw agreed        {_fmt(r['unanimous'])}")
    if r["single_draw_would_mislabel"] is not None:
        print(f"  a single draw would have mislabelled "
              f"{r['single_draw_would_mislabel']:.1%} of trials")


def _print_communication(c) -> None:
    for arm, cell in c.items():
        print(f"  {arm:6s} n={cell['n']:6d}  " + "  ".join(
            f"{k} {cell[k]['count']} ({cell[k]['rate']:.3f})"
            for k in ("silent", "hedged", "flagged")))
        for won, n in (cell.get("by_winner") or {}).items():
            total = sum(n.values())
            print(f"    {won + ' won':12s} n={total:6d}  " + "  ".join(
                f"{k} {n[k]} ({n[k] / total:.3f})" for k in ("silent", "hedged", "flagged")))


PRINTERS = {
    "scoring": _print_scoring, "hygiene": _print_hygiene, "outcomes": _print_outcomes,
    "position": _print_position, "sources": _print_sources, "solo": _print_solo,
    "unresolved": _print_unresolved, "items": _print_items,
    "repeats": _print_repeats,
    "communication": _print_communication,
}

TITLES = {
    "scoring": "WERE THESE VERDICTS MADE BY TODAY'S CHECKERS?",
    "hygiene": "IS THIS ONE RUN?",
    "outcomes": "WHAT THE MODEL DID  (the two arms are not comparable per trial)",
    "position": "DOES THE LATER INSTRUCTION WIN?",
    "sources": "DOES THE SOURCE MATTER, ONCE POSITION IS HELD FIXED?",
    "solo": "CAN THE MODEL DO IT WITH NOBODY DISAGREEING?",
    "unresolved": "WHY A REPLY COULD NOT BE LABELLED",
    "items": "WHICH SCENARIOS MEASURED NOTHING HERE",
    "repeats": "THE DRAW, OR THE ITEM?",
    "communication": "DID IT EVER SAY THE INSTRUCTIONS DISAGREED?",
}


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m whowins.runner.analyse",
        description="Report what a finished run did. Fits nothing, predicts nothing.")
    parser.add_argument("run_id", help="a run in configs/runs/")
    parser.add_argument("--log", metavar="PATH",
                        help="the records log to read (default: "
                             "results/<run_id>/records.jsonl)")
    parser.add_argument("--section", nargs="+", choices=SECTIONS, default=list(SECTIONS),
                        metavar="NAME",
                        help=f"which sections to print (default: all of "
                             f"{', '.join(SECTIONS)})")
    parser.add_argument("--json", metavar="PATH", default=None,
                        help="also write every number to this file, so two runs "
                             "can be compared without re-deriving anything")
    add_arguments(parser, progress=False)
    args = parser.parse_args(argv)
    written = from_arguments("analyse", args, args.run_id)

    try:
        out = analyse(args.run_id, args.log)
    except (ConfigError, AnalysisError, KeyError, OSError) as exc:
        log.error("analyse error: %s", exc)
        return 2

    print(f"{out['run_id']}  --  {out['model']} at {out['environment']}, "
          f"design {out['design']}")
    for name in args.section:
        print(f"\n{TITLES[name]}")
        PRINTERS[name](out[name])
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, sort_keys=False)
            fh.write("\n")
        log.info("wrote %s", args.json)
        print(f"\nwritten: {args.json}")
    if written:
        log.info("this report's log: %s", written)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
