# Grid → Math → Strattester: source audit and proposed design

Date: 2026-10-30. Status: DESIGN FOR REVIEW; implementation and numerical parity NOT_RUN.

## Verified source pins

- Strattester PR63: 62fe967cf7b2358cf8dd7035218db566e566a603.
- Grid PR249: bf9f108b6777085d6725675eac778d61ec55f42b.
- Math PR97 reference: b92cd96ab5a8cab048524b311f565f4fe1937b1f (proposed implementation base; not supplied by the user).

The first two pins match current remote PR heads. All three were checked out detached in separate task-local clones; status is clean. No source branches changed. Grid issue250 explicitly retains operational ingestion and safety.

## Confirmed source findings

1. Strattester docs/contracts/central_math_engine_v1_draft.md is a contract proposal, not an implemented caller.
2. Math src/math-engine-server.mjs: evaluateMathRequest accepts only schema, mode, authority and closes; output declares CALLER_SUPPLIED_UNATTESTED. It returns window metrics, not per-origin replay forecasts, and has no dataset or exact-code binding. Reusing this response as qualified backtest input would be incorrect.
3. Grid grid/provenance_gateway.py: read_snapshot checks row digests, symbol, minute bounds, duplicate revisions and epochs. Coverage uses returned minimum/maximum, not requested endpoints. Historical freshness is judged against wall clock. Complete exchange provenance remains PARTIAL; a matching hash cannot upgrade it.
4. Grid grid/timeseries_research.py: acf uses full-input mean and denominator; rolling_volatility uses expanding warmup and population variance. They are equivalent only with those conventions retained. Passing a future-inclusive array to acf or pair_error_correction is not causal feature generation.
5. Grid grid/stochastic_research.py: quadratic_variation silently filters nonpositive prices, joining formerly nonadjacent samples. Strict admission must reject invalid prices before legacy parity invocation. Spectral bands use cycles/sample [0,.5], not physical Hz; Nyquist has a special inclusion rule.
6. Grid grid/nonlinear_research.py: walk_forward_analog uses prefix history; neighbor exclusion is strict last_index-t > max(theiler,horizon), with inverse-distance epsilon 1e-12. Preserve boundaries, ordering and ties in a parity port. This alone does not prove available-at causality.
7. Grid grid/conditional_markov.py sorts events but global buckets can connect adjacent states from different symbols. EventConditionedMarkov.fit accumulates on repeated calls and accepts labels without availability cutoffs. These require explicit fit lifecycle, entity and label-time contracts; do not silently change semantics in a parity port.
8. Grid grid/strategy_statistics.py uses seeded Python random and subtracts fees/slippage, not funding. A JS PRNG replacement does not produce identical seeded samples. Share explicit resample indices for parity.
9. Grid grid/barrier_simulator.py validates OHLC and applies stop-first same-bar resolution, fees and slippage. It has no funding argument; load_forward_candles uses ts >= event_ts, requiring proof that the chosen bar is after actual signal availability. Existing code is not a qualified integrated backtest.

These are source observations and risks, not executed exploit reproductions or exhaustive audit closure.

## Ownership and migration map

| Component | Current dependency / consumer evidence | Destination and gate |
|---|---|---|
| Exchange ingestion, normalization, candle/footprint integrity | storage, provenance, source gateway | Grid; preserve all integrity enforcement |
| timeseries: acf, difference, volatility, correlations, pair proxy | scientific_discovery imports volatility_regime | Math pure kernels, preserve warmup/null and population conventions |
| stochastic: ACF, arrival diagnostics, Markov matrix, spectrum, variation | scientific_discovery imports ACF/variation | Math; explicit units and invalid-input policy |
| nonlinear analog forecasts | pure module; full external consumer census pending | Math; prefix and neighbor parity |
| conditional / event-conditioned Markov | historical_variant_engine → ConditionalMarkov → MarkovRegimeModel | Math fit/predict, freeze train state and learned vocabulary |
| strategy_statistics | historical_experiment_runner | Math bootstrap kernels; shared indices, exact quantiles |
| scientific_simulation | scientific_simulation_gate writes run/trade state | Math numerical kernels; Strattester simulation lifecycle; preserve Grid gate |
| barrier_simulator | historical_experiment_runner; contains SQL reader | Split numerical outcome policy from Grid data reader and Strattester replay |
| book_tape_research | stateful per-symbol observations | Math numerical feature transforms; Grid event admission; preserve proxy label |
| unified_features / features / regimes | storage → UnifiedFeatureBuilder; retention and consumer watermarks | Decompose; never move DB writes/watermarks as pure math |
| position_sizing_research | full operational consumer census pending | Research sizing candidate only; execution/risk enforcement stays Grid |

Import search is initial dependency evidence; dynamic imports, CLI paths, tests and external consumers still need closure. No algorithm is approved for deletion.

## Approaches

A (recommended, not yet user-selected): source-owned read-only Grid adapter, pure Math kernels, Strattester pinned local compute client and simulator. Preserves source schema ownership and avoids copied research math.

B: direct Strattester PostgreSQL reader. Less transport plumbing, but duplicates Grid schema/provenance knowledge and increases drift risk. Still needs a separately supplied read-only connection and independent source admission.

Do not implement a duplicated numerical library in Strattester or infer provenance from a compute service claim.

## Proposed versioned contracts

New opt-in schemas grid.history.v1, math.history.request.v1, math.history.result.v1 and strattester.terminan.result.v1; existing v1.1 provenance and Math v1 endpoints remain unchanged. Exact schema compatibility is checked, not guessed.

Grid snapshot request: source-owned immutable table/view only, explicit venue/market/instrument/timeframe, [start_ms,end_ms), as_of_ms, bounded row/byte counts. Read-only repeatable-read transaction, parameterized fixed SQL, statement timeout; no bootstrap, migration or DDL imports. No DB connection in this task unless separately supplied/authorized. Use fake cursor tests initially; disposable DB qualification remains separate.

Snapshot rows: event_start_ms, event_end_ms_exclusive, available_at_ms, immutable revision and OHLCV. UTC integer milliseconds, base volume and quote/base prices, explicit instrument multiplier. Require exact requested endpoint coverage and ordered unique bars, closed events, watermark, consistent identity/epoch/revision, finite valid OHLCV and source-owned units. Reject unknown availability rather than substituting ingestion or event time. Availability is earliest time this immutable revision was knowable, not time of later export. Preserve historical-footprint/aggregate labels; never infer L2.

Fingerprint: canonical versioned bytes covering identity, row revisions, units, requested bounds, availability and ordered rows. Independent expected fingerprint and authenticated source receipt pins are provisioned outside input. Hash integrity and authenticated exchange completeness are separate gates. Unattested fixture runs remain SYNTHETIC, not qualified historical runs. No synthetic fallback after source failure.

Math request: admitted snapshot digest; explicit kernel and parameters; dependency/availability interval; train/validation/test cutoffs; seed and resource caps; expected Math source commit/tree and kernel manifest hash. Return matching request digest, exact implementation manifest, per-origin values and validity flags. Strattester launches a pinned local checkout after independently checking Git tree, tracked bytes and runtime/dependency manifest; do not trust an HTTP self-reported SHA. A remote service requires an independently authenticated deployment identity contract and remains out of initial scope.

Replay: Math owns all portable transforms/fitting/prediction. Strattester owns position/cash ledger and execution policy. Freeze selection on validation; never select using test labels. Purge labels overlapping the next split and account for horizon/availability; embargo is explicit. Feature availability <= decision time; fills occur only at the first executable bar after decision and explicit latency. Costs use fill notional on each side, adverse slippage and signed funding settlements for held positions. Missing funding is UNAVAILABLE unless instrument policy explicitly establishes not-applicable. Same-bar barriers use documented conservative policy. No hidden zero-cost defaults.

Terminan result: run/request/receipt digests, schema, source admission and synthetic labels, dataset/Math/strategy pins, split intervals, cost policy, equity and fills with UTC time/units, metric definition and nullable undefined ratios, warnings and failure states. Net PnL reconciles gross minus fees/slippage/funding under explicit sign conventions. training_candidate status requires provenance, chronology and completed OOS receipts; training_authorized=false, execution_authority=false, trading_authorized=false always. Training candidate status never starts training automatically.

## Validation and acceptance

For each port: immutable identical fixture inputs from pinned Grid, expected source outputs and Math outputs; shape/labels/counts exact. Proposed float bound abs(a-b) <= 1e-12 + 1e-10*max(abs(a),abs(b)); justify separate accumulated/spectral bounds before acceptance. Undefined/empty/warmup semantics exact. Different PRNG streams are not parity; use fixed resampling indices. Numerical equivalence is not forward-error or predictive-quality proof.

Negative controls: empty/gapped/duplicated/incomplete bars; wrong venue/market/symbol/units; missing availability; future feature/label revisions; train/test vocabulary leakage; forged/rehashed source; altered Math checkout/manifest; unavailable/timeout/oversized/malformed compute; nonfinite/zero prices and returns; constant prices with costs; no-trade and zero-variance ratios; negative funding and held-position settlement; exact reproducibility and request/result binding. Mutate future test data and assert unchanged earlier predictions/selection. No random train/test shuffle.

Separate Draft PRs from exact bases, final head/tree/parent and source-ref preservation receipts. CI must exercise actual pinned Math code and Grid reference fixtures, emit machine-readable results and artifacts bound to final head/run/job. Pending, failed or zero-artifact CI remains BLOCKED. No deletion until numerical/temporal parity, all consumer migration and independent review.

## Current status

Source audit: INITIAL, source-level only. Implementation/backtest/parity: NOT_RUN. Authenticated source completeness: BLOCKED. Physical PostgreSQL E2E: NOT_RUN. Hosted integration CI: NOT_RUN. Production/trading admission: NO_GO. No orders, production writes, deployment, G1 Execute/Cleanup or merge performed.


## Implemented first stage

Grid: grid/history_export.py exports provenance_minutes through caller-owned
read-only repeatable-read connection, with independent per-revision receipt pins.
Missing real availability/completeness evidence is an error, never substituted.
Math: python/history_{timeseries,nonlinear,stochastic,statistics,sizing}.py retain
Grid reference semantics; all legacy Grid implementations and consumers remain.
The worker exposes analog forecast and price-difference population volatility.
Strattester: research/grid_math_history.py runs only pinned Git blobs in an isolated
stdlib Python process. Runtime executable is separately pinned; OS/stdlib trust
is assumed, not independently attested. Max 2000 bars/calls, 120 seconds per client,
5 seconds per call, 256 KiB input and 32 KiB output defaults. Not an OS sandbox.
Replay uses one-bar nonoverlapping positions, validation-only analog/flat selection,
and strictly prefix-only compute inputs. Fee and slippage debit each side's notional;
slippage is not embedded in fills. Funding requires an explicit settlement schedule:
positive rate means long pays and short receives, at provided mark price in USDT,
while position is held on [entry_ms,exit_ms). Spot can explicitly opt out.
OOS label rows are evaluation/training-review candidates, with training authority
always false. Terminan envelope includes diagnostic split curves and separate OOS
metrics, immutable source pins, implementation manifest, fills and receipt.

This stage is synthetic qualification, not authenticated historical-source acceptance.
No source algorithms were deleted; external consumer census and rollback qualification
remain prerequisites for deletion. Markov, book/tape and scientific policy decomposition
remain future migration work. No services, orders, production DB, G1, merge or deployment.
