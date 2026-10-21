# load/ — the load cell's bundles

Each `lb-NN.json` is one **load bundle**: a replicate of the worked load cell in
`data/trials/03-load.json`, written by hand under [LOAD-AUTHORING.md](../LOAD-AUTHORING.md). A
bundle holds a task, six component scenarios (one tool, one path, four format), a bank of filler
lines and ten trials on the worked bundle's grid of `n` instructions and `k` conflict groups.

The design `load-bundles` sends the worked bundle's ten trials and every bundle here, each on the
model family's own operator channel. Every file is checked by:

```bash
PYTHONPATH=src python3 -m whowins.validation.check_load            # add --lines for every line's tokens
```

It fails a bundle whose trials leave the grid, whose lines are not verbatim option texts or its own
fillers, whose fillers cannot be scored, which does not render as recorded, which shares a
component, project, task or filler line with another bundle, or whose `n`-levels are not one length
in Qwen 3 and Qwen 3.5 tokens.

## The nine bundles

Written by three `dataset-author` agents, one after another, three bundles each: `lb-02` to
`lb-04` on operations work, `lb-05` to `lb-07` on data work, `lb-08` to `lb-10` on product and
support work. Each went through review rounds and passes `check_load` with 0 FAIL; how they
were reviewed, and what review found, is in
[docs/codebase/16_load_bundles_and_tiers.md](../../docs/codebase/16_load_bundles_and_tiers.md).

| bundle | project | tool, path | the four format keys |
|---|---|---|---|
| `lb-02` | `fescue-billing` | `tool-0004`, `path-0011` | boolean_encoding, rate_expression, version_string, timezone_encoding |
| `lb-03` | `sorrel-queue` | `tool-0055`, `path-0027` | weekday_encoding, phone_format, email_display, record_separator |
| `lb-04` | `teasel-ingest` | `tool-0053`, `path-0076` | acronym_style, truncation_marker, link_style, uuid_rendering |
| `lb-05` | `larch-ingest` | `tool-0113`, `path-0098` | exit_code_scheme, env_list_packing, command_wrapping_style, todo_marker_style |
| `lb-06` | `sedge-board` | `tool-0130`, `path-0082` | time_window_parameters, field_mask_syntax, compression_signalling, cache_hit_disclosure |
| `lb-07` | `vetch-reports` | `tool-0152`, `path-0104` | job_progress_report, unset_field_convention, signature_carrier, schema_version_carrier |
| `lb-08` | `wrenfold-app` | `tool-0219`, `path-0224` | month_in_prose, percent_in_prose, env_file_quote_convention, figure_reference_style |
| `lb-09` | `mossgate-hq` | `tool-0202`, `path-0227` | relative_date_wording, contract_amount_expression, initials_punctuation, promotional_code_spelling_pattern |
| `lb-10` | `quillby-handbook` | `tool-0233`, `path-0236` | menu_path_notation, server_variable_placeholder_syntax, number_word_threshold, latin_abbreviation_policy |
