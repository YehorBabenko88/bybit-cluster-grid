# Retired instrument history preservation

This narrow safeguard disables automatic physical deletion in the existing
`grid.instrument_lifecycle.purge_retired(pool, grace_days=30)` compatibility hook.
It remains async, returns an empty list, and makes no database calls for either
default or custom grace periods. Instrument discovery, retirement, reconciliation
and stopping retired backfill retain their previous behavior. No reenable flag,
replacement cleaner, schema change or new retention mechanism is introduced.

Previously, a retired instrument older than 30 days with no queued/running
strategy job could cause five market-table deletes followed by registry deletion.
The ACTIVE coordinator refresh loop called this automatically after discovery.
The check did not establish approved retention, transitive dependency/pin safety,
verified surviving replicas, last-copy protection or deletion audit. A new runtime
defaults to INFRA_ONLY; this was not an unconditional purge on every fresh start.

Before implementation, the original module blob was verified identical between
audit HEAD `d537d525296ef34f727996e240ae6c60102c6082` and fix base
`a17f1db6b9aa04c105d2e993496026a83849ecfd`:
`74d462ee6865ec88ed72749b3c87803bb00ff7b5`.

`tests/test_retired_history_preservation.py` exercises the real function against
an in-memory history fixture and a database pool whose acquire raises. All four
cases failed on the original source: history was cleared or a DB connection was
requested. The safeguard makes those cases pass. Tests never connect to a DB.
The earlier isolated six-DELETE fake trace remains separate original evidence;
it is not evidence that production data was deleted.

Retired history now accumulates instead of being automatically purged. Disk
pressure must use nondeleting pause/throttle/admission denial and explicit status.
Future physical deletion belongs to a separately approved Storage retention policy
with dependency/pin, replica/last-copy, fencing and audit protections. Do not
reactivate deletion through grace_days or an environment toggle. Deployment,
production storage qualification and the broader ingestion lifecycle are separate
gates; this change performs no real deletion or physical operation.
