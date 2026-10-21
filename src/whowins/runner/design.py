"""The trials one run sends, built from the design rather than written by hand.
A trial is a base scenario plus a claim about where each instruction came from.
Nothing is random: the list is a function of the run config, so two people running
the same command send the same thing. `python3 -m whowins.runner.design RUN_ID --balance`."""

from __future__ import annotations

import collections
import dataclasses
import itertools
import math
import os
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Optional, Sequence

from ..data import ROOT, read_json
from ..logs import get_logger
from .rendering import Scenarios
from .spec import Block, Element, Message, Span, Task, TrialSpec, tool_call
from .tools import CONTEXT_TOOL

SOURCE_FILE = os.path.join(ROOT, "data", "splits", "source_pair.json")
SET_FILE = os.path.join(ROOT, "data", "splits", "set.json")

DESIGNS = ("pairwise-rotation", "pairwise-balanced", "composition-ladder",
           "composition-ladder-flat", "free-predictions", "load-cell", "load-bundles",
           "declared-tiers", "declared-tiers-6", "operator-decomposition", "one-message",
           "realism")
"""How a run's trials are built. A run names one, so a change to how trials are
laid out is a new name rather than a silent change to an old run.

    pairwise-rotation   the first run's. One two-source trial per scenario,
                        the sources always in the order S1 < S2 < ... < S5.
    pairwise-balanced   the same conflicts, laid out in a balanced arrangement,
                        and each side also asked on its own.

    composition-ladder  the same again, for sets of any declared size: pairs,
                        triples and the five-way, each source carrying a
                        different option.
    composition-ladder-flat
                        the same trials, with the options dealt so that in every
                        composition every source carries every option equally
                        often, to within one trial.
    free-predictions    the 80 sets in data/splits/set.json where several sources
                        demand the SAME option, dealt the same way. Never fitted:
                        a pair-only fit predicts them.
    load-cell           the ten hand-written load trials, every instruction in one
                        operator message, on each family's own operator channel.
    load-bundles        the same ten, and the ten of every hand-written bundle in
                        data/load/, each a replicate with its own task and fillers.
    declared-tiers      two options of each scenario under declared priority tiers
                        1 to 12, twelve tier pairs a scenario, for capacity.
    declared-tiers-6    the same under tiers 1 to 6, six tier pairs a scenario: half
                        the trials, and 432 items a pair instead of 196.
    operator-decomposition, one-message, realism
                        each moves one thing the ladder holds fixed, every item sent
                        under each layout: see whowins.runner.layouts.

`pairwise-rotation` is kept exactly as it was so that results/initial-qwen3-1.7b
can still be rebuilt from its config. It should not be used again: it fixed the
order of the sources, so which source arrived last was decided by its name.

`pairwise-balanced` is likewise frozen at what it was: it builds sizes 1 and 2
and refuses the rest, so the two runs on disk rebuild byte for byte. **The ladder
is a new name rather than a new behaviour for an old one**, which is this
repository's standing rule -- a design that quietly started building more would
make two runs carrying the same design string mean different things.

`composition-ladder` is frozen too. In a triple it let one source carry an option
8 times where another carried it 24, and options differ in how easily a model
produces them, so a source could look weak for the options it was handed. The
flat ladder is the fix, under a new name, so results/ladder-qwen3-14b still
rebuilds from its config.
"""


class DesignError(ValueError):
    """The design cannot be built as the run asks for it."""


@dataclass(frozen=True)
class Source:
    """One place an instruction can claim to come from."""

    source_id: str
    transport_role: str
    displayed_provenance: str

    def rides_on(self, operator_role: str) -> str:
        """The role this source arrives as, on a family with this operator channel.
        S1 declares system and S2 developer, and they are one level told apart by their
        label -- a role a model never saw in training measures formatting, not authority.
        Everything else rides as declared."""
        return operator_role if self.transport_role in ("system", "developer") \
            else self.transport_role


def load_sources(path: str = SOURCE_FILE) -> dict[str, Source]:
    """The five sources, read from the frozen source-pair split.
    They live there because the split fixes them: a source that gained or lost an
    identity would change which pairs exist, and the folds are built on the pairs."""
    doc = read_json(path)
    out: dict[str, Source] = {}
    for entry in doc["sources"]:
        source = Source(entry["source_id"], entry["transport_role"],
                        entry["displayed_provenance"])
        out[source.source_id] = source
    if len(out) < 2:
        raise DesignError(f"{path}: {len(out)} sources cannot make a pair")
    return out


def source_pairs(sources: Mapping[str, Source]) -> list[tuple[str, str]]:
    """Every unordered pair, in a fixed order."""
    return list(itertools.combinations(sorted(sources), 2))


def option_pairs(scenario: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Every unordered pair of the scenario's options, in a fixed order."""
    return option_sets(scenario, 2)


def option_sets(scenario: Mapping[str, Any], size: int) -> list[tuple[str, ...]]:
    """Every unordered set of `size` options, in a fixed order."""
    ids = [o["id"] for o in scenario["options"]]
    if len(ids) < 2:
        raise DesignError(f"{scenario['scenario_id']}: one option conflicts with nothing")
    if size > len(ids):
        raise DesignError(
            f"{scenario['scenario_id']}: a {size}-source set needs {size} mutually "
            f"exclusive options and the scenario has {len(ids)}. Every scenario in "
            f"this collection carries five, so this is a collection that has "
            f"changed rather than a run that asked for too much")
    return list(itertools.combinations(ids, size))


def trial_id(scenario_id: str, pair: Sequence[str]) -> str:
    return f"{scenario_id}@{pair[0]}-{pair[1]}"


def build_trial(scenario: Mapping[str, Any], sources: Mapping[str, Source],
                pair: Sequence[str], options: Sequence[str], *, flipped: bool,
                operator_role: str, renderer: str = "plain_chat") -> TrialSpec:
    """One trial: two instructions from one scenario, arriving from two sources.

    `flipped` swaps which source carries which option, so that over the run each
    source is seen with both halves of a conflict rather than always the first."""
    if len(pair) != 2 or len(options) != 2:
        raise DesignError(f"{scenario['scenario_id']}: a pairwise trial takes two "
                          f"sources and two options, got {list(pair)} and {list(options)}")
    first, second = (options[1], options[0]) if flipped else (options[0], options[1])
    carried = {pair[0]: first, pair[1]: second}

    operators = [s for s in pair if sources[s].rides_on(operator_role) == operator_role]
    others = [s for s in pair if s not in operators]

    elements: list[Element] = []
    slot = 0

    def span_for(source_id: str, call_id: Optional[str] = None) -> Span:
        nonlocal slot
        source = sources[source_id]
        span = Span(
            option_id=carried[source_id],
            transport_role=source.rides_on(operator_role),
            displayed_provenance=source.displayed_provenance,
            position_slot=slot,
            tool_call_id=call_id,
        )
        slot += 1
        return span

    # The operator channel first and only once: the Qwen 3.5 template refuses a later system message, and both ladders keep one shape.
    if len(operators) == 2:
        elements.append(Block(operator_role, [span_for(operators[0]),
                                              span_for(operators[1])]))
    elif operators:
        elements.append(span_for(operators[0]))

    for source_id in others:
        if sources[source_id].rides_on(operator_role) == "tool":
            call_id = f"call_{source_id.lower()}"
            elements.append(Message("assistant", "",
                                    tool_calls=[tool_call(call_id, CONTEXT_TOOL)]))
            elements.append(span_for(source_id, call_id))
        else:
            elements.append(span_for(source_id))

    return TrialSpec(
        trial_id=trial_id(scenario["scenario_id"], pair),
        scenario_id=scenario["scenario_id"],
        renderer=renderer,
        elements=elements,
        options_in_play=tuple(options),
        meta={
            "design": "pairwise-rotation",
            "n_competing": 2,
            "source_pair": list(pair),
            "carries": {s: carried[s] for s in pair},
            "flipped": flipped,
        },
    )


def assignments(scenarios: Sequence[Mapping[str, Any]], pairs: Sequence[tuple[str, str]]
                ) -> Iterator[tuple[Mapping[str, Any], tuple[str, str], tuple[str, str], bool]]:
    """Which source pair and option pair each scenario takes, family by family.
    A Latin square: scenario j takes source pair `j mod n` and option pair
    `(j + j div n) mod m`, so every pair meets every option pair once. `flipped` turns
    over every n scenarios, leaving it balanced across both."""
    by_family: dict[str, list[Mapping[str, Any]]] = {}
    for scenario in sorted(scenarios, key=lambda s: s["scenario_id"]):
        by_family.setdefault(scenario["family"], []).append(scenario)
    n = len(pairs)
    for family in sorted(by_family):
        for j, scenario in enumerate(by_family[family]):
            options = option_pairs(scenario)
            block, within = divmod(j, n)
            yield (scenario, pairs[within], options[(j + block) % len(options)],
                   bool(block % 2))


# --- pairwise-balanced: the same conflicts, position balanced, each side also asked alone ---

BALANCED = "pairwise-balanced"


def solo_trial_id(scenario_id: str, source_id: str) -> str:
    return f"{scenario_id}@{source_id}"


def arrangement_count(n_operators: int, n_others: int) -> int:
    """How many distinct arrangements a trial of this shape has.
    The operator block can be written either way round when it holds two lines, and the
    task and each non-operator source can come in any order. Nothing else moves: a
    system message must be first and alone."""
    return (2 if n_operators == 2 else 1) * math.factorial(n_others + 1)


def arrangement_for(index: int, n_operators: int, n_others: int
                    ) -> tuple[bool, tuple[int, ...]]:
    """(are the operator's two lines reversed, the order of the free region).
    The free region is `0 .. n_others-1` for the non-operator sources in pair order and
    `n_others` for the task. Enumerated in `itertools.permutations` order, which is
    fixed, so an index rebuilds the same arrangement forever."""
    perms = list(itertools.permutations(range(n_others + 1)))
    total = arrangement_count(n_operators, n_others)
    i = index % total
    return bool(i // len(perms)), perms[i % len(perms)]


def _units(scenario: Mapping[str, Any], sources: Mapping[str, Source],
           order: Sequence[str], carried: Mapping[str, str], operator_role: str,
           reversed_operators: bool, free_order: Sequence[int]
           ) -> tuple[list[Element], list[str]]:
    """The elements of one trial, in send order, and that order's names.
    Slots are handed out after the arrangement is settled: `TrialSpec` refuses spans
    whose recorded slots disagree with the element order."""
    operators = [s for s in order if sources[s].rides_on(operator_role) == operator_role]
    others = [s for s in order if s not in operators]
    if reversed_operators:
        operators = list(reversed(operators))

    elements: list[Element] = []
    names: list[str] = []
    slot = 0

    def span_for(source_id: str, call_id: Optional[str] = None) -> Span:
        nonlocal slot
        source = sources[source_id]
        span = Span(
            option_id=carried[source_id],
            transport_role=source.rides_on(operator_role),
            displayed_provenance=source.displayed_provenance,
            position_slot=slot,
            tool_call_id=call_id,
        )
        slot += 1
        return span

    if len(operators) == 2:
        elements.append(Block(operator_role, [span_for(operators[0]),
                                              span_for(operators[1])]))
        names.extend(operators)
    elif operators:
        elements.append(span_for(operators[0]))
        names.append(operators[0])

    for item in free_order:
        if item == len(others):
            elements.append(Task())
            names.append("task")
            continue
        source_id = others[item]
        if sources[source_id].rides_on(operator_role) == "tool":
            call_id = f"call_{source_id.lower()}"
            elements.append(Message("assistant", "",
                                    tool_calls=[tool_call(call_id, CONTEXT_TOOL)]))
            elements.append(span_for(source_id, call_id))
        else:
            elements.append(span_for(source_id))
        names.append(source_id)
    return elements, names


def build_balanced_trial(scenario: Mapping[str, Any], sources: Mapping[str, Source],
                         pair: Sequence[str], options: Sequence[str], *,
                         flipped: bool, operator_role: str, arrangement: int,
                         solo: Optional[str] = None,
                         renderer: str = "plain_chat") -> TrialSpec:
    """One trial of the balanced design: a conflict, or one side of it alone.
    `solo` keeps one source and deletes the other's turn, touching nothing else -- same
    scenario, option, arrangement and place. That is what makes it a control rather
    than a second experiment."""
    if len(pair) != 2 or len(options) != 2:
        raise DesignError(f"{scenario['scenario_id']}: a pairwise trial takes two "
                          f"sources and two options, got {list(pair)} and {list(options)}")
    if solo is not None and solo not in pair:
        raise DesignError(f"{scenario['scenario_id']}: {solo!r} is not one of "
                          f"{list(pair)}, so it cannot be the side kept")
    first, second = (options[1], options[0]) if flipped else (options[0], options[1])
    carried = {pair[0]: first, pair[1]: second}

    operators = [s for s in pair if sources[s].rides_on(operator_role) == operator_role]
    reversed_operators, free_order = arrangement_for(
        arrangement, len(operators), len(pair) - len(operators))

    kept = [s for s in pair if solo is None or s == solo]
    if solo is not None:
        # Drop the other source without disturbing what is left: the free region keeps its order and the task keeps its place.
        others = [s for s in pair if s not in operators]
        dropped = [i for i, s in enumerate(others) if s not in kept]
        free_order = tuple(i - sum(1 for d in dropped if d < i)
                           for i in free_order if i not in dropped)

    elements, names = _units(scenario, sources, kept, carried, operator_role,
                             reversed_operators, free_order)
    slots = {name: i for i, name in enumerate(names)}
    return TrialSpec(
        trial_id=(solo_trial_id(scenario["scenario_id"], solo) if solo
                  else trial_id(scenario["scenario_id"], pair)),
        scenario_id=scenario["scenario_id"],
        renderer=renderer,
        elements=elements,
        options_in_play=tuple(carried[s] for s in kept),
        meta={
            "design": BALANCED,
            "arm": "solo" if solo else "pair",
            "n_competing": len(kept),
            "source_pair": list(pair),
            "sources_in_play": kept,
            "carries": {s: carried[s] for s in kept},
            "flipped": flipped,
            "arrangement": arrangement,
            "order": names,
            "slots": slots,
            "operator_pinned": sorted(s for s in kept if s in operators),
        },
    )


def balanced_assignments(scenarios: Sequence[Mapping[str, Any]],
                         pairs: Sequence[tuple[str, str]],
                         sources: Mapping[str, Source], operator_role: str
                         ) -> Iterator[tuple[Mapping[str, Any], tuple[str, str],
                                             tuple[str, str], bool, int]]:
    """`assignments`, plus which arrangement each trial takes.
    The pair, option pair and flip are decided exactly as `pairwise-rotation` decides
    them. The arrangement counts within each (source pair, flipped) cell: counting
    within the pair alone would tie the arrangement to the flip."""
    counters: dict[tuple[tuple[str, str], bool], int] = {}
    for scenario, pair, options, flipped in assignments(scenarios, pairs):
        key = (pair, flipped)
        index = counters.get(key, 0)
        counters[key] = index + 1
        operators = sum(1 for s in pair
                        if sources[s].rides_on(operator_role) == operator_role)
        total = arrangement_count(operators, len(pair) - operators)
        yield scenario, pair, options, flipped, index % total


# --- composition-ladder: the same conflicts at every declared size ---

LADDER = "composition-ladder"
FLAT_LADDER = "composition-ladder-flat"
LADDERS = (LADDER, FLAT_LADDER)

# The sizes a ladder run may ask for. FOUR IS DELIBERATELY ABSENT -- four-way sets are enumerated under `not_in_declared_ladder` and adding one is a scope decision.
LADDER_SIZES = (1, 2, 3, 5)


def compositions_of(sources: Mapping[str, Source], size: int) -> list[tuple[str, ...]]:
    """Every unordered set of `size` sources, in a fixed order."""
    if size < 2:
        raise DesignError(f"a composition of {size} sources is not a conflict")
    if size > len(sources):
        raise DesignError(
            f"a {size}-source set needs {size} sources and there are {len(sources)}")
    return list(itertools.combinations(sorted(sources), size))


def composition_trial_id(scenario_id: str, composition: Sequence[str]) -> str:
    return f"{scenario_id}@{'-'.join(composition)}"


def composition_solo_trial_id(scenario_id: str, composition: Sequence[str],
                              source_id: str) -> str:
    """The id of one side of a composition, asked alone.
    It names the composition it was cut from. It has to: a scenario appears in a pair, a
    triple and the five-way, so `scenario@S1` would be three different trials wearing
    one id, and a run resumes by id."""
    return f"{scenario_id}@{'-'.join(composition)}~{source_id}"


def free_trial_id(scenario_id: str, groups: Sequence[Sequence[str]]) -> str:
    """`fmt-0001@S1|S2+S3`: the sources that share an option are joined by `+`, so a free
    prediction never takes the id of the ladder trial over the same sources."""
    return f"{scenario_id}@{'|'.join(sorted('+'.join(sorted(g)) for g in groups))}"


def _check_groups(scenario_id: str, composition: Sequence[str], carried: Mapping[str, str],
                  groups: Sequence[Sequence[str]]) -> None:
    """Every source in exactly one group, one option per group, a different one per group."""
    members = [s for g in groups for s in g]
    if sorted(members) != sorted(composition) or len(groups) < 2:
        raise DesignError(f"{scenario_id}: groups {list(groups)} do not partition "
                          f"{list(composition)} into two or more")
    if any(len({carried.get(s) for s in g}) != 1 for g in groups):
        raise DesignError(f"{scenario_id}: the sources of one group must demand one "
                          f"option, got {dict(carried)}")


def permutation_for(index: int, size: int) -> tuple[int, ...]:
    """Which option each source of a composition carries: a cyclic Latin square.
    Source i takes option `(i + index) mod size`, so over `size` values every source
    carries every option once. Not all n! permutations: that left eight scenarios per
    cell and the arrangement counter reached 8 of 48. At n = 2 this IS `flipped`."""
    if size < 1:
        raise DesignError(f"a composition of {size} has no permutation")
    return tuple((i + index) % size for i in range(size))


def build_composition_trial(scenario: Mapping[str, Any],
                            sources: Mapping[str, Source],
                            composition: Sequence[str], carried: Mapping[str, str], *,
                            deal: Mapping[str, Any], operator_role: str, arrangement: int,
                            solo: Optional[str] = None, design: str = LADDER,
                            groups: Sequence[Sequence[str]] = (),
                            renderer: str = "plain_chat") -> TrialSpec:
    """One trial of a ladder: a conflict between `composition`, or one side alone.
    `carried` says which option each source demands and `deal` how that was chosen. Every
    source carries a DIFFERENT option, unless `groups` names the sources that share one: a
    free prediction from data/splits/set.json."""
    size = len(composition)
    options = [carried.get(s) for s in composition]
    if groups:
        _check_groups(scenario["scenario_id"], composition, carried, groups)
        options = [carried[g[0]] for g in groups]
        size = len(groups)
    if size < 2:
        raise DesignError(f"{scenario['scenario_id']}: a conflict needs two sources, "
                          f"got {list(composition)}")
    if len(carried) != len(composition) or None in options:
        raise DesignError(
            f"{scenario['scenario_id']}: {size} sources and {len(carried)} options. "
            f"The ladder is bijective -- one option each -- and a set where two "
            f"sources ask for the same action is a free prediction, which "
            f"data/splits/set.json enumerates separately")
    if len(set(composition)) != len(composition) or len(set(options)) != size:
        raise DesignError(f"{scenario['scenario_id']}: a repeated source or option "
                          f"in {list(composition)} / {list(options)}")
    size = len(composition)
    if solo is not None and solo not in composition:
        raise DesignError(f"{scenario['scenario_id']}: {solo!r} is not one of "
                          f"{list(composition)}, so it cannot be the side kept")

    operators = [s for s in composition
                 if sources[s].rides_on(operator_role) == operator_role]
    reversed_operators, free_order = arrangement_for(
        arrangement, len(operators), size - len(operators))

    kept = [s for s in composition if solo is None or s == solo]
    if solo is not None:
        others = [s for s in composition if s not in operators]
        dropped = [i for i, s in enumerate(others) if s not in kept]
        free_order = tuple(i - sum(1 for d in dropped if d < i)
                           for i in free_order if i not in dropped)

    elements, names = _units(scenario, sources, kept, carried, operator_role,
                             reversed_operators, free_order)
    slots = {name: i for i, name in enumerate(names)}
    trial_id = (composition_solo_trial_id(scenario["scenario_id"], composition, solo)
                if solo else composition_trial_id(scenario["scenario_id"], composition))
    if groups:
        trial_id = free_trial_id(scenario["scenario_id"], groups)
    meta = {
        "design": design,
        "arm": "solo" if solo else "pair",
        "n_competing": len(kept),
        "composition": list(composition),
        "composition_size": size,
        # `source_pair` is what every reader already looks for and carries the whole composition; `analyse` guards on its length.
        "source_pair": list(composition),
        "sources_in_play": kept,
        "carries": {s: carried[s] for s in kept},
        **deal,
        "arrangement": arrangement,
        "order": names,
        "slots": slots,
        "operator_pinned": sorted(s for s in kept if s in operators),
    }
    if groups:
        meta["groups"] = [sorted(g) for g in groups]
    if size == 2:
        # The one thing a pair has that a larger set does not, so a ladder run's pairs read like a pairwise-balanced run's: the first source carries the later option.
        ids = [o["id"] for o in scenario["options"]]
        meta["flipped"] = ids.index(options[0]) > ids.index(options[1])
    return TrialSpec(
        trial_id=trial_id,
        scenario_id=scenario["scenario_id"],
        renderer=renderer,
        elements=elements,
        options_in_play=tuple(carried[s] for s in kept),
        meta=meta,
    )


def eligible_for(scenarios: Sequence[Mapping[str, Any]], size: int
                 ) -> tuple[list[Mapping[str, Any]], dict[str, int]]:
    """The scenarios that can carry a set of `size` sources, and what was left out.
    Read off the scenario's own option count, never off the family name, so a family that
    gained an option would join with no edit here. Refusal has two options and is
    pairwise-only by the dataset plan, so it is out above a pair."""
    keep, dropped = [], {}
    for scenario in scenarios:
        if len(scenario.get("options", ())) >= size:
            keep.append(scenario)
        else:
            dropped[scenario["family"]] = dropped.get(scenario["family"], 0) + 1
    return keep, dropped


Cell = tuple[Mapping[str, Any], tuple[str, ...], dict[str, str], dict[str, Any], int]
"""(scenario, composition, which option each source carries, how it was dealt, arrangement)."""


def ladder_assignments(scenarios: Sequence[Mapping[str, Any]],
                       compositions: Sequence[tuple[str, ...]],
                       sources: Mapping[str, Source], operator_role: str, size: int
                       ) -> Iterator[Cell]:
    """Which composition, option set, permutation and arrangement each scenario takes.
    The same Latin square as `assignments`, at any size. The ARRANGEMENT is not nested
    under the permutation: nesting it left the free triple reaching 8 of 24, putting one
    source first twice as often as another."""
    for scenario, composition, _, j, block, arrangement, _ in _cells(
            scenarios, compositions, sources, operator_role, size):
        sets = option_sets(scenario, size)
        options = sets[(j + block) % len(sets)]
        permutation = block % size
        order = permutation_for(permutation, size)
        carried = {composition[i]: options[order[i]] for i in range(size)}
        yield scenario, composition, carried, {"permutation": permutation}, arrangement


def flat_assignments(scenarios: Sequence[Mapping[str, Any]],
                     compositions: Sequence[tuple[str, ...]],
                     sources: Mapping[str, Source], operator_role: str, size: int
                     ) -> Iterator[Cell]:
    """The ladder's scenarios, compositions and arrangements, with the options dealt flat.
    Source i carries option (offset_i + rotation) mod n, counted per composition and option
    count. The rotation steps every trial, and once more every lcm(n, arrangements), so each
    arrangement meets each rotation; the offsets change after that cycle, or every n trials
    where two cycles do not fit, so every option set is still used."""
    for scenario, index, arrangement, offsets, rotation in _flat_cells(
            scenarios, compositions, sources, operator_role, size, size):
        composition = compositions[index]
        ids = [o["id"] for o in scenario["options"]]
        carried = {s: ids[(offsets[i] + rotation) % len(ids)]
                   for i, s in enumerate(composition)}
        yield (scenario, composition, carried,
               {"rotation": rotation, "offsets": list(offsets)}, arrangement)


def _flat_cells(scenarios: Sequence[Mapping[str, Any]], compositions: Sequence[tuple[str, ...]],
                sources: Mapping[str, Source], operator_role: str, size: int, units: int,
                needed: Optional[int] = None
                ) -> Iterator[tuple[Mapping[str, Any], int, int, tuple[int, ...], int]]:
    """(scenario, which composition, arrangement, offsets, rotation) under the flat deal, for
    `units` things that each carry a different option: sources, or groups of them."""
    cells = list(_cells(scenarios, compositions, sources, operator_role, size, needed))
    totals = collections.Counter((c[2], len(c[0]["options"])) for c in cells)
    turns: collections.Counter = collections.Counter()
    for scenario, composition, index, _, _, arrangement, arrangements in cells:
        n = len(scenario["options"])
        turn = turns[(index, n)]
        turns[(index, n)] += 1
        deals = [(0, *rest) for rest in itertools.permutations(range(1, n), units - 1)]
        cycle = n * arrangements
        offsets = deals[(turn // (cycle if 2 * cycle <= totals[(index, n)] else n))
                        % len(deals)]
        rotation = (turn + turn // math.lcm(n, arrangements)) % n
        yield scenario, index, arrangement, offsets, rotation


def _cells(scenarios: Sequence[Mapping[str, Any]], compositions: Sequence[tuple[str, ...]],
           sources: Mapping[str, Source], operator_role: str, size: int,
           needed: Optional[int] = None
           ) -> Iterator[tuple[Mapping[str, Any], tuple[str, ...], int, int, int, int, int]]:
    """(scenario, composition, which composition, index in family, block, arrangement,
    arrangements). The arrangement counter runs per composition, by its place in the list,
    across the families. A scenario needs `needed` options: `size`, unless sources share one."""
    usable, _ = eligible_for(sorted(scenarios, key=lambda s: s["scenario_id"]),
                             needed or size)
    by_family: dict[str, list[Mapping[str, Any]]] = {}
    for scenario in usable:
        by_family.setdefault(scenario["family"], []).append(scenario)
    # ONE COUNTER PER COMPOSITION, ACROSS THE FAMILIES: a family holds only 24 scenarios per composition, which is not enough to reach every arrangement.
    seen: collections.Counter = collections.Counter()
    for family in sorted(by_family):
        for j, scenario in enumerate(by_family[family]):
            block, within = divmod(j, len(compositions))
            composition = compositions[within]
            count = seen[within]
            seen[within] += 1
            operators = sum(1 for s in composition
                            if sources[s].rides_on(operator_role) == operator_role)
            arrangements = arrangement_count(operators, size - operators)
            # THE ARRANGEMENT IS NOT NESTED UNDER THE PERMUTATION, and that one change is the whole of the position fix -- nesting it left S3 leading 36 of 96 trials against S5's 18. The permutation stays on the per-family block with the option set, which is the content Latin square the study's method asks for. Measured four ways.
            yield (scenario, composition, within, j, block, count % arrangements,
                   arrangements)


def ladder_trials(scenarios: Sequence[Mapping[str, Any]],
                  sources: Mapping[str, Source], operator_role: str,
                  sizes: Sequence[int], design: str = LADDER) -> list[TrialSpec]:
    """Every trial a ladder sends, smallest composition first.
    A composition's solo arm comes before its conflict, so a run cut short holds the
    control for the conflicts it reached rather than conflicts with no control."""
    log = get_logger(__name__)
    assign = flat_assignments if design == FLAT_LADDER else ladder_assignments
    out: list[TrialSpec] = []
    for size in sorted(n for n in sizes if n >= 2):
        compositions = compositions_of(sources, size)
        _, dropped = eligible_for(list(scenarios), size)
        if dropped:
            log.info("size %d: %s left out, having fewer than %d options",
                     size, ", ".join(f"{k} ({v})" for k, v in sorted(dropped.items())),
                     size)
        for scenario, composition, carried, deal, arrangement in assign(
                list(scenarios), compositions, sources, operator_role, size):
            if 1 in sizes:
                for source_id in composition:
                    out.append(build_composition_trial(
                        scenario, sources, composition, carried, deal=deal,
                        operator_role=operator_role, arrangement=arrangement,
                        solo=source_id, design=design))
            out.append(build_composition_trial(
                scenario, sources, composition, carried, deal=deal,
                operator_role=operator_role, arrangement=arrangement, design=design))
    return out


# --- free-predictions: several sources demanding the same option ---

FREE = "free-predictions"
FREE_SIZES = (3, 4, 5)


def free_groupings(path: str = SET_FILE) -> list[tuple[tuple[str, ...], ...]]:
    """The free predictions the frozen set split enumerates, as groups of sources."""
    entries = read_json(path)["free_predictions"]["compositions"]
    return [tuple(tuple(g) for g in e["groups"]) for e in entries]


def free_trials(scenarios: Sequence[Mapping[str, Any]], sources: Mapping[str, Source],
                operator_role: str, sizes: Sequence[int]) -> list[TrialSpec]:
    """Every free-prediction trial: each scenario once per size, a grouping in turn.
    The groups are dealt options as the flat ladder deals sources, so every group carries
    every option equally often. No solo arm: the ladder run of the same model has it."""
    out: list[TrialSpec] = []
    for size in sorted(sizes):
        groupings = [g for g in free_groupings() if sum(len(x) for x in g) == size]
        compositions = [tuple(sorted(s for g in grouping for s in g)) for grouping in groupings]
        needed = max(len(g) for g in groupings)
        for scenario, index, arrangement, offsets, rotation in _flat_cells(
                list(scenarios), compositions, sources, operator_role, size, needed, needed):
            composition, grouping = compositions[index], groupings[index]
            ids = [o["id"] for o in scenario["options"]]
            carried = {s: ids[(offsets[g] + rotation) % len(ids)]
                       for g, group in enumerate(grouping) for s in group}
            out.append(build_composition_trial(
                scenario, sources, composition, carried, operator_role=operator_role,
                arrangement=arrangement, design=FREE, groups=grouping,
                deal={"rotation": rotation, "offsets": list(offsets)}))
    return out


# --- load-cell: the load-versus-conflict trials ---

LOAD = "load-cell"
LOAD_CELL = "load_vs_conflict"


def load_cell_trials(scenarios: Scenarios, operator_role: str) -> list[TrialSpec]:
    """The worked load trials, sent as written but on the family's operator channel.
    Every instruction sits in one operator message there by design, and that message is a
    system message on Qwen and a developer message on gpt-oss."""
    from .trials import load_cell_headers, load_trials, reconstruct

    header = load_cell_headers().get(LOAD_CELL)
    out = []
    for trial in load_trials():
        if trial.get("cell") != LOAD_CELL:
            continue
        spec = reconstruct(trial, scenarios, header).spec
        if spec is None:
            raise DesignError(f"{trial['trial_id']}: the worked trial no longer rebuilds")
        elements = tuple(_on_channel(e, operator_role) for e in spec.elements)
        out.append(dataclasses.replace(spec, elements=elements,
                                       meta={**spec.meta, "design": LOAD, "arm": "load"}))
    return out


# --- declared-tiers: two options under declared priority tiers, for capacity ---

TIERS = "declared-tiers"
TIERS_6 = "declared-tiers-6"
TIER_LEVELS = tuple(range(1, 13))
TIER_PAIRS_PER_SCENARIO = 12
TIER_DESIGNS = {TIERS: (TIER_LEVELS, TIER_PAIRS_PER_SCENARIO), TIERS_6: (tuple(range(1, 7)), 6)}
"""design -> (the tiers it uses, how many tier pairs each scenario takes). Tiers 1 to 6 give 15
pairs of 432 items, at half the trials, so capacity can certify 0.95 where 196 items could not."""
TIER_SETUP = {"scheme": "ordinal_1_12", "rule_direction": "lower_wins", "notation": "bracket",
              "displayed_provenance": "repo_config", "transport_role": "user"}
"""The one setup capacity is measured in, as tier-01 to tier-06 write it: the operator states that
lower numbers win, and both options arrive as repository configuration with a bracketed rank.
Rule direction and notation are held fixed; tier-09 and tier-10 vary them, and a run that crossed
them would be measuring a different setup."""


def tier_pairs(levels: Sequence[int] = TIER_LEVELS) -> list[tuple[int, int]]:
    return list(itertools.combinations(levels, 2))


def tier_trial_id(scenario_id: str, pair: Sequence[int]) -> str:
    return f"{scenario_id}@T{pair[0]:02d}-{pair[1]:02d}"


def tier_trials(scenarios: Sequence[Mapping[str, Any]], operator_role: str,
                design: str = TIERS) -> list[TrialSpec]:
    """Every scenario under k of the design's tier pairs: twelve of 66, or six of 15 for tiers 1
    to 6. Scenario i takes the pairs ki to ki + k - 1, counted round the list of pairs. Within a
    pair, whether the earlier- or later-listed option carries the winning tier, and whether it
    comes first, cycle through all four."""
    levels, per_scenario = TIER_DESIGNS[design]
    pairs = tier_pairs(levels)
    seen: collections.Counter = collections.Counter()
    dealt: collections.Counter = collections.Counter()
    out = []
    for i, scenario in enumerate(scenarios):
        ids = [o["id"] for o in scenario["options"]]
        m = len(ids)
        for t in range(per_scenario):
            index = (i * per_scenario + t) % len(pairs)
            k = seen[index]
            seen[index] += 1
            if design == TIERS:
                a = (i + t) % m
                b = (a + 1 + (i // m + t) % (m - 1)) % m
            else:
                # At six pairs a scenario the formula above leaves some tier pairs meeting 4 of 10 option pairs, so each tier pair takes them in turn.
                options = list(itertools.combinations(range(m), 2))
                a, b = options[(dealt[(index, m)] // 4) % len(options)]
                dealt[(index, m)] += 1
            earlier, later = ids[min(a, b)], ids[max(a, b)]
            winner, loser = (earlier, later) if k % 2 == 0 else (later, earlier)
            out.append(build_tier_trial(scenario, pairs[index], winner, loser,
                                        winner_first=(k // 2) % 2 == 0,
                                        operator_role=operator_role, occurrence=k,
                                        design=design))
    return out


def build_tier_trial(scenario: Mapping[str, Any], pair: Sequence[int], winner: str,
                     loser: str, *, winner_first: bool, operator_role: str,
                     occurrence: int = 0, design: str = TIERS) -> TrialSpec:
    """One conflict between two options of a scenario under declared tiers. `winner` carries the
    lower tier, which the stated policy makes the correct choice."""
    lo, hi = sorted(pair)
    if lo == hi or winner == loser:
        raise DesignError(f"{scenario['scenario_id']}: a tier conflict needs two tiers and "
                          f"two options, got {list(pair)} and {winner}/{loser}")
    ranks = {winner: lo, loser: hi}
    order = [winner, loser] if winner_first else [loser, winner]
    elements: list[Element] = []
    for slot, option in enumerate(order):
        elements.append(Span(option_id=option, transport_role=TIER_SETUP["transport_role"],
                             displayed_provenance=TIER_SETUP["displayed_provenance"],
                             position_slot=slot, declared_rank=ranks[option],
                             rank_notation=TIER_SETUP["notation"]))
    return TrialSpec(
        trial_id=tier_trial_id(scenario["scenario_id"], (lo, hi)),
        scenario_id=scenario["scenario_id"],
        renderer="plain_chat",
        elements=elements,
        policy_scheme=TIER_SETUP["scheme"],
        policy_direction=TIER_SETUP["rule_direction"],
        policy_role=operator_role,
        options_in_play=tuple(order),
        meta={"design": design, "arm": "tier", "rank_pair": [lo, hi], "gap": hi - lo,
              "ranks": ranks, "policy_winner": winner, "order": order,
              "winner_first": winner_first, "occurrence": occurrence,
              **{k: TIER_SETUP[k] for k in ("scheme", "rule_direction", "notation")}},
    )


LOAD_BUNDLES = "load-bundles"


def load_bundle_trials(scenarios: Scenarios, operator_role: str) -> list[TrialSpec]:
    """The worked load trials and every bundle's, a bundle refused whole if it is not fit to
    send. Tokens are the validator's job, since the tokenizers need not be on this machine."""
    from ..validation.check_load import check_bundle
    from . import bundles
    from .trials import reconstruct

    out = [dataclasses.replace(s, meta={**s.meta, "design": LOAD_BUNDLES})
           for s in load_cell_trials(scenarios, operator_role)]
    docs = bundles.load_bundles()
    for i, doc in enumerate(docs):
        fails, _ = check_bundle(doc, scenarios, others=docs[:i] + docs[i + 1:])
        if fails:
            raise DesignError(f"load bundle {doc.get('bundle_id')} is not fit to send: "
                              + "; ".join(fails[:3]))
        head = bundles.header(doc)
        for trial in bundles.as_trials(doc):
            spec = reconstruct(trial, scenarios, head).spec
            elements = tuple(_on_channel(e, operator_role) for e in spec.elements)
            out.append(dataclasses.replace(spec, elements=elements,
                                           meta={**spec.meta, "design": LOAD_BUNDLES,
                                                 "arm": "load"}))
    return out


def _on_channel(element: Element, operator_role: str) -> Element:
    if not isinstance(element, Block) or element.role != "system":
        return element
    items = [dataclasses.replace(i, transport_role=operator_role) if isinstance(i, Span) else i
             for i in element.items]
    return dataclasses.replace(element, role=operator_role, items=items)


def trials_for_run(run: Any, scenarios: Scenarios,
                   sources: Optional[Mapping[str, Source]] = None) -> list[TrialSpec]:
    """Every trial this run sends, in scenario order.
    `run` is an `whowins.runner.serving.Run`: which model, so which family's channels the
    sources ride on; how many sources a trial may use; and which design built the list."""
    design = run.design
    if design not in DESIGNS:
        raise DesignError(f"{run.run_id}: unknown design {design!r}; "
                          f"the ones built are {list(DESIGNS)}")
    if run.composition_max_sources < 2:
        raise DesignError(f"{run.run_id}: composition_max_sources is "
                          f"{run.composition_max_sources}; a conflict needs two sources")
    sizes = tuple(run.composition_sizes)
    if max(sizes) > run.composition_max_sources:
        raise DesignError(
            f"{run.run_id}: composition_sizes {list(sizes)} asks for more sources "
            f"than composition_max_sources ({run.composition_max_sources}) leaves "
            f"open on this model"
        )
    from . import layouts

    built = {FREE: FREE_SIZES, LOAD: (2,), LOAD_BUNDLES: (2,), TIERS: (2,), TIERS_6: (2,),
             **{d: (2,) for d in layouts.LAYOUT_DESIGNS}}.get(
        design, LADDER_SIZES if design in LADDERS else (1, 2))
    if any(n not in built for n in sizes):
        missing = sorted(n for n in sizes if n not in built)
        if design in (FREE, LOAD, LOAD_BUNDLES, *TIER_DESIGNS, *layouts.LAYOUT_DESIGNS):
            raise DesignError(
                f"{run.run_id}: {design} builds composition_sizes {list(built)}, not "
                f"{missing}. The free predictions are the three-, four- and five-source sets "
                f"of data/splits/set.json; the load cell's conflict groups and a tier "
                f"conflict are pairs")
        if design in LADDERS:
            raise DesignError(
                f"{run.run_id}: composition_sizes {list(sizes)} asks for arms of "
                f"{missing} sources. The ladder builds {list(LADDER_SIZES)}, which "
                f"is what dataset-plan.md declares -- n = 2, 3, 5 -- plus 1 for the "
                f"solo control. Four-way sets are enumerated in "
                f"data/splits/set.json under `not_in_declared_ladder` on purpose: "
                f"adding them is a scope decision somebody makes, not a size that "
                f"works because nothing stopped it"
            )
        raise DesignError(
            f"{run.run_id}: composition_sizes {list(sizes)} asks for arms of "
            f"{missing} sources, and {design} does not build one. The sizes it "
            f"builds are {list(built)}: 1 the solo control, 2 the conflict. "
            f"Triples and five-way sets are the composition ladder: name "
            f"{FLAT_LADDER!r} as the design, which builds {list(LADDER_SIZES)}"
        )
    if design in LADDERS and not any(n >= 2 for n in sizes):
        raise DesignError(
            f"{run.run_id}: composition_sizes {list(sizes)} is the solo control "
            f"and nothing for it to control. A solo trial is a composition with "
            f"the other sources deleted, so there has to be a composition"
        )
    if design == "pairwise-rotation" and sizes != (2,):
        raise DesignError(
            f"{run.run_id}: pairwise-rotation builds one two-source trial per "
            f"scenario and nothing else; composition_sizes {list(sizes)} needs "
            f"{BALANCED}"
        )
    sources = sources if sources is not None else load_sources()
    pairs = source_pairs(sources)
    operator_role = run.model.family.operator_role

    if run.scenario_count != len(scenarios):
        raise DesignError(
            f"{run.run_id}: the config says {run.scenario_count} scenarios and "
            f"{len(scenarios)} were supplied. A run that sent a different number "
            f"than it recorded could not be reproduced"
        )

    if design in LADDERS:
        out = ladder_trials(list(scenarios.values()), sources, operator_role, sizes,
                            design)
    elif design == FREE:
        out = free_trials(list(scenarios.values()), sources, operator_role, sizes)
    elif design == LOAD:
        out = load_cell_trials(scenarios, operator_role)
    elif design == LOAD_BUNDLES:
        out = load_bundle_trials(scenarios, operator_role)
    elif design in TIER_DESIGNS:
        out = tier_trials(list(scenarios.values()), operator_role, design)
    elif design in layouts.LAYOUT_DESIGNS:
        out = layouts.trials_for(design, scenarios, sources, run.model.family)
    elif design == "pairwise-rotation":
        out = [build_trial(scenario, sources, pair, options, flipped=flipped,
                           operator_role=operator_role)
               for scenario, pair, options, flipped
               in assignments(list(scenarios.values()), pairs)]
    else:
        out = []
        for scenario, pair, options, flipped, arrangement in balanced_assignments(
                list(scenarios.values()), pairs, sources, operator_role):
            # Solo first, so a run cut short holds the control for the conflicts it reached.
            if 1 in sizes:
                for source_id in pair:
                    out.append(build_balanced_trial(
                        scenario, sources, pair, options, flipped=flipped,
                        operator_role=operator_role, arrangement=arrangement,
                        solo=source_id))
            if 2 in sizes:
                out.append(build_balanced_trial(
                    scenario, sources, pair, options, flipped=flipped,
                    operator_role=operator_role, arrangement=arrangement))
    seen = {spec.trial_id for spec in out}
    if len(seen) != len(out):
        raise DesignError(f"{run.run_id}: two trials share an id, and a seed is "
                          f"drawn from the id")
    return out


def print_balance(specs: Sequence[TrialSpec]) -> None:
    """Per composition: arrangements used, how evenly sources sit and carry, and how far
    any option is from sitting last its fair share of the time. A non-zero slot spread
    confounds a source's strength with its position, which is what the first run's
    headline turned out to be; an option tied to a position confounds content with it."""
    groups: dict[str, list] = {}
    for spec in specs:
        if spec.meta.get("arm") != "pair":
            continue
        name = "-".join(spec.meta.get("composition") or spec.meta["source_pair"])
        groups.setdefault(name, []).append(spec)

    def spread(counter) -> float:
        worst = 0.0
        for key in {k for k, _ in counter}:
            values = [v for (k, _), v in counter.items() if k == key]
            worst = max(worst, (max(values) - min(values)) / max(values))
        return worst

    print("\nBALANCE, per composition. A source that sits early more often than")
    print("late has its strength confounded with position.")
    print(f"  {'composition':18s} {'n':>5} {'arrangements':>13} "
          f"{'slot spread':>12} {'option spread':>14} {'option last':>12}")
    for name, group in sorted(groups.items(), key=lambda kv: (len(kv[0]), kv[0])):
        slots: collections.Counter = collections.Counter()
        opts: collections.Counter = collections.Counter()
        last: collections.Counter = collections.Counter()
        for spec in group:
            for key, value in spec.meta["slots"].items():
                if key != "task":
                    slots[(key, value)] += 1
            final = max(spec.meta["carries"], key=lambda s: spec.meta["slots"][s])
            for key, value in spec.meta["carries"].items():
                # Keyed option first, so the spread is one option across the sources: which source carries it.
                opts[(value, key)] += 1
                last[value] += key == final
        size = len(group[0].meta.get("composition") or group[0].meta["source_pair"])
        seen = collections.Counter(value for (value, _) in opts.elements())
        tied = max(abs(last[o] / seen[o] - 1 / size) for o in seen)
        pinned = len(group[0].meta["operator_pinned"])
        total = arrangement_count(pinned, size - pinned)
        used = len({spec.meta["arrangement"] for spec in group})
        flag = "  <-- position" if spread(slots) > 1e-9 else ""
        print(f"  {name:18s} {len(group):>5} {used:>6}/{total:<6} "
              f"{spread(slots):>11.0%} {spread(opts):>13.0%} {tied:>+11.0%}{flag}")


def _sources(spec: TrialSpec) -> tuple:
    """The sources a trial sets against each other; none for the load and tier designs."""
    return tuple(spec.meta.get("composition") or spec.meta.get("source_pair") or ())


def print_tier_balance(specs: Sequence[TrialSpec], scenarios: Scenarios) -> None:
    """Per tier pair: its items, how evenly the four winner cases fall, and which options meet."""
    cells: dict = collections.defaultdict(collections.Counter)
    met: dict = collections.defaultdict(set)
    for spec in specs:
        ids = [o["id"] for o in scenarios[spec.scenario_id]["options"]]
        winner = spec.meta["policy_winner"]
        loser = next(o for o in spec.meta["order"] if o != winner)
        pair = tuple(spec.meta["rank_pair"])
        cells[pair][(ids.index(winner) < ids.index(loser), spec.meta["winner_first"])] += 1
        if len(ids) == 5:
            met[pair].add(frozenset((winner, loser)))
    items = [sum(c.values()) for c in cells.values()]
    print(f"declared tiers: {len(cells)} tier pairs, {min(items)} to {max(items)} items each")
    print("  earlier- or later-listed winner, shown first or second: the most two of the four "
          f"differ within a pair is {max(max(c.values()) - min(c.values()) for c in cells.values())}")
    print(f"  pairs of options that meet under every tier pair: at least "
          f"{min(len(m) for m in met.values())} of 10")


def print_load_balance(specs: Sequence[TrialSpec]) -> None:
    by_bundle = collections.Counter(spec.meta.get("bundle", "worked") for spec in specs)
    grid = collections.Counter((spec.meta["n_instructions"], spec.meta["k_conflict_groups"])
                               for spec in specs)
    print("load: " + ", ".join(f"{b} {n}" for b, n in sorted(by_bundle.items())))
    print("  trials per (n, k): " + ", ".join(f"({n}, {k}) {c}" for (n, k), c in sorted(grid.items())))


def _main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    import json

    from ..logs import add_arguments, from_arguments, get_logger
    from .rendering import render_dicts
    from .serving import ConfigError, load_run
    from .trials import load_scenarios

    parser = argparse.ArgumentParser(prog="python3 -m whowins.runner.design",
                                     description=__doc__.split("\n\n")[0])
    parser.add_argument("run_id", help="a run in configs/runs/")
    parser.add_argument("--show", type=int, default=0, metavar="N",
                        help="print the first N trials as they would be sent, "
                             "rendered (default: %(default)s, counts only)")
    parser.add_argument("--balance", action="store_true",
                        help="per composition: how many arrangements are used, "
                             "and how evenly each source sits in each slot and "
                             "carries each option. Read it before a run, not after")
    add_arguments(parser, progress=False)
    args = parser.parse_args(argv)
    from_arguments("design", args, args.run_id)
    log = get_logger(__name__)
    try:
        run = load_run(args.run_id)
    except (ConfigError, KeyError, OSError) as exc:
        log.error("config error: %s", exc)
        return 2
    scenarios = load_scenarios()
    specs = trials_for_run(run, scenarios)
    print(f"{len(specs)} trials over {len(scenarios)} scenarios, "
          f"{run.model.key} at {run.environment.key}, policy {run.policy.name}")
    repeats = getattr(run, "repeats", 1) or 1
    by_arm = collections.Counter((len(_sources(s)), s.meta.get("arm", "pair")) for s in specs)
    if len(by_arm) > 1 or args.balance:
        print(f"what it sends, at {repeats} draw(s) each:")
        for (size, arm), count in sorted(by_arm.items()):
            kind = f"{size}-source {arm}" if size else arm
            print(f"  {kind:16s} {count:6d} trials  {count * repeats:7d} draws")
        print(f"  {'':16s} {len(specs):6d} trials  {len(specs) * repeats:7d} draws")
        for size in sorted({n for n, _ in by_arm} - {0, 1}):
            _, dropped = eligible_for(list(scenarios.values()), size)
            if dropped:
                print(f"  size {size} leaves out "
                      + ", ".join(f"{k} ({v})" for k, v in sorted(dropped.items()))
                      + f": fewer than {size} mutually exclusive options")
    pairs = collections.Counter("-".join(_sources(s)) for s in specs if _sources(s))
    if pairs:
        print("compositions: " + ", ".join(f"{k} {v}" for k, v in sorted(pairs.items())))

    if args.balance:
        from .layouts import LAYOUT_DESIGNS, print_layout_balance

        if run.design in TIER_DESIGNS:
            print_tier_balance(specs, scenarios)
        elif run.design in LAYOUT_DESIGNS:
            print_layout_balance(specs)
        elif run.design in (LOAD, LOAD_BUNDLES):
            print_load_balance(specs)
        else:
            print_balance(specs)

    for spec in specs[:args.show]:
        print(f"\n--- {spec.trial_id}  {spec.meta.get('carries', '')}")
        for message in render_dicts(spec, scenarios):
            print(json.dumps(message)[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
