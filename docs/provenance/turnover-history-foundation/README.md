# Declared turnover history foundation

This scoped pure change preserves actual executed-trade quote notional instead
of trying to reconstruct it from OHLC, rounded footprint prices, POC or VWAP.
It does not activate a producer/writer, endpoint, database, catalog or consumer.

## Audited source flow and gaps

At Data622, FootprintBuilder.add retained raw Decimal price/quantity but had no
quote accumulator; pop_closed omitted turnover. provenance.minute_record fixed
its candle to nine fields and omitted turnover. history_export projected OHLC
plus base volume; v1.1 added clocks/receipt hashes but still had no quote amount.
Request and receipt units required exactly price+volume. history_snapshot._candle
also sums volume only, so the old rollup path would lose a new quote field.

A full source search found no non-test call sites for FootprintBuilder or
persist_minute. The active PublicTradeCollector captures raw frames rather than
wiring this minute pipeline. Existing market_backfill.store_kline_page writes
provider turnover to ohlcv_1m, allowing absent turnover as None; it is a separate
unproven lineage and is not used to repair this historical record path.

## Implemented boundary

FootprintBuilder stages Math.wall_notional(actual unrounded price,quantity) and
Math.exact_sum(previous quote amount,notional), along with existing numeric
updates, before any bucket, seen-ID, counter or OHLC mutation. Duplicate or late
trades add no amount. Finalization publishes finite binary64 turnover and a fixed
executed-trade basis. Conversion of a nonzero amount to zero or overflow refuses;
existing all-eligible-buckets preparation prevents an earlier unreturned minute
from being discarded when a later amount cannot be represented.

The exact accumulator stays Decimal inside the producer. JSON history is an
explicit finite binary64 presentation, as in the existing historical numeric DTO;
no precision recovery or exact provider-byte authentication is implied.

minute_record_v12 requires explicit units and available_at_ms. A new API1.2
record retains candle.turnover, a literal quote currency, declared availability,
fixed basis/encoding qualifiers and false authority. It shares existing source
and aggregate validation with legacy minute_record. The old API1.1 factory keeps
its previous fields and canonical bytes for identical legacy inputs. It does
not upgrade old records. The existing persist_minute body remains the old writer;
its raw-row content_id digest includes whatever row it receives, so it must not
be treated as a newly qualified turnover writer merely because the builder now
emits extra fields.

export_records_v12 requires new request/trust/receipt versions and API1.2 minute
records. Quote units must agree across record, request and receipt; receipt
availability must equal the explicit record declaration. Watermark cannot follow
availability. Exact record revisions and receipt pins are required; unrelated
extra receipts or duplicate revisions refuse. No missing turnover, unit, clock
or version is filled, inferred or silently promoted.

Both old and new exports use the same coverage/source/receipt core, timed-row
projection and dataset-content core. The old v1 and v1.1 fixtures retain their
captured canonical hashes (SOURCE.json). New dataset content uses v1.2 and binds
actual turnover, units, explicit clocks, qualifiers and new receipt/revision pins.
Changing request as-of policy changes the full fingerprint while immutable
content identity stays stable. A new version/quote/availability necessarily needs
new immutable revisions, external receipts, dataset IDs and catalog pins.

## Consumers and deliberately held gates

No stored record was opened or rewritten and no DDL was added. A future versioned
writer must qualify storage keys and append-only behavior separately; the old
reader counts multiple revisions at one minute as ambiguous. Catalog selection
currently calls export_records_v11, provenance_gateway accepts exact API1.1, and
all old rollups omit turnover. Term analytics.market_history requires exactly
13 v1.1 row fields and two units; its level paths accept only old rollup families.
These consumers need explicit later versioned updates before any endpoint switch.
Raw capture-to-minute lineage, genuine receipts, availability/PIT and overall
historical source qualification remain held. A synthetic projection test merely
shows that the new rows can supply the existing Math volatility eight-field ABI;
it does not qualify that held consumer pipeline.

Old fixtures expect a nine-field minute candle, nine-field v1 rows and13-field
v1.1 rows, with two-unit request/receipt maps. New minute candles add turnover,
and v1.2 timed rows have14 fields with three-unit declarations. Existing
Footprint lifecycle expectations (event-time OHLC, dedup, late refusal, Decimal
context and atomic finalization) remain covered; existing export/snapshot tests
use fake connections only. No database/network/thread/native/provider tests run.

The scoped tests deny Thread.start and _thread.start_new_thread, process/socket/
ctypes/SQLite operations, driver imports and writes. Receipts report only scoped
passes, including old export byte goldens. Legacy obligations remain547 declared
test functions /516 remaining, zero deduction; old consumers are retained and
overall release remains NO_GO.

## Unpublished literal-admission followup

Independent review found a resealed boolean start accepted as integer0 and a
foreign metaclass equality callback in literal type-membership checks. The new
v1.2 record preflight now checks every record clock by exact int identity and
validates minute/source/ingestion clock relationships. Literal scalar/container
branches and numeric handoff use only type identity before refusal. Future
nested evidence receives the same preflight. Legacy v1/v1.1 behavior and byte
goldens remain unchanged.

A separate P1 gate remains RED: positive base volume with zero quote turnover is
currently accepted. Data must not implement this numerical relation itself. The
Math-owned executed-notional consistency predicate is pending; publication is
HELD until that actual owner function is available and independently qualified.
The scoped37-test pass for these literal fixes does not close that third gate.

Follow-up consistency fix uses public Math `9ed369ddd41ae32c4b3a9434f0b29d6dcf51154f` (`executed_notional_consistent`) on the actual literal turnover and Math-owned total volume. This checks finite nonnegative zero/nonzero agreement only; it does not establish quantity/source authenticity or OHLC bounds. The prior 853 candidate RED is retained in external receipts. Mandatory canonical coverage retains all original 791 node IDs in order and appends all 30 new unittest method IDs (821 total). Installed custody now requires 47 Data + 3 Math payload files. Legacy declared inventory 547/516 remains unchanged.

Trade-snapshot follow-up: builder admission now requires the exact canonical public `Trade` DTO and snapshots all symbol/time/microsecond/id/side/price/quantity fields before its first Math call. It uses only these locals afterward. Canonical `Trade` constructor conversions remain the numeric-input admission owner; all existing Data builder callers and Root SDK fixture callers already use it. Postconstruction invalid fields and duck records now refuse before numeric callbacks. Three further regressions bring new mandatory cases to33 and total canonical roster824; all previous821 identities retain order. Both runtimes also execute all five unchanged lifecycle function ASTs with a minimal raises fixture; no pytest/native gate widening.
