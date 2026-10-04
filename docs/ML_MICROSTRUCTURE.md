# ML microstructure capture

The live cluster keeps two separate microstructure layers so future models can be
retrained without pretending that unavailable historical tick data exists.

## Raw replay layer

Pilot workers persist replayable batches of:

- `public_trade_raw_batch`: original public-trade objects, including exchange
  trade time, taker side, price, size, trade id, block/RPI flags and cross sequence.
- `orderbook_raw_batch`: every received level-50 snapshot/delta in the batch,
  including system timestamp, receive timestamp, matching-engine `cts`, update id
  `u`, cross sequence `seq`, bids and asks.
- `orderbook_gap`: explicit continuity failures.

These records are stored in `microstructure_raw_events`. The default retention
is 30 days and deletion is still protected by the normal consumer-watermark
retention gate.

## Long-lived ML sample layer

Every analytical book snapshot also produces an `ml_microstructure_snapshot`
stored in `microstructure_samples` (default retention: 365 days). Its payload is
compatible with the StratTester live-microstructure feature contract and includes:

- bid/ask and depth at 1/5/10/25/50 levels;
- side-aware added/removed visible liquidity;
- aggressor buy/sell volume, trade count, causal large-trade volumes;
- order-book and trade sequence metadata;
- exchange/system/receive timestamps;
- reset/gap/availability and feed-quality flags.

Missing trade data is represented by `trade_available=false`; it is never silently
treated as evidence of balanced flow.

## Continuity

For Bybit order books, `seq` is monotonic but is not assumed consecutive.
Continuity is validated with update id `u`. A forward gap in `u` invalidates the
local book and forces a WebSocket reconnect so a fresh snapshot is obtained.
Stale/backward packets are discarded without corrupting an otherwise valid book.

## Safety and load control

Raw capture is pilot-only and capped by `MICRO_MAX_SYMBOLS_PER_NODE` (default 8).
Raw order-book and public-trade messages are batched before remote ingestion.
The worker WAL remains the durability boundary before CONTROL acknowledges data.
