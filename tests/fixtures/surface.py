"""Adversarial fixtures for the surface-form format keys (fmt-0001..0030).
Each entry is `(checker_key, expected_label, output_text)`. Two kinds: outputs that should
win a label, and near-misses drawn from each scenario's own `exclusivity` field, which is
where the traps are written down."""

from whowins.checkers.core import UNRESOLVED

FIXTURES: list[tuple[str, str, str]] = [
    # ---- fmt-0001 output_format -----------------------------------------
    ("output_format", "json_object", '{"id": 1, "status": "open"}'),
    ("output_format", "json_array", '[{"id": 1}, {"id": 2}]'),
    ("output_format", "yaml_mapping", "id: 1\nstatus: open\n"),
    ("output_format", "md_table", "| id | status |\n|----|--------|\n| 1  | open   |"),
    ("output_format", "csv_header", "id,status\n1,open"),
    # THE trap fmt-0001 names: valid JSON AND valid YAML, so order must make it json_object.
    ("output_format", "json_object", '{"id": 1}'),
    ("output_format", "json_object", '```json\n{"id": 1, "status": "open"}\n```'),

    # ---- fmt-0002 key_casing --------------------------------------------
    ("key_casing", "snake_case", '{"user_id": 1, "first_name": "a"}'),
    ("key_casing", "camel_case", '{"userId": 1, "firstName": "a"}'),
    ("key_casing", "pascal_case", '{"UserId": 1, "FirstName": "a"}'),
    ("key_casing", "kebab_case", '{"user-id": 1, "first-name": "a"}'),
    ("key_casing", "screaming_snake", '{"USER_ID": 1, "FIRST_NAME": "a"}'),
    # Mixed casing must NOT score as either -- the hedge fmt-0002's exclusivity field says returns 'other'.
    ("key_casing", "__unresolved__", '{"user_id": 1, "firstName": "a"}'),
    # One all-caps word has no case change: silent, not PascalCase, so the snake field decides.
    ("key_casing", UNRESOLVED, '{"ABC": 1, "DEF": 2}'),
    ("key_casing", "screaming_snake", '{"TIMEOUT": 30, "MAX_RETRIES": 3}'),
    ("key_casing", "pascal_case", '{"UserID": 1, "FirstName": "a"}'),

    # ---- fmt-0003 date_encoding -----------------------------------------
    ("date_encoding", "iso_8601", "Due 2026-03-14."),
    ("date_encoding", "us_slash", "Due 3/14/2026."),
    ("date_encoding", "eu_dot", "Due 14.03.2026."),
    ("date_encoding", "unix_epoch", "Due 1773446400."),
    ("date_encoding", "rfc_2822", "Due Sat, 14 Mar 2026 00:00:00 +0000."),
    # An RFC 2822 string contains no ISO date, but an ISO datetime contains digits an epoch pattern could grab, so ISO must win.
    ("date_encoding", "iso_8601", "2026-03-14T09:30:00"),

    # ---- fmt-0004 numeric_precision -------------------------------------
    ("numeric_precision", "integer", "Latency 42"),
    ("numeric_precision", "one_dp", "Latency 42.5"),
    ("numeric_precision", "three_dp", "Latency 42.500"),
    ("numeric_precision", "scientific", "Latency 4.25e1"),
    ("numeric_precision", "percent_sign", "Latency 42%"),

    # ---- fmt-0005 delimiter ---------------------------------------------
    ("delimiter", "comma", "id,status,owner"),
    ("delimiter", "tab", "id\tstatus\towner"),
    ("delimiter", "pipe", "id|status|owner"),
    ("delimiter", "semicolon", "id;status;owner"),
    ("delimiter", "double_space", "id  status  owner"),
    # The table is read past a heading, a lead-in, a fence, a sentence or a list above it; each read unresolved when only the first line was judged.
    ("delimiter", "pipe", "# Lookup table\n\nid|status|owner\n1|open|ann"),
    ("delimiter", "tab", "Here is the lookup table:\n```\nid\tstatus\towner\n1\topen\tann\n```"),
    ("delimiter", "semicolon", "The loader reads it as is.\n\n- Columns are fixed\n\nid;status;owner"),
    ("delimiter", "comma", "**Release notes**\n\n- atlas-core, 2026-03-14, passed"),
    # A comma inside brackets or quotes, in a sentence, or in a lead-in separates no columns; each read comma when only the first line was judged.
    ("delimiter", UNRESOLVED, '{"id": 1, "status": "open", "owner": "ann"}'),
    ("delimiter", UNRESOLVED, "Pick a format (e.g., CSV, TSV, pipes)"),
    ("delimiter", UNRESOLVED, "Keep ids, statuses, and owners."),
    ("delimiter", UNRESOLVED, "Sure, here it is:\n\nimport csv\nrows = load()"),
    # Code above any row ends the search, and the hybrid fmt-0005's exclusivity names fails both.
    ("delimiter", UNRESOLVED, "lookup = load()\nkeys, values = split(lookup)"),
    ("delimiter", UNRESOLVED, "id,status|owner"),

    # ---- fmt-0006 id_format ---------------------------------------------
    ("id_format", "uuid4", "id 6f9619ff-8b86-4d01-b42d-00cf4fc964ff"),
    ("id_format", "hex8", "id a3f5c9d1"),
    ("id_format", "prefixed_counter", "id INC-4127"),
    ("id_format", "bare_integer", "id 4127"),
    ("id_format", "word_slug", "id calm-blue-otter"),

    # ---- fmt-0007 heading_style -----------------------------------------
    ("heading_style", "h1", "# Incident summary\nbody"),
    ("heading_style", "h2", "## Incident summary\nbody"),
    ("heading_style", "h3", "### Incident summary\nbody"),
    ("heading_style", "bold_line", "**Incident summary**\nbody"),
    ("heading_style", "caps_line", "INCIDENT SUMMARY\nbody"),

    # ---- fmt-0008 currency_format ---------------------------------------
    ("currency_format", "symbol_prefix", "Total $1,250.00"),
    ("currency_format", "code_suffix", "Total 1,250.00 USD"),
    ("currency_format", "integer_cents", "Total 125000"),
    ("currency_format", "bare_decimal", "Total 1250.00"),
    ("currency_format", "accounting_parens", "Total (1,250.00)"),

    # ---- fmt-0009 list_marker -------------------------------------------
    ("list_marker", "hyphen", "- one\n- two"),
    ("list_marker", "asterisk", "* one\n* two"),
    ("list_marker", "arabic", "1. one\n2. two"),
    ("list_marker", "roman", "i. one\nii. two"),
    ("list_marker", "prose", "First check the log, then restart, finally verify."),

    # ---- fmt-0010 timezone_encoding -------------------------------------
    ("timezone_encoding", "utc_z", "2026-03-14T09:30:00Z"),
    ("timezone_encoding", "numeric_offset", "2026-03-14 09:30:00 +05:30"),
    ("timezone_encoding", "named_zone", "2026-03-14 09:30 Europe/Berlin"),
    ("timezone_encoding", "epoch_seconds", "1773480600"),
    ("timezone_encoding", "date_only", "2026-03-14"),
    # A zone named with no time stamps nothing; the bare word once won over the epoch stamp beside it.
    ("timezone_encoding", "epoch_seconds", "1773480600 job started (all stamps UTC)"),
    ("timezone_encoding", UNRESOLVED, "Stamp each line with a numeric UTC offset."),

    # ---- fmt-0011 boolean_encoding --------------------------------------
    ("boolean_encoding", "true_false", "active: true"),
    ("boolean_encoding", "yes_no", "active: yes"),
    ("boolean_encoding", "one_zero", "active: 1"),
    ("boolean_encoding", "y_n", "active: Y"),
    ("boolean_encoding", "on_off", "active: on"),
    # Read from the values, and the whole dump agrees on one pair (fmt-0011).
    ("boolean_encoding", "__unresolved__", "Reviewers requested more detail on the migration."),
    ("boolean_encoding", "__unresolved__", "dark_mode: true\nbeta_banner: on"),
    ("boolean_encoding", "on_off",
     "| flag | value |\n|---|---|\n| dark_mode | on |\n| beta_banner | off |"),
    ("boolean_encoding", "true_false", '{"dark_mode": true, "beta_banner": false}'),
    ("boolean_encoding", "__unresolved__", "dark_mode: enabled\nbeta_banner: on"),

    # ---- fmt-0012 missing_value -----------------------------------------
    ("missing_value", "na_literal", "owner,N/A,open"),
    ("missing_value", "null_word", "owner: null"),
    ("missing_value", "unknown_word", "owner: unknown"),
    ("missing_value", "hyphen_dash", "owner,-,open"),
    ("missing_value", "empty_cell", "owner,,open"),

    # ---- fmt-0013 quote_style -------------------------------------------
    ("quote_style", "double_quote", 'name "alpha"'),
    ("quote_style", "single_quote", "name 'alpha'"),
    ("quote_style", "backtick", "name `alpha`"),
    ("quote_style", "curly_quote", "name \u201calpha\u201d"),
    # `unquoted` needs a real value to be unquoted rather than an absence of quote marks, so the fixture carries a name-value pair.
    ("quote_style", "unquoted", "name: alpha"),

    # ---- fmt-0014 byte_unit ---------------------------------------------
    ("byte_unit", "raw_bytes", "size 1048576 B"),
    ("byte_unit", "kb_decimal", "size 1049 kB"),
    ("byte_unit", "kib_binary", "size 1024 KiB"),
    ("byte_unit", "mb_decimal", "size 1.05 MB"),
    ("byte_unit", "mib_binary", "size 1 MiB"),

    # ---- fmt-0016 phone_format ------------------------------------------
    ("phone_format", "e164", "call +14155550123"),
    ("phone_format", "national_parens", "call (415) 555-0123"),
    ("phone_format", "dotted", "call 415.555.0123"),
    ("phone_format", "spaced_groups", "call 415 555 0123"),
    ("phone_format", "digits_only", "call 4155550123"),

    # ---- fmt-0017 rate_expression ---------------------------------------
    ("rate_expression", "decimal_fraction", "rate 0.045"),
    ("rate_expression", "percent_symbol", "rate 4.5%"),
    ("rate_expression", "basis_points", "rate 450 bps"),
    ("rate_expression", "per_mille", "rate 45\u2030"),
    ("rate_expression", "spelled_words", "rate 4.5 per cent"),

    # ---- fmt-0018 indent_unit -------------------------------------------
    ("indent_unit", "two_space", "root:\n  child: 1"),
    ("indent_unit", "four_space", "root:\n    child: 1"),
    ("indent_unit", "eight_space", "root:\n        child: 1"),
    ("indent_unit", "tab_char", "root:\n\tchild: 1"),
    ("indent_unit", "no_indent", "root:\nchild: 1"),

    # ---- fmt-0019 truncation_marker -------------------------------------
    ("truncation_marker", "unicode_ellipsis", "first line\u2026"),
    ("truncation_marker", "three_periods", "first line..."),
    ("truncation_marker", "bracketed_ellipsis", "first line [...]"),
    ("truncation_marker", "snip_tag", "first line [snip]"),
    ("truncation_marker", "plus_more", "first line +12 more"),
    ("truncation_marker", "snip_tag", "at A\n<snip>\nat B"),
    ("truncation_marker", "snip_tag", "at A\n--- snip ---\nat B"),
    # The word is not the tag: "cut" is in every option's wording, and in prose beside a real marker.
    ("truncation_marker", UNRESOLVED, "Mark the cut with three plain full stops."),
    ("truncation_marker", "three_periods", "I cut the framework frames:\nat A\n...\nat B"),

    # ---- fmt-0020 version_string ----------------------------------------
    ("version_string", "bare_semver", "release 2.4.1"),
    ("version_string", "v_prefixed", "release v2.4.1"),
    ("version_string", "calendar_version", "release 2026.3"),
    ("version_string", "major_minor", "release 2.4"),
    ("version_string", "build_metadata", "release 2.4.1+build.77"),

    # ---- fmt-0021 colour_encoding ---------------------------------------
    ("colour_encoding", "hex6", "brand #1a2b3c"),
    ("colour_encoding", "hex3", "brand #1a2"),
    ("colour_encoding", "rgb_functional", "brand rgb(26, 43, 60)"),
    ("colour_encoding", "hsl_functional", "brand hsl(210, 40%, 17%)"),
    ("colour_encoding", "css_named", "brand navy"),

    # ---- fmt-0022 duration_format ---------------------------------------
    ("duration_format", "iso_duration", "elapsed PT1H30M"),
    ("duration_format", "colon_clock", "elapsed 1:30:00"),
    ("duration_format", "unit_suffix", "elapsed 90 min"),
    ("duration_format", "decimal_hours", "elapsed 1.5 hours"),
    ("duration_format", "total_seconds", "elapsed 5400 seconds"),

    # ---- fmt-0024 log_level_style ---------------------------------------
    ("log_level_style", "uppercase_word", "[WARNING] disk low"),
    ("log_level_style", "lowercase_word", "[warning] disk low"),
    ("log_level_style", "title_case_word", "[Warning] disk low"),
    ("log_level_style", "initial_letter", "[W] disk low"),
    ("log_level_style", "syslog_number", "[4] disk low"),

    # ---- fmt-0026 escape_style ------------------------------------------
    ("escape_style", "backslash", 'line \\n break'),
    ("escape_style", "html_entity", "five &amp; six"),
    ("escape_style", "percent_encoded", "path a%2Fb"),
    ("escape_style", "unicode_escape", "char \\u00e9"),
    ("escape_style", "doubled_char", "it''s here"),

    # ---- fmt-0027 record_separator --------------------------------------
    ("record_separator", "hyphen_rule", "a\n---\nb"),
    ("record_separator", "equals_rule", "a\n===\nb"),
    ("record_separator", "asterisk_rule", "a\n***\nb"),
    ("record_separator", "tilde_rule", "a\n~~~~\nb"),
    ("record_separator", "blank_line", "a\n\nb"),

    # ---- fmt-0029 email_display -----------------------------------------
    ("email_display", "bare_address", "contact ada@example.org"),
    ("email_display", "name_angle", "contact Ada Lovelace <ada@example.org>"),
    ("email_display", "mailto_link", "contact mailto:ada@example.org"),
    ("email_display", "at_obfuscated", "contact ada [at] example [dot] org"),
    ("email_display", "display_name_only", "Ada Lovelace"),

    # ---- fmt-0030 path_style --------------------------------------------
    ("path_style", "absolute_posix", "open /var/log/app.log"),
    ("path_style", "relative_path", "open logs/app.log"),
    ("path_style", "home_tilde", "open ~/logs/app.log"),
    ("path_style", "windows_backslash", "open C:\\logs\\app.log"),
    ("path_style", "file_uri", "open file:///var/log/app.log"),
]

# Boundary regressions: a `\b` after a digit silently fails before a letter. These fail against the `\b` form and pass against the lookahead.
FIXTURES += [
    ("date_encoding", "iso_8601", "2026-03-14T09:30:00Z"),
    ("date_encoding", "us_slash", "due 3/14/2026th"),
    ("phone_format", "e164", "call +14155550123x22"),
]

# An ABSENCE label must never win on an empty or trivial response, or a total model failure scores as a deliberate choice.
FIXTURES += [
    ("indent_unit", "__unresolved__", ""),
    ("indent_unit", "__unresolved__", "single line"),
]

# Prose with several commas is NOT a comma-delimited row. This is the case discriminating the two implementations -- a shorter apology proves nothing.
FIXTURES += [
    ("delimiter", "__unresolved__",
     "In summary, the value, which we discussed at length, is fine."),
    ("delimiter", "__unresolved__", "Sorry, I don't have enough information."),
    ("delimiter", "comma", "region,owner,tier"),
]

# --- Surface-form keys from the later ranges, exercising classifiers whose rule order had never been checked against a concrete string ---
FIXTURES += [
    ("name_order", "given_first", "Ada Lovelace"),
    ("name_order", "family_comma", "Lovelace, Ada"),
    ("name_order", "family_caps", "LOVELACE Ada"),
    ("name_order", "initial_family", "A. Lovelace"),
    ("name_order", "family_only", "Lovelace"),
    # One attendee per line: `\s` inside a name joined the lines, so a list of family names read as given-first.
    ("name_order", "family_only", "Lovelace\nHopper\nTuring"),
    ("name_order", "given_first", "Ada Lovelace\nGrace Hopper"),
    # The hybrid fmt-0015 names: capitals AND a comma claims neither form.
    ("name_order", "__unresolved__", "OKAFOR, Jana"),

    ("coordinate_format", "signed_decimal", "at 51.5074, -0.1278"),
    ("coordinate_format", "hemisphere_decimal", "at 51.5074 N"),
    ("coordinate_format", "dms", "at 51\u00b030'26\"N"),
    ("coordinate_format", "ddm", "at 51\u00b030.44'N"),
    ("coordinate_format", "geohash", "at gcpvj0duq"),
    # A word from the geohash alphabet is not a geohash. Both of these used to be one.
    ("coordinate_format", "signed_decimal", "Cabinet A: 51.5074, -0.1278, installed as requested."),
    ("coordinate_format", "__unresolved__", "The request was deferred."),
    ("coordinate_format", "geohash", "gcpvjbdu"),

    ("checksum_format", "hex_lower", "sum " + "a3f5" * 8),
    ("checksum_format", "hex_upper", "sum " + "A3F5" * 8),
    ("checksum_format", "algo_prefixed", "sum sha256:abcdef0123456789"),
    ("checksum_format", "spaced_groups", "sum a3f5 c9d1 4e2b 7a80 1122"),
    ("checksum_format", "base64", "sum n4bQgYhMfWWaL+qgxVrQFaO/TxsrC4Is0V1sFbDwCgg="),

    ("citation_style", "bracket_number", "As shown [12]."),
    ("citation_style", "author_year", "As shown (Lovelace, 1843)."),
    ("citation_style", "superscript", "As shown\u00b9."),
    ("citation_style", "dagger_symbol", "As shown\u2020."),
    ("citation_style", "prose_attribution", "According to the working group, this holds."),
]
