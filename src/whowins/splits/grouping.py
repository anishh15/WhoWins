"""When are two base scenarios too alike to sit on opposite sides of a split?
The obvious answer is wrong: the field the dataset plan names is unique per scenario, so
following it literally groups nothing. Three within-family link rules are used instead, and
`check.py` refuses a grouping that turns out to be all singletons."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Sequence

from ..data import iter_scenarios

# --- Parameters, every one chosen by measuring the collection. Changing one changes the frozen splits, so it is a pre-registration decision ---

FRAME_MIN_SHARE = 0.25
"""A word is part of a family's frame if it appears in at least this share of
that family's tasks.

Chosen because the *grouping it produces* is identical at 0.20, 0.25 and 0.30 --
the same 1,038 groups with the same largest of 14, not merely similar counts. The
individual frames do shift a little over that band (refusal's is 9 words at 0.20
and 5 at 0.30) and it does not matter, because the words entering and leaving are
ones no pair's similarity turns on. Outside the band it does matter: 0.15 strips
too much and gives 1,054 groups, 0.40 too little and gives 1,024 with a largest
of 19."""

TASK_TAU = 0.40
"""Frame-stripped Jaccard at or above this links two scenarios.

Unlike the frame threshold this one sits on a slope, not a plateau, and the value
is a judgement rather than a discovery:

    tau    0.30   0.35   0.40   0.45   0.50
    groups  960   1012   1038   1060   1063
    largest  45     33     14      5      5

0.40 is the lowest value whose largest group is still small enough to balance
across three sides. Lower is a stronger leakage guard and a coarser split; 0.45
and above stop catching the `path` family's genuinely similar object-store items.
Moving it re-freezes the splits, so it is a pre-registration decision."""

SHARED_VALUES_MIN = 3
"""Same checker key and at least this many shared checker values. Four is
already a FAIL in check_batch.py, so three is the widest reachable band."""

SHARED_SUFFIX_MIN = 4
"""tool and path only: at least this many shared distinguishing-token sets out
of five. Identical suffix sets are already a FAIL upstream; four-of-five is not,
and three real pairs sit there."""


# ------------------------------------------------------------------- loading


def load_collection() -> list[dict]:
    """Every base scenario, with its batch file recorded as `_batch`.
    Read through `whowins.data`, which imports nothing from the checkers: splitting the collection
    has no business depending on how it is scored."""
    out = []
    for batch, s in iter_scenarios():
        s["_batch"] = batch
        out.append(s)
    return out


# --------------------------------------------------------------- link rules


def _words(task: str) -> set[str]:
    return set(task.lower().rstrip(".").split())


def family_frames(collection: Sequence[dict]) -> dict[str, frozenset[str]]:
    """The stock phrasing of each family: words in >= FRAME_MIN_SHARE of its tasks.

    Discovered per family rather than written down, so a family whose items are
    all phrased freely gets an almost empty frame and loses nothing."""
    by_family: dict[str, list[dict]] = defaultdict(list)
    for s in collection:
        by_family[s["family"]].append(s)

    frames = {}
    for family, items in by_family.items():
        counts: Counter = Counter()
        for s in items:
            counts.update(_words(s["task"]))
        floor = FRAME_MIN_SHARE * len(items)
        frames[family] = frozenset(w for w, n in counts.items() if n >= floor)
    return frames


def content_words(s: dict, frames: dict[str, frozenset[str]]) -> frozenset[str]:
    """A task's words with its family's frame removed."""
    return frozenset(_words(s["task"]) - frames.get(s["family"], frozenset()))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def checker_values(s: dict) -> frozenset[str]:
    return frozenset(o["checker"].split("==", 1)[1] for o in s["options"])


def suffix_sets(s: dict) -> frozenset[frozenset[str]]:
    """The distinguishing part of each value once the shared prefix is removed.

    Same construction as `suffix_set()` in check_batch.py, which fails on an
    exact match; this is the near-match band underneath it."""
    tokens = [
        set(re.split(r"[_\-/.]", o["checker"].split("==", 1)[1].lower()))
        for o in s["options"]
    ]
    shared = set.intersection(*tokens)
    return frozenset(frozenset(t - shared) for t in tokens)


def link_reason(a: dict, b: dict, frames: dict[str, frozenset[str]]) -> str | None:
    """Why these two scenarios must not be separated, or None if they may be.

    Returns the rule name so the built split can show its work: a group nobody
    can explain is a group nobody can check."""
    if a["family"] != b["family"]:
        return None

    if _jaccard(content_words(a, frames), content_words(b, frames)) >= TASK_TAU:
        return "task"

    if a["family"] != "refusal" and a["checker_key"] == b["checker_key"]:
        if len(checker_values(a) & checker_values(b)) >= SHARED_VALUES_MIN:
            return "values"

    if a["family"] in ("tool", "path"):
        if len(suffix_sets(a) & suffix_sets(b)) >= SHARED_SUFFIX_MIN:
            return "suffix"

    return None


# ------------------------------------------------------------------ grouping


class _Union:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, a: int) -> int:
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def build_groups(collection: Sequence[dict]) -> tuple[dict[str, list[str]], list[dict]]:
    """Group ids -> scenario ids, plus every link that was drawn and why.

    Groups are named for their lowest member so the same collection always
    produces the same group names, with no dependence on iteration order."""
    frames = family_frames(collection)
    union = _Union(len(collection))
    links = []

    by_family: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(collection):
        by_family[s["family"]].append(i)

    # Only within-family pairs can link, so the ~440,000 cross-family pairs are skipped.
    for members in by_family.values():
        for pos, i in enumerate(members):
            for j in members[pos + 1:]:
                reason = link_reason(collection[i], collection[j], frames)
                if reason:
                    union.union(i, j)
                    links.append({
                        "a": collection[i]["scenario_id"],
                        "b": collection[j]["scenario_id"],
                        "rule": reason,
                    })

    members: dict[int, list[str]] = defaultdict(list)
    for i, s in enumerate(collection):
        members[union.find(i)].append(s["scenario_id"])

    groups = {}
    for ids in members.values():
        groups["g-" + min(ids)] = sorted(ids)
    return dict(sorted(groups.items())), sorted(
        links, key=lambda x: (x["a"], x["b"])
    )


def group_of(groups: dict[str, list[str]]) -> dict[str, str]:
    """scenario id -> its group id."""
    return {sid: gid for gid, ids in groups.items() for sid in ids}


def singleton_share(groups: dict[str, list[str]]) -> float:
    """Fraction of groups holding exactly one scenario.
    The number that catches the `seed_family` trap: a grouping where this is 1.0 has grouped
    nothing, and `check.py` refuses such a split."""
    if not groups:
        return 0.0
    return sum(1 for ids in groups.values() if len(ids) == 1) / len(groups)
