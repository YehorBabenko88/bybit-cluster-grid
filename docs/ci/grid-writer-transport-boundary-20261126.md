# Grid canonical market-data ownership boundary — workstream B / P0

Status: **NO_GO**. This is a source inventory and migration contract, **not** a claim
of unified runtime behavior or a successful live Bybit test. Source snapshot:
`YehorBabenko88/bybit-cluster-grid@gpt/b-market-data-roster-custody-20261126`,
baseline `bf29f81b238c6236417f0ed9a13feea3dcbb5bec`.

## Verified source-level overlaps

| Runtime area | Existing legacy Grid source | Relocated canonical source | Migration risk |
| --- | --- | --- | --- |
| Public trade WS | `grid/worker.py` (subscription at ~493–504, buckets and persisted rows at ~448–616) | `market_data/collector.py::PublicTradeCollector` / `public_connection` | Concurrent subscription and divergent persistence/provenance; no single authoritative consumer proved |
| L2 | `grid/orderbook.py::analyze_book`, `parse_book_levels` | `market_data/orderbook.py`, `market_data/orderbook_stream.py::OrderBookStream` | Keep unique analytics and exact decimal/sequence correctness; connector sharing not yet demonstrated |
| Live ticker/OI/funding | legacy Grid services and Bybit fetch paths | `market_data/ticker_acquisition.py::TickerAcquisition`, `TickerState` | Bounded WAL with uncertain-outcome refusal must survive reconnect; no 24/7 supervisor acceptance |
| REST historical | `grid/market_backfill.py` (Bybit HTTP calls and SQL writes) | `market_data/market_backfill.py` (kline, open interest, funding and ratio endpoints) | Two independent REST callers/backfill stores and rate-limit budgets remain |
| Registry / discovery | `grid/worker.py`, `grid/coordinator.py` call `grid/bybit.py::linear_symbols` | `market_data/bybit.py`, `market_data/selection_rotation.py::RankedDiscoveryPlanner` | Need one registry freshness, instrument identity and quota ownership |
| Persisted minute/footprint | `grid/storage.py` writes `candles_1m`, `footprint_1m` | `market_data/capture_store.py` writes raw `market_data_capture_v2` and `market_data_execution_v1` | These are **not** interchangeable schemas; never alias or drop the Grid tables without equivalence |

## Runtime facts and refusal boundaries

- `market_data/selection_rotation.py::AcquisitionRotationService.run` explicitly
  reports `collection_mode='BOUNDED_CAPTURE_EPOCHS_NOT_CONTINUOUS'`.
  This cannot be advertised as continuous live service.
- `market_data/orderbook_stream.py` already includes bounded reconnect and
  forced fresh snapshot/epoch behavior. Do not replace it with an unbounded
  retry loop or expose an unverified orderbook as live.
- `market_data/collector.py` and `ticker_acquisition.py` record raw
  capture before delivery and refuse uncertain storage outcomes. A shared
  transport may demultiplex validated provider frames, but **must not**
  convert failed persistence into a successful ack.
- Legacy `grid/worker.py` still opens `websockets.connect` directly; the
  relocated canonical package and Grid legacy services can currently run
  parallel collectors if both are enabled. **One transport/writer is not proved**.
- `grid/market_backfill.py` and `market_data/market_backfill.py` have
  distinct functions with similar names; only source-level overlap has been
  established, not semantic equivalence across all datasets or failures.

## Required contract before B3/B4/B5 migration

1. **Startup/stop admission:** Unified must launch exactly one Grid market-data
   owner (service identity + source SHA/wheel hash). No second Grid legacy
   worker may simultaneously own the same feed. Agent C owns lab admission
   and E owns infrastructure/service boundaries.
2. **Transport:** a single admitted Grid owner governs Bybit REST budgets
   and public WS subscription/reconnect policy. Transport selection is not
   delegated to Math, Terminan, Strattester or Meta.
3. **Data:** pin instrument identity and provider timestamps, receive clock,
   source/product/category, raw observation SHA, sequence/update ID and epoch.
   Reconnect is not continuity proof; backfill must attest gaps and dedup keys.
4. **PostgreSQL:** establish independent versioned raw capture and derived
   candle/footprint schemas, sole write principals and schema migrations;
   Unified manages PostgreSQL lifecycle, Grid alone owns data writes.
5. **Compatibility:** preserve Grid's unique aggregation/analytics by exact
   input/output fixtures; move mathematical computation to Math only with
   agent D's approved DTO/API contract.
6. **Release evidence:** malicious/deformed WS frames, duplicate/reordered
   trades, lost ping, interrupted persist, unknown ack, 403/429/5xx, restart,
   long offline gap and delisting must fail closed. Run synthetic fault matrix
   first and live public-data (no credentials/order submission) separately.
7. **Retirement:** delete or alias neither legacy implementation nor tables
   until unique functionality and exact-byte/semantic equivalence tests pass,
   an accepted single-writer consumer switch lands, and MASTER approves.

B1 roster execution / branch [PR #299](https://github.com/YehorBabenko88/bybit-cluster-grid/pull/299)
is independent of this pending runtime ownership migration. General release
remains CODE NO_GO / PRODUCTION NO_GO.
