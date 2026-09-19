# Retention and safe cleanup

Cleanup is **analysis-aware**.

A row is eligible for deletion only when both are true:

1. it is older than the dataset retention period;
2. the corresponding analysis pipeline has advanced its `analysis_watermarks.analyzed_through` timestamp past that row.

This prevents age-only cleanup from deleting raw data that has never been analyzed.

## Default retention
- market_events: 7 days
- orderbook_snapshots: 14 days
- footprint_1m: 90 days
- derivatives_metrics: 365 days
- candles_1m: effectively long-term

These are defaults, not hard-coded business rules.

## Important
Analysis jobs must call `set_watermark(dataset, symbol, analyzed_through)` only after their results have been successfully committed.

## Telegram
- `/db` or `/dbsize`: database size, largest tables, row counts
- `/retention`: analysis watermark status
- `/cleanup`: run safe cleanup manually

Automatic cleanup can call the same cleanup functions on a schedule.
