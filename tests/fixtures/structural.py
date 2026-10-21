"""Fixtures for `fmt/structural.py` -- the keys that need a parser.
The alignment fixtures differ from one another only in the number of spaces, so they are
written as explicit strings rather than built, and a reformatting tool would break them
visibly rather than quietly."""

from whowins.checkers.core import UNRESOLVED

FIXTURES: list[tuple[str, str, str]] = [
    ("column_alignment", "left",
     "Opening balance   1234.56\nInterest          89\nClosing balance   4500.00"),
    ("column_alignment", "right",
     "Opening balance   1234.56\nInterest               89\nClosing balance   4500.00"),
    ("column_alignment", "decimal_point",
     "Opening balance   1234.56\nInterest            89\nClosing balance   4500.00"),
    ("column_alignment", "centred",
     "Opening balance   1234.56\nInterest             89\nClosing balance   4500.00"),
    ("column_alignment", "zero_padded",
     "Opening balance   0001234.56\nInterest          0000089\nClosing balance   0004500.00"),

    ("value_encoding", "bare_number", '{"temp": 21.4, "humidity": 48.2}'),
    ("value_encoding", "quoted_number", '{"temp": "21.4", "humidity": "48.2"}'),
    ("value_encoding", "unit_suffixed_string", '{"temp": "21.4 C", "humidity": "48.2 %"}'),
    ("value_encoding", "object_with_unit",
     '{"temp": {"value": 21.4, "unit": "C"}, "humidity": {"value": 48.2, "unit": "%"}}'),
    ("value_encoding", "pair_array", '{"temp": [21.4, "C"], "humidity": [48.2, "%"]}'),

    # Key names chosen so all five orders are distinct strings, with lengths 2, 6, 6, 10, 10 -- neither alphabetical nor reverse.
    ("key_ordering", "alphabetical",
     '{"amount": 120, "changed_by": "sam", "created_at": "2026-01-02", '
     '"id": "a1", "status": "paid"}'),
    ("key_ordering", "reverse_alphabetical",
     '{"status": "paid", "id": "a1", "created_at": "2026-01-02", '
     '"changed_by": "sam", "amount": 120}'),
    ("key_ordering", "id_first",
     '{"id": "a1", "amount": 120, "changed_by": "sam", "created_at": "2026-01-02", '
     '"status": "paid"}'),
    ("key_ordering", "audit_last",
     '{"amount": 120, "id": "a1", "status": "paid", "changed_by": "sam", '
     '"created_at": "2026-01-02"}'),
    ("key_ordering", "ascending_length",
     '{"id": "a1", "amount": 120, "status": "paid", "changed_by": "sam", '
     '"created_at": "2026-01-02"}'),

    ("empty_collection", "empty_array", '{"query": "widget", "results": []}'),
    ("empty_collection", "null_literal", '{"query": "widget", "results": null}'),
    ("empty_collection", "omitted_key", '{"query": "widget", "total": 0}'),
    ("empty_collection", "empty_string", '{"query": "widget", "results": ""}'),
    ("empty_collection", "zero_count_object", '{"query": "widget", "results": {"count": 0}}'),

    ("flatten_style", "dot_path", "id,user.tier,user.region\n7,gold,eu"),
    ("flatten_style", "double_underscore_path", "id,user__tier,user__region\n7,gold,eu"),
    ("flatten_style", "leaf_name_only", "id,tier,region\n7,gold,eu"),
    ("flatten_style", "json_blob_cell", 'id,user\n7,{"tier": "gold"}'),
    ("flatten_style", "exploded_rows", "key,value\nuser.tier,gold\nuser.region,eu"),

    ("tag_list_shape", "flow_array", "tags: [alpha, beta]"),
    ("tag_list_shape", "block_list", "tags:\n  - alpha\n  - beta"),
    ("tag_list_shape", "comma_string", 'tags: "alpha, beta"'),
    ("tag_list_shape", "space_string", 'tags: "alpha beta"'),
    ("tag_list_shape", "repeated_key", "tag: alpha\ntag: beta"),

    ("error_payload_shape", "flat_code_message",
     '{"code": "invalid_email", "message": "Email is not valid"}'),
    ("error_payload_shape", "nested_error_key",
     '{"error": {"code": "invalid_email", "message": "Email is not valid"}}'),
    ("error_payload_shape", "errors_array",
     '{"errors": [{"code": "invalid_email", "message": "Email is not valid"}]}'),
    ("error_payload_shape", "problem_detail",
     '{"type": "about:blank", "title": "Invalid request", "detail": "Email is not valid"}'),
    ("error_payload_shape", "field_keyed_map",
     '{"email": ["is not valid"], "name": ["is required"]}'),

    # Every sample sends BOTH an Accept header and a format parameter, because fmt-0068's request does; the label reads which the server honoured.
    ("response_type_selection", "accept_header",
     "The request sends both an Accept header and a format parameter. "
     "The server honours the Accept header."),
    ("response_type_selection", "format_query_param",
     "The request sends both an Accept header and a format parameter. "
     "The server honours the format query parameter."),
    ("response_type_selection", "path_extension",
     "The request sends both an Accept header and a format parameter. "
     "The server uses the path extension instead."),
    ("response_type_selection", "custom_header",
     "The request sends both an Accept header and a format parameter. "
     "The server reads X-Response-Format instead."),
    ("response_type_selection", "separate_endpoints",
     "The export is published as two separate endpoints, one per type."),
]

FIXTURES += [
    # fmt-0061: a body carrying both an error wrapper and a root-level code.
    ("error_payload_shape", UNRESOLVED,
     '{"code": "invalid_email", "error": {"message": "Email is not valid"}}'),
    # fmt-0068: two carriers named as honoured is not a decision.
    ("response_type_selection", UNRESOLVED,
     "The server honours the Accept header. The server also honours the format parameter."),
    # fmt-0037: a present, non-empty results field is none of the five.
    ("empty_collection", UNRESOLVED, '{"query": "widget", "results": [{"id": 1}]}'),
]

FIXTURES += [
    ("freshness_declaration", "max_age_only", "Cache-Control: max-age=300"),
    ("freshness_declaration", "s_maxage_only", "Cache-Control: s-maxage=300"),
    ("freshness_declaration", "expires_absolute", "Expires: Wed, 09 Sep 2026 10:00:00 GMT"),
    ("freshness_declaration", "max_age_with_swr",
     "Cache-Control: max-age=300, stale-while-revalidate=60"),
    ("freshness_declaration", "immutable_long_max_age",
     "Cache-Control: max-age=31536000, immutable"),

    ("cookie_attribute_policy", "samesite_lax", "Set-Cookie: sid=abc; Path=/; SameSite=Lax"),
    ("cookie_attribute_policy", "samesite_strict", "Set-Cookie: sid=abc; Path=/; SameSite=Strict"),
    ("cookie_attribute_policy", "samesite_none_secure",
     "Set-Cookie: sid=abc; Path=/; SameSite=None; Secure"),
    ("cookie_attribute_policy", "host_prefixed_lax",
     "Set-Cookie: __Host-sid=abc; Path=/; SameSite=Lax"),
    ("cookie_attribute_policy", "partitioned_lax",
     "Set-Cookie: sid=abc; Path=/; SameSite=Lax; Partitioned"),

    ("idempotency_key_carrier", "request_header", "POST /payments\nIdempotency-Key: 9f2c1b4a"),
    ("idempotency_key_carrier", "body_field",
     'POST /payments\n\n{"idempotency_key": "9f2c1b4a", "amount": 120}'),
    ("idempotency_key_carrier", "query_parameter", "POST /payments?idempotency_key=9f2c1b4a"),
    ("idempotency_key_carrier", "path_segment", "POST /payments/9f2c1b4a2d3e4f50"),
    ("idempotency_key_carrier", "derived_content_hash",
     "The client derives the key from a SHA-256 digest of the request body."),

    ("media_type_specificity", "generic_json", "Content-Type: application/json"),
    ("media_type_specificity", "vendor_tree_json", "Content-Type: application/vnd.orders.v3+json"),
    ("media_type_specificity", "resource_subtype_json", "Content-Type: application/orders+json"),
    ("media_type_specificity", "version_parameter", "Content-Type: application/json; version=3"),
    ("media_type_specificity", "schema_parameter", "Content-Type: application/json; schema=orders"),

    ("trailing_slash_policy", "slash_only", "GET /orders/\nGET /invoices/"),
    ("trailing_slash_policy", "bare_only", "GET /orders\nGET /invoices"),
    ("trailing_slash_policy", "bare_alias", "GET /orders/\nGET /orders  (alias)"),
    ("trailing_slash_policy", "slash_alias", "GET /orders\nGET /orders/  (alias)"),
    ("trailing_slash_policy", "optional_pattern", "GET /orders/?"),

    ("quota_exposure", "x_prefixed_triple",
     "X-RateLimit-Limit: 1000\nX-RateLimit-Remaining: 940\nX-RateLimit-Reset: 3600"),
    ("quota_exposure", "unprefixed_triple",
     "RateLimit-Limit: 1000\nRateLimit-Remaining: 940\nRateLimit-Reset: 3600"),
    ("quota_exposure", "structured_single_header",
     "RateLimit: limit=1000, remaining=940, reset=3600"),
    ("quota_exposure", "body_meta_object",
     '{"meta": {"limit": 1000, "remaining": 940, "reset": 3600}}'),
    ("quota_exposure", "on_breach_only", "HTTP/1.1 429 Too Many Requests\nRetry-After: 60"),

    ("retry_advice_encoding", "retry_after_seconds", "Retry-After: 60"),
    ("retry_advice_encoding", "retry_after_http_date",
     "Retry-After: Wed, 09 Sep 2026 10:00:00 GMT"),
    ("retry_advice_encoding", "body_delay_millis", '{"retry_after_ms": 60000}'),
    ("retry_advice_encoding", "body_absolute_timestamp", '{"retry_at": "2026-09-09T10:00:00Z"}'),
    ("retry_advice_encoding", "custom_header_millis", "X-Retry-After-Ms: 60000"),

    ("partial_result_signal", "partial_flag",
     'HTTP/1.1 200 OK\n\n{"data": [1, 2], "partial": true}'),
    ("partial_result_signal", "errors_alongside_data",
     'HTTP/1.1 200 OK\n\n{"data": [1, 2], "errors": [{"source": "c"}]}'),
    ("partial_result_signal", "status_206", "HTTP/1.1 206 Partial Content"),
    ("partial_result_signal", "status_207", "HTTP/1.1 207 Multi-Status"),
    ("partial_result_signal", "warning_header",
     'HTTP/1.1 200 OK\nWarning: 199 - "one backend timed out"'),

    ("delete_confirmation_body", "empty_body", "HTTP/1.1 204 No Content"),
    ("delete_confirmation_body", "full_echo", '{"id": "a1", "name": "Widget", "price": 120}'),
    ("delete_confirmation_body", "id_only", '{"id": "a1"}'),
    ("delete_confirmation_body", "count_object", '{"deleted": 1}'),
    ("delete_confirmation_body", "status_message", '{"message": "Record removed"}'),

    ("bulk_outcome_shape", "ordered_parallel_array", '[{"ok": true}, {"ok": false}]'),
    ("bulk_outcome_shape", "keyed_by_id", '{"r1": {"ok": true}, "r2": {"ok": false}}'),
    ("bulk_outcome_shape", "split_arrays", '{"succeeded": [1, 2], "failed": [3]}'),
    ("bulk_outcome_shape", "failures_only", '{"failed": [3]}'),
    ("bulk_outcome_shape", "all_or_nothing", '{"status": "rejected", "reason": "row 3 invalid"}'),
]

FIXTURES += [
    # fmt-0069: a response sending both Cache-Control and Expires.
    ("freshness_declaration", UNRESOLVED,
     "Cache-Control: max-age=300\nExpires: Wed, 09 Sep 2026 10:00:00 GMT"),
    # fmt-0071: a path segment routinely echoed as a body id as well.
    ("idempotency_key_carrier", UNRESOLVED,
     'POST /payments/9f2c1b4a2d3e4f50\n\n{"idempotency_key": "9f2c1b4a2d3e4f50"}'),
    # fmt-0076: the custom header sent beside the standard one.
    ("retry_advice_encoding", UNRESOLVED, "Retry-After: 60\nX-Retry-After-Ms: 60000"),
    # fmt-0078: a 206 that also carries a partial flag is labelled by status.
    ("partial_result_signal", "status_206",
     'HTTP/1.1 206 Partial Content\n\n{"data": [1, 2], "partial": true}'),
    # fmt-0075: a prefixed response must never also count as unprefixed.
    ("quota_exposure", "x_prefixed_triple", "X-RateLimit-Limit: 1000\nX-RateLimit-Remaining: 940"),
]

FIXTURES += [
    ("job_progress_report", "percent_field", '{"percent": 42}'),
    ("job_progress_report", "counts_pair", '{"processed": 4200, "total": 10000}'),
    ("job_progress_report", "stage_name", '{"stage": "merging"}'),
    ("job_progress_report", "state_only", '{"state": "running"}'),
    ("job_progress_report", "eta_timestamp", '{"eta": "2026-09-09T10:00:00Z"}'),

    ("signature_carrier", "single_header", "X-Signature: sha256=abc"),
    ("signature_carrier", "header_pair", "X-Signature: sha256=abc\nX-Timestamp: 1757400000"),
    ("signature_carrier", "authorization_scheme",
     'Authorization: Webhook keyId="k1", signature="abc"'),
    ("signature_carrier", "envelope_field", '{"signature": "abc", "event": "order.created"}'),
    ("signature_carrier", "query_parameter", "POST /hooks/inbound?signature=abc"),

    ("event_envelope_shape", "flat_reserved_keys",
     '{"id": "e1", "type": "order.created", "orderId": "a1", "total": 120}'),
    ("event_envelope_shape", "data_wrapper",
     '{"id": "e1", "type": "order.created", "data": {"orderId": "a1"}}'),
    ("event_envelope_shape", "header_body_pair",
     '{"headers": {"id": "e1"}, "body": {"orderId": "a1"}}'),
    ("event_envelope_shape", "typed_key_wrapper",
     '{"id": "e1", "order.created": {"orderId": "a1"}}'),
    ("event_envelope_shape", "headers_sidecar",
     'ce-id: e1\nce-type: order.created\n\n{"orderId": "a1"}'),

    ("dead_letter_marking", "reason_in_headers",
     'x-death-reason: max attempts exceeded\n\n{"orderId": "a1"}'),
    ("dead_letter_marking", "failure_envelope",
     '{"reason": "max attempts exceeded", "original": {"orderId": "a1"}}'),
    ("dead_letter_marking", "injected_field",
     '{"orderId": "a1", "failure_reason": "max attempts exceeded"}'),
    ("dead_letter_marking", "sidecar_record",
     '{"orderId": "a1"}\n{"ref": "a1", "reason": "max attempts exceeded"}'),
    ("dead_letter_marking", "topic_name_only", "Republish to orders.dlq unchanged."),

    # fmt-0086's record carries an unset field of each kind, so the mixed form shows an empty collection exactly where the plain form shows null.
    ("unset_field_convention", "always_null",
     '{"name": "Ada", "nickname": null, "tags": null, "address": null}'),
    ("unset_field_convention", "omit_unset", '{"name": "Ada", "tier": "gold"}'),
    ("unset_field_convention", "null_scalar_empty_collection",
     '{"name": "Ada", "nickname": null, "tags": [], "address": {}}'),
    ("unset_field_convention", "omitted_with_manifest",
     '{"name": "Ada", "omitted": ["nickname", "tags"]}'),
    ("unset_field_convention", "type_zero_value",
     '{"name": "Ada", "nickname": "", "visits": 0, "active": false}'),

    ("deprecation_signal", "response_header",
     'Deprecation: true\n\n{"id": "a1", "address": "12 Mill Street"}'),
    ("deprecation_signal", "deprecated_name_suffix",
     '{"id": "a1", "address_deprecated": "12 Mill Street"}'),
    ("deprecation_signal", "body_warning",
     '{"id": "a1", "address": "12 Mill Street", "warning": {"field": "address"}}'),
    ("deprecation_signal", "parallel_replacement_field",
     '{"id": "a1", "address": "12 Mill Street", "postal_address": "12 Mill Street"}'),
    ("deprecation_signal", "removal_date_field",
     '{"id": "a1", "address": "12 Mill Street", "removal_date": "2027-01-01"}'),

    ("enum_extension_policy", "reserved_block",
     "enum Status { PLACED = 1; SHIPPED = 2; reserved 3 to 9; }"),
    ("enum_extension_policy", "unknown_member",
     "enum Status { UNKNOWN = 0; PLACED = 1; SHIPPED = 2; }"),
    ("enum_extension_policy", "open_string", "status: string"),
    ("enum_extension_policy", "dense_numbering",
     "enum Status { PLACED = 1; PACKED = 2; SHIPPED = 3; }"),
    ("enum_extension_policy", "numeric_with_gaps",
     "enum Status { PLACED = 10; PACKED = 20; SHIPPED = 30; }"),

    ("total_count_exposure", "meta_total", '{"meta": {"total": 4200}, "results": []}'),
    ("total_count_exposure", "total_header", "X-Total-Count: 4200"),
    ("total_count_exposure", "estimated_total",
     '{"meta": {"estimated_total": 4200}, "results": []}'),
    ("total_count_exposure", "has_more_only", '{"meta": {"has_more": true}, "results": []}'),
    ("total_count_exposure", "last_page_link", '{"links": {"last": "/search?page=42"}}'),

    ("filter_operator_syntax", "bracket_operator", "GET /orders?total[gte]=500"),
    ("filter_operator_syntax", "underscore_operator", "GET /orders?total__gte=500"),
    ("filter_operator_syntax", "expression_string", "GET /orders?filter=total ge 500"),
    ("filter_operator_syntax", "encoded_object", 'GET /orders?filter={"total":{"gte":500}}'),
    ("filter_operator_syntax", "dedicated_param", "GET /orders?min_total=500"),

    ("field_mask_syntax", "comma_list", "GET /orders/1?fields=id,name,tier"),
    ("field_mask_syntax", "brace_expression", "GET /orders/1?fields=id,owner{name,tier}"),
    ("field_mask_syntax", "pointer_array", '{"fields": ["/id", "/owner/name"]}'),
    ("field_mask_syntax", "prefer_header", "GET /orders/1\nPrefer: return=minimal"),
    ("field_mask_syntax", "named_view", "GET /orders/1?view=summary"),
]

FIXTURES += [
    # fmt-0081: counts and a percentage express the same fraction; both is 'other'.
    ("job_progress_report", UNRESOLVED, '{"percent": 42, "processed": 4200, "total": 10000}'),
    # fmt-0085: an envelope carrying its OWN reason field is still the wrapper.
    ("dead_letter_marking", "failure_envelope",
     '{"failure_reason": "max attempts exceeded", "original": {"orderId": "a1"}}'),
    # fmt-0092: a request carrying two mask carriers.
    ("field_mask_syntax", UNRESOLVED, "GET /orders/1?fields=id,name&view=summary"),
    # fmt-0089: the estimated name must win over the exact one, not the type.
    ("total_count_exposure", "estimated_total", '{"meta": {"estimated_total": 4200}}'),
]

FIXTURES += [
    ("conditional_write_guard", "if_match", 'PUT /docs/1\nIf-Match: "v7"'),
    ("conditional_write_guard", "if_unmodified_since",
     "PUT /docs/1\nIf-Unmodified-Since: Wed, 09 Sep 2026 10:00:00 GMT"),
    ("conditional_write_guard", "body_version_field",
     'PUT /docs/1\n\n{"version": 7, "title": "Draft"}'),
    ("conditional_write_guard", "expected_state_object",
     'PUT /docs/1\n\n{"expected": {"version": 7}, "title": "Draft"}'),
    ("conditional_write_guard", "custom_version_header", "PUT /docs/1\nX-Doc-Version: 7"),

    ("schema_version_carrier", "envelope_field",
     '{"schema_version": 3, "payload": {"id": "a1"}}'),
    ("schema_version_carrier", "message_header", 'Schema-Version: 3\n\n{"id": "a1"}'),
    ("schema_version_carrier", "binary_prefix",
     "magic byte 0x00 then a four byte schema id ahead of the payload"),
    ("schema_version_carrier", "topic_segment", "topic orders.events-v3"),
    ("schema_version_carrier", "content_type_param",
     "Content-Type: application/json; version=3"),

    ("compression_signalling", "negotiated", "Content-Encoding: gzip\nVary: Accept-Encoding"),
    ("compression_signalling", "always_on", "Content-Encoding: gzip"),
    ("compression_signalling", "custom_header", "X-Body-Compression: zstd"),
    ("compression_signalling", "field_level", '{"payload_compressed": "H4sIAAAAAAAA"}'),
    ("compression_signalling", "codec_in_media_type",
     "Content-Type: application/json; codec=zstd"),

    ("request_id_echo", "same_header_echo",
     "Request: X-Request-Id: abc123\nResponse: X-Request-Id: abc123"),
    ("request_id_echo", "correlation_header",
     "Request: X-Request-Id: abc123\nResponse: X-Correlation-Id: abc123"),
    ("request_id_echo", "body_on_errors", '{"error": "not found", "request_id": "abc123"}'),
    ("request_id_echo", "header_and_body",
     'Response: X-Request-Id: abc123\n\n{"error": "not found", "request_id": "abc123"}'),
    ("request_id_echo", "server_minted",
     "Request: X-Request-Id: abc123\nResponse: X-Request-Id: 9f2c1b4a"),

    ("end_of_pages_signal", "cursor_null", '{"items": [], "next_cursor": null}'),
    ("end_of_pages_signal", "cursor_omitted", '{"items": []}'),
    ("end_of_pages_signal", "has_more_false", '{"items": [], "has_more": false}'),
    ("end_of_pages_signal", "cursor_empty_string", '{"items": [], "next_cursor": ""}'),
    ("end_of_pages_signal", "remaining_count_zero", '{"items": [], "remaining": 0}'),

    ("action_endpoint_shape", "post_subpath", "POST /orders/8812/cancel"),
    ("action_endpoint_shape", "patch_status_field",
     'PATCH /orders/8812\n\n{"status": "cancelled"}'),
    ("action_endpoint_shape", "actions_collection",
     'POST /actions\n\n{"type": "cancel", "order": "8812"}'),
    ("action_endpoint_shape", "put_subresource", "PUT /orders/8812/cancellation"),
    ("action_endpoint_shape", "command_field_in_body",
     'POST /orders/8812\n\n{"command": "cancel"}'),

    ("patch_body_format", "merge_patch", '{"email": "ada@example.test"}'),
    ("patch_body_format", "operation_array",
     '[{"op": "replace", "path": "/email", "value": "ada@example.test"}]'),
    ("patch_body_format", "full_replacement",
     '{"id": "c1", "name": "Ada", "email": "ada@example.test", "tier": "gold"}'),
    ("patch_body_format", "fields_plus_mask",
     '{"email": "ada@example.test", "mask": ["email"]}'),
    ("patch_body_format", "before_after_pair",
     '{"email": {"before": "old@example.test", "after": "ada@example.test"}}'),

    ("link_representation", "relation_keyed_object",
     '{"id": "i1", "links": {"self": "/invoices/i1"}}'),
    ("link_representation", "link_object_array",
     '{"id": "i1", "links": [{"rel": "self", "href": "/invoices/i1"}]}'),
    ("link_representation", "link_header", 'Link: </invoices/i1>; rel="self"'),
    ("link_representation", "flat_target_fields", '{"id": "i1", "self_url": "/invoices/i1"}'),
    ("link_representation", "ids_only", '{"id": "i1", "customer_id": "c1"}'),

    ("nested_resource_addressing", "nested_path", "GET /orders/8812/items/3"),
    ("nested_resource_addressing", "flat_with_parent_filter", "GET /items/3?order=8812"),
    ("nested_resource_addressing", "flat_global_id", "GET /items/3"),
    ("nested_resource_addressing", "composite_id_segment", "GET /items/8812:3"),
    ("nested_resource_addressing", "aggregate_only", "GET /orders/8812"),

    ("soft_delete_representation", "excluded", '{"accounts": [{"id": "a1", "name": "Ada"}]}'),
    ("soft_delete_representation", "deleted_flag",
     '{"accounts": [{"id": "a1", "name": "Ada", "deleted": true}]}'),
    ("soft_delete_representation", "deleted_at_timestamp",
     '{"accounts": [{"id": "a1", "name": "Ada", "deleted_at": "2026-09-01"}]}'),
    ("soft_delete_representation", "tombstone_id_only", '{"accounts": [{"id": "a1"}]}'),
    ("soft_delete_representation", "excluded_with_gone", "GET /accounts/a1\nHTTP/1.1 410 Gone"),

    ("cache_hit_disclosure", "age_header", "Age: 42"),
    ("cache_hit_disclosure", "hit_miss_header", "X-Cache: HIT"),
    ("cache_hit_disclosure", "body_meta_field", '{"meta": {"cache": "hit"}}'),
    ("cache_hit_disclosure", "server_timing_entry", 'Server-Timing: cache;desc="hit";dur=2'),
    ("cache_hit_disclosure", "node_id_header", "X-Cache-Node: edge-lhr-04"),
]

FIXTURES += [
    # fmt-0095: a request sending two guards.
    ("conditional_write_guard", UNRESOLVED, 'PUT /docs/1\nIf-Match: "v7"\nX-Doc-Version: 7'),
    # fmt-0096: a producer stamping the version in two places.
    ("schema_version_carrier", UNRESOLVED, 'Schema-Version: 3\n\n{"schema_version": 3}'),
    # fmt-0100: null, empty string and a missing key are three states of one field; two markers at once is 'other'.
    ("end_of_pages_signal", UNRESOLVED,
     '{"items": [], "next_cursor": null, "has_more": false}'),
    # fmt-0110: a response stating the outcome twice.
    ("cache_hit_disclosure", UNRESOLVED, "Age: 42\nX-Cache: HIT"),
    # fmt-0099: both carriers, tested before either single one.
    ("request_id_echo", "header_and_body",
     'X-Correlation-Id: abc123\n\n{"correlation_id": "abc123"}'),
]

FIXTURES += [
    ("config_comment_placement", "above_each_setting",
     "# how many workers to run\nworkers = 8\n"
     "# seconds before a task is abandoned\ntimeout = 30"),
    ("config_comment_placement", "trailing_same_line",
     "workers = 8   # how many workers to run\n"
     "timeout = 30  # seconds before a task is abandoned"),
    ("config_comment_placement", "single_file_header",
     "# Worker configuration for the ingest service.\n# Change these with care.\n\n"
     "workers = 8\ntimeout = 30"),
    ("config_comment_placement", "per_section_banner",
     "# Concurrency\nworkers = 8\nthreads = 4\n\n# Timeouts\ntimeout = 30\nretries = 3"),
    ("config_comment_placement", "trailing_file_footer",
     "workers = 8\ntimeout = 30\n\n"
     "# Both values are tuned for the ingest service.\n# Change them with care."),

    ("diff_presentation", "unified_three_lines",
     "@@ -10,7 +10,7 @@\n def price(x):\n     base = x * 1.2\n     tax = base * 0.2\n"
     "-    return base + tax\n+    return round(base + tax, 2)\n     # end\n"),
    ("diff_presentation", "unified_whole_file",
     "@@ -1,9 +1,9 @@\n import math\n \n def price(x):\n     base = x * 1.2\n"
     "     tax = base * 0.2\n-    return base + tax\n+    return round(base + tax, 2)\n"),
    ("diff_presentation", "side_by_side",
     "    return base + tax        |     return round(base + tax, 2)\n"
     "    # end                    |     # end\n"),
    ("diff_presentation", "word_level_inline",
     "    return {+round(+}base + tax{+, 2)+}\n"),
    ("diff_presentation", "stat_summary_only",
     "pricing.py | 4 ++--\n1 file changed, 2 insertions(+), 2 deletions(-)"),

    ("ownership_declaration", "path_then_team", "/api/ @payments\n/web/ @frontend"),
    ("ownership_declaration", "team_then_path_block",
     "@payments:\n  /api/\n@frontend:\n  /web/"),
    ("ownership_declaration", "default_then_overrides", "* @platform\n/api/ @payments"),
    ("ownership_declaration", "commented_section_groups",
     "# Services\n/api/ @payments\n\n# Front end\n/web/ @frontend"),
    ("ownership_declaration", "single_repository_owner", "@platform"),
    # Prose around the file is not a record.
    ("ownership_declaration", "single_repository_owner", "Here is the file:\n\n@platform"),
    ("script_argument_style", "environment_driven",
     "RELEASE_VERSION=3.4.0 RELEASE_ENV=production\n./release.sh\n\n"
     "Let me know if you need anything else."),
    ("footnote_marker_position", "paragraph_end",
     "The boundary was redrawn. The treaty followed soon after.¹\n\n"
     "Let me know if you need anything else."),

    ("import_group_order", "origin_groups",
     "import os\nimport sys\n\nimport requests\n\nfrom src.models import Order\n"),
    ("import_group_order", "single_alphabetical", "import json\nimport os\nimport sys\n"),
    ("import_group_order", "line_length_ascending",
     "import os\nimport json\nimport subprocess\n"),
    ("import_group_order", "depth_grouped",
     "from a import x\n\nfrom a.b import y\n\nfrom a.b.c import z\n"),
    ("import_group_order", "type_imports_last", "import os\n\nfrom typing import Optional\n"),

    ("license_notice_form", "identifier_line", "// SPDX-License-Identifier: MIT"),
    ("license_notice_form", "full_text_block",
     "// Permission is hereby granted, free of charge, to any person\n"
     "// obtaining a copy of this software and associated documentation\n"
     "// files, to deal in the Software without restriction, including\n"
     "// without limitation the rights to use, copy, modify, merge,\n"
     "// publish, distribute, sublicense, and sell copies of it, and to\n"
     "// permit persons to whom the Software is furnished to do so,\n"
     "// subject to the following conditions being met in full.\n"
     "// The above notice shall be included in all copies.\n"
     "// The software is provided as is, without warranty."),
    ("license_notice_form", "short_notice_year_holder", "// Copyright 2026 the authors"),
    ("license_notice_form", "file_reference_line", "// See LICENSE at the repository root."),
    ("license_notice_form", "boxed_banner",
     "/* ============================\n * Released under the MIT licence.\n"
     " * ============================ */"),

    ("editor_settings_scoping", "root_file_glob_sections",
     '{"src/**/*.ts": {"indent": 2}, "docs/**/*.md": {"indent": 4}}'),
    ("editor_settings_scoping", "language_keyed_map",
     '{"python": {"indent": 4}, "typescript": {"indent": 2}}'),
    ("editor_settings_scoping", "severity_keyed_groups",
     '{"error": {"no-unused": true}, "warn": {"no-console": true}}'),
    ("editor_settings_scoping", "one_flat_rule_set", '{"indent": 2, "quotes": "single"}'),
    ("editor_settings_scoping", "ordered_last_wins",
     '{"indent": 2, "quotes": "single", "indent": 4}'),

    ("vendored_code_marking", "upstream_name_line", "// Upstream: fastjsonparser"),
    ("vendored_code_marking", "version_and_date_line",
     "// fastjsonparser v2.4.1, copied 2026-08-30"),
    ("vendored_code_marking", "local_patch_list", "// Local patches: none"),
    ("vendored_code_marking", "do_not_edit_banner", "// GENERATED FILE - DO NOT EDIT"),
    ("vendored_code_marking", "checksum_line",
     "// sha256 " + "9f2c1b4a" * 8),

    ("help_text_layout", "usage_then_flags",
     "Usage: reporter [options] <path>\n\n  --format   output format\n"
     "  --quiet    suppress progress"),
    ("help_text_layout", "flags_then_examples",
     "  --format   output format\n  --quiet    suppress progress\n\n"
     "Examples:\n  reporter --format json ."),
    ("help_text_layout", "two_column_table",
     "  --format   output format\n  --quiet    suppress progress"),
    ("help_text_layout", "prose_paragraphs",
     "The reporter walks a path and prints a summary of what it finds.\n\n"
     "It writes to standard output and never modifies the tree it reads."),
    ("help_text_layout", "sectioned_man_style",
     "NAME\n  reporter\n\nSYNOPSIS\n  reporter [options] <path>"),

    ("script_argument_style", "positional_only", "./release.sh 3.4.0 production"),
    ("script_argument_style", "long_flags_only",
     "./release.sh --version 3.4.0 --env production"),
    ("script_argument_style", "subcommand_first", "./release.sh publish --version 3.4.0"),
    ("script_argument_style", "environment_driven",
     "RELEASE_VERSION=3.4.0 RELEASE_ENV=production\n./release.sh"),
    ("script_argument_style", "config_file_argument", "./release.sh release.yaml"),

    ("workspace_glob_declaration", "explicit_path_list",
     'members = ["packages/api", "packages/web"]'),
    ("workspace_glob_declaration", "single_star_glob", 'members = ["packages/*"]'),
    ("workspace_glob_declaration", "double_star_glob", 'members = ["packages/**"]'),
    ("workspace_glob_declaration", "per_layer_globs",
     'members = ["apps/*", "libs/*", "tools/*"]'),
    ("workspace_glob_declaration", "glob_with_exclusion",
     'members = ["packages/*", "!packages/legacy"]'),

    ("matrix_axis_declaration", "full_cross_product",
     "strategy:\n  matrix:\n    os: [ubuntu, macos]\n    node: [20, 22]\n"),
    ("matrix_axis_declaration", "cross_with_exclusions",
     "strategy:\n  matrix:\n    os: [ubuntu, macos]\n    node: [20, 22]\n"
     "    exclude:\n      - os: macos\n"),
    ("matrix_axis_declaration", "primary_axis_plus_extras",
     "strategy:\n  matrix:\n    node: [20, 22]\n    include:\n      - node: 18\n"),
    ("matrix_axis_declaration", "explicit_combination_list",
     "strategy:\n  matrix:\n    - os: ubuntu\n      node: 20\n    - os: macos\n      node: 22\n"),
    ("matrix_axis_declaration", "separate_jobs_no_matrix",
     "jobs:\n  test-ubuntu:\n    runs-on: ubuntu\n  test-macos:\n    runs-on: macos\n"),
]

FIXTURES += [
    # fmt-0114: a header block AND per-setting notes -- the realistic mixed case.
    ("config_comment_placement", UNRESOLVED,
     "# Worker configuration for the ingest service.\n\n"
     "workers = 8   # how many workers to run\ntimeout = 30  # seconds before a task"),
    # fmt-0118: word-level marking sits inside an ordinary three-line hunk, so a checker counting context first would call it unified_three_lines.
    ("diff_presentation", "word_level_inline",
     "@@ -10,7 +10,7 @@\n def price(x):\n     base = x * 1.2\n     tax = base * 0.2\n"
     "-    return {+round(+}base + tax{+, 2)+}\n"),
    # fmt-0126: the catch-all form's LATER records are path-then-team lines.
    ("ownership_declaration", "default_then_overrides",
     "* @platform\n/api/ @payments\n/web/ @frontend"),
    # fmt-0140: the exclusion form also contains a glob.
    ("workspace_glob_declaration", "glob_with_exclusion",
     'members = ["packages/**", "!packages/legacy"]'),
]

FIXTURES += [
    ("hook_declaration_style", "script_per_phase", ".git/hooks/pre-commit\n.git/hooks/pre-push"),
    ("hook_declaration_style", "declarative_tool_list", "hooks:\n  - id: ruff\n  - id: black"),
    ("hook_declaration_style", "dispatcher_with_registry",
     "run: scripts/hooks.sh\nregistry: hooks.toml"),
    ("hook_declaration_style", "shared_symlinked_directory", "ln -s ../../tools/hooks .git/hooks"),
    ("hook_declaration_style", "inline_command", "pre-commit:\n  command: ruff check ."),

    ("phony_target_declaration", "one_grouped_declaration",
     ".PHONY: build test clean\n\nbuild:\n\tgo build ./..."),
    ("phony_target_declaration", "per_target_declaration",
     ".PHONY: build\nbuild:\n\tgo build ./...\n.PHONY: test\ntest:\n\tgo test ./..."),
    ("phony_target_declaration", "naming_convention_only",
     "build:\n\tgo build ./...\ntest:\n\tgo test ./..."),
    ("phony_target_declaration", "sentinel_dependency",
     "build: FORCE\n\tgo build ./...\ntest: FORCE\n\tgo test ./...\nFORCE:"),
    ("phony_target_declaration", "pattern_rule",
     "%.task:\n\t@echo running $@\nbuild.task:\n\tgo build ./..."),

    ("default_value_documentation", "parenthetical_suffix",
     "  --format   output format (default: json)\n  --retries  attempts to make (default: 3)"),
    ("default_value_documentation", "separate_column",
     "  --format   json    output format\n  --retries  3       attempts to make"),
    ("default_value_documentation", "inline_bracket",
     "  --format   output format [default: json]\n  --retries  attempts to make [default: 3]"),
    ("default_value_documentation", "after_flag_name",
     "  --format json output format\n  --retries 3 attempts to make"),
    ("default_value_documentation", "footer_list",
     "  --format   output format\n  --retries  attempts to make\n\n"
     "Defaults: format=json, retries=3"),

    ("required_config_placeholder", "angle_bracket_token",
     "database_url: <postgres connection string>\napi_key: <issued key>"),
    ("required_config_placeholder", "empty_with_comment",
     "# the postgres connection string\ndatabase_url:\n# the key issued to you\napi_key:"),
    ("required_config_placeholder", "changeme_literal",
     "database_url: CHANGEME\napi_key: CHANGEME"),
    ("required_config_placeholder", "commented_example_value",
     "# database_url: postgres://localhost/app\ndatabase_url:\n# api_key: abc123\napi_key:"),
    ("required_config_placeholder", "null_with_required_flag",
     "database_url: null  # required\napi_key: null  # required"),

    ("skipped_test_marking", "skip_annotation_with_reason",
     '@pytest.mark.skip(reason="flaky on the timezone boundary")\n'
     "def test_timezone():\n    assert convert() == 1"),
    ("skipped_test_marking", "commented_out_body",
     "def test_timezone():\n    # assert convert() == 1\n    # assert offset() == 0"),
    ("skipped_test_marking", "name_prefix_marker",
     "def skip_test_timezone():\n    assert convert() == 1"),
    ("skipped_test_marking", "conditional_early_return",
     "def test_timezone():\n    if os.environ.get('CI'):\n        return\n"
     "    assert convert() == 1"),
    ("skipped_test_marking", "expected_failure_marker",
     "@pytest.mark.xfail(reason='flaky on the timezone boundary')\n"
     "def test_timezone():\n    assert convert() == 1"),

    ("merge_requirement_expression", "fixed_reviewer_count",
     "A change needs 2 approvals before it lands."),
    ("merge_requirement_expression", "owner_approval_only",
     "A change needs one approval from a listed code owner."),
    ("merge_requirement_expression", "count_plus_owner",
     "A change needs 2 approvals, one of which must be a code owner."),
    ("merge_requirement_expression", "per_path_rules",
     "/api/*: two approvals\n/docs/*: one approval"),
    ("merge_requirement_expression", "checks_only",
     "A change lands once the checks are green; no human approval is required."),

    ("toolchain_pin_declaration", "root_version_file", ".nvmrc contains 22.4.0"),
    ("toolchain_pin_declaration", "manifest_engines_field", '"engines": { "node": "22.4.0" }'),
    ("toolchain_pin_declaration", "image_reference", "FROM node:22.4.0-bookworm"),
    ("toolchain_pin_declaration", "readme_prose_only",
     "## Getting started\n\nBuild this with Node 22.4 or later."),
    ("toolchain_pin_declaration", "script_enforced", "#!/bin/sh\nnvm install 22.4.0"),

    ("optional_dependency_grouping", "named_extra_group",
     '[project.optional-dependencies]\nplotting = ["matplotlib"]'),
    ("optional_dependency_grouping", "dev_section_split",
     '[tool.poetry.dev-dependencies]\nmatplotlib = "^3.9"'),
    ("optional_dependency_grouping", "per_line_optional_flag",
     'matplotlib = { version = "^3.9", optional = true }'),
    ("optional_dependency_grouping", "platform_markers",
     "matplotlib>=3.9; sys_platform == 'linux'"),
    ("optional_dependency_grouping", "all_required",
     'matplotlib = "^3.9"\npandas = "^2.2"'),

    ("migration_revert_strategy_declaration", "dedicated_down_block",
     "-- +migrate Up\nALTER TABLE orders ADD COLUMN note text;\n"
     "-- down\nALTER TABLE orders DROP COLUMN note;"),
    ("migration_revert_strategy_declaration", "reversible_change_block",
     "def change do\n  add_column :orders, :note, :text\nend"),
    ("migration_revert_strategy_declaration", "transaction_wrapper",
     "BEGIN;\nALTER TABLE orders ADD COLUMN note text;\nCOMMIT;"),
    ("migration_revert_strategy_declaration", "sql_comment_toggle",
     "ALTER TABLE orders ADD COLUMN note text;\n-- DROP COLUMN note;"),
    ("migration_revert_strategy_declaration", "prohibited_irreversible",
     "-- irreversible\nDROP TABLE legacy_orders;"),

    ("cache_revalidation_policy_header", "must_revalidate_max",
     "Cache-Control: max-age=60, must-revalidate"),
    ("cache_revalidation_policy_header", "no_cache_alone", "Cache-Control: no-cache"),
    ("cache_revalidation_policy_header", "immutable_long",
     "Cache-Control: max-age=31536000, immutable"),
    ("cache_revalidation_policy_header", "stale_while_revalidate",
     "Cache-Control: max-age=60, stale-while-revalidate=300"),
    ("cache_revalidation_policy_header", "no_store_strict", "Cache-Control: no-store"),
]

FIXTURES += [
    # fmt-0156: a global count AND per-path delegation.
    ("merge_requirement_expression", UNRESOLVED,
     "Every change needs 2 approvals.\n/api/*: three approvals\n/docs/*: one approval"),
    # fmt-0222: a file carrying an irreversible annotation AND a change block.
    ("migration_revert_strategy_declaration", "prohibited_irreversible",
     "-- irreversible\ndef change do\n  drop_table :legacy_orders\nend"),
    # fmt-0222: any of the other four may sit inside BEGIN/COMMIT, so the transaction wrapper is only for a patch carrying no other marker.
    ("migration_revert_strategy_declaration", "dedicated_down_block",
     "BEGIN;\n-- down\nALTER TABLE orders DROP COLUMN note;\nCOMMIT;"),
    # fmt-0228: contradictory tokens.
    ("cache_revalidation_policy_header", UNRESOLVED, "Cache-Control: no-store, max-age=60"),
    # fmt-0155: a decorated test that ALSO returns early is not a guard.
    ("skipped_test_marking", "skip_annotation_with_reason",
     '@pytest.mark.skip(reason="flaky")\ndef test_timezone():\n    if True:\n        return\n'
     "    assert convert() == 1"),
]

FIXTURES += [
    ("note_placement", "beneath_citing_line",
     "The treaty was signed in 1919 [1]\n[1] The date is disputed.\n"
     "The borders changed [2]\n[2] See the annexe."),
    ("note_placement", "end_of_passage",
     "The treaty was signed in 1919 [1]\nThe borders changed [2]\n\n"
     "[1] The date is disputed.\n[2] See the annexe."),
    ("note_placement", "inline_parenthetical",
     "The treaty was signed in 1919 (the date is disputed by some historians)."),
    ("note_placement", "indented_under_paragraph",
     "The treaty was signed in 1919 [1]\nThe borders changed soon after.\n"
     "    [1] The date is disputed."),
    ("note_placement", "preface_before_passage",
     "[1] The date is disputed.\n\nThe treaty was signed in 1919 [1]"),

    ("table_caption_position", "above_table",
     "Table 1. Recovery by segment\n| Segment | Rate |\n| --- | --- |\n| North | 12% |"),
    ("table_caption_position", "below_table",
     "| Segment | Rate |\n| --- | --- |\n| North | 12% |\nTable 1. Recovery by segment"),
    ("table_caption_position", "first_row",
     "| Table 1. Recovery by segment |\n| --- |\n| North 12% |"),
    ("table_caption_position", "in_preceding_paragraph",
     "Recovery differed sharply by segment across the whole period.\n"
     "| Segment | Rate |\n| --- | --- |\n| North | 12% |"),
    ("table_caption_position", "last_row",
     "| Segment | Rate |\n| --- | --- |\n| North | 12% |\n| Table 1. Recovery by segment |"),

    ("measurement_presentation", "metric_only", "Width 60 cm, depth 45 cm."),
    ("measurement_presentation", "imperial_only", "Width 24 in, depth 18 in."),
    ("measurement_presentation", "metric_then_imperial",
     "Width 60 cm (24 in), depth 45 cm (18 in)."),
    ("measurement_presentation", "imperial_then_metric",
     "Width 24 in (60 cm), depth 18 in (45 cm)."),
    ("measurement_presentation", "parallel_columns",
     "| Metric | Imperial |\n| --- | --- |\n| 60 cm | 24 in |"),

    # fmt-0179's marker sits MID-SENTENCE, because the word-anchored form coincides with both sentence-end forms when the cited word closes the sentence.
    ("footnote_marker_position", "after_terminal_period",
     "The boundary moved.¹ The treaty followed.²"),
    ("footnote_marker_position", "before_terminal_period",
     "The boundary moved¹. The treaty followed²."),
    ("footnote_marker_position", "at_the_cited_word",
     "The boundary¹ was redrawn in 1919 and the treaty followed² soon after."),
    ("footnote_marker_position", "paragraph_end",
     "The boundary was redrawn. The treaty followed soon after.¹"),
    ("footnote_marker_position", "inline_bracketed", "The boundary (1) was redrawn in 1919."),

    ("amount_scale_statement", "column_heading",
     "| Segment | Revenue (£m) |\n| --- | --- |\n| North | 12.4 |"),
    ("amount_scale_statement", "table_caption",
     "Revenue in millions\n| Segment | Revenue |\n| --- | --- |\n| North | 12.4 |"),
    ("amount_scale_statement", "per_figure_suffix",
     "| Segment | Revenue |\n| --- | --- |\n| North | 12.4m |"),
    ("amount_scale_statement", "unscaled_full_digits",
     "| Segment | Revenue |\n| --- | --- |\n| North | 12,400,000 |"),
    ("amount_scale_statement", "closing_footnote",
     "| Segment | Revenue |\n| --- | --- |\n| North | 12.4 |\n\nAll figures in millions."),

    ("optional_step_marking", "trailing_parenthetical",
     "1. Count the back room shelves\n2. Photograph any damaged stock (optional)"),
    ("optional_step_marking", "leading_label_colon",
     "1. Count the back room shelves\n2. Optional: photograph any damaged stock"),
    ("optional_step_marking", "if_clause",
     "1. Count the back room shelves\n2. If any stock is damaged, photograph it"),
    ("optional_step_marking", "note_beneath",
     "1. Count the back room shelves\nPhotographing damaged stock is optional.\n"
     "2. File the count sheet"),
    ("optional_step_marking", "separate_section",
     "1. Count the back room shelves\n2. File the count sheet\n\n"
     "Optional steps\nPhotograph any damaged stock."),

    ("warning_presentation", "bold_inline_label",
     "**Warning:** the disk is wiped before the node leaves the pool."),
    ("warning_presentation", "boxed_callout",
     "+--------------------------+\n| Warning                  |\n"
     "| The disk is wiped first. |\n+--------------------------+"),
    ("warning_presentation", "glyph_prefix",
     "⚠ The disk is wiped before the node leaves the pool."),
    ("warning_presentation", "numbered_caution_step",
     "3. Caution: the disk is wiped before the node leaves the pool."),
    ("warning_presentation", "indented_small_type",
     "    <small>The disk is wiped before the node leaves the pool.</small>"),

    # fmt-0193 needs more than one bullet: the final-bullet and every-bullet rules agree on the last item.
    ("bullet_terminal_punctuation", "no_terminal_mark",
     "- Ships in two days\n- Fits every model\n- Costs nothing to return"),
    ("bullet_terminal_punctuation", "period_on_each",
     "- Ships in two days.\n- Fits every model.\n- Costs nothing to return."),
    ("bullet_terminal_punctuation", "period_on_last_only",
     "- Ships in two days\n- Fits every model\n- Costs nothing to return."),
    ("bullet_terminal_punctuation", "semicolons_then_period",
     "- Ships in two days;\n- Fits every model;\n- Costs nothing to return."),
    ("bullet_terminal_punctuation", "commas_with_conjunction",
     "- Ships in two days,\n- Fits every model,\n- and costs nothing to return."),

    ("definition_list_layout", "term_line_indented_definition",
     "Ledger\n    The record of every posted entry.\n"
     "Accrual\n    Revenue recognised before cash arrives."),
    ("definition_list_layout", "dash_same_line",
     "Ledger - the record of every posted entry.\n"
     "Accrual - revenue recognised before cash arrives."),
    ("definition_list_layout", "colon_same_line",
     "Ledger: the record of every posted entry.\n"
     "Accrual: revenue recognised before cash arrives."),
    ("definition_list_layout", "two_column_table",
     "| Term | Meaning |\n| --- | --- |\n| Ledger | The record of every posted entry. |"),
    ("definition_list_layout", "heading_and_paragraph",
     "### Ledger\n\nThe record of every posted entry."),

    ("glossary_ordering", "strict_alphabetical",
     "Accrual - revenue recognised early\nLedger - the record of entries\n"
     "Zeroing - closing a balance"),
    ("glossary_ordering", "topic_grouped",
     "## Accounting\n\nAccrual - revenue recognised early\nLedger - the record of entries"),
    ("glossary_ordering", "acronyms_first",
     "GAAP - the accounting standard\nIFRS - the reporting standard\n"
     "Accrual - revenue recognised early\nLedger - the record of entries"),
    ("glossary_ordering", "letter_headings",
     "A\n\nAccrual - revenue recognised early\n\nL\n\nLedger - the record of entries"),
    ("glossary_ordering", "two_column_split",
     "| Accrual - revenue early | Ledger - record of entries |\n| --- | --- |\n"
     "| Zeroing - closing | Netting - offsetting |"),
]

FIXTURES += [
    # fmt-0194: an entry carrying both joining characters.
    ("definition_list_layout", UNRESOLVED,
     "Ledger - the record: of every posted entry.\nAccrual - revenue: recognised early."),
    # fmt-0184: the scale declared in two places at once.
    ("amount_scale_statement", UNRESOLVED,
     "Revenue in millions\n| Segment | Revenue (£m) |\n| --- | --- |\n| North | 12.4 |"),
    # fmt-0193: a list of one bullet cannot separate the two period rules.
    ("bullet_terminal_punctuation", UNRESOLVED, "- Costs nothing to return."),
    # fmt-0173: a passage placing notes in two of the five positions.
    ("note_placement", UNRESOLVED,
     "[0] A preface note.\n\nThe treaty was signed in 1919 [1]\n[1] The date is disputed."),
]
