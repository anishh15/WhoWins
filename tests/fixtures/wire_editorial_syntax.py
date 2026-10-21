"""Fixtures for the wire, editorial and syntax format classifiers.
Weighted toward the NESTING traps, because that is where this group breaks: one label's
literal form sits inside another's."""

FIXTURES: list[tuple[str, str, str]] = [
    # ---- wire ------------------------------------------------------------
    ("delete_repeat_status", "status_204", "HTTP/1.1 204 No Content"),
    ("delete_repeat_status", "status_404", "HTTP/1.1 404 Not Found"),
    ("delete_repeat_status", "status_410", "HTTP/1.1 410 Gone"),
    ("delete_repeat_status", "status_202", "HTTP/1.1 202 Accepted"),
    ("delete_repeat_status", "status_200_body", "HTTP/1.1 200 OK\n\n{\"deleted\": true}"),
    ("move_redirect_status", "status_301", "HTTP/1.1 301 Moved Permanently"),
    ("move_redirect_status", "status_308", "HTTP/1.1 308 Permanent Redirect"),
    ("move_redirect_status", "status_307", "HTTP/1.1 307 Temporary Redirect"),
    # The status LINE decides, never a number elsewhere. The first classifier searched the whole text and tested 200 first, so any 200 anywhere won status_200_body.
    ("delete_repeat_status", "status_204", "HTTP/1.1 204 No Content\nX-Deleted-Order: 200"),
    ("delete_repeat_status", "status_404",
     "HTTP/1.1 404 Not Found\nContent-Type: application/json\n\n{\"error\": \"order 200 not found\"}"),
    ("delete_repeat_status", "status_410",
     "DELETE /orders/200 HTTP/1.1\nHost: api.internal\n\nHTTP/1.1 410 Gone"),
    ("delete_repeat_status", "__unresolved__",
     "It used to answer 200 OK; from now on it should answer 410 Gone."),
    ("delete_repeat_status", "__unresolved__",
     "HTTP/1.1 204 No Content\n\nor, if you prefer:\n\nHTTP/1.1 404 Not Found"),
    ("move_redirect_status", "status_301",
     "HTTP/1.1 301 Moved Permanently\nLocation: /reports/302-archive"),
    ("move_redirect_status", "status_308", "Status: 308 Permanent Redirect\nLocation: /reports/new"),

    ("header_name_casing", "lower_hyphen", "content-type: application/json\nx-request-id: 1"),
    ("header_name_casing", "title_hyphen", "Content-Type: application/json\nX-Request-Id: 1"),
    ("header_name_casing", "upper_hyphen", "CONTENT-TYPE: application/json\nX-REQUEST-ID: 1"),
    ("header_name_casing", "upper_underscore", "CONTENT_TYPE: application/json\nX_REQUEST_ID: 1"),
    ("header_name_casing", "camel_no_separator", "contentType: application/json\nxRequestId: 1"),

    # indexed_bracket must beat bracket_repeat: `tag[0]=` contains `tag[`.
    ("query_array_encoding", "indexed_bracket", "/search?tag[0]=red&tag[1]=blue"),
    ("query_array_encoding", "bracket_repeat", "/search?tag[]=red&tag[]=blue"),
    ("query_array_encoding", "comma_joined", "/search?tag=red,blue"),
    ("query_array_encoding", "pipe_joined", "/search?tag=red|blue"),
    ("query_array_encoding", "repeated_key", "/search?tag=red&tag=blue"),

    ("api_version_placement", "path_prefix", "GET https://api.example.test/v2/accounts"),
    ("api_version_placement", "query_parameter", "GET /accounts?version=2"),
    ("api_version_placement", "request_header", "GET /accounts\nAPI-Version: 2"),
    ("api_version_placement", "media_type_parameter",
     "Accept: application/vnd.acme+json; version=2"),
    ("api_version_placement", "host_prefix", "GET https://v2.api.example.test/accounts"),

    ("credential_transport", "bearer_scheme", "Authorization: Bearer abc.def"),
    ("credential_transport", "token_scheme", "Authorization: Token abc123"),
    ("credential_transport", "basic_scheme", "Authorization: Basic dXNlcjpwdw=="),
    ("credential_transport", "api_key_header", "X-API-Key: abc123"),
    ("credential_transport", "session_cookie", "Cookie: sid=abc123"),

    ("charset_parameter", "omitted", "Content-Type: text/csv"),
    ("charset_parameter", "lower_no_space", "Content-Type: text/csv;charset=utf-8"),
    ("charset_parameter", "upper_no_space", "Content-Type: text/csv;charset=UTF-8"),
    ("charset_parameter", "quoted_value", 'Content-Type: text/csv;charset="utf-8"'),

    ("timestamp_precision", "whole_seconds", "at 09:30:15"),
    ("timestamp_precision", "milliseconds", "at 09:30:15.250"),
    ("timestamp_precision", "microseconds", "at 09:30:15.250000"),
    ("timestamp_precision", "nanoseconds", "at 09:30:15.250000000"),
    ("timestamp_precision", "whole_minutes", "at 09:30"),

    ("health_status_vocabulary", "ok_lower", '{"status": "ok"}'),
    ("health_status_vocabulary", "healthy_word", '{"status": "healthy"}'),
    ("health_status_vocabulary", "up_upper", '{"status": "UP"}'),
    ("health_status_vocabulary", "pass_word", '{"status": "pass"}'),
    ("health_status_vocabulary", "green_word", '{"status": "green"}'),

    ("stream_framing", "sse_blocks", "event: tick\ndata: {\"n\":1}\n\n"),
    ("stream_framing", "newline_delimited", '{"n":1}\n{"n":2}\n'),
    ("stream_framing", "json_array_chunks", '[\n  {"n":1},\n  {"n":2}\n]'),

    ("time_window_parameters", "from_to", "/metrics?from=2026-01-01&to=2026-01-31"),
    ("time_window_parameters", "since_until", "/metrics?since=2026-01-01&until=2026-01-31"),
    ("time_window_parameters", "interval_string", "/metrics?range=2026-01-01/2026-01-31"),

    # --- editorial: the abbreviation-nesting trap, M / Mo / Mon / Monday ---
    ("weekday_encoding", "full_name", "Runs on Monday and Thursday."),
    ("weekday_encoding", "three_letter", "Runs on Mon and Thu."),
    ("weekday_encoding", "two_letter", "Runs on Mo and Th."),
    ("weekday_encoding", "single_letter", "Runs on M and T."),
    ("weekday_encoding", "iso_number", "Runs on 1 and 4."),

    ("month_in_prose", "full_name", "Filed in March 2026."),
    ("month_in_prose", "three_letter", "Filed in Mar 2026."),
    ("month_in_prose", "three_letter_period", "Filed in Mar. 2026."),
    ("month_in_prose", "three_letter_caps", "Filed in MAR 2026."),

    ("heading_capitalisation", "sentence_case", "# Incident response overview"),
    ("heading_capitalisation", "headline_title_case", "# Incident Response for the Team"),
    ("heading_capitalisation", "start_case", "# Incident Response For The Team"),
    # Every word capitalised and no article or preposition: both rules hold, so fmt-0162 says 'other'. This fixture used to expect start_case, written from the classifier rather than the scenario.
    ("heading_capitalisation", "__unresolved__", "# Incident Response Overview"),
    # The headings are read, not a lead-in above them, and they must agree.
    ("heading_capitalisation", "sentence_case",
     "Here is the output:\n\n# Getting started with the tools\n## Your first week"),
    ("heading_capitalisation", "__unresolved__",
     "# Getting started with the tools\n# Your First Week At The Company"),
    ("heading_capitalisation", "all_lowercase", "# incident response overview"),
    ("heading_capitalisation", "all_capitals", "# INCIDENT RESPONSE OVERVIEW"),

    ("spelling_variant_policy", "our_ise", "The colour was standardised."),
    ("spelling_variant_policy", "or_ize", "The color was standardized."),
    ("spelling_variant_policy", "our_ize", "The colour was standardized."),
    ("spelling_variant_policy", "or_ise", "The color was standardised."),
    # Crediting deliberate avoidance needs enough prose for the choice to have arisen; a one-line refusal avoids the variants too.
    ("spelling_variant_policy", "variants_avoided",
     "The team set the shade on the summary panel and left the rest of the "
     "page as it was, so the header, the footer and the side rail all keep "
     "the tones they had before the release went out to the wider group."),

    ("percent_in_prose", "symbol_tight", "Up 12% this quarter."),
    ("percent_in_prose", "symbol_spaced", "Up 12 % this quarter."),
    ("percent_in_prose", "one_word_percent", "Up 12 percent this quarter."),
    ("percent_in_prose", "two_words_per_cent", "Up 12 per cent this quarter."),
    ("percent_in_prose", "number_and_word_spelled", "Up twelve per cent this quarter."),

    ("temperature_scale", "celsius_symbol", "Holds at 21 °C."),
    ("temperature_scale", "fahrenheit_symbol", "Holds at 70 °F."),
    ("temperature_scale", "kelvin_no_symbol", "Holds at 294 K."),
    ("temperature_scale", "celsius_then_fahrenheit", "Holds at 21 °C (70 °F)."),

    ("section_numbering", "top_level_only", "1. Scope\n2. Terms"),
    ("section_numbering", "multilevel_decimal", "1.1 Scope\n1.2 Terms"),
    ("section_numbering", "multilevel_decimal_trailing_period", "1.1. Scope\n1.2. Terms"),
    ("section_numbering", "roman_then_arabic", "I. Scope\nII. Terms"),

    # --- syntax: `${VAR}` contains `$VAR`, so double must win ---
    ("placeholder_delimiter", "double_brace", "Deploy to {{ region }} now."),
    ("placeholder_delimiter", "dollar_brace", "Deploy to ${REGION} now."),
    ("placeholder_delimiter", "percent_wrapped", "Deploy to %REGION% now."),
    ("placeholder_delimiter", "angle_bracket", "Deploy to <region> now."),
    ("placeholder_delimiter", "dollar_bare", "Deploy to $REGION now."),

    # `{{host}}` contains `{host}`; double must win.
    ("server_variable_placeholder_syntax", "double_curly", "https://{{host}}/v1"),
    ("server_variable_placeholder_syntax", "single_curly", "https://{host}/v1"),
    ("server_variable_placeholder_syntax", "dollar_curly", "https://${host}/v1"),
    ("server_variable_placeholder_syntax", "angle_brackets", "https://<host>/v1"),
    ("server_variable_placeholder_syntax", "colon_prefix", "https://example.test/:host/v1"),

    # `urn:uuid:...` contains a bare lower-hyphenated UUID; urn must win.
    ("uuid_rendering", "urn_prefixed", "id urn:uuid:6f9619ff-8b86-4d01-b42d-00cf4fc964ff"),
    ("uuid_rendering", "lower_hyphenated", "id 6f9619ff-8b86-4d01-b42d-00cf4fc964ff"),
    ("uuid_rendering", "upper_hyphenated", "id 6F9619FF-8B86-4D01-B42D-00CF4FC964FF"),
    ("uuid_rendering", "hyphenless", "id 6f9619ff8b864d01b42d00cf4fc964ff"),

    ("thousands_separator", "comma", "Total 1,250,000"),
    ("thousands_separator", "period", "Total 1.250.000"),
    ("thousands_separator", "space", "Total 1 250 000"),
    ("thousands_separator", "apostrophe", "Total 1'250'000"),
    ("thousands_separator", "none", "Total 1250000"),

    ("emphasis_marker", "double_asterisk", "This is **critical** now."),
    ("emphasis_marker", "double_underscore", "This is __critical__ now."),
    ("emphasis_marker", "single_asterisk", "This is *critical* now."),
    ("emphasis_marker", "backticks", "This is `critical` now."),
    ("emphasis_marker", "uppercase", "This is CRITICAL now."),

    ("code_block_style", "backtick_with_language", "```python\nx = 1\n```"),
    ("code_block_style", "backtick_no_language", "```\nx = 1\n```"),
    ("code_block_style", "tilde_fence", "~~~\nx = 1\n~~~"),
    ("code_block_style", "html_pre", "<pre>x = 1</pre>"),
    ("code_block_style", "four_space_indent", "    x = 1"),

    ("link_style", "inline_link", "See [the guide](https://example.test/g)."),
    ("link_style", "reference_style", "See [the guide][guide]."),
    ("link_style", "angle_autolink", "See <https://example.test/g>."),
    ("link_style", "bare_autolink", "See https://example.test/g ."),
    ("link_style", "footnote_style", "See the guide[^1]."),

    ("range_notation", "en_dash", "Range 10–20"),
    ("range_notation", "hyphen", "Range 10-20"),
    ("range_notation", "to_word", "Range 10 to 20"),
    ("range_notation", "interval_brackets", "Range [10, 20]"),
    ("range_notation", "plus_minus", "Range 15 ± 5"),

    ("negative_sign", "leading_hyphen", "Balance -250.00"),
    ("negative_sign", "unicode_minus", "Balance −250.00"),
    ("negative_sign", "trailing_minus", "Balance 250.00-"),
    ("negative_sign", "parenthesised", "Balance (250.00)"),
    ("negative_sign", "cr_marker", "Balance 250.00 CR"),

    ("isbn_hyphenation_formatting", "thirteen_hyphenated", "ISBN 978-0-306-40615-7"),
    ("isbn_hyphenation_formatting", "thirteen_unhyphenated", "ISBN 9780306406157"),
    ("isbn_hyphenation_formatting", "ten_hyphenated", "ISBN 0-306-40615-2"),
    ("isbn_hyphenation_formatting", "urn_isbn_uri", "ISBN urn:isbn:9780306406157"),

    ("display_aspect_ratio_notation", "integer_colon_ratio", "Aspect 16:9"),
    ("display_aspect_ratio_notation", "decimal_to_one", "Aspect 1.78:1"),
    ("display_aspect_ratio_notation", "pixel_dimensions", "Aspect 1920x1080"),
    ("display_aspect_ratio_notation", "marketing_named_preset", "Aspect widescreen"),

    ("env_file_quote_convention", "unquoted_plain", "TOKEN=abc123"),
    ("env_file_quote_convention", "double_quoted", 'TOKEN="abc123"'),
    ("env_file_quote_convention", "single_quoted", "TOKEN='abc123'"),
    ("env_file_quote_convention", "export_prefix", "export TOKEN=abc123"),
    ("env_file_quote_convention", "escaped_newlines", 'KEY="line1\\nline2"'),

    ("env_var_nesting", "single_underscore", "DB_HOST=localhost"),
    ("env_var_nesting", "double_underscore", "DB__HOST=localhost"),
    ("env_var_nesting", "dotted_lower", "db.host=localhost"),
    ("env_var_nesting", "camel_joined", "dbHost=localhost"),
    ("env_var_nesting", "json_blob_var", "DB={\"host\": \"localhost\"}"),

    ("cli_option_spelling", "double_dash_kebab", "run --dry-run --max-retries 3"),
    ("cli_option_spelling", "double_dash_snake", "run --dry_run --max_retries 3"),
    ("cli_option_spelling", "double_dash_camel", "run --dryRun --maxRetries 3"),
    ("cli_option_spelling", "double_dash_joined", "run --dryrun --maxretries 3"),
    ("cli_option_spelling", "single_dash_word", "run -dryrun -maxretries 3"),

    ("graphql_enum_naming_case", "screaming_snake", "enum S {\n  IN_PROGRESS\n  ON_HOLD\n}"),
    ("graphql_enum_naming_case", "lowercase_snake", "enum S {\n  in_progress\n  on_hold\n}"),
    ("graphql_enum_naming_case", "upper_camel", "enum S {\n  InProgress\n  OnHold\n}"),
    ("graphql_enum_naming_case", "lower_camel", "enum S {\n  inProgress\n  onHold\n}"),
]

# Regressions for the two bugs the fixtures above found.
FIXTURES += [
    # `1.78:1` contains `78:1`
    ("display_aspect_ratio_notation", "decimal_to_one", "Aspect 2.39:1"),
    ("display_aspect_ratio_notation", "integer_colon_ratio", "Aspect 4:3"),
    # prefixed_upper is a set-level property: every member shares a head segment
    ("graphql_enum_naming_case", "prefixed_upper",
     "enum S {\n  STATUS_ACTIVE\n  STATUS_PAUSED\n  STATUS_CLOSED\n}"),
    ("graphql_enum_naming_case", "screaming_snake",
     "enum S {\n  IN_PROGRESS\n  ON_HOLD\n  IS_DONE\n}"),
]

FIXTURES += [
    ("spelling_variant_policy", "__unresolved__", ""),
    ("spelling_variant_policy", "__unresolved__", "ok"),
]

# --- Wire, editorial and syntax keys from the later ranges, exercising classifiers whose rule order had never been checked against a concrete string ---
FIXTURES += [
    # ---- wire ------------------------------------------------------------
    ("pagination_style", "offset_limit", "GET /activity?offset=40&limit=20"),
    ("pagination_style", "page_number", "GET /activity?page=3"),
    ("pagination_style", "opaque_cursor", "GET /activity?cursor=eyJpZCI6NDB9"),
    ("pagination_style", "link_header", 'Link: </activity?x=1>; rel="next"'),
    ("pagination_style", "range_header", "Content-Range: items 40-59/500"),

    ("query_flag_encoding", "word_literal", "/items?archived=true"),
    ("query_flag_encoding", "digit_literal", "/items?archived=1"),
    ("query_flag_encoding", "enabled_word", "/items?archived=enabled"),
    ("query_flag_encoding", "empty_value", "/items?archived="),
    ("query_flag_encoding", "bare_presence", "/items?archived"),

    ("event_type_naming", "dotted_lower", "order.created"),
    ("event_type_naming", "colon_scoped", "order:created"),
    ("event_type_naming", "slash_path", "order/created"),
    ("event_type_naming", "screaming_snake", "ORDER_CREATED"),
    ("event_type_naming", "pascal_past", "OrderCreated"),

    ("sort_param_syntax", "sign_prefix", "/items?sort=-created"),
    ("sort_param_syntax", "colon_suffix", "/items?sort=created:desc"),
    ("sort_param_syntax", "separate_direction_param", "/items?sort=created&order=desc"),
    ("sort_param_syntax", "bracketed_direction", "/items?sort[created]=desc"),
    ("sort_param_syntax", "spaced_string", "/items?sort=created%20desc"),

    ("error_field_pointer", "json_pointer", '{"pointer": "/items/0/name"}'),
    ("error_field_pointer", "bracket_index_path", '{"field": "items[0].name"}'),
    ("error_field_pointer", "dotted_path", '{"field": "items.name"}'),
    ("error_field_pointer", "leaf_name_only", '{"field": "name"}'),
    ("error_field_pointer", "name_and_location", '{"detail": "field name in body"}'),

    ("binary_field_encoding", "data_scheme_string", 'data:image/png;base64,iVBORw0KGgo='),
    ("binary_field_encoding", "integer_byte_array", "[137, 80, 78, 71, 13, 10]"),
    ("binary_field_encoding", "base64_standard", "iVBORw0KGgoAAAANSUhEUg=="),
    ("binary_field_encoding", "base64url_unpadded", "iVBORw0KGgoAAAANSUhEUg-_"),
    ("binary_field_encoding", "base85_compact", "<~87cURD]i,\"Ebo80~>"),

    ("error_code_vocabulary", "screaming_symbol", '{"code": "RATE_LIMITED"}'),
    ("error_code_vocabulary", "dotted_namespace", '{"code": "billing.card.declined"}'),
    ("error_code_vocabulary", "integer_code", '{"code": 1042}'),
    ("error_code_vocabulary", "prefixed_alphanumeric", '{"code": "ERR4021"}'),
    ("error_code_vocabulary", "http_status_reuse", '{"code": 429}'),

    # ---- editorial -------------------------------------------------------
    ("quotation_mark_style", "double_outer", 'She said "no" firmly.'),
    ("quotation_mark_style", "single_outer", "She said 'no' firmly."),
    ("quotation_mark_style", "guillemets", "She said \u00abno\u00bb firmly."),
    ("quotation_mark_style", "italic_no_marks", "She said *no* firmly."),
    ("quotation_mark_style", "indented_unmarked", "She said:\n\n    no\n"),

    ("initials_punctuation", "period_and_space", "J. R. Tolkien wrote it."),
    ("initials_punctuation", "period_no_space", "J.R. Tolkien wrote it."),
    ("initials_punctuation", "spaced_no_periods", "J R Tolkien wrote it."),
    ("initials_punctuation", "closed_no_periods", "JR Tolkien wrote it."),
    ("initials_punctuation", "names_spelled_out", "John Ronald Tolkien wrote it."),

    ("honorific_style", "abbreviated_with_period", "Dr. Chen will review."),
    ("honorific_style", "abbreviated_no_period", "Dr Chen will review."),
    ("honorific_style", "spelled_in_full", "Doctor Chen will review."),
    ("honorific_style", "no_title_plain_name", "Wei Chen"),
    ("honorific_style", "postnominal_letters", "Chen, MD, PhD"),

    ("rating_display", "fraction_of_five", "Rated 4.5/5"),
    ("rating_display", "star_glyphs", "Rated \u2605\u2605\u2605\u2605"),
    ("rating_display", "percentage", "Rated 90%"),
    ("rating_display", "bare_decimal", "Rated 4.5"),
    ("rating_display", "word_band", "Rated excellent"),

    ("fraction_in_prose", "words", "About a third of users."),
    ("fraction_in_prose", "slash_digits", "About 1/3 of users."),
    ("fraction_in_prose", "single_glyph", "About \u00bd of users."),
    ("fraction_in_prose", "decimal_two_places", "About 0.33 of users."),
    ("fraction_in_prose", "percentage", "About 33% of users."),

    # ---- syntax ----------------------------------------------------------
    ("acronym_style", "all_caps", "Use the API here."),
    ("acronym_style", "period_separated", "Use the A.P.I. here."),
    ("acronym_style", "initial_cap", "Use the Api here."),
    ("acronym_style", "all_lower", "use the api here"),
    ("acronym_style", "expanded_words", "Use the Application Programming Interface here."),
    # Only a listed acronym is one: "errors" is not, and "e.g." is not a period-separated acronym. Both used to be.
    ("acronym_style", "__unresolved__", "The migration completed without errors."),
    ("acronym_style", "all_caps", "We called the API for each team, e.g. the platform group."),
    ("acronym_style", "all_lower", "Data were collected through the api and stored as csv files."),
    ("acronym_style", "all_caps", "Three APIs and one SDK were tested."),
    # Two forms follow no one option; a capital opening a sentence is no form.
    ("acronym_style", "__unresolved__", "We called the API, then the sdk."),
    ("acronym_style", "__unresolved__", "Api calls were logged."),

    ("time_of_day", "colon_24h", "Starts 14:30"),
    ("time_of_day", "ampm_spaced_caps", "Starts 2:30 PM"),
    ("time_of_day", "ampm_tight_lower", "Starts 2:30pm"),
    ("time_of_day", "four_digit_military", "Starts 1430"),
    ("time_of_day", "dotted_24h", "Starts 14.30"),

    ("ordinal_style", "bare_number", "Position 3"),
    ("ordinal_style", "suffix_letters", "Position 3rd"),
    ("ordinal_style", "word_form", "Position third"),
    ("ordinal_style", "roman_numeral", "Position III"),
    ("ordinal_style", "hash_prefix", "Position #3"),

    ("dash_punctuation", "closed_em_dash", "the result\u2014a failure\u2014was clear"),
    ("dash_punctuation", "spaced_em_dash", "the result \u2014 a failure \u2014 was clear"),
    ("dash_punctuation", "spaced_en_dash", "the result \u2013 a failure \u2013 was clear"),
    ("dash_punctuation", "double_hyphen", "the result -- a failure -- was clear"),
    ("dash_punctuation", "paired_commas", "the result, a failure, was clear"),

    ("env_list_packing", "colon_separated", "PATHS=/a:/b:/c"),
    ("env_list_packing", "comma_separated", "PATHS=/a,/b"),
    ("env_list_packing", "space_separated", 'PATHS="/a /b"'),
    ("env_list_packing", "numbered_variables", "PATH_1=/a\nPATH_2=/b"),
    ("env_list_packing", "json_array_string", 'PATHS=["/a","/b"]'),

    ("policy_directive_separator", "semicolon_newline", "allow read;\nallow write;\n"),
    ("policy_directive_separator", "semicolon_space", "allow read; allow write"),
    ("policy_directive_separator", "pipe_symbol", "allow read | allow write"),
    ("policy_directive_separator", "comma_delimited", "allow read, allow write"),
    ("policy_directive_separator", "double_newline", "allow read\n\nallow write"),
    # fmt-0213: mixed delimiters are 'other'. The ordered list returned the first kind it met.
    ("policy_directive_separator", "__unresolved__", "allow read; allow write | allow exec"),
    ("policy_directive_separator", "semicolon_space",
     "Here is the header:\n\nallow read; allow write"),
]

# Regressions for two more bugs these fixtures found. Each is the case that DISCRIMINATES.
FIXTURES += [
    # `sort=-?[+-]?\w` matched any value, so every label but sign_prefix was starved.
    ("sort_param_syntax", "colon_suffix", "/items?sort=name:asc"),
    # Underscore emphasis must not fire inside a snake_case identifier.
    ("quotation_mark_style", "double_outer", '{"user_id": "a", "note": "x"}'),
]

# fmt-0053: real services ship two paging mechanisms for compatibility, so two is 'other'.
FIXTURES += [
    ("pagination_style", "__unresolved__", "GET /activity?page=3&cursor=eyJpZCI6NDB9"),
]

# The last thirteen declared labels no fixture reached: until these were written, thirteen options across ten scenarios had never been shown reachable at all.
FIXTURES += [
    ("uuid_rendering", "base32_compact", "id MFRGGZDFMZTWQ2LKNNWG23TPOA"),
    ("charset_parameter", "spaced_parameter", "Content-Type: text/plain; charset = utf-8"),
    ("move_redirect_status", "status_302", "HTTP/1.1 302 Found"),
    ("move_redirect_status", "status_303", "HTTP/1.1 303 See Other"),
    ("stream_framing", "length_prefixed", '42\n{"id": 1}'),
    ("stream_framing", "multipart_boundaries",
     '--chunkA1B2C3\nContent-Type: application/json\n\n{"n": 1}\n--chunkA1B2C3--'),
    ("time_window_parameters", "start_plus_duration", "/metrics?start=2026-03-01&duration=P7D"),
    ("time_window_parameters", "relative_keyword", "/metrics?range=last_7_days"),
    # A full month name AND an abbreviated long one is the mixed policy: the label is a property of the pair.
    ("month_in_prose", "mixed_by_length", "Filed in March, revised in Sept. and closed in Dec."),
    # The scale sits in the heading and nowhere else; no reading carries a degree sign, or `celsius_symbol` would take it.
    ("temperature_scale", "bare_number_scale_in_heading",
     "| Sensor | Temp (°C) |\n| intake | 21.4 |\n| outlet | 19.8 |"),
    # `unnumbered` is an absence label, so it needs two real headings as proof of presence.
    ("section_numbering", "unnumbered",
     "## Scope\n\nThe change is small.\n\n## Rollout\n\nStaged over a week."),
    ("isbn_hyphenation_formatting", "ten_unhyphenated", "ISBN 0306406152"),
    ("display_aspect_ratio_notation", "fractional_expression", "Aspect 16/9"),
]
