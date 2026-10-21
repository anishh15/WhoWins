"""Value-rendering axes -- how one datum is written down (fmt-0031..0059).
Beside `surface.py`: same job, but the label comes from a CLOSED VOCABULARY rather than
from shape alone, so every composite form is tested before the bare one it contains."""

from __future__ import annotations

import re

from ..core import UNRESOLVED
from ._lib import (
    COMMON_WORDS,
    first_body,
    fn_spec,
    looks_like_sentence,
    rx,
    spec,
    vocab,
)


def _token_in(words: frozenset[str], *, drop_common: bool = True):
    """Predicate: some standalone alphabetic token of the text is in `words`.
    Tokens split on non-letters, so `pt` is found inside `pt-BR` too. Safe only because every
    composite form is tested BEFORE the bare one."""

    def pred(s: str) -> bool:
        for t in re.findall(r"[A-Za-z]+", s):
            if t in words and not (drop_common and t.lower() in COMMON_WORDS):
                return True
        return False

    return pred


# --- fmt-0031  language_tag ---

_LANG2 = vocab("""
af am ar az be bg bn bs ca cs cy da de el en es et eu fa fi fr ga gl gu he hi
hr hu hy id is it ja ka kk km kn ko ky lo lt lv mk ml mn mr ms mt my ne nl no
pa pl pt ro ru si sk sl so sq sr sv sw ta te th tl tr uk ur uz vi zh zu
""")

_LANG3 = vocab("""
afr amh ara aze bel bul ben bos cat ces cym dan deu ell eng spa est eus fas fin
fra gle glg guj heb hin hrv hun hye ind isl ita jpn kat kaz khm kan kor kir lao
lit lav mkd mal mon mar msa mlt mya nep nld nor pan pol por ron rus sin slk slv
som sqi srp swe swa tam tel tha tgl tur ukr urd uzb vie zho zul
""")

_LANG_NAMES = vocab("""
Afrikaans Amharic Arabic Azerbaijani Belarusian Bulgarian Bengali Bosnian
Catalan Czech Welsh Danish German Greek English Spanish Estonian Basque Persian
Finnish French Irish Galician Gujarati Hebrew Hindi Croatian Hungarian Armenian
Indonesian Icelandic Italian Japanese Georgian Kazakh Khmer Kannada Korean
Kyrgyz Lao Lithuanian Latvian Macedonian Malayalam Mongolian Marathi Malay
Maltese Burmese Nepali Dutch Norwegian Punjabi Polish Portuguese Romanian
Russian Sinhala Slovak Slovenian Somali Albanian Serbian Swedish Swahili Tamil
Telugu Thai Tagalog Turkish Ukrainian Urdu Uzbek Vietnamese Chinese Zulu
""")

_L2 = "|".join(sorted(_LANG2))

spec(
    "language_tag",
    # Both composites CONTAIN the bare subtag, so both are tested before it -- fmt-0031's exclusivity field names exactly this.
    ("hyphen_region", rx(rf"(?<![A-Za-z])(?:{_L2})-[A-Z]{{2}}(?![A-Za-z])")),
    ("underscore_locale", rx(rf"(?<![A-Za-z])(?:{_L2})_[A-Z]{{2}}(?![A-Za-z])")),
    ("english_name", _token_in(_LANG_NAMES)),
    # Three letters before two: keeping the longer code first keeps the pair ordered the way every other abbreviation key is.
    ("three_letter", _token_in(_LANG3)),
    ("two_letter", _token_in(_LANG2)),
)

# --- fmt-0032 country_code_style: the two alpha-2 forms are the same letters in different case, so every test is case SENSITIVE and a mixed-case `De` matches none ---

_CC2 = vocab("""
ae ar at au be bd bg br ca ch cl cn co cr cz de dk do eg es et fi fr gb gh gr
hk hr hu id ie il in iq ir is it jp ke kr kw kz lk lt lu lv ma mx my ng nl no
nz pe ph pk pl pt qa ro rs ru sa se sg si sk th tn tr tw ua ug us uy uz ve vn
za
""")

_CC3 = vocab("""
ARE ARG AUT AUS BEL BGD BGR BRA CAN CHE CHL CHN COL CRI CZE DEU DNK DOM EGY ESP
ETH FIN FRA GBR GHA GRC HKG HRV HUN IDN IRL ISR IND IRQ IRN ISL ITA JPN KEN KOR
KWT KAZ LKA LTU LUX LVA MAR MEX MYS NGA NLD NOR NZL PER PHL PAK POL PRT QAT ROU
SRB RUS SAU SWE SGP SVN SVK THA TUN TUR TWN UKR UGA USA URY UZB VEN VNM ZAF
""")

COUNTRY_NAMES = vocab("""
Argentina Australia Austria Bangladesh Belgium Brazil Bulgaria Canada Chile
China Colombia Croatia Czechia Denmark Egypt Estonia Ethiopia Finland France
Germany Ghana Greece Hungary Iceland India Indonesia Iran Iraq Ireland Israel
Italy Japan Kazakhstan Kenya Kuwait Latvia Lithuania Luxembourg Malaysia Mexico
Morocco Netherlands Nigeria Norway Pakistan Peru Philippines Poland Portugal
Qatar Romania Russia Serbia Singapore Slovakia Slovenia Spain Sweden
Switzerland Taiwan Thailand Tunisia Turkey Uganda Ukraine Uruguay Uzbekistan
Venezuela Vietnam
""")


def _country_code(text: str) -> str:
    toks = re.findall(r"[A-Za-z]+", text)
    if any(t in _CC3 for t in toks):
        return "alpha3_upper"
    if any(t.lower() in _CC2 and t.isupper() for t in toks):
        return "alpha2_upper"
    if any(t in _CC2 and t.lower() not in COMMON_WORDS for t in toks):
        return "alpha2_lower"
    if any(t in COUNTRY_NAMES for t in toks):
        return "english_name"
    # A bare three-digit run, last: it is the loosest evidence in the set.
    if re.search(r"(?<![\d.])\d{3}(?![\d.])", text):
        return "numeric_code"
    return UNRESOLVED


fn_spec(
    "country_code_style",
    ["alpha2_upper", "alpha2_lower", "alpha3_upper", "numeric_code", "english_name"],
    _country_code,
)

# --- fmt-0039 unit_spacing: `unit_in_header` is tested LAST, because it is the only label where no unit sits beside the value, so it must be reachable only when the four in-cell forms have failed ---

_U_FULL = r"(?:milli|micro|nano)?seconds?"
_U_ABBR = r"(?:msec|usec|nsec|sec)"
_U_SHORT = r"(?:ms|us|µs|ns|s)"


def _unit_in_header(s: str) -> bool:
    header = re.search(rf"\(\s*(?:{_U_SHORT}|{_U_ABBR}|{_U_FULL})\s*\)", s, re.I)
    bare = re.search(r"(?<![\w.(])\d[\d,]*(?:\.\d+)?(?![\w.)])", s)
    return bool(header and bare)


spec(
    "unit_spacing",
    ("full_word", rx(rf"\d[\d,.]*\s*{_U_FULL}\b", re.I)),
    ("abbreviated_word", rx(rf"\d[\d,.]*\s*{_U_ABBR}(?![a-z])", re.I)),
    ("suffix_spaced", rx(rf"\d[\d,.]*\s+{_U_SHORT}(?![A-Za-z])")),
    ("suffix_tight", rx(rf"\d[\d,.]*{_U_SHORT}(?![A-Za-z])")),
    ("unit_in_header", _unit_in_header),
)

# --- fmt-0040  change_expression ---

spec(
    "change_expression",
    # The bracketed form CONTAINS a signed percentage, so it is read first.
    ("percent_in_parens", rx(r"\(\s*[+-]?\d[\d,]*(?:\.\d+)?\s*%\s*\)")),
    ("arrow_pair", rx(r"\d[\d,]*(?:\.\d+)?\s*(?:→|->|⇒)\s*\d")),
    ("growth_multiple", rx(r"\d(?:\.\d+)?\s*[x×](?![A-Za-z0-9])")),
    ("signed_percent", rx(r"[+−-]\d[\d,]*(?:\.\d+)?\s*%")),
    ("signed_absolute", rx(r"[+−-]\d[\d,]*(?:\.\d+)?(?!\s*%)")),
)

# --- fmt-0046 large_number_style: both grouped forms use a comma, so the label reads the GROUP SIZES rather than the separator; the Indian form is first because its trailing groups are the unusual ones ---

spec(
    "large_number_style",
    ("scientific", rx(r"\d(?:\.\d+)?[eE][+-]?\d+\b")),
    ("word_scale", rx(r"\d(?:\.\d+)?\s*(?:thousand|million|billion|trillion|lakh|crore)\b", re.I)),
    ("si_suffix", rx(r"\d(?:\.\d+)?\s?[KMGBT](?![A-Za-z0-9])")),
    ("indian_grouping", rx(r"(?<![\d,])\d{1,2}(?:,\d{2})+,\d{3}(?![\d,])")),
    ("western_grouping", rx(r"(?<![\d,])\d{1,3}(?:,\d{3})+(?![\d,])")),
)

# --- fmt-0047  shell_prompt ---

_PROMPT_CHAR = {"$": "dollar_prompt", "#": "hash_prompt",
                ">": "angle_prompt", "%": "percent_prompt"}


def _shell_prompt(text: str) -> str:
    """The leading character of the command lines, not any character in them.
    fmt-0047's exclusivity field asks for exactly this: a command whose own text contains a
    $ is not a $-prompted command."""
    lines = [ln for ln in first_body(text).splitlines() if ln.strip()]
    seen: set[str] = set()
    plain = 0
    for ln in lines:
        m = re.match(r"^\s*([$#>%])\s+\S", ln)
        if m:
            seen.add(_PROMPT_CHAR[m.group(1)])
        elif re.match(r"^\s*[a-z][\w.-]*(?:\s+\S+)+\s*$", ln) and not looks_like_sentence(ln):
            plain += 1
    if len(seen) == 1:
        return seen.pop()
    if seen:
        return UNRESOLVED  # two prompt characters is not a house style
    # `no_prompt` is an ABSENCE label, so two command-shaped lines are the evidence it needs.
    return "no_prompt" if plain >= 2 else UNRESOLVED


fn_spec(
    "shell_prompt",
    ["dollar_prompt", "hash_prompt", "angle_prompt", "percent_prompt", "no_prompt"],
    _shell_prompt,
)

# --- fmt-0048  param_doc_style ---

_SECTION_WORD = r"(?:Args|Arguments|Parameters|Params)"


def _param_doc(text: str) -> str:
    """How a parameter is documented, read from the doc line's own shape.
    The shapes nest, so the most specific is tested first and the list records the order."""
    if re.search(r"^[\s*#/]*@param\b", text, re.M):
        return "at_param_tags"
    if re.search(r"^[\s*#/]*:param\b", text, re.M):
        return "field_list_tags"
    if re.search(rf"^\s*{_SECTION_WORD}\s*$\n\s*[-=]{{3,}}\s*$", text, re.M | re.I):
        return "underlined_section"
    if re.search(rf"^\s*{_SECTION_WORD}\s*:\s*$\n\s+\S", text, re.M | re.I):
        return "indented_args_section"
    if re.search(rf"^\s*{_SECTION_WORD}\b", text, re.M | re.I):
        return UNRESOLVED  # a section heading in some shape we do not model
    # `prose_summary` is the absence of all four markers, so it needs positive evidence that a doc comment was written -- a one-line refusal is marker-free too.
    return "prose_summary" if len(re.findall(r"[A-Za-z][A-Za-z']+", text)) >= 12 else UNRESOLVED


fn_spec(
    "param_doc_style",
    ["field_list_tags", "indented_args_section", "underlined_section",
     "at_param_tags", "prose_summary"],
    _param_doc,
)

# --- fmt-0049  branch_name_style ---

_BRANCH_TYPES = vocab("""
feat feature fix bugfix hotfix chore docs doc refactor test tests perf ci build
release spike revert style wip
""")


def _branch_one(t: str) -> str | None:
    if re.match(r"^\d{4}-\d{2}-\d{2}-\w", t):
        return "dated_prefix"
    if re.match(r"^[A-Z]{2,10}-\d+-\w", t):
        return "ticket_key_first"
    head, sep, rest = t.partition("/")
    if sep and rest:
        # Both prefixes end at the slash, so they split on the segment before it: a known type word against a short initials pair.
        if head.lower() in _BRANCH_TYPES:
            return "type_slash_prefix"
        if re.fullmatch(r"[a-z]{2,3}", head):
            return "initials_prefix"
        return None
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", t):
        return "bare_slug"
    return None


def _branch_name(text: str) -> str:
    for t in re.findall(r"(?<![\w./-])\w[\w./-]*\w", text):
        if "-" not in t and "/" not in t:
            continue
        hit = _branch_one(t)
        if hit:
            return hit
    return UNRESOLVED


fn_spec(
    "branch_name_style",
    ["type_slash_prefix", "ticket_key_first", "initials_prefix", "bare_slug", "dated_prefix"],
    _branch_name,
)

# --- fmt-0051  period_label ---

_MONTH_NAME = (r"(?:January|February|March|April|May|June|July|August|September|"
               r"October|November|December)")

spec(
    "period_label",
    # The fiscal marker is read first: both quarter forms end in a quarter number and would otherwise collide.
    ("fiscal_quarter", rx(r"\bFY\s?\d{2,4}\s*[-/ ]?\s*Q[1-4]\b", re.I)),
    ("calendar_quarter", rx(r"\b(?:19|20)\d{2}\s*[-/ ]?\s*Q[1-4]\b|\bQ[1-4]\s+(?:19|20)\d{2}\b")),
    ("iso_week", rx(r"\b(?:19|20)\d{2}-?W\d{1,2}\b", re.I)),
    ("month_name_year", rx(rf"\b{_MONTH_NAME}\s+(?:19|20)\d{{2}}\b")),
    ("numeric_year_month", rx(r"\b(?:19|20)\d{2}-(?:0[1-9]|1[0-2])(?![\d-])")),
)

# --- fmt-0052  bool_field_naming ---

_IDENT = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


def _bool_columns(text: str) -> list[str]:
    """Column names: JSON/YAML keys, or the leading identifier of a DDL line."""
    keys = re.findall(r'"([a-z][\w]{0,60})"\s*:', text)
    if not keys:
        keys = re.findall(r"^\s*[\"`]?([a-z][\w]{0,60})[\"`]?\s*(?::|\s+(?:BOOLEAN|BOOL|TINYINT))",
                          text, re.M | re.I)
    if not keys:
        keys = re.findall(r"^\s*[-*]?\s*([a-z][a-z0-9_]{2,60})\s*$", text, re.M)
    return keys


def _bool_field_naming(text: str) -> str:
    cols = [c for c in _bool_columns(text) if _IDENT.match(c)]
    if not cols:
        return UNRESOLVED
    labels = set()
    for c in cols:
        if c.startswith("is_"):
            labels.add("is_prefix")
        elif c.startswith("has_"):
            labels.add("has_prefix")
        elif c.endswith("_enabled"):
            labels.add("enabled_suffix")
        elif c.endswith("_flag"):
            labels.add("flag_suffix")
        else:
            # Reached only for a real lowercase identifier carrying neither prefix nor suffix. Prose never gets here, because it fails _IDENT.
            labels.add("bare_adjective")
    return labels.pop() if len(labels) == 1 else UNRESOLVED


fn_spec(
    "bool_field_naming",
    ["is_prefix", "has_prefix", "bare_adjective", "enabled_suffix", "flag_suffix"],
    _bool_field_naming,
)

# --- fmt-0059  redaction_style ---

_SECRET_KEY = re.compile(
    r"(?:pass(?:word|wd)?|secret|token|api[_-]?key|credential|private[_-]?key)", re.I
)


def _redaction(text: str) -> str:
    # last_four before full_mask: keeping four characters leaves a mask run in front of them, which a full-mask test would match.
    if re.search(r"[*x•●]{3,}\s*[A-Za-z0-9]{4}(?![A-Za-z0-9])", text):
        return "last_four"
    if re.search(r"[*x•●]{4,}", text):
        return "full_mask"
    if re.search(r"\b(?:REDACTED|MASKED|HIDDEN|SCRUBBED|SANITIZED)\b", text, re.I):
        return "fixed_token"
    if re.search(r"(?<![0-9A-Za-z])[0-9a-f]{8,64}(?![0-9A-Za-z])", text):
        return "hash_digest"
    # `field_omitted` is an ABSENCE label, so it needs three or more settings with no secret among them, or an empty response wins it.
    keys = re.findall(r"^\s*[\"']?([\w.-]+)[\"']?\s*[:=]\s*\S", text, re.M)
    if len(keys) >= 3 and not any(_SECRET_KEY.fullmatch(k) for k in keys):
        return "field_omitted"
    return UNRESOLVED


fn_spec(
    "redaction_style",
    ["full_mask", "last_four", "fixed_token", "hash_digest", "field_omitted"],
    _redaction,
)
