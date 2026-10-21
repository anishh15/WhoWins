"""A chat completion, turned into something the checkers can score.
The join between an OpenAI-compatible envelope and `Response(text, tool_calls)`, and the
last place a run could quietly turn a model failure into a fake win. So it invents no
arguments, repairs nothing, and reports a fault rather than guessing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from ..checkers.core import Response, ToolCall


class MalformedCompletion(ValueError):
    """The envelope is not a chat completion at all.
    Distinct from a badly-behaved model: the transport returned something unreadable, which
    is our problem. Conflating the two would let an outage look like a refusal rate."""


@dataclass(frozen=True)
class Parsed:
    """A parsed completion, with everything that went wrong recorded beside it."""

    response: Response
    finish_reason: Optional[str] = None
    faults: tuple[str, ...] = ()
    """Non-fatal problems: arguments that would not parse, a call with no name.
    Carried into the run record so a low score can be traced to bad plumbing
    rather than assumed to be behaviour."""

    raw: Optional[Mapping[str, Any]] = field(default=None, repr=False)

    reasoning: str = ""
    """What this module split off as the model's thinking, where the server did
    not do it. Empty when the server's reasoning parser did, or when there was
    none: `reasoning_text` reads the server's field. No checker sees either."""

    @property
    def truncated(self) -> bool:
        """Hit the token limit mid-answer.
        Worth its own name: a truncated answer is a censored measurement, not a choice, and the
        plan requires truncations to be logged rather than scored as ordinary failures."""
        return self.finish_reason == "length"


def _arguments(raw: Any, faults: list[str], index: int) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
        except (ValueError, TypeError):
            faults.append(f"tool_call[{index}]: arguments are not JSON: {raw[:80]!r}")
            return {}
        if isinstance(loaded, Mapping):
            return dict(loaded)
        faults.append(
            f"tool_call[{index}]: arguments parsed to {type(loaded).__name__}, "
            f"not an object"
        )
        return {}
    faults.append(f"tool_call[{index}]: arguments are {type(raw).__name__}")
    return {}


UNSEPARATED_MARKERS = ("<think>", "</think>", "<|channel|>", "<|message|>",
                       "<|start|>", "<|end|>", "<|return|>", "<|call|>")
"""Text only a reasoning parser or a harmony parser should ever see.

In a reply's content they mean nothing separated the model's reasoning from its
answer: a thinking reply left "...</think>" in `content`, or a harmony reply
that was never parsed still carries its channel tokens. Where the environment
says the server splits, that is the server's failure; where it says this module
splits, these are what is left *after* the split, which is a second `</think>`
or a marker in an answer that should hold none. Either way the text being scored
may not be the answer, so the attempt carries a fault and is not counted as
behaviour."""


THINK_START, THINK_END = "<think>", "</think>"


def split_reasoning(text: str, *, prompt_opened: bool = False) -> tuple[str, str, list[str]]:
    """Thinking off the front of a reply the server did not split.
    For the engine with no reasoning parser. Two shapes, because the templates differ: a
    Qwen 3.5 prompt ends with `<think>` already open so only the closing tag arrives, while
    a Qwen 3 prompt prefills nothing. Which one applies is a recorded fact, not a guess."""
    faults: list[str] = []
    if THINK_END not in text:
        if prompt_opened or text.lstrip().startswith(THINK_START):
            return "", text, [
                "the reply never closed its reasoning block, so it holds no answer "
                "to score: it reached the token limit while thinking"
            ]
        return text, "", faults
    head, _, tail = text.partition(THINK_END)
    reasoning = head.partition(THINK_START)[2] if THINK_START in head else head
    answer = tail.lstrip("\n")
    if "<tool_call>" in reasoning:
        faults.append(
            "the reasoning holds a <tool_call> tag: the server's tool parser reads "
            "the whole reply, so a call the model only considered may have been "
            "recorded as one it made"
        )
    return answer, reasoning, faults


def reasoning_text(payload: Mapping[str, Any], choice: int = 0) -> str:
    """What the server's parser filed as reasoning, or "" when nothing.
    vLLM 0.28.0 calls the field `reasoning` and earlier versions `reasoning_content`; both
    are read. Kept out of `Response` on purpose -- no checker reads reasoning, because the
    answer is what the model gave, not what it considered."""
    try:
        message = payload["choices"][choice]["message"]
    except (KeyError, IndexError, TypeError):
        return ""
    if not isinstance(message, Mapping):
        return ""
    value = message.get("reasoning") or message.get("reasoning_content") or ""
    return value if isinstance(value, str) else ""


def parse_completion(payload: Mapping[str, Any], choice: int = 0, *,
                     reasoning_separation: str = "server",
                     thinking: Optional[bool] = None,
                     prompt_opened_thinking: bool = False) -> Parsed:
    """One chat completion -> a `Response` the checkers can score.
    `reasoning_separation` says who was meant to split thinking from the answer. With
    "server" a surviving reasoning marker is a fault, because the parser that should have
    removed it did not; with "client" this module splits it, and a survivor is still a fault."""
    choices = payload.get("choices")
    if not isinstance(choices, Sequence) or len(choices) <= choice:
        raise MalformedCompletion(
            f"no choice {choice} in the completion (got "
            f"{len(choices) if isinstance(choices, Sequence) else 'none'})"
        )
    item = choices[choice]
    message = item.get("message")
    if not isinstance(message, Mapping):
        raise MalformedCompletion("choice has no message object")

    faults: list[str] = []
    text = message.get("content") or ""
    if not isinstance(text, str):
        faults.append(f"content is {type(text).__name__}, not a string")
        text = ""
    reasoning = ""
    if reasoning_separation == "client" and thinking:
        text, reasoning, split_faults = split_reasoning(
            text, prompt_opened=prompt_opened_thinking)
        faults.extend(split_faults)
    leaked = [marker for marker in UNSEPARATED_MARKERS if marker in text]
    if leaked:
        faults.append(
            f"content carries {leaked}: the server did not separate reasoning "
            f"from the answer, so the text scored may not be the answer"
        )

    calls: list[ToolCall] = []
    for i, call in enumerate(message.get("tool_calls") or []):
        fn = call.get("function") if isinstance(call, Mapping) else None
        if not isinstance(fn, Mapping):
            faults.append(f"tool_call[{i}]: no function object")
            continue
        name = fn.get("name")
        if not isinstance(name, str) or not name:
            faults.append(f"tool_call[{i}]: no name")
            name = ""
        calls.append(ToolCall(name, _arguments(fn.get("arguments"), faults, i)))

    return Parsed(
        response=Response(text=text, tool_calls=tuple(calls)),
        finish_reason=item.get("finish_reason"),
        faults=tuple(faults),
        raw=payload,
        reasoning=reasoning,
    )


def completion_from(text: str = "", tool_calls: Sequence[Mapping[str, Any]] = (),
                    finish_reason: str = "stop") -> dict:
    """Build a completion envelope. For tests and for the offline backend.

    Here rather than in the tests so that what the parser is exercised against
    is the same shape the parser claims to accept."""
    return {
        "choices": [{
            "finish_reason": finish_reason,
            "message": {
                "role": "assistant",
                "content": text,
                "tool_calls": [
                    {
                        "id": f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": c["name"],
                            "arguments": json.dumps(c.get("arguments", {})),
                        },
                    }
                    for i, c in enumerate(tool_calls)
                ],
            },
        }],
    }
