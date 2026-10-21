"""API and wire-protocol format axes -- drawn from fmt-0061..0110.
These read a rendered request, response or header block. Decidable because the choice
shows up as literal syntax: a status number, a header name, a media type."""

from __future__ import annotations

import re

from ..core import UNRESOLVED
from ._lib import fn_spec, fullrx, rx, spec, uniform_spec

# --- fmt-0062 / fmt-0094: the status LINE decides when there is one, because a body, header or request line can carry other numbers. The first version searched the whole text, so a 200 anywhere won `status_200_body` outright. Two disagreeing status lines are a hedge ---

_STATUS_LINE = re.compile(
    r"^[ \t]*(?:HTTP/\d(?:\.\d)?[ \t]+|Status[ \t]*:[ \t]*)(\d{3})(?!\d)", re.I | re.M
)


def _status(labels: dict[str, str]):
    """code -> label, read off the status line when there is one."""
    def fn(text: str) -> str:
        on_status_lines = set(_STATUS_LINE.findall(text))
        if on_status_lines:
            if len(on_status_lines) != 1:
                return UNRESOLVED
            return labels.get(on_status_lines.pop(), UNRESOLVED)
        found = [code for code in labels if re.search(rf"(?<!\d){code}(?!\d)", text)]
        return labels[found[0]] if len(found) == 1 else UNRESOLVED
    return fn


_DELETE_REPEAT = {"204": "status_204", "404": "status_404", "200": "status_200_body",
                  "410": "status_410", "202": "status_202"}
fn_spec("delete_repeat_status", list(_DELETE_REPEAT.values()), _status(_DELETE_REPEAT))

_MOVE_REDIRECT = {code: f"status_{code}" for code in ("301", "308", "302", "307", "303")}
fn_spec("move_redirect_status", list(_MOVE_REDIRECT.values()), _status(_MOVE_REDIRECT))

# --- fmt-0063 header_name_casing: anchored and disjoint, names extracted as `Name:` at line start ---

_HEADER_NAME = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_-]{2,40})\s*:", re.M)

uniform_spec(
    "header_name_casing",
    lambda t: _HEADER_NAME.findall(t),
    ("upper_underscore", fullrx(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+")),
    ("upper_hyphen", fullrx(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+")),
    ("title_hyphen", fullrx(r"[A-Z][a-z0-9]*(?:-[A-Z][a-z0-9]*)+")),
    ("lower_hyphen", fullrx(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+")),
    ("camel_no_separator", fullrx(r"[a-z]+(?:[A-Z][a-z0-9]*)+")),
)

# --- fmt-0064 query_array_encoding: indexed brackets before bare ones, since `tag[0]=` also contains `tag[` ---

spec(
    "query_array_encoding",
    ("indexed_bracket", rx(r"\w+\[\d+\]=")),
    ("bracket_repeat", rx(r"\w+\[\]=")),
    ("pipe_joined", rx(r"\w+=[^&\s]*\|[^&\s]*")),
    ("comma_joined", rx(r"\w+=[^&\s]*,[^&\s]*")),
    ("repeated_key", lambda s: bool(
        [k for k in set(re.findall(r"[?&](\w+)=", s))
         if len(re.findall(rf"[?&]{re.escape(k)}=", s)) > 1])),
)

# fmt-0065 query_flag_encoding ---------------------------------------------

spec(
    "query_flag_encoding",
    ("enabled_word", rx(r"\w+=(?:enabled|disabled)\b", re.I)),
    ("word_literal", rx(r"\w+=(?:true|false|yes|no)\b", re.I)),
    ("digit_literal", rx(r"\w+=[01](?![\w.])")),
    ("empty_value", rx(r"[?&]\w+=(?:&|$)")),
    ("bare_presence", rx(r"[?&]\w+(?:&|$)")),
)

# fmt-0066 api_version_placement -------------------------------------------

spec(
    "api_version_placement",
    ("media_type_parameter", rx(r"application/[\w.+-]+\s*;\s*version=", re.I)),
    ("request_header", rx(r"^\s*(?:X-)?API-?Version\s*:", re.I | re.M)),
    ("host_prefix", rx(r"https?://v\d+\.[\w.-]+")),
    ("path_prefix", rx(r"https?://[\w.-]+/v\d+/|(?<![\w.])/v\d+/")),
    ("query_parameter", rx(r"[?&](?:api[-_]?)?version=", re.I)),
)

# fmt-0067 credential_transport --------------------------------------------

spec(
    "credential_transport",
    ("bearer_scheme", rx(r"^\s*Authorization\s*:\s*Bearer\s", re.I | re.M)),
    ("token_scheme", rx(r"^\s*Authorization\s*:\s*Token\s", re.I | re.M)),
    ("basic_scheme", rx(r"^\s*Authorization\s*:\s*Basic\s", re.I | re.M)),
    ("api_key_header", rx(r"^\s*(?:X-)?API[-_]?Key\s*:", re.I | re.M)),
    ("session_cookie", rx(r"^\s*Cookie\s*:", re.I | re.M)),
)

# fmt-0072 charset_parameter -----------------------------------------------


def _charset(text: str) -> str:
    m = re.search(r"charset\s*(=)\s*(\"?)([\w-]+)\2", text, re.I)
    if not m:
        return "omitted" if re.search(r"Content-Type\s*:", text, re.I) else UNRESOLVED
    quoted, value = m.group(2), m.group(3)
    spaced = bool(re.search(r"charset\s+=|=\s+[\"\w]", m.group(0)))
    if quoted:
        return "quoted_value"
    if spaced:
        return "spaced_parameter"
    return "upper_no_space" if value.isupper() else "lower_no_space"


fn_spec(
    "charset_parameter",
    ["omitted", "lower_no_space", "upper_no_space", "spaced_parameter", "quoted_value"],
    _charset,
)

# --- fmt-0077 timestamp_precision: fractional digits counted longest first, so a nanosecond value is never read as a millisecond one sharing its prefix ---

spec(
    "timestamp_precision",
    ("nanoseconds", rx(r"\d{2}:\d{2}:\d{2}\.\d{9}(?!\d)|(?<!\d)\d{19}(?!\d)")),
    ("microseconds", rx(r"\d{2}:\d{2}:\d{2}\.\d{6}(?!\d)|(?<!\d)\d{16}(?!\d)")),
    ("milliseconds", rx(r"\d{2}:\d{2}:\d{2}\.\d{3}(?!\d)|(?<!\d)\d{13}(?!\d)")),
    ("whole_seconds", rx(r"\d{2}:\d{2}:\d{2}(?![.\d])|(?<!\d)\d{10}(?!\d)")),
    ("whole_minutes", rx(r"\d{2}:\d{2}(?![:.\d])")),
)

# fmt-0084 event_type_naming -----------------------------------------------

spec(
    "event_type_naming",
    ("screaming_snake", rx(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")),
    ("colon_scoped", rx(r"\b[a-z][\w]*(?::[a-z][\w]*)+\b")),
    ("slash_path", rx(r"\b[a-z][\w]*(?:/[a-z][\w]*)+\b")),
    ("dotted_lower", rx(r"\b[a-z][\w]*(?:\.[a-z][\w]*)+\b")),
    ("pascal_past", rx(r"\b(?:[A-Z][a-z0-9]+){2,}(?:ed|en)\b")),
)

# fmt-0090 sort_param_syntax -----------------------------------------------

spec(
    "sort_param_syntax",
    ("bracketed_direction", rx(r"sort\[[\w]+\]=", re.I)),
    ("separate_direction_param", rx(r"[?&]order=(?:asc|desc)\b", re.I)),
    ("colon_suffix", rx(r"sort=[\w]+:(?:asc|desc)\b", re.I)),
    ("spaced_string", rx(r"sort=[\w]+(?:\s|%20)(?:asc|desc)\b", re.I)),
    # Must require an actual sign and be tested LAST: the first version matched any sort value and made every other label unreachable.
    ("sign_prefix", rx(r"sort=[+-]\w", re.I)),
)

# --- fmt-0093 error_field_pointer: JSON Pointer first, or `/items/0/name` reads as a slash path ---

spec(
    "error_field_pointer",
    ("json_pointer", rx(r'"(?:/[\w~%-]+)+"|(?<![\w/])/(?:[\w-]+/)+[\w-]+(?![\w/])')),
    ("bracket_index_path", rx(r"\w+\[\d+\](?:\.\w+)*")),
    ("name_and_location", rx(r"\b(?:field|param(?:eter)?)\b.{0,20}\b(?:in|at)\b", re.I)),
    ("dotted_path", rx(r"\b[a-z_]\w*(?:\.[a-z_]\w*)+\b", re.I)),
    ("leaf_name_only", rx(r'"field"\s*:\s*"[\w]+"')),
)

# --- fmt-0097 binary_field_encoding: base64url before standard, since the url alphabet is a subset once `-` and `_` appear ---

spec(
    "binary_field_encoding",
    ("data_scheme_string", rx(r"data:[\w/+.-]+;base64,")),
    ("integer_byte_array", rx(r"\[\s*\d{1,3}\s*(?:,\s*\d{1,3}\s*){3,}\]")),
    ("base64url_unpadded", rx(r"(?<![\w+/=])[A-Za-z0-9_-]{16,}(?![\w=])")),
    ("base64_standard", rx(r"(?<![\w+/=])[A-Za-z0-9+/]{16,}={0,2}(?![\w])")),
    ("base85_compact", rx(r"<~[!-u]{8,}~>")),
)

# fmt-0104 health_status_vocabulary ----------------------------------------

spec(
    "health_status_vocabulary",
    ("up_upper", rx(r"(?<![\w])UP(?![\w])")),
    ("healthy_word", rx(r"\bhealthy\b", re.I)),
    ("pass_word", rx(r"\bpass\b", re.I)),
    ("green_word", rx(r"\bgreen\b", re.I)),
    ("ok_lower", rx(r"(?<![\w])ok(?![\w])")),
)

# fmt-0105 error_code_vocabulary -------------------------------------------

spec(
    "error_code_vocabulary",
    ("http_status_reuse", rx(r"\"?code\"?\s*[:=]\s*\"?(?:4\d{2}|5\d{2})\"?(?!\d)")),
    ("screaming_symbol", rx(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")),
    ("dotted_namespace", rx(r"\b[a-z][\w]*(?:\.[a-z][\w]*)+\b")),
    ("prefixed_alphanumeric", rx(r"\b[A-Za-z]{2,6}[-_]?\d{3,5}\b")),
    ("integer_code", rx(r"\"?code\"?\s*[:=]\s*\"?\d{1,5}\"?(?!\d)")),
)

# fmt-0106 stream_framing --------------------------------------------------

spec(
    "stream_framing",
    ("sse_blocks", rx(r"^\s*(?:event|data|id|retry)\s*:", re.M)),
    ("multipart_boundaries", rx(r"--[A-Za-z0-9'()+_,./:=?-]{6,}\s*$", re.M)),
    ("length_prefixed", rx(r"^\s*\d+\r?\n\{", re.M)),
    ("json_array_chunks", rx(r"^\s*\[\s*\{", re.M)),
    ("newline_delimited", rx(r"\}\s*\n\s*\{")),
)

# fmt-0107 time_window_parameters ------------------------------------------

spec(
    "time_window_parameters",
    ("since_until", rx(r"[?&]since=.*[?&]until=", re.I | re.S)),
    ("from_to", rx(r"[?&]from=.*[?&]to=", re.I | re.S)),
    ("start_plus_duration", rx(r"[?&]start=.*[?&](?:duration|for|window)=", re.I | re.S)),
    ("interval_string", rx(r"\d{4}-\d{2}-\d{2}[^/\s]*/\d{4}-\d{2}-\d{2}")),
    ("relative_keyword", rx(r"[?&]\w*(?:range|period|window)=(?:last|past|previous)[\w_]*", re.I)),
)

# --- fmt-0053 pagination_style: not an ordered list. A response carrying TWO mechanisms is 'other' rather than the first found, because real services ship two for compatibility ---


def _pagination(text: str) -> str:
    found = []
    if re.search(r"[?&]offset=", text, re.I) and re.search(r"[?&]limit=", text, re.I):
        found.append("offset_limit")
    if re.search(r"[?&]page=\d", text, re.I):
        found.append("page_number")
    if re.search(r"[?&](?:cursor|page_token|next_token|after)=", text, re.I):
        found.append("opaque_cursor")
    if re.search(r"^\s*Link\s*:[^\n]*\brel\s*=\s*\"?next", text, re.I | re.M):
        found.append("link_header")
    if re.search(r"^\s*Content-Range\s*:", text, re.I | re.M):
        found.append("range_header")
    return found[0] if len(found) == 1 else UNRESOLVED


fn_spec(
    "pagination_style",
    ["offset_limit", "page_number", "opaque_cursor", "link_header", "range_header"],
    _pagination,
)
