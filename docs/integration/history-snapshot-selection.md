# Read-only historical snapshot selection

`grid.history_snapshot.select_snapshot(connection, selection, catalog)` selects
venue, market, instrument, [start_ms,end_ms) and an immutable snapshot ID.
The catalog is provisioned independently by the source owner. Each entry binds
the request (including as-of policy), ordered revision pins, receipt trust,
dataset ID and snapshot fingerprint; its canonical SHA256 is the snapshot ID.
Caller input cannot replace the catalog or supply a new trust policy.

Selection validates the catalog hash and exact identity before SQL. The existing
reader uses repeatable-read/read-only, bounded rows/bytes, statement/lock timeouts
and parameters, with an explicit fingerprint ANY filter. Additional revisions in
PostgreSQL do not silently displace the snapshot. Missing/conflicting rows fail.
The caller supplies a fresh dedicated connection and must roll back and close it.
This API does not connect to production or create/alter roles, schemas or data.

Example selection fields: schema=`grid.history.selection.v1`, snapshot_id=<catalog
entry SHA256>, venue=`bybit`, market_type=`linear`, symbol=`BTCUSDT`, start_ms=0,
end_ms=4800000. Entry fields are `request`, `trust`, `revisions`, `dataset_id`,
`dataset_fingerprint`; tests/test_history_snapshot.py contains a synthetic example.

Event time, actual source-event range, first availability, watermark, source
revision, receipt pins, units, dataset ID and as-of fingerprint are unchanged.
Grid performs no formulas, fitting, forecasting, statistics or OOS accounting.
Real data remains blocked until independently authenticated per-revision receipts
and availability/completeness evidence are provisioned and reviewed.
