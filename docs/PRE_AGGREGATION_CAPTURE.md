# Durable source evidence before aggregation

Public-trade messages are appended through the existing micro-event WAL before
FootprintBuilder.add or MicroTapeAggregator.add. Valid orderbook messages are
captured before applying their snapshot/delta to the book. Worker OwnedSink
retains the original session/generation. No new worker database connection,
replacement scheduler, aggregator or storage subsystem is introduced.

Capture events (`public_trade_capture_evidence`, `orderbook_capture_evidence`)
always receive QUARANTINED receipts, even with current ownership. Their complete
JSON is retained in migration47's collection_ingest_receipts. They never enter
market_events, canonical candles, footprints, features or the scientific live
router. This also avoids the market_events whole-payload unique index's large
index-row limitation. Durable receipts and SHA-256 support idempotent retry;
WAL ACK follows the same hash-verified response as other records.

An upgraded worker accepts assignments only from CONTROL advertising
capture_evidence_protocol=1. Upgrade CONTROL first. A previously unknown event
must not be sent to an old CONTROL that would consider it a live market event.
Existing ownership_protocol=1, live aggregate schemas and external scientific
package contracts remain unchanged. No migration48 is needed. The evidence
payload reuses the message/event field structure examined in older Draft #11;
its buffered raw-capture approach is not copied because buffering still leaves
a crash gap before WAL.

The sender uses /ingest/capture and requires capture_evidence_protocol=1 plus
QUARANTINED before WAL ACK. Older CONTROL returns 404 on this dedicated endpoint.
This protects startup replay before heartbeat and rollback between heartbeat and
send, which capability negotiation alone cannot protect.

Deterministic synthetic tests kill actual collector subprocesses with an open
minute/micro bucket, after append but before queue admission, and after a book
snapshot. Before the fix, open trade and book tests recovered zero source
records. PostgreSQL tests require capture evidence to be quarantined and
deduplicated, including a payload exceeding 20 KB.

Limits: a frame lost before durable append (including subscription/pre-ACK
buffers, failed fsync, invalid/unparsed data, disk-full admission) is not covered.
This is evidence preservation, not exact reconstruction or lossless statistics.
No automatic replay into live aggregates, repair of canonical statistics,
retention purge or quarantine disposal is provided. Standalone micro collectors
without the OwnedSink capture capability retain their prior behavior and need
separate validation. One fsync per frame increases disk traffic; benchmark
fleet event rates and capacity before any separately approved rollout. Existing
bounded micro WAL stops admission on pressure; CONTROL quarantine needs the
operator budget and reconciliation policy in the rollout design.
