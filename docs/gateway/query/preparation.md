# Synthetic OHLCV query preparation — local review2

Only grid.gateway_query.prepare_query(request_bytes) and immutable PreparedQuery
are implemented. No shared query ABI, listener, store, mTLS module or capability
adapter is wired. not_executed() always returns NOT_EXECUTED, rows/coverage/gaps/
capabilities/resolved_manifest=null, native_authenticated=false. Requested identity
and cuts remain claims. No success-empty history or verified fixture coverage.

Root authorized pure preparation/tests after ownership ACK. Exact A2 proposed
identity ABI review2 is design-compatible; actual implementation/source admission,
A4 bounded row snapshot seam and Root composition still required. No disclosure
callbacks or store arguments exist in this slice. The fixed local descriptor
profile is not an adopted financial/shared wire.

## Closed request and canonical encoding

schema=grid.gateway.ohlcv-query.v1-review2. Required exact fields: request_id,
dataset_id, dataset_revision, source_class=SYNTHETIC, instrument_id, interval_ms,
data_schema_sha256, query_profile_sha256, range, event_cut_ms, knowledge_cut and
consumer_context. No unknown or missing fields at any level.

Instrument is exchange=bybit/category=linear/symbol=BTCUSDT with explicit positive
u63 instrument_version. Parser does not allocate or prove incarnation. Dataset and
request IDs, consumer_id and view_id are lowercase canonical UUID4. Consumer/view
are claims until actual server-commissioned A2 context/grant verification.

Dataset revision and manifest revision are separate positive u63 decimal strings.
knowledge_cut={manifest_sha256,manifest_revision}. No latest-selector substitution,
clock mapping or counter equality inferred. consumer_context={consumer_id,view_id,
authorization_contract_sha256}; authorization reference is not a grant.

interval_ms='60000'. range={start_ms,end_ms}, aligned half-open UTC Unix ms;
0<=start<end<=event_cut_ms<=253402300799999 and at most1440 requested rows.
event_cut_ms is an inclusive cutoff for final candle END timestamps, not an
ingestion clock. The complete range must end by cutoff; no provisional/future
candle preparation. All times are canonical u63 strings; no JSON numbers/bools,
offset time strings, signs, leading zeroes or guessed clocks.

Encoding is exact ASCII compact JSON, recursively ASCII-key sorted; no BOM,
whitespace or trailing newline. Strings restricted by closed grammar; no optional
escapes, Unicode, duplicate keys, arrays or unknown objects. Maximum32768 bytes;
fixed five-object shape bounds parser recursion before decoding. Hashes lowercase
64hex. prepare_query rejects noncanonical input rather than converting it.

## Planned actual capability mapping, not implemented

A2 schema unified.gateway.read-binding.v1-review2 fields map to dataset_id,
dataset_revision, knowledge_cut.manifest_sha256, data_schema_sha256 and context
consumer/view UUIDs. Manifest revision is not the dataset_revision field. Full
original request bytes also bind range/event cut/manifest revision/query profile/
instrument/auth reference. Per-tool unified.query_market_data capability cannot
be replaced by get_dataset_manifest capability; Root issues separate capabilities
for separately validated original requests. Actual exact type/issuer/source/store
and current-session checks must precede IO and final return.

## Verification and rollback

Own tests cover closed/canonical hostile input, semantic range/cut/bounds,
cross-profile/market/instrument rejection, separate revisions, detached immutable
claims, denial/nulls and preparation with file/socket IO hooks forbidden. These
are local CODE tests, not actual TLS/disclosure/store/reopen/publication/coverage
or hosted Windows CI tests. Financial OHLCV rows are not processed by this slice.
Remove only new files to roll back. Existing Grid paths and data unchanged.
