# Existing book capability correction — 2026-11-07

Base7a19ab40c30efef431bb16f0ddc91960608bf597,
treee7adbc40562e962ae529d157eebeacd550c5b7f6. Separate Agent3 branch/worktree;
PR265/142CI and Root-owned statistics paths remain unchanged.

The collector previously emitted usable book quality for empty-sided snapshots
and deltas. The feature builder admitted any selected database row as an available
book, regardless of feed quality or level completeness, and exposed its metrics.

Correction in existing fields only:

- Empty-sided book invalidates the current sequence epoch, clears both sides and
  derived velocity/wall baselines, marks existing qualityMISSING, and publishes
  no invented book prices or market-data event. Later deltas cannot restore that
  epoch; a fresh valid snapshot is needed. Existing replay/gap rules stay intact.
- Builder requires explicit existing `_quality.feeds.orderbook.status=available`,
  valid nonempty uncrossed sides and finite usable summary metrics. Boolean level
  scalars are rejected locally before the shared float parser. Unavailable rows
  yield orderbook=false and null book_imbalance/spread/bid_depth/ask_depth.
- ROOT explicitly approved strict legacy quality-absent=>unavailable semantics.
  The one authorized old positive fixture now supplies existing producer quality
  and complete sides. Its old assertions remain intact; no test was discarded.

No new schema/wire, source identity assertion, financial-unit profile, L3/raw
ordered history, timestamp authority, provider admission or execution is added.
Capability here is a current analytical feature prerequisite, not history proof.

Evidence: initial25 tests24RED/1validPASS; focused review found boolean price/qty
conversion, reproduced3RED/1already-crossedPASS, corrected locally. New29+old11
focused tests40PASS/0skip. Broader source-bound regression evidence is recorded
separately in the handoff; actual disposablePG/source durability is NOT_RUN when
explicit PG18 is absent. Fakes only, no real websocket or DB connection.

## Residual temporal quality limitation — not closed by this narrow fix

On invalidation the collector clears in-memory state but does not persist a new
availability observation. The last stored valid snapshot can remain selected
within the existing micro_max_age_s window (default5seconds). Strict rejection of
stored missing quality does not prove immediate propagation of a later gap.
Adding quality-only rows under orderbook_snapshot could affect scientific router/
plugins that currently consume that kind without a quality gate. ROOT must choose
and allocate that contract/consumer work before extension. No synthetic invalid
event, zero liquidity or stale replacement price is emitted to disguise this gap.

Current fix is limited to empty/malformed selected inputs and explicit-quality
gating. It must not be reported as complete end-to-end failclosed gap capability,
live-feed, Windows service, native or physical acceptance. Rollback restores only
this narrow code/test/doc diff, without data migration or deletion.
