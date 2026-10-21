"""Editorial, natural-language and locale axes -- fmt-0161..0210.
The recurring hazard is ABBREVIATION NESTING: `M` is inside `Mo` is inside `Mon`, so the
longest form is tested first and every short form must match as a standalone token."""

from __future__ import annotations

import re

from ..core import UNRESOLVED
from ._lib import fn_spec, looks_like_sentence, rx, spec, unwrap

_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]


def _abbrev_length(text: str, words: list[str], labels: dict[int, str]) -> str:
    """Which abbreviation length was used, by exact token length.
    `labels` maps token length to label; 0 means the full word. Longest first, and each short
    form matches only as a standalone token so `M` cannot match inside `Mon`."""
    if any(re.search(rf"\b{w}\b", text) for w in words):
        return labels.get(0, UNRESOLVED)
    for n in sorted((k for k in labels if k), reverse=True):
        stems = {w[:n] for w in words}
        # A standalone token of exactly n letters, optionally followed by a dot.
        if any(re.search(rf"(?<![A-Za-z]){re.escape(s)}\.?(?![A-Za-z])", text)
               for s in stems):
            return labels[n]
    return UNRESOLVED


# fmt-0033 weekday_encoding ------------------------------------------------


def _weekday(text: str) -> str:
    hit = _abbrev_length(
        text, _DAYS, {0: "full_name", 3: "three_letter", 2: "two_letter", 1: "single_letter"}
    )
    if hit != UNRESOLVED:
        return hit
    return "iso_number" if re.search(r"(?<![\d.])[1-7](?![\d.])", text) else UNRESOLVED


fn_spec(
    "weekday_encoding",
    ["full_name", "three_letter", "two_letter", "single_letter", "iso_number"],
    _weekday,
)

# fmt-0176 month_in_prose --------------------------------------------------


def _month_in_prose(text: str) -> str:
    if any(re.search(rf"\b{m}\b", text) for m in _MONTHS):
        # `mixed_by_length` spells short month names and abbreviates long ones, so a full name AND a three-letter form together is that policy.
        if re.search(r"(?<![A-Za-z])(?:Jan|Feb|Aug|Sept?|Oct|Nov|Dec)\.?(?![A-Za-z])", text):
            return "mixed_by_length"
        return "full_name"
    stems = {m[:3] for m in _MONTHS}
    if any(re.search(rf"(?<![A-Za-z]){s}\.(?![A-Za-z])", text) for s in stems):
        return "three_letter_period"
    if any(re.search(rf"(?<![A-Za-z]){s.upper()}(?![A-Za-z])", text) for s in stems):
        return "three_letter_caps"
    if any(re.search(rf"(?<![A-Za-z]){s}(?![A-Za-z.])", text) for s in stems):
        return "three_letter"
    return UNRESOLVED


fn_spec(
    "month_in_prose",
    ["full_name", "three_letter", "three_letter_period", "three_letter_caps", "mixed_by_length"],
    _month_in_prose,
)

# --- fmt-0161 spelling_variant_policy: four cells of a 2x2, so a text showing only one axis is UNRESOLVED rather than a guess ---

_OUR = r"\b\w+(?:our)\b"          # colour, behaviour
_OR = r"\b(?:col|behavi|hon|lab|flav|neighb)or\b"
_ISE = r"\b\w+is(?:e|ed|es|ing|ation)\b"
_IZE = r"\b\w+iz(?:e|ed|es|ing|ation)\b"


def _spelling(text: str) -> str:
    our, or_ = bool(re.search(_OUR, text, re.I)), bool(re.search(_OR, text, re.I))
    ise, ize = bool(re.search(_ISE, text, re.I)), bool(re.search(_IZE, text, re.I))
    if not (our or or_) and not (ise or ize):
        # `variants_avoided` is an ABSENCE label: an empty response contains no variants either, so crediting deliberate avoidance needs enough prose for the choice to have arisen.
        if len(re.findall(r"[A-Za-z]{2,}", text)) < 30:
            return UNRESOLVED
        return "variants_avoided"
    if our and ise and not ize:
        return "our_ise"
    if or_ and ize and not ise:
        return "or_ize"
    if our and ize and not ise:
        return "our_ize"
    if or_ and ise and not ize:
        return "or_ise"
    return UNRESOLVED


fn_spec(
    "spelling_variant_policy",
    ["our_ise", "or_ize", "our_ize", "or_ise", "variants_avoided"],
    _spelling,
)

# --- fmt-0162 heading_capitalisation: headings are read rather than whatever line comes first, and all must agree. Start case is granted only when a capitalised article or preposition proves it, since a heading of major words alone satisfies both rules ---

_MINOR_WORDS = frozenset({"a", "an", "and", "as", "at", "but", "by", "for", "in", "of",
                          "on", "or", "the", "to", "up", "via", "with", "from", "into"})
_MARKDOWN_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+(.+?)[ \t#]*$", re.M)


def _one_heading(line: str) -> str:
    line = line.strip().lstrip("#").strip()
    # A heading does not end in sentence punctuation and is not a paragraph, or "I can't help with that." is one.
    if looks_like_sentence(line) or len(line.split()) > 12:
        return UNRESOLVED
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]*", line)]
    if len(words) < 2:
        return UNRESOLVED
    if all(w.isupper() for w in words):
        return "all_capitals"
    if all(w.islower() for w in words):
        return "all_lowercase"
    caps = [w[0].isupper() for w in words]
    if all(caps):
        if any(w.lower() in _MINOR_WORDS for w in words[1:]):
            return "start_case"
        return UNRESOLVED
    if caps[0] and all(
        c or w.lower() in _MINOR_WORDS for c, w in zip(caps[1:], words[1:], strict=False)
    ) and any(not c for c in caps[1:]):
        return "headline_title_case"
    if caps[0] and not any(caps[1:]):
        return "sentence_case"
    return UNRESOLVED


def _heading_cap(text: str) -> str:
    body = unwrap(text)
    headings = _MARKDOWN_HEADING.findall(body) or \
        [next((ln for ln in body.splitlines() if ln.strip()), "")]
    # A heading too short or too plain to decide carries no evidence either way.
    labels = {_one_heading(h) for h in headings} - {UNRESOLVED}
    return labels.pop() if len(labels) == 1 else UNRESOLVED


fn_spec(
    "heading_capitalisation",
    ["sentence_case", "headline_title_case", "start_case", "all_lowercase", "all_capitals"],
    _heading_cap,
)

# fmt-0167 quotation_mark_style --------------------------------------------

spec(
    "quotation_mark_style",
    ("guillemets", rx(r"[«»‹›]")),
    ("double_outer", rx(r"[\"“][^\"“”\n]+[\"”]")),
    ("single_outer", rx(r"[‘'][^'‘’\n]+[’']")),
    ("italic_no_marks", rx(r"\*[^*\n]+\*|(?<!\w)_[^_\n]+_(?!\w)")),
    ("indented_unmarked", rx(r"^(?: {4,}|\t|>\s)\S", re.M)),
)

# fmt-0168 initials_punctuation --------------------------------------------

spec(
    "initials_punctuation",
    ("period_and_space", rx(r"\b[A-Z]\.\s+[A-Z]\.\s+[A-Z][a-z]")),
    ("period_no_space", rx(r"\b[A-Z]\.[A-Z]\.\s*[A-Z][a-z]")),
    ("spaced_no_periods", rx(r"\b[A-Z]\s+[A-Z]\s+[A-Z][a-z]")),
    ("closed_no_periods", rx(r"\b[A-Z]{2}\s+[A-Z][a-z]")),
    ("names_spelled_out", rx(r"\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}")),
)

# fmt-0169 honorific_style -------------------------------------------------

_TITLES = r"Mr|Mrs|Ms|Dr|Prof|Sir|Rev|Hon"

spec(
    "honorific_style",
    ("spelled_in_full", rx(r"\b(?:Doctor|Professor|Mister|Reverend|Honourable)\s+[A-Z]")),
    ("postnominal_letters", rx(r"[A-Z][a-z]+,\s*(?:[A-Z]{2,5}\.?)(?:,\s*[A-Z]{2,5}\.?)*\b")),
    ("abbreviated_with_period", rx(rf"\b(?:{_TITLES})\.\s+[A-Z]")),
    ("abbreviated_no_period", rx(rf"\b(?:{_TITLES})\s+[A-Z][a-z]")),
    ("no_title_plain_name", rx(r"^\s*[A-Z][a-z]+\s+[A-Z][a-z]+\s*$", re.M)),
)

# fmt-0178 temperature_scale -----------------------------------------------

spec(
    "temperature_scale",
    ("celsius_then_fahrenheit", rx(r"-?\d+(?:\.\d+)?\s*°?C\b.{0,12}-?\d+(?:\.\d+)?\s*°?F\b")),
    ("kelvin_no_symbol", rx(r"\b\d+(?:\.\d+)?\s*K\b")),
    ("fahrenheit_symbol", rx(r"-?\d+(?:\.\d+)?\s*°\s*F\b")),
    ("celsius_symbol", rx(r"-?\d+(?:\.\d+)?\s*°\s*C\b")),
    ("bare_number_scale_in_heading", rx(r"^[^\n]*\(\s*°?\s*[CFK]\s*\)", re.M)),
)

# fmt-0182 rating_display --------------------------------------------------

spec(
    "rating_display",
    ("star_glyphs", rx(r"[★☆⭐]")),
    ("fraction_of_five", rx(r"\b\d(?:\.\d)?\s*/\s*5\b")),
    ("percentage", rx(r"\b\d{1,3}\s*%")),
    ("word_band", rx(r"\b(?:excellent|good|average|fair|poor|outstanding)\b", re.I)),
    ("bare_decimal", rx(r"(?<![\d./])\d\.\d(?![\d/%])")),
)

# fmt-0197 fraction_in_prose -----------------------------------------------

spec(
    "fraction_in_prose",
    ("single_glyph", rx(r"[½¼¾⅓⅔⅛]")),
    ("percentage", rx(r"\b\d{1,3}(?:\.\d+)?\s*%")),
    ("slash_digits", rx(r"(?<![\d/])\d{1,2}\s*/\s*\d{1,2}(?![\d/])")),
    ("decimal_two_places", rx(r"(?<![\d.])0?\.\d{2}(?![\d])")),
    ("words", rx(r"\b(?:a |one[- ])?(?:half|third|quarter|two[- ]thirds|three[- ]quarters)\b", re.I)),
)

# --- fmt-0201 percent_in_prose: `per cent` before `percent`, because the spelled-out form contains the one-word spelling ---

spec(
    "percent_in_prose",
    ("number_and_word_spelled", rx(r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|"
                                   r"eleven|twelve|twenty|thirty|forty|fifty)\s+per\s?cent\b", re.I)),
    ("two_words_per_cent", rx(r"\d\s*per cent\b", re.I)),
    ("one_word_percent", rx(r"\d\s*percent\b", re.I)),
    ("symbol_spaced", rx(r"\d\s+%")),
    ("symbol_tight", rx(r"\d%")),
)

# fmt-0204 section_numbering -----------------------------------------------

spec(
    "section_numbering",
    ("multilevel_decimal_trailing_period", rx(r"^\s*\d+(?:\.\d+)+\.\s+\S", re.M)),
    ("multilevel_decimal", rx(r"^\s*\d+(?:\.\d+)+\s+\S", re.M)),
    ("roman_then_arabic", rx(r"^\s*(?:I|II|III|IV|V|VI|VII|VIII|IX|X)\.\s+\S", re.M)),
    ("top_level_only", rx(r"^\s*\d+\.?\s+\S", re.M)),
    # `unnumbered` is the absence of numbering, so it needs at least two heading lines, none of them a sentence.
    ("unnumbered", lambda s: len([
        ln for ln in s.splitlines()
        if ln.strip() and not looks_like_sentence(ln) and
           (re.match(r"^\s*#{1,6}\s+\S", ln) or re.match(r"^\s*[A-Z][^\n\d]{3,}$", ln.rstrip()))
    ]) >= 2),
)
