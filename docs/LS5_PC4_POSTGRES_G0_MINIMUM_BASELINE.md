# LS5/PC4 PostgreSQL 18 — minimum G0 baseline, physical G1 blocked

Reviewed source: PR240 `7066c99fb6064d1454f7cfc07e24e44da1766735` (input), PR244 `1d06bf8104c25642133ae76de9996eb098514e59`, PR245 `0892a1c850787d024a782ff3e44286c191529232`; PostgreSQL contracts PR227 `da69209af86567232fb3038a899580fe2e061a0b`, PR229 `62e3e180da35fc8d6eb6c11ec1f0bf2d04f93cd7`, PR230 `bb224dc73bcac71aba2807b4ca85a9adca314b3d`.

**No host or database access is authorized by this document.** This is the evidence contract for a separately approved least-privileged read-only G0 observer, not an instruction to execute on LS5 now.

## Exact read-only inventory requirements

1. Independently identify LS5 and PC4 host, OS, observation UTC, observer identity and permission scope. Never include credentials, full DSNs, environment dumps, process command-line arguments, raw PGDATA or unredacted connection strings.
2. On LS5 identify PostgreSQL service name/state, service process PID and executable binary identity, bound local TCP port(s), PGDATA path and filesystem owner/ACL of every path ancestor, disk free space and filesystem identity. Treat any unknown service/path/ACL as BLOCKED.
3. **Only if separately approved SELECT-only PostgreSQL access is available:** record PostgreSQL server_version_num, system_identifier from `pg_catalog.pg_control_system()` if privileges permit, current_database, session_user/current_user, database OIDs/names/owners/ACLs, role OIDs/names/LOGIN/CREATEDB/CREATEROLE/SUPERUSER/REPLICATION/BYPASSRLS and membership, schema owners and relevant grants. Avoid printing connection details or passwords. No read-only role should be elevated just to collect this inventory.
4. Observe WAL/backup/archive configuration and custody **without invoking** `CHECKPOINT`, `pg_switch_wal`, `pg_backup_start`, `pg_dump`, `pg_basebackup`, `VACUUM`, DDL, ALTER ROLE, or service commands. A read-only query can still create logs; owner must approve that side effect.
5. Identify PC4 Worker identity and prove it has no direct owner/admin PostgreSQL credentials, no superuser/DDL privilege, and no ability to select a production DSN through inherited environment or fallback configuration. Unknown is BLOCKED.
6. Create a signed/independently stored redacted evidence manifest: source exact HEAD, observation run ID/attempt, UTC, individual SHA256, host identity, query version, source of each claim, unknowns and explicit `physical=0/10 NOT_RUN`. Compare with a separately approved later snapshot to detect changes; matching hashes alone do not authenticate the observer.

## PASS / FAIL / BLOCKED

- **G0 inventory COMPLETE**: every approved read-only field observed from the right host/cluster with independent custody and no mutations; this is not G1 approval.
- **FAIL / NO-GO**: known production DSN selected by test worker, owner/admin privilege exposed to PC4, unknown or changed cluster identity after attestation, unexpected database/role/WAL mutation, unowned cleanup target.
- **BLOCKED**: missing authorized read-only credentials, unknown service/cluster identity, incomplete ACL, unverified WAL/backup, unverifiable observer, or any absent evidence. Never interpret inability to read as absence.
- **STOP** immediately if any command would mutate state or reveal secrets, if service/port/cluster changes during observation, or if observed data disagrees with pinned inventory. No automatic repair/rollback; G0 is observation only.

## Disposable G1 prerequisites

Use only a separate attested disposable PG18 cluster, unique random database and owner/app/ro roles, isolated PGDATA/port, no production DSN, exact migration 1–48 and sealed schema, effective grants (not merely `default_transaction_read_only`), owned cleanup receipts, and independent backup/restore and WAL crash recovery. Physical G1 requires its **own** explicit authorization. Even hosted `ISOLATED_E2E_PASS` cannot satisfy this authorization.

## Independent optimized password-guard regression

PR240 CI fetches the exact PR245 SHA above, checks its source guard, and runs the **actual imported async database fixture** with fake SQL recorder under `python -O`. Four invalid passwords must fail before any mutating SQL; read-only session-setting calls are recorded but not treated as DDL. This is an **offline negative test**, not a real PG18 mutation test or physical evidence. A separate real disposable PostgreSQL 18 before/after `pg_roles` and `pg_database` inventory is required for stronger integration assurance.

**POSTGRES_PHYSICAL_READINESS=BLOCKED; Physical0/10 NOT_RUN; Execute/Cleanup NOT_AUTHORIZED; Deployment NO-GO.**
