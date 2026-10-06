# Unified Strattester -> Grid Research Lifecycle

## Goal

The complete system is a staged research platform for intraday/scalp discovery around volatile instruments, important levels and short-lived impulses. Historical research may seed priors and candidate hypotheses. Only live causal evidence may validate them for current market conditions. Simulation and later paper trading are separate promotion barriers.

## Phases

1. INFRASTRUCTURE
   - install CONTROL/agents, PostgreSQL, Tailscale, services, credentials and recovery
   - no training/paper trading
2. MARKET_HISTORY_SYNC
   - Strattester discovers/reuses/downloads historical Bybit data
   - Grid may already collect live raw data in the background
3. HISTORICAL_STRATEGY_RESEARCH
   - backtest registered strategies with causal event_time/known_at rules
   - focus: levels, SMC, POC/volume profile, volatility-conditioned impulses
4. HISTORICAL_SCIENCE_BOOTSTRAP
   - export historical-science-bootstrap.json
   - available: OHLCV/turnover, mark/index/premium, OI, funding, long/short, public-trade aggregates
   - unavailable and never fabricated: historical true L2, liquidations, true L2 absorption
   - historical scalp ontology creates causal LEVEL_APPROACH / IMPULSE_BUILDUP / BREAKOUT / REJECTION samples
5. GRID_IMPORT
   - verify bundle hash and capability mask
   - historical information is imported only as priors; never as live evidence
6. LIVE_LEARNING
   - true trade tape, OI, orderbook velocity, imbalance, cancellations, walls and spread enrich the same scalp ontology
   - scientific discovery, forward outcomes, pattern mining and independent replication run continuously
7. PAPER_TRADING
   - only hypotheses that are VALIDATED and SIMULATION_PASSED may become paper candidates
   - there is still no automatic live-order authority

## Scalp ontology

Core sequence:
LEVEL_APPROACH -> IMPULSE_BUILDUP -> BREAKOUT/REJECTION -> FOLLOW_THROUGH/FAILURE

Historical features:
- important-level distance/type
- volatility regime
- volume/turnover expansion
- public-trade delta/CVD where available
- OI/funding/long-short where historical coverage exists
- SMC structure and POC proxy/trade POC

Live enrichment:
- tape speed
- large-trade intensity
- true book imbalance
- book update/cancel velocity
- wall size/persistence/replenishment
- spread
- fresh OI/funding

A historical proxy must never populate a LIVE_ONLY feature.

## Conflict rules

- Historical/live disagreement is a regime-shift observation, not an overwrite error.
- Live observations override priors only for fields actually observed.
- A stale L2 snapshot is not mixed with a fresh trade impulse.
- One hypothesis fingerprint must use stable categorical/quantized features, not continuously changing coefficients.
- Overlapping outcomes are embargoed and cannot manufacture independent sample count.
- Historical discovery cannot directly yield VALIDATED live status.
- Scientific VALIDATED does not imply SIMULATION_PASSED.
- SIMULATION_PASSED does not imply live trading authority.
- Reboot recovery uses durable source event checkpoints; replay after checkpoint must be deterministic.
- Strattester and Grid must never concurrently write one SQLite market-data file over the network.

## Telegram

Main menu:
- Operations: fleet lifecycle, nodes, health, logs, updates, storage, repair
- Simulation: runs, PnL/expectancy/PF/DD, passed/waiting OOS, logs/results
- Science: lifecycle, historical bootstrap, candidate discoveries, replicated/validated/rejected knowledge, mining statistics and multiple-testing counts

## Historical handoff

Strattester emits:
- historical-science-bootstrap.json
- grid-handoff.json
- phase-manifest.json
- research_results.sqlite3 when present

Grid verifies bundle content/hash/capabilities and imports it separately from live scientific evidence.
