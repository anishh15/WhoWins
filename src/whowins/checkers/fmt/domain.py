"""Specialist-notation axes -- fmt-0211..0240.
The most mechanical keys in the family: each label is a real notation from a real trade,
with genuinely disjoint orthographies. The hazard is that an ordinary word can look like
one, so the notation is located first and only then read."""

from __future__ import annotations

import re

from ..core import UNRESOLVED
from ._lib import COMMON_WORDS, first_body, fn_spec, rx, spec, unwrap

# --- fmt-0211 network_generation_notation: `Band-4G` CONTAINS `4G`, so the band-prefixed form is tested first or it could never be reported ---

spec(
    "network_generation_notation",
    ("band_prefix", rx(r"\bBand[-_ ]?\d?G?\b|\bClass[-_ ]?\d\b", re.I)),
    ("generation_prefix", rx(r"\bGen[-_ ]?\d\b", re.I)),
    ("cellular_standard", rx(r"\b(?:LTE|LTE-A|UMTS|HSPA\+?|GSM|CDMA|WCDMA|EDGE|GPRS|NR)\b")),
    ("short_numeric", rx(r"(?<![\w.])[2-6]G(?![\w])")),
    # An ordinal is a tier when it says so, or stands alone as the value. Any ordinal used to count made "after the second attempt" report a network.
    ("spelled_ordinal", rx(r"\b(?:second|third|fourth|fifth|sixth)[- ]gen(?:eration)?\b|"
                           r"(?:^|:)[ \t]*(?:second|third|fourth|fifth|sixth)[ \t]*\.?[ \t]*$",
                           re.I | re.M)),
)

# --- fmt-0212  bounding_box_syntax ---

spec(
    "bounding_box_syntax",
    ("wkt_polygon", rx(r"\bPOLYGON\s*\(\(", re.I)),
    # Keyed before the bare tuple: a GeoJSON bbox IS a four-element array, so only the key name separates them.
    ("geojson_bbox", rx(r"[\"']bbox[\"']\s*:\s*\[")),
    ("corner_pair", rx(r"\b(?:sw|southwest|south_west)\b.{0,80}?\b(?:ne|northeast|north_east)\b",
                       re.I | re.S)),
    ("center_span", rx(r"\b(?:cent(?:er|re))\b.{0,80}?\b(?:span|width|height|delta|radius)\b",
                       re.I | re.S)),
    ("tuple_array", rx(r"[\[(]\s*-?\d+(?:\.\d+)?\s*(?:,\s*-?\d+(?:\.\d+)?\s*){3}[\])]")),
)

# --- fmt-0214  cipher_suite_naming_standard ---

spec(
    "cipher_suite_naming_standard",
    ("iana_standard", rx(r"\bTLS_[A-Z0-9]+(?:_[A-Z0-9]+)+\b")),
    ("gnutls_keyword", rx(r"\+(?:VERS|AES|SHA|ECDHE|RSA|COMP|CTYPE|MAC|CIPHER)[-\w]*|"
                          r"\bNORMAL\s*:")),
    ("hexadecimal_id", rx(r"0x[0-9A-Fa-f]{2}\s*,\s*0x[0-9A-Fa-f]{2}|0x[0-9A-Fa-f]{4}\b")),
    # Three or more hyphen-joined upper-case groups. Two groups is `AES-128`, which the verbose form also writes.
    ("openssl_shorthand", rx(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+){2,}\b")),
    ("rfc_verbose", lambda s: bool(
        re.search(r"\b(?:key exchange|authentication|encryption|message authentication|"
                  r"in\s+\w+\s+mode)\b", s, re.I)) and len(s.split()) >= 8),
)

# --- fmt-0215  timer_schedule_expression ---

spec(
    "timer_schedule_expression",
    ("monotonic_time", rx(r"\bOn(?:Boot|Startup|UnitActive|UnitInactive)Sec\s*=", re.I)),
    # Tested before the frequency word: `OnCalendar=daily` is a calendar event, not a bare cadence word.
    ("calendar_event", rx(r"\bOnCalendar\s*=|\*-\*-\*|"
                          r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.\.(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b")),
    ("crontab_fields", rx(r"^\s*[\d*/,-]+\s+[\d*/,-]+\s+[\d*/,-]+\s+[\d*/,-]+\s+[\d*/,-]+\s*$",
                          re.M)),
    ("relative_span", rx(r"\bevery\s+(?:\d+|one|two|three|four|six|eight|twelve|twenty[- ]four)\s+"
                         r"(?:second|minute|hour|day|week|month)s?\b", re.I)),
    ("frequency_word", rx(r"\b(?:daily|hourly|weekly|monthly|yearly|annually|nightly|quarterly)\b",
                          re.I)),
)

# --- fmt-0216  channel_layout_notation ---

spec(
    "channel_layout_notation",
    ("point_surround", rx(r"(?<![\d.])[1-9]\.[0-9](?:\.[0-9])?(?![\d.])")),
    ("channel_count_suffix", rx(r"\b\d{1,2}\s*(?:ch|channels?)\b", re.I)),
    ("positional_acronyms", rx(r"\b(?:FL|FR|FC|LFE|SL|SR|BL|BR|TFL|TFR)\b"
                               r"[\s,]+\b(?:FL|FR|FC|LFE|SL|SR|BL|BR|TFL|TFR)\b")),
    ("matrix_pair", rx(r"\b\d{1,2}\s*(?:x|×|by)\s*\d{1,2}\b", re.I)),
    ("descriptive_word", rx(r"\b(?:surround|stereo|monaural|mono|quadraphonic|binaural|"
                            r"ambisonic)\b", re.I)),
)

# --- fmt-0217 financial_institution_identifier: a sort code and a CHIPS UID are BOTH six digits, so length cannot separate them whatever the exclusivity field says; the sort code's pair hyphenation is the only thing in the string that differs ---

spec(
    "financial_institution_identifier",
    # Eleven before eight: the eight-character BIC is a literal prefix of the eleven-character one.
    ("bic_eleven", rx(r"\b[A-Z]{6}[A-Z0-9]{2}[A-Z0-9]{3}\b")),
    ("bic_eight", rx(r"\b[A-Z]{6}[A-Z0-9]{2}\b")),
    ("national_sort", rx(r"\b\d{2}-\d{2}-\d{2}\b")),
    ("fedwire_aba", rx(r"(?<![\d-])\d{9}(?![\d-])")),
    ("chips_uid", rx(r"(?<![\d-])\d{6}(?![\d-])")),
)

# --- fmt-0218 legal_statute_citation_style: `Sec.` is tested before `Section`, since the abbreviation is a prefix and only the trailing period tells them apart ---

spec(
    "legal_statute_citation_style",
    ("section_symbol", rx(r"§")),
    ("paragraph_mark", rx(r"¶")),
    ("abbreviated_sec", rx(r"\bSecs?\.\s*\d", re.I)),
    ("spelled_section", rx(r"\bSections?\s+\d", re.I)),
    ("parenthetical_clause", rx(r"\(\s*\d+\s*\)\s*\(\s*[a-zA-Z0-9]+\s*\)")),
)

# --- fmt-0219  intermodal_container_notation ---

_OWNER = r"[A-Z]{4}"

spec(
    "intermodal_container_notation",
    ("bracketed_check", rx(rf"\b{_OWNER}\s?\d{{6}}\s?\[\s?\d\s?\]")),
    ("hyphenated_check", rx(rf"\b{_OWNER}\s?\d{{6}}-\d(?!\d)")),
    ("slash_partitioned", rx(rf"\b{_OWNER}\s?/\s?\d{{6,7}}(?!\d)")),
    ("spaced_groups", rx(rf"\b{_OWNER}\s+\d{{6}}\s+\d(?!\d)")),
    ("iso_continuous", rx(rf"\b{_OWNER}\d{{7}}(?![\d])")),
)

# --- fmt-0220  electrical_power_unit_presentation ---

spec(
    "electrical_power_unit_presentation",
    ("volt_ampere_apparent", rx(r"\b\d[\d,]*(?:\.\d+)?\s*[kMG]?VA\b")),
    ("gigawatt_symbol", rx(r"\b\d[\d,]*(?:\.\d+)?\s*GW\b")),
    ("megawatt_decimal", rx(r"\b\d[\d,]*\.\d+\s*MW\b")),
    ("kilowatt_integer", rx(r"\b\d[\d,]*\s*kW\b")),
    ("scientific_watts", rx(r"\d(?:\.\d+)?\s*(?:[eE][+-]?\d+|[x×]\s*10\s*\^?\s*\d+)\s*W\b")),
)

# --- fmt-0225  volume_mount_specification_style ---


def _volume_mount(text: str) -> str:
    """The short and named forms are the same `left:right` shape, so the LEFT
    side decides: a filesystem path is a bind mount, a bare identifier is a
    named volume reference. That is the only thing separating them."""
    body = first_body(text)
    if re.search(r"\btmpfs\b", body, re.I):
        return "tmpfs_memory_clause"
    if re.search(r"^\s*-?\s*type\s*:\s*\w+", body, re.M | re.I) and \
            re.search(r"^\s*(?:source|target)\s*:", body, re.M | re.I):
        return "long_key_value"
    pairs = re.findall(r"^\s*-\s*[\"']?([^\s:\"']+)\s*:\s*(/[^\s:\"']+)", body, re.M)
    if pairs:
        left = pairs[0][0]
        return "short_colon_syntax" if left[0] in "/.~$" else "named_volume_ref"
    if re.search(r"^\s*-\s*[\"']?/[\w./-]+[\"']?\s*$", body, re.M):
        return "anonymous_volume"
    return UNRESOLVED


fn_spec(
    "volume_mount_specification_style",
    ["short_colon_syntax", "long_key_value", "anonymous_volume",
     "named_volume_ref", "tmpfs_memory_clause"],
    _volume_mount,
)

# --- fmt-0226  security_label_context_format ---

_ALIAS = r"(?:unconfined|default_context|initrc_context|user_context|system_context|failsafe)"


def _security_label(text: str) -> str:
    """Segment COUNT decides between the two tuple forms, so the tuple is found
    first and its colons are counted -- a five-part label contains a four-part
    prefix, so testing four first would make five unreachable."""
    m = re.search(r"\b[\w.-]+(?::[\w.,:-]*[\w.,-])+\b", text)
    if m:
        parts = m.group(0).split(":")
        if len(parts) >= 5:
            return "five_part_mls"
        if len(parts) == 4:
            return "four_part_colon"
    if re.search(rf"\b{_ALIAS}\b", text, re.I):
        return "alias_keyword"
    if re.search(r"\b\w+_t\b", text):
        return "type_only_shorthand"
    if re.search(r"(?<![\w.])\d{1,6}(?![\w.])", text):
        return "raw_numeric_sid"
    return UNRESOLVED


fn_spec(
    "security_label_context_format",
    ["four_part_colon", "five_part_mls", "type_only_shorthand",
     "raw_numeric_sid", "alias_keyword"],
    _security_label,
)

# --- fmt-0227 sql_null_precedence_clause: a CASE rank CONTAINS the literal `IS NULL` the boolean form is detected by, so CASE is tested first and boolean last; the two NULLS literals are disjoint and come ahead of both ---

spec(
    "sql_null_precedence_clause",
    ("nulls_first", rx(r"\bNULLS\s+FIRST\b", re.I)),
    ("nulls_last", rx(r"\bNULLS\s+LAST\b", re.I)),
    ("case_expression_rank", rx(r"\bCASE\s+WHEN\b", re.I)),
    ("coalesce_fallback", rx(r"\bCOALESCE\s*\(", re.I)),
    ("is_null_boolean", rx(r"\bIS\s+(?:NOT\s+)?NULL\b", re.I)),
)

# --- fmt-0229  columnar_file_compression_codec ---

spec(
    "columnar_file_compression_codec",
    ("zstd_level_tuned", rx(r"\bzstd\b", re.I)),
    ("snappy_standard", rx(r"\bsnappy\b", re.I)),
    ("gzip_compatible", rx(r"\bgzip\b", re.I)),
    ("lz4_raw_block", rx(r"\blz4(?:_raw)?\b", re.I)),
    # `none` is a real Parquet codec name, not an absence: granted only where written as the value of a compression setting.
    ("uncompressed_none", rx(r"\bUNCOMPRESSED\b|"
                             r"\bcompression\b[^\n]{0,20}[:=]\s*[\"']?(?:none|uncompressed)\b",
                             re.I)),
)

# --- fmt-0230  playbook_step_description_style ---

_STEP_VERB = (r"(?:Upgrade|Run|Apply|Migrate|Back|Restore|Verify|Stop|Start|Drain|Restart|"
              r"Check|Deploy|Rotate|Snapshot|Promote|Disable|Enable|Create|Drop)")

spec(
    "playbook_step_description_style",
    ("ticket_prefixed_tag", rx(r"^\s*[A-Z]{2,10}-\d+\s*[:\-]\s*\S", re.M)),
    ("action_noun_bracketed", rx(r"^\s*\[[A-Za-z][\w /-]{0,20}\]\s*\S", re.M)),
    ("hierarchical_dot_path", rx(r"^\s*[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\s*$", re.M)),
    ("imperative_verb", rx(rf"^\s*{_STEP_VERB}\b", re.M)),
    ("lowercase_phrase", rx(r"^\s*[a-z][a-z ]{6,60}$", re.M)),
)

# --- fmt-0231  academic_grade_notation ---

spec(
    "academic_grade_notation",
    ("descriptive_honors", rx(r"\b(?:summa|magna)?\s*cum laude\b|\bwith (?:distinction|honou?rs)\b",
                              re.I)),
    ("percentage_integer", rx(r"\b\d{1,3}\s*%")),
    ("four_point_gpa", rx(r"(?<![\d.])[0-4]\.\d{1,2}(?![\d.])")),
    # A bare capital letter is far too common in prose to be a grade, so the modifier or an explicit label is required.
    ("letter_grade_modifier", rx(r"(?<![\w+-])[A-F][+-](?![\w+-])|"
                                 r"\bgrade\b[^\n]{0,10}?(?<![\w])[A-F](?![\w])", re.I)),
    ("pass_fail_binary", rx(r"\b(?:pass|fail|passed|failed)\b", re.I)),
)

# --- fmt-0232 product_barcode_symbology_scheme: the three numeric forms are separated by LENGTH alone, tested longest first and fenced by digit lookarounds ---

spec(
    "product_barcode_symbology_scheme",
    ("qr_matrix_uri", rx(r"https?://\S+")),
    ("itf_fourteen_digit", rx(r"(?<!\d)\d{14}(?!\d)")),
    ("ean_thirteen_digit", rx(r"(?<!\d)\d{13}(?!\d)")),
    ("upc_twelve_digit", rx(r"(?<!\d)\d{12}(?!\d)")),
    ("code_one_twenty_eight", lambda s: any(
        re.search(r"[A-Z]", t) and re.search(r"\d", t)
        for t in re.findall(r"(?<![\w-])[A-Z0-9]{6,24}(?![\w-])", s))),
)

# --- fmt-0234  prescription_frequency_convention ---

spec(
    "prescription_frequency_convention",
    ("latin_sig_abbreviation", rx(r"(?<![\w])(?:bid|tid|qid|qd|qhs|prn|ac|pc|q\d+h)(?![\w])",
                                  re.I)),
    ("hourly_interval_phrase", rx(r"\bevery\s+(?:\d+|two|three|four|six|eight|twelve|"
                                  r"twenty[- ]four)\s+hours?\b", re.I)),
    ("daily_count_words", rx(r"\b(?:once|twice|thrice|\d+|two|three|four)\s+times?\s+"
                             r"(?:a|per|each)\s+day\b|\b(?:once|twice)\s+daily\b", re.I)),
    ("mealtime_relative", rx(r"\b(?:before|after|with)\s+(?:meals?|food|breakfast|lunch|dinner)\b",
                             re.I)),
    ("specific_clock_times", rx(r"\b\d{1,2}(?::\d{2})?\s*(?:AM|PM|a\.m\.|p\.m\.)\b|"
                                r"\b(?:eight|nine|ten|eleven|twelve|noon|midnight)\s*"
                                r"(?:AM|PM|a\.m\.|p\.m\.)\b", re.I)),
)

# --- fmt-0235  promotional_code_spelling_pattern ---

_VOUCHER = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
_VOUCHER_SHAPES = (
    ("hyphenated_word_pairs", re.compile(r"[A-Za-z]{3,}-[A-Za-z]{3,}")),
    ("number_prefixed_tag", re.compile(r"\d{1,3}[A-Za-z]{3,}")),
    ("mixed_alphanumeric_hex", re.compile(r"(?=.*[A-Z])(?=.*\d)[A-Z0-9]{5,}")),
    ("all_caps_word", re.compile(r"[A-Z]{4,}")),
    ("lowercase_keyword", re.compile(r"[a-z]{4,14}")),
)
_ON_ITS_OWN = re.compile(rf"^[ \t]*(?:[-*][ \t]+)?[`\"*_“]*({_VOUCHER})[`\"*_”]*\.?[ \t]*$", re.M)
_SET_APART = re.compile(rf"`({_VOUCHER})`|\"({_VOUCHER})\"|“({_VOUCHER})”|\*\*({_VOUCHER})\*\*")
_LABELLED = re.compile(rf"\b(?:code|voucher|coupon)(?:[ \t]+(?:code|string))?[ \t]*[:=][ \t]*"
                       rf"[`\"*“]*({_VOUCHER})", re.I)
_AFTER_CODE = re.compile(rf"\bcode[ \t]+({_VOUCHER})\b", re.I)


def _voucher_candidates(text: str) -> list[str]:
    body = unwrap(text)
    found = _ON_ITS_OWN.findall(body)
    found += [next(g for g in m.groups() if g) for m in _SET_APART.finditer(body)]
    found += _LABELLED.findall(body)
    if found:
        return found
    # Only then the word after "code", and not one that reads as a verb.
    return [t for t in _AFTER_CODE.findall(body)
            if t.lower() not in COMMON_WORDS and not re.fullmatch(r"[a-z]+(?:s|ed|ing)", t)]


def _promotional_code_spelling_pattern(text: str) -> str:
    """The voucher is found first, and only then is its shape read.
    Every shape here is also what some ordinary word looks like -- a lower-case run is any
    English word, a hyphenated pair is "one-time" -- so searching the whole text for the
    shape would label the prose instead of the code."""
    labels = set()
    for token in _voucher_candidates(text):
        for label, shape in _VOUCHER_SHAPES:
            if shape.fullmatch(token):
                if not (label == "lowercase_keyword" and token in COMMON_WORDS):
                    labels.add(label)
                break
    return labels.pop() if len(labels) == 1 else UNRESOLVED


fn_spec(
    "promotional_code_spelling_pattern",
    ["hyphenated_word_pairs", "number_prefixed_tag", "mixed_alphanumeric_hex",
     "all_caps_word", "lowercase_keyword"],
    _promotional_code_spelling_pattern,
)

# --- fmt-0236  work_authorization_category_code ---

spec(
    "work_authorization_category_code",
    ("official_code_hyphen", rx(r"(?<![\w-])[A-Z]{1,2}-\d[A-Z]?(?![\w-])")),
    ("numeric_regulation_statute", rx(r"\b\d+\s*U\.?S\.?C\.?\s*§?\s*\d+|\b\d+\s*C\.?F\.?R\.?\s*"
                                      r"§?\s*\d+|§\s*\d+")),
    ("popular_letter_only", rx(r"(?<![\w-])[A-Z]\d[A-Z]?(?![\w-])")),
    ("descriptive_program_title", rx(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){2,}\b")),
    ("general_eligibility_phrase", rx(r"\b(?:authoris|authoriz|permitted|eligible|entitled)\w*\s+"
                                      r"to\s+work\b|\bright to work\b", re.I)),
)

# --- fmt-0238  city_state_postal_arrangement ---


def _city_state_postal(text: str) -> str:
    """The country-prefixed form is caught BEFORE the permutation is read.
    A country ISO code and a state abbreviation are both bare two-letter upper-case tokens,
    so the permutation reader cannot tell them apart."""
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if not line:
        return UNRESOLVED
    kinds: list[str] = []
    for t in re.findall(r"[A-Za-z]{2,}|\d{5}(?:-\d{4})?", line):
        if re.fullmatch(r"\d{5}(?:-\d{4})?", t):
            kinds.append("zip")
        elif re.fullmatch(r"[A-Z]{2,3}", t):
            kinds.append("state")
        elif t[0].isupper():
            kinds.append("city")
        else:
            continue
    collapsed: list[str] = []
    for k in kinds:
        if not collapsed or collapsed[-1] != k:
            collapsed.append(k)
    if not collapsed:
        return UNRESOLVED
    if collapsed[0] == "state" and kinds.count("state") >= 2:
        return "country_prefixed_code"
    return {
        ("city", "state", "zip"): "city_state_zip",
        ("zip", "city", "state"): "zip_city_state",
        ("state", "city", "zip"): "state_city_zip",
        ("city", "zip", "state"): "city_zip_state",
    }.get(tuple(collapsed), UNRESOLVED)


fn_spec(
    "city_state_postal_arrangement",
    ["city_state_zip", "zip_city_state", "state_city_zip",
     "city_zip_state", "country_prefixed_code"],
    _city_state_postal,
)

# --- fmt-0239 corrective_action_entry_layout: the checkbox form CONTAINS square brackets so it is tested before both bracketed forms; the priority tag is narrower than an assignee tag ---

spec(
    "corrective_action_entry_layout",
    ("table_grid_row", rx(r"^\s*\|.*\|\s*$\n\s*\|[\s:|-]+\|\s*$", re.M)),
    ("checkbox_markdown_task", rx(r"^\s*[-*]\s*\[[ xX]\]\s+\S", re.M)),
    ("priority_tagged_bullet", rx(r"^\s*[-*]?\s*\[(?:P[0-4]|Sev-?[0-5]|SEV-?[0-5])\]\s*\S", re.M)),
    ("owner_prefixed_line", rx(r"^\s*[-*]?\s*(?:\[[A-Z][\w .-]{1,24}\]|@[\w.-]{2,24})\s*\S", re.M)),
    ("numbered_action_verb", rx(r"^\s*\d+[.)]\s+[A-Z][a-z]+\b", re.M)),
)

# --- fmt-0240  equity_symbol_exchange_qualifier ---

spec(
    "equity_symbol_exchange_qualifier",
    ("bracketed_exchange_code", rx(r"\b[A-Z]{1,5}\s*\[\s*[A-Z]{2,6}\s*\]")),
    ("colon_exchange_first", rx(r"\b[A-Z]{2,8}\s*:\s*[A-Z]{1,5}(?![\w.])")),
    ("dot_exchange_suffix", rx(r"\b[A-Z]{1,5}\.[A-Z]{1,4}(?![\w.])")),
    ("hyphen_country_suffix", rx(r"\b[A-Z]{1,5}-[A-Z]{2}(?![\w-])")),
    # Fenced by the punctuation the other four use, and at least two letters: a lone capital `I` opens too many English sentences.
    ("unqualified_ticker", rx(r"(?<![\w:.\-\[])[A-Z]{2,5}(?![\w:.\-\]])")),
)
