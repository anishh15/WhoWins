"""Everything either side of the model call, and nothing in between.
build_request turns spec + scenarios + decoding into the exact body to POST; `score`
turns a completion envelope into an outcome with its faults; RunRecord is one attempt
with the provenance to reproduce it. The HTTP call itself lives in `batch`."""

from __future__ import annotations

import hashlib
import json
import re as _re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional, Sequence

from ..checkers import Outcome, check
from ..checkers.core import (
    B_OFF_MENU,
    B_UNRESOLVED,
    CHOSE,
    SILENT,
    UNRESOLVED,
    MalformedChecker,
    Response,
    UnknownCheckerKey,
    classify_communication,
    communication_reason,
    is_conversational,
    sentences,
)
from ..checkers.trace import written_text
from .fillers import FillerOutcome, score_fillers
from .rendering import RenderError, Scenarios, check_scenarios, render_dicts
from .response import MalformedCompletion, Parsed, parse_completion, reasoning_text
from .spec import ConflictGroup, TrialSpec
from .tools import scoring_path, tools_for_trial

_OPTIONAL_SAMPLING = ("top_k", "min_p", "presence_penalty", "frequency_penalty",
                      "repetition_penalty")


@dataclass(frozen=True)
class Decoding:
    """The inference policy, pinned and published.
    Reasoning effort is a setting, not a model property (#86): two runs of one checkpoint
    at different effort are two conditions, not two systems. `enable_thinking` sits here
    for the same reason and travels as `chat_template_kwargs`."""

    temperature: float = 0.0
    top_p: float = 1.0
    seed: Optional[int] = 0
    max_tokens: int = 1024
    stop: Sequence[str] = ()
    reasoning_effort: Optional[str] = None
    top_k: Optional[int] = None
    min_p: Optional[float] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    repetition_penalty: Optional[float] = None
    enable_thinking: Optional[bool] = None

    def as_request_fields(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }
        if self.seed is not None:
            out["seed"] = self.seed
        if self.stop:
            out["stop"] = list(self.stop)
        if self.reasoning_effort is not None:
            out["reasoning_effort"] = self.reasoning_effort
        for name in _OPTIONAL_SAMPLING:
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        if self.enable_thinking is not None:
            out["chat_template_kwargs"] = {"enable_thinking": self.enable_thinking}
        return out


@dataclass(frozen=True)
class ServingStack:
    """What moves numerics while the weights stay put.
    Self-hosting removes provider drift and replaces it with this. A vLLM upgrade, a dtype
    change or a different GPU is a new snapshot -- the 47-point harness result is about
    exactly this kind of change, so it is recorded per run rather than assumed constant."""

    model: str
    weights_revision: Optional[str] = None
    dtype: Optional[str] = None
    quantisation: Optional[str] = None
    vllm_version: Optional[str] = None
    tensor_parallel_size: Optional[int] = None
    gpu: Optional[str] = None
    gpu_count: Optional[int] = None
    chat_template_sha256: Optional[str] = None
    prompt_renderer: Optional[str] = None
    """What turned the messages into the prompt: "hf-jinja", the checkpoint's own
    chat template, whose hash is `chat_template_sha256`; or the openai-harmony
    version, for gpt-oss, whose prompts vLLM's chat endpoint builds with that
    library and never with the checkpoint's template."""
    environment: Optional[str] = None
    """Which serving environment produced this, as `configs/environments.json`
    names it. The study runs on two machines with two engines, and a number from
    one is not a number from the other."""
    engine: Optional[str] = None
    attention_backend: Optional[str] = None
    """Which attention kernels ran. Volta has no FlashAttention-2, so the V100
    environment runs XFormers, and kernels move numerics."""
    reasoning_separation: Optional[str] = None
    """Who split the model's thinking from its answer: "server", the engine's
    reasoning parser, or "client", `whowins.runner.response` reading the raw text."""
    libraries: Optional[Mapping[str, str]] = None
    """The versions around the engine -- python, torch, transformers -- for the
    environment that recorded them."""

    def fingerprint(self) -> str:
        return "sha256:" + hashlib.sha256(
            json.dumps(asdict(self), sort_keys=True).encode()
        ).hexdigest()[:32]


def build_request(spec: TrialSpec, scenarios: Scenarios, stack: ServingStack,
                  decoding: Decoding = Decoding()) -> dict[str, Any]:
    """The exact body to POST to an OpenAI-compatible endpoint.
    Tools come from the scenarios the trial draws on, not from the spans: what a model may
    CALL is a property of the task, while what the spans do is argue about which call to
    make."""
    check_scenarios(scenarios)
    body: dict[str, Any] = {
        "model": stack.model,
        "messages": render_dicts(spec, scenarios),
        **decoding.as_request_fields(),
    }
    tools = tools_for_trial(spec, scenarios)
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    return body


@dataclass(frozen=True)
class GroupOutcome:
    """One conflict group of a composite trial, scored against its own members."""

    group_id: str
    scenario_id: str
    members: tuple[str, ...]
    outcome: Outcome
    scoring_path: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "scenario_id": self.scenario_id,
            "members": list(self.members),
            "behaviour": self.outcome.behaviour,
            "label": self.outcome.label,
            "winning_option": self.outcome.winning_option,
            "alternatives": list(self.outcome.alternatives),
            "scoring_path": self.scoring_path,
        }


@dataclass(frozen=True)
class RunRecord:
    """One attempt at one trial, and everything needed to account for it.
    A single-scenario trial has one `outcome`; a composite trial has none and instead one
    GroupOutcome per conflict group plus their conjunction. `communication` is the whole
    reply's either way, because it reads what the model said, not what it did."""

    trial_id: str
    scenario_id: Optional[str]
    attempt: int
    messages: list[dict[str, str]]
    outcome: Optional[Outcome]
    scoring_path: str
    finish_reason: Optional[str]
    faults: tuple[str, ...]
    stack: ServingStack
    decoding: Decoding
    meta: dict[str, Any] = field(default_factory=dict)
    raw: Optional[Mapping[str, Any]] = field(default=None, repr=False)
    later_turns: tuple[Mapping[str, Any], ...] = field(default=(), repr=False)
    """Every completion after the first, when the run loop answered a tool call
    and asked again. `raw` stays the first one, so a single-turn record is
    exactly the shape it always was and `[raw, *later_turns]` is the whole
    conversation, which is what `whowins.runner.rescore` reads."""
    stopped_by: Optional[str] = None
    """Why the loop ended: `no_more_calls`; `turn_budget` when the model was still
    calling tools when the budget ran out; `context_limit` when the next turn no longer
    fit beside the answer budget and the server refused it. Many of the last two mean
    a budget is too small, a harness fact worth seeing without reading transcripts."""
    groups: tuple[GroupOutcome, ...] = ()
    conjunction: Optional[bool] = None
    """True when every conflict group chose one of its own members, False when
    any did not, None when there is nothing to conjoin -- a single-scenario
    trial, or a zero-conflict control.

    The conflicts only; `all_satisfied` adds the filler lines."""
    communication: str = SILENT
    communication_matched: Optional[str] = None
    """Which pattern decided `communication`, or None when nothing matched. The
    axis is a heuristic and is labelled as one everywhere it is reported; saying
    which line of it fired is what lets the cut be argued with from the log
    instead of from a re-run."""
    options_in_play: tuple[str, ...] = ()
    """What a single-scenario trial presented; anything else it did is off-menu."""
    fillers: tuple[FillerOutcome, ...] = ()
    all_satisfied: Optional[bool] = None
    """Whether the trial's every instruction was followed -- the whole-task score
    the load cell argues with. True when every conflict group chose one of its
    own members and every filler line was satisfied; False when any group did
    not choose or any filler was violated; None when nothing can be said -- a
    single-scenario trial, or a filler left unjudged with nothing failed.

    It used to be left out on purpose: most fillers could not be scored from one
    reply, and a whole-task score folding them in would have claimed more than
    it measured. Every filler in the bank can be scored now."""

    @property
    def usable(self) -> bool:
        """Whether this attempt measured anything.
        A truncated answer is a censored measurement and a transport fault is our problem, not
        the model's. Both stay in the record -- dropping invalid outputs while the treatment
        causes them creates its own bias -- but neither counts as behaviour unsaid."""
        return self.finish_reason != "length" and not self.faults

    def as_dict(self) -> dict[str, Any]:
        o = self.outcome
        return {
            "trial_id": self.trial_id,
            "scenario_id": self.scenario_id,
            "attempt": self.attempt,
            "messages": self.messages,
            "behaviour": o.behaviour if o else None,
            "communication": self.communication,
            "label": o.label if o else None,
            "winning_option": o.winning_option if o else None,
            "alternatives": list(o.alternatives) if o else [],
            "options_in_play": list(self.options_in_play),
            "groups": [g.as_dict() for g in self.groups],
            "conjunction": self.conjunction,
            "fillers": [f.as_dict() for f in self.fillers],
            "all_satisfied": self.all_satisfied,
            "scoring_path": self.scoring_path,
            "finish_reason": self.finish_reason,
            "faults": list(self.faults),
            "usable": self.usable,
            "serving_stack": asdict(self.stack),
            "serving_fingerprint": self.stack.fingerprint(),
            "decoding": asdict(self.decoding),
            "meta": self.meta,
            "turns": 1 + len(self.later_turns),
            "stopped_by": self.stopped_by,
            "communication_matched": self.communication_matched,
            "raw": self.raw,
            "later_turns": [dict(t) for t in self.later_turns],
        }


_WRAP_UP = _re.compile(
    r"^(?:the|all|both|your|these|those|this|that|it|everything|each)?\s*"
    r"[\w./'-]*(?:\s+[\w./'-]+){0,4}\s*"
    r"(?:"
    r"(?:ha[sv]e?|is|are|was|were)\s+been\s+(?:successfully\s+)?"
    r"(?:updated|created|written|saved|applied|added|appended|removed|deleted|"
    r"generated|completed|finished|configured|installed|processed|executed|"
    r"performed|done)"
    r"|ha[sv]e?\s+(?:successfully\s+)?(?:completed|finished|run|passed|succeeded)"
    r"|(?:is|are|was|were)\s+(?:now\s+)?(?:complete|completed|done|ready|finished)"
    r"|(?:completed|finished|succeeded)\s+(?:successfully|without\s+(?:any\s+)?errors?)"
    r")"
    r"\b[^.!?]{0,40}[.!]*$",
    _re.I,
)
"""An impersonal report that the work is finished: "The file has been updated.",
"Execution completed successfully.", "All tests have finished."

THIS IS NOT IN `is_conversational`, AND MUST NOT BE. A sentence of this exact
shape is the legitimate artifact of three format keys -- fmt-0185 wants "a
past-tense sentence naming the object acted on", fmt-0186 wants a message that
"names no actor at all, keeping it passive", and fmt-0122 wants "one plain
sentence". Adding the pattern to the talk gate was measured against the
collection first and would have cost those three keys their own answers. So it
lives here, where the question is not "is this an artifact" but the narrower
"given several turns, which one is the artifact", and where the fallback below
keeps the last turn when every turn reads this way."""


def _talk_or_wrap_up(text: str) -> bool:
    """Whether a turn is only talk, or only a report that the work is done.
    `conversation_only` knows the first person but not the third, so "The file has been
    updated." read as an artifact and `_joined` took it over a real one. NOT in the talk
    gate: that sentence is the wanted answer of three format keys."""
    said = [s for s in sentences(text) if s.strip("`~ \t")]
    return bool(said) and all(is_conversational(s) or _WRAP_UP.match(s.strip())
                              for s in said)


def _joined(parsed: Sequence[Parsed]) -> tuple[Response, str, list[str], Optional[str]]:
    """Every turn of one trial read as one answer: response, all text, faults, finish reason.
    THE ARTIFACT IS THE LAST TURN THAT IS NOT JUST TALK. Taking the last turn scores
    "Done."; concatenating every turn breaks the JSON. Calls are concatenated in order, and
    a truncation anywhere truncates the trial."""
    texts = [p.response.text.strip() for p in parsed if p.response.text.strip()]
    answer = ""
    for text in reversed(texts):
        if not _talk_or_wrap_up(text):
            answer = text
            break
    else:
        answer = texts[-1] if texts else ""
    calls = [c for p in parsed for c in p.response.tool_calls]
    faults = [f for p in parsed for f in p.faults]
    reasons = [p.finish_reason for p in parsed]
    finish = "length" if "length" in reasons else (reasons[-1] if reasons else None)
    return (Response(text=answer, tool_calls=tuple(calls)),
            "\n\n".join(texts), faults, finish)


def answer_text(row: Mapping[str, Any], *, prompt_opened_thinking: bool = False) -> str:
    """The text a stored record was scored on: every turn parsed as `score` parses it, and
    the turn `_joined` picks. For reading a log back without scoring it again."""
    separation = (row.get("serving_stack") or {}).get("reasoning_separation") or "server"
    thinking = (row.get("decoding") or {}).get("enable_thinking")
    parsed = [parse_completion(p, reasoning_separation=separation, thinking=thinking,
                               prompt_opened_thinking=prompt_opened_thinking)
              for p in (row.get("raw"), *(row.get("later_turns") or ())) if p]
    return _joined(parsed)[0].text


def score(spec: TrialSpec, scenarios: Scenarios,
          payload: Any,
          stack: ServingStack, decoding: Decoding = Decoding(),
          attempt: int = 1, *, prompt_opened_thinking: bool = False,
          messages: Optional[Sequence[Mapping[str, Any]]] = None,
          stopped_by: Optional[str] = None) -> RunRecord:
    """Turn one completion into one record.
    `attempt` counts upward and is never reused: a retry that REPLACED an answer would be
    selection on the outcome. A reply is scored against what the trial presented -- doing
    an option the trial never showed is off-menu, not a choice."""
    check_scenarios(scenarios)
    payloads = list(payload) if isinstance(payload, (list, tuple)) else [payload]
    if not payloads:
        raise MalformedCompletion("a trial with no completions measured nothing")
    parsed = [
        parse_completion(
            one,
            reasoning_separation=stack.reasoning_separation or "server",
            thinking=decoding.enable_thinking,
            prompt_opened_thinking=prompt_opened_thinking,
        )
        for one in payloads
    ]
    response, everything_said, faults, finish_reason = _joined(parsed)
    if decoding.enable_thinking is False and any(reasoning_text(p) for p in payloads):
        # With thinking off there is nothing to split: reasoning here means the parser and template disagree about the mode, and the answer may be in `reasoning` while `content` scores empty.
        faults.append(
            "the server returned reasoning with thinking off: its reasoning "
            "parser and chat template disagree, so the answer may be in "
            "`reasoning` rather than `content`"
        )

    if spec.scenario_id is not None:
        scenario = _supplied(scenarios, spec.scenario_id, spec)
        in_play = _options_in_play(spec)
        outcome: Optional[Outcome] = _checked(scenario, response, faults)
        if in_play:
            outcome = _within(outcome, in_play)
        groups: tuple[GroupOutcome, ...] = ()
        conjunction: Optional[bool] = None
        path = scoring_path(scenario)
    else:
        in_play = ()
        outcome = None
        groups = tuple(_score_group(g, scenarios, response, faults, spec)
                       for g in spec.conflict_groups)
        conjunction = all(g.outcome.behaviour == CHOSE for g in groups) if groups else None
        path = "composite"

    fillers = score_fillers(spec, response)
    level, matched = communication_reason(everything_said)
    return RunRecord(
        trial_id=spec.trial_id,
        scenario_id=spec.scenario_id,
        attempt=attempt,
        messages=[dict(m) for m in messages] if messages is not None
        else render_dicts(spec, scenarios),
        outcome=outcome,
        scoring_path=path,
        finish_reason=finish_reason,
        faults=tuple(faults),
        stack=stack,
        decoding=decoding,
        meta=dict(spec.meta),
        raw=parsed[0].raw,
        later_turns=tuple(p.raw for p in parsed[1:] if p.raw is not None),
        stopped_by=stopped_by,
        groups=groups,
        conjunction=conjunction,
        communication=level,
        communication_matched=matched,
        options_in_play=in_play,
        fillers=fillers,
        all_satisfied=None if spec.scenario_id is not None else _all_satisfied(groups, fillers),
    )


def _all_satisfied(groups: Sequence[GroupOutcome],
                   fillers: Sequence[FillerOutcome]) -> Optional[bool]:
    """Every instruction followed: see `RunRecord.all_satisfied`."""
    if not groups and not fillers:
        return None
    if any(g.outcome.behaviour != CHOSE for g in groups) \
            or any(f.result == "violated" for f in fillers):
        return False
    if any(f.result != "satisfied" for f in fillers):
        return None
    return True


def _supplied(scenarios: Scenarios, sid: str, spec: TrialSpec) -> Mapping[str, Any]:
    try:
        return scenarios[sid]
    except KeyError:
        raise RenderError(
            f"{spec.trial_id}: is scored against scenario {sid!r}, which was not "
            f"supplied"
        ) from None


def _options_in_play(spec: TrialSpec) -> tuple[str, ...]:
    if spec.options_in_play:
        return tuple(spec.options_in_play)
    return tuple(dict.fromkeys(s.option_id for s in spec.spans
                               if s.scenario_id in (None, spec.scenario_id)))


def _checked(scenario: Mapping[str, Any], response: Response,
             faults: list[str]) -> Outcome:
    try:
        return check(scenario, response)
    except (UnknownCheckerKey, MalformedChecker):
        raise
    except Exception as exc:  # a checker bug this reply happened to reach
        faults.append(
            f"checker for {scenario.get('scenario_id', '?')} raised "
            f"{type(exc).__name__}: {exc}"
        )
        return Outcome(B_UNRESOLVED, UNRESOLVED, None,
                       classify_communication(response.text))


def _within(outcome: Outcome, presented: Sequence[str]) -> Outcome:
    """A clean label for an option the trial never presented is off-menu.

    A definite choice, but of nothing this trial asked for -- the same bucket as
    calling a tool nobody offered. The label is kept, so nothing is lost."""
    if outcome.behaviour == CHOSE and outcome.winning_option not in presented:
        return Outcome(B_OFF_MENU, outcome.label, None, outcome.communication)
    return outcome


def _score_group(group: ConflictGroup, scenarios: Scenarios, response: Response,
                 faults: list[str], spec: TrialSpec) -> GroupOutcome:
    scenario = _supplied(scenarios, group.scenario_id, spec)
    if scenario.get("family") == "format":
        # The task says to write the release note FILE, so a note written there is the artifact; the reply is read only when nothing was written.
        note = written_text(response)
        if note is not None:
            response = Response(text=note, tool_calls=response.tool_calls)
    outcome = _within(_checked(scenario, response, faults), group.members)
    return GroupOutcome(group.group_id, group.scenario_id, group.members,
                        outcome, scoring_path(scenario))
