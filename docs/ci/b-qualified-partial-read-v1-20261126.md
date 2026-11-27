# B / ROUND 3 — managed Market Data v2 qualified PARTIAL read

**Candidate only — CODE NO_GO / PRODUCTION NO_GO.** Existing draft
[Grid PR #300](https://github.com/YehorBabenko88/bybit-cluster-grid/pull/300)
is stacked on draft #299. No merge or live activation.

## Explicit compatibility and source ownership

- Historical canonical Data49 `market_data/*` source files and original sealed
  902-node roster are **byte-unmodified**. The 884 Grid + 18 Strattester
  exact-node test split remains an independently mandatory gate in #299.
- New additive `market_data_v2` is packaged in the **same** `market-data`
  wheel, now **`0.2.0.dev0` candidate**, with no second Bybit transport,
  writer, database, supervisor or HTTP listener. The legacy
  `grid/qualified_read_contract.py` has only a short import alias; the
  **single** validator is `market_data_v2.qualified_read_contract`.
- Existing `market_data.cli`, `market_data.history_api` and v1.1 routes
  remain untouched. v2 must be explicitly selected in Root's protected
  manifest; there is **no fallback or automatic change** to v1 deployment.

## Managed-only GET route

`GET /internal/v2/candles/qualified?symbol=BTCUSDT&limit=1[&before_ms=...]`

Query uses closed fields and one value each, exact uppercase symbol, page size
1–1000 and optional positive int64 millisecond cursor. Missing fields,
duplicates, noncanonical decimals, extra keys and malformed syntax fail
without querying PostgreSQL. Bytes bounded at ingress; response ≤8 MiB.

Entrypoint: `market_data_v2.read_api.main(['serve'], startup_admission=source)`,
compatible with Root `service_module_runtime.py::serve_module`'s existing
`module.main(arguments, startup_admission=source)` invocation.
Only a Root-approved, version/source-pinned manifest may select this module
**instead of** old `market_data.cli`; B does not alter Root's selector.

The replacement handler extends the historical `history_api.Handler`, uses
the **same loopback socket/port**, and preserves historical v1 routes.
Unmanaged invocation is rejected **before bind**. Required at each request:
valid private `Bearer UNIFIED_INSTANCE_TOKEN`, current Root
`startup_identity` and `require_current()` checked at ingress, immediately
before PostgreSQL read and again before response publication. C still owns
isolated database lifecycle and SQL reader/writer grants. No route invokes
Bybit, opens a writer, starts a new service or trades.

Canonical source read uses `market_data.history_api.immutable_minutes`
(`READ ONLY REPEATABLE READ` SQL on `provenance_minutes`) and records
created by `market_data.provenance.minute_record` with
`producer='market_data'`. Legacy `producer='bybit-cluster-grid'` is
rejected **even if the record is rehashed**; no migration by relabeling.

## Versioned DTO and evidence boundaries

Published exact structural schema:
`docs/contracts/qualified-read-envelope-v1.schema.json`.
Published isolated synthetic producer fixture:
`scripts/qualified_read_v2_fixture.py`.

- Outer `schema='market_data.qualified-read-envelope.v1'`,
  `api_version={major:2,minor:0}`; individual source rows remain v1.1.
- `read_only=True`, `record_integrity=VERIFIED` only for closed shape,
  canonical SHA256 and canonical Math OHLC/footprint validation.
- `source_authenticity=NOT_INDEPENDENTLY_ATTESTED` despite current
  Root transport identity; public-provider authenticity is separate.
- `quality_attestation=NOT_INDEPENDENTLY_ATTESTED`,
  `source_declared_quality` is an explicitly **untrusted** source label.
- `exchange_completeness=NOT_ATTESTED`; interval
  `coverage.expected_minutes/observed_minutes/missing_minutes` is
  **not** exchange-wide trade completeness or backtest authorization.
- `storage_immutability=NOT_ATTESTED`, `immutable=False` always.
  C's `lab-postgres-custody.v1` role/trigger witness is an independent,
  owner-only, LAB-scoped value **outside the untrusted HTTP record**.
  It must not be promoted by caller-supplied JSON or made to prove Bybit.
- `execution_authority=False`, `trading_authorized=False`,
  `paper_admitted=False` for **every** status.

A validated, fresh continuous interval produces
`PARTIAL/EXCHANGE_COMPLETENESS_UNATTESTED`, **never AVAILABLE**.
Missing minutes or epoch/identity/revision changes produce
`GAP/MISSING_MINUTES_OR_EPOCH_CHANGE`; expired source event watermark
produces `STALE/FRESHNESS_WATERMARK_EXPIRED`; unavailable source records
or empty storage produce `UNAVAILABLE/SOURCE_PROVENANCE_UNAVAILABLE`.
Duplicate minute revisions, invalid row fingerprints, forged
completeness/authority, malformed clock, future events/ingestion,
invalid OHLC/levels or unbounded quality reasons are rejected.

HTTP 400 is reserved for malformed request/query; integrity/SQL failures
return HTTP 503 with constant redacted errors. No DSN, raw exception,
secret, token or market source data appears in error responses.

## Test contract / exact scope (not yet CI-accepted)

- `tests/market_data/test_qualified_read_contract.py`: **15** authored
  canonical provenance, freshness, epoch, gaps, source-quality and tamper
  positive/negative methods.
- `tests/market_data/test_qualified_route_v2.py`: **12** authored actual
  canonical producer to read response, in-memory managed HTTP handler,
  bearer, pre/post Root revocation, mismatched producer, no-socket
  unmanaged/argv refusal and Root launcher ABI tests.
- `tests/market_data/test_qualified_read_schema_v2.py`: **4** authored
  JSON Schema + fixture validation and forged-status/witness/authority
  negative methods.
- `.github/workflows/gpt-b-qualified-read-contract.yml` runs all **31**
  methods on Linux/Windows × Python 3.11/3.12/3.13, pins Math
  `9e6acbd9e12a91189f57234828e31640983af553`, builds the actual
  candidate wheel, and imports it in `python -I` with exact metadata
  version `0.2.0.dev0`. Until exact-HEAD jobs complete, none of these
  authored test counts is a PASS claim.

## B / C / D / E dependencies before activation

1. **C**: independently prove canonical source-generated `market_data`
   producer rows in isolated PG18, guarded read role and
   `lab-postgres-custody.v1` role/trigger receipt. A role/trigger
   immutability witness is **not** a transactional single-writer fence;
   current INSERT-only role still permits two writer sessions to INSERT.
   Owner-enforced monotone generation/fencing on **each** write is required
   before a live collector can start.
2. **D**: use exact v2 route/DTO in the managed `MarketDataReadClient`,
   preserve v1.1 separately (no fallback/downgrade), validate rows again via
   canonical Math, show only provisional chart/receipt. New v2 client work
   exists in Terminan draft #126, but the D cross-repository CI must be
   repinned to the **current** B SHA and green on its exact D head.
   `PARTIAL` is not an authorization to run paper strategies.
3. **E**: Root owns the one Consul session authority, native service/port,
   release manifest and process quiescence proof. E's protected entrypoint
   selection must be a separately reviewed explicit source re-anchor to
   `market_data_v2.read_api`, **never** an implicit alias. It must reject
   old v1 listener, legacy Grid worker/Bybit REST and writer activity,
   UNKNOWN process state, stolen/reused incarnation and C's missing
   DB-side writer fence before starting any new producer.
4. **B**: continuous WS/trades/L2/ticker/OI/funding migration remains
   unadmitted. Existing bounded `market_data.collector`,
   `orderbook_stream`, `ticker_acquisition` and legacy
   `grid/worker.py` must not be simultaneously activated. No unique
   preexisting behavior is removed before parity, crash/reconnect,
   backfill and exact-head CI evidence.

The published v2 synthetic/inert contract **does not** prove physical
PostgreSQL 18, six-node service exclusion, current Bybit origin, continuous
collector, market completeness, source-wheel bootstrap or any production
readiness. No existing user DB, services, market data, real trades,
Claude/Codex, main branch or native release configuration were modified.
