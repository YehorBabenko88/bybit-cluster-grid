# Independent PostgreSQL/storage review of PR #244

Review snapshot: PR #244 exact `38e6ab40928cbdd6a2d6d84cbb05b4628167258f`; PR #240 input `3bb49c2c99dc461aec52f014432511e1fd694a28`. Source review only. No PostgreSQL connection, Docker, production/LS5/PC4 access, merge or deployment. **Real PG18 test BLOCKED; no hosted PASS.**

## Verified source contracts

- `integration/first_boot.py` invokes `attest()` before database fixture; `database(False, cleanup_guard=...)` uses a generated `ddl18_<uuid>` DB, three generated owner/app/ro roles, and `prepare_schema()` then `verify_runtime_schema()`. It checks migration versions `range(1,49)`, second preparation `ALREADY_PREPARED`, app CREATE TABLE denial, RO DELETE denial, source catalog digest after runtime.
- `tests/_pg18_database.py` connects via `host='127.0.0.1'` and attested random port, CI-only generated password, and verifies `pg_control_system()` identity plus `server_version_num=180004` before role/database creation. `tools/ci_pg18.py` requires GitHub-hosted Linux `GITHUB_JOB=pg18`, matching repository/run/attempt container labels, exact image `postgres:18.4`, loopback-only Docker port, tmpfs PGDATA, nonprivileged container, image ID and cluster ID. This is **source-intended containment**, not observed runtime isolation.
- Coordinator child DSN is constructed only from the generated app role, loopback port and generated DB; worker child env is created separately. No literal production DSN appears in this construction. **Full repository environment inheritance and credential-exfiltration safety remain unproven** without inspecting all subprocess environment filtering and hosted evidence.
- `fresh_collection()` queries real `candles_1m` and `collection_ingest_receipts` by timestamp, with expected two synthetic symbols and buy/sell volumes; duplicate receipt replay must be accepted idempotently, changed payload rejected. Restart cases include worker, coordinator and PostgreSQL `pg_ctl restart -m fast`, then new collection/readback; catalog digest is compared at end.
- PostgreSQL restart `-m fast` is **orderly fast shutdown**, not crash recovery (`-m immediate`/power loss); the latter remains NOT_RUN. There is no verified `pg_dump/pg_restore` or independent restored-row digest in `integration/first_boot.py`. PR #240 has a separate disposable toy-table logical backup test, not the full Grid schema.
- Concurrent enrollment is exercised; concurrent market-data DB writes, isolation anomalies, advisory lock contention, interrupted migration, disk-full and outstanding writes at forced shutdown are **not independently demonstrated by the first_boot source**. The separate mandatory 32 PG18 regression cases require hosted artifacts and exact test inventory before acceptance.

## Independent negative-test plan (isolated only)

1. Reject absent `GITHUB_ACTIONS`, wrong `RUNNER_ENVIRONMENT`, remote Docker context, wrong image digest/PGDATA/tmpfs, wrong run attempt, wrong DB cluster ID **before** any connection or mutation.
2. Verify no `postgres`/production DSN reaches Coordinator or Worker; record redacted env-key inventory, never secrets.
3. Check `grid_schema_contract` and `schema_migrations` cannot be modified by app, owner seal/catalog drift fails; test interrupted migration rollback in a **new disposable DB**.
4. Concurrent replay of the same minute: exactly one canonical committed value; conflicting payload fails; crash a writer mid-transaction and verify rollback.
5. Distinguish `pg_ctl restart -m fast` (clean restart) from a separate isolated crash/recovery test; verify `pg_control` identity, WAL replay and fresh durable writes after recovery.
6. `pg_dump` Grid schema and synthetic rows, SHA256 custom archive, restore into a **second generated database**, compare canonical rows, migration registry, constraints and indexes; reject truncated archive.
7. During controlled shutdown, record active DB sessions and in-flight writes before/after; ensure no unknown child remains before cleanup and no uncommitted rows persist.
8. Inject ENOSPC only into a separate disposable fault fixture; never fill a shared runner disk or real PGDATA.

## Acceptance and blockers

P0: run 40081972021 queued (no E2E artifact), real Grid schema/bootstrap/role/data integration not independently executed; PR #244 `ls5-postgres18-disposable` profile is SKIPPED (not a pass); independent artifact/DSN environment proof missing. P1: crash recovery vs fast restart, full Grid backup/restore, interrupted migration, concurrent writes, shutdown drain, ENOSPC. P2: retention/RPO/RTO, repeatable restore and dependency pinning.

Required receipts: exact SHA + run ID + attempt, PG18 image ID/system_identifier, verified 1–48 registry and role grants, zero-skip JUnit and source inventory, synthetic row/receipt counts and hashes, WAL/restart evidence, backup archive SHA256 plus restored canonical row digest, process/session cleanup and independent artifact bytes/digest. Any missing evidence => BLOCKED.

No changes to PR #244 or other agents' branches. Physical NO-GO.
