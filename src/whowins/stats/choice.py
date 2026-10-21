"""One measurement: some options competed, and one of them won -- or none did.
Deliberately not a trial: no chat templates, tool calls, repeats or checkers, so
the same code reads a simulated world and a real log. The resampling unit is the
ITEM. `won=None` is an outcome, not a missing value.
"""

from __future__ import annotations

import collections
import itertools
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Mapping, Optional, Sequence


class ChoiceError(ValueError):
    """A choice that does not describe a measurement."""


@dataclass(frozen=True)
class Option:
    """One thing the model could have done, and where it was asked from.
    `position` is None when the design did not record one -- which is not slot 0 and
    must never be filled in as one."""
    option_id: str
    source: str
    position: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.option_id or not self.source:
            raise ChoiceError("an option needs an id and a source")


@dataclass(frozen=True)
class Choice:
    """One measurement: which options competed, and which won.
    `won` is an option_id present in `options`, or None. `weight` carries identical
    choices as counts; every estimator is weight-aware so it is only a speed change."""
    item: str
    options: tuple[Option, ...]
    won: Optional[str]
    weight: int = 1
    tags: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.options) < 2:
            raise ChoiceError(
                f"{self.item}: a choice needs at least two options; one option "
                f"is a solo trial, which measures ability and not precedence")
        ids = [o.option_id for o in self.options]
        if len(set(ids)) != len(ids):
            raise ChoiceError(f"{self.item}: the same option twice: {ids}")
        srcs = [o.source for o in self.options]
        if len(set(srcs)) != len(srcs):
            raise ChoiceError(
                f"{self.item}: two options from source {srcs}: a composition is "
                f"a set of distinct sources")
        if self.won is not None and self.won not in ids:
            raise ChoiceError(f"{self.item}: {self.won} won, but it did not compete")
        if self.weight < 1:
            raise ChoiceError(f"{self.item}: weight {self.weight}")

    @property
    def sources(self) -> tuple[str, ...]:
        """The composition, sorted -- the key the ladder splits on."""
        return tuple(sorted(o.source for o in self.options))

    @property
    def composition(self) -> str:
        return "-".join(self.sources)

    @property
    def size(self) -> int:
        return len(self.options)

    def winning_source(self) -> Optional[str]:
        for o in self.options:
            if o.option_id == self.won:
                return o.source
        return None


class Dataset:
    """Choices, with the groupings every later step needs and nothing else."""

    def __init__(self, choices: Iterable[Choice]):
        self.choices: tuple[Choice, ...] = tuple(choices)

    def __len__(self) -> int:
        return len(self.choices)

    def __iter__(self) -> Iterator[Choice]:
        return iter(self.choices)

    def __repr__(self) -> str:
        return (f"Dataset({len(self.choices)} choices, {self.n_draws} draws, "
                f"{len(self.items)} items, {len(self.compositions)} compositions)")

    @property
    def n_draws(self) -> int:
        """Measurements, counting weights. `len()` counts rows."""
        return sum(c.weight for c in self.choices)

    @property
    def items(self) -> tuple[str, ...]:
        return tuple(sorted({c.item for c in self.choices}))

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(sorted({o.source for c in self.choices for o in c.options}))

    @property
    def compositions(self) -> tuple[tuple[str, ...], ...]:
        return tuple(sorted({c.sources for c in self.choices}))

    @property
    def sizes(self) -> dict[int, int]:
        out: collections.Counter = collections.Counter()
        for c in self.choices:
            out[c.size] += c.weight
        return dict(sorted(out.items()))

    def filter(self, predicate) -> "Dataset":
        return Dataset(c for c in self.choices if predicate(c))

    def with_compositions(self, wanted: Iterable[Sequence[str]]) -> "Dataset":
        keys = {tuple(sorted(w)) for w in wanted}
        return self.filter(lambda c: c.sources in keys)

    def abstentions(self) -> int:
        return sum(c.weight for c in self.choices if c.won is None)

    def wins_by_source(self) -> dict[str, int]:
        out: collections.Counter = collections.Counter()
        for c in self.choices:
            s = c.winning_source()
            if s is not None:
                out[s] += c.weight
        return dict(sorted(out.items()))

    def appearances_by_source(self) -> dict[str, int]:
        out: collections.Counter = collections.Counter()
        for c in self.choices:
            for o in c.options:
                out[o.source] += c.weight
        return dict(sorted(out.items()))

    def connected(self) -> bool:
        """Is the comparison graph over sources connected?
        A disconnected graph is unidentified, not merely hard: two components slide apart
        freely, so any difference between them is where the optimiser stopped."""
        srcs = self.sources
        if len(srcs) < 2:
            return True
        parent = {s: s for s in srcs}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for c in self.choices:
            first = c.options[0].source
            for o in c.options[1:]:
                a, b = find(first), find(o.source)
                if a != b:
                    parent[a] = b
        return len({find(s) for s in srcs}) == 1

    def summary(self) -> dict[str, Any]:
        return {
            "rows": len(self.choices), "draws": self.n_draws,
            "items": len(self.items), "sources": list(self.sources),
            "compositions": ["-".join(c) for c in self.compositions],
            "by_size": self.sizes, "abstentions": self.abstentions(),
            "connected": self.connected(),
        }


# --- Real records ---


def from_records(rows: Iterable[Mapping[str, Any]], *,
                 include_abstentions: bool = True) -> Dataset:
    """A run's scored records, read as choices. Conflict arm only, one option per source.
    A solo trial measures ability, not preference, and a free prediction, where sources share
    an option, is read by `free_from_records`. Position comes across: the later instruction
    wins about 0.9, so a strength fitted without a position term measures arrangement."""
    out = []
    for row in rows:
        meta = row.get("meta") or {}
        # An unusable reply measured nothing (docs/codebase/09_runner_execution.md, section 3).
        if (meta.get("arm") or "pair") != "pair" or row.get("usable") is False:
            continue
        carries = meta.get("carries") or {}
        if len(carries) < 2 or len(set(carries.values())) != len(carries):
            continue
        slots = meta.get("slots") or {}
        options = tuple(
            Option(option_id=opt, source=src, position=slots.get(src))
            for src, opt in sorted(carries.items()))
        won = row.get("winning_option") if row.get("behaviour") == "chose" else None
        if won is None and not include_abstentions:
            continue
        item = row.get("scenario_id") or row.get("trial_id") or "?"
        out.append(Choice(item=str(item), options=options, won=won,
                          tags={"behaviour": row.get("behaviour"),
                                "trial_id": row.get("trial_id"),
                                "run_id": row.get("run_id"),
                                "operator_pinned": tuple(
                                    meta.get("operator_pinned") or ())}))
    return Dataset(out)


def free_from_records(rows: Iterable[Mapping[str, Any]]) -> Dataset:
    """A run's free predictions: conflict trials where several sources demand one option.
    Each source stays its own Option, named `option@source` so a Choice can hold them; the
    option it stands for is in `tags["actions"]`, and what won in `tags["action_won"]`.
    Never fitted: `predict_actions` scores them with a fit made on bijective choices."""
    out = []
    for row in rows:
        meta = row.get("meta") or {}
        carries = meta.get("carries") or {}
        if (meta.get("arm") or "pair") != "pair" or len(set(carries.values())) == len(carries):
            continue
        if row.get("usable") is False:
            continue
        slots = meta.get("slots") or {}
        options = tuple(Option(option_id=f"{opt}@{src}", source=src, position=slots.get(src))
                        for src, opt in sorted(carries.items()))
        won = row.get("winning_option") if row.get("behaviour") == "chose" else None
        out.append(Choice(item=str(row.get("scenario_id") or row.get("trial_id") or "?"),
                          options=options, won=None,
                          tags={"actions": {o.option_id: o.option_id.split("@")[0]
                                            for o in options},
                                "action_won": won, "trial_id": row.get("trial_id"),
                                "groups": meta.get("groups")}))
    return Dataset(out)


def predict_actions(fitted, choice: Choice) -> Optional[dict[Optional[str], float]]:
    """The chance of each option, and of abstaining, for a free prediction: the chance of
    each source, summed over the sources that demand the option. That is the independent-
    draw reading, and the one a pair-only fit commits to with no new parameter."""
    predicted = fitted.predict(choice)
    if predicted is None:
        return None
    out: dict[Optional[str], float] = {}
    for key, p in predicted.items():
        action = choice.tags["actions"].get(key) if key is not None else None
        out[action] = out.get(action, 0.0) + p
    return out


def kinds(dataset: Dataset) -> dict[str, list[tuple[str, ...]]]:
    """Sort the compositions by whether their order can be read.

    FREE means EVERY pair of sources inside it is seen both ways round. At two
    sources that is one test; above two it is the only correct one, and the
    version written for pairs called a triple free when its operator block was
    always first -- so "being an operator" and "being early" stayed one column.
    """
    orders: dict[tuple, dict[tuple, set]] = collections.defaultdict(
        lambda: collections.defaultdict(set))
    pinned: dict[tuple, tuple] = {}
    for c in dataset:
        where = {o.source: o.position for o in c.options}
        if any(p is None for p in where.values()):
            continue
        pinned[c.sources] = tuple(c.tags.get("operator_pinned") or ())
        for a, b in itertools.combinations(sorted(where), 2):
            if where[a] != where[b]:
                orders[c.sources][(a, b)].add(where[a] < where[b])
    out: dict[str, list] = {"within_message": [], "free": [], "pinned": []}
    for comp, pairs in sorted(orders.items()):
        if comp and all(s in pinned.get(comp, ()) for s in comp):
            out["within_message"].append(comp)
        elif pairs and all(len(seen) == 2 for seen in pairs.values()):
            out["free"].append(comp)
        else:
            out["pinned"].append(comp)
    return out


def canonical(dataset: Dataset) -> Dataset:
    """The same draws with the items forgotten: one weighted row per (sources, order, winner).
    Options are named by source and sit at their order index, so every rank is unchanged. A
    speed change for a fit, never for anything that resamples items."""
    buckets: dict[tuple, int] = collections.defaultdict(int)
    for c in dataset:
        order = sorted(c.options, key=lambda o: (o.position is None, o.position, o.option_id))
        known = all(o.position is not None for o in c.options)
        slots = tuple(sorted((o.source, i if known else None) for i, o in enumerate(order)))
        buckets[(slots, c.winning_source())] += c.weight
    return Dataset(
        Choice(item="*", options=tuple(Option(s, s, position=p) for s, p in slots),
               won=won, weight=n)
        for (slots, won), n in sorted(buckets.items(), key=lambda kv: repr(kv[0])))


def collapse(dataset: Dataset) -> Dataset:
    """Identical choices carried as one row with a weight.
    A speed change only; a test pins that collapsed and expanded fit the same."""
    buckets: dict[tuple, int] = collections.defaultdict(int)
    keep: dict[tuple, Choice] = {}
    for c in dataset:
        key = (c.item, c.options, c.won)
        buckets[key] += c.weight
        keep.setdefault(key, c)
    return Dataset(
        Choice(item=k[0], options=k[1], won=k[2], weight=n, tags=keep[k].tags)
        for k, n in buckets.items())
