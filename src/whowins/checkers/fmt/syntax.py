"""Syntactic axes -- notation, delimiters, and markup shapes.
What they share is a NESTING HAZARD: one label's literal form contains another's, so the
more specific is always tested first and the rule list says why."""

from __future__ import annotations

import re

from ..core import UNRESOLVED
from ._lib import (
    first_line,
    fn_spec,
    rx,
    short_fields,
    spec,
    uniform_spec,
    unwrap,
)

# fmt-0038 acronym_style ---------------------------------------------------

_ACRONYMS = """
api sdk sql csv json xml yaml html css http https url uri pdf cpu gpu ssd os vm ip tcp udp
dns tls ssl ssh ftp vpn cdn cli gui ui ux ide ci qa sla kpi roi crm erp etl ai nlp llm sso
mfa pii gdpr faq rct irb pca jwt rbac
""".split()
"""Acronyms common enough in a white paper to be recognised in any casing.

A lower-case acronym is spelled like a word, so only a listed one can be told
from one: `api` is an acronym and `errors` is not. Left out on purpose: those
that are also words or units (it, us, am, rest, ram, hr, ml), those with a
conventional mixed case (SaaS, IoT), which no option asks for, and brand names.
"""

_ACRONYM_ALTS = sorted(_ACRONYMS, key=len, reverse=True)
_ACRONYM_TOKEN = re.compile(
    r"(?<![\w./-])(?:" + "|".join(r"\.".join(a) + r"\.?" for a in _ACRONYM_ALTS)
    + "|" + "|".join(_ACRONYM_ALTS) + r")(?:['’]?s)?(?![\w/]|\.\w|://)",
    re.I,
)
_EXPANSION = re.compile(
    r"\b(?:application programming interface|software development kit|structured query language|"
    r"comma[- ]separated values|javascript object notation|extensible markup language|"
    r"hypertext markup language|cascading style sheet|hypertext transfer protocol|"
    r"uniform resource (?:locator|identifier)|portable document format|central processing unit|"
    r"graphics processing unit|solid[- ]state drive|operating system|virtual machine|"
    r"internet protocol|transmission control protocol|user datagram protocol|domain name system|"
    r"transport layer security|secure sockets layer|secure shell|file transfer protocol|"
    r"virtual private network|content delivery network|command[- ]line interface|"
    r"graphical user interface|user interface|user experience|integrated development environment|"
    r"continuous integration|quality assurance|service[- ]level agreement|"
    r"key performance indicator|return on investment|customer relationship management|"
    r"enterprise resource planning|extract,? transform,? (?:and )?load|artificial intelligence|"
    r"natural language processing|large language model|single sign[- ]on|"
    r"multi[- ]factor authentication|personally identifiable information|"
    r"general data protection regulation|frequently asked question|randomi[sz]ed controlled trial|"
    r"institutional review board|principal component analysis|json web token|"
    r"role[- ]based access control)s?\b",
    re.I,
)


def _acronym_form(token: str) -> str | None:
    core = token
    if core.endswith(("'s", "’s")):
        core = core[:-2]
    elif core.endswith("s") and len(core) > 2 and (core[:-1].isupper() or core[-2] == "."):
        core = core[:-1]  # a plural: APIs, A.P.I.s
    if "." in core:
        return "period_separated"
    if core.isupper():
        return "all_caps"
    if core.islower():
        return "all_lower"
    if core[0].isupper() and core[1:].islower():
        return "initial_cap"
    return None


def _opens_sentence(text: str, at: int) -> bool:
    before = text[:at]
    line = before.rsplit("\n", 1)[-1]
    if line.lstrip().startswith("#") or not re.sub(r"^[\s>*+\-\d.)]*", "", line):
        return True
    return bool(re.search(r"[.!?:]\s+$", before))


def _acronym_style(text: str) -> str:
    """Read from the acronyms themselves, and every one must agree.
    Testing token shapes anywhere in the text made any "e.g." an acronym and let ordinary
    prose decide the label. Only real acronym tokens are read now."""
    forms = []
    for m in _ACRONYM_TOKEN.finditer(text):
        form = _acronym_form(m.group(0))
        if form == "initial_cap" and _opens_sentence(text, m.start()):
            continue
        forms.append(form)
    if forms:
        return forms[0] if len(set(forms)) == 1 and forms[0] else UNRESOLVED
    return "expanded_words" if _EXPANSION.search(text) else UNRESOLVED


fn_spec(
    "acronym_style",
    ["period_separated", "expanded_words", "all_caps", "initial_cap", "all_lower"],
    _acronym_style,
)

# fmt-0041 time_of_day -----------------------------------------------------

spec(
    "time_of_day",
    ("ampm_spaced_caps", rx(r"\b\d{1,2}:\d{2}\s+(?:AM|PM)\b")),
    ("ampm_tight_lower", rx(r"\b\d{1,2}:\d{2}(?:am|pm)\b")),
    ("dotted_24h", rx(r"\b\d{1,2}\.\d{2}(?![\d.])")),
    ("colon_24h", rx(r"\b\d{1,2}:\d{2}(?::\d{2})?(?!\s*[APap][Mm])")),
    ("four_digit_military", rx(r"(?<!\d)(?:[01]\d|2[0-3])[0-5]\d(?:\s*(?:h|hrs))?(?!\d)")),
)

# fmt-0042 ordinal_style ---------------------------------------------------

spec(
    "ordinal_style",
    ("hash_prefix", rx(r"#\d+")),
    ("suffix_letters", rx(r"\b\d+(?:st|nd|rd|th)\b", re.I)),
    # A single "I" only counts when punctuated as a numeral, or "I can't help with that." is one.
    ("roman_numeral", rx(r"(?<![A-Za-z])(?:I{2,3}|IV|VI{0,3}|IX|X|[IVX][.)])(?![A-Za-z])")),
    ("word_form", rx(r"\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b", re.I)),
    ("bare_number", rx(r"(?<![\w#])\d+(?![\w])")),
)

# fmt-0043 range_notation --------------------------------------------------

spec(
    "range_notation",
    ("plus_minus", rx(r"±|\+/-")),
    ("interval_brackets", rx(r"[\[(]\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*[\])]")),
    ("en_dash", rx(r"\d\s*–\s*\d")),
    ("to_word", rx(r"\d\s+to\s+\d", re.I)),
    ("hyphen", rx(r"\d\s*-\s*\d")),
)

# fmt-0044 negative_sign ---------------------------------------------------

spec(
    "negative_sign",
    ("unicode_minus", rx(r"−\d")),
    ("cr_marker", rx(r"\d[\d,.]*\s*CR\b")),
    ("parenthesised", rx(r"\(\s*[\d,]+(?:\.\d+)?\s*\)")),
    ("trailing_minus", rx(r"[\d,]+(?:\.\d+)?-(?!\d)")),
    ("leading_hyphen", rx(r"(?<![\w)])-\d")),
)

# fmt-0045 thousands_separator ---------------------------------------------


def _thousands(text: str) -> str:
    """Judged on a grouped number, longest separator evidence first.

    `none` is only returned for a run of >=4 digits with no grouping anywhere,
    so a short number does not read as a deliberate no-separator policy."""
    if re.search(r"\d{1,3}(?:,\d{3})+(?![\d])", text):
        return "comma"
    if re.search(r"\d{1,3}(?:\.\d{3})+(?![\d])", text):
        return "period"
    if re.search(r"\d{1,3}(?:[  ]\d{3})+(?![\d])", text):
        return "space"
    if re.search(r"\d{1,3}(?:'\d{3})+(?![\d])", text):
        return "apostrophe"
    if re.search(r"(?<![\d,.'])\d{4,}(?![\d,.'])", text):
        return "none"
    return UNRESOLVED


fn_spec("thousands_separator", ["comma", "period", "space", "apostrophe", "none"], _thousands)

# fmt-0050 uuid_rendering --------------------------------------------------

spec(
    "uuid_rendering",
    # URN first: it CONTAINS a lower hyphenated UUID, so testing that first would make urn_prefixed unreachable.
    ("urn_prefixed", rx(r"urn:uuid:[0-9a-fA-F-]{36}", re.I)),
    ("upper_hyphenated", rx(r"(?<![\w-])[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-"
                            r"[0-9A-F]{4}-[0-9A-F]{12}(?![\w-])")),
    ("lower_hyphenated", rx(r"(?<![\w-])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                            r"[0-9a-f]{4}-[0-9a-f]{12}(?![\w-])")),
    ("hyphenless", rx(r"(?<![\w-])[0-9a-fA-F]{32}(?![\w-])")),
    ("base32_compact", rx(r"(?<![\w-])[A-Z2-7]{26}(?![\w-])")),
)

# fmt-0054 link_style ------------------------------------------------------

spec(
    "link_style",
    ("footnote_style", rx(r"\[\^[\w-]+\]")),
    ("reference_style", rx(r"\[[^\]\n]+\]\[[^\]\n]*\]")),
    ("inline_link", rx(r"\[[^\]\n]+\]\(\S+\)")),
    ("angle_autolink", rx(r"<https?://[^>\s]+>")),
    ("bare_autolink", rx(r"(?<![(<\]])https?://\S+")),
)

# fmt-0055 code_block_style ------------------------------------------------

spec(
    "code_block_style",
    ("html_pre", rx(r"<pre\b", re.I)),
    ("tilde_fence", rx(r"^\s*~~~", re.M)),
    ("backtick_with_language", rx(r"^\s*```[A-Za-z][\w+-]*\s*$", re.M)),
    ("backtick_no_language", rx(r"^\s*```\s*$", re.M)),
    ("four_space_indent", rx(r"^ {4}\S", re.M)),
)

# fmt-0057 emphasis_marker -------------------------------------------------

spec(
    "emphasis_marker",
    ("double_asterisk", rx(r"\*\*[^*\n]+\*\*")),
    ("double_underscore", rx(r"__[^_\n]+__")),
    ("backticks", rx(r"`[^`\n]+`")),
    ("single_asterisk", rx(r"(?<!\*)\*[^*\n]+\*(?!\*)")),
    ("uppercase", rx(r"(?<![A-Za-z])[A-Z]{3,}(?![A-Za-z])")),
)

# fmt-0058 dash_punctuation ------------------------------------------------

spec(
    "dash_punctuation",
    ("spaced_em_dash", rx(r"\s—\s")),
    ("closed_em_dash", rx(r"\w—\w")),
    ("spaced_en_dash", rx(r"\s–\s")),
    ("double_hyphen", rx(r"\w\s*--\s*\w")),
    ("paired_commas", rx(r",\s+[^,\n]{3,40},\s+")),
)

# --- fmt-0112 placeholder_delimiter: `${VAR}` contains `$VAR`, so dollar_brace is tested before dollar_bare ---

spec(
    "placeholder_delimiter",
    ("double_brace", rx(r"\{\{\s*[\w.]+\s*\}\}")),
    ("dollar_brace", rx(r"\$\{\s*[\w.]+\s*\}")),
    ("percent_wrapped", rx(r"%[\w.]+%")),
    ("angle_bracket", rx(r"<[A-Za-z_][\w.]*>")),
    ("dollar_bare", rx(r"\$[A-Za-z_]\w*")),
)

# fmt-0115 cli_option_spelling ---------------------------------------------

uniform_spec(
    "cli_option_spelling",
    lambda t: re.findall(r"(?<![\w-])--?[A-Za-z][\w-]*", t),
    ("double_dash_kebab", lambda s: s.startswith("--") and "-" in s[2:]),
    ("double_dash_snake", lambda s: s.startswith("--") and "_" in s[2:]),
    ("double_dash_camel", lambda s: s.startswith("--") and bool(re.search(r"[a-z][A-Z]", s[2:]))),
    ("double_dash_joined", lambda s: s.startswith("--") and s[2:].isalnum() and s[2:].islower()),
    ("single_dash_word", lambda s: not s.startswith("--") and s.startswith("-")),
)

# fmt-0117 env_list_packing ------------------------------------------------

spec(
    "env_list_packing",
    ("json_array_string", rx(r"=\s*'?\[\s*\"")),
    ("numbered_variables", rx(r"^\s*\w+_\d+\s*=", re.M)),
    ("colon_separated", rx(r"=[^\s=]*:[^\s=]*:")),
    ("comma_separated", rx(r"=[^\s=]*,[^\s=]*")),
    ("space_separated", rx(r'=\s*"[^"\n]+\s+[^"\n]+"')),
)

# fmt-0123 env_var_nesting -------------------------------------------------

spec(
    "env_var_nesting",
    ("json_blob_var", rx(r"^\s*\w+\s*=\s*'?\{", re.M)),
    ("double_underscore", rx(r"^\s*[A-Z][A-Z0-9]*(?:__[A-Z0-9]+)+\s*=", re.M)),
    ("dotted_lower", rx(r"^\s*[a-z][\w]*(?:\.[a-z][\w]*)+\s*=", re.M)),
    ("camel_joined", rx(r"^\s*[a-z]+(?:[A-Z][a-z0-9]*)+\s*=", re.M)),
    ("single_underscore", rx(r"^\s*[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\s*=", re.M)),
)

# --- fmt-0213 policy_directive_separator: every separator present is found and more than one kind is 'other'. An ordered list tested the blank line first, so framing around the header won `double_newline` whatever the header used ---


def _policy_directive_separator(text: str) -> str:
    body = unwrap(text)
    found = set()
    if re.search(r"\S[ \t]*\n[ \t]*\n[ \t]*\S", body):
        found.add("double_newline")
    if re.search(r";[ \t]*\n", body):
        found.add("semicolon_newline")
    if re.search(r";[ \t]+\S", body):
        found.add("semicolon_space")
    if re.search(r"\S[ \t]*\|[ \t]*\S", body):
        found.add("pipe_symbol")
    # A row of short directives, not a sentence that happens to hold a comma.
    if short_fields(first_line(body), r","):
        found.add("comma_delimited")
    return found.pop() if len(found) == 1 else UNRESOLVED


fn_spec(
    "policy_directive_separator",
    ["double_newline", "semicolon_newline", "semicolon_space", "pipe_symbol",
     "comma_delimited"],
    _policy_directive_separator,
)

# fmt-0221 env_file_quote_convention ---------------------------------------

spec(
    "env_file_quote_convention",
    ("export_prefix", rx(r"^\s*export\s+\w+=", re.M)),
    ("escaped_newlines", rx(r'=\s*"[^"\n]*\\n')),
    ("double_quoted", rx(r'^\s*\w+\s*=\s*"[^"\n]*"\s*$', re.M)),
    ("single_quoted", rx(r"^\s*\w+\s*=\s*'[^'\n]*'\s*$", re.M)),
    ("unquoted_plain", rx(r"^\s*\w+\s*=\s*[^\s'\"][^\n]*$", re.M)),
)

# fmt-0223 graphql_enum_naming_case ----------------------------------------

def _graphql_enum(text: str) -> str:
    """GraphQL enum member casing.
    `prefixed_upper` is not a per-member property -- `IN_PROGRESS` and `STATUS_IN_PROGRESS`
    are both SCREAMING_SNAKE. What distinguishes it is a shared leading segment across
    members, so the members are compared with each other."""
    members = re.findall(r"^\s{2,}([A-Za-z_]\w*)\s*$", text, re.M)
    if not members:
        members = re.findall(r"(?<![\w\"])([A-Za-z_]\w*)(?=\s*[,\n])", text)
    members = [m for m in members if m not in {"enum"}]
    if len(members) < 2:
        return UNRESOLVED

    def all_match(pat: str) -> bool:
        return all(re.fullmatch(pat, m) for m in members)

    if all_match(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+"):
        heads = {m.split("_", 1)[0] for m in members}
        return "prefixed_upper" if len(heads) == 1 else "screaming_snake"
    if all_match(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+"):
        return "lowercase_snake"
    if all_match(r"(?:[A-Z][a-z0-9]*){2,}"):
        return "upper_camel"
    if all_match(r"[a-z]+(?:[A-Z][a-z0-9]*)+"):
        return "lower_camel"
    return UNRESOLVED


fn_spec(
    "graphql_enum_naming_case",
    ["screaming_snake", "upper_camel", "lower_camel", "prefixed_upper", "lowercase_snake"],
    _graphql_enum,
)

# --- fmt-0224 server_variable_placeholder_syntax: `{{host}}` contains `{host}`, so double curly must be tested first ---

spec(
    "server_variable_placeholder_syntax",
    ("double_curly", rx(r"\{\{\s*\w+\s*\}\}")),
    ("dollar_curly", rx(r"\$\{\s*\w+\s*\}")),
    ("angle_brackets", rx(r"<\s*\w+\s*>")),
    ("colon_prefix", rx(r"(?<![\w:])/:\w+|(?<=/):\w+")),
    ("single_curly", rx(r"(?<!\{)\{\s*\w+\s*\}(?!\})")),
)

# fmt-0233 isbn_hyphenation_formatting -------------------------------------

spec(
    "isbn_hyphenation_formatting",
    ("urn_isbn_uri", rx(r"urn:isbn:[\d-]{10,17}", re.I)),
    ("thirteen_hyphenated", rx(r"(?<![\d-])97[89](?:-\d+){3,4}(?![\d-])")),
    ("ten_hyphenated", rx(r"(?<![\d-])\d(?:-\d+){2,3}-[\dXx](?![\d-])")),
    ("thirteen_unhyphenated", rx(r"(?<![\dXx-])97[89]\d{10}(?![\dXx-])")),
    ("ten_unhyphenated", rx(r"(?<![\dXx-])\d{9}[\dXx](?![\dXx-])")),
)

# fmt-0237 display_aspect_ratio_notation -----------------------------------

spec(
    "display_aspect_ratio_notation",
    ("pixel_dimensions", rx(r"\b\d{3,5}\s*[x×]\s*\d{3,5}\b", re.I)),
    ("marketing_named_preset", rx(r"\b(?:widescreen|ultrawide|academy|cinemascope|"
                                  r"anamorphic|standard|full ?screen)\b", re.I)),
    ("fractional_expression", rx(r"\b\d{1,2}\s*/\s*\d{1,2}\b")),
    # `1.78:1` CONTAINS `78:1`, so the decimal form is tested before the integer one. Found by fixture, not by reading.
    ("decimal_to_one", rx(r"\d\.\d{1,2}\s*:\s*1(?!\d)")),
    ("integer_colon_ratio", rx(r"(?<![\d.])\d{1,2}\s*:\s*\d{1,2}(?!\d)")),
)
