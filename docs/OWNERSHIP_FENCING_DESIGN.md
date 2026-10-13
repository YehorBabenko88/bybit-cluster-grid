# R2/R1: persistence fencing without replacing Grid architecture

The existing PostgreSQL CONTROL, DB-less workers, local SegmentWAL and source-owned read-only integrations remain in place. Work is isolated in draft branches; migrations are additive and are never executed against production.

## R2 invariants and protocol

1. PostgreSQL has one ownership row per symbol. Owner is authenticated node plus a fresh worker-process session UUID. Generation strictly increases on takeover, including same-node process restart.
2. Scheduler produces desired placements, not grants. Heartbeat renews only desired ownership. A different owner/session cannot acquire until the previous DB lease expires. Lost ACK and CONTROL restart do not release a live lease early.
3. A worker requires ownership protocol 1 and expires local grants conservatively from heartbeat request start. Collector sinks capture an immutable grant at creation; a pending collector cannot be relabelled with its successor's generation.
4. WAL persists ownership metadata and a durable delivery UUID before queue admission. Retries/restart preserve both. Missing old metadata is never invented from a current grant.
5. Ingest authenticates node, locks the ownership row and validates node/session/generation/lease in the same PostgreSQL transaction as canonical, footprint, feature, derived writes and a durable delivery receipt. A final database-clock check prevents a delayed transaction from committing after expiry. Concurrent takeover waits on the row lock.
6. Stale/legacy WAL is durably quarantined, not discarded and not promoted into live statistics. The response and worker log explicitly report quarantine; only durable LIVE/QUARANTINED receipts permit local WAL ACK. Delivery-ID reuse with different bytes is an error.
7. Transaction failure does not advance in-memory feature/derived state. Stage a state copy and publish only after commit. Scientific consumers are notified after commit.

Compatibility: heartbeat adds collector_session, ownership_protocol and ownership grants. Existing source read schemas remain unchanged. Older workers receive no live grants; old WAL is quarantined. Older CONTROL cannot issue protocol-1 grants or return acceptable durable receipts. Deploying this protocol requires a coordinated release, but deployment is out of scope. Quarantined records require an explicit research/reconciliation process; no automatic merge into canonical statistics is provided.

## R1 invariants

Existing FloatingLeader drives CONTROL lifecycle. Each singleton and request binds an immutable leader epoch. PostgreSQL persistence checks owner+epoch+lease under a shared lease-row lock and checks the database clock before transaction commit. Renewal/campaign use the raw pool; every runtime service receives the fenced pool. Followers expose health but reject managing requests. Cleanup must complete before singleton restart; PR #169 is reused as a base dependency, not duplicated.

Takeover cannot pass an in-flight fenced transaction. Expired transactions roll back. Requests and singleton startup/DB operations must be bounded; cancellation and failed cleanup keep local leadership disabled. Schema bootstrap is serialized and separate from runtime effects.

## Implementation plan and verification

- R2 first: additive schema, ownership/grant service and receipts; worker immutable sinks and WAL; transactional ingest with staged analytical state. Unit tests before code for expiry, late grants, immutable WAL and receipt ACK; PostgreSQL tests for concurrent grant, same-node restart, ingest/takeover, rollback, duplicate delivery and quarantine. Adapt the existing overlap reproducer to actual granted assignments, retaining its disjointness assertion.
- Run the complete offline suite, real PostgreSQL gates in CI, and the saved Strattester/Terminan synthetic contracts. Publish R2 as a Draft PR based on #169; await exact-head CI.
- R1 second: fenced pool, request epoch binding, leader-driven singleton lifecycle; tests with two CONTROL runtimes, long transactions, DB outage, stale leader and failed cleanup. Publish a stacked Draft PR on R2; await exact-head CI and independent review.
- Report all remaining safety/availability limits. Passing CI demonstrates only the exercised invariants, not deployed production HA, physical reboot or exchange behavior.
