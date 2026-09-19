# Architecture notes

## Data philosophy
The database uses two layers:

1. **Stable analytical tables** for frequently queried fields (candles, footprints, order-book summaries, derivatives metrics).
2. **Append-only raw/extensible events** in `market_events.payload JSONB`.

This means a newly introduced Bybit field does not require an immediate destructive schema change. Unknown/new fields can be stored in JSONB first; later, if they become important, a migration promotes them to typed columns.

## Schema evolution
- Never depend on `SELECT *`.
- Inserts always name columns.
- All migrations are additive and guarded with `IF NOT EXISTS`.
- Services apply idempotent migrations on startup.
- New optional fields go into `extra JSONB` until promoted.
- Old workers continue to run when newer columns are added because existing inserts remain valid.

## Reliability
- websocket reconnect with exponential backoff + jitter
- explicit internet reachability wait
- heartbeat-based worker eviction and reassignment
- idempotent DB writes / conflict handling
- append-only raw market events for replay
- JSON structured rotating logs
- no hard dependency on any single optional market field

## Market data
Per symbol, when available:
- public trades
- order book depth
- best bid/ask + spread
- depth imbalance
- detected bid/ask walls
- open interest
- funding rate
- mark price
- index price
- basis
- footprint clusters
- candle POC / delta / aggressive volume
