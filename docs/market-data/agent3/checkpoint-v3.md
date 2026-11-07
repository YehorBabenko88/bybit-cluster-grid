# Checkpoint V3 claim codec

This additive standard-library module implements the reviewed V3 CLAIM format.
It does not load schemas from files, access storage/network, create authority,
verify real receipt/clock evidence, or enable a factory/router/collector. Existing
shared checkpoint readers, lifecycle modules and startup remain unchanged.

`parse_claim(bytes)` requires bounded canonical bytes and returns an immutable
`ParsedCheckpointClaim`. `as_dict()` returns a detached copy. `encode_claim(dict)`
validates the same closed shape and internal relationships, returning canonical
claim bytes. `require_authoritative_checkpoint(...)` always raises
`AuthorityIntegrationUnavailable`; no caller boolean or fake verifier enables it.
The claim's `commit_status` describes submitted data, not independent verification.

Owner Option1 decision is pinned at Unified commit
`381b18bab7f1162db4eef7f348b6e1c921e76403`,
`release/contracts/checkpoint-v3-time/DECISION.json`, raw SHA256
`aa84f7acbe7632f8d534c96f529c7a39b9b1b26c1a49cf7a69a9366e5c04670e`.
All12 required fields remain in immutable publication_content, with exact
`committed_at_utc:null` and `commit_time_status:UNKNOWN_COMMIT_INSTANT`.
`confirmed_observed_at_utc` is external qualified-or-null observation time, never
the actual commit instant. Time uncertainty does not make a confirmed commit
unconfirmed; `COMMIT_UNCONFIRMED` is a separate closed result with no committed
content/evidence. A parsed COMMITTED claim still cannot authorize any effect.

Reviewed source images:

- schema SHA256 `4de720d9391e5a89c0577b5298c283e742fbfe490c4454c184e31c2348589ea4`
- protocol SHA256 `79efbcb70d1ed9204fbd8295a4990650d99582196712097280d2483298ad4f8e`
- golden manifest SHA256 `69ef7786400030ae1bb9dbf4bd1fb30c6b6e50ac9690437536aa669a7c18b0d4`

A2/A4/A5 exact ACKs cover pure content/evidence schema and consumer design, not
actual publication. The module embeds the exact raw schema as escaped byte
constants. Approved CRLF schema/manifest fixtures are base64-wrapped in
`tests/fixtures/agent3-checkpoint-v3/approved-text-images.json`, preserving reviewed
raw bytes across Git checkout line-ending policies. Other fixtures are exact
canonical synthetic bytes. Tests independently check decoded raw hashes, not
LF-normalized substitutes. No synthetic receipt is an actual authority proof.

Canonical rules: UTF-8/ASCII, sorted unique object keys, no whitespace/BOM/newline,
exact null/enums, checked decimal-string u63 counters (no JSON numbers), exact
UUID/hash/id patterns, Gregorian UTC milliseconds, no old aliases. Max32768bytes,
depth12,48members/object; raw depth/size checked before recursive JSON parse.
The fixed embedded-schema subset and cross-object checks reject conflicting
identity/fence/revision/hash/cursor/clock claims. Encoding is bounded too. This
is not a general JSON Schema implementation or a proof that referenced objects,
sessions or clocks exist. Native session UUID/authenticity/current-state checks
and independently qualified clock evidence belong to an admitted proof adapter.

## Actual legacy formats and compatibility boundary

At base `ec967b3ebb67bb9f04d0d82c78bba5b4245a3333`, historical REST backfill consumes
a SQL state mapping containing `symbol`, `timeframe`, `next_end_ms` and launch
metadata in `grid/market_backfill.py`; it is not a versioned V1/V2 JSON checkpoint
reader. `ObserverCheckpoint.load/save` in `grid/observer_checkpoint.py` reads/writes
analytics observer last_ts/state and returns a tuple; it is a separate contract.
`SegmentWAL` reads numeric acknowledgment checkpoints, not ingestion publication
proof. Those files and their behavior are unchanged by this additive module.

The previously drafted V1/V2 publication schemas were output-only designs, not
deployed readers. Preserving draft bytes alone is not runtime backward-compatibility
proof. Tests exercise the actual ObserverCheckpoint reader with a fake SQL boundary
and reject legacy SQL/observer/draft objects at the V3 entry point. Callers must
explicitly select an existing legacy reader when appropriate. There is no automatic
dispatch, conversion, timestamp relabel, missing-status fallback or admitted
legacy-to-V3 migration. Integrating a real version router/migration remains a gate.

## Evidence scope

Offline tests cover confirmed claim/unknown time, unconfirmed shape, delayed and
repeated observation, separate-process reload retaining UNTRUSTED status, malformed
evidence, incompatible versions, canonical/size/depth errors and inconsistent or
historical fences never authorizing. They use only local synthetic fixtures and
fake DB results; no real database, provider or authority. Reload tests demonstrate
codec behavior after process restart, not durable Consul recovery after a crash.

Actual A2 publication confirmation requires original receipt/idempotency/full intent,
actual publication index/revisions/root/content/identity and current disclosure
authorization. Lifecycle EFFECT_UNWIRED/index cannot substitute. Real no-quorum,
renewal/revocation, closure/allocation/debit, crash durability and stale-writer
rejection require the separately allocated actual producer and real fault tests.
Provider budgets/civil-time deadlines/external paused-sender containment remain
independent. No full lifecycle, runtime deployment or physical acceptance is claimed.
