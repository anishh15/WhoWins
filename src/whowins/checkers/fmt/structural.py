"""Format keys that need a parser, not a rule table.
The 70 keys where the label is a property of a SHAPE -- a field's type, a record's key
order, a column's alignment -- and no amount of regex ordering reads a shape. Absence
still needs evidence, and a shape nesting inside another is still read outermost first."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..core import UNRESOLVED
from ._lib import first_body, fn_spec, rx, spec, unwrap

# --- Parsing helpers ---


def load_json(text: str, *, ordered: bool = False) -> Optional[Any]:
    """The first complete JSON value in the text, or None.
    Scans for a balanced container rather than trying every substring, so a fenced body with
    prose around it still parses. With `ordered`, objects come back as (key, value) pairs so
    key ORDER survives."""
    hook = (lambda pairs: pairs) if ordered else None
    body = first_body(text).strip()
    try:
        return json.loads(body, object_pairs_hook=hook)
    except Exception:
        pass
    start = next((i for i, ch in enumerate(body) if ch in "{["), None)
    if start is None:
        return None
    depth, in_string, escaped = 0, False, False
    for i in range(start, len(body)):
        ch = body[i]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(body[start:i + 1], object_pairs_hook=hook)
                except Exception:
                    return None
    return None


def as_dict(value: Any) -> Optional[dict]:
    """A parsed value as a plain dict, whether or not it kept its key order."""
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and all(
            isinstance(p, (list, tuple)) and len(p) == 2 and isinstance(p[0], str) for p in value):
        return dict(value)
    return None


def first_record(value: Any) -> Optional[list]:
    """The first object in a value, as its (key, value) pairs in written order."""
    if isinstance(value, list) and value and all(
            isinstance(p, (list, tuple)) and len(p) == 2 and isinstance(p[0], str) for p in value):
        return list(value)
    if isinstance(value, list) and value:
        return first_record(value[0])
    return None


def find_key(d: dict, *names: str) -> Optional[str]:
    lowered = {k.lower(): k for k in d}
    for n in names:
        if n in lowered:
            return lowered[n]
    return None


def body_lines(text: str) -> list[str]:
    return [ln for ln in first_body(text).splitlines() if ln.strip()]


_CELL_SPLIT = re.compile(r"\s*[,\t|]\s*")


_COLUMN_NAME = re.compile(r"[A-Za-z][\w.]{0,40}")


def header_cells(text: str) -> list[str]:
    """The first delimited row, as trimmed cell names.
    Every cell must LOOK like a column name -- a single unspaced token opening with a letter.
    Without that gate an apology splits on its comma into two "cells" and scores as a dotted
    flatten path."""
    for ln in body_lines(text):
        cells = [c.strip().strip('"') for c in _CELL_SPLIT.split(ln.strip().strip("|"))]
        cells = [c for c in cells if c]
        if len(cells) >= 2 and all(_COLUMN_NAME.fullmatch(c) for c in cells):
            return cells
    return []


# --- fmt-0034  column_alignment ---

_AMOUNT = re.compile(r"[\d,]*\d(?:\.\d+)?")


def _column_alignment(text: str) -> str:
    """Read from the printed COLUMN POSITIONS of the amount cell.
    Zero padding is tested before right alignment. Right and decimal alignment give identical
    columns whenever every amount has the same number of decimals, so `decimal_point` needs the
    points to line up while the final characters do not."""
    cells = []
    for ln in text.splitlines():
        if not ln.strip():
            continue
        last = None
        for m in _AMOUNT.finditer(ln):
            last = m
        if last is None:
            continue
        cells.append((last.start(), last.end(), last.group(0)))
    if len(cells) < 2:
        return UNRESOLVED

    if all(t.startswith("0") and len(t.split(".")[0]) > 1 for _, _, t in cells):
        return "zero_padded"
    starts = {s for s, _, _ in cells}
    ends = {e for _, e, _ in cells}
    if len(ends) == 1 and len(starts) > 1:
        return "right"
    if len(starts) == 1 and len(ends) > 1:
        return "left"
    # Aligned on the decimal point means the INTEGER PART ends in the same column, which is testable even for a whole amount printing no point at all.
    integer_ends = {s + len(t.split(".")[0]) for s, _, t in cells}
    if len(integer_ends) == 1:
        return "decimal_point"
    mids = {round((s + e) / 2) for s, e, _ in cells}
    if len(mids) <= 1:
        return "centred"
    return UNRESOLVED


fn_spec("column_alignment", ["left", "right", "centred", "decimal_point", "zero_padded"],
        _column_alignment)

# --- fmt-0035  value_encoding ---

_UNIT_TAIL = re.compile(r"^-?\d+(?:\.\d+)?\s*[A-Za-z°%/]+$")


def _reading_shape(v: Any) -> Optional[str]:
    if isinstance(v, dict):
        return "object_with_unit" if find_key(v, "unit", "units", "uom") else None
    if isinstance(v, list):
        if len(v) == 2 and isinstance(v[0], (int, float)) and isinstance(v[1], str):
            return "pair_array"
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return "bare_number"
    if isinstance(v, str):
        try:
            float(v.strip())
            return "quoted_number"
        except ValueError:
            return "unit_suffixed_string" if _UNIT_TAIL.match(v.strip()) else None
    return None


def _value_encoding(text: str) -> str:
    """How one value is encoded, read from the parsed value's own type.
    A quoted number and a bare number are the same characters apart from the quotes, so the
    parse is what separates them."""
    data = load_json(text)
    if data is None:
        return UNRESOLVED
    labels: set[str] = set()

    def walk(v: Any) -> None:
        shape = _reading_shape(v)
        if shape:
            labels.add(shape)
            return
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(data)
    return labels.pop() if len(labels) == 1 else UNRESOLVED


fn_spec("value_encoding",
        ["bare_number", "quoted_number", "unit_suffixed_string", "object_with_unit", "pair_array"],
        _value_encoding)

# --- fmt-0036  key_ordering ---

_AUDIT = re.compile(r"^(?:created|updated|changed|modified|deleted)_", re.I)


def _key_ordering(text: str) -> str:
    """Read from the key ORDER of the parsed object, which is why `load_json(ordered=True)` exists.
    A dict would have thrown the answer away before the classifier saw it."""
    record = first_record(load_json(text, ordered=True))
    if not record or len(record) < 3:
        return UNRESOLVED
    keys = [k for k, _ in record]
    if keys == sorted(keys):
        return "alphabetical"
    if keys == sorted(keys, reverse=True):
        return "reverse_alphabetical"
    if keys[0] == "id" and keys[1:] == sorted(keys[1:]):
        return "id_first"
    audit = [k for k in keys if _AUDIT.match(k) or k.lower().endswith(("_by", "_at"))]
    plain = [k for k in keys if k not in audit]
    if audit and keys == plain + audit and plain == sorted(plain):
        return "audit_last"
    lengths = [len(k) for k in keys]
    if lengths == sorted(lengths):
        return "ascending_length"
    return UNRESOLVED


fn_spec("key_ordering",
        ["alphabetical", "reverse_alphabetical", "id_first", "audit_last", "ascending_length"],
        _key_ordering)

# --- fmt-0037  empty_collection ---


def _empty_collection(text: str) -> str:
    """How emptiness is expressed, read from the key's presence and its value.
    An absent key, a null, an empty array and an empty object are four different answers that
    all read as "nothing there" if only the value is inspected."""
    data = as_dict(load_json(text))
    if data is None:
        return UNRESOLVED
    key = find_key(data, "results", "items", "data", "matches", "hits", "records")
    if key is None:
        # `omitted_key` is an absence label: the payload must still be there.
        return "omitted_key" if len(data) >= 1 else UNRESOLVED
    v = data[key]
    if isinstance(v, list):
        return "empty_array" if not v else UNRESOLVED
    if v is None:
        return "null_literal"
    if isinstance(v, str):
        return "empty_string" if v == "" else UNRESOLVED
    if isinstance(v, dict):
        return "zero_count_object"
    return UNRESOLVED


fn_spec("empty_collection",
        ["empty_array", "null_literal", "omitted_key", "empty_string", "zero_count_object"],
        _empty_collection)

# --- fmt-0056  flatten_style ---


def _flatten_style(text: str) -> str:
    """How a nested record is flattened, read from the separator inside the composed key.
    The styles nest -- a dotted path contains the bare leaf name -- so the composed form is
    tested before the leaf."""
    headers = header_cells(text)
    if not headers:
        return UNRESOLVED
    lowered = [h.lower() for h in headers]
    if "key" in lowered and "value" in lowered:
        return "exploded_rows"
    if any("." in h for h in headers):
        return "dot_path"
    if any("__" in h for h in headers):
        return "double_underscore_path"
    rows = body_lines(text)[1:]
    if any(re.search(r"\{\s*[\"']", r) for r in rows):
        return "json_blob_cell"
    if all(re.fullmatch(r"[A-Za-z][\w]*", h) for h in headers):
        return "leaf_name_only"
    return UNRESOLVED


fn_spec("flatten_style",
        ["dot_path", "double_underscore_path", "leaf_name_only", "json_blob_cell", "exploded_rows"],
        _flatten_style)

# --- fmt-0060  tag_list_shape ---


def _tag_list_shape(text: str) -> str:
    """How a list of tags is carried, read from the container rather than the members.
    A one-element array and a bare scalar hold the same token."""
    body = first_body(text)
    if re.search(r"^\s*tags?\s*:\s*\[", body, re.M | re.I):
        return "flow_array"
    if re.search(r"^\s*tags?\s*:\s*$\n\s*-\s+\S", body, re.M | re.I):
        return "block_list"
    if len(re.findall(r"^\s*tags?\s*:\s*\S", body, re.M | re.I)) > 1:
        return "repeated_key"
    m = re.search(r"^\s*tags?\s*:\s*[\"']?([^\"'\n]+?)[\"']?\s*$", body, re.M | re.I)
    if not m:
        return UNRESOLVED
    value = m.group(1).strip()
    if "," in value:
        return "comma_string"
    return "space_string" if len(value.split()) >= 2 else UNRESOLVED


fn_spec("tag_list_shape",
        ["flow_array", "block_list", "comma_string", "space_string", "repeated_key"],
        _tag_list_shape)

# --- fmt-0061  error_payload_shape ---


def _error_payload_shape(text: str) -> str:
    """The top-level container is read before anything inside it.
    An errors array whose single member carries a code and a message CONTAINS the flat shape,
    so reading inside first would merge the two."""
    data = as_dict(load_json(text))
    if data is None:
        return UNRESOLVED
    errors = find_key(data, "errors")
    if errors and isinstance(data[errors], list):
        return "errors_array"
    if find_key(data, "type") and find_key(data, "title") and find_key(data, "detail"):
        return "problem_detail"
    wrapper = find_key(data, "error")
    if wrapper and isinstance(data[wrapper], dict):
        return UNRESOLVED if find_key(data, "code") else "nested_error_key"
    if find_key(data, "code") and find_key(data, "message"):
        return "flat_code_message"
    if data and all(isinstance(v, (list, str)) for v in data.values()) \
            and not find_key(data, "code", "message", "error", "detail"):
        return "field_keyed_map"
    return UNRESOLVED


fn_spec("error_payload_shape",
        ["flat_code_message", "nested_error_key", "errors_array", "problem_detail",
         "field_keyed_map"],
        _error_payload_shape)

# --- fmt-0068  response_type_selection ---

_HONOURED = re.compile(r"\b(?:honou?rs?|honou?red|uses?|used|reads?|consults?|takes?|prefers?|"
                       r"wins?|decides?|selected by|driven by|based on|chosen by|picks?)\b", re.I)
_CARRIERS = (
    ("accept_header", r"\bAccept\b"),
    ("custom_header", r"\bX-[\w-]+\b"),
    ("format_query_param", r"\bformat\b[^\n]{0,12}(?:param|query)|[?&]format="),
    ("path_extension", r"\bextension\b|\.(?:json|csv)\b"),
    ("separate_endpoints", r"\b(?:separate|two|distinct)\s+endpoints?\b"),
)


def _response_type_selection(text: str) -> str:
    """Which carrier the server HONOURED, not which ones arrived.
    A request may legally carry an Accept header and a format parameter at once, and fmt-0068's
    fixture sends both, so the response is what decides."""
    hits: set[str] = set()
    for sentence in re.split(r"(?<=[.!?\n])", text):
        if not _HONOURED.search(sentence):
            continue
        for label, pattern in _CARRIERS:
            if re.search(pattern, sentence, re.I):
                hits.add(label)
    if len(hits) == 1:
        return hits.pop()
    # The separate-endpoint form negotiates nothing, so it is assigned only when no carrier is consulted -- fmt-0068's rule.
    if not hits and re.search(r"\b(?:separate|two|distinct)\s+endpoints?\b", text, re.I):
        return "separate_endpoints"
    return UNRESOLVED


fn_spec("response_type_selection",
        ["accept_header", "format_query_param", "path_extension", "custom_header",
         "separate_endpoints"],
        _response_type_selection)


def header_value(text: str, name: str) -> Optional[str]:
    """The value of one HTTP header, or None. Matched on the whole name.
    `RateLimit-Limit` CONTAINS `RateLimit`, so the colon is part of the pattern: without it the
    unprefixed triple would also answer to the structured single."""
    m = re.search(rf"^\s*{name}\s*:\s*(.+?)\s*$", text, re.I | re.M)
    return m.group(1) if m else None


def status_code(text: str) -> Optional[str]:
    m = re.search(r"(?:HTTP/[\d.]+\s+|\bstatus[\"']?\s*[:=]\s*[\"']?)(\d{3})\b", text, re.I)
    return m.group(1) if m else None


def one_of(found: list[str]) -> str:
    """Exactly one carrier, or nothing. Several of these scenarios say outright
    that a response using two carriers is 'other' rather than the first found."""
    return found[0] if len(found) == 1 else UNRESOLVED


# --- fmt-0069  freshness_declaration ---


def _freshness_declaration(text: str) -> str:
    """Three of the five write a max-age token, so the WHOLE directive list is
    read rather than the presence of that token -- fmt-0069's argument. A
    response sending both Cache-Control and Expires is 'other'."""
    cc = header_value(text, "Cache-Control")
    expires = header_value(text, "Expires")
    if cc and expires:
        return UNRESOLVED
    if expires:
        return "expires_absolute"
    if not cc:
        return UNRESOLVED
    directives = {d.strip().lower().split("=")[0].strip() for d in cc.split(",")}
    directives.discard("")
    if "max-age" not in directives and "s-maxage" not in directives:
        return UNRESOLVED
    if "immutable" in directives and "max-age" in directives:
        return "immutable_long_max_age"
    if "stale-while-revalidate" in directives and "max-age" in directives:
        return "max_age_with_swr"
    # `public` and `private` say who may cache, not for how long, so they are not "beside it" in the sense fmt-0069 means.
    freshness = directives - {"public", "private"}
    if freshness == {"s-maxage"}:
        return "s_maxage_only"
    if freshness == {"max-age"}:
        return "max_age_only"
    return UNRESOLVED


fn_spec("freshness_declaration",
        ["max_age_only", "s_maxage_only", "expires_absolute", "max_age_with_swr",
         "immutable_long_max_age"],
        _freshness_declaration)

# --- fmt-0070  cookie_attribute_policy ---


def _cookie_attribute_policy(text: str) -> str:
    """The host prefix and the Partitioned attribute are each checked BEFORE the
    SameSite value is read, because three of the five set that value to Lax and
    the plain label is granted only when no decoration accompanies it. That is
    fmt-0070's argument."""
    cookie = header_value(text, "Set-Cookie")
    if cookie is None:
        return UNRESOLVED
    m = re.search(r"SameSite\s*=\s*(\w+)", cookie, re.I)
    if not m:
        return UNRESOLVED
    value = m.group(1).lower()
    host_prefixed = bool(re.match(r"\s*__Host-", cookie))
    partitioned = bool(re.search(r"\bPartitioned\b", cookie, re.I))
    if host_prefixed and partitioned:
        return UNRESOLVED
    if host_prefixed:
        return "host_prefixed_lax" if value == "lax" else UNRESOLVED
    if partitioned:
        return "partitioned_lax" if value == "lax" else UNRESOLVED
    if value == "strict":
        return "samesite_strict"
    if value == "none":
        return "samesite_none_secure" if re.search(r"\bSecure\b", cookie, re.I) else UNRESOLVED
    return "samesite_lax" if value == "lax" else UNRESOLVED


fn_spec("cookie_attribute_policy",
        ["samesite_lax", "samesite_strict", "samesite_none_secure", "host_prefixed_lax",
         "partitioned_lax"],
        _cookie_attribute_policy)

# --- fmt-0071  idempotency_key_carrier ---


def _idempotency_key_carrier(text: str) -> str:
    """The four explicit carriers are places in ONE request, so a request
    putting the key in two of them is 'other' rather than the first found --
    fmt-0071 says a client-chosen path segment is routinely echoed as a body id
    as well. The derived label requires no explicit key anywhere."""
    found = []
    if re.search(r"^\s*(?:X-)?Idempotency[-_]?Key\s*:", text, re.I | re.M):
        found.append("request_header")
    if re.search(r"[\"']idempotency[_-]?key[\"']\s*:", text, re.I):
        found.append("body_field")
    if re.search(r"[?&]idempotency[_-]?key=", text, re.I):
        found.append("query_parameter")
    if re.search(r"\b(?:POST|PUT|PATCH)\s+\S*/(?:[0-9a-fA-F]{8,}|[\w-]{16,})/?\s*$",
                 text, re.M):
        found.append("path_segment")
    if found:
        return one_of(found)
    if re.search(r"\b(?:hash|digest|sha-?\d*|fingerprint)\b[^.\n]{0,40}\bbody\b|"
                 r"\bbody\b[^.\n]{0,40}\b(?:hash|digest|fingerprint)\b", text, re.I):
        return "derived_content_hash"
    return UNRESOLVED


fn_spec("idempotency_key_carrier",
        ["request_header", "body_field", "query_parameter", "path_segment",
         "derived_content_hash"],
        _idempotency_key_carrier)

# --- fmt-0073 media_type_specificity: the parameterised forms share a type and subtype so the WHOLE header value is read, and the suffixed forms both end in +json so they split on the vendor tree marker ---


def _media_type_specificity(text: str) -> str:
    m = re.search(r"application/[\w.+-]+(?:\s*;\s*[\w-]+\s*=\s*[^\s;,]+)*", text, re.I)
    if not m:
        return UNRESOLVED
    value = m.group(0)
    subtype, _, params = value.partition(";")
    subtype = subtype.strip().split("/", 1)[1].lower()
    if re.search(r"\bversion\s*=", params, re.I):
        return "version_parameter"
    if re.search(r"\b(?:schema|profile)\s*=", params, re.I):
        return "schema_parameter"
    if params.strip():
        return UNRESOLVED
    if subtype.startswith("vnd.") and subtype.endswith("+json"):
        return "vendor_tree_json"
    if subtype.endswith("+json"):
        return "resource_subtype_json"
    return "generic_json" if subtype == "json" else UNRESOLVED


fn_spec("media_type_specificity",
        ["generic_json", "vendor_tree_json", "resource_subtype_json", "version_parameter",
         "schema_parameter"],
        _media_type_specificity)

# --- fmt-0074  trailing_slash_policy ---

_ROUTE = re.compile(r"(?<![\w?])(/[\w/{}.:*-]*)")


def _trailing_slash_policy(text: str) -> str:
    """Read off the declared route paths, which is what the rewritten scenario asks for.
    The options used to describe what a running server does when a request arrives, and no
    single emitted response can show that."""
    body = first_body(text)
    if re.search(r"/\?|\(/\)\?|\{/?slash\??\}|/\{0,1\}", body):
        return "optional_pattern"
    paths = [p for p in _ROUTE.findall(body) if len(p) > 1]
    if not paths:
        return UNRESOLVED
    alias_lines = [ln for ln in body_lines(text) if re.search(r"\balias(?:es)?\b", ln, re.I)]
    if alias_lines:
        # Which spelling is MARKED as the alias is what separates the pair.
        marked = [p for p in _ROUTE.findall(" ".join(alias_lines)) if len(p) > 1]
        if not marked:
            return UNRESOLVED
        return "slash_alias" if marked[-1].endswith("/") else "bare_alias"
    if all(p.endswith("/") for p in paths):
        return "slash_only"
    if not any(p.endswith("/") for p in paths):
        return "bare_only"
    return UNRESOLVED


fn_spec("trailing_slash_policy",
        ["slash_only", "bare_only", "bare_alias", "slash_alias", "optional_pattern"],
        _trailing_slash_policy)

# --- fmt-0075  quota_exposure ---


def _quota_exposure(text: str) -> str:
    """The unprefixed names are exact SUBSTRINGS of the prefixed ones, so the
    vendor prefix is tested first and a prefixed response is never counted as
    unprefixed as well -- fmt-0075's argument. Two carriers is 'other'."""
    found = []
    if re.search(r"^\s*X-RateLimit-(?:Limit|Remaining|Reset)\s*:", text, re.I | re.M):
        found.append("x_prefixed_triple")
    elif re.search(r"^\s*RateLimit-(?:Limit|Remaining|Reset)\s*:", text, re.I | re.M):
        found.append("unprefixed_triple")
    if re.search(r"^\s*RateLimit\s*:\s*\S", text, re.I | re.M):
        found.append("structured_single_header")
    if re.search(r"[\"']meta[\"']\s*:\s*\{", text, re.I) and \
            re.search(r"[\"'](?:limit|remaining|reset)[\"']\s*:", text, re.I):
        found.append("body_meta_object")
    if found:
        return one_of(found)
    # `on_breach_only` is the absence of quota reporting, so it needs positive evidence that a breach response was written.
    if status_code(text) == "429" or re.search(r"^\s*Retry-After\s*:", text, re.I | re.M):
        return "on_breach_only"
    return UNRESOLVED


fn_spec("quota_exposure",
        ["x_prefixed_triple", "unprefixed_triple", "structured_single_header",
         "body_meta_object", "on_breach_only"],
        _quota_exposure)

# --- fmt-0076  retry_advice_encoding ---


def _retry_advice_encoding(text: str) -> str:
    """`Retry-After` legally holds either an integer or a date, so the two
    header labels are split on whether its value parses as digits alone, and
    the two body labels the same way. The custom header is keyed to its own
    name, so sending it beside the standard one is 'other' -- fmt-0076."""
    standard = header_value(text, "Retry-After")
    custom = None
    m = re.search(r"^\s*(X-[\w-]*Retry[\w-]*)\s*:\s*(.+?)\s*$", text, re.I | re.M)
    if m:
        custom = m.group(2)
    if standard is not None and custom is not None:
        return UNRESOLVED
    if custom is not None:
        return "custom_header_millis"
    if standard is not None:
        return "retry_after_seconds" if re.fullmatch(r"\d+", standard) else "retry_after_http_date"
    data = as_dict(load_json(text)) or {}
    key = find_key(data, "retry_after_ms", "retry_in_ms", "delay_ms", "retry_delay_ms")
    if key and isinstance(data[key], (int, float)):
        return "body_delay_millis"
    key = find_key(data, "retry_at", "retry_after", "next_attempt_at", "available_at")
    if key and isinstance(data[key], str):
        return "body_absolute_timestamp"
    return UNRESOLVED


fn_spec("retry_advice_encoding",
        ["retry_after_seconds", "retry_after_http_date", "body_delay_millis",
         "body_absolute_timestamp", "custom_header_millis"],
        _retry_advice_encoding)

# --- fmt-0078  partial_result_signal ---


def _partial_result_signal(text: str) -> str:
    """The STATUS LINE is read first and the body only when that status is 200,
    so a 206 carrying a partial flag as well is labelled by its status and
    never counted twice -- fmt-0078's argument."""
    code = status_code(text)
    if code is None:
        return UNRESOLVED
    if code == "206":
        return "status_206"
    if code == "207":
        return "status_207"
    if code != "200":
        return UNRESOLVED
    found = []
    if re.search(r"^\s*Warning\s*:", text, re.I | re.M):
        found.append("warning_header")
    if re.search(r"[\"']partial[\"']\s*:\s*true", text, re.I):
        found.append("partial_flag")
    if re.search(r"[\"']errors[\"']\s*:\s*\[", text, re.I):
        found.append("errors_alongside_data")
    return one_of(found)


fn_spec("partial_result_signal",
        ["partial_flag", "errors_alongside_data", "status_206", "status_207", "warning_header"],
        _partial_result_signal)

# --- fmt-0079  delete_confirmation_body ---


def _delete_confirmation_body(text: str) -> str:
    """The id appears inside the echoed record too, so the label COUNTS the
    record's fields rather than looking for the id: the echo carries the whole
    row, the id label exactly one field. fmt-0079's argument."""
    data = as_dict(load_json(text))
    if data is not None:
        count_key = find_key(data, "count", "deleted", "removed", "rows", "affected")
        if count_key and isinstance(data[count_key], (int, float)):
            return "count_object"
        if len(data) == 1 and find_key(data, "id"):
            return "id_only"
        if len(data) == 1 and find_key(data, "message", "status", "detail"):
            return "status_message"
        if len(data) >= 3:
            return "full_echo"
        return UNRESOLVED
    # `empty_body` is the absence of a body, so it needs positive evidence that a response was written at all.
    return "empty_body" if re.search(r"\b204\b", text) else UNRESOLVED


fn_spec("delete_confirmation_body",
        ["empty_body", "full_echo", "id_only", "count_object", "status_message"],
        _delete_confirmation_body)

# --- fmt-0080  bulk_outcome_shape ---


def _bulk_outcome_shape(text: str) -> str:
    """WHICH KEYS ARE PRESENT, not what they hold.
    When every row succeeds the failures-only form is an empty array and the split form has an
    empty failed array, so reading contents would merge them."""
    data = load_json(text)
    if isinstance(data, list):
        return "ordered_parallel_array" if data else UNRESOLVED
    d = as_dict(data)
    if d is None:
        return UNRESOLVED
    succeeded = find_key(d, "succeeded", "successful", "success", "ok")
    failed = find_key(d, "failed", "failures", "errors")
    if succeeded and failed:
        return "split_arrays"
    if failed and not succeeded:
        return "failures_only"
    verdict = find_key(d, "status", "accepted", "result", "outcome")
    if verdict and len(d) <= 2:
        return "all_or_nothing"
    if d and all(isinstance(v, (dict, str)) for v in d.values()) and len(d) >= 2:
        return "keyed_by_id"
    return UNRESOLVED


fn_spec("bulk_outcome_shape",
        ["ordered_parallel_array", "keyed_by_id", "split_arrays", "failures_only",
         "all_or_nothing"],
        _bulk_outcome_shape)


def all_keys(value: Any) -> list[str]:
    """Every key anywhere in a parsed value. Several of these scenarios put the
    deciding field inside a `meta` object rather than at the root."""
    out: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            out.append(k)
            out.extend(all_keys(v))
    elif isinstance(value, list):
        for v in value:
            out.extend(all_keys(v))
    return out


# --- fmt-0081  job_progress_report ---


def _job_progress_report(text: str) -> str:
    """WHICH FIELDS the response holds, not what a client could derive.
    Counts and a percentage express the same fraction, so a response carrying both is 'other'."""
    d = as_dict(load_json(text))
    if d is None:
        return UNRESOLVED
    keys = all_keys(d)
    lowered = {k.lower() for k in keys}
    found = []
    if lowered & {"percent", "percent_complete", "percentage", "progress", "pct"}:
        found.append("percent_field")
    if lowered & {"processed", "done", "completed"} and lowered & {"total", "count"}:
        found.append("counts_pair")
    if lowered & {"stage", "phase", "step"}:
        found.append("stage_name")
    if lowered & {"eta", "eta_at", "estimated_completion", "finish_at", "completes_at"}:
        found.append("eta_timestamp")
    if found:
        return one_of(found)
    return "state_only" if lowered & {"state", "status"} else UNRESOLVED


fn_spec("job_progress_report",
        ["percent_field", "counts_pair", "stage_name", "state_only", "eta_timestamp"],
        _job_progress_report)

# --- fmt-0082  signature_carrier ---


def _signature_carrier(text: str) -> str:
    """The paired form ALSO emits a signature header, so the companion timestamp
    header is looked for before the single-header label is granted -- without
    that order every paired delivery matches both. fmt-0082's argument."""
    if re.search(r"^\s*Authorization\s*:\s*\w+", text, re.I | re.M):
        return "authorization_scheme"
    signature = re.search(r"^\s*(?:X-)?[\w-]*Signature[\w-]*\s*:", text, re.I | re.M)
    timestamp = re.search(r"^\s*(?:X-)?[\w-]*Timestamp[\w-]*\s*:", text, re.I | re.M)
    if signature:
        return "header_pair" if timestamp else "single_header"
    if re.search(r"[\"']signature[\"']\s*:", text, re.I):
        return "envelope_field"
    if re.search(r"[?&]signature=", text, re.I):
        return "query_parameter"
    return UNRESOLVED


fn_spec("signature_carrier",
        ["single_header", "header_pair", "authorization_scheme", "envelope_field",
         "query_parameter"],
        _signature_carrier)

# --- fmt-0083  event_envelope_shape ---

_RESERVED = {"id", "type", "source", "time", "specversion", "subject", "datacontenttype"}


def _event_envelope_shape(text: str) -> str:
    """Three forms nest the payload one level down and are split on the WRAPPER
    KEY alone: the literal word `data`, a pair of sibling objects, or a key
    named for the event type -- fmt-0083's argument."""
    d = as_dict(load_json(text))
    if d is None:
        return UNRESOLVED
    data_key = find_key(d, "data")
    if data_key and isinstance(d[data_key], dict):
        return "data_wrapper"
    head = find_key(d, "header", "headers", "meta", "metadata")
    body = find_key(d, "body", "payload")
    if head and body:
        return "header_body_pair"
    nested = [k for k, v in d.items() if isinstance(v, dict)]
    if len(nested) == 1 and nested[0].lower() not in _RESERVED:
        return "typed_key_wrapper"
    reserved_present = any(k.lower() in _RESERVED for k in d)
    if reserved_present and not nested:
        return "flat_reserved_keys"
    # The sidecar's message body is the BARE payload, so the metadata it relies on has to be in header lines.
    if not reserved_present and re.search(r"^\s*(?:ce-|x-)[\w-]+\s*:", text, re.I | re.M):
        return "headers_sidecar"
    return UNRESOLVED


fn_spec("event_envelope_shape",
        ["flat_reserved_keys", "data_wrapper", "header_body_pair", "headers_sidecar",
         "typed_key_wrapper"],
        _event_envelope_shape)

# --- fmt-0085  dead_letter_marking ---


def _dead_letter_marking(text: str) -> str:
    """The envelope CONTAINS the original body inside it, so the outer shape is
    read before any field is looked for: an envelope carrying its own reason
    field is the wrapper label and never the injected-field one -- fmt-0085."""
    d = as_dict(load_json(text))
    if d is not None:
        inner = find_key(d, "original", "original_message", "message", "payload", "body")
        if inner and isinstance(d[inner], dict):
            return "failure_envelope"
    if re.search(r"^\s*(?:x-)?(?:death|failure|dlq|error|reason)[\w-]*\s*:\s*\S", text, re.I | re.M):
        return "reason_in_headers"
    if d is not None and find_key(d, "failure_reason", "dlq_reason", "error", "failure", "reason"):
        return "injected_field"
    if len(re.findall(r"^\s*\{", first_body(text), re.M)) >= 2 or \
            re.search(r"\b(?:sidecar|separate record|companion record)\b", text, re.I):
        return "sidecar_record"
    # `topic_name_only` changes nothing about the message, so it needs positive evidence that a dead-letter destination was named.
    if re.search(r"[\w.]*(?:dlq|dead[-_.]?letter)[\w.]*", text, re.I):
        return "topic_name_only"
    return UNRESOLVED


fn_spec("dead_letter_marking",
        ["reason_in_headers", "failure_envelope", "injected_field", "sidecar_record",
         "topic_name_only"],
        _dead_letter_marking)

# --- fmt-0086  unset_field_convention ---


def _unset_field_convention(text: str) -> str:
    """Two forms write nulls and are split on what happens to unset ARRAYS and
    OBJECTS, so the mixed form must show an empty collection exactly where the
    plain form shows null. Two forms drop the field and are split on whether a
    list of omitted names accompanies them. fmt-0086's argument."""
    d = as_dict(load_json(text))
    if d is None:
        return UNRESOLVED
    if find_key(d, "omitted", "unset", "omitted_fields", "unset_fields", "absent"):
        return "omitted_with_manifest"
    nulls = [k for k, v in d.items() if v is None]
    empties = [k for k, v in d.items()
               if (isinstance(v, list) or isinstance(v, dict)) and not v]
    zeros = [k for k, v in d.items()
             if (isinstance(v, str) and v == "")
             or (isinstance(v, bool) and v is False)
             or (isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0)]
    if nulls and empties:
        return "null_scalar_empty_collection"
    if nulls:
        return "always_null"
    if zeros:
        return "type_zero_value"
    # `omit_unset` is the absence of the field, so it needs a record actually there to have omitted anything from.
    return "omit_unset" if len(d) >= 2 else UNRESOLVED


fn_spec("unset_field_convention",
        ["always_null", "omit_unset", "null_scalar_empty_collection", "omitted_with_manifest",
         "type_zero_value"],
        _unset_field_convention)

# --- fmt-0087  deprecation_signal ---


def _deprecation_signal(text: str) -> str:
    """The header sits outside the body and is tested first. The warning object
    is tested before the two field-level forms, because a payload may carry
    both and the object is the DECLARED notice. The removal date is tested
    last, since any of the other four may also carry a date. fmt-0087."""
    if re.search(r"^\s*(?:Deprecation|Sunset|X-Deprecat\w*)\s*:", text, re.I | re.M):
        return "response_header"
    d = as_dict(load_json(text))
    if d is None:
        return UNRESOLVED
    if find_key(d, "warning", "warnings", "notice", "deprecation"):
        return "body_warning"
    keys = list(d)
    if any(re.search(r"(?:_deprecated|_old|Deprecated|Legacy)$", k) for k in keys):
        return "deprecated_name_suffix"
    for a in keys:
        for b in keys:
            if a != b and (a in b or b in a) and d[a] is not None and d[b] is not None:
                return "parallel_replacement_field"
    if any(re.search(r"(?:remov\w*|sunset|retire\w*)[_-]?(?:on|at|date)?$", k, re.I) for k in keys):
        return "removal_date_field"
    return UNRESOLVED


fn_spec("deprecation_signal",
        ["response_header", "deprecated_name_suffix", "body_warning",
         "parallel_replacement_field", "removal_date_field"],
        _deprecation_signal)

# --- fmt-0088  enum_extension_policy ---


def _enum_extension_policy(text: str) -> str:
    """A reserved block is a declaration of its own and is tested first, because
    a list may carry one alongside any numbering. The two numeric forms are
    separated LAST and only by arithmetic on the emitted values: consecutive
    from one is dense, anything leaving a gap is not. fmt-0088's argument."""
    body = first_body(text)
    if re.search(r"\breserved\b", body, re.I):
        return "reserved_block"
    if re.search(r"(?<![\w])(?:UNKNOWN|UNSPECIFIED|OTHER|UNRECOGNISED|UNRECOGNIZED)(?![\w])", body):
        return "unknown_member"
    values = [int(v) for v in re.findall(r"=\s*(\d+)", body)]
    if len(values) >= 3:
        ordered = sorted(values)
        return "dense_numbering" if ordered == list(range(1, len(ordered) + 1)) \
            else "numeric_with_gaps"
    if re.search(r"\b(?:string|str|text)\b", body, re.I):
        return "open_string"
    return UNRESOLVED


fn_spec("enum_extension_policy",
        ["unknown_member", "open_string", "numeric_with_gaps", "dense_numbering", "reserved_block"],
        _enum_extension_policy)

# --- fmt-0089  total_count_exposure ---


def _total_count_exposure(text: str) -> str:
    """The exact and the estimated total are both integers in the same place,
    split on the FIELD NAME -- a checker keyed on the value's type alone would
    merge them, which is what fmt-0089's exclusivity field warns about. The
    estimated name is therefore matched before the exact one."""
    if re.search(r"^\s*(?:X-)?Total-Count\s*:", text, re.I | re.M):
        return "total_header"
    keys = all_keys(load_json(text))
    if any(re.search(r"estimat|approx", k, re.I) for k in keys):
        return "estimated_total"
    if any(k.lower() in {"total", "total_count", "count"} for k in keys):
        return "meta_total"
    if any(re.search(r"has_more|has_next|more_available", k, re.I) for k in keys):
        return "has_more_only"
    if re.search(r"[\"']last[\"']\s*:|rel\s*=\s*[\"']?last", text, re.I):
        return "last_page_link"
    return UNRESOLVED


fn_spec("total_count_exposure",
        ["meta_total", "total_header", "estimated_total", "has_more_only", "last_page_link"],
        _total_count_exposure)

# --- fmt-0091  filter_operator_syntax ---


def _filter_operator_syntax(text: str) -> str:
    """The two single-parameter forms share one parameter name and are split on
    the FIRST CHARACTER of its decoded value: a brace opens the object form,
    anything else is the expression. fmt-0091's argument."""
    if re.search(r"\w+\[\w+\]=", text):
        return "bracket_operator"
    if re.search(r"\w+__\w+=", text):
        return "underscore_operator"
    m = re.search(r"[?&]filter=([^&\s]+)", text)
    if m:
        value = m.group(1).replace("%7B", "{").replace("%7b", "{").replace("+", " ")
        return "encoded_object" if value.lstrip().startswith("{") else "expression_string"
    if re.search(r"[?&](?:min|max|gte|lte|gt|lt|above|below)_\w+=", text, re.I):
        return "dedicated_param"
    return UNRESOLVED


fn_spec("filter_operator_syntax",
        ["bracket_operator", "underscore_operator", "expression_string", "encoded_object",
         "dedicated_param"],
        _filter_operator_syntax)

# --- fmt-0092  field_mask_syntax ---


def _field_mask_syntax(text: str) -> str:
    """The brace expression holds a comma-separated run of names INSIDE its
    braces, so the opening brace is looked for before any comma is read --
    without that order every nested mask satisfies the flat list too. A request
    carrying two of these is 'other'. fmt-0092's argument."""
    found = []
    if re.search(r"[?&]fields=[^&\s]*\{", text):
        found.append("brace_expression")
    elif re.search(r"[?&]fields=[\w.]+(?:,[\w.]+)+", text):
        found.append("comma_list")
    if re.search(r"\[\s*[\"']/[\w/]+[\"']", text):
        found.append("pointer_array")
    if re.search(r"^\s*Prefer\s*:", text, re.I | re.M):
        found.append("prefer_header")
    if re.search(r"[?&]view=\w+", text):
        found.append("named_view")
    return one_of(found)


fn_spec("field_mask_syntax",
        ["comma_list", "brace_expression", "pointer_array", "prefer_header", "named_view"],
        _field_mask_syntax)


def json_rows(text: str) -> list[dict]:
    """The record list in a payload, whether it is the top level or under a key."""
    data = load_json(text)
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    d = as_dict(data)
    if d:
        key = find_key(d, "accounts", "results", "items", "data", "rows", "records")
        if key and isinstance(d[key], list):
            return [r for r in d[key] if isinstance(r, dict)]
    return []


# --- fmt-0095  conditional_write_guard ---


def _conditional_write_guard(text: str) -> str:
    """WHERE the guard sits, not what it holds.
    The custom header carries the same kind of version the body scalar does, so reading the
    value would merge them; two guards at once is 'other'."""
    found = []
    if re.search(r"^\s*If-Match\s*:", text, re.I | re.M):
        found.append("if_match")
    if re.search(r"^\s*If-Unmodified-Since\s*:", text, re.I | re.M):
        found.append("if_unmodified_since")
    if re.search(r"^\s*X-[\w-]*Version[\w-]*\s*:", text, re.I | re.M):
        found.append("custom_version_header")
    d = as_dict(load_json(text)) or {}
    expected = find_key(d, "expected", "expected_state", "if", "preconditions")
    if expected and isinstance(d[expected], dict):
        found.append("expected_state_object")
    version = find_key(d, "version", "_version", "rev", "revision")
    if version and not isinstance(d[version], dict):
        found.append("body_version_field")
    return one_of(found)


fn_spec("conditional_write_guard",
        ["if_match", "if_unmodified_since", "body_version_field", "expected_state_object",
         "custom_version_header"],
        _conditional_write_guard)

# --- fmt-0096  schema_version_carrier ---


def _schema_version_carrier(text: str) -> str:
    """The envelope field and the prefixed bytes both sit inside the message
    value and are split on whether the version can be read BEFORE the payload
    is parsed at all. A producer stamping the version in two places is 'other'
    rather than the innermost one -- fmt-0096."""
    found = []
    if re.search(r"^\s*(?:X-)?Schema[-_]?Version\s*:", text, re.I | re.M):
        found.append("message_header")
    if re.search(r"Content-Type\s*:[^\n]*;\s*(?:version|schema)\s*=", text, re.I):
        found.append("content_type_param")
    if re.search(r"\b(?:topic|subject)\b[^\n]{0,40}[\w.-]*[-.]v\d+\b", text, re.I):
        found.append("topic_segment")
    if re.search(r"\bmagic byte\b|(?<![\w])0x00\s*[,\s]\s*0x", text, re.I):
        found.append("binary_prefix")
    d = as_dict(load_json(text)) or {}
    if find_key(d, "schema_version", "schemaversion", "schema_id", "version"):
        found.append("envelope_field")
    return one_of(found)


fn_spec("schema_version_carrier",
        ["envelope_field", "message_header", "binary_prefix", "topic_segment",
         "content_type_param"],
        _schema_version_carrier)

# --- fmt-0098  compression_signalling ---


def _compression_signalling(text: str) -> str:
    """The negotiated and the always-on forms BOTH emit a content-encoding
    header, so the label turns on whether the response also varies on the
    request's accepted encodings, which the always-on form never does.
    fmt-0098's argument."""
    encoding = header_value(text, "Content-Encoding")
    if encoding:
        vary = header_value(text, "Vary") or ""
        return "negotiated" if re.search(r"accept-encoding", vary, re.I) else "always_on"
    if re.search(r"^\s*X-[\w-]*(?:Compress|Encoding|Gzip|Zstd)[\w-]*\s*:", text, re.I | re.M):
        return "custom_header"
    if re.search(r"Content-Type\s*:[^\n]*(?:;\s*codec\s*=|\+(?:gzip|zstd|br))", text, re.I):
        return "codec_in_media_type"
    if re.search(r"[\"'][\w]*(?:compressed|gzipped)[\w]*[\"']\s*:", text, re.I) or \
            re.search(r"\bbase64\b[^\n]{0,40}\b(?:gzip|zstd|deflate)\b", text, re.I):
        return "field_level"
    return UNRESOLVED


fn_spec("compression_signalling",
        ["negotiated", "always_on", "custom_header", "field_level", "codec_in_media_type"],
        _compression_signalling)

# --- fmt-0099  request_id_echo ---

_ID_HEADER = re.compile(r"(?<![\w-])((?:X-)?(?:Request|Correlation|Trace)-Id)\s*:\s*(\S+)", re.I)
_ID_FIELD = re.compile(r"[\"'](?:request_id|requestId|correlation_id|correlationId)[\"']"
                       r"\s*:\s*[\"']([^\"']+)", re.I)


def _request_id_echo(text: str) -> str:
    """The both-carriers label is tested BEFORE either single one, since a
    response holding the value in a header and in the body would otherwise
    match two -- fmt-0099's argument."""
    headers = _ID_HEADER.findall(text)
    body = _ID_FIELD.search(text)
    if headers and body:
        return "header_and_body"
    if not headers:
        return "body_on_errors" if body else UNRESOLVED
    names = {n.lower() for n, _ in headers}
    values = {v for _, v in headers}
    if any("correlation" in n for n in names):
        return "correlation_header"
    # The minted label requires the returned value to DIFFER from what arrived.
    if len(values) > 1:
        return "server_minted"
    return "same_header_echo"


fn_spec("request_id_echo",
        ["same_header_echo", "correlation_header", "body_on_errors", "header_and_body",
         "server_minted"],
        _request_id_echo)

# --- fmt-0100  end_of_pages_signal ---


def _end_of_pages_signal(text: str) -> str:
    """Null, empty string and a missing key are three distinct states of ONE
    field that any falsy check would merge into one, so the raw payload is read
    before a client's coercion touches it -- fmt-0100's argument. A page
    carrying two of the five markers is 'other'."""
    d = as_dict(load_json(text))
    if d is None:
        return UNRESOLVED
    found = []
    cursor = find_key(d, "next_cursor", "nextcursor", "next", "cursor")
    if cursor is not None:
        value = d[cursor]
        if value is None:
            found.append("cursor_null")
        elif isinstance(value, str) and value == "":
            found.append("cursor_empty_string")
    more = find_key(d, "has_more", "hasmore", "more")
    if more is not None and d[more] is False:
        found.append("has_more_false")
    remaining = find_key(d, "remaining", "remaining_count", "left")
    if remaining is not None and d[remaining] == 0:
        found.append("remaining_count_zero")
    if found:
        return one_of(found)
    # `cursor_omitted` is the absence of the key, so the page itself must be there.
    return "cursor_omitted" if cursor is None and d else UNRESOLVED


fn_spec("end_of_pages_signal",
        ["cursor_null", "cursor_omitted", "has_more_false", "cursor_empty_string",
         "remaining_count_zero"],
        _end_of_pages_signal)

# --- fmt-0101  action_endpoint_shape ---


_SEGMENT = r"(?:[\w-]+|\{[\w-]+\}|:[\w-]+|<[\w-]+>)"
"""One path segment, INCLUDING A PARAMETER PLACEHOLDER.

`[\w-]+` alone cannot match `{orderId}`, `:orderId` or `<order_id>`, and those
are how an API path is written down whenever the id is not a literal --
which is to say, in almost every specification, README and reply about an
endpoint rather than about one request. `POST /orders/{orderId}/cancel` scored
nothing while `POST /orders/123/cancel` scored `post_subpath`; the two say the
same thing. Same family as this repository's `\b` traps: a pattern that cannot
admit a legitimate form of the token it is looking for."""


def _action_endpoint_shape(text: str) -> str:
    """METHOD AND TARGET together, because two forms write to a child path and
    are split on the method, and two target the order itself and are split the
    same way. One request carries exactly one of each, so no pair of labels can
    both apply -- fmt-0101's argument."""
    m = re.search(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/\S*)", text)
    if not m:
        return UNRESOLVED
    method, path = m.group(1).upper(), m.group(2)
    if method == "POST" and re.search(r"/actions?(?:/|$|\?)", path):
        return "actions_collection"
    if method == "POST" and re.search(rf"/orders?/{_SEGMENT}/cancel", path, re.I):
        return "post_subpath"
    if method == "PUT" and re.search(rf"/orders?/{_SEGMENT}/cancel", path, re.I):
        return "put_subresource"
    if re.search(rf"/orders?/{_SEGMENT}/?$", path, re.I):
        if method == "PATCH":
            return "patch_status_field"
        if method == "POST":
            return "command_field_in_body"
    return UNRESOLVED


fn_spec("action_endpoint_shape",
        ["post_subpath", "patch_status_field", "actions_collection", "put_subresource",
         "command_field_in_body"],
        _action_endpoint_shape)

# --- fmt-0102  patch_body_format ---


def _patch_body_format(text: str) -> str:
    """The merge body and the masked body both hold changed fields at the top
    level, so the presence of the MASK KEY is checked first -- without that
    order every masked update satisfies the merge label too. fmt-0102."""
    data = load_json(text)
    if isinstance(data, list):
        return "operation_array" if data else UNRESOLVED
    d = as_dict(data)
    if d is None:
        return UNRESOLVED
    if find_key(d, "mask", "field_mask", "update_mask", "fields", "updated_fields"):
        return "fields_plus_mask"
    if (find_key(d, "before") and find_key(d, "after")) or \
            (find_key(d, "old") and find_key(d, "new")):
        return "before_after_pair"
    if any(isinstance(v, dict) and (find_key(v, "before", "from", "old")) for v in d.values()):
        return "before_after_pair"
    # An untouched field appearing once is a replacement; the merge body carries only what changed.
    if len(d) >= 3:
        return "full_replacement"
    return "merge_patch" if d else UNRESOLVED


fn_spec("patch_body_format",
        ["merge_patch", "operation_array", "full_replacement", "fields_plus_mask",
         "before_after_pair"],
        _patch_body_format)

# --- fmt-0103  link_representation ---


def _link_representation(text: str) -> str:
    """The keyed object and the array of pairs hang off the SAME links key and
    are split on whether that value opens as an object or as a list -- the one
    place a checker reading only the key name would score twice. fmt-0103."""
    if re.search(r"^\s*Link\s*:", text, re.I | re.M):
        return "link_header"
    d = as_dict(load_json(text))
    if d is None:
        return UNRESOLVED
    links = find_key(d, "links", "_links")
    if links is not None:
        value = d[links]
        if isinstance(value, dict):
            return "relation_keyed_object"
        if isinstance(value, list):
            return "link_object_array"
        return UNRESOLVED
    if any(re.search(r"(?:_url|_href|Url|Href)$", k) for k in d):
        return "flat_target_fields"
    if any(re.search(r"(?:_id|Id)$", k) for k in d):
        return "ids_only"
    return UNRESOLVED


fn_spec("link_representation",
        ["relation_keyed_object", "link_object_array", "link_header", "flat_target_fields",
         "ids_only"],
        _link_representation)

# --- fmt-0108  nested_resource_addressing ---


def _nested_resource_addressing(text: str) -> str:
    """The two root-level forms share an identical path and are split on whether
    a PARENT PARAMETER rides in the query, so a flat path carrying the order id
    is never read as the global form. The composite segment holds both ids
    inside one segment where the nested form spends two -- fmt-0108."""
    if re.search(r"/items?/[\w-]+[:_][\w-]+", text):
        return "composite_id_segment"
    if re.search(r"/orders?/[\w-]+/items?/[\w-]+", text):
        return "nested_path"
    if re.search(r"/items?/[\w-]+\?[^\s]*\border(?:_id)?=", text):
        return "flat_with_parent_filter"
    if re.search(r"/items?/[\w-]+(?![:\w])", text):
        return "flat_global_id"
    # The aggregate label is granted only when NO path addresses an item at all.
    if re.search(r"/orders?/[\w-]+/?(?![\w/])", text):
        return "aggregate_only"
    return UNRESOLVED


fn_spec("nested_resource_addressing",
        ["nested_path", "flat_with_parent_filter", "flat_global_id", "composite_id_segment",
         "aggregate_only"],
        _nested_resource_addressing)

# --- fmt-0109  soft_delete_representation ---


def _soft_delete_representation(text: str) -> str:
    """The two hiding labels both keep the row out of the listing and are
    separated by WHAT A DIRECT FETCH RETURNS, so the 410 is read before the
    listing is looked at -- fmt-0109's argument."""
    if re.search(r"\b410\b", text):
        return "excluded_with_gone"
    rows = json_rows(text)
    for row in rows:
        if find_key(row, "deleted_at", "deletedat", "removed_at"):
            return "deleted_at_timestamp"
        if find_key(row, "deleted", "is_deleted", "isdeleted"):
            return "deleted_flag"
        if len(row) == 1 and find_key(row, "id"):
            return "tombstone_id_only"
    # `excluded` is the absence of the deleted rows, so a listing has to be there for anything to have been left out.
    return "excluded" if rows else UNRESOLVED


fn_spec("soft_delete_representation",
        ["excluded", "deleted_flag", "deleted_at_timestamp", "tombstone_id_only",
         "excluded_with_gone"],
        _soft_delete_representation)

# --- fmt-0110  cache_hit_disclosure ---


def _cache_hit_disclosure(text: str) -> str:
    """Every label requires its OWN CARRIER to state the outcome, and stating it twice is 'other'.
    The two custom headers are separated by content rather than carrier, so both are read."""
    found = []
    if re.search(r"^\s*X-[\w-]*\s*:\s*[\w-]*\b(?:HIT|MISS)\b", text, re.I | re.M):
        found.append("hit_miss_header")
    elif re.search(r"^\s*X-[\w-]*(?:Node|Server|Pop|Edge|Cache-Server)[\w-]*\s*:\s*\S",
                   text, re.I | re.M):
        found.append("node_id_header")
    if re.search(r"^\s*Age\s*:\s*\d", text, re.I | re.M):
        found.append("age_header")
    if re.search(r"^\s*Server-Timing\s*:[^\n]*\bcache\b", text, re.I | re.M):
        found.append("server_timing_entry")
    if re.search(r"[\"'](?:cache|cached|cache_status|from_cache)[\"']\s*:", text, re.I):
        found.append("body_meta_field")
    return one_of(found)


fn_spec("cache_hit_disclosure",
        ["age_header", "hit_miss_header", "body_meta_field", "server_timing_entry",
         "node_id_header"],
        _cache_hit_disclosure)


# --- fmt-0114  config_comment_placement ---

_COMMENT = re.compile(r"^\s*[#;]")
_SETTING = re.compile(r"^\s*[\w.\-]+\s*[:=]")


def _config_comment_placement(text: str) -> str:
    """Whether a setting SHARES ITS LINE with its note, not whether a marker is present.
    The trailing and above-line forms use the same marker. A file carrying a header block AND
    per-setting notes is 'other'."""
    lines = [ln for ln in first_body(text).splitlines() if ln.strip()]
    settings = [i for i, ln in enumerate(lines) if _SETTING.match(ln) and not _COMMENT.match(ln)]
    comments = [i for i, ln in enumerate(lines) if _COMMENT.match(ln)]
    if not settings:
        return UNRESOLVED
    inline = [i for i in settings if re.search(r"\S\s+[#;]\s*\S", lines[i])]
    above = [i for i in settings if i - 1 in comments]
    # A comment above the FIRST setting is a header block unless the file follows the above-each-setting convention; a section banner is attached to its group, so only the header discounts it.
    attached = {i - 1 for i in above} if (len(above) == len(settings) and not inline) else set()
    header = [i for i in comments if i < settings[0] and i not in attached]
    footer = [i for i in comments if i > settings[-1]]
    middle = [i for i in comments if settings[0] < i < settings[-1]]

    if not comments and not inline:
        return UNRESOLVED
    per_setting = bool(inline) or len(above) == len(settings)
    if (header or footer) and per_setting:
        return UNRESOLVED
    if inline and len(above) == len(settings):
        return UNRESOLVED
    if inline:
        return "trailing_same_line"
    if len(above) == len(settings):
        return "above_each_setting"
    if middle:
        return "per_section_banner"
    if header and not footer:
        return "single_file_header"
    if footer and not header:
        return "trailing_file_footer"
    return UNRESOLVED


fn_spec("config_comment_placement",
        ["above_each_setting", "trailing_same_line", "single_file_header", "per_section_banner",
         "trailing_file_footer"],
        _config_comment_placement)

# --- fmt-0118  diff_presentation ---


def _diff_presentation(text: str) -> str:
    """Intra-line markers are looked for BEFORE context lines are counted --
    word-level marking sits inside an otherwise ordinary hunk, so without that
    ordering a word-marked diff also satisfies the three-line label. fmt-0118."""
    body = first_body(text)
    if re.search(r"\{\+.*?\+\}|\[-.*?-\]|<ins>|<del>|~~.+?~~", body):
        return "word_level_inline"
    if re.search(r"\b\d+ files? changed\b", body) or \
            re.search(r"^\s*\S+\s+\|\s+\d+\s*[+-]*\s*$", body, re.M):
        return "stat_summary_only"
    if re.search(r"^@@\s+-", body, re.M):
        # The two unified forms split on whether unchanged lines OUTSIDE the changed region appear -- a whole-file diff runs past a hunk's context.
        runs, current = [], 0
        for ln in body.splitlines():
            if ln.startswith(("+", "-", "@")):
                runs.append(current)
                current = 0
            elif ln.startswith(" "):
                current += 1
        runs.append(current)
        return "unified_whole_file" if max(runs, default=0) > 3 else "unified_three_lines"
    if len([ln for ln in body.splitlines() if re.search(r"\S\s*\|\s*\S", ln)]) >= 2:
        return "side_by_side"
    return UNRESOLVED


fn_spec("diff_presentation",
        ["unified_three_lines", "unified_whole_file", "side_by_side", "word_level_inline",
         "stat_summary_only"],
        _diff_presentation)

# --- fmt-0126  ownership_declaration ---


_OWNERSHIP_RECORD = re.compile(r"^\s*(?:@[\w/.-]+:?|[/\w.*\[\]-]+)(?:\s+@[\w/.-]+)*\s*$")


def _ownership_declaration(text: str) -> str:
    """WHICH TOKEN OPENS each record is read, never which tokens are present.
    The first two forms contain exactly the same tokens and are ordered opposites."""
    lines = [ln for ln in first_body(text).splitlines() if ln.strip()]
    comments = [ln for ln in lines if ln.lstrip().startswith("#")]
    # A record is a path or a team, alone or followed by teams. Read as records, "Here is the output:" above a lone @platform made a single-owner file a team block.
    records = [ln for ln in lines
               if not ln.lstrip().startswith("#") and _OWNERSHIP_RECORD.match(ln)]
    if not records:
        return UNRESOLVED
    if re.match(r"^\s*\*\s+\S", records[0]):
        return "default_then_overrides"
    if comments:
        return "commented_section_groups"
    if len(records) == 1 and re.fullmatch(r"\s*@[\w/-]+\s*", records[0]):
        return "single_repository_owner"
    if all(re.match(r"^\s*[/\w*.-]+\s+@\S", r) for r in records):
        return "path_then_team"
    if any(re.match(r"^\s*@[\w/-]+\s*:?\s*$", r) for r in records):
        return "team_then_path_block"
    return UNRESOLVED


fn_spec("ownership_declaration",
        ["path_then_team", "team_then_path_block", "default_then_overrides",
         "commented_section_groups", "single_repository_owner"],
        _ownership_declaration)

# --- fmt-0129  import_group_order ---

_STDLIB = {"os", "sys", "json", "re", "time", "math", "io", "pathlib", "typing", "collections",
           "itertools", "functools", "datetime", "logging", "subprocess", "random", "string",
           "hashlib", "abc", "dataclasses", "enum"}


def _import_origin(module: str) -> int:
    if module.startswith(".") or module.startswith("./") or module.split(".")[0] in {"src", "app"}:
        return 2
    return 0 if module.split(".")[0] in _STDLIB else 1


def _import_group_order(text: str) -> str:
    """The TOP-LEVEL PARTITION is read first, and within-block ordering only
    when there is a single unbroken block -- origin groups can each be
    alphabetical inside themselves, so the two are compatible in principle.
    That is fmt-0129's argument."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for ln in first_body(text).splitlines():
        if ln.strip() and re.match(r"^\s*(?:import|from)\b", ln):
            current.append(ln.strip())
        elif not ln.strip() and current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    if not blocks:
        return UNRESOLVED

    def module(line: str) -> str:
        m = re.match(r"^\s*(?:from|import)\s+([\w./]+)", line)
        return m.group(1) if m else ""

    if len(blocks) > 1:
        if all(re.search(r"\btype\b|\btypes\b|typing", ln, re.I) for ln in blocks[-1]):
            return "type_imports_last"
        origins = [{_import_origin(module(ln)) for ln in b} for b in blocks]
        if all(len(o) == 1 for o in origins):
            flat = [next(iter(o)) for o in origins]
            if flat == sorted(flat) and len(set(flat)) == len(flat):
                return "origin_groups"
        depths = [{module(ln).count(".") + module(ln).count("/") for ln in b} for b in blocks]
        if all(len(d) == 1 for d in depths) and len({next(iter(d)) for d in depths}) == len(blocks):
            return "depth_grouped"
        return UNRESOLVED
    block = blocks[0]
    if len(block) < 2:
        return UNRESOLVED
    if block == sorted(block):
        return "single_alphabetical"
    # Checked on CHARACTERS, not on the paths themselves -- fmt-0129 says so.
    if [len(ln) for ln in block] == sorted(len(ln) for ln in block):
        return "line_length_ascending"
    return UNRESOLVED


fn_spec("import_group_order",
        ["origin_groups", "single_alphabetical", "line_length_ascending", "depth_grouped",
         "type_imports_last"],
        _import_group_order)

# --- fmt-0130  license_notice_form ---


def _license_notice_form(text: str) -> str:
    """The full text is tested first, because a banner or short notice can appear INSIDE it.
    The banner is next, on its rule characters, since the line it frames may itself be a short
    notice."""
    lines = [ln for ln in first_body(text).splitlines() if ln.strip()]
    if not lines:
        return UNRESOLVED
    if len(lines) >= 8:
        return "full_text_block"
    if any(re.search(r"[*=#+-]{6,}", ln) for ln in lines):
        return "boxed_banner"
    body = "\n".join(lines)
    if re.search(r"SPDX-License-Identifier\s*:\s*\S", body, re.I):
        return "identifier_line"
    year = re.search(r"\b(?:19|20)\d{2}\b", body)
    if re.search(r"\b(?:LICEN[SC]E|COPYING)(?:\.\w+)?\b", body) and not year:
        return "file_reference_line"
    if year and re.search(r"Copyright|\(c\)|©", body, re.I):
        return "short_notice_year_holder"
    return UNRESOLVED


fn_spec("license_notice_form",
        ["identifier_line", "full_text_block", "short_notice_year_holder", "file_reference_line",
         "boxed_banner"],
        _license_notice_form)

# --- fmt-0133  editor_settings_scoping ---

_LANGUAGES = {"python", "javascript", "typescript", "go", "rust", "java", "ruby", "php", "c",
              "cpp", "csharp", "html", "css", "scss", "json", "yaml", "markdown", "shell", "sql"}
_SEVERITIES = {"error", "warn", "warning", "off", "info", "none", "hint"}


def _editor_settings_scoping(text: str) -> str:
    """Three forms cut the file into sections and are separated by WHAT THE SECTION HEAD IS.
    The remaining two carry no heads and are told apart by whether any setting name repeats --
    the ordered form repeats them."""
    record = first_record(load_json(text, ordered=True))
    if record is None:
        return UNRESOLVED
    keys = [k for k, _ in record]
    sections = [k for k, v in record if as_dict(v) is not None]
    if sections:
        if all(re.search(r"[*/]", s) for s in sections):
            return "root_file_glob_sections"
        if all(s.lower().lstrip("[").rstrip("]") in _LANGUAGES for s in sections):
            return "language_keyed_map"
        if all(s.lower() in _SEVERITIES for s in sections):
            return "severity_keyed_groups"
        return UNRESOLVED
    if len(keys) != len(set(keys)):
        return "ordered_last_wins"
    return "one_flat_rule_set" if len(keys) >= 2 else UNRESOLVED


fn_spec("editor_settings_scoping",
        ["root_file_glob_sections", "language_keyed_map", "severity_keyed_groups",
         "one_flat_rule_set", "ordered_last_wins"],
        _editor_settings_scoping)

# --- fmt-0135 vendored_code_marking: the capitalised warning is tested first because a stamp carrying it declares itself generated; the patch list may be EMPTY and still present, so it matches on its heading. fmt-0135's exclusivity argument in order ---

spec(
    "vendored_code_marking",
    ("do_not_edit_banner", rx(r"\bDO NOT EDIT\b|\bGENERATED FILE\b|\bDO NOT MODIFY\b")),
    ("checksum_line", rx(r"(?<![0-9a-zA-Z])[0-9a-f]{32,64}(?![0-9a-zA-Z])")),
    ("version_and_date_line", rx(r"v?\d+\.\d+(?:\.\d+)?\b[^\n]{0,40}\b(?:19|20)\d{2}-\d{2}-\d{2}\b|"
                                  r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b[^\n]{0,40}\bv?\d+\.\d+")),
    ("local_patch_list", rx(r"^[\s#/*]*(?:local\s+)?patch(?:es)?\s*:", re.I | re.M)),
    ("upstream_name_line", rx(r"^[\s#/*]*(?:upstream|vendored from|source|copied from)\s*:\s*\S",
                               re.I | re.M)),
)

# --- fmt-0136  help_text_layout ---


def _help_text_layout(text: str) -> str:
    """A usage line and a worked example are both single lines of sample
    invocation, so their POSITION relative to the flag list is read rather than
    their content. The table and prose forms are split on whether flag names
    occupy a column of their own. fmt-0136's argument."""
    lines = first_body(text).splitlines()
    if re.search(r"^\s*(?:\d+\.\s+)?(?:NAME|SYNOPSIS|DESCRIPTION|OPTIONS|EXAMPLES)\s*$",
                 "\n".join(lines), re.M):
        return "sectioned_man_style"
    flags = [i for i, ln in enumerate(lines) if re.match(r"^\s*-{1,2}[\w-]+", ln)]
    if not flags:
        paragraphs = [p for p in re.split(r"\n\s*\n", first_body(text)) if p.strip()]
        return "prose_paragraphs" if len(paragraphs) >= 2 else UNRESOLVED
    usage = next((i for i, ln in enumerate(lines) if re.match(r"^\s*usage\b", ln, re.I)), None)
    example = next((i for i, ln in enumerate(lines) if re.match(r"^\s*examples?\b", ln, re.I)), None)
    if usage is not None and usage < flags[0]:
        return "usage_then_flags"
    if example is not None and example > flags[-1]:
        return "flags_then_examples"
    columns = {len(m.group(1)) for i in flags
               if (m := re.match(r"^(\s*-{1,2}[\w-]+\s+)\S", lines[i]))}
    if len(columns) == 1 and len(flags) >= 2:
        return "two_column_table"
    return UNRESOLVED


fn_spec("help_text_layout",
        ["usage_then_flags", "flags_then_examples", "two_column_table", "prose_paragraphs",
         "sectioned_man_style"],
        _help_text_layout)

# --- fmt-0139  script_argument_style ---


def _script_argument_style(text: str) -> str:
    """Whether the FIRST NON-FLAG WORD selects behaviour, read before any flags
    are counted -- the subcommand form carries flags too, so otherwise every
    subcommand invocation also satisfies the flags label. The config-file form
    takes exactly one positional path. fmt-0139's argument."""
    # `[ \t]*`, not `\s*`: with `\s*` the arguments ran onto the next line and a sign-off read as positional arguments.
    m = re.search(r"^[^\n]*?(?:\./)?[\w-]+\.(?:sh|py|rb|js)[ \t]*([^\n]*)$", first_body(text), re.M)
    if not m:
        return UNRESOLVED
    args = m.group(1).split()
    if not args:
        return "environment_driven" if re.search(r"^\s*[A-Z][A-Z0-9_]{2,}\s*=", text, re.M) \
            else UNRESOLVED
    if not args[0].startswith("-"):
        if len(args) == 1 and re.search(r"\.(?:ya?ml|toml|json|ini|conf|cfg)$", args[0]):
            return "config_file_argument"
        if any(a.startswith("-") for a in args[1:]):
            return "subcommand_first"
        return "positional_only"
    return "long_flags_only" if all(a.startswith("--") or not a.startswith("-")
                                    for a in args) else UNRESOLVED


fn_spec("script_argument_style",
        ["positional_only", "long_flags_only", "subcommand_first", "environment_driven",
         "config_file_argument"],
        _script_argument_style)

# --- fmt-0140  workspace_glob_declaration ---


def _workspace_glob_declaration(text: str) -> str:
    """STARS ARE COUNTED, not tested for.
    The one-star and two-star globs differ by a single character in the same position; the
    per-layer form is several one-star globs, separated by how many there are."""
    entries = re.findall(r"[\"']([!\w*./-]+)[\"']", first_body(text))
    if not entries:
        entries = [e.strip() for e in re.split(r"[,\n]", first_body(text))
                   if re.fullmatch(r"\s*[-*]?\s*[!\w*./-]+\s*", e)]
        entries = [e.lstrip("-* ").strip() for e in entries if e.strip()]
    # A member entry is a PATH or a glob, so every entry must carry a separator or a star -- without it an apology split on commas into a one-entry member list.
    entries = [e for e in entries if e and re.search(r"[/*]", e)]
    if not entries:
        return UNRESOLVED
    if any(e.startswith("!") for e in entries):
        return "glob_with_exclusion"
    if any("**" in e for e in entries):
        return "double_star_glob"
    starred = [e for e in entries if "*" in e]
    if len(starred) >= 2:
        return "per_layer_globs"
    if len(starred) == 1:
        return "single_star_glob"
    return "explicit_path_list"


fn_spec("workspace_glob_declaration",
        ["explicit_path_list", "single_star_glob", "double_star_glob", "per_layer_globs",
         "glob_with_exclusion"],
        _workspace_glob_declaration)

# --- fmt-0142  matrix_axis_declaration ---


def _matrix_axis_declaration(text: str) -> str:
    """The exclusion form and the plain cross product declare IDENTICAL AXES and
    differ only by a block that may be empty, so that block must be present and
    NON-EMPTY rather than inferred from how many jobs actually ran. The
    explicit list declares no axes at all. fmt-0142's argument."""
    body = first_body(text)
    exclude = re.search(r"^\s*exclude\s*:\s*$\n\s+\S", body, re.M | re.I)
    include = re.search(r"^\s*include\s*:\s*$\n\s+\S", body, re.M | re.I)
    axes = re.findall(r"^\s{2,}([\w-]+)\s*:\s*\[", body, re.M)
    if not axes:
        axes = re.findall(r"^\s{2,}([\w-]+)\s*:\s*$\n(?:\s+-\s+\S+\n?)+", body, re.M)
    axes = [a for a in axes if a.lower() not in {"include", "exclude", "matrix", "strategy"}]
    if exclude and len(axes) >= 2:
        return "cross_with_exclusions"
    if include and len(axes) == 1:
        return "primary_axis_plus_extras"
    if len(axes) >= 2:
        return "full_cross_product"
    if re.search(r"^\s*matrix\s*:\s*$\n\s+-\s+\S", body, re.M | re.I) or \
            (include and not axes):
        return "explicit_combination_list"
    jobs = re.findall(r"^\s{2}([\w-]+)\s*:\s*$", body, re.M)
    if len([j for j in jobs if j.lower() not in {"strategy", "matrix"}]) >= 2:
        return "separate_jobs_no_matrix"
    return UNRESOLVED


fn_spec("matrix_axis_declaration",
        ["full_cross_product", "explicit_combination_list", "cross_with_exclusions",
         "primary_axis_plus_extras", "separate_jobs_no_matrix"],
        _matrix_axis_declaration)


# --- fmt-0143  hook_declaration_style ---


def _hook_declaration_style(text: str) -> str:
    """Whether A SCRIPT THE TEAM MAINTAINS sits between the hook and the tools.
    The dispatcher and the declarative list both read their work from a tracked file; the inline
    form declares no file at all."""
    body = first_body(text)
    if re.search(r"\bln\s+-s\b|\bsymlink", body, re.I):
        return "shared_symlinked_directory"
    if re.search(r"\b[\w./-]+\.(?:sh|py|rb)\b", body) and \
            re.search(r"\bregistry\b|\bhooks\.(?:toml|ya?ml|json|txt)\b", body, re.I):
        return "dispatcher_with_registry"
    if re.search(r"^\s*-\s+(?:id|repo|hook|tool|name)\s*:", body, re.M | re.I) or \
            re.search(r"^\s*hooks\s*:\s*$", body, re.M | re.I):
        return "declarative_tool_list"
    if re.search(r"\.git/hooks/(?:pre-commit|pre-push|commit-msg|prepare-commit-msg)", body):
        return "script_per_phase"
    if re.search(r"^\s*(?:command|entry|run|exec)\s*[:=]\s*\S", body, re.M | re.I):
        return "inline_command"
    return UNRESOLVED


fn_spec("hook_declaration_style",
        ["script_per_phase", "declarative_tool_list", "dispatcher_with_registry",
         "shared_symlinked_directory", "inline_command"],
        _hook_declaration_style)

# --- fmt-0148  phony_target_declaration ---


def _phony_target_declaration(text: str) -> str:
    """The grouped and per-target forms use the IDENTICAL directive and differ
    only in how many times it appears, so occurrences are counted rather than
    the directive matched once. The naming convention is tested last, since a
    file using any of the other four may also follow it. fmt-0148's argument."""
    body = first_body(text)
    phony = re.findall(r"^\s*\.PHONY\s*:\s*(.*)$", body, re.M)
    if len(phony) > 1:
        return "per_target_declaration"
    if len(phony) == 1:
        return "one_grouped_declaration" if len(phony[0].split()) >= 2 else UNRESOLVED
    rules = re.findall(r"^([\w.%/-]+)[ \t]*:(?!=)[ \t]*(.*)$", body, re.M)
    if not rules:
        return UNRESOLVED
    # The sentinel and pattern forms use no directive at all, and are separated by whether the extra name is a DEPENDENCY or a RULE HEAD.
    if any("%" in head for head, _ in rules):
        return "pattern_rule"
    dependency_sets = [set(deps.split()) for head, deps in rules if deps.strip()]
    if len(dependency_sets) >= 2:
        shared = set.intersection(*dependency_sets)
        if shared and not any(s in {h for h, _ in rules} and
                              dict(rules)[s].strip() for s in shared):
            return "sentinel_dependency"
    return "naming_convention_only" if len(rules) >= 2 else UNRESOLVED


fn_spec("phony_target_declaration",
        ["one_grouped_declaration", "per_target_declaration", "naming_convention_only",
         "sentinel_dependency", "pattern_rule"],
        _phony_target_declaration)

# --- fmt-0153  default_value_documentation ---


def _default_value_documentation(text: str) -> str:
    """The BRACKET CHARACTERS are compared rather than a bracketed run looked for.
    Round and square brackets both sit inside the description line. The post-name form places
    the value between the flag and its description."""
    body = first_body(text)
    lines = body.splitlines()
    flags = [ln for ln in lines if re.match(r"^\s*--[\w-]+", ln)]
    if not flags:
        return UNRESOLVED
    last_flag = max(i for i, ln in enumerate(lines) if re.match(r"^\s*--[\w-]+", ln))
    if any(re.search(r"\bdefaults?\b", ln, re.I) for ln in lines[last_flag + 1:]):
        return "footer_list"
    if re.search(r"\(\s*default[^)]*\)", body, re.I):
        return "parenthetical_suffix"
    if re.search(r"\[\s*default[^\]]*\]", body, re.I):
        return "inline_bracket"
    parts = [re.match(r"^(\s*--[\w-]+\s+)(\S+)(\s+)(\S.*)$", ln) for ln in flags]
    if not all(parts):
        return UNRESOLVED
    description_columns = {len(m.group(1)) + len(m.group(2)) + len(m.group(3)) for m in parts}
    return "separate_column" if len(description_columns) == 1 else "after_flag_name"


fn_spec("default_value_documentation",
        ["parenthetical_suffix", "separate_column", "inline_bracket", "after_flag_name",
         "footer_list"],
        _default_value_documentation)

# --- fmt-0154  required_config_placeholder ---


def _required_config_placeholder(text: str) -> str:
    """Taken from the FILE TEXT, never the parsed tree.
    An empty value and a null value both read as unset once parsed, and the text is the only
    place they still differ."""
    body = first_body(text)
    if re.search(r":\s*<[\w ._-]+>", body):
        return "angle_bracket_token"
    if re.search(r"\bCHANGE[-_ ]?ME\b|\bchangeme\b|\bREPLACE[-_ ]?ME\b", body, re.I):
        return "changeme_literal"
    if re.search(r":\s*(?:null|~)\s*(?:#|$)", body, re.M | re.I) and \
            re.search(r"\brequired\b", body, re.I):
        return "null_with_required_flag"
    comments = [ln for ln in body.splitlines() if ln.lstrip().startswith("#")]
    if any(re.match(r"^\s*#\s*[\w.-]+\s*:\s*\S", ln) for ln in comments):
        return "commented_example_value"
    if comments and re.search(r"^\s*[\w.-]+\s*:\s*$", body, re.M):
        return "empty_with_comment"
    return UNRESOLVED


fn_spec("required_config_placeholder",
        ["angle_bracket_token", "empty_with_comment", "changeme_literal",
         "commented_example_value", "null_with_required_flag"],
        _required_config_placeholder)

# --- fmt-0155  skipped_test_marking ---


def _skipped_test_marking(text: str) -> str:
    """The skip annotation and the expected-failure marker are both decorators
    above the body, and are told apart by which one they are; the guarded form
    carries no decorator and is tested AFTER both, to keep a decorated test
    that also returns early from reading as a guard. fmt-0155's argument."""
    body = first_body(text)
    if re.search(r"@[\w.]*(?:xfail|expectedfailure|expected_failure)", body, re.I):
        return "expected_failure_marker"
    if re.search(r"@[\w.]*skip\w*", body, re.I):
        return "skip_annotation_with_reason"
    lines = [ln for ln in body.splitlines() if ln.strip()]
    definition = next((i for i, ln in enumerate(lines) if re.match(r"^\s*def\s+\w+", ln)), None)
    if definition is None:
        # A commented-out body is never collected, so it carries no marker and no live definition either.
        if lines and all(ln.lstrip().startswith(("#", "//")) for ln in lines):
            return "commented_out_body"
        return UNRESOLVED
    if all(ln.lstrip().startswith("#") for ln in lines[definition + 1:]) and \
            len(lines) > definition + 1:
        return "commented_out_body"
    name = re.match(r"^\s*def\s+(\w+)", lines[definition]).group(1)
    if re.match(r"^(?:skip|skipped|disabled|x|wip)_", name, re.I):
        return "name_prefix_marker"
    if re.search(r"^\s+if\s+[^\n]+:\s*\n\s+return\b", body, re.M):
        return "conditional_early_return"
    return UNRESOLVED


fn_spec("skipped_test_marking",
        ["skip_annotation_with_reason", "commented_out_body", "name_prefix_marker",
         "conditional_early_return", "expected_failure_marker"],
        _skipped_test_marking)

# --- fmt-0156  merge_requirement_expression ---


def _merge_requirement_expression(text: str) -> str:
    """The count-plus-owner rule satisfies the plain count rule on every merge
    it permits, so the label is read from the WRITTEN POLICY rather than from
    any individual merge. A policy stating a global count and then delegating
    some paths to their own rules is 'other'. fmt-0156's argument."""
    body = first_body(text)
    path_rule = re.compile(r"^\s*[/\w*.-]+/\S*\s*[:\-]\s*\S")
    path_lines = [ln for ln in body.splitlines() if path_rule.match(ln)]
    per_path = len(path_lines) >= 2
    # The count is read off whatever is NOT a path rule, so a policy made entirely of per-path rules is not also a global count.
    global_text = "\n".join(ln for ln in body.splitlines() if not path_rule.match(ln))
    count = bool(re.search(r"\b(?:\d+|one|two|three)\s+approvals?\b|"
                           r"\brequires?\s+(?:\d+|one|two|three)\b", global_text, re.I))
    owner = bool(re.search(r"\bcode ?owner|\bowner(?:'s)? approval|\bowning team\b",
                           global_text, re.I))
    # The combining word is what the count-plus-owner policy writes; without it the plain owner rule could never be reported.
    combined = bool(re.search(r"\b(?:including|one of (?:which|them)|plus|of which|"
                              r"and at least one)\b", global_text, re.I))
    if count and per_path:
        return UNRESOLVED
    if per_path:
        return "per_path_rules"
    if count and owner and combined:
        return "count_plus_owner"
    if owner:
        return "owner_approval_only"
    if count:
        return "fixed_reviewer_count"
    if re.search(r"\b(?:checks?|pipelines?|CI)\b[^.\n]{0,40}\b(?:green|pass\w*)\b|"
                 r"\bno (?:human )?(?:approval|review)\b", body, re.I):
        return "checks_only"
    return UNRESOLVED


fn_spec("merge_requirement_expression",
        ["fixed_reviewer_count", "owner_approval_only", "count_plus_owner", "per_path_rules",
         "checks_only"],
        _merge_requirement_expression)

# --- fmt-0157  toolchain_pin_declaration ---


def _toolchain_pin_declaration(text: str) -> str:
    """WHICH FILE carries the version is read, not the string's shape.
    The root version file and the manifest field both hold a bare version string. The setup
    script states no version of its own."""
    body = first_body(text)
    if re.search(r"^\s*FROM\s+\S+:\S+|^\s*image\s*:\s*\S+:\S+", body, re.M | re.I):
        return "image_reference"
    if re.search(r"[\"']engines[\"']\s*:|^\s*engines\s*:", body, re.M):
        return "manifest_engines_field"
    if re.search(r"\.(?:nvmrc|node-version|tool-versions|python-version|ruby-version)\b|"
                 r"\brust-toolchain(?:\.toml)?\b", body, re.I):
        return "root_version_file"
    if re.search(r"#!/|\.sh\b", body) and re.search(r"\d+\.\d+", body):
        return "script_enforced"
    if re.search(r"\bREADME\b", body, re.I) or re.search(r"^#{1,6}\s", body, re.M):
        return "readme_prose_only"
    return UNRESOLVED


fn_spec("toolchain_pin_declaration",
        ["root_version_file", "manifest_engines_field", "image_reference", "readme_prose_only",
         "script_enforced"],
        _toolchain_pin_declaration)

# --- fmt-0159  optional_dependency_grouping ---


def _optional_dependency_grouping(text: str) -> str:
    """The named group and the development section both sit under a heading of
    their own, so the label reads whether that heading is a TEAM-CHOSEN WORD or
    the RESERVED development key. The three main-list forms are separated by
    what rides on the dependency's line. fmt-0159's argument."""
    body = first_body(text)
    if re.search(r"^\s*\[?(?:tool\.\w+\.)?(?:dev-dependencies|devDependencies|dev)\]?\s*[:=\]]",
                 body, re.M):
        return "dev_section_split"
    if re.search(r"^\s*\[?(?:project\.)?optional-dependencies\]?|^\s*\[?extras?\]?\s*[:=\]]|"
                 r"^\s*\[?(?:tool\.\w+\.)?extras[\w.-]*\]", body, re.M | re.I):
        return "named_extra_group"
    if re.search(r"optional\s*=\s*true|\boptional\b\s*:\s*true", body, re.I):
        return "per_line_optional_flag"
    if re.search(r";\s*(?:sys_platform|platform_machine|platform_system|os_name)\s*[=!]", body):
        return "platform_markers"
    if re.search(r"^\s*[\"']?[\w.-]+[\"']?\s*[=:]\s*[\"']?[\^~>=<]?\d", body, re.M):
        return "all_required"
    return UNRESOLVED


fn_spec("optional_dependency_grouping",
        ["named_extra_group", "dev_section_split", "per_line_optional_flag", "all_required",
         "platform_markers"],
        _optional_dependency_grouping)

# --- fmt-0222 migration_revert_strategy_declaration: irreversible first, since a file may carry one and still show a change block; a transaction wrapper LAST, since any of the other four may also sit inside BEGIN/COMMIT ---

spec(
    "migration_revert_strategy_declaration",
    ("prohibited_irreversible", rx(r"\birreversible\b|\bnot reversible\b|@irreversible|"
                                    r"\bdisable_ddl\b|\bno rollback\b", re.I)),
    ("dedicated_down_block", rx(r"^\s*--\s*down\b|\bdef\s+down\b|^\s*down\s*:|"
                                 r"^\s*-{2,}\s*\+?migrate\s+Down\b", re.I | re.M)),
    ("reversible_change_block", rx(r"\bdef\s+change\b|^\s*change\s*:|\breversible\b",
                                    re.I | re.M)),
    ("sql_comment_toggle", rx(r"^\s*--\s*(?:DROP|ALTER|DELETE|TRUNCATE|CREATE)\b", re.I | re.M)),
    ("transaction_wrapper", rx(r"\bBEGIN\b[\s\S]{0,600}\bCOMMIT\b", re.I)),
)

# --- fmt-0228  cache_revalidation_policy_header ---


def _cache_revalidation_policy_header(text: str) -> str:
    """Read as a DIRECTIVE SET, because four of the five write an age and are
    separated only by what accompanies it. Contradictory tokens -- a no-store
    beside a max-age -- are 'other'. fmt-0228's argument."""
    value = header_value(text, "Cache-Control") or first_body(text)
    directives = {d.strip().lower().split("=")[0].strip() for d in value.split(",")}
    directives.discard("")
    if not directives & {"no-store", "no-cache", "max-age", "s-maxage", "immutable",
                         "must-revalidate", "stale-while-revalidate"}:
        return UNRESOLVED
    has_age = bool(directives & {"max-age", "s-maxage"})
    if "no-store" in directives:
        return "no_store_strict" if not has_age and len(directives - {"no-store"}) == 0 \
            else UNRESOLVED
    if "no-cache" in directives:
        return "no_cache_alone" if not has_age else UNRESOLVED
    if not has_age:
        return UNRESOLVED
    if "immutable" in directives:
        return "immutable_long"
    if "stale-while-revalidate" in directives:
        return "stale_while_revalidate"
    if "must-revalidate" in directives:
        return "must_revalidate_max"
    return UNRESOLVED


fn_spec("cache_revalidation_policy_header",
        ["must_revalidate_max", "no_cache_alone", "immutable_long", "stale_while_revalidate",
         "no_store_strict"],
        _cache_revalidation_policy_header)


# --- fmt-0173  note_placement ---

_NOTE_LINE = re.compile(r"^\s*(?:\[\d+\]|\(\d+\)|\d+\.|Note\b[:.])\s*\S")
_CITE = re.compile(r"\S\s*(?:\[\d+\]|\(\d+\))")


def _note_placement(text: str) -> str:
    """WHERE THE NOTE TEXT SITS relative to the line that cites it.
    The preface form is tested first, since a note standing before the passage is the only one
    no citing line precedes."""
    lines = [ln for ln in first_body(text).splitlines() if ln.strip()]
    if not lines:
        return UNRESOLVED
    notes = [i for i, ln in enumerate(lines) if _NOTE_LINE.match(ln)]
    cites = [i for i, ln in enumerate(lines) if _CITE.search(ln) and i not in notes]
    if not notes:
        return "inline_parenthetical" if re.search(r"\([^)\n]{12,}\)", first_body(text)) \
            else UNRESOLVED
    if not cites:
        return UNRESOLVED
    # fmt-0173: a passage placing notes in TWO of these positions is 'other', so notes on both sides resolve to nothing rather than to whichever came first.
    before = [n for n in notes if n < cites[0]]
    after = [n for n in notes if n > cites[0]]
    if before and after:
        return UNRESOLVED
    if before:
        return "preface_before_passage"
    if all(any(c == n - 1 for c in cites) for n in notes):
        return "beneath_citing_line"
    if all(lines[n][:1] in (" ", "\t") for n in notes):
        return "indented_under_paragraph"
    if all(n > cites[-1] for n in notes):
        return "end_of_passage"
    return UNRESOLVED


fn_spec("note_placement",
        ["beneath_citing_line", "end_of_passage", "inline_parenthetical",
         "indented_under_paragraph", "preface_before_passage"],
        _note_placement)

# --- fmt-0174  table_caption_position ---

_CAPTION = re.compile(r"\bTable\s*\d*\s*[.:]|\bCaption\s*[.:]", re.I)


def _table_caption_position(text: str) -> str:
    """Whether the caption lies INSIDE the table's own borders is tested before
    position at all -- a caption occupying the first row also sits above the
    table's data. The preceding-paragraph form carries no caption label, which
    is what separates it from the above-table form. fmt-0174's argument."""
    lines = [ln for ln in first_body(text).splitlines() if ln.strip()]
    rows = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("|")]
    if not rows:
        return UNRESOLVED
    first, last = rows[0], rows[-1]
    if _CAPTION.search(lines[first]):
        return "first_row"
    if _CAPTION.search(lines[last]):
        return "last_row"
    if first > 0 and _CAPTION.search(lines[first - 1]):
        return "above_table"
    if last + 1 < len(lines) and _CAPTION.search(lines[last + 1]):
        return "below_table"
    if first > 0 and len(lines[first - 1].split()) >= 6:
        return "in_preceding_paragraph"
    return UNRESOLVED


fn_spec("table_caption_position",
        ["above_table", "below_table", "first_row", "in_preceding_paragraph", "last_row"],
        _table_caption_position)

# --- fmt-0177  measurement_presentation ---

_METRIC = r"\d+(?:\.\d+)?\s*(?:mm|cm|m|kg|g|ml|l)\b"
_IMPERIAL = r"\d+(?:\.\d+)?\s*(?:in\b|inch(?:es)?\b|ft\b|feet\b|lbs?\b|oz\b|\")"


def _measurement_presentation(text: str) -> str:
    """The two dual forms carry the SAME TWO NUMBERS and differ only in which is
    bracketed, so what sits INSIDE the brackets is read rather than which
    system appears anywhere. The column form brackets nothing, which keeps it
    outside both dual labels. fmt-0177's argument."""
    body = first_body(text)
    bracketed = " ".join(re.findall(r"\(([^)\n]*)\)", body))
    outside = re.sub(r"\([^)\n]*\)", " ", body)
    metric_in = bool(re.search(_METRIC, bracketed, re.I))
    imperial_in = bool(re.search(_IMPERIAL, bracketed, re.I))
    metric_out = bool(re.search(_METRIC, outside, re.I))
    imperial_out = bool(re.search(_IMPERIAL, outside, re.I))
    if not bracketed.strip() and metric_out and imperial_out:
        return "parallel_columns"
    if metric_out and imperial_in and not metric_in:
        return "metric_then_imperial"
    if imperial_out and metric_in and not imperial_in:
        return "imperial_then_metric"
    if metric_out and not (imperial_out or imperial_in):
        return "metric_only"
    if imperial_out and not (metric_out or metric_in):
        return "imperial_only"
    return UNRESOLVED


fn_spec("measurement_presentation",
        ["metric_only", "imperial_only", "metric_then_imperial", "imperial_then_metric",
         "parallel_columns"],
        _measurement_presentation)

# --- fmt-0179  footnote_marker_position ---

_RAISED = r"(?:[¹²³⁰-⁹]+|<sup>\d+</sup>|\[\d+\])"


def _footnote_marker_position(text: str) -> str:
    """The inline bracketed marker is set at FULL SIZE rather than raised.
    That separates it from every raised form before position is considered. The paragraph-end
    form places ONE marker for the whole paragraph."""
    # Without framing: a sign-off after the chapter moved "the end of the paragraph" off the marker.
    body = unwrap(text)
    if re.search(r"\(\d+\)", body):
        return "inline_bracketed"
    markers = list(re.finditer(_RAISED, body))
    if not markers:
        return UNRESOLVED
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", body.strip()) if s.strip()]
    if len(markers) == 1 and markers[0].end() >= len(body.rstrip()) and len(sentences) >= 2:
        return "paragraph_end"
    if re.search(rf"\.\s*{_RAISED}", body):
        return "after_terminal_period"
    if re.search(rf"{_RAISED}\s*\.", body):
        return "before_terminal_period"
    if re.search(rf"\w{_RAISED}\s+\w", body):
        return "at_the_cited_word"
    return UNRESOLVED


fn_spec("footnote_marker_position",
        ["after_terminal_period", "before_terminal_period", "at_the_cited_word", "paragraph_end",
         "inline_bracketed"],
        _footnote_marker_position)

# --- fmt-0184  amount_scale_statement ---

_SCALE = re.compile(r"\(\s*[£$€]?\s*(?:m|bn|k|000s|millions?|thousands?|billions?)\b[^)]*\)|"
                    r"\bin\s+(?:millions|thousands|billions)\b", re.I)


def _amount_scale_statement(text: str) -> str:
    """Three rules shorten the same digits and differ only in WHERE the scale is
    declared, so the location is read and two locations at once is 'other'. The
    unscaled rule is granted only when the widest figure carries its full digit
    count, which no shortened form does. fmt-0184's argument."""
    lines = [ln for ln in first_body(text).splitlines() if ln.strip()]
    if not lines:
        return UNRESOLVED
    rows = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("|")]
    found = []
    if any(re.search(r"\d[\d,.]*\s*(?:m|bn|k)\b", ln) for ln in lines):
        found.append("per_figure_suffix")
    if rows and _SCALE.search(lines[rows[0]]):
        found.append("column_heading")
    if rows and rows[0] > 0 and _SCALE.search(lines[rows[0] - 1]):
        found.append("table_caption")
    if rows and rows[-1] + 1 < len(lines) and \
            any(_SCALE.search(ln) for ln in lines[rows[-1] + 1:]):
        found.append("closing_footnote")
    if found:
        return one_of(found)
    widest = max((len(re.sub(r"[^\d]", "", m)) for m in re.findall(r"[\d,]{4,}", "\n".join(lines))),
                 default=0)
    return "unscaled_full_digits" if widest >= 7 else UNRESOLVED


fn_spec("amount_scale_statement",
        ["column_heading", "table_caption", "per_figure_suffix", "unscaled_full_digits",
         "closing_footnote"],
        _amount_scale_statement)

# --- fmt-0187  optional_step_marking ---

_STEP = re.compile(r"^\s*\d+[.)]\s*(.*)$")


def _optional_step_marking(text: str) -> str:
    """The bracketed word and the opening label use the SAME WORD, so its
    POSITION within the step is read rather than the word itself. The note
    beneath and the separate section both lift the step out of the numbered
    run, and are separated by whether the run continues after it. fmt-0187."""
    lines = [ln for ln in first_body(text).splitlines() if ln.strip()]
    steps = [i for i, ln in enumerate(lines) if _STEP.match(ln)]
    if not steps:
        return UNRESOLVED
    for i in steps:
        body = _STEP.match(lines[i]).group(1)
        if re.search(r"\(\s*optional\s*\)\s*$", body, re.I):
            return "trailing_parenthetical"
        if re.match(r"^Optional\s*:", body, re.I):
            return "leading_label_colon"
        if re.match(r"^If\b", body):
            return "if_clause"
    marker = next((i for i, ln in enumerate(lines)
                   if i not in steps and re.search(r"\boptional\b", ln, re.I)), None)
    if marker is None:
        return UNRESOLVED
    return "note_beneath" if any(i > marker for i in steps) else "separate_section"


fn_spec("optional_step_marking",
        ["trailing_parenthetical", "leading_label_colon", "if_clause", "note_beneath",
         "separate_section"],
        _optional_step_marking)

# --- fmt-0188  warning_presentation ---

_WARN_WORD = r"(?:warning|caution|danger|important|note)"


def _warning_presentation(text: str) -> str:
    """Whether a BORDER or a HEADING WORD encloses the text, not the indentation
    alone -- the boxed callout and the indented block are both set apart from
    the column. The glyph and the bold label both open the paragraph, and only
    one of the two is a word. fmt-0188's argument."""
    body = first_body(text)
    if re.search(r"^\s*[+|][-=+]{4,}", body, re.M) or re.search(r"[┌└│─]", body) or \
            re.search(rf"^\s*>\s*\*\*{_WARN_WORD}\*\*", body, re.I | re.M):
        return "boxed_callout"
    if re.search(rf"^\s*\d+[.)]\s*{_WARN_WORD}\b", body, re.I | re.M):
        return "numbered_caution_step"
    if re.search(r"^\s*[⚠❗☠▲!]️?\s+\S", body, re.M):
        return "glyph_prefix"
    if re.search(rf"^\s*\*\*{_WARN_WORD}[:!]?\*\*", body, re.I | re.M):
        return "bold_inline_label"
    if re.search(r"^(?: {4,}|\t)\S", body, re.M) and \
            re.search(r"<small>|smaller type|\bsmall\b", body, re.I):
        return "indented_small_type"
    return UNRESOLVED


fn_spec("warning_presentation",
        ["bold_inline_label", "boxed_callout", "glyph_prefix", "numbered_caution_step",
         "indented_small_type"],
        _warning_presentation)

# --- fmt-0193  bullet_terminal_punctuation ---


def _bullet_terminal_punctuation(text: str) -> str:
    """Read from the items BEFORE the last, because the final-bullet rule and
    the every-bullet rule agree on the last item. A list of one bullet is
    'other'. fmt-0193's argument."""
    bullets = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", ln).strip()
               for ln in first_body(text).splitlines()
               if re.match(r"^\s*(?:[-*•]|\d+[.)])\s+\S", ln)]
    if len(bullets) < 2:
        return UNRESOLVED
    earlier, last = bullets[:-1], bullets[-1]
    ends = [b[-1] for b in earlier if b]
    if len(ends) != len(earlier):
        return UNRESOLVED
    if all(e == ";" for e in ends) and last.endswith("."):
        return "semicolons_then_period"
    if all(e == "," for e in ends) and re.match(r"^and\b", last, re.I):
        return "commas_with_conjunction"
    if all(e == "." for e in ends) and last.endswith("."):
        return "period_on_each"
    if not any(e in ".;," for e in ends) and last.endswith("."):
        return "period_on_last_only"
    if not any(e in ".;," for e in ends) and not last.endswith("."):
        return "no_terminal_mark"
    return UNRESOLVED


fn_spec("bullet_terminal_punctuation",
        ["no_terminal_mark", "period_on_each", "period_on_last_only", "semicolons_then_period",
         "commas_with_conjunction"],
        _bullet_terminal_punctuation)

# --- fmt-0194  definition_list_layout ---


_MD_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$\n\s*\|[\s:|-]+\|\s*$", re.M)


def _definition_list_layout(text: str) -> str:
    """The dash and colon forms share the same single-line shape, so the JOINING
    CHARACTER alone is read and an entry carrying both is 'other'. The indented
    and heading forms both put the term on its own line, and are separated by
    whether the term carries heading markup. fmt-0194's argument."""
    lines = [ln for ln in first_body(text).splitlines() if ln.strip()]
    if not lines:
        return UNRESOLVED
    if _MD_TABLE_ROW.search(first_body(text)):
        return "two_column_table"
    if any(re.match(r"^\s*(?:#{1,6}\s+\S|\*\*[^*\n]+\*\*\s*$)", ln) for ln in lines):
        return "heading_and_paragraph"
    dash = [ln for ln in lines if re.match(r"^\s*\S[^\n:]*?\s+[—–-]\s+\S", ln)]
    colon = [ln for ln in lines if re.match(r"^\s*\S[^\n]*?\s*:\s+\S", ln)]
    if dash and colon:
        return UNRESOLVED
    if dash:
        return "dash_same_line"
    if colon:
        return "colon_same_line"
    if any(re.match(r"^(?: {2,}|\t)\S", ln) for ln in lines):
        return "term_line_indented_definition"
    return UNRESOLVED


fn_spec("definition_list_layout",
        ["term_line_indented_definition", "dash_same_line", "colon_same_line", "two_column_table",
         "heading_and_paragraph"],
        _definition_list_layout)

# --- fmt-0195  glossary_ordering ---


def _glossary_ordering(text: str) -> str:
    """The TOP-LEVEL PARTITION is read first, and the strict label granted only
    where there is no partition at all -- three of the rules sort alphabetically
    inside something. fmt-0195's argument."""
    body = first_body(text)
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if not lines:
        return UNRESOLVED
    if _MD_TABLE_ROW.search(body) or any(re.search(r"\S\s{4,}\S[^\n]*\s{4,}\S", ln)
                                         for ln in lines):
        return "two_column_split"
    if any(re.match(r"^\s*(?:#{1,6}\s*)?[A-Z]\s*$", ln) for ln in lines):
        return "letter_headings"
    if any(re.match(r"^\s*#{1,6}\s+\S", ln) for ln in lines):
        return "topic_grouped"
    terms = [m.group(1) for ln in lines
             if (m := re.match(r"^\s*(?:[-*]\s*)?([A-Za-z][\w ]*?)\s*[-—:]\s+\S", ln))]
    if len(terms) < 3:
        return UNRESOLVED
    acronyms = [t.isupper() for t in terms]
    if any(acronyms) and not all(acronyms) and acronyms == sorted(acronyms, reverse=True):
        return "acronyms_first"
    lowered = [t.lower() for t in terms]
    return "strict_alphabetical" if lowered == sorted(lowered) else UNRESOLVED


fn_spec("glossary_ordering",
        ["strict_alphabetical", "topic_grouped", "acronyms_first", "letter_headings",
         "two_column_split"],
        _glossary_ordering)
