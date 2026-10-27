# Versioned read-only gateway boundary

Frozen base: d537d525296ef34f727996e240ae6c60102c6082 (independent branch).
Reviewed source: grid/db.py Database.ensure_schema, grid/schema.sql,
grid/storage.py insert paths, grid/data_capabilities.py and grid/terminan_gateway.py.
No live database was inspected or accessed. PG18 runtime identity is not attested.

GET /internal/v1/capabilities advertises API major 1/minor 0 and read_only true.
GET /internal/v1/health probes database version/read-only transaction with the
existing connect timeout 3s and statement timeout 3000ms. Database reachability
never grants market readiness. Probe errors return no exception/connection data.
GET /internal/v1/candles and /internal/v1/footprint accept symbol and strict limit
1..1000 (default 300). They return UNAVAILABLE, empty rows and
SOURCE_PROVENANCE_UNAVAILABLE without querying market tables.

These source-owned tables key candles by (symbol, ts) and footprint by
(symbol, ts, price); neither persists mandatory market type, immutable dataset
identity/epoch or qualified freshness. JSON extra and capability readiness flags
do not establish those identities. No request/environment override can grant
readiness. Source identity, release digest, epoch, freshness UTC milliseconds and
market type are explicitly null. Future source metadata needs independent
qualification before enabling data. Footprint is a historical trade aggregate;
it is never live L2. Missing source evidence is UNAVAILABLE, never synthetic PASS.

Legacy /v1 routes retain their existing format for compatibility; they are
unqualified and must not be consumed as the versioned integration contract.
No schema, service, credentials, ACL, exchange subscriptions or order APIs change.
This contract does not claim compatibility with unified-system's synthetic
strattester handoff envelope; that envelope has a different producer and purpose.

Validation: mocked unit/contract tests are SYNTHETIC. Hosted tests, even with a
disposable PostgreSQL instance, do not establish PHYSICAL admission. G0 physical,
G1 Execute/Cleanup and trading remain NOT_AUTHORIZED.
