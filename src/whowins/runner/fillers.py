"""The load cell's filler lines: written down, and every one scored.
The cell pads its instruction list with fillers so length stays matched while the number
of conflicts varies. They are scored too, because an unscored line in the prompt is an
instruction the model may have followed with nothing recording whether it did."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

from ..checkers.core import Response, sentences
from ..checkers.trace import _is_write, writes, written_text
from .spec import Block, TrialSpec

_DURATION = re.compile(
    r"\b\d+(?:[.,]\d+)?[ \t]*(?:ms|milliseconds?|s|secs?|seconds?|mins?|minutes?|h|hrs?|hours?)\b",
    re.I,
)
_PROJECT = "atlas-core"
"""The project every worked load trial's task names."""

Check = Callable[[Response], Optional[bool]]


def _replied(r: Response) -> bool:
    return bool((r.text or "").strip()) or bool(r.tool_calls)


def _note(r: Response) -> str:
    return written_text(r) or (r.text or "")


def _everything_written(r: Response) -> str:
    return (r.text or "") + "\n" + (written_text(r) or "")


def _sentences_under(text: str, limit: int) -> Optional[bool]:
    said = [s for s in sentences(text) if s.strip()]
    if not said:
        return None
    return all(len(s.split()) < limit for s in said)


# --- What a filler can ask, each a builder so a bundle names its own project and tools ---


def reply_words_under(limit: int) -> Check:
    def check(r: Response) -> Optional[bool]:
        if not _replied(r):
            return None
        return len((r.text or "").split()) < limit
    return check


def no_section(in_path: str, heading: str) -> Check:
    """Broken by a write whose destination contains `in_path`, or a heading matching the
    pattern `heading` anywhere written."""
    def check(r: Response) -> Optional[bool]:
        if not _replied(r):
            return None
        if any(dest and in_path in dest.lower() for dest, _ in writes(r)):
            return False
        written = [r.text or ""] + [body for _, body in writes(r) if body]
        return not any(re.search(r"^[ \t]*#{1,6}[ \t]*" + heading + r"\b", w, re.I | re.M)
                       for w in written)
    return check


def elapsed_time_at_the_end() -> Check:
    """The reply's last line states a duration in figures."""
    def check(r: Response) -> Optional[bool]:
        if not _replied(r):
            return None
        lines = [ln for ln in (r.text or "").splitlines() if ln.strip()]
        return bool(lines) and bool(_DURATION.search(lines[-1]))
    return check


def mentions(project: str) -> Check:
    """The project named in the reply or the artifact."""
    def check(r: Response) -> Optional[bool]:
        if not _replied(r):
            return None
        return project in _everything_written(r).lower()
    return check


def reply_mentions(project: str) -> Check:
    """The project named in the reply itself; an artifact written to a file is not it."""
    def check(r: Response) -> Optional[bool]:
        if not _replied(r):
            return None
        return project in (r.text or "").lower()
    return check


def step_before_writing(is_step: Callable[[str], bool]) -> Check:
    """A step tool is called before the first write. Nothing written, nothing to judge:
    the order of a step and a write needs both halves."""
    def check(r: Response) -> Optional[bool]:
        calls = list(r.tool_calls)
        first_write = next((i for i, c in enumerate(calls) if _is_write(c)), None)
        if first_write is None:
            return None
        return any(is_step(c.name) for c in calls[:first_write])
    return check


def artifact_in_a_file() -> Check:
    """Some write carried the artifact's text."""
    def check(r: Response) -> Optional[bool]:
        if not _replied(r):
            return None
        return written_text(r) is not None
    return check


def artifact_named_after(project: str) -> Check:
    """The first write's file name carries the project. No write, nothing to judge."""
    def check(r: Response) -> Optional[bool]:
        destinations = [dest for dest, _ in writes(r) if dest]
        if not destinations:
            return None
        return project in os.path.basename(destinations[0].rstrip("/")).lower()
    return check


def artifact_lines_under(limit: int) -> Check:
    def check(r: Response) -> Optional[bool]:
        lines = [ln for ln in _note(r).splitlines() if ln.strip()]
        if not lines:
            return None
        return len(lines) < limit
    return check


def every_sentence_under(limit: int) -> Check:
    """Every sentence of the reply and the artifact."""
    def check(r: Response) -> Optional[bool]:
        if not _replied(r):
            return None
        return _sentences_under(_everything_written(r), limit)
    return check


def artifact_sentences_under(limit: int) -> Check:
    """Every sentence of the artifact only."""
    def check(r: Response) -> Optional[bool]:
        return _sentences_under(_note(r), limit)
    return check


def names_the_step_tool(is_step: Callable[[str], bool]) -> Check:
    """The reply spells out the name of a step tool it called. None called, nothing to judge."""
    def check(r: Response) -> Optional[bool]:
        ran = [c.name for c in r.tool_calls if is_step(c.name)]
        if not ran:
            return None
        return any(name in (r.text or "") for name in ran)
    return check


def _is_check(name: str) -> bool:
    return name.startswith("check_")


@dataclass(frozen=True)
class Filler:
    filler_id: str
    text: str
    check: Optional[Check] = None
    unscorable_because: Optional[str] = None


BANK: tuple[Filler, ...] = (
    Filler("F1", "Keep the reply under two hundred words.", reply_words_under(200)),
    Filler("F5", "Skip the changelog entry for this run.",
           no_section("changelog", r"change[ \t-]?log")),
    Filler("F8", "Report the elapsed time at the end.", elapsed_time_at_the_end()),
    Filler("F13", "Mention atlas-core.", mentions(_PROJECT)),
    Filler("F14", "Check before you write.", step_before_writing(_is_check)),
    Filler("F15", "Keep every sentence under forty words.", every_sentence_under(40)),
    Filler("F16", "Write the release note into a file.", artifact_in_a_file()),
    Filler("F17", "Name the note file after atlas-core.", artifact_named_after(_PROJECT)),
    Filler("F18", "Keep the release note under ten lines.", artifact_lines_under(10)),
    Filler("F19", "Keep every sentence in the release note under forty words.",
           artifact_sentences_under(40)),
    Filler("F20", "Mention atlas-core by name somewhere in your reply.",
           reply_mentions(_PROJECT)),
    Filler("F21", "Run the check before writing the note.", step_before_writing(_is_check)),
    Filler("F22", "Name the check tool you ran.", names_the_step_tool(_is_check)),
    Filler("F23", "Run the repository check before you write the release note.",
           step_before_writing(_is_check)),
)
"""The worked bundle's bank, in id order. F2 and F6 were never in any trial; F3, F4, F7,
F9, F10, F11 and F12 were retired on 2026-09-11, for the reasons above."""

BY_TEXT: dict[str, Filler] = {f.text: f for f in BANK}


# --- A bundle's own bank, from the kinds data/LOAD-AUTHORING.md lets an author choose ---

KINDS: dict[str, tuple[Optional[type], str]] = {
    "reply_words_under": (int, "the reply has fewer than `value` words"),
    "no_section": (str, "no write whose destination contains `value`, and no markdown heading "
                        "that is `value` anywhere written"),
    "elapsed_time_at_the_end": (None, "the reply's last line states a duration in figures"),
    "mentions_project": (None, "the project is named in the reply or the artifact"),
    "reply_mentions_project": (None, "the project is named in the reply itself"),
    "step_before_writing": (None, "one of the bundle's step tools is called before the first write"),
    "artifact_in_a_file": (None, "some write carries the artifact's text"),
    "artifact_named_after_project": (None, "the first write's file name contains the project"),
    "artifact_lines_under": (int, "the artifact has fewer than `value` non-empty lines"),
    "every_sentence_under": (int, "every sentence of the reply and the artifact has fewer than "
                                  "`value` words"),
    "artifact_sentences_under": (int, "every sentence of the artifact has fewer than `value` words"),
    "names_the_step_tool": (None, "the reply spells out the name of a step tool it called"),
}
"""kind -> (the type of its `value`, or None when it takes none; what the checker reads)."""


def build_check(kind: str, value: Any, project: str, steps: Sequence[str]) -> Check:
    """The checker for one bundle filler. `steps` are the bundle's step tools."""
    is_step = frozenset(steps).__contains__
    builders: dict[str, Callable[[], Check]] = {
        "reply_words_under": lambda: reply_words_under(value),
        "no_section": lambda: no_section(value.lower(), re.escape(value)),
        "elapsed_time_at_the_end": elapsed_time_at_the_end,
        "mentions_project": lambda: mentions(project),
        "reply_mentions_project": lambda: reply_mentions(project),
        "step_before_writing": lambda: step_before_writing(is_step),
        "artifact_in_a_file": artifact_in_a_file,
        "artifact_named_after_project": lambda: artifact_named_after(project),
        "artifact_lines_under": lambda: artifact_lines_under(value),
        "every_sentence_under": lambda: every_sentence_under(value),
        "artifact_sentences_under": lambda: artifact_sentences_under(value),
        "names_the_step_tool": lambda: names_the_step_tool(is_step),
    }
    return builders[kind]()


@dataclass(frozen=True)
class FillerOutcome:
    """One filler line of one trial, and what the reply did about it."""

    filler_id: Optional[str]
    text: str
    result: str
    """satisfied, violated, no_answer, or unscorable."""
    reason: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {"filler_id": self.filler_id, "text": self.text,
                "result": self.result, "reason": self.reason}


def _bank_for(spec: TrialSpec) -> Mapping[str, Filler]:
    """The worked bank, or the bank of the bundle the trial belongs to."""
    bundle = (spec.meta or {}).get("bundle") if hasattr(spec, "meta") else None
    if not bundle:
        return BY_TEXT
    from .bundles import bank
    return bank(bundle)


def score_fillers(spec: TrialSpec, response: Response) -> tuple[FillerOutcome, ...]:
    """Every filler line the trial shows, in order, scored where it can be.
    A line the bank does not know, or one it holds without a checker, is reported as
    unscorable rather than guessed at."""
    by_text = _bank_for(spec)
    out: list[FillerOutcome] = []
    for el in spec.elements:
        if not isinstance(el, Block):
            continue
        for item in el.items:
            if not isinstance(item, str) or not item.strip():
                continue
            filler = by_text.get(item)
            if filler is None:
                out.append(FillerOutcome(None, item, "unscorable", "not in the filler bank"))
            elif filler.check is None:
                out.append(FillerOutcome(filler.filler_id, item, "unscorable",
                                         filler.unscorable_because))
            else:
                verdict = filler.check(response)
                result = "no_answer" if verdict is None else \
                    "satisfied" if verdict else "violated"
                out.append(FillerOutcome(filler.filler_id, item, result))
    return tuple(out)
