# LS5 PG18 hosted acceptance checkpoint (2026-10-24)

This is an **independent GitHub-hosted** CI checkpoint, not a physical LS5 or PC4 commissioning certificate.

## Exact source and CI evidence

- PR #240 HEAD: `d40304c4e42adb44bd201e231c0b68f1a1ee62a2`.
- `ls5-postgres18-disposable` run `40094802632`, job `120874702511`: **SUCCESS**. Job log confirms `Ran 3 tests` and `7 passed in 1.57s`. The evidence validator received `PG18_TEST_OUTCOME: success`.
- `ls5-postgres-readiness-offline` run `40094802528`: **SUCCESS**.
- `isolated-postgres-offline` run `40094802474`: **SUCCESS**.
- `integration-evidence-audit` run `40094802433`: **SUCCESS**.

The receipt validator on this exact HEAD requires actual pytest-step success, the exact seven testcase identities, no duplicate names, matching suite counters, zero failures/errors/skips, and permitted XML elements. A green job confirms the positive path; **malicious JUnit mutation tests have not been independently exercised against this exact validator**. Uploaded artifact ZIP bytes have not been independently rehashed here.

## Integration boundary

- PR #244 exact HEAD at inspection: `106a6c5a508cbdcf1b6bf99fe531fe27fb94715a`.
- DDL PG18 run `40091003727`: PostgreSQL job SUCCESS, acceptance job FAILURE (`BLOCKED_SOURCE_HASH_MISSING`).
- Full-system-first-boot run `40091003818`: PG18 job FAILURE after 32 passing database tests; native observer jobs and required first-boot gate FAILURE.
- Hosted isolated PostgreSQL tests **do not** demonstrate production DSN safety, real LS5 PostgreSQL version/roles, end-to-end Grid worker execution, backup/restore RPO/RTO, or physical host custody.

## Release decision

**PR240 isolated PostgreSQL 18: hosted PASS** on the exact source SHA above. **PR244 integrated: NO-GO**. **LS5/PC4 physical: 0/10 NOT_RUN; G1 NOT_AUTHORIZED; deployment NO-GO**.

Before G1, owner must approve G0 read-only inventory and review actual LS5 service/port/version/disk/role evidence, a disposable DB/role plan, and independent custody-gated cleanup. Never create roles/DBs, restart services, run destructive migrations or connect to unknown DSNs based solely on hosted CI.
