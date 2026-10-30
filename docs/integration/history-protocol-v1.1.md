# Historical research protocol v1.1

Status: opt-in source/synthetic qualification. Authenticated historical dataset admission remains BLOCKED without independently provisioned owner/source receipts. No live orders, PG changes, G1, deployment or merge.

## Ownership and compatibility

Grid owns source capture, bounded READ ONLY REPEATABLE READ export and integrity.
Math owns numerical transforms/fitting/forecast kernels; Strattester owns experiment,
capital/cost/funding ledger, OOS and training lifecycle; Terminan only presents receipts.
Existing v1 APIs and all legacy Grid kernels/consumers remain. Five Math port files
remain byte-identical Git blobs to Grid bf9f108b6777085d6725675eac778d61ec55f42b.
No deletion is admitted until full consumer migration, numerical/temporal parity and rollback.

## Grid → Math/Strattester

Source API: grid.history_export_v11.export_records_v11(records, request, trust) or
read_postgres_v11(conn, request, trust). The connection is fresh, caller-owned and
read-only; the adapter does not create connections, bootstrap schemas or modify data.
The fixed parameterized query reads provenance_minutes only, max2000 rows,
8MiB aggregate/1MiB row, statement_timeout3000ms and lock_timeout1000ms.

Response schema grid.history.v1.1 preserves, per immutable revision:
- event_start_ms inclusive / event_end_ms exclusive minute boundaries;
- source_event_start_ms / source_event_end_ms actual observed exchange events,
  both inside the minute (last observed event is not evidence of exchange completeness);
- watermark_ms: exchange-event progress through which the receipt attests completeness;
- available_at_ms: first knowability of this immutable revision including completeness.

Invariant: event_end_ms <= watermark_ms <= available_at_ms <= as_of_ms.
No substitution of event or ingestion time for availability. All timestamps UTC integer
milliseconds <=2^53-1; exact window coverage, no duplicate/reordered/ambiguous revisions.
Staleness is measured at historical as_of and decisions, not against the current clock.
Units: explicit USDT/BTC price, BTC volume; venue/market/instrument/source revision/epoch
are pinned. Historical aggregates/footprints are not L2.

Each independent receipt pin binds the immutable record fingerprint, availability,
watermark, completeness, venue, units and evidence class. Missing pins/false completeness/
source mismatch deny export. Pins must be provisioned independently and authentically;
SHA256 or HISTORICAL text alone never establishes exchange identity/completeness.

Canonical JSON: Python JSON sorted keys, separators comma/colon, allow_nan=false,
UTF-8, ensure_ascii default=true. This initial numerical protocol assumes pinned Python
serialization; other-language writers must match these bytes rather than assume an
unqualified generic JSON canonicalization standard.

Stable dataset_id = SHA256 of {schema:grid.dataset.v1.1, source,
identity:{venue,market_type,symbol,units}, timeframe:1m,
representation:historical_aggregate, evidence_class, rows, source_receipts}.
As-of/max-age request changes do not change that content identity.
Snapshot dataset_fingerprint = SHA256 of complete envelope excluding only itself;
it additionally binds request/as-of/max-age policy. Both travel through Math/results.

## Versioned Math API

Opt-in transport is isolated stdio python/history_timed_worker.py, Python -I -S,
not an untrusted network endpoint. Request math.history.request.v1.1 fields:
dataset_id,dataset_fingerprint,source,market,units,rows (causal prefix only),
decision_ms,train_count,train_end_ms,max_age_ms,model_version.
Model version is exactly grid-frozen-analog-v1; unknown versions/fields are rejected.
Pure timed validation delegates to existing kernels without changing arithmetic.

Math independently checks all row clocks, units, OHLCV, provenance hash shapes,
prefix continuity and availability <= decision. Training labels/neighbors are restricted
to the prefix available by train_end_ms. Request max2000 rows/2MiB; result finite.
Response math.history.result.v1.1 includes request_digest, prefix_digest, dataset IDs,
source, model/kernel version, feature_event_end_ms, feature_available_at_ms,
watermark_ms, forecast_target_event_end_ms (one minute after feature event end),
train cutoff/count and finite forecast/volatility. source_authenticity is explicitly
NOT_EVALUATED_BY_MATH; all authority flags false.

The Strattester client independently pins Math commit/tree and Python executable,
copies exact Git blobs to an isolated temp directory and checks manifest SHA256.
No imports from a caller-controlled PYTHONPATH. Default call timeout5s, output32KiB,
experiment120s/max2000 calls. Trusted local Python/stdlib/OS is assumed, not host
attestation or an OS sandbox. Response/request/model/clock mismatch denies result.

## Replay and OOS

Training neighbors and labels freeze at cutoff. Validation chooses ANALOG vs FLAT;
test never selects a model. Causal query features can use previously observed OOS
prices. First executable bar starts at/after available decision+latency; same-entry
signals resolve to latest decision/origin, one-bar positions cannot overlap.
Full-notional collateral plus entry costs required. Cash carries across splits;
validation selection uses the same opening cash as its reported receipt. Spot is
long/flat, with no implicit borrow or leverage. Slippage is a separate debit, not
embedded in fills. Entry and exit fees use each side's notional. Positive funding
means long pays/short receives at the supplied settlement mark while held on
[entry,exit). Interval/anchor/settlement coverage are explicit; max2000 settlements.
No funding zero-fill for a missing schedule; spot opt-out is explicit.

Horizon-one training-review labels are emitted only when origin < label event end
<= label availability, within test. Already-known targets after publication delays
are excluded. OOS rows remain evaluation-only for this run; training eligibility
and training/trading/execution authority are always false.

## Terminan review handoff

Result strattester.terminan.result.v1.1 binds source request/observations/receipts,
Math manifest and timed request traces, separate split/OOS/cost receipts and equity.
review_packet(result, independently_pinned_completion_receipt) reconstructs source
admission and timed request hashes, validates train cutoff/count, units/identity,
ledger/split/equity reconciliation and candidate chronology before display.
Output terminan.history.review.v1.1 maps fills to existing Terminan TradeEvent fields:
run_id,strategy_id,symbol,trade_id,entry_ms,exit_ms,entry_price,exit_price,side(long/short),
quantity,pnl(net). Compatibility is tested against Terminan PR48
 d10d5a0e2f00fcd68e284d2b6e743f61430997c9, tree8d4025fddbcf6f6ea1c2db152404e217d0240aec.
The packet is not the live Grid contract and is not silently relabelled as it.

Producer-side render_review emits escaped, network-free HTML/SVG for models,
prices/forecasts at target event end, diagnostic cash, OOS metrics, simulated trades,
source receipts and training review. No JavaScript, remote resources, compute service,
buttons for promotion or training launcher. This is an offline integration artifact;
Terminan /math route/service has not been changed or deployed by this work.

Commands: scripts/run_history_replay.py --dataset snapshot.json --policy policy.json
--pins independently-provisioned-pins.json --math-root pinned-checkout --output new-result.json.
Pins require dataset_id,dataset_fingerprint,math_commit,math_tree,python_sha256.
Policy includes model_version plus train/validation/test, costs/funding/capital.
Legacy v1 low-level functions are retained for compatibility, not admitted by this CLI.
Display: scripts/render_history_review.py --input result.json --receipt-pin SHA256
--output new-review.html. Failure writes no success artifact.

## Additional Math graph API proposal

A separate v2.1 scientific-graph proposal was received during this task. It is not
silently substituted for this pinned historical stdio protocol. In that proposal,
availability<=timestamp can describe an output/decision sample timestamp; it cannot
replace exchange event time (which normally precedes availability). Any future
bridge must preserve event time, available time and decision/as-of as distinct
fields, bind exact model/units/source/request, and retain OOS metric availability.
USD, USDT and BTC remain distinct; no implicit currency conversion is authorized.
