# Product goal

This grid is not intended to be a permanent raw archive of every Bybit packet.

Its purpose is to produce reliable evidence for:

1. detecting transitions into high-volatility regimes;
2. detecting impulses and genuine/failed breakouts;
3. studying POC interaction specifically during volatile regimes;
4. later running simulated trades;
5. later training models that improve entry filtering and parameter selection.

## Preserve features that matter

### Volatility
- realized volatility over multiple rolling windows
- candle/range expansion
- trade-rate acceleration
- volume and turnover acceleration
- spread expansion/contraction
- book depth and depth imbalance
- OI level/change/acceleration
- liquidation events when supported
- funding/basis context

### Impulse / breakout
- prior rolling highs/lows and distance through them
- aggressive buy/sell volume and delta
- delta acceleration
- volume ratio vs baseline
- trade count/rate
- book imbalance before/during/after break
- wall appearance/removal/consumption
- OI change with price direction
- close location and rejection after break
- retest outcome

### POC
- POC price and migration
- distance price-to-POC
- POC location inside candle/range
- repeated/naked POCs
- volume around POC
- acceptance/rejection around POC
- POC interaction conditioned on volatility regime

Raw high-frequency data may be deleted only after the required derived features/results are committed and the analysis watermark advances.
