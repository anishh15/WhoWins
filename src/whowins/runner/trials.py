"""Read the worked trials in `data/trials/` back as specs.
The 70 trials were hand-written before any renderer existed, so they are the renderer's
specification and its only independent test: reproducing them byte for byte is
agreement with what a person decided, not with our own code."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Optional, Sequence

from ..data import iter_scenarios, read_json, trial_files
from .rendering import RenderError, render_dicts, span_body, task_line
from .spec import Block, COLLAPSED, ConflictGroup, Element, Message, Span, TrialSpec
from .vocabulary import (
    POLICY_MESSAGES,
    POLICY_SENTENCES,
    PROVENANCE_HEADERS,
    RANK_NOTATIONS,
    UnknownVocabulary,
)

FORM_ORDER = (
    "default", "declares_precedence", "text_claim_only",
    "self", "another_agent", "self_terse", "the_user",
)
"""Tried in this order. `default` first, so a trial that does not need one of the
others is never recorded as using one."""


def load_scenarios() -> dict[str, dict]:
    """scenario_id -> scenario, for every base scenario."""
    return {s["scenario_id"]: s for _, s in iter_scenarios()}


def load_trials() -> list[dict]:
    """Every worked trial, in file order, cell headers dropped."""
    out = []
    for path in trial_files():
        for t in read_json(path):
            if "trial_id" in t:
                t = dict(t)
                t["_file"] = os.path.basename(path)
                out.append(t)
    return out


def load_cell_headers() -> dict[str, dict]:
    """cell -> the `_cell_header` its trial file opens with.
    The load cell's header is the only record of which scenarios its composite task is made
    of: the zero-conflict trials name no conflict group, so their own fields cannot say
    which tools the task needs."""
    out = {}
    for path in trial_files():
        for entry in read_json(path):
            header = entry.get("_cell_header")
            if header and header.get("cell"):
                out[header["cell"]] = header
    return out


@dataclass
class Reconstruction:
    """One attempt to express a hand-written trial as a spec."""

    trial_id: str
    cell: str
    spec: Optional[TrialSpec]
    stored: list[dict[str, str]]
    rendered: Optional[list[dict[str, str]]]
    reason: Optional[str] = None

    @property
    def exact(self) -> bool:
        return self.rendered is not None and self.rendered == self.stored

    @property
    def quoted_chars(self) -> int:
        if self.spec is None:
            return self.total_chars
        return sum(len(el.content) for el in self.spec.elements
                   if isinstance(el, Message))

    @property
    def total_chars(self) -> int:
        return sum(len(m["content"]) for m in self.stored)

    @property
    def derived_share(self) -> float:
        if not self.total_chars:
            return 1.0
        return 1.0 - self.quoted_chars / self.total_chars

    def diff(self) -> str:
        if self.rendered is None:
            return self.reason or "no spec"
        for i, (a, b) in enumerate(zip(self.rendered, self.stored)):
            if a != b:
                return f"message {i}\n     rendered {a!r}\n     stored   {b!r}"
        if len(self.rendered) != len(self.stored):
            return (f"{len(self.rendered)} messages rendered, "
                    f"{len(self.stored)} stored")
        return ""


# --- Candidate spans ---


def _claimed_transport(raw: Mapping[str, Any]) -> Optional[str]:
    """The transport a span claims.
    The harness cell records `actual_transport` and `claimed_transport` separately, because
    in the collapsed renderers everything really arrives as `user` while still claiming to
    be a system or tool block."""
    return (raw.get("claimed_transport") or raw.get("transport_role")
            or raw.get("actual_transport"))


def _candidates(raw: Mapping[str, Any], text: Optional[str] = None,
                scenario_id: Optional[str] = None,
                transport: Optional[str] = None) -> Iterator[Span]:
    """Every span the recorded fields permit, most likely first."""
    provenance = raw.get("displayed_provenance", "none")
    forms = ("text_claim_only",) if raw.get("realization") == "text_claim_only" \
        else FORM_ORDER
    notations = (raw["rank_notation"],) \
        if raw.get("rank_notation") in RANK_NOTATIONS else tuple(RANK_NOTATIONS)

    for form in forms:
        if (provenance, form) not in PROVENANCE_HEADERS:
            continue
        for notation in notations:
            yield Span(
                option_id=raw["option_id"],
                transport_role=transport or _claimed_transport(raw),
                displayed_provenance=provenance,
                position_slot=raw.get("position_slot", 0),
                surface=raw.get("surface") or "plain",
                declared_rank=raw.get("declared_rank"),
                rank_notation=notation,
                provenance_form=form,
                scenario_id=scenario_id,
                text=text,
            )


def _policy_of(trial, stored) -> tuple[Optional[str], Optional[str]]:
    """Whether this trial states a priority policy, and in which direction."""
    if trial.get("scheme") and trial.get("rule_direction"):
        return trial["scheme"], trial["rule_direction"]
    first = stored[0]["content"] if stored else ""
    for (scheme, direction), message in POLICY_MESSAGES.items():
        if first == message:
            return scheme, direction
    # The collapsed renderers have no system turn to put it in, so the bare sentence travels inside the envelope.
    blob = " ".join(m["content"] for m in stored)
    for (scheme, direction), sentence in POLICY_SENTENCES.items():
        if f"<policy>{sentence}</policy>" in blob or f'"policy": "{sentence}"' in blob:
            return scheme, direction
    return None, None


# --- The three shapes a worked trial takes ---


def _spans_shape(trial, scenarios, stored, renderer, has_policy) -> Sequence[Element]:
    """Trials that record spans: decomposition, composition, tier, binding, harness.
    Each stored message is either a recorded span, rendered, or a turn the vocabulary does
    not produce, quoted. Matching is by exact body, so a span that "matches" really does
    render to those bytes."""
    scenario = scenarios[trial["scenario_id"]]
    unused = list(trial["spans"])
    elements: list[Element] = []

    body = stored[1 if has_policy else 0:-1] if renderer not in COLLAPSED else []
    if renderer in COLLAPSED:
        # One envelope carries every span; only surrounding turns are elements.
        for raw in trial["spans"]:
            elements.append(next(_candidates(raw)))
        return elements

    for msg in body:
        hit = None
        for raw in unused:
            for cand in _candidates(raw, _elicited(raw, trial, scenario, stored)):
                if (cand.transport_role == msg["role"]
                        and span_body(cand, scenario) == msg["content"]):
                    hit = (raw, cand)
                    break
            if hit:
                break
        if hit:
            unused.remove(hit[0])
            elements.append(hit[1])
        else:
            elements.append(Message(**msg))

    # A span left unmatched sits inside a bespoke turn that was quoted instead; appending it would render a turn nobody wrote, so the quoted share records the cost.
    return elements


def _load_shape(trial, scenarios, stored) -> Sequence[Element]:
    """The load cell: every instruction inside one system message.
    Source is held constant here on purpose -- that is what makes the cell about load rather
    than provenance -- so the instructions are lines, not turns."""
    wanted: dict[str, tuple[str, str]] = {}
    for group in trial.get("conflict_groups", []):
        sid = group["scenario_id"]
        for oid in group["members"]:
            text = next(o["text"] for o in scenarios[sid]["options"] if o["id"] == oid)
            wanted[text] = (sid, oid)

    items: list[Any] = []
    slot = 0
    for line in stored[0]["content"].split("\n"):
        if line in wanted:
            sid, oid = wanted[line]
            items.append(Span(option_id=oid, transport_role="system",
                              displayed_provenance="none", position_slot=slot,
                              scenario_id=sid))
            slot += 1
        else:
            items.append(line)
    return [Block(stored[0]["role"], items)]


def _authorship_shape(trial, scenarios, stored) -> Sequence[Element]:
    """The authorship cell, which records no spans at all.
    It describes itself with real_generator / claimed_author / channel / style and leaves the
    transcript to say the rest, so each message is matched against the whole vocabulary."""
    scenario = scenarios[trial["scenario_id"]]
    values = {o["id"]: o["checker"].split("==", 1)[1] for o in scenario["options"]}
    elements: list[Element] = []
    slot = 0

    for msg in stored[:-1]:
        hit = None
        for oid, value in values.items():
            if value not in msg["content"]:
                continue
            lines = msg["content"].split("\n")
            raw = {"option_id": oid, "displayed_provenance": None,
                   "position_slot": slot}
            for provenance in ("operator_policy", "repo_config", "memory",
                               "user_message", "tool_result", "none"):
                raw["displayed_provenance"] = provenance
                for cand in _candidates(raw, text=lines[-1], transport=msg["role"]):
                    if span_body(cand, scenario) == msg["content"]:
                        hit = cand
                        break
                if hit:
                    break
            if hit:
                break
        if hit:
            elements.append(hit)
            slot += 1
            del values[hit.option_id]
        else:
            elements.append(Message(**msg))
    return elements


def _elicited(raw, trial, scenario, stored) -> Optional[str]:
    """A span whose wording is not the collection's, recovered from the text."""
    if trial.get("cell") != "authorship_and_provenance":
        return None
    option = next((o for o in scenario["options"] if o["id"] == raw["option_id"]), None)
    if option is None:
        return None
    value = option["checker"].split("==", 1)[1]
    for msg in stored:
        if value in msg["content"] and option["text"] not in msg["content"]:
            return msg["content"].split("\n")[-1]
    return None


# --------------------------------------------------------------------------


def reconstruct(trial: Mapping[str, Any], scenarios: Mapping[str, dict],
                header: Optional[Mapping[str, Any]] = None) -> Reconstruction:
    """One hand-written trial, as a spec, rendered back.
    `header` is the trial's `_cell_header`, needed only by the load cell: its composite task
    is made of the header's component_scenarios."""
    tid, cell = trial["trial_id"], trial.get("cell", "?")
    stored = [dict(m) for m in trial["messages"]]
    renderer = trial.get("renderer", "plain_chat")
    if renderer == "plain_chat_reordered":
        renderer = "plain_chat"

    scheme, direction = _policy_of(trial, stored)
    groups: tuple[ConflictGroup, ...] = ()
    tool_scenarios: tuple[str, ...] = ()
    in_play: tuple[str, ...] = ()

    try:
        if trial.get("conflict_groups") is not None and not trial.get("scenario_id"):
            # Composite: no scenario of its own. The first group's scenario used to stand in, which scored every other group as if it were not there.
            elements = _load_shape(trial, scenarios, stored)
            scenario_id = None
            task = stored[-1]["content"][len(task_line("")):]
            groups = tuple(ConflictGroup(g["group"], g["scenario_id"], g["members"])
                           for g in trial["conflict_groups"])
            tool_scenarios = tuple((header or {}).get("component_scenarios", ()))
        else:
            scenario_id = trial["scenario_id"]
            task = None
            # What the trial presents, as its own `checkers` field records it -- including options presented inside quoted prose.
            in_play = tuple(trial.get("checkers") or ())
            if trial.get("spans"):
                elements = _spans_shape(trial, scenarios, stored, renderer,
                                        scheme is not None)
            else:
                elements = _authorship_shape(trial, scenarios, stored)
    except (KeyError, StopIteration, UnknownVocabulary, ValueError) as exc:
        return Reconstruction(tid, cell, None, stored, None,
                              f"{type(exc).__name__}: {exc}")

    try:
        spec = TrialSpec(trial_id=tid, scenario_id=scenario_id, renderer=renderer,
                         elements=elements, task=task,
                         policy_scheme=scheme, policy_direction=direction,
                         meta={k: v for k, v in trial.items()
                               if k not in ("messages", "spans", "_file")},
                         conflict_groups=groups, tool_scenarios=tool_scenarios,
                         options_in_play=in_play)
    except (ValueError, UnknownVocabulary) as exc:
        return Reconstruction(tid, cell, None, stored, None,
                              f"{type(exc).__name__}: {exc}")

    try:
        rendered = render_dicts(spec, scenarios)
    except (RenderError, UnknownVocabulary) as exc:
        return Reconstruction(tid, cell, spec, stored, None, str(exc))
    return Reconstruction(tid, cell, spec, stored, rendered)


def reconstruct_all() -> list[Reconstruction]:
    scenarios = load_scenarios()
    headers = load_cell_headers()
    return [reconstruct(t, scenarios, headers.get(t.get("cell")))
            for t in load_trials()]
