"""Helpers for building format classifiers.
Every format classifier maps output text to exactly one label. These helpers exist so
the ORDERING of the tests -- which is the exclusivity argument -- is written as data
rather than buried in control flow."""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping, Optional, Sequence

from ..core import (
    UNRESOLVED,
    conversation_only,
    drop_restated_instructions,
    register,
    sentences,
)

Predicate = Callable[[str], bool]
Rule = tuple[str, Predicate]

SPEC_LABELS: dict[str, tuple[str, ...]] = {}
"""key -> the labels its classifier can emit, in test order.

Recorded so the suite can assert that a classifier's label set is exactly the
value set the collection declares for that key -- a classifier that can emit a label
no option asks for, or that cannot emit one an option does ask for, is broken
whatever its fixtures say.
"""


def vocab(words: str) -> frozenset[str]:
    """A closed word list, written as one space-separated string."""
    return frozenset(words.split())


TOKEN_START = r"(?<![^\s`'\"*(\[{<|,;:=>])"
"""Where a token may begin: at the start, after whitespace, or after the markup
a model wraps an artifact in.

`(?<!\\S)` is the obvious way to write "starts a token" and it is wrong here,
because a backtick is not whitespace. The first run showed it: the 1.7B answered
fmt-0030 with "The agent's configuration file is located at `/etc/agent/config`."
and `path_style` returned UNRESOLVED, because the `/` was preceded by a backtick.
The same reply without the backticks scored `absolute_posix`. Inline code, bold
markers, quotes, brackets and table pipes are how models present exactly the
short artifacts this family asks for, so none of them may end a token boundary.

Deliberately NOT in the set: word characters, `.`, `~`, `\\` and `-`. Each one
can be part of a token, and admitting it would let a rule match inside another
form -- `../etc` would read as an absolute POSIX path, `~/etc` as one too.
"""


def rx(pattern: str, flags: int = 0) -> Predicate:
    """A predicate that searches `pattern` anywhere in the string."""
    c = re.compile(pattern, flags)
    return lambda s: bool(c.search(s))


def fullrx(pattern: str, flags: int = 0) -> Predicate:
    """A predicate that requires `pattern` to match the whole string."""
    c = re.compile(pattern, flags)
    return lambda s: bool(c.fullmatch(s.strip()))


def ordered(*rules: Rule) -> Callable[[str], str]:
    """First rule whose predicate matches the text wins.
    A predicate that raises is NOT read as "no match": catching the exception and trying the
    next rule hands the win to whichever label happens to be tested after the broken one."""

    def classify(text: str) -> str:
        for label, pred in rules:
            if pred(text):
                return label
        return UNRESOLVED

    return classify


def uniform(
    extract: Callable[[str], Sequence[str]], *rules: Rule
) -> Callable[[str], str]:
    """Every token that carries evidence must agree on one label.
    Tokens no rule can classify are silence, not disagreement -- `{"id": ...}` matches none
    of the five casing patterns, and treating that as a mixture sank replies that were
    perfectly uniform. At least one token must still carry evidence."""
    per_token = ordered(*rules)

    def classify(text: str) -> str:
        toks = [t for t in extract(text) if t and t.strip()]
        if not toks:
            return UNRESOLVED
        labels = {per_token(t) for t in toks} - {UNRESOLVED}
        if len(labels) == 1:
            return labels.pop()
        return UNRESOLVED

    return classify


READS_PROSE: frozenset[str] = frozenset({
    # A message or instructions to a person, where the artifact itself may open "I" or "Please".
    "relative_date_wording", "cli_error_message_style", "filename_in_prose",
    # Artifacts that are questions by design.
    "heading_phrasing", "review_remark_convention",
})
"""Keys exempt from the conversation-only test in `artifact_text`.

For these a reply of nothing but conversational sentences can be the artifact,
so that test cannot tell a non-answer from an answer and does not try; their
own classifiers must. Three more keys sat here -- confirmation_wording,
error_voice_and_person and salutation_style -- until their scenarios were
rewritten so that no option can be satisfied by talk (fmt-0185, fmt-0186,
fmt-0203, 2026-09-11). Anything left exposed is pinned by name in the suite."""

_FENCE_LINE = re.compile(r"^[ \t]*(?:```|~~~)[^\n]*$", re.M)
_INLINE_LEAD_IN = re.compile(
    r"\A\s*(?:(?:sure|certainly|of course)\b[^:\n]*|"
    r"(?:here(?:'s|’s| is| are| it is| you go)|below (?:is|are))\b[^:\n]*):[ \t]",
    re.I,
)


def artifact_text(key: str, text: str, scenario: Mapping[str, Any]) -> Optional[str]:
    """The reply as a classifier should see it, or None when it carries no artifact.
    Four steps before any classifier reads a word: drop sentences quoting the scenario's own
    instructions, strip framing, take the answer part, and return None if what is left is
    only talk. A reply that only talks wins nothing."""
    text = drop_restated_instructions(text, scenario)
    text = _INLINE_LEAD_IN.sub("", text, count=1)
    if text.strip() and not _FENCE_LINE.sub("", text).strip():
        return None
    if key in READS_PROSE:
        # Even a message key has no artifact when the reply is only framing: a lead-in promising content that never came, or a placeholder.
        if _framing_only(text):
            return None
    elif conversation_only(text):
        return None
    return text


_PLACEHOLDER = re.compile(r"^(?:n/?a|tbd|tbc|todo)[.!]?$", re.I)


def _framing_only(text: str) -> bool:
    said = [s.replace("’", "'") for s in sentences(text) if s.strip("`~ \t")]
    return bool(said) and all(
        _LEAD_IN.match(s) or _SIGN_OFF.match(s) or _PLACEHOLDER.match(s) for s in said
    )


def text_checker(key: str, fn: Callable[[str], str]) -> None:
    """Register a text-only classifier under `key`, reading `artifact_text`."""
    def run(response, scenario):
        text = artifact_text(key, response.text or "", scenario)
        return UNRESOLVED if text is None else fn(text)

    register(key, run)


def spec(key: str, *rules: Rule) -> None:
    """Register an `ordered` classifier. The common case."""
    SPEC_LABELS[key] = tuple(label for label, _ in rules)
    text_checker(key, ordered(*rules))


def uniform_spec(
    key: str, extract: Callable[[str], Sequence[str]], *rules: Rule
) -> None:
    """Register a `uniform` classifier."""
    SPEC_LABELS[key] = tuple(label for label, _ in rules)
    text_checker(key, uniform(extract, *rules))


def fn_spec(key: str, labels: Sequence[str], fn: Callable[[str], str]) -> None:
    """Register a hand-written classifier, declaring the labels it can emit."""
    SPEC_LABELS[key] = tuple(labels)
    text_checker(key, fn)


# --- Extractors -- pulling the tokens a rule set is meant to judge ---

_JSON_KEY = re.compile(r'"([^"\\]{1,80})"\s*:')
_YAML_KEY = re.compile(r"^\s*([A-Za-z_][\w\-]{0,79})\s*:(?:\s|$)", re.M)
_CSV_SPLIT = re.compile(r"[,\t|;]")


def field_names(text: str) -> list[str]:
    """Field/key names from JSON, YAML, or a delimited header row.
    Tries JSON keys first, then YAML, then the first line as a header, stopping at the first
    source that yields anything."""
    keys = _JSON_KEY.findall(text)
    if keys:
        return keys
    keys = _YAML_KEY.findall(text)
    if keys:
        return keys
    for line in text.strip().splitlines():
        line = line.strip().strip("|").strip()
        if not line:
            continue
        parts = [p.strip() for p in _CSV_SPLIT.split(line) if p.strip()]
        if len(parts) >= 2:
            return parts
        return [line]
    return []


def first_body(text: str) -> str:
    """The output proper: fenced block contents if present, else the whole text."""
    m = re.search(r"(?:```|~~~)[^\n]*\n(.*?)(?:```|~~~)", text, re.S)
    return m.group(1) if m else text


_LEAD_IN = re.compile(
    r"^(?:sure|certainly|of course|absolutely|okay|ok|great|"
    r"here(?:'s| is| are| you go| it is)|below (?:is|are))\b[^\n]*:$",
    re.I,
)
_SIGN_OFF = re.compile(
    r"^(?:let me know|i hope this helps|hope this helps|feel free to|"
    r"happy to (?:help|adjust|change|revise|tweak)|if you(?:'d| would)? like me to|"
    r"would you like me to|want me to|i can also|is there anything else)\b",
    re.I,
)


def unwrap(text: str) -> str:
    """The artifact without the framing a model puts around it.
    A lead-in, a code fence, a closing offer -- none is what an option asked for, and a
    classifier reading them scores the framing instead of the answer."""
    m = re.search(r"(?:```|~~~)[^\n]*\n(.*?)(?:```|~~~)", text, re.S)
    body = m.group(1) if m else text
    lines = body.splitlines()
    first = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    framed = False
    if first is not None and first + 1 < len(lines) \
            and _LEAD_IN.match(lines[first].strip().replace("’", "'")):
        lines, framed = lines[first + 1:], True
    paras = re.split(r"\n[ \t]*\n", "\n".join(lines).strip())
    while len(paras) > 1 and _SIGN_OFF.match(paras[-1].strip().replace("’", "'")):
        paras.pop()
        framed = True
    return "\n\n".join(paras) if framed else body


# --- Relevance gates: require positive evidence that the artifact is present, never evidence that a marker is absent. Ten classifiers failed the other way ---

_SENTENCE_END = re.compile(r"[.!?]['\"’”)]?\s*$")

COMMON_WORDS = frozenset("""
a an and are as at be been but by can cant could did do does doing done dont
for from get got had has have he her here hers him his how i if in into is it
its just let like make may me more most much must my no not now of off on one
only or other our out over own said same see she should so some such than that
the their them then there these they this those through to too under up us use
used very was way we were what when where which while who why will with would
you your sorry enough information help thing things need needs want wants
""".split())
"""Frequent English words. A short lowercase run that is one of these is prose,
not an acronym written in lower case."""


def looks_like_sentence(text: str) -> bool:
    """Prose: several words ending in sentence punctuation."""
    t = text.strip()
    return len(t.split()) >= 3 and bool(_SENTENCE_END.search(t))


def first_line(text: str) -> str:
    return next((ln for ln in text.splitlines() if ln.strip()), "")


def short_fields(line: str, sep: str, max_words: int = 4) -> list[str]:
    """Split `line` on `sep`, returning fields only if they look like a delimited row.
    At least two, none longer than `max_words`. A sentence containing a comma splits into
    fields too, but one of them runs on."""
    parts = [p.strip() for p in re.split(sep, line) if p.strip()]
    if len(parts) < 2:
        return []
    if any(len(p.split()) > max_words for p in parts):
        return []
    return parts
