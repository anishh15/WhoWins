"""What one thing sent to a model is, as a value.
A TrialSpec is complete: the rendered messages are a pure function of it and the base
scenarios it names. The 70 worked trials store their messages verbatim AND the fields
they were built from, so the renderer can be checked against a person's decision."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence, Union

from .vocabulary import (
    SURFACES,
    UnknownVocabulary,
    check_transport,
    provenance_header,
)

RENDERERS = ("plain_chat", "xml_wrapped", "json_envelope")
"""The three the harness cell defines and prices against each other.

`plain_chat_reordered` is deliberately absent. harn-10 carries that name and
renders through `plain_chat` unchanged -- what differs is the slot order of its
spans, a property of the design rather than of the serialization. Treating it as
a fourth renderer would count one manipulation twice.
"""

COLLAPSED = ("xml_wrapped", "json_envelope")
"""Renderers with no role tokens: every span actually arrives as `user`, and the
transport it claims survives only as text. That collapse is the measurement, not
an artifact -- many production harnesses genuinely do this."""


@dataclass(frozen=True)
class Message:
    """One verbatim turn, reproduced exactly as given.
    `tool_calls` carries an assistant turn that called a tool, because a tool result has to
    answer a call: gpt-oss reads the tool's name off the call, and a result nobody asked for
    is refused before it is sent."""

    role: str
    content: str
    tool_calls: Sequence[Mapping[str, Any]] = ()
    tool_call_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.tool_calls and self.role != "assistant":
            raise ValueError(f"a {self.role!r} message cannot carry tool calls")
        if self.tool_call_id is not None and self.role != "tool":
            raise ValueError(f"a {self.role!r} message answers no tool call")
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            out["tool_calls"] = [dict(call) for call in self.tool_calls]
        if self.tool_call_id is not None:
            out["tool_call_id"] = self.tool_call_id
        return out


def tool_call(call_id: str, name: str, arguments: str = "{}") -> dict[str, Any]:
    """One entry of an assistant message's `tool_calls`, in the wire shape both
    engines read."""
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": arguments}}


@dataclass(frozen=True)
class Span:
    """One instruction, and every claim made about where it came from."""

    option_id: str
    transport_role: str
    displayed_provenance: str = "none"
    position_slot: int = 0
    surface: str = "plain"
    declared_rank: Optional[int] = None
    rank_notation: str = "bracket"
    provenance_form: str = "default"

    tool_call_id: Optional[str] = None
    """For a tool-transport span: the id of the assistant call it answers.

    A tool result that answers nothing is refused before it is sent, on both
    families, so a trial that puts an instruction in a tool result has to show
    the call as well. The id ties the two together.
    """

    scenario_id: Optional[str] = None
    """Which scenario this option belongs to, when it is not the spec's own.

    The load cell draws its conflict groups from six different scenarios at
    once -- tool-0001, path-0008 and four format items -- because what it varies
    is the *number* of conflicts, not their content.
    """

    text: Optional[str] = None
    """Overrides the scenario's option text.

    Needed by the authorship cell, whose instruction is *elicited* from the
    model and so is phrased in the model's own words -- "When staging
    intermediate files, always use /scratch/c." where the scenario's option says
    "Stage them in /scratch/c." Both drive the same checker, because the checker
    reads the write target off the trace and never reads instruction text.

    Nothing verifies that an override still means what the option means. It
    cannot: the checker scores what the model *did*, so there is no code path
    from an instruction's wording to its intended value. An override is an
    authoring decision, recorded as one.
    """

    def __post_init__(self) -> None:
        check_transport(self.transport_role)
        if self.tool_call_id is not None and self.transport_role != "tool":
            raise ValueError(
                f"span {self.option_id} arrives as {self.transport_role!r} and "
                f"answers no tool call; only a tool result does"
            )
        if self.surface not in SURFACES:
            raise UnknownVocabulary(
                f"unknown surface {self.surface!r}; defined: {sorted(SURFACES)}"
            )
        # Resolving the header now turns an unusable provenance into an error at construction rather than halfway through rendering a batch.
        provenance_header(self.displayed_provenance, self.provenance_form)


@dataclass(frozen=True)
class Block:
    """Several lines inside one message.
    The load cell holds source constant by putting every instruction into one system
    message, so its instructions are lines and not turns. Filler lines are plain strings;
    instruction lines are spans; a Task puts the task line inside the message."""

    role: str
    items: Sequence[Union["Span", str, "Task"]]

    def __post_init__(self) -> None:
        check_transport(self.role)
        if not self.items:
            raise ValueError("a Block with no items renders an empty message")


@dataclass(frozen=True)
class Task:
    """Where the task line goes, for a design that places it.
    The renderer appends the task last when no trial says otherwise. That is also a claim --
    that every instruction source arrives before the person says what they want -- so a
    design that varies it says so here rather than relying on the default."""


@dataclass(frozen=True)
class ConflictGroup:
    """One conflict inside a composite trial: a scenario, and which options compete.
    The load cell holds several at once, drawn from different scenarios, because what it
    varies is how many conflicts there are rather than what they are about. Each group is
    scored on its own."""

    group_id: str
    scenario_id: str
    members: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "members", tuple(self.members))
        if len(self.members) < 2:
            raise ValueError(
                f"{self.group_id}: a conflict group needs two or more members -- "
                f"one instruction conflicts with nothing"
            )
        if len(set(self.members)) != len(self.members):
            raise ValueError(f"{self.group_id}: repeated member in {list(self.members)}")


Element = Union[Span, Message, Block, Task]


def spans_of(elements: Sequence[Element]) -> list[Span]:
    """Every span in order, reaching inside blocks."""
    out: list[Span] = []
    for el in elements:
        if isinstance(el, Span):
            out.append(el)
        elif isinstance(el, Block):
            out.extend(i for i in el.items if isinstance(i, Span))
    return out


@dataclass(frozen=True)
class TrialSpec:
    """One rendered thing to send, complete enough to rebuild byte for byte.
    A single-scenario trial names its scenario and is scored against it. A COMPOSITE trial
    names none: it states its own task, every span says which scenario it came from, and it
    is scored per conflict group."""

    trial_id: str
    scenario_id: Optional[str]
    renderer: str
    elements: Sequence[Element]

    task: Optional[str] = None
    """Overrides the scenario's task. The load cell uses one composite task
    across six component scenarios, so it cannot take any single one's."""

    policy_scheme: Optional[str] = None
    policy_direction: Optional[str] = None
    """Set both to state a priority policy. plain_chat emits it as a leading
    message; the collapsed renderers carry it inside the envelope."""

    policy_role: str = "system"
    """The role that leading message rides on: the operator channel of the family the trial
    is sent to. `system` in every worked trial; gpt-oss's operator channel is `developer`."""

    meta: dict[str, Any] = field(default_factory=dict)
    """Cell-specific bookkeeping carried through to the run record untouched:
    contrast, n_competing, prediction_role, rank_pair, condition, and the rest.
    The renderer never reads it."""

    conflict_groups: Sequence[ConflictGroup] = ()
    """Composite trials only: the conflicts the trial contains, each scored alone.

    Must name exactly the instructions the trial shows -- every span a member of
    some group, every member shown as a span. An instruction shown but in no
    group would never be scored; a member never shown would be scored on an
    instruction the model never saw. Empty for a zero-conflict control, which
    then has nothing on the behaviour axis to score."""

    tool_scenarios: Sequence[str] = ()
    """The scenarios whose tools this trial offers, in order.

    Empty means the scenarios it is scored against: its own, or its groups'. The
    load cell names every component of its composite task, so all ten of its
    trials offer the same tools whatever k is. That is the cell's own rule -- it
    holds prompt length fixed while conflict varies -- and a chat template puts
    the tool schemas into the prompt, so a tool list that grew with k would
    break it. It is also what makes the task doable at k = 0: "run the required
    repo check, then write the release note file" needs a check tool and a
    write tool whether or not anything conflicts."""

    options_in_play: Sequence[str] = ()
    """Single-scenario trials: which of the scenario's options the trial puts in
    front of the model. Empty means the options its spans carry.

    Recorded rather than always derived, because an option can be presented
    without a span of its own: dec-10 carries o1 inside the operator's policy
    turn, and bind-10 carries two options inside the parser's output, both
    quoted verbatim. A reply that does one of the scenario's OTHER options
    answers nothing this trial asked and is scored off-menu -- the rule the
    conflict groups of a composite trial already follow."""

    def __post_init__(self) -> None:
        if self.renderer not in RENDERERS:
            raise UnknownVocabulary(
                f"unknown renderer {self.renderer!r}; defined: {list(RENDERERS)}"
            )
        if self.policy_role not in ("system", "developer"):
            raise ValueError(f"{self.trial_id}: a policy rides on the operator channel, "
                             f"system or developer, not {self.policy_role!r}")
        if (self.policy_scheme is None) != (self.policy_direction is None):
            raise ValueError(
                f"{self.trial_id}: policy_scheme and policy_direction must be "
                f"set together -- a policy with no direction states nothing, "
                f"and a direction with no scheme has nothing to order"
            )
        spans = self.spans
        slots = [s.position_slot for s in spans]
        if len(set(slots)) != len(slots):
            raise ValueError(
                f"{self.trial_id}: two spans share a position slot {slots}. "
                f"Slot order is what the analysis reads as position, so a tie "
                f"makes position undefined for those spans."
            )
        if slots != sorted(slots):
            raise ValueError(
                f"{self.trial_id}: spans appear in element order {slots}, which "
                f"is not their slot order. Rendering follows element order, so "
                f"the recorded slots would describe a different transcript."
            )
        if any(s.declared_rank is not None for s in spans) \
                and self.policy_scheme is None:
            raise ValueError(
                f"{self.trial_id}: a span declares a rank but no policy says "
                f"which direction wins. An unstated policy makes the ground "
                f"truth undefined -- a rank label is not authority on its own, "
                f"which is the whole point of dec-10."
            )
        tasks = [el for el in self.elements if isinstance(el, Task)] + [
            i for el in self.elements if isinstance(el, Block) for i in el.items
            if isinstance(i, Task)]
        if len(tasks) > 1:
            raise ValueError(
                f"{self.trial_id}: {len(tasks)} Task elements. The task is said "
                f"once, and a trial that said it twice would not be the trial "
                f"the record describes"
            )
        if self.renderer in COLLAPSED:
            if tasks:
                raise ValueError(
                    f"{self.trial_id}: a Task cannot be placed inside "
                    f"{self.renderer}, which folds every span into one envelope "
                    f"and appends the task after it. No worked trial asks for "
                    f"this, and the collapsed renderers are a stimulus whose "
                    f"byte layout is the measurement"
                )
            if any(isinstance(el, Block) for el in self.elements):
                raise ValueError(
                    f"{self.trial_id}: a Block cannot be collapsed. "
                    f"{self.renderer} folds every span into one envelope, so "
                    f"lines inside a separate message have nowhere to go. "
                    f"No worked trial asks for this."
                )
        if self.scenario_id is None:
            self._check_composite(spans)
        else:
            if self.conflict_groups:
                raise ValueError(
                    f"{self.trial_id}: conflict groups belong to composite trials. "
                    f"This one names scenario {self.scenario_id!r} and is scored "
                    f"against it."
                )
            shown = {s.option_id for s in spans
                     if s.scenario_id in (None, self.scenario_id)}
            left_out = sorted(shown - set(self.options_in_play)) \
                if self.options_in_play else []
            if left_out:
                raise ValueError(
                    f"{self.trial_id}: spans show {left_out}, which options_in_play "
                    f"{list(self.options_in_play)} leaves out -- a shown option "
                    f"cannot be scored off-menu"
                )

    def _check_composite(self, spans: list[Span]) -> None:
        if self.options_in_play:
            raise ValueError(
                f"{self.trial_id}: a composite trial's options in play are its "
                f"conflict groups' members; options_in_play is for single-scenario "
                f"trials"
            )
        if self.task is None:
            raise ValueError(
                f"{self.trial_id}: a composite trial names no scenario, so it "
                f"must state its own task"
            )
        unnamed = [s.option_id for s in spans if s.scenario_id is None]
        if unnamed:
            raise ValueError(
                f"{self.trial_id}: spans {unnamed} name no scenario, and a "
                f"composite trial has none of its own to fall back on"
            )
        ids = [g.group_id for g in self.conflict_groups]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{self.trial_id}: repeated conflict group id in {ids}")
        shown = {(s.scenario_id, s.option_id) for s in spans}
        scored = {(g.scenario_id, m) for g in self.conflict_groups for m in g.members}
        if shown != scored:
            raise ValueError(
                f"{self.trial_id}: the conflict groups must score exactly the "
                f"instructions shown. Shown but in no group: "
                f"{sorted(shown - scored)}; in a group but never shown: "
                f"{sorted(scored - shown)}"
            )

    @property
    def spans(self) -> list[Span]:
        return spans_of(self.elements)
