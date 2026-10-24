# LS5 PostgreSQL 18: independent readiness and recovery contract

Base PR #237 exact SHA: `e25197b169ef0e5f37b5bd0030ee4a97b13965e2`.
**No LS5 connection, SQL execution, migration, service/ACL change or deployment.**
Physical PC4 0/10 NOT_RUN; Execute NOT_AUTHORIZED; deployment NO-GO.

## Scope and current evidence

Repository requirements include `asyncpg>=0.30`; actual PostgreSQL adapter, migrations,
schema init, SQL statements, advisory lock identifiers and backup mechanisms require a
separate line-by-line source inventory. Do not infer correct behavior from the dependency.
The LS5 service reportedly runs PostgreSQL 18 on TCP/55432; `grid_pg_test` is enabled
with unconfirmed purpose; spool/logs/backups/deploy/ml-artifacts custody is unresolved.
Treat all physical configuration and permissions as **BLOCKED** until separately authorized
read-only observations. A passing synthetic test is never a physical attestation.

## Data-integrity matrix and failure criteria

| Domain | PASS evidence | FAIL | BLOCKED |
| --- | --- | --- | --- |
| Service principal and roles | SID, service account, memberships, DB roles, effective grants and least privilege independently verified | excessive privileges, unowned objects | missing live inventory |
| grid_pg_test | owner-approved purpose, login scope, expiry, grants, and audit | unapproved privileged login | purpose unknown |
| Storage ACL | owner, DACL, inheritance, reparse and parent custody for spool/logs/backups/deploy/ml-artifacts | unauthorized writer or replacer | any uninspected ancestor |
| Migrations | immutable checksummed ordering, transactional boundaries, compatibility and rollback strategy | non-idempotent or destructive replay | source/runtime mismatch |
| Transactions | rollback on cancellation, atomic commit, no half-ack, retries with unique operation IDs | duplicate or partial committed operation | untested crash window |
| Advisory locks | namespaced lock IDs, transaction vs session scope, guaranteed release and fencing | collision or stale lock acceptance | no source-level proof |
| WAL/checkpoint | version, wal_level, fsync, full_page_writes, archiving, retention and checkpoint settings | disabled durability or missing WAL chain | no observed config |
| Backup | consistent base backup/dump, manifest, checksums, WAL continuity and retention | missing segment or digest mismatch | no independent backup inventory |
| Restore | isolated PostgreSQL 18 restore, integrity queries, recovery target and measured RPO/RTO | corrupt restore or missing tables | no rehearsal |
| Shutdown/network | durable queue drain, retry and idempotent replay after disconnect | acknowledged lost write, duplicate | no fault injection |
| Disk full | ENOSPC leaves consistent state and never fabricates success | silent data loss | not tested |
| Evidence | independent JUnit, JSON, SHA256 and exact HEAD, no skips-as-pass | forged or mismatched receipt | missing artifact |

## Ordered work plan

1. **Static source audit (offline)**: identify asyncpg pools, connection settings, retry loops,
   SQL schema/migration entrypoints, transaction boundaries, advisory locks and file writers.
   Produce file:line inventory and a concrete SQL operation graph. STOP if provenance uncertain.
2. **Isolated PostgreSQL 18 laboratory**: fresh disposable DB with dedicated least-privilege
   test user; use ephemeral CI service/container only. Explicitly prohibit LS5 endpoints and
   production credentials. Assert PostgreSQL major 18, local host, unique database name.
   Test migrations twice, concurrent workers, abort/restart, advisory lock contention,
   disk-full simulation, abrupt shutdown and replay. Every case must emit JUnit and SHA256.
3. **Backup/restore rehearsal**: on isolated lab only, create a consistent backup with
   documented PostgreSQL tooling, capture checksums and WAL start/end LSN where applicable,
   restore into *another* fresh database/cluster, compare schema, row counts, constraints,
   canonical data digests, sequences and idempotency keys. Missing WAL is BLOCKED/FAIL,
   never repaired by ignoring a segment.
4. **Read-only LS5 preflight** (separately authorized): collect service identity, PostgreSQL
   version/config, roles/grants, database list, migration ledger, storage directory owners/ACLs,
   disk free, WAL/archive/checkpoint status, replication slots and backup metadata.
   Prefer SELECT/catalog views and OS read-only inspection; no pg_dump, pg_basebackup,
   CHECKPOINT, VACUUM, REINDEX, DDL or service commands under this authorization.
   Even SELECT may write audit/access logs; document these side effects.
5. **Owner approval**: review evidence with independent PostgreSQL and Windows ACL owners,
   approve any provisioning separately, reverify custody, then authorize bounded physical
   tests in a new scope. No auto-escalation.

## Authorization and STOP/rollback

Each step requires a distinct owner approval specifying host, principal, exact commands,
time window, expected side effects and evidence destination. Immediately STOP on unknown
identity, unexpected production endpoint, privilege escalation, DACL/reparse drift,
unexpected WAL or database mutation, insufficient disk, mismatched checksum, incomplete
JUnit, unknown process or recovery state. Preserve evidence; do not automatically repair
ACLs, retry migrations, delete WAL, restart services or restore production.

Offline failure rollback: discard only the known isolated disposable test database after
preserving evidence. Physical rollback is **not authorized**; prepare a reviewed restore
plan and test it offline before any separately approved physical operation.

## P0/P1/P2

- **P0**: unknown `grid_pg_test` purpose/grants; unverified writable storage ancestry;
  no verified LS5 backup/restore and WAL continuity; no proven migration/crash idempotency.
- **P1**: unverified advisory lock namespace, cancellation/shutdown semantics, pool exhaustion,
  network loss, ENOSPC and evidence custody.
- **P2**: observability gaps, RPO/RTO baselines, retention and periodic restore drill.

This document is a review plan, not proof of physical readiness.
