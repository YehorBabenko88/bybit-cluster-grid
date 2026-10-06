# Mathematical Research Lab

Research-only layer. Nothing in this package may place orders or promote a strategy without the existing out-of-sample promotion gates.

## Pipeline

1. Normalize event-time data per instrument: trades, OI, L2 book updates, walls and volume.
2. Micro agents learn instrument-relative baselines and emit WARMUP/QUIET/EXCITED/REFRACTORY observations.
3. Attach forward outcomes at multiple horizons (1/2/5/10/30/60 s): return, MFE, MAE, realized volatility, spread/slippage and time-to-move.
4. Stochastic diagnostics test event arrivals, state transitions, covariance/memory, spectral concentration and path variation.
5. Time-series diagnostics test stationarity-oriented transforms, ACF, distributed lags, volatility regimes and pair error-correction candidates.
6. Nonlinear phase-space research searches historical analogues using delay embeddings and strict past-only walk-forward evaluation.
7. Candidate patterns must beat simple benchmarks after costs and survive time split, instrument split, regime split and multiple-testing controls.
8. Only validated candidates may be copied into the simulator. Research tables remain non-trading.

## Source-to-module map

- Loskutov/Mikhailov: delay embeddings, local analogue prediction, maps, regime transitions, coupled simple agents.
- Bekareva, Random Processes: Markov-state diagnostics, Poisson-like event-arrival diagnostics, covariance/memory, spectral diagnostics, stochastic path variation.
- Artamonov et al., Time Series: stationarity/ACF, ARMA/ARIMA benchmark concepts, state-space/regime estimation, ARCH/GARCH volatility benchmarks, distributed lags, VAR/impulse-response/Granger hypotheses, cointegration/error correction.
- Algebraic geometry: reserved for a later experimental branch only. It must first demonstrate a measurable benefit for polynomial constraints/manifold structure on microstructure state vectors; no trading feature is justified merely by geometric terminology.

## Guardrails

Correlation is not causality. Granger-style lead/lag evidence is predictive precedence, not structural causation. A fitted cointegration proxy is not proof of cointegration. Poisson/Markov/Brownian assumptions are null models to challenge, not assumptions to force on market data. Spectral peaks require stability and surrogate testing. Nonlinear embeddings require walk-forward neighbors from the past only.
