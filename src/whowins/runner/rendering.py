"""TrialSpec + scenario -> the exact messages a model receives.
Pure and deterministic: same spec, same bytes, every time. Every trial stores its
rendered transcript, and a renderer that could produce two for one spec would make the
stored one unverifiable. The byte layout IS the stimulus, so it is written by hand."""

from __future__ import annotations

from typing import Any, Mapping

from .spec import Block, Message, Span, Task, TrialSpec
from .vocabulary import (
    apply_surface,
    policy_message,
    policy_sentence,
    provenance_header,
    rank_line,
    source_attribute,
    task_line,
)


class RenderError(ValueError):
    """The spec and the scenario do not fit together."""


# --- Pulling the instruction text ---


Scenarios = Mapping[str, Mapping[str, Any]]
"""scenario_id -> scenario. A trial may draw on more than one: the load cell
takes its conflict groups from six different scenarios at once, because what it
varies is how many conflicts there are, not what they are about. For one
scenario, pass `{s["scenario_id"]: s}` -- never the bare scenario."""


def check_scenarios(scenarios: Any) -> None:
    """Refuse a single scenario passed where the mapping of them belongs.
    A bare scenario is a Mapping too, so without this it fails later and misleadingly:
    `render` reports the trial's own scenario as "not supplied"."""
    if isinstance(scenarios, Mapping) and "scenario_id" in scenarios \
            and "options" in scenarios:
        raise TypeError(
            f"expected a mapping of scenario_id -> scenario, but got the scenario "
            f"{scenarios['scenario_id']!r} itself; pass "
            f"{{scenario['scenario_id']: scenario}}"
        )


def _scenario(span: Span, spec: TrialSpec, scenarios: Scenarios) -> Mapping[str, Any]:
    sid = span.scenario_id or spec.scenario_id
    try:
        return scenarios[sid]
    except KeyError:
        raise RenderError(
            f"{spec.trial_id}: span {span.option_id!r} names scenario {sid!r}, "
            f"which was not supplied"
        ) from None


def span_text(span: Span, scenario: Mapping[str, Any]) -> str:
    """The instruction this span carries, before surface is applied."""
    if span.text is not None:
        return span.text
    for option in scenario["options"]:
        if option["id"] == span.option_id:
            return option["text"]
    raise RenderError(
        f"scenario {scenario.get('scenario_id')} has no option "
        f"{span.option_id!r}; it offers "
        f"{[o['id'] for o in scenario['options']]}"
    )


def _task(spec: TrialSpec, scenarios: Scenarios) -> str:
    if spec.task is not None:
        return spec.task
    return scenarios[spec.scenario_id]["task"]


def span_body(span: Span, scenario: Mapping[str, Any]) -> str:
    """Header lines plus the instruction, as one plain_chat message body.
    Public because reconstructing a hand-written trial needs to ask what a single span looks
    like without building a whole spec around it."""
    lines = []
    header = provenance_header(span.displayed_provenance, span.provenance_form)
    if header:
        lines.append(header)
    if span.declared_rank is not None:
        lines.append(rank_line(span.declared_rank, span.rank_notation))
    lines.append(apply_surface(span_text(span, scenario), span.surface))
    return "\n".join(lines)


# --- plain_chat ---


def _render_plain_chat(spec: TrialSpec, scenarios: Scenarios) -> list[Message]:
    messages: list[Message] = []
    if spec.policy_scheme is not None:
        messages.append(
            Message(spec.policy_role, policy_message(spec.policy_scheme, spec.policy_direction))
        )
    for el in spec.elements:
        if isinstance(el, Message):
            messages.append(el)
        elif isinstance(el, Span):
            messages.append(
                Message(el.transport_role, span_body(el, _scenario(el, spec, scenarios)),
                        tool_call_id=el.tool_call_id)
            )
        elif isinstance(el, Block):
            lines = [
                i if isinstance(i, str)
                else task_line(_task(spec, scenarios)) if isinstance(i, Task)
                else span_body(i, _scenario(i, spec, scenarios))
                for i in el.items
            ]
            messages.append(Message(el.role, "\n".join(lines)))
        elif isinstance(el, Task):
            messages.append(Message("user", task_line(_task(spec, scenarios))))
        else:
            raise RenderError(f"{spec.trial_id}: unknown element {el!r}")
    # Appended last unless the trial placed it. Every worked trial leaves it to us, so this stays the default.
    if not any(isinstance(el, Task) or isinstance(el, Block)
               and any(isinstance(i, Task) for i in el.items) for el in spec.elements):
        messages.append(Message("user", task_line(_task(spec, scenarios))))
    return messages


# --- xml_wrapped ---


_XML_UNSAFE = ("<", ">", "&")


def _xml_block(span: Span, scenario: Mapping[str, Any]) -> str:
    """One span as an XML-ish block.
    NOTHING IS ESCAPED, AND TEXT THAT WOULD NEED ESCAPING IS REFUSED. The byte layout is the
    stimulus, so turning `a & b` into `a &amp; b` would change what the model was asked --
    quietly, and only in one renderer."""
    text = apply_surface(span_text(span, scenario), span.surface)
    bad = [c for c in _XML_UNSAFE if c in text]
    if bad:
        raise RenderError(
            f"{scenario.get('scenario_id', '?')}: instruction text contains "
            f"{bad!r}, which the xml_wrapped envelope cannot carry unescaped. "
            f"This renderer escapes nothing on purpose -- its bytes are the "
            f"stimulus -- so either the scenario is reworded or the envelope "
            f"gains an escaping rule, and both are decisions for a person"
        )
    attrs = [
        f'transport="{span.transport_role}"',
        f'source="{source_attribute(span.displayed_provenance)}"',
    ]
    if span.declared_rank is not None:
        attrs.append(f'priority="{span.declared_rank}"')
    return f'  <block {" ".join(attrs)}>{text}</block>'


def _render_xml_wrapped(spec: TrialSpec, scenarios: Scenarios) -> list[Message]:
    lines = ["<context>"]
    if spec.policy_scheme is not None:
        sentence = policy_sentence(spec.policy_scheme, spec.policy_direction)
        lines.append(f"  <policy>{sentence}</policy>")
    lines.extend(_xml_block(sp, _scenario(sp, spec, scenarios)) for sp in spec.spans)
    lines.append("</context>")
    lines.append(task_line(_task(spec, scenarios)))
    return _around(spec, Message("user", "\n".join(lines)))


# --- json_envelope ---


def _json_string(value: str) -> str:
    """Escape a string for the envelope.
    Hand-written because `json.dumps` may change how it escapes non-ASCII between
    interpreter versions, and the exact bytes here are the stimulus."""
    out = []
    for ch in value:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


def _json_entry(span: Span, scenario: Mapping[str, Any]) -> str:
    parts = [
        f'"transport": "{span.transport_role}"',
        f'"source": "{source_attribute(span.displayed_provenance)}"',
    ]
    if span.declared_rank is not None:
        parts.append(f'"priority": {span.declared_rank}')
    text = apply_surface(span_text(span, scenario), span.surface)
    parts.append(f'"text": "{_json_string(text)}"')
    return "    {" + ", ".join(parts) + "}"


def _render_json_envelope(spec: TrialSpec, scenarios: Scenarios) -> list[Message]:
    lines = ["{"]
    if spec.policy_scheme is not None:
        sentence = policy_sentence(spec.policy_scheme, spec.policy_direction)
        lines.append(f'  "policy": "{_json_string(sentence)}",')
    lines.append('  "context": [')
    entries = [_json_entry(sp, _scenario(sp, spec, scenarios)) for sp in spec.spans]
    lines.append(",\n".join(entries))
    lines.append("  ],")
    lines.append(f'  "task": "{_json_string(_task(spec, scenarios))}"')
    lines.append("}")
    return _around(spec, Message("user", "\n".join(lines)))


def _around(spec: TrialSpec, envelope: Message) -> list[Message]:
    """Verbatim turns keep their place relative to the collapsed envelope.
    A MESSAGE BETWEEN TWO SPANS HAS NOWHERE TO GO and is refused rather than moved:
    everything the envelope collapses becomes one turn, so a verbatim message is either
    before it or after it."""
    positions = [i for i, el in enumerate(spec.elements) if not isinstance(el, Message)]
    if positions:
        first, last = positions[0], positions[-1]
        stranded = [i for i, el in enumerate(spec.elements)
                    if isinstance(el, Message) and first < i < last]
        if stranded:
            raise RenderError(
                f"{spec.trial_id}: a verbatim message sits between two spans, "
                f"and {spec.renderer} folds every span into one envelope, so it "
                f"has no place left to sit. Put it before the first span or "
                f"after the last, or send this trial as plain_chat"
            )
    before, after, seen = [], [], False
    for el in spec.elements:
        if isinstance(el, Message):
            (after if seen else before).append(el)
        else:
            seen = True
    return [*before, envelope, *after]


# --- Entry point ---

_RENDERERS = {
    "plain_chat": _render_plain_chat,
    "xml_wrapped": _render_xml_wrapped,
    "json_envelope": _render_json_envelope,
}


def render(spec: TrialSpec, scenarios: Scenarios) -> list[Message]:
    """The exact messages for one trial.
    `scenarios` maps scenario_id to scenario -- always the mapping; a bare scenario raises.
    A composite trial needs every scenario its spans name."""
    check_scenarios(scenarios)
    if spec.scenario_id is not None and spec.scenario_id not in scenarios:
        raise RenderError(
            f"{spec.trial_id}: names scenario {spec.scenario_id!r}, which was "
            f"not supplied (given {sorted(scenarios)[:6]})"
        )
    return _RENDERERS[spec.renderer](spec, scenarios)


def render_dicts(spec: TrialSpec, scenarios: Scenarios) -> list[dict[str, str]]:
    """`render`, in the shape a chat API takes and a trial file stores."""
    return [m.as_dict() for m in render(spec, scenarios)]


def quoted_share(spec: TrialSpec, scenarios: Scenarios) -> float:
    """How much of this trial was quoted verbatim rather than derived.
    A spec that is nothing but `Message` elements re-renders perfectly and proves nothing, so
    the acceptance test reports this alongside the diff."""
    messages = render(spec, scenarios)
    total = sum(len(m.content) for m in messages)
    quoted = sum(len(el.content) for el in spec.elements if isinstance(el, Message))
    return 0.0 if total == 0 else quoted / total
