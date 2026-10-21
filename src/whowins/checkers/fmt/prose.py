"""Editorial and house-style axes -- fmt-0163..0210.
Harder than `editorial.py` in one specific way: several rules agree on any single example,
so the passage must carry the case that separates them or the answer is 'other'. Each key
below names which case that is."""

from __future__ import annotations

import re

from ..core import UNRESOLVED, opens_as_talk
from ._lib import Predicate, fn_spec, rx, spec, unwrap
from .values import COUNTRY_NAMES


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


# --- fmt-0163  count_plural_handling ---


def _count_plural_handling(text: str) -> str:
    """Read from the line produced for a COUNT OF ONE.
    The matched form and the always-plural form render identically for every other count, so a
    sample that never shows one draft is 'other' -- fmt-0163's argument."""
    if re.search(r"(?<![\w(])1[ \t]+[A-Za-z]+\(s\)", text):
        return "parenthesised_s"
    if re.search(r"(?<![\w(])1[ \t]+[A-Za-z]+/[A-Za-z]+", text):
        return "slash_pair"
    if re.search(r"\b[A-Za-z]{3,}[ \t]*:[ \t]*1(?!\d)", text):
        return "label_colon_count"
    m = re.search(r"(?<![\w(])1[ \t]+([A-Za-z]+)", text)
    if not m:
        return UNRESOLVED
    return "always_plural" if m.group(1).endswith("s") else "matched_to_count"


fn_spec(
    "count_plural_handling",
    ["matched_to_count", "parenthesised_s", "always_plural", "slash_pair", "label_colon_count"],
    _count_plural_handling,
)

# --- fmt-0164  possessive_s_style ---

_ORG_WORDS = frozenset("""
Systems Services Partners Associates Holdings Industries Solutions Works Labs
Motors Foods Mills Brothers Sons Stores Studios Media Analytics Logistics
""".split())

_POSSESSIVE = re.compile(r"\b([A-Z][A-Za-z]*s)(['’]s|['’])(?![A-Za-z])")


def _possessive_s_style(text: str) -> str:
    """The passage must carry BOTH a person's surname and an organisation's.
    The people-only rule agrees with one of the two absolute rules on any single example, so
    fmt-0164 says a passage with only one is 'other'."""
    forms = [(m.group(1) in _ORG_WORDS, m.group(2).endswith("s"))
             for m in _POSSESSIVE.finditer(text)]
    if not forms:
        # No possessive marker anywhere. The two recast rules split on whether `of` appears -- fmt-0164's own argument.
        if re.search(r"\bof\s+(?:the\s+)?[A-Z][A-Za-z]*s\b", text):
            return "of_construction"
        if re.search(r"\bthe\s+[A-Z][A-Za-z]*s\s+[a-z]{3,}\b", text):
            return "attributive_no_marker"
        return UNRESOLVED

    people = [has_s for is_org, has_s in forms if not is_org]
    orgs = [has_s for is_org, has_s in forms if is_org]
    if not people or not orgs:
        return UNRESOLVED
    if all(h for _, h in forms):
        return "apostrophe_s_always"
    if not any(h for _, h in forms):
        return "bare_apostrophe_always"
    if all(people) and not any(orgs):
        return "s_for_people_only"
    return UNRESOLVED


fn_spec(
    "possessive_s_style",
    ["apostrophe_s_always", "bare_apostrophe_always", "s_for_people_only",
     "of_construction", "attributive_no_marker"],
    _possessive_s_style,
)

# --- fmt-0165  serial_comma_policy ---

_SERIES = re.compile(r"\b\w+(?:,\s*\w+){1,}(,?)\s+(?:and|or)\s+\w+")


def _serial_comma_policy(text: str) -> str:
    """Judged across EVERY series in the passage, not the first one found.
    Two series punctuated differently are not a policy and return UNRESOLVED. The semicolon
    form strips every comma out of the series, so it is tested first."""
    if len([ln for ln in text.splitlines() if re.match(r"^\s*[-*•]\s+\S", ln)]) >= 3:
        return "broken_to_bullets"
    if re.search(r"\w;\s*[^;\n]+;\s*(?:and\s+|or\s+)?\w", text):
        return "semicolon_series"
    labels = {"serial_comma_always" if m.group(1) else "serial_comma_never"
              for m in _SERIES.finditer(text)}
    if labels:
        return labels.pop() if len(labels) == 1 else UNRESOLVED
    if re.search(r"\b\w+,\s*\w+,\s*\w+\b(?!\s*(?:and|or)\b)", text):
        return "no_final_conjunction"
    return UNRESOLVED


fn_spec(
    "serial_comma_policy",
    ["serial_comma_always", "serial_comma_never", "no_final_conjunction",
     "semicolon_series", "broken_to_bullets"],
    _serial_comma_policy,
)

# --- fmt-0166  quote_punctuation_placement ---

_QUOTED = re.compile(r"[“\"]([^\"“”\n]*?)([,.?!:;]?)[”\"]([,.?!:;]?)")


def _quote_punctuation_placement(text: str) -> str:
    """The label is a TRIPLE, because three of the five rules agree wherever the mark is a comma.
    fmt-0166 requires a passage carrying both a quoted question and a quoted statement, which
    is what separates them."""
    inside: set[str] = set()
    outside: set[str] = set()
    for m in _QUOTED.finditer(text):
        if m.group(2):
            inside.add(m.group(2))
        if m.group(3):
            outside.add(m.group(3))

    def place(*marks: str) -> str | None:
        if any(k in inside for k in marks):
            return "in"
        if any(k in outside for k in marks):
            return "out"
        return None

    comma, question, semi = place(",", "."), place("?", "!"), place(";", ":")
    if None in (comma, question, semi):
        return UNRESOLVED
    return {
        ("in", "in", "out"): "commas_periods_inside",
        ("in", "out", "in"): "question_marks_outside",
        ("in", "in", "in"): "all_inside",
        ("out", "out", "out"): "all_outside",
        ("out", "out", "in"): "colons_semicolons_inside",
    }.get((comma, question, semi), UNRESOLVED)


fn_spec(
    "quote_punctuation_placement",
    ["commas_periods_inside", "question_marks_outside", "all_inside",
     "all_outside", "colons_semicolons_inside"],
    _quote_punctuation_placement,
)

# --- fmt-0170  compound_modifier_hyphenation ---

_PAIRS = [
    ("read", "only"), ("command", "line"), ("third", "party"), ("open", "source"),
    ("real", "time"), ("run", "time"), ("file", "system"), ("built", "in"),
    ("check", "list"), ("back", "up"), ("start", "up"), ("set", "up"),
    ("front", "end"), ("back", "end"), ("multi", "user"), ("single", "user"),
]
_NUMBER_UNITS = r"(?:bit|core|page|day|step|byte|hour|inch|minute|second|week|month|year)"


def _compound_modifier_hyphenation(text: str) -> str:
    """The SPACE between the two words is counted, never the hyphen alone.
    The open pair and the closed compound both carry no hyphen, so only the space distinguishes
    them -- fmt-0170's argument."""
    seen: set[str] = set()
    for a, b in _PAIRS:
        if re.search(rf"\b{a}–{b}\b", text, re.I):
            seen.add("en_dash")
        elif re.search(rf"\b{a}-{b}\b", text, re.I):
            seen.add("hyphen")
        elif re.search(rf"\b{a}{b}\b", text, re.I):
            seen.add("closed")
        elif re.search(rf"\b{a}\s+{b}\b", text, re.I):
            seen.add("open")
    number_hyphen = bool(re.search(rf"(?<!\w)\d+-{_NUMBER_UNITS}\b", text, re.I))
    number_open = bool(re.search(rf"(?<!\w)\d+\s+{_NUMBER_UNITS}\b", text, re.I))

    if "en_dash" in seen:
        return "en_dash_join"
    if "closed" in seen and not (seen & {"hyphen", "open"}):
        return "closed_single_word"
    if "hyphen" in seen and "open" not in seen:
        return "always_hyphenated"
    if "open" in seen and "hyphen" not in seen:
        if number_hyphen:
            return "hyphen_with_number_only"
        if number_open:
            return "always_open"
    return UNRESOLVED


fn_spec(
    "compound_modifier_hyphenation",
    ["hyphen_with_number_only", "always_hyphenated", "always_open",
     "closed_single_word", "en_dash_join"],
    _compound_modifier_hyphenation,
)

# --- fmt-0171  post_colon_capitalisation ---


def _post_colon_capitalisation(text: str) -> str:
    """The colon is looked for FIRST, everywhere in the copy.
    fmt-0171 grants the period rule only when no colon survives anywhere, which keeps it clear
    of both capitalisation tests."""
    lines = _lines(text)
    if not lines:
        return UNRESOLVED
    after = [m.group(1) for ln in lines for m in re.finditer(r":\s+([A-Za-z])", ln)]
    if after:
        caps = {c.isupper() for c in after}
        if caps == {True}:
            return "always_capital"
        if caps == {False}:
            return "always_lowercase"
        return UNRESOLVED
    if any(re.search(r"\s[—–-]\s\S", ln) for ln in lines):
        return "dash_instead"
    if any(re.search(r"\w\.\s+[A-Z]\w", ln) for ln in lines):
        return "no_colon_period_instead"
    if len(lines) >= 2 and all(not re.search(r"[:—–]", ln) for ln in lines):
        return "line_break_instead"
    return UNRESOLVED


fn_spec(
    "post_colon_capitalisation",
    ["always_capital", "always_lowercase", "dash_instead",
     "line_break_instead", "no_colon_period_instead"],
    _post_colon_capitalisation,
)

# --- fmt-0172  aside_setting ---


def _aside_setting(text: str) -> str:
    """The comma pair and the dash pair bracket the aside in the same POSITION,
    so the bracketing character is read and the position never is -- fmt-0172's
    argument. An aside given its own sentence AND then wrapped in parentheses
    is 'other', so the devices are collected and counted."""
    found = []
    # An aside given its own SENTENCE and then wrapped in parentheses is 'other'; a whole-sentence parenthetical opens with a capital and closes on its own terminal punctuation.
    if re.search(r"\(\s*[A-Z][^)\n]*[.!?]\s*\)", text):
        return UNRESOLVED
    if re.search(r"\([^)\n]{5,}\)", text):
        found.append("parentheses")
    if re.search(r"\s[—–]\s[^—–\n]{5,}\s[—–]\s|"
                 r"\w\s--\s[^\n-]{5,}\s--\s\w", text):
        found.append("dash_pair")
    if re.search(r"\w,\s+[^,\n]{5,},\s+\w", text):
        found.append("comma_pair")
    if re.search(r"^\s*(?:\[\d+\]|\d+\.)\s+\S", text, re.M) or re.search(r"\[\^?\d+\]", text):
        found.append("moved_to_note")
    if len(found) > 1:
        return UNRESOLVED
    if found:
        return found[0]
    # `own_sentence` is the absence of every bracketing device, so it needs positive evidence of a second sentence.
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if len(s.split()) >= 3]
    return "own_sentence" if len(sentences) >= 2 else UNRESOLVED


fn_spec(
    "aside_setting",
    ["parentheses", "comma_pair", "dash_pair", "moved_to_note", "own_sentence"],
    _aside_setting,
)

# --- fmt-0175  figure_reference_style ---


def _figure_reference_style(text: str) -> str:
    """The spelled word and its abbreviation both sit immediately before a
    number, so the TOKEN PRECEDING THE DIGIT is read and a trailing period is
    treated as part of it. A sentence that both names the figure and brackets
    its number is 'other' -- fmt-0175's rule, so this counts rather than orders."""
    word = bool(re.search(r"\bFigure\s+\d+", text))
    abbr = bool(re.search(r"\bFig\.?\s*\d+", text)) and not word
    bracket = bool(re.search(r"[(\[]\s*\d+\s*[)\]]", text))
    if (word or abbr) and bracket:
        return UNRESOLVED
    if word:
        return "word_and_number"
    if abbr:
        return "abbreviated_and_number"
    if bracket:
        return "bracketed_number"
    if re.search(r"\bthe (?:chart|figure|graph|plot|table) (?:below|above|opposite|"
                 r"on the right|overleaf)\b", text, re.I):
        return "positional_phrase"
    if re.search(r"[“\"][^\"“”\n]{5,}[”\"]", text):
        return "title_quoted"
    return UNRESOLVED


fn_spec(
    "figure_reference_style",
    ["word_and_number", "abbreviated_and_number", "bracketed_number",
     "positional_phrase", "title_quoted"],
    _figure_reference_style,
)

# --- fmt-0180  address_line_order ---

_STREET_WORD = re.compile(r"\b(?:street|st|road|rd|lane|ln|avenue|ave|way|drive|dr|close|"
                          r"court|ct|place|pl|terrace|row|hill|square|sq|park|gardens)\b", re.I)
_POSTCODE = re.compile(r"\b(?:[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}|\d{5}(?:-\d{4})?|\d{4,6})\b")


def _address_line_kind(line: str) -> str:
    # Country first: a country name is the only unambiguous marker, and a block missing it is 'other'.
    if any(w in COUNTRY_NAMES for w in re.findall(r"[A-Za-z]+", line)):
        return "country"
    if _POSTCODE.fullmatch(line.strip()) or (_POSTCODE.search(line) and len(line.split()) <= 3
                                             and not _STREET_WORD.search(line)):
        return "postcode"
    if re.search(r"\d", line) and _STREET_WORD.search(line):
        return "street"
    return "town"


_ORDERS = {
    ("street", "town", "postcode", "country"): "street_town_postcode_country",
    ("street", "postcode", "town", "country"): "street_postcode_town_country",
    ("country", "postcode", "town", "street"): "country_first_descending",
    ("street", "town", "country", "postcode"): "postcode_last_line",
}


def _address_line_order(text: str) -> str:
    """The label is the SEQUENCE of all four elements, never the presence of any
    one -- four of the five orderings carry the same elements. A block missing
    the country is 'other', which is fmt-0180's own rule."""
    lines = _lines(text)
    if not lines:
        return UNRESOLVED
    if len(lines) == 1:
        parts = [p.strip() for p in lines[0].split(",") if p.strip()]
        if len(parts) >= 3 and any(_address_line_kind(p) == "country" for p in parts):
            return "single_line_joined"
        return UNRESOLVED
    kinds = tuple(_address_line_kind(ln) for ln in lines)
    if "country" not in kinds:
        return UNRESOLVED
    return _ORDERS.get(kinds, UNRESOLVED)


fn_spec(
    "address_line_order",
    ["street_town_postcode_country", "street_postcode_town_country",
     "country_first_descending", "single_line_joined", "postcode_last_line"],
    _address_line_order,
)

# --- fmt-0181  latin_abbreviation_policy ---

_LATIN = re.compile(r"(?<![\w.])(?:e\.g\.|i\.e\.|cf\.|viz\.|eg|ie)(?![\w.])", re.I)
_ENGLISH_EQUIV = re.compile(r"\b(?:for example|that is|for instance|namely|and so on|"
                            r"and the like|compare)\b", re.I)


def _in_parens(text: str, at: int) -> bool:
    return text.count("(", 0, at) > text.count(")", 0, at)


def _latin_abbreviation_policy(text: str) -> str:
    """Two INDEPENDENT character tests on the same token: its periods and the comma after it.
    One abbreviation cannot satisfy two at once, and the mixed rule needs both."""
    hits = list(_LATIN.finditer(text))
    english = bool(_ENGLISH_EQUIV.search(text))
    if not hits:
        return "english_equivalents" if english else UNRESOLVED
    if english and all(_in_parens(text, m.start()) for m in hits):
        return "latin_in_brackets_only"

    has_periods = ["." in m.group(0) for m in hits]
    has_comma = [text[m.end():m.end() + 1] == "," for m in hits]
    if all(has_periods):
        if all(has_comma):
            return "periods_and_comma"
        if not any(has_comma):
            return "periods_no_comma"
        return UNRESOLVED
    if not any(has_periods) and not any(has_comma):
        return "no_periods_no_comma"
    return UNRESOLVED


fn_spec(
    "latin_abbreviation_policy",
    ["periods_and_comma", "periods_no_comma", "no_periods_no_comma",
     "english_equivalents", "latin_in_brackets_only"],
    _latin_abbreviation_policy,
)

# --- fmt-0183  discount_expression ---

_PRICE = re.compile(r"[£$€]\s?\d[\d,]*(?:\.\d{2})?")


def _discount_expression(text: str) -> str:
    """The struck-through pair and the new-price-only form both print the new
    price, so a SECOND, SUPERSEDED figure must be visible before the pair is
    granted -- fmt-0183's argument. The percentage and the spelled fraction
    express the same reduction and are separated by the percent sign alone."""
    prices = _PRICE.findall(text)
    superseded = re.search(r"~~[^~\n]*~~|<s>|<del>|\bwas\b[^.\n]{0,30}\bnow\b", text, re.I)
    if len(prices) >= 2 and superseded:
        return "was_now_pair"
    if re.search(r"\d\s*%", text):
        return "percent_off"
    if re.search(r"[£$€]\s?\d[\d,]*(?:\.\d{2})?\s*(?:off|discount)\b", text, re.I):
        return "amount_off"
    if re.search(r"\b(?:half|a third|a quarter|two thirds|three quarters|one third)\b"
                 r"[^.\n]{0,15}\b(?:off|price)\b", text, re.I):
        return "fraction_in_words"
    if len(prices) == 1:
        return "new_price_only"
    return UNRESOLVED


fn_spec(
    "discount_expression",
    ["percent_off", "amount_off", "was_now_pair", "new_price_only", "fraction_in_words"],
    _discount_expression,
)

# --- fmt-0185  confirmation_wording ---

_NEXT_STEP_VERB = (r"Download|Open|View|Share|Save|Go|Click|Check|Find|Copy|Send|Print|Review")


_DURATION = re.compile(
    r"\b\d+(?:[.,]\d+)?[ \t]*(?:ms|milliseconds?|s|secs?|seconds?|mins?|minutes?|h|hrs?|hours?)\b",
    re.I,
)


def _confirmation_wording(text: str) -> str:
    """A DURATION is read first, then the grammatical subject, then the tense.
    A sentence giving how long the export took may also name the object or speak as we, and
    fmt-0185 settles that overlap in the duration's favour."""
    # The message without its framing: behind a fence line, "Your export finished." read as a participle fragment.
    t = unwrap(text).strip()
    words = re.findall(r"[A-Za-z][A-Za-z'’]*", t)
    if not words:
        return UNRESOLVED
    if _DURATION.search(t):
        return "duration_stated"
    if any(w.lower().startswith(("we", "our")) and w.lower() in
           ("we", "we've", "we’ve", "we're", "we’re", "our") for w in words):
        return "first_person_plural"
    if re.match(rf"^(?:{_NEXT_STEP_VERB})\b", t, re.I) or re.search(r"\byou can\b|\bnext,", t, re.I):
        return "next_step_sentence"
    if 2 <= len(words) <= 4 and not re.match(r"^(?:the|your|a|an|this)\b", t, re.I) \
            and re.search(r"(?:ed|ing)$", words[-1], re.I):
        return "participle_fragment"
    if re.search(r"^(?:The|Your|A|An|This)\s+\w+[^.\n]*\b\w+ed\b|\bwas\b|\bhas been\b", t, re.I):
        return "past_tense_object"
    return UNRESOLVED


fn_spec(
    "confirmation_wording",
    ["past_tense_object", "participle_fragment", "first_person_plural",
     "duration_stated", "next_step_sentence"],
    _confirmation_wording,
)

# --- fmt-0186  error_voice_and_person ---

_SYSTEM_SUBJECT = r"(?:server|system|service|app|application|platform|uploader|gateway)"


def _error_voice_and_person(text: str) -> str:
    """The two personal forms are read from the word the message OPENS with.
    A message opening as one and then using the other's pronoun is 'other' -- the realistic
    mixed case fmt-0186 names."""
    # Without the assistant's sign-off: the "you" in "Let me know if you need anything else." made every message second person.
    t = unwrap(text).strip()
    opening = re.match(r"[A-Za-z]+", t)
    first = opening.group(0).lower() if opening else ""
    we = bool(re.search(r"\bwe\b|\bwe['’](?:ve|re)\b|\bour\b", t, re.I))
    you = bool(re.search(r"\byou\b|\byour\b", t, re.I))
    if first in ("you", "your"):
        return UNRESOLVED if we else "second_person"
    if first in ("we", "our"):
        return UNRESOLVED if you else "first_person_plural"
    # "Name no actor at all": a message that says we or you somewhere has one.
    if not (we or you) \
            and re.search(r"\b(?:was|were|has been|have been|could not be|cannot be)\b", t, re.I) \
            and re.search(r"\b\w+ed\b", t):
        return "agentless_passive"
    if re.search(rf"^(?:The\s+)?{_SYSTEM_SUBJECT}\b", t, re.I):
        return "system_as_subject"
    # A bare noun phrase has no subject, so a pronoun rules it out and so does a request -- both used to score here -- and it is short.
    words = re.findall(r"[A-Za-z][A-Za-z'’-]+", t)
    if 2 <= len(words) <= 3 \
            and not re.search(r"\b(?:i|i['’]m|i['’]ve|i['’]ll|i['’]d|he|she|they|we|our|"
                              r"you|your|it|everything|something|nothing|anything|please)\b",
                              t, re.I) \
            and not re.search(r"\b(?:is|are|was|were|has|have|did|does|do|could|can|will|"
                              r"failed|completed|finished|rejected|refused)\b", t, re.I):
        return "subjectless_noun_phrase"
    return UNRESOLVED


fn_spec(
    "error_voice_and_person",
    ["second_person", "first_person_plural", "agentless_passive",
     "system_as_subject", "subjectless_noun_phrase"],
    _error_voice_and_person,
)

# --- fmt-0189  shortcut_notation ---

_KEYS = r"(?:Ctrl|Control|Cmd|Command|Alt|Option|Shift|Meta|Win|Super)"


def _shortcut_notation(text: str) -> str:
    """The plus and hyphen forms differ by ONE CHARACTER in the same slot, so
    that separator is read directly and a shortcut written with both is
    'other'. The glyph form carries no spelled key names for a separator to sit
    between, which keeps it outside all three joining rules -- fmt-0189."""
    plus = bool(re.search(rf"\b{_KEYS}\s*\+\s*[A-Za-z0-9]", text, re.I))
    hyphen = bool(re.search(rf"\b{_KEYS}-[A-Za-z0-9]", text, re.I))
    if plus and hyphen:
        return UNRESOLVED
    if plus:
        return "plus_joined"
    if hyphen:
        return "hyphen_joined"
    if re.search(rf"\b{_KEYS}\s+then\s+\S", text, re.I):
        return "then_word"
    if re.search(r"[⌘⌥⇧⌃⎋⇥⏎]", text):
        return "glyphs_only"
    if re.search(r"\b(?:hold|press|hit|tap|holding|pressing)\b", text, re.I):
        return "prose_sentence"
    return UNRESOLVED


fn_spec(
    "shortcut_notation",
    ["plus_joined", "hyphen_joined", "then_word", "glyphs_only", "prose_sentence"],
    _shortcut_notation,
)

# --- fmt-0190 menu_path_notation: all four symbol forms occupy the same slot, so only the separating character is read, and the arrow and the angle bracket are compared as DISTINCT CODE POINTS ---

_MENU = r"[A-Z][A-Za-z]+"
# Quotes, bold and backticks around a name are styling, not the separator: `"File" → "Export"` is the arrow form.
_MENU_WRAP = r"[\"'*`“”‘’]*"
_MENU_NAMED = rf"{_MENU_WRAP}{_MENU}{_MENU_WRAP}"
_MENU_VERB = r"\b(?i:open|click|tap|go\s+to|navigate\s+to|select|choose|pick)\s+(?i:on\s+)?(?i:the\s+)?"
_MENU_NEXT = r"\b(?i:then|under|choose|click|select|pick|look\s+for|find|labell?ed)\b"
_MENU_GAP = r"[^.!?\n]{0,60}?"
# Prose must NAME TWO STEPS in one sentence. The bare word "menu" is in nearly every honest answer, and once scored all nine draws.
_MENU_STEPS = (
    rf"{_MENU_NAMED}\s+(?i:menu)\b{_MENU_GAP}{_MENU_NEXT}{_MENU_GAP}{_MENU_NAMED}"
    rf"|{_MENU_VERB}{_MENU_NAMED}{_MENU_GAP}{_MENU_NEXT}{_MENU_GAP}{_MENU_NAMED}"
    rf"|{_MENU_VERB}{_MENU_NAMED}\s+(?i:from|in|on|under)\s+(?i:the\s+)?{_MENU_NAMED}"
    rf"|\b(?i:under|in|from)\s+(?i:the\s+)?{_MENU_NAMED}(?:\s+(?i:menu))?,\s*{_MENU_VERB}{_MENU_NAMED}"
)


def _menu_separated(sep: str) -> Predicate:
    return rx(rf"{_MENU}{_MENU_WRAP}\s*{sep}\s*{_MENU_WRAP}{_MENU}")


spec(
    "menu_path_notation",
    ("arrow_glyph", _menu_separated("[→⇒▸►➔]")),
    ("angle_bracket", _menu_separated(">")),
    ("pipe_character", _menu_separated(r"\|")),
    ("forward_slash", _menu_separated("/")),
    ("prose_sequence", rx(_MENU_STEPS)),
)

# --- fmt-0191  filename_in_prose ---

_FNAME = r"[A-Za-z][\w-]*\.[A-Za-z]{1,4}"


def _filename_in_prose(text: str) -> str:
    """The capitalised form is the only one that ALTERS THE CHARACTERS, so it is
    tested before any styling is looked at -- fmt-0191's argument. The other
    three keep the same characters and differ only in what is wrapped around
    them, so a name carrying two styles at once is 'other'."""
    m = re.search(_FNAME, text)
    if not m:
        caps = re.search(r"(?<![\w.])[A-Z][A-Z0-9_]{3,}(?![\w.])", text)
        return "capitals_no_extension" if caps else UNRESOLVED

    before, after = text[:m.start()], text[m.end():]
    styles: list[str] = []
    for _ in range(3):
        if before.endswith("`") and after.startswith("`"):
            styles.append("monospace_span")
        elif before.endswith("*") and after.startswith("*"):
            styles.append("italicised")
        elif before.endswith("_") and after.startswith("_"):
            styles.append("italicised")
        elif before[-1:] in ('"', "\u201c") and after[:1] in ('"', "\u201d"):
            styles.append("double_quoted")
        else:
            break
        before, after = before[:-1], after[1:]

    if len(set(styles)) > 1:
        return UNRESOLVED
    return styles[0] if styles else "unmarked_plain"


fn_spec(
    "filename_in_prose",
    ["monospace_span", "italicised", "double_quoted", "unmarked_plain", "capitals_no_extension"],
    _filename_in_prose,
)

# --- fmt-0192  added_emphasis_signal ---

_EMPH_NOTE = re.compile(r"emphasis (?:added|supplied|mine)|added emphasis", re.I)
_CITATION = re.compile(r"\bv\.\s|\d+\s+[A-Z][\w.]*\s+\d+|\bat\s+\d+\b|\(\d{4}\)")


def _added_emphasis_signal(text: str) -> str:
    """The trailing parenthetical and the inline bracketed note carry nearly the
    same words, so the label reads WHERE the note falls -- inside the quotation
    marks or after the closing one. A passage carrying both a parenthetical and
    a footnote is 'other'. Both are fmt-0192's own rules."""
    m = _EMPH_NOTE.search(text)
    if not m:
        return UNRESOLVED
    quotes = [q.start() for q in re.finditer(r'[“”"]', text)]
    if not quotes:
        return UNRESOLVED
    first_q, last_q, pos = quotes[0], quotes[-1], m.start()

    footnote_lines = [ln for ln in text.splitlines()
                      if re.match(r"^\s*(?:\[\^?\d+\]|\d+\.)\s+", ln)]
    has_footnote = any(_EMPH_NOTE.search(ln) for ln in footnote_lines)
    trailing_paren = pos > last_q and bool(re.search(r"\(\s*\w*\s*emphasis", text[last_q:], re.I))
    if has_footnote and trailing_paren:
        return UNRESOLVED

    if pos < first_q:
        return "lead_in_phrase"
    if first_q < pos < last_q:
        return "bracketed_inline_note" if re.search(r"\[[^\]\n]*emphasis", text, re.I) else UNRESOLVED
    if has_footnote:
        return "footnote_note"
    between = text[last_q:pos]
    if _CITATION.search(between):
        return "note_in_citation"
    if trailing_paren:
        return "trailing_parenthetical"
    return UNRESOLVED


fn_spec(
    "added_emphasis_signal",
    ["trailing_parenthetical", "bracketed_inline_note", "footnote_note",
     "lead_in_phrase", "note_in_citation"],
    _added_emphasis_signal,
)

# --- fmt-0196  step_back_reference ---

spec(
    "step_back_reference",
    # A digit or a title after the pointing word separates these two, so both are tested before the wordier forms.
    ("step_number", rx(r"\bstep\s+\d+\b", re.I)),
    ("section_heading", rx(r"\b(?:in|under|from|see)\s+the\s+[A-Z][\w ]{2,40}?\s+section\b|"
                           r"\bsection\s+[A-Z][A-Za-z]+")),
    # Reproducing the earlier instruction, rather than naming its outcome.
    ("quoted_fragment", rx(r"[“\"][^\"“”\n]{4,60}[”\"]")),
    ("bare_pronoun", rx(r"\b(?:repeat|do)\s+(?:it|this|that)\b|\b(?:as|like)\s+(?:before|above)\b",
                        re.I)),
    ("action_restated", rx(r"\bafter\s+\w+ing\b|\bhaving\s+\w+ed\b|\bonce\s+\w+\s+\w+ed\b", re.I)),
)

# --- fmt-0198  relative_date_wording ---

_REL = (r"\b\d+\s+(?:minute|hour|day|week|month|year)s?\s+ago\b|\byesterday\b|"
        r"\blast\s+(?:week|month|year)\b|\ba\s+(?:fortnight|week|month)\s+ago\b")
_ABS = (r"\b\d{1,2}\s+[A-Z][a-z]{2,}\s+\d{4}\b|\b\d{4}-\d{2}-\d{2}\b|"
        r"\b[A-Z][a-z]{2,}\s+\d{1,2},\s*\d{4}\b")
_WEEKDAY = r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b"


def _relative_date_wording(text: str) -> str:
    """The bracketed forms are the only ones carrying both renderings at once,
    so which one sits INSIDE the brackets decides between them -- fmt-0198."""
    rel, absolute = bool(re.search(_REL, text, re.I)), bool(re.search(_ABS, text))
    if rel and absolute:
        if re.search(rf"[(\[]\s*(?:{_REL})", text, re.I):
            return "absolute_with_relative"
        if re.search(rf"[(\[]\s*(?:{_ABS})", text):
            return "relative_with_absolute"
        return UNRESOLVED
    if rel:
        return "relative_only"
    if absolute:
        return "absolute_only"
    if re.search(_WEEKDAY, text) and re.search(r"\b\d{1,2}[:.]\d{2}\b", text):
        return "weekday_and_time"
    return UNRESOLVED


fn_spec(
    "relative_date_wording",
    ["absolute_only", "relative_only", "relative_with_absolute",
     "weekday_and_time", "absolute_with_relative"],
    _relative_date_wording,
)

# --- fmt-0199  heading_phrasing ---

_IMPERATIVE = frozenset("""
install configure set connect add create send enable run use choose verify test
deploy build write open start stop check import export register upgrade migrate
""".split())


def _heading_lines(text: str) -> list[str]:
    """The section headings: the marked heading lines when there are any.
    Otherwise a heading is a short line that does not close like a sentence -- without that, an
    ordinary apology is a heading and scores a phrasing."""
    marked = [re.sub(r"^#{1,6}\s*", "", ln).strip()
              for ln in text.splitlines() if re.match(r"^\s*#{1,6}\s+\S", ln)]
    if marked:
        return [] if any(opens_as_talk(h) for h in marked) else marked
    heads = [ln.strip() for ln in text.splitlines()
             if ln.strip() and len(ln.split()) <= 10 and not ln.rstrip().endswith(".")
             and not opens_as_talk(ln)]
    return heads if len(heads) >= 2 else []


def _heading_one(h: str) -> str | None:
    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", h)
    if len(words) < 2:
        return None
    first = words[0].lower()
    if h.rstrip().endswith("?"):
        # A question phrased as a gerund is 'other' rather than scoring twice.
        return None if first.endswith("ing") else "question"
    if first.endswith("ing"):
        return "gerund_phrase"
    if first in _IMPERATIVE:
        return "imperative"
    # A full sentence is the only remaining form carrying a SUBJECT, which the imperative never does.
    if re.match(r"^(?:The|A|An|Your|This|Each|Every|It)\s+\w+\s+(?:\w+s|\w+ed|is|are|can|will|must)\b",
                h):
        return "full_sentence"
    return "noun_phrase"


def _heading_phrasing(text: str) -> str:
    heads = _heading_lines(text)
    if not heads:
        return UNRESOLVED
    # One unclassifiable heading spoils the set: sections phrased two ways have followed neither instruction.
    labels = {_heading_one(h) for h in heads}
    if None in labels or len(labels) != 1:
        return UNRESOLVED
    return labels.pop()


fn_spec(
    "heading_phrasing",
    ["noun_phrase", "gerund_phrase", "imperative", "question", "full_sentence"],
    _heading_phrasing,
)

# --- fmt-0200  number_word_threshold ---

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}
_UNIT = (r"(?:km|kg|mm|cm|kW|MW|MB|GB|TB|%|per cent|miles?|metres?|tonnes?|litres?|"
         r"acres?|hectares?)")


def _number_word_threshold(text: str) -> str:
    """Read from a number in the 10-99 band.
    The two threshold rules agree on everything below ten and above a hundred, so a piece
    without a number in that band is 'other' -- fmt-0200's argument."""
    figures = [(m.start(), int(m.group(1)), text[m.end():m.end() + 12])
               for m in re.finditer(r"(?<![\w.,])(\d{1,3})(?![\d.,])", text)]
    words = [(m.start(), _NUMBER_WORDS[m.group(0).lower()])
             for m in re.finditer(r"\b(?:%s)\b" % "|".join(_NUMBER_WORDS), text, re.I)]
    if not figures and not words:
        return UNRESOLVED

    if figures and words and all(re.match(rf"\s*{_UNIT}\b", tail, re.I) for _, _, tail in figures):
        return "figures_with_units_only"
    # A line starts a sentence too: a number word after a heading, or after a blank line, was read as mid-sentence.
    if figures and words and all(
            re.search(r"(?:\A|\n|[.!?]\s)\s*\Z", text[:p]) for p, _ in words):
        return "words_sentence_initial"

    mid_fig = [f for f in figures if 10 <= f[1] <= 99]
    mid_word = [w for w in words if 10 <= w[1] <= 99]
    if not mid_fig and not mid_word:
        return UNRESOLVED
    if mid_fig and not mid_word:
        return "words_under_ten" if any(v < 10 for _, v in words) else "figures_always"
    if mid_word and not mid_fig and not figures:
        return "words_always"
    return UNRESOLVED


fn_spec(
    "number_word_threshold",
    ["words_under_ten", "words_sentence_initial", "figures_always",
     "words_always", "figures_with_units_only"],
    _number_word_threshold,
)

# --- fmt-0202  job_title_capitalisation ---

_TITLE = re.compile(r"([\"“]?)\b((?i:head|director|manager|chief|officer|president|lead)\b"
                    r"(?:\s+of\s+[A-Za-z]+)?)([\"”]?)")


def _job_title_capitalisation(text: str) -> str:
    """Two of the rules capitalise some occurrences and not others, so every
    occurrence is collected and the SHORTENED ones are compared against the
    full ones -- fmt-0202's argument. The recast label is granted only where no
    title token survives anywhere."""
    occ = list(_TITLE.finditer(text))
    if not occ:
        return UNRESOLVED
    if any(m.group(1) and m.group(3) for m in occ):
        return "quoted_title"
    infos = []
    for m in occ:
        toks = [t for t in m.group(2).split() if t.lower() not in ("of", "the", "and")]
        infos.append((len(toks), [t[0].isupper() for t in toks]))
    if all(not any(c) for _, c in infos):
        return "lowercase_always"
    if all(all(c) for _, c in infos):
        return "capital_always"
    multi = [(n, c) for n, c in infos if n > 1]
    if multi and all(c[0] and not any(c[1:]) for _, c in multi):
        return "capital_first_word"
    short = [(n, c) for n, c in infos if n == 1]
    if multi and short and all(all(c) for _, c in multi) and all(not any(c) for _, c in short):
        return "capital_full_title_only"
    return UNRESOLVED


fn_spec(
    "job_title_capitalisation",
    ["capital_first_word", "capital_always", "lowercase_always",
     "capital_full_title_only", "quoted_title"],
    _job_title_capitalisation,
)

# --- fmt-0203  salutation_style ---


_NOT_A_NAME = frozenset("""
thanks thank sorry apologies morning afternoon evening greetings cheers hiya hey
hi hello dear update note summary regards team everyone all folks customer
""".split())
"""Words that can open a reply on a line of their own and are not a name."""


def _salutation_style(text: str) -> str:
    """The FIRST LINE decides, and nothing after it.
    Three rules put a greeting word before a name and are separated by WHICH PARTS OF THE NAME
    follow it, never by the greeting word -- fmt-0203's argument."""
    lines = _lines(unwrap(text))
    if not lines:
        return UNRESOLVED
    first = lines[0]
    if re.match(r"^Dear\s+(?:Mr|Mrs|Ms|Dr|Prof)\b\.?\s+[A-Z][a-z]+", first):
        return "dear_honorific_surname"
    if re.match(r"^(?:Hello|Hi|Dear)\s+[A-Z][a-z]+\s+[A-Z][a-z]+\s*[,:]", first):
        return "hello_full_name"
    if re.match(r"^(?:Hi|Hello|Hey)\s+[A-Z][a-z]+\s*[,:]", first):
        return "hi_given_name"
    if re.match(r"^(?:Hi|Hello|Hey|Greetings|Good (?:morning|afternoon|evening)|Dear)"
                r"\s*(?:there|team|customer|all|everyone|sir or madam)?\s*[,:]", first, re.I):
        return "generic_greeting"
    # The name alone: one or two capitalised words and nothing else. Every greeting form is tested above, so a greeting word never reaches here as a name.
    name = re.fullmatch(r"([A-Z][a-z]+)(?:[ \t]+([A-Z][a-z]+))?[ \t]*[,:—–-]?", first)
    if name and not any(w and w.lower() in _NOT_A_NAME for w in name.groups()):
        return "name_only"
    return UNRESOLVED


fn_spec(
    "salutation_style",
    ["hi_given_name", "hello_full_name", "dear_honorific_surname",
     "name_only", "generic_greeting"],
    _salutation_style,
)

# --- fmt-0205 section_cross_reference: the number-and-title form CONTAINS a bare number so it is tested first, and clause and page numbers are separated by the noun introducing them ---

spec(
    "section_cross_reference",
    ("page_number", rx(r"\bpage\s+\d+", re.I)),
    ("number_and_title", rx(r"\bclause\s+\d+[^,\n]{0,4}[,:]\s*[“\"][^\"”\n]+[”\"]|"
                            r"\bclause\s+\d+\s*[,:]\s*[A-Z][\w ]{3,}", re.I)),
    ("number_only", rx(r"\bclause\s+\d+", re.I)),
    ("title_quoted", rx(r"[“\"][^\"”\n]{4,60}[”\"]")),
    ("descriptive_phrase", rx(r"\bthe clause\s+(?:that|which|dealing|governing|covering|on|"
                              r"setting|requiring)\b", re.I)),
)

# --- fmt-0206  acronym_first_use ---

_EXP_THEN_ACR = re.compile(r"\b([A-Z][A-Za-z]*(?:\s+[A-Za-z]+){1,4})\s*\(\s*([A-Z]{2,6})\s*\)")
_ACR_THEN_EXP = re.compile(r"\b([A-Z]{2,6})\s*\(\s*([A-Za-z][A-Za-z]*(?:\s+[A-Za-z]+){1,4})\s*\)")


def _acronym_first_use(text: str) -> str:
    """The two bracketed forms carry the same two strings and are separated by
    WHICH OF THEM SITS INSIDE THE BRACKETS, never by which appears first on the
    page -- fmt-0206's argument. The glossary and heading rules both leave the
    body unexpanded and are separated by where the expansion appears."""
    if _EXP_THEN_ACR.search(text):
        return "expansion_then_acronym"
    if _ACR_THEN_EXP.search(text):
        return "acronym_then_expansion"
    acronyms = re.findall(r"(?<![A-Za-z])[A-Z]{2,6}(?![A-Za-z])", text)
    headings = [ln for ln in text.splitlines() if re.match(r"^\s*#{1,6}\s+\S", ln)]
    if acronyms and headings and any(
            re.search(r"\b[A-Z][A-Za-z]*(?:\s+[A-Za-z]+){1,4}\b", h) for h in headings):
        return "expansion_in_heading"
    if acronyms and re.search(r"^\s*(?:\[\^?\d+\]|\d+\.|\*)\s+\S", text, re.M):
        return "acronym_with_footnote"
    # `expansion_always` is the absence of the short form, so it needs a capitalised phrase used more than once and no acronym anywhere.
    phrases = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4}\b", text)
    if not acronyms and phrases and len(phrases) >= 2:
        return "expansion_always"
    return UNRESOLVED


fn_spec(
    "acronym_first_use",
    ["expansion_then_acronym", "acronym_then_expansion", "expansion_always",
     "acronym_with_footnote", "expansion_in_heading"],
    _acronym_first_use,
)

# --- fmt-0207  foreign_term_treatment ---

_FOREIGN = ("pension pensione ryokan paseo sobremesa hygge siesta trattoria souk riad "
            "onsen tapas auberge posada gite konbini izakaya medina hammam piazza "
            "autostrada aperitivo passeggiata parador taverna").split()
_ENGLISH_SUB = ("guesthouse inn stroll nap market bathhouse square tavern "
                "boardinghouse").split()


def _foreign_term_treatment(text: str) -> str:
    """The two italic rules agree on the term's FIRST appearance, so the label
    needs a second one -- a feature using the term once is 'other', which is
    fmt-0207's rule and why this counts occurrences before judging any."""
    occ = []
    for term in _FOREIGN:
        for m in re.finditer(rf"([*_\"“]?)\b({term})\b([*_\"”]?)", text, re.I):
            occ.append((m.group(1), m.group(2), m.group(3)))
    if not occ:
        # The substitution label requires the borrowed term to be absent entirely, so it needs positive evidence of an English rendering.
        return "english_equivalent" if any(
            re.search(rf"\b{w}\b", text, re.I) for w in _ENGLISH_SUB) else UNRESOLVED
    if len(occ) < 2:
        return UNRESOLVED
    if all(o[0] in "*_" and o[2] in "*_" and o[0] for o in occ):
        return "italic_always"
    if all(o[0] in '"“' and o[2] in '"”' and o[0] for o in occ):
        return "upright_quoted"
    if not any(o[0] or o[2] for o in occ):
        if all(o[1][0].isupper() for o in occ):
            return "capitalised_unmarked"
        if not any(o[1][0].isupper() for o in occ):
            return "upright_unmarked"
    return UNRESOLVED


fn_spec(
    "foreign_term_treatment",
    ["italic_always", "capitalised_unmarked", "upright_quoted",
     "upright_unmarked", "english_equivalent"],
    _foreign_term_treatment,
)

# --- fmt-0208  attribution_format ---

_NAME = r"[A-Z][a-z]+\s+[A-Z][a-z]+"


def _attribution_format(text: str) -> str:
    """The dashed credit and the name-and-role stack open with the same words,
    so WHAT PRECEDES THE NAME and HOW MANY LINES the credit occupies are what
    is read. A block carrying both a dashed credit and a prose introduction is
    'other' -- fmt-0208's rule, so these are collected rather than ordered."""
    dash = bool(re.search(rf"^\s*(?:—|–|--)\s*{_NAME}\s*$", text, re.M))
    stack = bool(re.search(rf"^\s*{_NAME}\s*$\n\s*[A-Za-z][^\n]{{3,60}}$", text, re.M))
    bracket = bool(re.search(rf"^\s*[(\[]\s*{_NAME}\s*[)\]]\s*$", text, re.M))
    prose = bool(re.search(rf"{_NAME}\s*,?\s+(?:said|says|told|explained|added|noted)\b", text))
    footnote = bool(re.search(r"^\s*(?:\[\^?\d+\]|\d+\.)\s+\S", text, re.M))

    if dash and prose:
        return UNRESOLVED
    if dash:
        return "dash_then_name"
    if stack:
        return "name_then_role"
    if bracket:
        return "bracketed_name"
    if prose:
        return "introduced_in_prose"
    if footnote:
        return "footnote_credit"
    return UNRESOLVED


fn_spec(
    "attribution_format",
    ["dash_then_name", "name_then_role", "bracketed_name",
     "introduced_in_prose", "footnote_credit"],
    _attribution_format,
)

# --- fmt-0209  contract_amount_expression ---

_AMOUNT_FIG = re.compile(r"[£$€]\s?[\d,]+(?:\.\d{2})?")
_AMOUNT_WORDS = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million)\b"
    r"[^.\n]{0,60}?\b(?:pounds|dollars|euros)\b", re.I)


def _contract_amount_expression(text: str) -> str:
    """The two paired forms carry the same two renderings and are separated by
    WHICH SITS INSIDE THE BRACKETS, not by which reaches the reader first. The
    split rule keeps them in different documents, so a clause containing both
    falls to one of the paired labels -- fmt-0209's argument."""
    figs, words = bool(_AMOUNT_FIG.search(text)), bool(_AMOUNT_WORDS.search(text))
    if figs and words:
        if re.search(r"[(\[]\s*[£$€]", text):
            return "words_then_figures"
        if re.search(r"[(\[][^)\]\n]{0,60}\b(?:pounds|dollars|euros)\b", text, re.I):
            return "figures_then_words"
        return UNRESOLVED
    if figs and re.search(r"\bschedule\b", text, re.I):
        return "split_clause_and_schedule"
    if figs:
        return "figures_only"
    if words:
        return "words_only"
    return UNRESOLVED


fn_spec(
    "contract_amount_expression",
    ["figures_only", "words_only", "words_then_figures",
     "figures_then_words", "split_clause_and_schedule"],
    _contract_amount_expression,
)

# --- fmt-0210  defined_term_marking ---

_CALENDAR_NAMES = frozenset("""
Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March
April May June July August September October November December
""".split())


def _defined_term_marking(text: str) -> str:
    """The HEIGHT OF THE LETTERS AFTER THE FIRST is read, not the first letter alone.
    Initial capitals and small capitals both alter case, which is fmt-0210's argument and the
    reason the all-capital form is tested first."""
    bold = bool(re.search(r"\*\*[A-Za-z][\w ]{2,30}\*\*", text))
    underlined = bool(re.search(r"<u>[^<\n]{2,30}</u>", text, re.I))
    quoted = bool(re.search(r"[“\"][A-Z][\w ]{2,30}[”\"]\s+(?:means|shall mean|has the meaning)",
                            text, re.I))
    small = bool(re.search(r"(?<=[a-z,]\s)[A-Z]{3,}\b", text))
    # A weekday or a month is capitalised mid-sentence by grammar, not marking: "moved to Thursday afternoon" used to be a defined term.
    initial = any(w not in _CALENDAR_NAMES
                  for w in re.findall(r"(?<=[a-z,]\s)([A-Z][a-z]{2,})\b", text))

    if bold and small:
        return UNRESOLVED
    if underlined:
        return "underlined_term"
    if bold:
        return "bold_face"
    if quoted:
        return "quoted_at_definition"
    if small:
        return "small_capitals"
    if initial:
        return "initial_capitals"
    return UNRESOLVED


fn_spec(
    "defined_term_marking",
    ["initial_capitals", "bold_face", "quoted_at_definition",
     "small_capitals", "underlined_term"],
    _defined_term_marking,
)
