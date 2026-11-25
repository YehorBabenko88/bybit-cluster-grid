# Market Data

Canonical `market_data` package and `market-data` service, temporarily hosted in the Strattester repository. This candidate consolidates public market acquisition, immutable historical read APIs and bounded original-payload capture. No strategy simulation or domain numerical model is shipped.

Commands: `market-data serve`, `market-data capture --symbol BTCUSDT --database <dedicated-db> --source-revision <exact-SHA>`, and `market-data backfill --symbols BTCUSDT --database <prepared-dedicated-db>`. Connection strings are read only from `MARKET_DATA_DSN` (read API) and `MARKET_DATA_INGEST_DSN` (writer); do not put credentials in command arguments. No source databases or services are opened during package import.

Capture is a bounded unauthenticated public-provider observation, at most four application frames per run, not a qualified continuous live feed. It preserves original bytes before validation, requires a successful subscription acknowledgement, commits local readback before continuing, stops on uncertain storage and retains coverage UNKNOWN. Unified must independently authorize and supervise any operational invocation.

The read API uses loopback `MARKET_DATA_PORT` (default 18766), `MARKET_DATA_PINNED_HISTORY_CATALOG`, and canonical `market_data.*` wire identities. Public source authenticity and historical completeness are not inferred from checksums. Original legacy receipt hashes are never rewritten.

Historical frozen SQLite snapshots can be read with `market_data.sqlite_history.HistoricalMarketReader.open_snapshot`; no writer/bootstrap is included in that reader. WAL/live files require an independently prepared checkpointed backup first.

See `docs/market-data-consolidation.md` for old→new mappings, retained unique source and incomplete release gates. Release remains **NO_GO**. Legacy source trees remain explicit migration sources while their unique features are transferred; neither legacy package is part of this wheel/sdist. No Git refs, real stores or repositories were deleted.
