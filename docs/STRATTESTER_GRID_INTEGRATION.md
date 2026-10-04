# Strattester ↔ Cluster Grid integration contract

## Ownership

Cluster Grid is the only distributed scheduler and source of truth for leases,
resource reservations, research-run state, dataset identity and promotion.
Strattester owns research algorithms and executes one explicitly assigned shard.
Its standalone scheduler remains supported, but is disabled for Grid-assigned work.

## Immutable boundary

Every distributed job is fenced by protocol version, run id, shard/job id,
job type, dataset hash, Strattester code version, config hash and input hash.
Workers return a result hash covering result, metrics and artifact descriptors.
Grid rejects stale, mismatched or mutated handoffs.

Workers must never write shared SQLite databases over the network. Inputs are
immutable/cached locally; durable control metadata and accepted summaries live
in Grid PostgreSQL. Large artifacts are content-addressed and referenced by
hash/URI rather than mutated in place.

## Priority

Live ingestion/execution and database durability outrank research. Research
uses Grid resource reservations and leases and may be retried on another node.
A worker that loses its lease cannot commit a late result.

## DAG

History sync -> feature build -> strategy shards -> aggregate -> ML dataset ->
walk-forward training -> OOS/robustness -> shadow -> simulation -> approval.

No research result can directly activate a live model. Promotion remains a
separate Grid lifecycle gate.

## Required integration tests before simulation handoff

1. Single-node reference run is deterministic.
2. Distributed result hashes match the reference workload.
3. Worker death causes lease expiry/retry without duplicate accepted results.
4. Lost ACK/replayed result is idempotent; conflicting replay is rejected.
5. Dataset/config/code/input hash mismatches fail closed.
6. PostgreSQL/CONTROL restart resumes queued work.
7. Resource pressure pauses research before live collection.
8. Future-data mutation cannot change earlier ML features.
9. Corrupt artifact/hash is rejected.
10. Only after all above pass may an artifact enter shadow/simulated trading.
