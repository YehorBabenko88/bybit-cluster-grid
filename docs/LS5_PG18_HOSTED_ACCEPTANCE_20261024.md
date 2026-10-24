# Independent PG18 hosted CI acceptance checkpoint (2026-10-24)

**Scope:** PR240 PostgreSQL-only readiness versus PR244 integrated first boot. No LS5/PC4 operations. Source and GitHub job logs reviewed; artifact IDs enumerated but raw ZIP bytes not independently downloaded by this reviewer.

## Exact HEAD and run inventory

- PR240 `e908a9aa557efa6fb515cbaacb364757e5f283f8`: `ls5-postgres18-disposable` run `40086752355` **SUCCESS**, artifact `12557471102` (pg18-disposable-evidence, 968 bytes). Offline readiness, isolated PostgreSQL offline and evidence audit workflows all **SUCCESS**.
- PR244 `780362f39246498a85ca268ece4fb274b11d5745`: `full-system-first-boot` run `40087733739` **FAILURE**. `pg18` job `120853985851` **FAILURE** because the integrated first-boot step exited 1; **within that job, actual PG18 test command reported `32 passed, 4 warnings in 24.86s`**, followed by `python -m integration.first_boot --execute-ci` printing `core_status=BLOCKED`. `required-first-boot` acceptance job `120854681166` FAILURE; native jobs also failed. `ls5-postgres18-disposable` profile on this integrated HEAD was SKIPPED, not PASS.

## Interpretation

The 32-case PostgreSQL contract test result is real hosted execution per job log, **not a claim that integrated first boot succeeded**. Job-level failure must not be overwritten by test-level PASS. No direct LS5 PostgreSQL service version/role/schema inventory has been performed. This source-level review does not prove Grid WAL crash recovery, full-schema backup/restore, ENOSPC, concurrent writes or shutdown drain. The first-boot failure requires inspection of the latest **exact-head** evidence ZIP and child logs; do not assume the previous HEAD's socket guard failure persists without checking.

## Review acceptance checklist for Codex

1. Pin exact `780362f...` and job/run attempt, download actual first-boot evidence artifact and recompute archive SHA256 independently.
2. Parse the exact 32 PG18 JUnit testcase identities, failure/error/skip counters, DB cluster ID, migration 1–48 registry, role negative checks and schema seal. Cross-check job log and receipt.
3. Parse 26 first-boot stage statuses and the first blocked stage; correlate process logs, PostgreSQL restart evidence and cleanup ownership.
4. Require independent byte-level source inventory and no secret-bearing DSN in child environment receipts. Never publish password or full DSN.
5. Compare real schema and synthetic row/receipt canonical values before and after worker/coordinator/PG restart. Distinguish orderly fast restart from crash recovery.
6. Require full Grid backup/restore to separately owned random database, archive digest and canonical row/catalog digest; PR240's toy-table restore is not equivalent.
7. Any artifact missing, failed, inconsistent, or not from exact HEAD/attempt => **BLOCKED**, not PASS.

## Priority

**P0:** PR244 E2E failure; physical LS5 PostgreSQL identity UNKNOWN; owner G1 authorization absent. **P1:** exact-head independent artifact inspection, complete real Grid restore and crash WAL proof, shutdown drain. **P2:** RPO/RTO and retention. **Verdict:** PostgreSQL-only hosted smoke SUCCESS, integrated PG tests 32/32 PASS at testcase level but overall integrated job FAILURE; first boot BLOCKED; physical NO-GO.
