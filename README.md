# Bybit Cluster Grid

Private distributed collector for Bybit linear futures/perpetual public trades.

## What a cluster means
For every time bucket (default 1 minute), executed public trades are grouped by exchange tick price.
Each price level stores aggressive Buy volume, aggressive Sell volume, total volume, delta and trade counts.
The candle POC is the price level with the largest executed volume.

This is executed trade flow, not resting order-book liquidity.

## Architecture
- **Coordinator** discovers active Bybit linear contracts and dynamically assigns symbols.
- **Workers** report CPU/RAM/disk headroom and consume their assigned publicTrade streams.
- If a node disappears or becomes overloaded, its capacity becomes zero and symbols are reassigned.
- **PostgreSQL** stores 1m OHLCV/POC plus price-level footprint data.
- Node count is dynamic; it is not hard-coded to five machines.

## Current milestone
Core coordinator, worker, resource scoring, Bybit discovery/WebSocket ingestion, footprint construction and PostgreSQL schema are implemented.
Next: Windows bootstrap/service installer, safe DB provisioning, batched WebSocket subscriptions, Telegram control, retention/partitioning, metrics and recovery tests.

## Security
Never commit .env, Telegram tokens or generated DB/grid passwords. Bootstrap generates local secrets.

## Data model
`candles_1m`: OHLC, aggressive buy/sell volume, delta, trade count, POC.
`footprint_1m`: one row per symbol/minute/price tick with buy/sell volume, delta and counts.
