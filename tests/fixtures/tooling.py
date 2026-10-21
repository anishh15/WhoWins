"""Fixtures for the repository and tooling keys in `fmt/tooling.py`.
Every negative fixture is one the scenario's own `exclusivity` field asks for, so the suite
tests the argument the author made rather than one invented here."""

from whowins.checkers.core import UNRESOLVED

FIXTURES: list[tuple[str, str, str]] = [
    ("dependency_constraint_style", "exact_pin", "4.2.1"),
    ("dependency_constraint_style", "caret_range", "^4.2.1"),
    ("dependency_constraint_style", "tilde_range", "~4.2.1"),
    ("dependency_constraint_style", "comparator_pair", ">=4.2.1,<5.0.0"),
    ("dependency_constraint_style", "wildcard_patch", "4.2.*"),

    ("test_name_style", "should_phrase", "def should_apply_discount_to_large_orders():"),
    ("test_name_style", "given_when_then",
     "def given_empty_cart_when_discount_applied_then_total_is_zero():"),
    ("test_name_style", "test_prefixed", "def test_applies_discount():"),
    ("test_name_style", "plain_sentence", "def discount_is_zero_for_an_empty_cart():"),
    ("test_name_style", "subject_first", "def calculate_discount_returns_zero_on_empty_cart():"),

    ("migration_filename_style", "sequential_integer", "0042_add_refund_column.sql"),
    ("migration_filename_style", "utc_timestamp", "20260908T114233_add_refund_column.sql"),
    ("migration_filename_style", "date_plus_counter", "20260908-03_add_refund_column.sql"),
    ("migration_filename_style", "release_version", "v3.4.0_add_refund_column.sql"),
    ("migration_filename_style", "content_hash_suffix", "add_refund_column_9f2c1b.sql"),

    ("secret_reference_syntax", "env_var_indirection", "password: ${DB_PASSWORD}"),
    ("secret_reference_syntax", "uri_scheme_reference", "password: vault://secret/data/db#password"),
    ("secret_reference_syntax", "file_path_pointer", "passwordFile: /run/secrets/db_password"),
    ("secret_reference_syntax", "deploy_time_placeholder", "password: {{DB_PASSWORD}}"),
    ("secret_reference_syntax", "inline_encrypted_value", "password: ENC[AES256_GCM,data:xLk9]"),

    ("test_double_naming", "mock_prefix", "class MockGateway:"),
    ("test_double_naming", "fake_prefix", "class FakeGateway:"),
    ("test_double_naming", "stub_prefix", "class StubGateway:"),
    ("test_double_naming", "double_suffix", "class GatewayDouble:"),
    ("test_double_naming", "in_memory_prefix", "class InMemoryGateway:"),

    ("ignore_pattern_style", "bare_name", "build"),
    ("ignore_pattern_style", "anchored_slash", "/build"),
    ("ignore_pattern_style", "trailing_slash_dir", "build/"),
    ("ignore_pattern_style", "globstar_path", "**/build/**"),
    ("ignore_pattern_style", "negated_allowlist", "*\n!src/"),

    ("changelog_entry_shape", "plain_sentence",
     "Cache the rate table between requests instead of refetching."),
    ("changelog_entry_shape", "category_prefix", "Fixed: cache stampede on repeated misses."),
    ("changelog_entry_shape", "component_prefix", "scheduler: cache stampede on repeated misses."),
    ("changelog_entry_shape", "ticket_suffix", "Cache the rate table between requests (ABC-412)"),
    ("changelog_entry_shape", "contributor_suffix", "Cache the rate table between requests (@dnorth)"),

    ("exit_code_scheme", "zero_one_binary", "Exit 0 on success, exit 1 otherwise."),
    ("exit_code_scheme", "findings_versus_errors",
     "Exit 0 clean, exit 1 for findings, exit 2 for tool errors."),
    ("exit_code_scheme", "per_category_codes",
     "Exit 1 for style, exit 2 for imports, exit 3 for typing, exit 4 for licence."),
    ("exit_code_scheme", "failure_count",
     "Return the number of findings; the reference run exits 3."),
    ("exit_code_scheme", "reserved_high_range", "Exit 0 clean; failures use codes 64 and 65."),

    ("assertion_style", "fluent_chain", "expect(total).to.equal(4.20)"),
    ("assertion_style", "two_argument_helper", "assertEqual(4.20, total)"),
    ("assertion_style", "bare_assert_expression", "assert total == 4.20"),
    ("assertion_style", "matcher_argument", "assertThat(total, equalTo(4.20))"),
    ("assertion_style", "property_should", "total.should.equal(4.20)"),

    ("fixture_naming", "bare_noun", "def payment():"),
    ("fixture_naming", "validity_prefixed", "def valid_payment():"),
    ("fixture_naming", "article_prefixed", "def a_payment():"),
    ("fixture_naming", "purpose_suffixed", "def payment_for_refund_test():"),
    ("fixture_naming", "numbered_variants", "def payment_1():"),

    ("commit_trailer_style", "key_colon_trailer", "Cache the rate table\n\nCloses: ABC-412"),
    ("commit_trailer_style", "key_equals_footer", "Cache the rate table\n\ncloses=ABC-412"),
    ("commit_trailer_style", "bracketed_subject_token", "[ABC-412] Cache the rate table"),
    ("commit_trailer_style", "bare_subject_reference", "Cache the rate table for ABC-412"),
    ("commit_trailer_style", "closing_body_sentence",
     "Cache the rate table\n\nThis closes ticket ABC-412."),

    ("task_target_naming", "bare_verb", "build:"),
    ("task_target_naming", "verb_noun_colon", "build:docs:"),
    ("task_target_naming", "noun_verb_colon", "docs:build:"),
    ("task_target_naming", "dotted_namespace", "docs.build:"),
    ("task_target_naming", "slash_path", "docs/build:"),
]

# The 'other' cases each exclusivity field names. Without them a classifier reporting the first of two competing decorations passes every positive fixture.
FIXTURES += [
    # fmt-0113: a name opening with an opening word and carrying clause markers later is neither.
    ("test_name_style", UNRESOLVED,
     "def should_given_empty_cart_when_applied_then_zero():"),
    # fmt-0120: opening with one of the three words AND closing with the suffix.
    ("test_double_naming", UNRESOLVED, "class MockGatewayDouble:"),
    # fmt-0121: the leading and trailing slash are independent decorations, and one pattern can legally carry both.
    ("ignore_pattern_style", UNRESOLVED, "/build/"),
    # fmt-0122: a leading token and a trailing one, not the more specific of them.
    ("changelog_entry_shape", UNRESOLVED, "Fixed: cache stampede (ABC-412)"),
    # fmt-0127: a leading decoration and a trailing number.
    ("fixture_naming", UNRESOLVED, "def valid_payment_1():"),
    # fmt-0128: a subject token and a final-line trailer.
    ("commit_trailer_style", UNRESOLVED, "[ABC-412] Cache the rate table\n\nCloses: ABC-412"),
    # fmt-0111: a constraint mixing a caret with a comparator.
    ("dependency_constraint_style", UNRESOLVED, "^4.2.1,<5.0.0"),
]

# --- fmt-0132..0160: six of these keys put one decoration at the front of a name and a competing one at the back and call it 'other'; only a negative fixture shows a classifier honours that ---
FIXTURES += [
    ("todo_marker_style", "bare_marker", "// TODO: retry the poller on a 429"),
    ("todo_marker_style", "owner_in_parens", "// TODO(dnorth): retry the poller on a 429"),
    ("todo_marker_style", "ticket_in_brackets", "// TODO[ABC-412]: retry the poller on a 429"),
    ("todo_marker_style", "review_date_attached", "// TODO 2026-12-01: retry the poller on a 429"),
    ("todo_marker_style", "note_on_next_line", "// TODO\n// retry the poller on a 429"),

    ("workspace_package_naming", "scoped_prefix", '"@acme/billing"\n"@acme/reporting"'),
    ("workspace_package_naming", "dotted_domain", '"com.acme.billing"\n"com.acme.reporting"'),
    ("workspace_package_naming", "dashed_path_echo", '"packages-billing-api"\n"packages-reporting-api"'),
    ("workspace_package_naming", "bare_short_name", '"billing"\n"reporting"'),
    ("workspace_package_naming", "layer_prefixed", '"api-billing"\n"core-reporting"'),

    ("generated_file_marking", "header_banner",
     "// Code generated by schemagen. DO NOT EDIT.\npackage client"),
    ("generated_file_marking", "filename_infix", "client.generated.ts"),
    ("generated_file_marking", "extension_suffix", "client.ts.gen"),
    ("generated_file_marking", "sibling_manifest",
     "generated-files.txt lists client.ts and models.ts"),
    ("generated_file_marking", "own_directory", "generated/client.ts"),

    ("ci_job_naming", "bare_verb", "build:\ntest:"),
    ("ci_job_naming", "stage_prefixed", "build-docker:\ntest-unit:"),
    ("ci_job_naming", "platform_suffixed", "unit-linux:\nsmoke-macos:"),
    ("ci_job_naming", "tool_named", "eslint:\npytest:"),
    ("ci_job_naming", "ordinal_numbered", "job-1:\njob-2:"),

    ("manifest_script_naming", "bare_verbs", '"build": "vite build"'),
    ("manifest_script_naming", "colon_scoped", '"build:css": "postcss"'),
    ("manifest_script_naming", "dash_scoped", '"build-css": "postcss"'),
    ("manifest_script_naming", "lifecycle_prefixed", '"pre-build": "rimraf dist"'),
    ("manifest_script_naming", "camel_names", '"buildCss": "postcss"'),

    ("build_stage_naming", "purpose_words",
     "FROM node:20 AS dependencies\nFROM node:20 AS assets"),
    ("build_stage_naming", "ordinal_numbers", "FROM node:20 AS stage-1\nFROM node:20 AS stage-2"),
    ("build_stage_naming", "tool_named",
     "FROM node:20 AS node-build\nFROM golang:1.23 AS golang-build"),
    ("build_stage_naming", "role_prefixed",
     "FROM node:20 AS builder-web\nFROM node:20 AS runtime-web"),
    ("build_stage_naming", "unnamed_positional", "FROM node:20\nFROM node:20"),

    ("cache_key_composition", "lockfile_hash", "key: deps-${{ hashFiles('**/package-lock.json') }}"),
    ("cache_key_composition", "manifest_hash_plus_platform",
     "key: ${{ runner.os }}-deps-${{ hashFiles('package.json') }}"),
    ("cache_key_composition", "branch_name_segment", "key: deps-${{ github.ref_name }}"),
    ("cache_key_composition", "fixed_key_with_fallback", "key: deps-v1\nrestore-keys: |\n  deps-"),
    ("cache_key_composition", "commit_sha_exact", "key: deps-${{ github.sha }}"),

    ("deprecation_annotation_style", "language_attribute", "@Deprecated\nfun settingsHelper() {}"),
    ("deprecation_annotation_style", "doc_comment_tag",
     "/**\n * @deprecated Use SettingsStore instead.\n */\nfun settingsHelper() {}"),
    ("deprecation_annotation_style", "name_suffix", "fun settingsHelperDeprecated() {}"),
    ("deprecation_annotation_style", "runtime_warning_call",
     'fun settingsHelper() { logger.warn("Use SettingsStore") }'),
    ("deprecation_annotation_style", "dated_removal_comment",
     "// Remove this helper on 2027-03-01\nfun settingsHelper() {}"),

    ("artifact_filename_shape", "name_version_platform", "reporter-3.4.0-linux-amd64.tar.gz"),
    ("artifact_filename_shape", "name_short_hash", "reporter-9f2c1b4.tar.gz"),
    ("artifact_filename_shape", "name_version_build", "reporter-3.4.0-b812.tar.gz"),
    ("artifact_filename_shape", "name_build_date", "reporter-20260908.tar.gz"),
    ("artifact_filename_shape", "name_only", "reporter.tar.gz"),

    ("feature_flag_naming", "behaviour_phrase", '"new_checkout_screen"'),
    ("feature_flag_naming", "team_scoped", '"payments_new_checkout_screen"'),
    ("feature_flag_naming", "ticket_keyed", '"abc_412_checkout_screen"'),
    ("feature_flag_naming", "removal_dated", '"new_checkout_screen_2026_12"'),
    ("feature_flag_naming", "stage_suffixed", '"new_checkout_screen_rollout"'),

    ("review_remark_convention", "nit_prefix",
     "- nit: rename this variable\n- this needs a null check"),
    ("review_remark_convention", "severity_word_prefix",
     "- praise: clean refactor\n- question: why the retry here?"),
    ("review_remark_convention", "question_phrasing",
     "- could this drop the retry cap?\n- should the timeout be configurable?"),
    ("review_remark_convention", "blocking_marked_instead",
     "- blocker: this leaks a connection\n- rename this variable"),
    ("review_remark_convention", "optional_in_summary",
     "## Summary\n- rename this variable\n- tighten the retry cap"),

    ("patch_filename_shape", "numbered_prefix", "02-fix-unicode-escapes.patch"),
    ("patch_filename_shape", "package_version_prefixed", "parser-2.9.1-fix-escapes.patch"),
    ("patch_filename_shape", "ticket_keyed", "ABC-412.patch"),
    ("patch_filename_shape", "description_slug", "fix-unicode-escapes.patch"),
    ("patch_filename_shape", "upstream_hash_named", "a71f0c9.patch"),

    # Two messages each: a house style is a property of the set, and one line alone is indistinguishable from ordinary prose.
    ("cli_error_message_style", "lowercase_no_period",
     "could not read the config file\ncould not reach the metrics endpoint"),
    ("cli_error_message_style", "sentence_case_period",
     "Could not read the config file.\nCould not reach the metrics endpoint."),
    ("cli_error_message_style", "tool_name_prefixed",
     "reporter: could not read the config file\nreporter: could not reach the metrics endpoint"),
    ("cli_error_message_style", "code_then_text",
     "E1042: could not read the config file\nE1043: could not reach the metrics endpoint"),
    ("cli_error_message_style", "remedy_sentence_appended",
     "Could not read the config file. Run reporter init to create one.\n"
     "Could not reach the metrics endpoint. Check the proxy settings."),

    ("command_wrapping_style", "single_long_line",
     "cargo build --release --target x86_64-unknown-linux-gnu --features telemetry --locked"),
    ("command_wrapping_style", "backslash_continuations",
     "cargo build \\\n  --release \\\n  --locked"),
    ("command_wrapping_style", "argument_array",
     'args=(--release --locked --features telemetry)\ncargo build "${args[@]}"'),
    ("command_wrapping_style", "flags_in_config_file", "cargo build --config ./build.toml"),
    ("command_wrapping_style", "flags_in_variable",
     'FLAGS="--release --locked --features telemetry"\ncargo build $FLAGS'),

    ("copyright_year_style", "first_year_only", "Copyright 2021 the authors"),
    ("copyright_year_style", "year_range", "Copyright 2021-2026 the authors"),
    ("copyright_year_style", "year_present_word", "Copyright 2021-present the authors"),
    ("copyright_year_style", "current_year_only", "Copyright 2026 the authors"),
    ("copyright_year_style", "comma_separated_years", "Copyright 2021, 2026 the authors"),
]

FIXTURES += [
    # fmt-0132: a marker carrying two decorations, not the first of them.
    ("todo_marker_style", UNRESOLVED, "// TODO(dnorth)[ABC-412]: retry the poller"),
    # fmt-0137: several teams run two markings at once, and that is 'other'.
    ("generated_file_marking", UNRESOLVED,
     "// Code generated by schemagen. DO NOT EDIT.\n// file: client.generated.ts"),
    # fmt-0138: a leading stage word and a trailing platform word.
    ("ci_job_naming", UNRESOLVED, "build-linux:\nbuild-macos:"),
    # fmt-0145: a branch name combined with a file hash.
    ("cache_key_composition", UNRESOLVED,
     "key: deps-${{ github.ref_name }}-${{ hashFiles('package-lock.json') }}"),
    # fmt-0146: a renamed symbol that also carries the attribute.
    ("deprecation_annotation_style", UNRESOLVED, "@Deprecated\nfun settingsHelperDeprecated() {}"),
    # fmt-0149: a leading team token and a trailing stage token.
    ("feature_flag_naming", UNRESOLVED, '"payments_new_checkout_screen_rollout"'),
    # fmt-0150: a review both marking blocking items and prefixing optional ones.
    ("review_remark_convention", UNRESOLVED,
     "- blocker: this leaks a connection\n- nit: rename this variable"),
]
