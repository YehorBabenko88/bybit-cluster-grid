# PR245 independent PostgreSQL G0 / optimized role guard review

Reviewed exact HEADs: PR240 `cca659fd115c3d96a5073721f0f14e68b6ecf2ba` (input); PR244 `79049906cb004e324bec5ef4cc53b85381cab83a`; PR245 `0892a1c850787d024a782ff3e44286c191529232`. All observations are source/hosted-CI only. No LS5/PC4 access or physical G1 authorization.

## Unconditional role password guard

PR245 `tests/_pg18_database.py` rejects invalid secret using `if type(secret) is not str or len(secret) != 64 or any(ch not in '0123456789abcdef' for ch in secret): raise RuntimeError('PG18_INVALID_ROLE_SECRET_NO_MUTATIONS')`, immediately before `CREATE ROLE`. This is not removed by `python -O`. PR240 adds `tools/audit_pg245_guard.py` to check the exact supplied source file's AST, ordering and optimized interpreter behavior on malformed secrets. Run **only on a local read-only checkout**:

```bash
git rev-parse HEAD  # must equal 0892a1c850787d024a782ff3e44286c191529232
python /path/to/PR240/tools/audit_pg245_guard.py tests/_pg18_database.py
```

The checker tests the **extracted guard expression**, not the full database fixture. It does **not** prove zero SQL mutations. To establish that, Codex must run the actual async fixture with an attested disposable PG18 and an instrumented SQL recorder under `python -O`, inject malformed secret before role creation, verify no `CREATE ROLE`, `CREATE DATABASE`, `DROP`, `GRANT` or `REVOKE`, and compare `pg_roles` and `pg_database` before/after. A session-local `SET default_transaction_read_only=off` occurs before the secret guard; this does not itself create objects, but its position should be evaluated for strict no-SQL-before-validation semantics.

## Cluster identity and cleanup

The fixture calls `attest()` before opening a connection, then checks `pg_control_system().system_identifier` and exact PG18 version. Cleanup re-attests the provider and cluster, refuses live/unknown children, and drops only names it recorded creating. These are source properties; tests must reject swapped container, changed system_identifier, stale port, wrong DSN, unowned DB, interrupted create and partial role creation. In particular, a successful `CREATE ROLE` followed by a failed receipt step requires manual proof of ownership before any DROP.

`default_transaction_read_only=on` is a safety default, **not a privilege boundary**. The privileged owner/admin deliberately sets it `off`; effective role grants, schema ownership, PUBLIC privileges, TEMP/CREATE, inheritance, SECURITY DEFINER and `SET ROLE` paths must independently prevent app/PC4 worker DDL and metadata writes. Verify these with real PG18, not mocks.

## G0 physical baseline (not executed)

Read-only owner-approved LS5 inventory must record redacted host identity, PostgreSQL service identity/version, cluster system_identifier (only with separately approved DB read access), port and listener ownership, existing DB names/OIDs and role names/OIDs/grants, WAL/backup locations and custody, PGDATA ownership, disk capacity and live connection targets. Never collect passwords, full DSNs, environment dumps or SQL logs containing secrets. No `CREATE ROLE`, `CREATE DATABASE`, `pg_ctl`, `pg_dump`, migration, cleanup, ACL or service operation is authorized at G0. Compare baseline to a separately authorized post-test snapshot before claiming no production impact.

## Evidence matrix

| Domain | Current | Required to advance |
|---|---|---|
| PR245 password guard source | Source shape PASS | Optimized guard checker output + real disposable no-SQL-mutation test |
| PR245 hosted PG18 | Disposable workflow SUCCESS, DDL and first boot pending at inspection | Exact HEAD/attempt raw JUnit/receipts |
| PR244 hosted DDL | SUCCESS | Independent artifact provenance and negative privilege inventory |
| PR244 first boot | IN_PROGRESS at inspection | 26-stage raw receipts and zero BLOCKED |
| DSN / cluster | Source attestation reviewed | Independent exact cluster ID/port/role proof |
| WAL crash recovery | NOT_VERIFIED | Real disposable crash/restart and durable replay |
| Backup/restore | Partial toy-table lab | Full Grid schema+rows restored into new owned DB |
| Physical LS5 | UNKNOWN | Owner-approved G0 baseline; G1 separate authorization |

**POSTGRES_PHYSICAL_READINESS=BLOCKED.** P0: LS5 baseline, no production DSN proof, G1 authorization. P1: optimized full-fixture negative test, full Grid restore, crash WAL, worker role rights and cleanup custody. P2: RPO/RTO and retention.
