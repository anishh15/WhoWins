"""Surface-form format axes -- fmt-0001..0030.
One of five ways of writing a value down: casing, dates, delimiters, units, quoting.
These read the literal characters, so the hazard is one form nesting inside another and
the rule order is the exclusivity argument."""

from __future__ import annotations

import json
import re
from typing import Optional

from ..core import UNRESOLVED, opens_as_talk
from ._lib import (
    TOKEN_START,
    field_names,
    first_body,
    first_line,
    fn_spec,
    fullrx,
    looks_like_sentence,
    rx,
    short_fields,
    spec,
    uniform_spec,
    unwrap,
)

# --- fmt-0001  output_format ---

_MD_TABLE = re.compile(r"^\s*\|.*\|\s*$\n\s*\|[\s:|-]+\|\s*$", re.M)


def _output_format(text: str) -> str:
    """JSON is tested before YAML, because much valid JSON is also valid YAML.
    The trap fmt-0001's exclusivity field names, closed by order rather than by a cleverer
    YAML test."""
    body = first_body(text).strip()
    if body:
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            return "json_object"
        if isinstance(parsed, list):
            return "json_array"
    if _MD_TABLE.search(text):
        return "md_table"
    lines = [ln for ln in body.splitlines() if ln.strip()]
    # CSV before YAML: a header row is delimited and has no `key:` shape.
    if len(lines) >= 2 and all("," in ln for ln in lines[:2]) and ":" not in lines[0]:
        return "csv_header"
    if re.search(r"^\s*[A-Za-z_][\w\-]*\s*:(?:\s|$)", body, re.M):
        return "yaml_mapping"
    return UNRESOLVED


fn_spec(
    "output_format",
    ["json_object", "json_array", "yaml_mapping", "md_table", "csv_header"],
    _output_format,
)

# --- fmt-0002 key_casing: the five patterns are fully anchored and mutually disjoint, and a field with no separator and no case change matches none, so such a set is UNRESOLVED rather than an arbitrary win ---

uniform_spec(
    "key_casing",
    field_names,
    ("screaming_snake", fullrx(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+")),
    ("snake_case", fullrx(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")),
    ("kebab_case", fullrx(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+")),
    ("camel_case", fullrx(r"[a-z]+(?:[A-Z][a-z0-9]*)+")),
    # At least one lower-case letter: "TIMEOUT" has no case change, and read as two humps it won a different option.
    ("pascal_case", fullrx(r"(?=.*[a-z])(?:[A-Z][a-z0-9]*){2,}")),
)

# --- fmt-0003  date_encoding ---

spec(
    "date_encoding",
    # RFC 2822 first: it carries a weekday and a month name, so no purely numeric pattern can be confused with it.
    ("rfc_2822", rx(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+\d{1,2}\s+"
                    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}")),
    # `\b` after a digit cannot match before `T`, so an ISO datetime would escape entirely -- the same trap as `\b` inside `export_datadog`.
    ("iso_8601", rx(r"\b\d{4}-\d{2}-\d{2}(?![\d-])")),
    ("us_slash", rx(r"\b\d{1,2}/\d{1,2}/\d{4}(?!\d)")),
    ("eu_dot", rx(r"\b\d{1,2}\.\d{1,2}\.\d{4}(?!\d)")),
    # Epoch last: a bare 9-11 digit run is only a date if nothing else claimed it.
    ("unix_epoch", rx(r"(?<!\d)\d{9,11}(?!\d)")),
)

# --- fmt-0004  numeric_precision ---

spec(
    "numeric_precision",
    ("percent_sign", rx(r"\d\s*%")),
    ("scientific", rx(r"\d(?:\.\d+)?[eE][+-]?\d+")),
    ("three_dp", rx(r"\b\d+\.\d{3}(?!\d)")),
    ("one_dp", rx(r"\b\d+\.\d(?!\d)")),
    ("integer", rx(r"(?<![\d.])\d+(?![\d.])")),
)

# --- fmt-0005  delimiter ---


_SEPARATORS = {"tab": r"\t", "pipe": r"\|", "semicolon": r";", "comma": r",",
               "double_space": r" {2,}"}
_NEVER_A_ROW = re.compile(r"^\s*(?:#{1,6}\s|\*\*[^*\n]+\*\*\s*$|```|~~~)|:\s*$")
_NESTED = re.compile(r"\([^()\n]*\)|\[[^\[\]\n]*\]|\{[^{}\n]*\}|\"[^\"\n]*\"|`[^`\n]*`")
_CAPS_TITLE = re.compile(r"^\s*[A-Z][A-Z0-9 ,'&/:-]{3,}\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")


def _row(line: str) -> Optional[str]:
    """The separator that splits `line` into a row of short fields: None if none does,
    UNRESOLVED if two tie. A sentence is never a row, and brackets and quotes are masked,
    since a comma inside them never separates columns: "(e.g., a, b)" is not a row."""
    if looks_like_sentence(line):
        return None
    flat = line
    while (masked := _NESTED.sub(lambda m: "x" * len(m.group()), flat)) != flat:
        flat = masked
    # A candidate counts only if it splits the line into a row of short fields; without this the comma in an apology reads as a delimiter.
    counts = {k: len(short_fields(flat, sep)) for k, sep in _SEPARATORS.items()}
    best = max(counts.values())
    if best < 2:
        return None
    winners = [k for k, v in counts.items() if v == best]
    return winners[0] if len(winners) == 1 else UNRESOLVED


def _above_a_table(line: str) -> bool:
    """A title, talk, a sentence or a list item: what a model writes above the table it gives."""
    s = line.strip()
    return bool(_CAPS_TITLE.match(s) or opens_as_talk(s) or looks_like_sentence(s)
                or _LIST_ITEM.match(s))


def _delimiter(text: str) -> str:
    """Judged on the table's first row, and by which separator dominates it.
    Testing "contains a comma" would label almost any prose comma-delimited, so the winner is
    the candidate with the highest count on that row. Headings, fences, lead-ins, sentences
    and list items above the row are passed over; any other line ends the search unresolved."""
    for line in text.splitlines():
        if not line.strip() or _NEVER_A_ROW.search(line):
            continue
        label = _row(line)
        if label is not None:
            return label
        if not _above_a_table(line):
            return UNRESOLVED
    return UNRESOLVED


fn_spec("delimiter", ["comma", "tab", "pipe", "semicolon", "double_space"], _delimiter)

# --- fmt-0006  id_format ---

spec(
    "id_format",
    ("uuid4", rx(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-"
                 r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b")),
    ("prefixed_counter", rx(r"\b[A-Za-z]{2,}[-_]\d+\b")),
    ("hex8", rx(r"(?<![0-9a-zA-Z])[0-9a-f]{8}(?![0-9a-zA-Z])")),
    ("word_slug", rx(r"\b[a-z]+(?:-[a-z]+){1,3}\b")),
    ("bare_integer", rx(r"(?<![\w-])\d{1,9}(?![\w-])")),
)

# --- fmt-0007  heading_style ---

spec(
    "heading_style",
    ("h3", rx(r"^\s*###\s+\S", re.M)),
    ("h2", rx(r"^\s*##\s+\S", re.M)),
    ("h1", rx(r"^\s*#\s+\S", re.M)),
    ("bold_line", rx(r"^\s*\*\*[^*\n]+\*\*\s*$", re.M)),
    # The colon is in the class because a caps heading routinely carries one. caps_line is tested last, so widening it can only take a line no other rule claimed.
    ("caps_line", rx(r"^\s*[A-Z][A-Z0-9 ,'&/:-]{3,}\s*$", re.M)),
)

# --- fmt-0008  currency_format ---

spec(
    "currency_format",
    ("accounting_parens", rx(r"\(\s*[$£€]?\s*[\d,]+(?:\.\d{2})?\s*\)")),
    ("code_suffix", rx(r"\b[\d,]+(?:\.\d{2})?\s+(?:USD|EUR|GBP|JPY|CAD|AUD|CHF)\b")),
    ("symbol_prefix", rx(r"[$£€¥]\s?[\d,]+(?:\.\d{2})?")),
    ("bare_decimal", rx(r"(?<![$£€¥\d.])\d+\.\d{2}(?!\d)")),
    ("integer_cents", rx(r"(?<![\d.$£€¥])\d{3,}(?![\d.])")),
)

# --- fmt-0009  list_marker ---

spec(
    "list_marker",
    ("roman", rx(r"^\s*(?:i{1,3}|iv|v|vi{1,3}|ix|x)[.)]\s+\S", re.M | re.I)),
    ("arabic", rx(r"^\s*\d+[.)]\s+\S", re.M)),
    ("hyphen", rx(r"^\s*-\s+\S", re.M)),
    ("asterisk", rx(r"^\s*\*\s+\S", re.M)),
    ("prose", rx(r"\b(?:first|firstly|then|next|finally|lastly)\b", re.I)),
)

# --- fmt-0010  timezone_encoding ---

spec(
    "timezone_encoding",
    ("utc_z", rx(r"\d{2}:\d{2}(?::\d{2})?Z\b")),
    ("numeric_offset", rx(r"\d{2}:\d{2}(?::\d{2})?\s*[+-]\d{2}:?\d{2}(?!\d)")),
    # A zone name is a stamp only after a time, as the offset is: "a numeric UTC offset" names UTC and stamps nothing.
    ("named_zone", rx(r"\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?\s*\[?"
                      r"(?:[A-Z][a-z]+/[A-Z][a-z_]+|UTC|GMT|EST|PST|CET|IST)\b")),
    ("epoch_seconds", rx(r"(?<!\d)\d{9,11}(?!\d)")),
    # Explicit about excluding a time part rather than relying on `\b` accidentally failing before `T`.
    ("date_only", rx(r"\b\d{4}-\d{2}-\d{2}(?![T\d-])")),
)

# --- fmt-0011  boolean_encoding ---

_FLAG_VALUE = re.compile(
    r"""(?:^|[\s{,])\s*["']?[A-Za-z_][\w.-]*["']?\s*[:=]\s*["']?([A-Za-z0-9]+)["']?(?=\s*(?:[,}]|$))""",
    re.M,
)
_TABLE_VALUE = re.compile(r"^\s*\|?\s*[A-Za-z_][\w.-]*\s*\|\s*([A-Za-z0-9]+)\s*\|?\s*$", re.M)
_BARE_VALUE = re.compile(r"^[ \t]*[\"']?([A-Za-z0-9]+)[\"']?[ \t]*$", re.M)
"""A line holding nothing but a value, with its flag name on the line above.

Only ever read for a token that *is* one of the boolean spellings, so a stray
one-word line cannot make a dump 'other'; the whole-dump agreement test still
does that. It exists because a reply split under two headings gives each value
its own part, and a part of just "0" has no `name: value` pair left in it."""
_BOOLEAN_PAIRS = {"true": "true_false", "false": "true_false", "yes": "yes_no", "no": "yes_no",
                  "on": "on_off", "off": "on_off", "1": "one_zero", "0": "one_zero"}
_OTHER_BOOLEANS = frozenset("enabled disabled active inactive set unset t f".split())


def _boolean_encoding(text: str) -> str:
    """Read from the dump's VALUES, and the whole dump must agree on one pair.
    What follows a flag's name after a colon or equals sign, or a table row's second cell, as
    fmt-0011 asks. Reading the whole text would let a prose "yes" decide it."""
    labels = set()
    for v in _FLAG_VALUE.findall(text) + _TABLE_VALUE.findall(text):
        if v in ("Y", "N"):
            labels.add("y_n")
        elif v.lower() in _BOOLEAN_PAIRS:
            labels.add(_BOOLEAN_PAIRS[v.lower()])
        elif v.lower() in _OTHER_BOOLEANS:
            return UNRESOLVED
    for v in _BARE_VALUE.findall(text):
        if v in ("Y", "N"):
            labels.add("y_n")
        elif v.lower() in _BOOLEAN_PAIRS:
            labels.add(_BOOLEAN_PAIRS[v.lower()])
    return labels.pop() if len(labels) == 1 else UNRESOLVED


fn_spec(
    "boolean_encoding",
    ["true_false", "yes_no", "on_off", "y_n", "one_zero"],
    _boolean_encoding,
)

# --- fmt-0012  missing_value ---

spec(
    "missing_value",
    ("na_literal", rx(r"(?<![\w/])N/?A(?![\w])", re.I)),
    ("null_word", rx(r"\bnull\b", re.I)),
    ("unknown_word", rx(r"\bunknown\b", re.I)),
    ("hyphen_dash", rx(r"(?:^|[,\t|;])\s*[-–—]\s*(?:$|[,\t|;])", re.M)),
    ("empty_cell", rx(r"(?:^|,),|,\s*$", re.M)),
)

# --- fmt-0013  quote_style ---

spec(
    "quote_style",
    ("curly_quote", rx(r"[\u2018\u2019\u201c\u201d]")),
    ("backtick", rx(r"`[^`\n]+`")),
    ("double_quote", rx(r'"[^"\n]*"')),
    ("single_quote", rx(r"'[^'\n]*'")),
    # `unquoted` is close to an absence label, so it requires positive evidence of a value -- prose with no quotation marks is not an unquoted value.
    ("unquoted", lambda s: (not re.search(r"[\"'`\u2018\u2019\u201c\u201d]", s))
                 and bool(re.search(r"[\w.-]+\s*[:=]\s*\S", s) or short_fields(first_line(s), r"[,\t|;]"))),
)

# --- fmt-0014 byte_unit: binary prefixes before decimal, anchored on a word boundary plus the exact letters so `MB` cannot match inside `MiB` ---

spec(
    "byte_unit",
    ("mib_binary", rx(r"\b\d+(?:\.\d+)?\s*MiB\b")),
    ("kib_binary", rx(r"\b\d+(?:\.\d+)?\s*KiB\b")),
    ("mb_decimal", rx(r"\b\d+(?:\.\d+)?\s*MB\b")),
    ("kb_decimal", rx(r"\b\d+(?:\.\d+)?\s*kB\b", re.I)),
    ("raw_bytes", rx(r"\b\d+\s*(?:B\b|bytes\b)")),
)

# --- fmt-0015 name_order: one attendee per line, so the space inside a name is `[ \t]` and never `\s` -- with `\s` two family names on separate lines read as one given-first name. The capitals form takes NO comma, so the hybrid `OKAFOR, Jana` claims neither and returns 'other' ---

spec(
    "name_order",
    ("initial_family", rx(r"\b[A-Z]\.[ \t]*[A-Z][a-z]+\b")),
    ("family_caps", rx(r"\b[A-Z]{2,}[ \t]+[A-Z][a-z]+\b")),
    ("family_comma", rx(r"\b[A-Z][a-z]+[ \t]*,[ \t]*[A-Z][a-z]+\b")),
    ("given_first", rx(r"\b[A-Z][a-z]+[ \t]+[A-Z][a-z]+\b")),
    ("family_only", rx(r"^[ \t]*[A-Z][a-z]+[ \t]*$", re.M)),
)

# --- fmt-0016  phone_format ---

spec(
    "phone_format",
    ("e164", rx(r"\+\d{8,15}(?!\d)")),
    ("national_parens", rx(r"\(\d{3}\)\s*\d{3}[- ]?\d{4}")),
    ("dotted", rx(r"\b\d{3}\.\d{3}\.\d{4}(?!\d)")),
    ("spaced_groups", rx(r"\b\d{3}\s+\d{3}\s+\d{4}(?!\d)")),
    ("digits_only", rx(r"(?<!\d)\d{10,11}(?!\d)")),
)

# --- fmt-0017  rate_expression ---

spec(
    "rate_expression",
    ("basis_points", rx(r"\b\d+\s*(?:bps|basis points)\b", re.I)),
    ("per_mille", rx(r"\d\s*\u2030|\bper mille\b", re.I)),
    ("percent_symbol", rx(r"\d\s*%")),
    ("spelled_words", rx(r"\b\d+(?:\.\d+)?\s+per\s?cent\b", re.I)),
    ("decimal_fraction", rx(r"(?<![\d.%])0\.\d+(?![\d%])")),
)

# --- fmt-0018  indent_unit ---


def _indent_unit(text: str) -> str:
    """Smallest non-zero leading indent across continuation lines."""
    widths = set()
    tabs = False
    for line in text.splitlines():
        if not line.strip():
            continue
        m = re.match(r"^([ \t]+)", line)
        if not m:
            widths.add(0)
            continue
        lead = m.group(1)
        if "\t" in lead:
            tabs = True
        else:
            widths.add(len(lead))
    if tabs:
        return "tab_char"
    nonzero = {w for w in widths if w}
    if not nonzero:
        # `no_indent` is an ABSENCE label, so it needs positive evidence that the model produced something to not indent; without it an empty response wins outright.
        return "no_indent" if len([l for l in text.splitlines() if l.strip()]) >= 2 else UNRESOLVED
    unit = min(nonzero)
    return {2: "two_space", 4: "four_space", 8: "eight_space"}.get(unit, UNRESOLVED)


fn_spec(
    "indent_unit",
    ["two_space", "four_space", "eight_space", "tab_char", "no_indent"],
    _indent_unit,
)

# --- fmt-0019  truncation_marker ---

spec(
    "truncation_marker",
    ("bracketed_ellipsis", rx(r"[\[(]\s*(?:\.\.\.|\u2026)\s*[\])]")),
    # A TAG, not the word: bracketed, dashed or alone on its line. The bare word won "Mark the cut with three plain full stops." and "I cut the frames" beside a real `...`.
    ("snip_tag", rx(r"[\[<(]\s*(?:(?:\.\.\.|…)\s*)?(?:snip|snipped|truncated|cut)(?![A-Za-z])"
                    r"[^\]>)\n]{0,40}[\]>)]|-{2,}\s*(?:snip|snipped|truncated|cut)\s*-{2,}"
                    r"|^\s*(?:snip|snipped|truncated)\s*$", re.I | re.M)),
    ("plus_more", rx(r"\+\s*\d+\s+more\b", re.I)),
    ("unicode_ellipsis", rx(r"\u2026")),
    ("three_periods", rx(r"\.\.\.")),
)

# --- fmt-0020  version_string ---

spec(
    "version_string",
    ("build_metadata", rx(r"\b\d+\.\d+\.\d+[+][0-9A-Za-z.-]+")),
    ("v_prefixed", rx(r"\bv\d+\.\d+(?:\.\d+)?\b")),
    ("calendar_version", rx(r"\b(?:19|20)\d{2}\.(?:0?[1-9]|1[0-2])(?:\.\d+)?\b")),
    ("bare_semver", rx(r"(?<![\w.v])\d+\.\d+\.\d+(?![\w.])")),
    ("major_minor", rx(r"(?<![\w.v])\d+\.\d+(?![\w.])")),
)

# --- fmt-0021  colour_encoding ---

spec(
    "colour_encoding",
    ("hex6", rx(r"#[0-9a-fA-F]{6}\b")),
    ("hex3", rx(r"#[0-9a-fA-F]{3}\b")),
    ("rgb_functional", rx(r"\brgba?\s*\(", re.I)),
    ("hsl_functional", rx(r"\bhsla?\s*\(", re.I)),
    ("css_named", rx(r"\b(?:red|green|blue|black|white|teal|olive|navy|maroon|"
                     r"silver|gray|grey|purple|fuchsia|lime|aqua|yellow)\b", re.I)),
)

# --- fmt-0022  duration_format ---

spec(
    "duration_format",
    ("iso_duration", rx(r"\bP(?:\d+[YMWD])*(?:T(?:\d+[HMS])+)?\b")),
    ("colon_clock", rx(r"\b\d{1,3}:\d{2}(?::\d{2})?\b")),
    ("unit_suffix", rx(r"\b\d+\s*(?:h|hr|hrs|m|min|mins|s|sec|secs)\b", re.I)),
    ("decimal_hours", rx(r"\b\d+\.\d+\s*(?:hours?|h)\b", re.I)),
    ("total_seconds", rx(r"\b\d{2,}\s*seconds\b", re.I)),
)

# --- fmt-0023  coordinate_format ---

_GEOHASH = re.compile(r"(?<![\w-])[0-9bcdefghjkmnpqrstuvwxyz]{7,12}(?![\w-])")


def _geohash(text: str) -> bool:
    """A geohash's alphabet is also every English word without a, i, l or o, so
    "deferred" and "requested" read as geohashes, and ahead of the signed
    decimal beside them. A token carrying both a digit and a letter is one; a
    digit-free token only when it is the whole reply, framing aside."""
    if any(re.search(r"\d", t) and re.search(r"[a-z]", t) for t in _GEOHASH.findall(text)):
        return True
    lone = re.fullmatch(r"[`'\"*_]*([0-9bcdefghjkmnpqrstuvwxyz]{7,12})[`'\"*_]*\.?",
                        unwrap(text).strip())
    return bool(lone and re.search(r"[a-z]", lone.group(1)))


spec(
    "coordinate_format",
    ("dms", rx(r"\d+°\s*\d+['\u2032]\s*\d+(?:\.\d+)?[\"\u2033]")),
    ("ddm", rx(r"\d+°\s*\d+(?:\.\d+)?['\u2032]")),
    ("hemisphere_decimal", rx(r"\d+(?:\.\d+)?\s*°?\s*[NSEW]\b")),
    ("geohash", _geohash),
    ("signed_decimal", rx(r"-?\d{1,3}\.\d{3,}")),
)

# --- fmt-0024  log_level_style ---

_LEVELS = "DEBUG|INFO|NOTICE|WARN|WARNING|ERROR|CRIT|CRITICAL|ALERT|EMERG|FATAL|TRACE"

spec(
    "log_level_style",
    ("uppercase_word", rx(rf"\b(?:{_LEVELS})\b")),
    ("lowercase_word", rx(rf"\b(?:{_LEVELS.lower()})\b")),
    ("title_case_word", rx(r"\b(?:Debug|Info|Notice|Warn|Warning|Error|Critical|Fatal|Trace)\b")),
    # Must sit where a level sits -- bracketed, or opening a line before a colon -- or the "I" in "I can't help with that." is a level.
    ("initial_letter", rx(r"\[\s*[DIWEF]\s*\]|^\s*[DIWEF]\s*:", re.M)),
    ("syslog_number", rx(r"(?<![\w.])[0-7](?![\w.])")),
)

# --- fmt-0025  checksum_format ---

spec(
    "checksum_format",
    ("algo_prefixed", rx(r"\b(?:sha256|sha1|sha512|md5|crc32)[:=]", re.I)),
    ("spaced_groups", rx(r"\b[0-9a-fA-F]{4}(?:\s[0-9a-fA-F]{4}){3,}\b")),
    ("hex_upper", rx(r"(?<![0-9A-Za-z])[0-9A-F]{32,128}(?![0-9A-Za-z])")),
    ("hex_lower", rx(r"(?<![0-9A-Za-z])[0-9a-f]{32,128}(?![0-9A-Za-z])")),
    ("base64", rx(r"(?<![0-9A-Za-z+/])[0-9A-Za-z+/]{20,}={0,2}(?![0-9A-Za-z+/])")),
)

# --- fmt-0026  escape_style ---

spec(
    "escape_style",
    ("unicode_escape", rx(r"\\u[0-9a-fA-F]{4}")),
    ("html_entity", rx(r"&(?:[a-zA-Z]{2,10}|#\d{2,5});")),
    ("percent_encoded", rx(r"%[0-9A-Fa-f]{2}")),
    ("backslash", rx(r'\\[nrt"\'\\]')),
    ("doubled_char", rx(r"(?:''|\"\")")),
)

# --- fmt-0027  record_separator ---

spec(
    "record_separator",
    ("hyphen_rule", rx(r"^\s*-{3,}\s*$", re.M)),
    ("equals_rule", rx(r"^\s*={3,}\s*$", re.M)),
    ("asterisk_rule", rx(r"^\s*\*{3,}\s*$", re.M)),
    ("tilde_rule", rx(r"^\s*~{3,}\s*$", re.M)),
    # Content, blank line, content: a response that is nothing but newlines has not separated two records.
    ("blank_line", rx(r"\S[^\n]*\n[ \t]*\n[ \t]*\S")),
)

# --- fmt-0028  citation_style ---

spec(
    "citation_style",
    ("bracket_number", rx(r"\[\d{1,3}\]")),
    ("author_year", rx(r"\([A-Z][A-Za-z]+(?:\s+(?:et al\.?|and\s+[A-Z][A-Za-z]+))?,?\s+\d{4}\)")),
    ("superscript", rx(r"[\u00b9\u00b2\u00b3\u2070-\u2079]|<sup>")),
    ("dagger_symbol", rx(r"[†‡]")),
    ("prose_attribution", rx(r"\baccording to\b|\bas reported by\b|\bcites?\b", re.I)),
)

# --- fmt-0029  email_display ---

spec(
    "email_display",
    ("mailto_link", rx(r"mailto:[^\s>)\]]+@")),
    ("name_angle", rx(r"[A-Za-z][\w.\- ]*<[^@\s>]+@[^\s>]+>")),
    ("at_obfuscated", rx(r"\b[\w.+-]+\s*(?:\[at\]|\(at\)|\sat\s)\s*[\w.-]+\s*"
                         r"(?:\[dot\]|\(dot\)|\sdot\s)", re.I)),
    ("bare_address", rx(r"(?<![<:\w])[\w.+-]+@[\w-]+\.[\w.]+")),
    ("display_name_only", rx(r"^\s*[A-Z][a-z]+(?: [A-Z][a-z]+)+\s*$", re.M)),
)

# --- fmt-0030  path_style ---

spec(
    "path_style",
    ("file_uri", rx(r"\bfile://\S+")),
    ("windows_backslash", rx(r"(?:[A-Za-z]:)?\\[\w.$-]+\\")),
    # TOKEN_START, not `(?<!\S)`: a path in inline code is still a path.
    ("home_tilde", rx(TOKEN_START + r"~/[\w./-]+")),
    ("absolute_posix", rx(TOKEN_START + r"/(?!/)[\w.-]+(?:/[\w.-]+)*")),
    ("relative_path", rx(TOKEN_START + r"(?:\./)?[\w.-]+(?:/[\w.-]+)+")),
)
