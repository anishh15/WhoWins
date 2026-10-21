"""Repository and tooling conventions -- fmt-0111..0160.
The choice is a naming or declaration convention, so the classifier reads an identifier's
parts rather than the prose around it. Conventions nest, so the rule order carries the
exclusivity argument."""

from __future__ import annotations

import re

from ..core import UNRESOLVED
from ._lib import first_body, fn_spec, looks_like_sentence, rx, spec, vocab


def _words(name: str) -> list[str]:
    """Split an identifier into lower-case words, snake or camel."""
    parts = re.split(r"[_\-. ]+", name)
    out: list[str] = []
    for p in parts:
        out.extend(w.lower() for w in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+", p))
    return [w for w in out if w]


def _body_lines(text: str) -> list[str]:
    """Non-blank lines of the fenced body, indentation intact.

    Named apart from `prose._lines`, which strips each line and does not unfence:
    several keys here read a line's leading whitespace, and several there do not."""
    return [ln for ln in first_body(text).splitlines() if ln.strip()]


def _agree(labels: set[str]) -> str:
    """One label, or nothing. A file written half one way is not a house style."""
    return labels.pop() if len(labels) == 1 else UNRESOLVED


# --- fmt-0111  dependency_constraint_style ---


def _dependency_constraint(text: str) -> str:
    """Read the operator token, never the release set it resolves to.
    A caret on a zero-major version resolves to exactly what a tilde would, so a checker
    reasoning about resolved ranges would merge the two labels."""
    caret = bool(re.search(r"\^\s*\d", text))
    tilde = bool(re.search(r"~>?\s*\d", text))
    comps = re.findall(r"[<>]=?\s*\d", text)
    wild = bool(re.search(r"\d+\.[\dx*]*[x*](?![\d.])", text, re.I))
    exact = bool(re.search(r"(?<![\w.^~*<>=~-])\d+\.\d+\.\d+(?![\w.*])", text))

    # The comparator form is the only one carrying two operators; a constraint mixing a caret with a comparator is 'other', not the first found.
    if len(comps) >= 2 and not caret and not tilde:
        return "comparator_pair"
    if caret and not (tilde or comps):
        return "caret_range"
    if tilde and not (caret or comps):
        return "tilde_range"
    if wild and not (caret or tilde or comps):
        return "wildcard_patch"
    if exact and not (caret or tilde or comps or wild):
        return "exact_pin"
    return UNRESOLVED


fn_spec(
    "dependency_constraint_style",
    ["exact_pin", "caret_range", "tilde_range", "comparator_pair", "wildcard_patch"],
    _dependency_constraint,
)

# --- fmt-0113  test_name_style ---

_CLAUSE = re.compile(r"(?:^|[_\s])given[_\s].*[_\s]when[_\s]|(?:^|[_\s])when[_\s].*[_\s]then[_\s]", re.I)
_METHOD_VERBS = vocab("""
calculate compute apply round get set add remove create update delete parse
format validate resolve convert derive build render fetch load save
""")
_FUNCTION_WORDS = vocab("""
is are was were the a an does do has have and or for with to of on in at from
by not no it its that this than then out over under between into
""")


def _test_name_style(text: str) -> str:
    """Read from the first token, except the clause form, read from anywhere in the name.
    fmt-0113's exclusivity field is explicit that the clause form IS a clause wherever it sits."""
    name = None
    m = re.search(r"\b(?:def|fn|func|function)\s+(\w+)", text)
    if m:
        name = m.group(1)
    else:
        m = re.search(r"\b(?:it|test|describe|scenario)\s*\(\s*[\"'](.+?)[\"']", text)
        if m:
            name = m.group(1)
    if name is None:
        # A bare name on its own line. Prose is refused: without this gate any apology scores plain_sentence.
        for ln in _body_lines(text):
            ln = ln.strip().lstrip("-*").strip()
            if ln and not looks_like_sentence(ln) and len(ln.split()) <= 12:
                name = ln
                break
    if not name:
        return UNRESOLVED

    clause = bool(_CLAUSE.search(name))
    toks = _words(name)
    if not toks:
        return UNRESOLVED
    first = toks[0]

    if first in ("should", "shoulds"):
        return UNRESOLVED if clause else "should_phrase"
    if first in ("test", "tests"):
        return UNRESOLVED if clause else "test_prefixed"
    if clause:
        return "given_when_then"
    # The method exercised, as a closed list of operation verbs. Tested before plain_sentence, the label for everything descriptive.
    if first in _METHOD_VERBS:
        return "subject_first"
    if len(toks) >= 4 and any(t in _FUNCTION_WORDS for t in toks):
        return "plain_sentence"
    return UNRESOLVED


fn_spec(
    "test_name_style",
    ["should_phrase", "given_when_then", "test_prefixed", "plain_sentence", "subject_first"],
    _test_name_style,
)

# --- fmt-0116 migration_filename_style: the timestamp and date-plus-counter forms open with the SAME eight date digits, so both are tested before `sequential_integer` ---

spec(
    "migration_filename_style",
    ("utc_timestamp", rx(r"(?<!\d)\d{8}T?\d{6}[_-][a-z]")),
    ("date_plus_counter", rx(r"(?<!\d)\d{8}[-.]\d{1,3}[_-][a-z]")),
    ("release_version", rx(r"(?<![\w.])v\d+\.\d+(?:\.\d+)?[_-][a-z]", re.I)),
    ("content_hash_suffix", rx(r"[a-z]_[0-9a-f]{6,12}(?:\.\w+)?(?![\w])")),
    ("sequential_integer", rx(r"(?<![\d.])\d{1,6}[_-][a-z]")),
)

# --- fmt-0119 secret_reference_syntax: the store reference and file pointer both render as locators, so the scheme prefix is read before any slashes ---

spec(
    "secret_reference_syntax",
    ("uri_scheme_reference", rx(r"(?<![\w])[a-z][\w+.-]{1,20}://\S+")),
    # The deploy step's markers against the process's, split by which they are rather than by shape -- both are curly-brace placeholders otherwise.
    ("deploy_time_placeholder", rx(r"\{\{\s*[\w.]+\s*\}\}|<<\s*[\w.]+\s*>>|%[A-Z_][\w]*%|__[A-Z][\w]*__")),
    ("env_var_indirection", rx(r"\$\{?[A-Z][A-Z0-9_]{2,}\}?|\benv\s*:\s*[A-Z][A-Z0-9_]{2,}")),
    ("inline_encrypted_value", rx(r"\bENC\[|-----BEGIN [A-Z ]*-----|(?<![\w+/=])[A-Za-z0-9+/]{40,}={0,2}(?![\w])")),
    ("file_path_pointer", rx(r"(?<![\w:])/(?!/)[\w.-]+(?:/[\w.-]+)+")),
)

# --- fmt-0120  test_double_naming ---

_DOUBLE_HEADS = {"mock": "mock_prefix", "fake": "fake_prefix", "stub": "stub_prefix"}


def _test_double_naming(text: str) -> str:
    """Head word and tail word are read separately, and a name carrying both a
    leading word and the trailing one is 'other' -- fmt-0120's exclusivity
    field says so explicitly, so this cannot be an ordered rule list."""
    names = re.findall(r"(?<![\w])((?:[A-Z][a-z0-9]+){2,}|[a-z]+(?:_[a-z0-9]+)+)(?![\w])", text)
    labels = set()
    for n in names:
        w = _words(n)
        if len(w) < 2:
            continue
        head = None
        if w[0] == "in" and w[1] == "memory":
            head = "in_memory_prefix"
        elif w[0] in _DOUBLE_HEADS:
            head = _DOUBLE_HEADS[w[0]]
        tail = "double_suffix" if w[-1] == "double" else None
        if head and tail:
            return UNRESOLVED
        if head or tail:
            labels.add(head or tail)
    return _agree(labels)


fn_spec(
    "test_double_naming",
    ["mock_prefix", "fake_prefix", "stub_prefix", "double_suffix", "in_memory_prefix"],
    _test_double_naming,
)

# --- fmt-0121  ignore_pattern_style ---

_PATTERN_LINE = re.compile(r"[\w*!/][\w*.!/-]*")


def _ignore_pattern_style(text: str) -> str:
    """A leading slash and a trailing slash are independent decorations that one
    pattern can legally carry at once, so each label requires exactly one of
    them and a pattern carrying both is 'other'. That is fmt-0121's exclusivity
    argument, and it is why this is not an ordered rule list."""
    pats = []
    for ln in _body_lines(text):
        ln = ln.strip()
        if ln.startswith("#") or not _PATTERN_LINE.fullmatch(ln):
            continue
        pats.append(ln)
    if not pats:
        return UNRESOLVED
    if any(p.startswith("!") for p in pats):
        return "negated_allowlist"
    if any("**" in p for p in pats):
        return "globstar_path"
    labels = set()
    for p in pats:
        lead, trail = p.startswith("/"), p.endswith("/")
        if lead and trail:
            return UNRESOLVED
        labels.add("anchored_slash" if lead else "trailing_slash_dir" if trail else "bare_name")
    return _agree(labels)


fn_spec(
    "ignore_pattern_style",
    ["bare_name", "anchored_slash", "trailing_slash_dir", "globstar_path", "negated_allowlist"],
    _ignore_pattern_style,
)

# --- fmt-0122  changelog_entry_shape ---

_CATEGORIES = vocab("""
added changed deprecated removed fixed security fix feat feature chore docs
doc perf refactor build ci revert style test
""")


def _changelog_entry_shape(text: str) -> str:
    """Both leading forms occupy the same position, so the opening token is
    matched against the closed list of change kinds FIRST and read as a
    component name only when it fails that list -- fmt-0122's exclusivity
    argument. An entry carrying a leading token and a trailing one is 'other'."""
    line = next((ln.strip().lstrip("-*").strip() for ln in _body_lines(text) if ln.strip()), "")
    if not line:
        return UNRESOLVED
    lead = re.match(r"^([\w][\w.-]*)\s*[:—-]\s+\S", line)
    ticket = re.search(r"[(\[]?\b[A-Z]{2,10}-\d+\b[)\]]?[.\s]*$", line)
    handle = re.search(r"[(\[]?@[\w-]+[)\]]?[.\s]*$", line)
    if lead and (ticket or handle):
        return UNRESOLVED
    if lead:
        return "category_prefix" if lead.group(1).lower() in _CATEGORIES else "component_prefix"
    if handle:
        return "contributor_suffix"
    if ticket:
        return "ticket_suffix"
    # `plain_sentence` is the absence of every decoration, so it needs enough words to be an entry at all.
    return "plain_sentence" if len(re.findall(r"[A-Za-z][A-Za-z']+", line)) >= 6 else UNRESOLVED


fn_spec(
    "changelog_entry_shape",
    ["plain_sentence", "category_prefix", "component_prefix", "ticket_suffix", "contributor_suffix"],
    _changelog_entry_shape,
)

# --- fmt-0124  exit_code_scheme ---

_CODE = re.compile(r"(?:exit(?:s|ed)?(?:\s+with)?(?:\s+code)?|returns?|status|code)\D{0,4}(\d{1,3})\b", re.I)
_COUNTING = re.compile(r"\b(?:number|count) of (?:findings|failures|violations|issues|errors)\b"
                       r"|\bone per (?:finding|failure|violation)\b", re.I)


def _exit_code_scheme(text: str) -> str:
    """Read from the documented mapping, not from one observed exit.
    fmt-0124 is explicit: a run with exactly one finding exits 1 under both the binary and the
    counting scheme, so a single observed exit decides nothing."""
    codes = {int(c) for c in _CODE.findall(text)}
    if not codes:
        codes = {int(c) for c in re.findall(r"^\s*\|?\s*(\d{1,3})\s*[|:\t-]", text, re.M)}
    if not codes:
        return UNRESOLVED
    nonzero = {c for c in codes if c}
    if _COUNTING.search(text):
        return "failure_count"
    if nonzero and all(c >= 64 for c in nonzero):
        return "reserved_high_range"
    if len(nonzero) >= 3:
        return "per_category_codes"
    if nonzero == {1, 2}:
        return "findings_versus_errors"
    if nonzero == {1}:
        return "zero_one_binary"
    return UNRESOLVED


fn_spec(
    "exit_code_scheme",
    ["zero_one_binary", "findings_versus_errors", "per_category_codes",
     "failure_count", "reserved_high_range"],
    _exit_code_scheme,
)

# --- fmt-0125 assertion_style: chained and property forms both read left to right, separated by whether the first member is a call or a bare attribute; the matcher form passes its comparison as an argument and is tested first ---

spec(
    "assertion_style",
    ("matcher_argument", rx(r"\bassert[_]?[Tt]hat\s*\(\s*[^,()]+,\s*\w+\s*\(")),
    ("two_argument_helper", rx(r"\bassert[_]?[Ee]quals?\s*\(\s*[^,()]+,")),
    ("fluent_chain", rx(r"\bexpect\s*\(|\.to(?:\.|Be|Equal|Match)")),
    ("property_should", rx(r"\.should\b")),
    ("bare_assert_expression", rx(r"\bassert\s+[^,\n(]+(?:==|!=|<=|>=|<|>)")),
)

# --- fmt-0127  fixture_naming ---

_ARTICLES = vocab("a an the")
_VALIDITY = vocab("valid invalid good bad malformed broken ok legal illegal")


def _fixture_names(text: str) -> list[str]:
    names = re.findall(r"\bdef\s+([a-z][a-z0-9_]*)", text)
    names += re.findall(r'"([a-z][a-z0-9_]*)"\s*:', text)
    if not names:
        names = [ln.strip().lstrip("-*").strip()
                 for ln in _body_lines(text) if re.fullmatch(r"\s*[-*]?\s*[a-z][a-z0-9_]*\s*", ln)]
    return [n for n in names if n]


def _fixture_naming(text: str) -> str:
    """A validity word and an article both sit in front of the noun, so the
    leading token is matched against the closed article list FIRST and read as
    a validity word only when it is not an article -- fmt-0127's argument. A
    name carrying a leading decoration and a trailing number is 'other'."""
    names = _fixture_names(text)
    if not names:
        return UNRESOLVED
    labels = set()
    for n in names:
        segs = n.split("_")
        lead = ("article_prefixed" if segs[0] in _ARTICLES
                else "validity_prefixed" if segs[0] in _VALIDITY else None)
        numbered = bool(re.fullmatch(r"\d+", segs[-1]))
        if lead and numbered:
            return UNRESOLVED
        if lead:
            labels.add(lead)
        elif numbered:
            labels.add("numbered_variants")
        elif len(segs) >= 3 and ("for" in segs or segs[-1] in ("test", "tests", "case")):
            labels.add("purpose_suffixed")
        elif len(segs) == 1:
            labels.add("bare_noun")
        else:
            return UNRESOLVED
    return _agree(labels)


fn_spec(
    "fixture_naming",
    ["bare_noun", "validity_prefixed", "article_prefixed", "purpose_suffixed", "numbered_variants"],
    _fixture_naming,
)

# --- fmt-0128  commit_trailer_style ---

_TRAILER_COLON = re.compile(r"[A-Za-z][\w-]*\s*:\s*\S+")
_TRAILER_EQUALS = re.compile(r"[A-Za-z][\w-]*=\S+")
_TICKET = re.compile(r"\b[A-Z]{2,10}-\d+\b")


def _commit_trailer_style(text: str) -> str:
    """The two final-line forms differ by a single separator character in the
    same position and are compared literally, because a parser accepting both
    would collapse them onto one label. A message carrying a subject token and
    a final-line trailer is 'other'."""
    lines = _body_lines(text)
    if not lines:
        return UNRESOLVED
    subject, last = lines[0].strip(), lines[-1].strip()

    trailer = ("key_colon_trailer" if _TRAILER_COLON.fullmatch(last)
               else "key_equals_footer" if _TRAILER_EQUALS.fullmatch(last) else None)
    if trailer:
        if len(lines) > 1 and _TICKET.search(subject):
            return UNRESOLVED
        return trailer
    if re.search(r"\b(?:closes|fixes|resolves)\b[^.\n]*", last, re.I) and _TICKET.search(last) \
            and last.endswith("."):
        return "closing_body_sentence"
    if re.match(r"^\[[A-Z]{2,10}-\d+\]", subject):
        return "bracketed_subject_token"
    if _TICKET.search(subject):
        return "bare_subject_reference"
    return UNRESOLVED


fn_spec(
    "commit_trailer_style",
    ["key_colon_trailer", "bracketed_subject_token", "bare_subject_reference",
     "closing_body_sentence", "key_equals_footer"],
    _commit_trailer_style,
)

# --- fmt-0131  task_target_naming ---

_TASK_VERBS = vocab("""
build test lint format run start serve clean deploy publish check watch install
release compile bundle package migrate seed audit fix generate
""")


def _task_target_naming(text: str) -> str:
    """The two colon forms use identical punctuation and differ only in which
    side the verb sits on, so the label reads the ROLES of the two tokens
    rather than the character between them -- fmt-0131's exclusivity argument."""
    targets = []
    for ln in _body_lines(text):
        m = re.match(r"^\s*[-*]?\s*([a-z][a-z0-9]*(?:[:./][a-z0-9]+)*)\s*:?\s*$", ln)
        if m:
            targets.append(m.group(1))
    if not targets:
        targets = re.findall(r"(?<![\w:./])([a-z][a-z0-9]*[:./][a-z0-9]+)(?![\w:./])", text)
    if not targets:
        return UNRESOLVED
    labels = set()
    for t in targets:
        if ":" in t:
            a, _, b = t.partition(":")
            if a in _TASK_VERBS and b not in _TASK_VERBS:
                labels.add("verb_noun_colon")
            elif b in _TASK_VERBS and a not in _TASK_VERBS:
                labels.add("noun_verb_colon")
            else:
                return UNRESOLVED
        elif "." in t:
            labels.add("dotted_namespace")
        elif "/" in t:
            labels.add("slash_path")
        elif t in _TASK_VERBS:
            labels.add("bare_verb")
        else:
            return UNRESOLVED
    return _agree(labels)


fn_spec(
    "task_target_naming",
    ["bare_verb", "verb_noun_colon", "noun_verb_colon", "dotted_namespace", "slash_path"],
    _task_target_naming,
)

# --- fmt-0132  todo_marker_style ---

_MARKER = re.compile(r"^(?P<lead>\s*(?://|#|/\*|\*|--)?\s*)(?P<word>TODO|FIXME|HACK|XXX)\b(?P<rest>.*)$",
                     re.M | re.I)


def _todo_marker_style(text: str) -> str:
    """All five labels need the marker word; what differs is what follows it.
    The owner and ticket decorations differ in BRACKET CHARACTER rather than content -- a short
    ticket key reads as a name and a name reads as a key."""
    m = _MARKER.search(text)
    if not m:
        return UNRESOLVED
    rest = m.group("rest")
    head, sep, tail = rest.partition(":")
    if not sep:
        head, tail = rest, ""
    decorations = {
        "owner_in_parens": bool(re.search(r"\([^)\n]+\)", head)),
        "ticket_in_brackets": bool(re.search(r"\[[^\]\n]+\]", head)),
        "review_date_attached": bool(re.search(r"\d{4}-\d{2}-\d{2}|\bby\s+\d{4}\b", head, re.I)),
    }
    hits = [k for k, v in decorations.items() if v]
    if len(hits) > 1:
        return UNRESOLVED
    if hits:
        return hits[0]
    if tail.strip():
        return "bare_marker"
    # The marker sits alone on its line and the note is the next one -- a marker with nothing after it is not a deliberate two-line convention.
    after = text[m.end():]
    return "note_on_next_line" if any(ln.strip() for ln in after.splitlines()) else UNRESOLVED


fn_spec(
    "todo_marker_style",
    ["bare_marker", "owner_in_parens", "ticket_in_brackets",
     "review_date_attached", "note_on_next_line"],
    _todo_marker_style,
)

# --- fmt-0134  workspace_package_naming ---

_LAYER_WORDS = vocab("api ui core web cli data domain infra service lib app shared common worker admin")
_DIR_WORDS = vocab("packages apps libs services modules tools")


def _package_names(text: str) -> list[str]:
    names = re.findall(r'"(@?[\w][\w.@/-]{2,60})"', text)
    if not names:
        names = [ln.strip().lstrip("-*").strip()
                 for ln in _body_lines(text)
                 if re.fullmatch(r"\s*[-*]?\s*@?[\w][\w.@/-]{2,60}\s*", ln)]
    return [n for n in names if n]


def _workspace_package_naming(text: str) -> str:
    """The shared scope and the layer marker both open the name with a common
    token, so the label checks whether that token is CONSTANT across every
    package or VARIES with the package's tier -- fmt-0134's exclusivity
    argument. That is a property of the set, so it cannot be a rule list."""
    names = _package_names(text)
    if len(names) < 2:
        return UNRESOLVED
    if all(n.startswith("@") for n in names):
        return "scoped_prefix" if len({n.split("/")[0] for n in names}) == 1 else UNRESOLVED
    if all("." in n and "/" not in n for n in names):
        return "dotted_domain"
    if all("-" in n for n in names):
        heads = [n.split("-")[0] for n in names]
        if all(h in _DIR_WORDS for h in heads):
            return "dashed_path_echo"
        if all(h in _LAYER_WORDS for h in heads):
            # A layer that never varies is a shared scope, not a layer marker.
            return "layer_prefixed" if len(set(heads)) > 1 else "scoped_prefix"
        if len(set(heads)) == 1:
            return "scoped_prefix"
        # A name echoing its directory path AND carrying a leading token is 'other', per the scenario, as is any other mixture.
        return UNRESOLVED
    if all(re.fullmatch(r"[a-z][a-z0-9]*", n) for n in names):
        return "bare_short_name"
    return UNRESOLVED


fn_spec(
    "workspace_package_naming",
    ["scoped_prefix", "dotted_domain", "dashed_path_echo", "bare_short_name", "layer_prefixed"],
    _workspace_package_naming,
)

# --- fmt-0137  generated_file_marking ---

_BANNER = re.compile(r"(?:Code generated\b|@generated\b|DO NOT EDIT|AUTO-?GENERATED|Generated by\b)", re.I)
_GEN_TOKEN = r"(?:generated|autogen|gen|pb)"


def _generated_file_marking(text: str) -> str:
    """The label reads where the added token sits relative to the final dot.
    The infix marker and the extra extension both change the file NAME, so position is what
    separates them."""
    files = re.findall(r"[\w./-]*\w\.\w{1,8}(?:\.\w{1,8})?", text)
    found = set()
    if _BANNER.search(text):
        found.add("header_banner")
    if any(re.search(rf"(?:^|/){_GEN_TOKEN}/", f, re.I) for f in files):
        found.add("own_directory")
    # Suffix before infix: the added token as the FINAL segment is more specific, and `client.ts.gen` also contains `.gen`.
    if any(re.search(rf"\.\w{{1,8}}\.{_GEN_TOKEN}$", f, re.I) for f in files):
        found.add("extension_suffix")
    elif any(re.search(rf"[._-]{_GEN_TOKEN}[._-]", f, re.I) for f in files):
        found.add("filename_infix")
    if re.search(r"\bmanifest\b", text, re.I) or \
            re.search(rf"{_GEN_TOKEN}[-_]files?\.(?:txt|json|list)", text, re.I):
        found.add("sibling_manifest")
    return found.pop() if len(found) == 1 else UNRESOLVED


fn_spec(
    "generated_file_marking",
    ["header_banner", "filename_infix", "extension_suffix", "sibling_manifest", "own_directory"],
    _generated_file_marking,
)

# --- fmt-0138  ci_job_naming ---

_CI_TOOLS = vocab("""
eslint ruff pytest jest mypy black prettier gradle maven cargo npm tox flake8
golangci shellcheck hadolint trivy pylint vitest phpunit rubocop clippy bandit
""")
_CI_STAGES = vocab("build test lint deploy release verify package publish scan check analyse analyze")
_PLATFORMS = vocab("linux macos windows darwin ubuntu alpine amd64 arm64 x86 win32 android ios")


def _job_names(text: str) -> list[str]:
    names = re.findall(r"^\s{0,8}([a-z][\w-]{1,40})\s*:\s*$", text, re.M)
    if not names:
        names = [ln.strip().lstrip("-*").strip() for ln in _body_lines(text)
                 if re.fullmatch(r"\s*[-*]?\s*[a-z][\w-]{1,40}\s*", ln)]
    return names


def _ci_job_naming(text: str) -> str:
    """A tool name often reads as a verb too, so the token is matched against
    the tool list BEFORE the bare-verb label is considered -- fmt-0138's
    argument. A leading stage word plus a trailing platform word is 'other'."""
    names = _job_names(text)
    if not names:
        return UNRESOLVED
    labels = set()
    for n in names:
        w = _words(n)
        if not w:
            return UNRESOLVED
        if any(t in _CI_TOOLS for t in w):
            labels.add("tool_named")
            continue
        if any(re.fullmatch(r"\d+", t) for t in w):
            labels.add("ordinal_numbered")
            continue
        stage = len(w) >= 2 and w[0] in _CI_STAGES
        platform = len(w) >= 2 and w[-1] in _PLATFORMS
        if stage and platform:
            return UNRESOLVED
        if platform:
            labels.add("platform_suffixed")
        elif stage:
            labels.add("stage_prefixed")
        elif len(w) == 1 and w[0] in _CI_STAGES:
            labels.add("bare_verb")
        else:
            return UNRESOLVED
    return _agree(labels)


fn_spec(
    "ci_job_naming",
    ["bare_verb", "stage_prefixed", "platform_suffixed", "tool_named", "ordinal_numbered"],
    _ci_job_naming,
)

# --- fmt-0141  manifest_script_naming ---

_LIFECYCLE = vocab("pre post prepare prepublish preinstall postinstall")


def _manifest_script_naming(text: str) -> str:
    """A lifecycle prefix is itself joined with a dash, so a dashed name is
    checked against the closed lifecycle list BEFORE the plain dashed label is
    granted -- fmt-0141's argument. The colon and dash forms are then compared
    on the separator character alone."""
    names = re.findall(r'"([a-z][\w:.-]{1,40})"\s*:', text)
    if not names:
        names = _job_names(text)
    names = [n for n in names if n]
    if not names:
        return UNRESOLVED
    labels = set()
    for n in names:
        if ":" in n:
            labels.add("colon_scoped")
        elif "-" in n:
            labels.add("lifecycle_prefixed" if n.split("-")[0] in _LIFECYCLE else "dash_scoped")
        elif re.fullmatch(r"[a-z]+(?:[A-Z][a-z0-9]*)+", n):
            labels.add("camel_names")
        elif re.fullmatch(r"[a-z][a-z0-9]*", n):
            labels.add("bare_verbs")
        else:
            return UNRESOLVED
    return _agree(labels)


fn_spec(
    "manifest_script_naming",
    ["bare_verbs", "colon_scoped", "dash_scoped", "lifecycle_prefixed", "camel_names"],
    _manifest_script_naming,
)

# --- fmt-0144  build_stage_naming ---

_ROLE_WORDS = vocab("builder base runtime final deps dev prod test release build compile")
_STAGE_TOOLS = vocab("node golang maven gradle npm cargo poetry python rust java bun deno pnpm")


def _build_stage_naming(text: str) -> str:
    """The purpose name and the role prefix both describe what the stage does,
    so a token from the closed role list is looked for at the FRONT before the
    rest is read as a purpose -- fmt-0144's argument."""
    froms = re.findall(r"^\s*FROM\s+\S+(?:\s+AS\s+([\w.-]+))?", text, re.M | re.I)
    if not froms:
        return UNRESOLVED
    named = [f for f in froms if f]
    if not named:
        # `unnamed_positional` is an absence label, so it needs positive evidence of a real multi-stage build: two FROM lines, none named.
        return "unnamed_positional" if len(froms) >= 2 else UNRESOLVED
    labels = set()
    for n in named:
        w = _words(n)
        if not w:
            return UNRESOLVED
        # Tested on the raw name, not its split words: `stage1` splits into one token and would fall through to purpose.
        if re.fullmatch(r"(?:stage|step|s)?[-_]?\d{1,3}", n, re.I):
            labels.add("ordinal_numbers")
        elif any(t in _STAGE_TOOLS for t in w):
            labels.add("tool_named")
        elif w[0] in _ROLE_WORDS:
            labels.add("role_prefixed")
        else:
            labels.add("purpose_words")
    return _agree(labels)


fn_spec(
    "build_stage_naming",
    ["purpose_words", "ordinal_numbers", "tool_named", "role_prefixed", "unnamed_positional"],
    _build_stage_naming,
)

# --- fmt-0145  cache_key_composition ---

_LOCKFILE = re.compile(r"\b[\w.-]*lock(?:file)?\b|package-lock\.json|yarn\.lock|poetry\.lock|"
                       r"Cargo\.lock|Gemfile\.lock|pnpm-lock\.yaml|go\.sum", re.I)
_MANIFEST = re.compile(r"package\.json|pyproject\.toml|requirements\.txt|Cargo\.toml|go\.mod|"
                       r"build\.gradle|Gemfile\b|setup\.py|composer\.json", re.I)
_PLATFORM_TOKEN = re.compile(r"\b(?:linux|macos|windows|ubuntu|darwin|amd64|arm64|"
                             r"runner\.os|matrix\.os|RUNNER_OS)\b", re.I)


def _cache_key_composition(text: str) -> str:
    """Two of the five render as identical hexadecimal, so the label reads WHICH
    FILE was hashed and whether a platform token trails it -- never the digest.
    A key combining a branch name with a file hash is 'other'."""
    lock = bool(_LOCKFILE.search(text))
    manifest = bool(_MANIFEST.search(text))
    platform = bool(_PLATFORM_TOKEN.search(text))
    branch = bool(re.search(r"\b(?:branch|ref_name|head_ref|GIT_BRANCH|CI_COMMIT_BRANCH)\b", text, re.I))
    sha = bool(re.search(r"\b(?:commit[_ ]?sha|github\.sha|GIT_COMMIT|revision|\bsha\b)", text, re.I))
    fallback = bool(re.search(r"\b(?:restore-keys|restore_keys|fallback)\b", text, re.I))

    if branch and (lock or manifest):
        return UNRESOLVED
    if branch:
        return "branch_name_segment"
    if fallback:
        return "fixed_key_with_fallback"
    if manifest and platform and not lock:
        return "manifest_hash_plus_platform"
    if lock and not manifest:
        return "lockfile_hash"
    if sha:
        return "commit_sha_exact"
    return UNRESOLVED


fn_spec(
    "cache_key_composition",
    ["lockfile_hash", "manifest_hash_plus_platform", "branch_name_segment",
     "fixed_key_with_fallback", "commit_sha_exact"],
    _cache_key_composition,
)

# --- fmt-0146  deprecation_annotation_style ---

_COMMENT_LINE = re.compile(r"^\s*(?:\*|//|#|/\*|--|///)")


def _deprecation_annotation_style(text: str) -> str:
    """The attribute and the doc tag both sit immediately above the declaration,
    so the label reads whether the marker is language syntax the COMPILER sees
    or comment text it ignores -- fmt-0146's argument. A renamed symbol that
    also carries an attribute is 'other'."""
    attribute = doc_tag = dated = False
    for ln in text.splitlines():
        commented = bool(_COMMENT_LINE.match(ln))
        if re.search(r"@deprecated\b", ln, re.I) or re.search(r"\bDeprecated\b", ln):
            if commented:
                doc_tag = True
            elif re.match(r"^\s*(?:@\w+|#\[|\[[A-Z]|@available\s*\()", ln):
                attribute = True
        if commented and re.search(r"\b(?:remov\w+|delet\w+|drop\w+)\b", ln, re.I) \
                and re.search(r"\d{4}-\d{2}(?:-\d{2})?|\b(?:19|20)\d{2}\b", ln):
            dated = True

    renamed = bool(re.search(r"\b\w*(?:[Dd]eprecated|_deprecated|Legacy|_old)\b\s*[({=:]", text))
    runtime = bool(re.search(r"\b(?:warnings\.warn|console\.warn|DeprecationWarning|"
                             r"Log\.w|logger\.warn(?:ing)?)\s*\(", text))

    if renamed and attribute:
        return UNRESOLVED
    found = [k for k, v in (("language_attribute", attribute), ("doc_comment_tag", doc_tag),
                            ("name_suffix", renamed), ("runtime_warning_call", runtime),
                            ("dated_removal_comment", dated)) if v]
    return found[0] if len(found) == 1 else UNRESOLVED


fn_spec(
    "deprecation_annotation_style",
    ["language_attribute", "doc_comment_tag", "name_suffix",
     "runtime_warning_call", "dated_removal_comment"],
    _deprecation_annotation_style,
)

# --- fmt-0147  artifact_filename_shape ---

_ARCHIVE_EXT = re.compile(r"\.(?:tar\.(?:gz|bz2|xz|zst)|tgz|zip|whl|jar|deb|rpm|gz)$", re.I)


def _artifact_filename_shape(text: str) -> str:
    """Dot-separated version fields are COUNTED before anything is read.
    A longer version string contains a shorter one, so counting first keeps the labels apart."""
    cand = [t for t in re.findall(r"[\w][\w.-]*\.[A-Za-z0-9.]{1,12}", text) if _ARCHIVE_EXT.search(t)]
    if not cand:
        return UNRESOLVED
    stem = _ARCHIVE_EXT.sub("", cand[0])
    parts = stem.split("-")
    rest = parts[1:]
    if not rest:
        return "name_only"
    version = any(re.fullmatch(r"v?\d+(?:\.\d+)+", p) for p in rest)
    platform = any(p.lower() in _PLATFORMS for p in rest)
    build = any(re.fullmatch(r"b\d{2,6}|build\d{1,6}", p, re.I) for p in rest)
    date = any(re.fullmatch(r"(?:19|20)\d{6}", p) for p in rest)
    short_hash = any(re.fullmatch(r"[0-9a-f]{6,12}", p) and re.search(r"[a-f]", p) for p in rest)

    if version and platform:
        return "name_version_platform"
    if version and build:
        return "name_version_build"
    if date and not version:
        return "name_build_date"
    if short_hash and not version:
        return "name_short_hash"
    return UNRESOLVED


fn_spec(
    "artifact_filename_shape",
    ["name_version_platform", "name_short_hash", "name_version_build",
     "name_build_date", "name_only"],
    _artifact_filename_shape,
)

# --- fmt-0149  feature_flag_naming ---

# `checkout` is deliberately NOT a team word here -- this flag guards the checkout screen. A team word this list has never heard of returns UNRESOLVED.
_TEAM_WORDS = vocab("""
growth payments platform core mobile web infra billing search identity risk ops
commerce fulfilment fulfillment discovery retention activation
""")
_STAGE_SUFFIX = vocab("rollout beta ga canary experiment alpha pilot staged internal preview")


def _feature_flag_naming(text: str) -> str:
    """The removal date and the rollout stage are both TRAILING tokens on a
    behaviour name, so the label reads what KIND of token trails, not that one
    does -- fmt-0149's argument. A leading team token plus a trailing stage
    token is 'other'."""
    names = re.findall(r'"([a-z][\w.-]{4,60})"', text)
    if not names:
        names = [ln.strip().lstrip("-*").strip() for ln in _body_lines(text)
                 if re.fullmatch(r"\s*[-*]?\s*[a-z][\w.-]{4,60}\s*", ln)]
    if not names:
        return UNRESOLVED
    n = names[0]
    w = _words(n)
    if len(w) < 2:
        return UNRESOLVED
    team = w[0] in _TEAM_WORDS
    stage = w[-1] in _STAGE_SUFFIX
    if team and stage:
        return UNRESOLVED
    if re.search(r"(?:19|20)\d{2}[_-]?(?:0[1-9]|1[0-2])", n):
        return "removal_dated"
    if stage:
        return "stage_suffixed"
    if team:
        return "team_scoped"
    if re.search(r"(?<!\w)[a-z]{2,10}[_-]\d{2,6}(?!\d)", n) and not re.search(r"(?:19|20)\d{2}", n):
        return "ticket_keyed"
    return "behaviour_phrase" if len(w) >= 2 else UNRESOLVED


fn_spec(
    "feature_flag_naming",
    ["behaviour_phrase", "team_scoped", "ticket_keyed", "removal_dated", "stage_suffixed"],
    _feature_flag_naming,
)

# --- fmt-0150  review_remark_convention ---

_SEVERITY = vocab("nit blocker blocking praise question suggestion issue minor major critical optional note must")
_BLOCKING = vocab("blocker blocking must required")


def _remarks(text: str) -> list[str]:
    items = [re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", ln).strip()
            for ln in text.splitlines() if re.match(r"^\s*(?:[-*]|\d+[.)])\s+\S", ln)]
    if items:
        return items
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _review_remark_convention(text: str) -> str:
    """The nit word is itself one member of the severity vocabulary.
    So the label checks whether EVERY remark carries a word from that list before the severity
    form is assigned, and treats one used on only some remarks as the narrower label.
    fmt-0150's argument."""
    remarks = _remarks(text)
    if len(remarks) < 2:
        return UNRESOLVED
    if re.search(r"^\s*#{1,6}\s*Summary|^\s*Summary\s*:", text, re.M | re.I):
        return "optional_in_summary"

    prefixes = []
    for r in remarks:
        m = re.match(r"([A-Za-z]+)\s*[:!\-]", r)
        prefixes.append(m.group(1).lower() if m and m.group(1).lower() in _SEVERITY else None)
    marked = {p for p in prefixes if p}

    if marked & {"nit"} and marked & _BLOCKING:
        return UNRESOLVED
    if marked <= _BLOCKING and marked:
        return "blocking_marked_instead"
    if marked == {"nit"}:
        return "nit_prefix"
    if marked and all(p for p in prefixes):
        return "severity_word_prefix"
    if marked:
        return UNRESOLVED
    if sum(1 for r in remarks if r.rstrip().endswith("?")) >= max(2, len(remarks) // 2):
        return "question_phrasing"
    return UNRESOLVED


fn_spec(
    "review_remark_convention",
    ["nit_prefix", "severity_word_prefix", "question_phrasing",
     "blocking_marked_instead", "optional_in_summary"],
    _review_remark_convention,
)

# --- fmt-0151 patch_filename_shape: sequence and version prefixes both bring digit groups, so DOTS between them are tested first; ticket and description forms are told apart by the ticket key SHAPE, never by meaning ---


def _patch_filename_shape(text: str) -> str:
    m = re.search(r"([\w][\w.-]*)\.(?:patch|diff)\b", text)
    if not m:
        return UNRESOLVED
    stem = m.group(1)
    if re.search(r"\d+\.\d+", stem):
        return "package_version_prefixed"
    if re.match(r"^[A-Z]{2,10}-\d+", stem):
        return "ticket_keyed"
    if re.fullmatch(r"[0-9a-f]{6,12}", stem) and re.search(r"[a-f]", stem):
        return "upstream_hash_named"
    if re.match(r"^\d{1,3}[-_]", stem):
        return "numbered_prefix"
    if re.fullmatch(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)+", stem):
        return "description_slug"
    return UNRESOLVED


fn_spec(
    "patch_filename_shape",
    ["numbered_prefix", "package_version_prefixed", "ticket_keyed",
     "description_slug", "upstream_hash_named"],
    _patch_filename_shape,
)

# --- fmt-0152  cli_error_message_style ---

_REMEDY = re.compile(r"\b(?:try|run|use|set|check|see|pass|install|add)\b[^.\n]{4,}[.]?\s*$", re.I)


def _cli_message_label(line: str) -> str | None:
    """One message line. The two prefixed forms are tested first: otherwise a
    prefixed message would ALSO satisfy whichever casing label its first letter
    happened to fit, which is fmt-0152's exclusivity argument."""
    if re.match(r"^\[?[A-Z]{1,4}[-_]?\d{3,5}\]?\s*[:\]]?\s+\S", line):
        return "code_then_text"
    if re.match(r"^[a-z][\w.-]*\s*:\s+\S", line):
        return "tool_name_prefixed"
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()]
    if len(sentences) >= 2 and _REMEDY.search(sentences[-1]):
        return "remedy_sentence_appended"
    if re.match(r"^[a-z]", line) and "." not in line:
        return "lowercase_no_period"
    if re.match(r"^[A-Z]", line) and line.rstrip().endswith("."):
        return "sentence_case_period"
    return None


def _cli_error_message_style(text: str) -> str:
    """A house style is a property of the SET of messages, so two agreeing lines are required.
    That is also the relevance gate: read one line at a time, "I can't help with that." opens
    with a capital and closes with a full stop, and an apology was recorded as a deliberate
    convention. fmt-0152 asks for "the messages", plural."""
    lines = [re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", ln).strip() for ln in _body_lines(text)]
    lines = [ln for ln in lines if ln]
    if len(lines) < 2:
        return UNRESOLVED
    labels = {_cli_message_label(ln) for ln in lines}
    if None in labels or len(labels) != 1:
        return UNRESOLVED
    return labels.pop()


fn_spec(
    "cli_error_message_style",
    ["lowercase_no_period", "sentence_case_period", "tool_name_prefixed",
     "code_then_text", "remedy_sentence_appended"],
    _cli_error_message_style,
)

# --- fmt-0158  command_wrapping_style ---


def _command_wrapping_style(text: str) -> str:
    """The array and the variable both hold the flags in a name expanded at the
    call site, so the label reads whether the value is a LIST or a single
    STRING -- which is exactly what decides whether a flag containing a space
    survives. fmt-0158 names that as the distinction."""
    body = first_body(text)
    if re.search(r"^\s*\w+=\(", body, re.M):
        return "argument_array"
    if re.search(r"\\\s*$", body, re.M):
        return "backslash_continuations"
    if re.search(r"^\s*\w+=\"[^\"\n]*--\w", body, re.M) and re.search(r"\$\{?\w+\}?", body):
        return "flags_in_variable"
    if re.search(r"--(?:config|options?|args?|flags?)[= ]\S+|@\S+\.(?:txt|args|cfg|conf|ini|toml)",
                 body, re.I):
        return "flags_in_config_file"
    # `single_long_line` is the absence of every wrapping device, so it needs positive evidence of a long invocation on one line.
    for ln in body.splitlines():
        if len(ln.strip()) >= 80 and len(re.findall(r"(?<![\w-])--\w", ln)) >= 3:
            return "single_long_line"
    return UNRESOLVED


fn_spec(
    "command_wrapping_style",
    ["single_long_line", "backslash_continuations", "argument_array",
     "flags_in_config_file", "flags_in_variable"],
    _command_wrapping_style,
)

# --- fmt-0160  copyright_year_style ---

_CURRENT_YEAR = 2026
"""The reference tree's "now". fmt-0160 tells the two single-year forms apart
against the file creation date, "which the reference tree places several years
back" -- so a single year at or after the current one is the refreshed form and
an earlier one is the creation year. The constant is the scenario's own
reference point, not today's date, and it moves only if the reference moves."""


def _copyright_year_style(text: str) -> str:
    """The range and the open-ended form both open with the first year and a
    dash, so what FOLLOWS the dash is read: a digit run or a word. The comma
    form also carries two years and is separated from the range by the
    separator character alone."""
    if re.search(r"\b(?:19|20)\d{2}\s*[-–]\s*(?:present|now|current)\b", text, re.I):
        return "year_present_word"
    if re.search(r"\b(?:19|20)\d{2}\s*[-–]\s*(?:19|20)\d{2}\b", text):
        return "year_range"
    if re.search(r"\b(?:19|20)\d{2}\s*,\s*(?:19|20)\d{2}\b", text):
        return "comma_separated_years"
    years = [int(y) for y in re.findall(r"\b((?:19|20)\d{2})\b", text)]
    if len(set(years)) != 1:
        return UNRESOLVED
    return "current_year_only" if years[0] >= _CURRENT_YEAR else "first_year_only"


fn_spec(
    "copyright_year_style",
    ["first_year_only", "year_range", "year_present_word",
     "current_year_only", "comma_separated_years"],
    _copyright_year_style,
)
