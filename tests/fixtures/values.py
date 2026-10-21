"""Fixtures for the closed-vocabulary value keys in `fmt/values.py`.
Written from each scenario's `exclusivity` field, which is where the traps are recorded --
mostly one vocabulary item containing another."""

from whowins.checkers.core import UNRESOLVED

FIXTURES: list[tuple[str, str, str]] = [
    ("language_tag", "two_letter", "locale: pt"),
    ("language_tag", "hyphen_region", "locale: pt-BR"),
    ("language_tag", "underscore_locale", "locale: pt_BR"),
    ("language_tag", "three_letter", "locale: por"),
    ("language_tag", "english_name", "locale: Portuguese"),

    ("country_code_style", "alpha2_upper", "country: DE"),
    ("country_code_style", "alpha2_lower", "country: de"),
    ("country_code_style", "alpha3_upper", "country: DEU"),
    ("country_code_style", "numeric_code", "country: 276"),
    ("country_code_style", "english_name", "country: Germany"),

    ("unit_spacing", "suffix_tight", "p95 180ms"),
    ("unit_spacing", "suffix_spaced", "p95 180 ms"),
    ("unit_spacing", "abbreviated_word", "p95 180 msec"),
    ("unit_spacing", "full_word", "p95 180 milliseconds"),
    ("unit_spacing", "unit_in_header", "| p95 (ms) |\n| 180 |"),

    ("change_expression", "signed_absolute", "+4,912,000"),
    ("change_expression", "signed_percent", "+58.5%"),
    ("change_expression", "percent_in_parens", "13,312,000 (+58.5%)"),
    ("change_expression", "growth_multiple", "1.58x"),
    ("change_expression", "arrow_pair", "8,400,000 → 13,312,000"),

    ("large_number_style", "western_grouping", "1,240,000"),
    ("large_number_style", "indian_grouping", "12,40,000"),
    ("large_number_style", "si_suffix", "1.24M"),
    ("large_number_style", "word_scale", "1.24 million"),
    ("large_number_style", "scientific", "1.24e6"),

    ("shell_prompt", "dollar_prompt", "$ systemctl restart api\n$ journalctl -u api"),
    ("shell_prompt", "hash_prompt", "# systemctl restart api\n# journalctl -u api"),
    ("shell_prompt", "angle_prompt", "> systemctl restart api\n> journalctl -u api"),
    ("shell_prompt", "percent_prompt", "% systemctl restart api\n% journalctl -u api"),
    ("shell_prompt", "no_prompt", "systemctl restart api\njournalctl -u api"),

    ("param_doc_style", "field_list_tags", ":param retries: attempts before giving up"),
    ("param_doc_style", "indented_args_section", "Args:\n    retries: attempts before giving up"),
    ("param_doc_style", "underlined_section", "Parameters\n----------\nretries : int"),
    ("param_doc_style", "at_param_tags", "@param retries attempts before giving up"),
    ("param_doc_style", "prose_summary",
     "Retries the call up to the given number of attempts before it gives up entirely."),

    ("branch_name_style", "type_slash_prefix", "git checkout -b feat/retry-poller"),
    ("branch_name_style", "ticket_key_first", "git checkout -b OPS-412-retry-poller"),
    ("branch_name_style", "initials_prefix", "git checkout -b jd/retry-poller"),
    ("branch_name_style", "bare_slug", "git checkout -b retry-poller"),
    ("branch_name_style", "dated_prefix", "git checkout -b 2026-09-07-retry-poller"),

    ("period_label", "iso_week", "2026-W37"),
    ("period_label", "calendar_quarter", "2026 Q3"),
    ("period_label", "fiscal_quarter", "FY27 Q1"),
    ("period_label", "month_name_year", "September 2026"),
    ("period_label", "numeric_year_month", "2026-09"),

    ("bool_field_naming", "is_prefix", '{"is_active": true, "is_verified": false}'),
    ("bool_field_naming", "has_prefix", '{"has_active": true, "has_verified": false}'),
    ("bool_field_naming", "bare_adjective", '{"active": true, "verified": false}'),
    ("bool_field_naming", "enabled_suffix", '{"active_enabled": true, "verified_enabled": false}'),
    ("bool_field_naming", "flag_suffix", '{"active_flag": true, "verified_flag": false}'),


    ("redaction_style", "full_mask", "password=********"),
    ("redaction_style", "last_four", "password=********3f7a"),
    ("redaction_style", "fixed_token", "password=[REDACTED]"),
    ("redaction_style", "hash_digest", "password=9f86d081"),
    ("redaction_style", "field_omitted", "host=db.internal\nport=5432\nuser=reporting"),
]

# The traps each scenario's exclusivity field names, as negative fixtures.
FIXTURES += [
    # fmt-0032: the two alpha-2 forms are the same letters in different case, so a mixed-case value is 'other'.
    ("country_code_style", UNRESOLVED, "country: De"),
    # fmt-0047: a command whose ARGUMENTS carry a dollar sign is not prompted -- only the leading character is.
    ("shell_prompt", "no_prompt", "systemctl restart api\necho $HOME/logs"),
    # fmt-0052: the scenario forbids a name carrying both a prefix and a suffix, and a mixed schema wins neither.
    ("bool_field_naming", UNRESOLVED, '{"is_active": true, "verified_flag": false}'),
    # fmt-0039: a table writing the unit in BOTH the header and the cells has not chosen the header form.
    ("unit_spacing", "suffix_spaced", "| p95 (ms) |\n| 180 ms |"),
]
