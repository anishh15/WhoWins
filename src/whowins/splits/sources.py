"""The sources a trial's instructions arrive from, and the sets they form.
A source is a transport role plus the provenance it displays. The five are DERIVED from the
worked trials rather than declared here, so the inventory cannot drift from what the trials
actually demonstrate."""

from __future__ import annotations


import itertools
import os
from dataclasses import dataclass
from typing import Iterator, Sequence

from ..data import ROOT, read_json

COMPOSITION_TRIALS = "data/trials/02-composition.json"

DECLARED_LADDER = (2, 3, 5)
"""Set sizes the composition cell declares, from the dataset plan's cell table:
"which sources compete, and how many (n = 2, 3, 5)". Four-way bijective sets are
enumerable and are recorded separately rather than folded in, because adding them
is a scope decision and not a discovery."""


class SourceInventoryError(RuntimeError):
    """The worked trials do not agree on what a source is."""


@dataclass(frozen=True, order=True)
class Source:
    source_id: str
    transport_role: str
    displayed_provenance: str

    def as_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "transport_role": self.transport_role,
            "displayed_provenance": self.displayed_provenance,
        }


def load_sources() -> list[Source]:
    """The five sources, read off the composition cell's spans.
    Every span carries `source`, `transport_role` and `displayed_provenance`. A source
    appearing with two different identities raises, because the inventory would then be
    ambiguous."""
    path = os.path.join(ROOT, COMPOSITION_TRIALS)
    identities: dict[str, set[tuple[str, str]]] = {}
    for trial in read_json(path):
        for span in trial.get("spans", []) if "trial_id" in trial else []:
            if "source" not in span:
                continue
            identities.setdefault(span["source"], set()).add(
                (span["transport_role"], span["displayed_provenance"])
            )

    disagreeing = {k: sorted(v) for k, v in identities.items() if len(v) != 1}
    if disagreeing:
        raise SourceInventoryError(
            f"sources with more than one identity in {COMPOSITION_TRIALS}: "
            f"{disagreeing}. A source is (transport_role, displayed_provenance); "
            f"fix the trials rather than picking one."
        )
    if not identities:
        raise SourceInventoryError(
            f"no spans carrying `source` in {COMPOSITION_TRIALS}"
        )

    return [
        Source(sid, *next(iter(ident)))
        for sid, ident in sorted(identities.items())
    ]


# ------------------------------------------------------------------ subsets


def subsets(sources: Sequence[Source], size: int) -> list[tuple[str, ...]]:
    """Every combination of that many source ids, in a fixed order."""
    ids = [s.source_id for s in sources]
    return [tuple(c) for c in itertools.combinations(ids, size)]


def covering_slice(sources: Sequence[Source],
                   must_include: Sequence[tuple[str, ...]] = ()) -> list[tuple[str, ...]]:
    """The preselected triples stage two is allowed to fit on.
    Chosen so EVERY pair appears in at least one triple, in the fewest triples that manage it: a
    pair covered by no triple is a correlation stage two cannot estimate, and pairs cannot
    supply it. Ties are broken by a stated rule, never by expected closeness."""
    ids = [s.source_id for s in sources]
    all_pairs = {frozenset(p) for p in itertools.combinations(ids, 2)}
    triples = [tuple(t) for t in itertools.combinations(ids, 3)]
    required = {tuple(sorted(m)) for m in must_include}

    def covered(slice_: Sequence[tuple[str, ...]]) -> set[frozenset]:
        out: set[frozenset] = set()
        for t in slice_:
            out |= {frozenset(p) for p in itertools.combinations(t, 2)}
        return out

    for size in range(1, len(triples) + 1):
        winners = [
            c for c in itertools.combinations(triples, size)
            if covered(c) == all_pairs and required <= {tuple(sorted(t)) for t in c}
        ]
        if winners:
            return [tuple(t) for t in sorted(winners)[0]]

    raise SourceInventoryError(
        f"no slice of triples covers every pair while containing {sorted(required)}"
    )


def two_action_partitions(subset: Sequence[str]) -> Iterator[tuple[tuple[str, ...], ...]]:
    """Every way of splitting a set of sources into exactly two action groups.
    The free-prediction family: where several sources demand the SAME action, an
    independent-draw account and a consensus account predict different things, and a pair-only
    fit commits to one with no new parameters."""
    ids = sorted(subset)
    first, rest = ids[0], ids[1:]
    for size in range(len(rest) + 1):
        for with_first in itertools.combinations(rest, size):
            group_a = tuple(sorted((first, *with_first)))
            group_b = tuple(sorted(set(ids) - set(group_a)))
            if group_b:  # both groups non-empty
                yield (group_a, group_b)
