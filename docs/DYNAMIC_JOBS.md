# Dynamic instruments and strategy jobs

## Instrument lifecycle
The coordinator periodically fetches the complete paginated Trading universe.

Diff:
- NEW -> register, schedule to a capable worker, worker subscribes without process restart
- STILL TRADING -> keep/update metadata
- RETIRED -> remove from assignments; workers cancel/unsubscribe it
- RETIRED DATA -> quarantine first, then purge only after grace period and when no queued/running strategy job references it

Never immediately erase a delisted symbol. Historical data may still be needed by an active analysis or reproducibility run.

## Strategy jobs without collector restart
Collection and analysis are independent workloads.

A strategy job contains:
- strategy name/version
- parameters
- symbols
- start/end time
- status
- assigned worker
- result records

Workers poll/claim jobs using PostgreSQL `FOR UPDATE SKIP LOCKED`, allowing several agents to process a shared queue safely. Collection remains online while a strategy reads historical data.

Future coordinator scheduling should consider CPU/RAM/DB pressure before allowing a worker to claim a heavy strategy job.

## Isolation
Strategy code must have read-only access to market-data tables and write access only to strategy result/job tables. Production deployment should use a dedicated PostgreSQL role for this separation.
