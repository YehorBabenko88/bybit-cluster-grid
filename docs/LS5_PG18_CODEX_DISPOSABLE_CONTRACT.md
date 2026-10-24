# Codex disposable PostgreSQL 18 contract — GPT-3 / PR #240

**Scope:** isolated GitHub-hosted disposable database only. This document is NOT authorization for LS5, PC4, production SQL, schema upgrade, service changes, merge or deployment. No physical host access.

## Source-verified boundaries

PR #227 exact HEAD `da69209af86567232fb3038a899580fe2e061a0b` implements the candidate DDL-free runtime. PR #230 exact HEAD `bb224dc73bcac71aba2807b4ca85a9adca314b3d` hardens privilege and acceptance checks. These are separate source snapshots and are **not integrated into PR #240**. Never mix arbitrary branch HEADs or reuse a schema seal from a different source tree.

- `grid/db.py`: `asyncpg.create_pool(settings.postgres_dsn, min_size=1, max_size=10, command_timeout=30, setup=configure_connection)`. Pool acquisition sets `search_path=pg_catalog,public`.
- `grid/schema_preparation.py`: explicit `prepare_schema(owner_pool)`; serializes with advisory lock `0x42594347`; baseline `Database.ensure_schema()`, migrations 1–48, nine supplemental schema initializers, schema seal. The default CLI invocation is **PLAN_ONLY**, no DB connection; `--execute` requires separately approved disposable DB owner context.
- `grid/schema_contract.py`: schema source digest, catalog digest, exact migration registry, migration48 index and runtime gate; `verify_runtime_schema()` enforces non-owner, no schema/database CREATE/TEMP, no elevated memberships, and read-only metadata seal/registry.
- `tests/_pg18_database.py` in PR #227: attests disposable cluster identity before creating per-run DB and roles; owner/app/ro separation, runtime DML grants; do **not** replace this with toy schema as proof of Grid integration.
- `grid/db.py` baseline market tables: `market_events`, `candles_1m`, `footprint_1m`, `orderbook_snapshots`, `derivatives_metrics`. Other instrument/collector/assignment tables must be discovered from reviewed migration source and verified with catalog introspection before fixtures. No invented table names.

## Disposable service for PR #240's **standalone toy-table** probes

Only in an isolated CI job with Docker and GitHub-hosted runner:

```yaml
services:
  postgres:
    image: postgres:18
    env:
      POSTGRES_DB: grid_ci_disposable
      POSTGRES_USER: grid_ci
      POSTGRES_PASSWORD: ci_only_disposable
    ports:
      - 55439:5432
    options: >-
      --health-cmd "pg_isready -U grid_ci -d grid_ci_disposable"
      --health-interval 5s --health-timeout 3s --health-retries 10
```

```text
GRID_DISPOSABLE_PG18=YES
GRID_DISPOSABLE_PG_DSN=postgresql://grid_ci:ci_only_disposable@127.0.0.1:55439/grid_ci_disposable
GITHUB_ACTIONS=true
PGHOST=127.0.0.1
PGPORT=55439
PGUSER=grid_ci
PGDATABASE=grid_ci_disposable
```

The fixed credential above is for the disposable CI service **only**. Do not use it on real hosts, share a production DSN, or expose it in evidence. Container-side `inet_server_port()` is 5432, host-side connection port is 55439. `GRID_DISPOSABLE_PG18` alone is **not** proof of isolation; attest server version, exact host/port/database, disposable cluster identity and runner custody before any CREATE/ALTER/DROP. The existing standalone tests check version and fixed DSN, but do not yet provide the full PR #227 attestation.

```bash
python -m pip install 'psycopg[binary]==3.2.10' 'pytest==8.3.5'
python -m pytest -q tests/test_ls5_pg18_disposable.py tests/test_ls5_pg18_restore.py --junitxml=pg18-junit.xml
```

Only run this command on an **attested isolated runner**; never locally against an unknown database. The tests include disposable toy-table rollback, idempotency, advisory lock contention, disconnect, WAL settings, and logical backup/restore. **They do not prove actual Grid schema compatibility, physical WAL crash recovery, PITR or ENOSPC.**

## Reproducible Grid bootstrap — separate candidate, NOT executed

1. Pin one reviewed exact commit containing PR #227 and PR #230 compatible code. Verify source tree and migrations 1–48 before connection.
2. Attest an isolated PostgreSQL 18 server, disposable cluster identity and version; use PR #227 `tools/ci_pg18.py` and `tests/_pg18_database.py` only after reviewing their current exact HEAD.
3. Create a unique random per-run DB and three isolated non-superuser roles (owner, app, read-only) using the attested CI fixture. No `postgres` or default database reuse.
4. Run trusted `prepare_schema(owner_pool)` exactly once on an empty database. Re-run must return `ALREADY_PREPARED`; any source/catalog drift must fail closed.
5. Grant the app only the verified required DML and sequence permissions. Revoke writes to `grid_schema_contract` and `schema_migrations`. Prove app cannot CREATE TABLE, CREATE TEMP TABLE, ALTER schema or write the seal.
6. Execute `verify_runtime_schema(app_pool)` before application startup; wrong role, schema mismatch, missing gate or migration registry mismatch must STOP.
7. Enumerate actual `pg_catalog` relations and columns, then exercise `market_events` insert/idempotency, `candles_1m`, `footprint_1m`, `orderbook_snapshots`, `derivatives_metrics` only if confirmed. Instrument assignment/collector state fixtures must be derived from the reviewed schema and source writers; do not guess tables.
8. Simulate concurrency, rollback, duplicate writes, interrupted migration and shutdown while pending DB writes. Verify no partial committed rows. WAL/crash/PITR require a separate isolated cluster restart/recovery harness with verified data directory custody.
9. Take `pg_dump` custom archive, SHA256 it, restore to **a new disposable database**, compare row counts and canonical values plus constraints and indexes. Reject corrupt archive and mismatched digest.
10. Upload exact-head JUnit/JSONL (where supported), manifest, attempt number and independent artifact digest. Drop only the unique per-run disposable resources after evidence custody; no global cleanup.

## STOP conditions

Any unexpected host/port/cluster identity, non-PG18 version, default/production database, role with superuser/CREATEDB/CREATEROLE/replication/BYPASSRLS, owner role at runtime, schema source/catalog mismatch, missing migration 1–48, DDL capability for app, unknown table, unverified restore, disk-full, invalid DSN, evidence corruption, missing/queued/skipped CI or runner uncertainty => **BLOCKED / NO-GO**. Never automatically reseal, migrate an unknown schema, retry destructive SQL or treat mock/SQLite as PG18 evidence.

## Open acceptance evidence

**P0:** source-level integrated candidate, complete real-schema fixtures, independent role/grant matrix, exact-head hosted JUnit/artifacts and database identity; physical LS5 custody remains separate. **P1:** real disposable WAL crash/restart/PITR, interrupted migration, disk-full, shutdown drain. **P2:** repeatable retention/RPO/RTO measurements. G0 BLOCKED, G1 NOT_RUN, physical NO-GO.
