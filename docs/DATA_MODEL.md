# Data model and forward compatibility

The collector intentionally separates **canonical analytics** from **raw/extensible events**.

## Canonical analytical fields
Frequently queried values are stored in typed tables:
- candles / footprint levels
- order-book summaries
- derivatives metrics

## Extensible fields
Every analytical table has an `extra JSONB` column and generic market events use `payload JSONB`.

If Bybit adds a new field tomorrow:
1. collector can store it in JSONB immediately;
2. existing code continues using explicitly named columns;
3. later a migration can add a typed column with `ADD COLUMN IF NOT EXISTS`;
4. old workers remain compatible.

## Migration rules
- additive changes by default
- never `DROP COLUMN` during normal startup
- no positional inserts
- no `SELECT *` in application logic
- schema changes are idempotent
- nullable/defaulted new columns
- version table records applied migrations
- deploy code that tolerates both old/new schema before promoting fields

## Persistence rates
Raw 20ms order-book changes are maintained in RAM. PostgreSQL stores sampled book snapshots and significant liquidity-wall events. This avoids turning a five-node collector into an uncontrolled multi-terabyte write workload.
