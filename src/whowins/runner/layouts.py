"""Three designs that each move one thing the ladder holds fixed, paired within the item.
`operator-decomposition` sends the operator's line first or last, as a real operator message or
as its label in a user message. `one-message` puts the user's line and the memory note in their
own messages or inside the task's. `realism` sends hand-written items bare and in context."""

from __future__ import annotations

import collections
import json
from typing import Any, Mapping, Optional, Sequence

from .design import DesignError, Source, option_pairs
from .rendering import Scenarios
from .spec import Block, Element, Message, Span, Task, TrialSpec, tool_call
from .tools import CONTEXT_TOOL

OPERATOR = "operator-decomposition"
ONE_MESSAGE = "one-message"
REALISM = "realism"
LAYOUT_DESIGNS = (OPERATOR, ONE_MESSAGE, REALISM)

OPERATOR_PAIRS = (("S1", "S3"), ("S1", "S4"), ("S1", "S5"),
                  ("S2", "S3"), ("S2", "S4"), ("S2", "S5"))
"""Each operator line against each source outside the operator message. S1 against S2 is two
lines of one message, which no layout here could move apart."""

ONE_MESSAGE_EVERY = 4
"""One scenario in four, by id: 270 items, enough for an effect the size of primacy against
recency, at a quarter of the cost of all 1,080."""

REALISM_PAIRS = (("S3", "S4"), ("S3", "S5"), ("S4", "S5"),
                 ("S1", "S3"), ("S1", "S4"), ("S1", "S5"))


def _deal(scenario: Mapping[str, Any], key: Any, counts: collections.Counter
          ) -> tuple[str, str]:
    """Which two options a pair carries, and which way round: every pair of the scenario's
    options in turn, each both ways, counted per composition so content is spread evenly."""
    pairs = option_pairs(scenario)
    k = counts[key]
    counts[key] += 1
    a, b = pairs[(k // 2) % len(pairs)]
    return (a, b) if k % 2 == 0 else (b, a)


def _send(order: Sequence[str], carried: Mapping[str, str], sources: Mapping[str, Source],
          roles: Mapping[str, str], texts: Optional[Mapping[str, str]] = None
          ) -> list[Element]:
    """Each source's span in send order, a tool result behind the call it answers."""
    elements: list[Element] = []
    for slot, source_id in enumerate(order):
        role = roles[source_id]
        call_id = f"call_{source_id.lower()}" if role == "tool" else None
        if call_id:
            elements.append(Message("assistant", "", tool_calls=[tool_call(call_id, CONTEXT_TOOL)]))
        elements.append(Span(option_id=carried[source_id], transport_role=role,
                             displayed_provenance=sources[source_id].displayed_provenance,
                             position_slot=slot, tool_call_id=call_id,
                             text=(texts or {}).get(source_id)))
    return elements


def _spec(design: str, scenario: Mapping[str, Any], trial_id: str, order: Sequence[str],
          carried: Mapping[str, str], elements: Sequence[Element], operator_role: str,
          roles: Mapping[str, str], layout: Mapping[str, Any], **extra: Any) -> TrialSpec:
    pair = sorted(order)
    ids = [o["id"] for o in scenario["options"]]
    meta = {
        "design": design, "arm": "pair", "n_competing": 2, "composition": pair,
        "composition_size": 2, "source_pair": pair, "sources_in_play": pair,
        "carries": {s: carried[s] for s in pair},
        "order": [*order, "task"], "slots": {**{s: i for i, s in enumerate(order)},
                                             "task": len(order)},
        "operator_pinned": [order[0]] if roles[order[0]] == operator_role else [],
        "flipped": ids.index(carried[pair[0]]) > ids.index(carried[pair[1]]),
        "layout": dict(layout), **extra,
    }
    return TrialSpec(trial_id=trial_id, scenario_id=scenario["scenario_id"],
                     renderer="plain_chat", elements=list(elements),
                     options_in_play=tuple(carried[s] for s in pair), meta=meta)


def operator_trials(scenarios: Sequence[Mapping[str, Any]], sources: Mapping[str, Source],
                    operator_role: str, late_possible: bool) -> list[TrialSpec]:
    """Every scenario against one of the six operator pairs, under four layouts: the operator's
    line first or last, as a real operator message or as its label in a user message. Where the
    template refuses a late operator message, that one layout is not built."""
    counts: collections.Counter = collections.Counter()
    by_family: dict[str, list] = collections.defaultdict(list)
    for scenario in sorted(scenarios, key=lambda s: s["scenario_id"]):
        by_family[scenario["family"]].append(scenario)
    out = []
    for family in sorted(by_family):
        for j, scenario in enumerate(by_family[family]):
            op, other = OPERATOR_PAIRS[j % len(OPERATOR_PAIRS)]
            carried = dict(zip((op, other), _deal(scenario, (op, other), counts)))
            for role in ("real", "label"):
                for position in ("first", "last"):
                    if role == "real" and position == "last" and not late_possible:
                        continue
                    order = (op, other) if position == "first" else (other, op)
                    roles = {op: operator_role if role == "real" else "user",
                             other: sources[other].rides_on(operator_role)}
                    trial_id = f"{scenario['scenario_id']}@{op}-{other}~{role}-{position}"
                    out.append(_spec(
                        OPERATOR, scenario, trial_id,
                        order, carried, _send(order, carried, sources, roles), operator_role, roles,
                        {"role": role, "operator_position": position, "operator": op},
                        operator_late=role == "real" and position == "last"))
    return out


def one_message_trials(scenarios: Sequence[Mapping[str, Any]], sources: Mapping[str, Source],
                       operator_role: str) -> list[TrialSpec]:
    """The user's line (S3) against the memory note (S5), each in its own message or both
    inside the task's message, each order: whether "the first line wins inside a message, the
    last across messages" is about messages, measured instead of built in."""
    counts: collections.Counter = collections.Counter()
    chosen = sorted(scenarios, key=lambda s: s["scenario_id"])[::ONE_MESSAGE_EVERY]
    roles = {"S3": "user", "S5": "user"}
    out = []
    for scenario in chosen:
        carried = dict(zip(("S3", "S5"), _deal(scenario, ("S3", "S5"), counts)))
        for message in ("separate", "merged"):
            for first in ("S3", "S5"):
                order = (first, "S5" if first == "S3" else "S3")
                elements = _send(order, carried, sources, roles)
                if message == "merged":
                    elements = [Block("user", [*elements, Task()])]
                out.append(_spec(
                    ONE_MESSAGE, scenario,
                    f"{scenario['scenario_id']}@S3-S5~{message}-{first}first",
                    order, carried, elements, operator_role, roles,
                    {"message": message, "first": first}))
    return out


def realism_items() -> list[dict]:
    """Every hand-written item on disk, in batch order."""
    from ..validation.check_realism import batch_files

    items = []
    for path in batch_files():
        with open(path, encoding="utf-8") as fh:
            items.extend(json.load(fh)["items"])
    return items


def filled(item: Mapping[str, Any], source_id: str, text: str) -> str:
    """An item's context for one source, with the option's own text in its slot."""
    from ..validation.check_realism import SLOT

    return "\n".join(item["contexts"][source_id]).replace(SLOT, text)


def realism_trials(scenarios: Scenarios, sources: Mapping[str, Source], operator_role: str,
                   late_possible: bool) -> list[TrialSpec]:
    """Each item under six pairs of its sources, each order the format allows, bare and inside
    the item's own context, so "the later instruction wins" is compared on the same item with
    and without the text around it. A batch that fails its validator is never sent."""
    from ..validation.check_realism import check_all

    items = realism_items()
    if not items:
        raise DesignError("no realism batch in data/realism/ yet: the realism design sends "
                          "hand-written items, and none has been written")
    fails, _, _ = check_all(scenarios=scenarios)
    if fails:
        raise DesignError(f"the realism batches are not fit to send ({len(fails)} FAIL): "
                          + "; ".join(fails[:3]))
    counts: collections.Counter = collections.Counter()
    out = []
    for item in items:
        scenario = scenarios[item["scenario_id"]]
        text = {o["id"]: o["text"] for o in scenario["options"]}
        for pair in REALISM_PAIRS:
            carried = dict(zip(pair, _deal(scenario, pair, counts)))
            roles = {s: sources[s].rides_on(operator_role) for s in pair}
            orders = [pair] if "S1" in pair and not late_possible else [pair, pair[::-1]]
            for order in orders:
                for context in ("bare", "context"):
                    texts = {s: filled(item, s, text[carried[s]]) for s in pair} \
                        if context == "context" else None
                    trial_id = f"{scenario['scenario_id']}@{order[0]}-{order[1]}~{context}"
                    out.append(_spec(
                        REALISM, scenario, trial_id,
                        order, carried, _send(order, carried, sources, roles, texts),
                        operator_role, roles, {"context": context},
                        item_id=item["item_id"],
                        operator_late=roles[order[-1]] == operator_role))
    return out


def trials_for(design: str, scenarios: Scenarios, sources: Mapping[str, Source], family: Any
               ) -> list[TrialSpec]:
    """The trials one of these designs sends to a model of this family."""
    from .serving import late_operator_possible

    role = family.operator_role
    if design == OPERATOR:
        return operator_trials(list(scenarios.values()), sources, role,
                               late_operator_possible(family))
    if design == ONE_MESSAGE:
        return one_message_trials(list(scenarios.values()), sources, role)
    if design == REALISM:
        return realism_trials(scenarios, sources, role, late_operator_possible(family))
    raise DesignError(f"{design!r} is not one of {list(LAYOUT_DESIGNS)}")


def print_layout_balance(specs: Sequence[TrialSpec]) -> None:
    """Per composition: trials under each layout, and whether every item has all of them."""
    cells: dict = collections.defaultdict(collections.Counter)
    per_item: dict = collections.defaultdict(set)
    for spec in specs:
        key = "-".join(spec.meta["composition"])
        layout = tuple(sorted(spec.meta["layout"].items())) + (("order", spec.meta["order"][0]),)
        cells[key][layout] += 1
        per_item[(key, spec.meta.get("item_id") or spec.scenario_id)].add(layout)
    print("\nLAYOUTS, per composition. Every item must be sent under each of its layouts, so a")
    print("difference between layouts is read within the item.")
    for key, counter in sorted(cells.items()):
        full = len({len(v) for (k, _), v in per_item.items() if k == key}) == 1
        print(f"  {key:8s} " + ", ".join(
            f"{'/'.join(str(v) for _, v in layout)} {n}" for layout, n in sorted(counter.items()))
              + ("" if full else "  <-- an item misses a layout"))
