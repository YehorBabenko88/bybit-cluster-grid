# Independent PG18 acceptance checkpoint — PR244 exact HEAD 106a6c5 (2026-10-24)

## Source of evidence
GitHub Actions job logs inspected by GPT-3. Exact PR244 HEAD: `106a6c5a508cbdcf1b6bf99fe531fe27fb94715a`. PR240 prior HEAD: `9e5b392c4499127402eafe489f98cdb3c27855fa`. Raw artifact ZIP bytes **not independently downloaded or checked** in this checkpoint.

| Scope | Run / job | Result |
|---|---|---|
| PR240 disposable PG18 | 40090513605 / 120862043474 | SUCCESS, 7/7 PG18 + 3/3 offline guards |
| PR240 readiness offline | 40090513495 | SUCCESS |
| PR240 integration evidence audit | 40090513533 | SUCCESS |
| PR240 isolated-postgres-offline | 40090513460 | SUCCESS |
| PR244 ddl-free PG18 tests | 40091003727 / 120863477545 | SUCCESS, 32 passed, 4 warnings in 32.41s |
| PR244 ddl-free acceptance | 40091003727 / 120864457070 | FAILURE: `RuntimeError: BLOCKED_SOURCE_HASH_MISSING` |
| PR244 full-system-first-boot PG18 | 40091003818 / 120863477878 | FAILURE: 32 passed, 4 warnings in 24.33s, then `core_status=BLOCKED` |
| PR244 native observer | 40091003818 | Four native fixture jobs FAILURE; required observer gate FAILURE |
| PR244 required first boot | 40091003818 | FAILURE |

## Root-cause boundaries

The exact-head logs establish **source-hash acceptance failure** and **first-boot failure**, but not the cause of the latter. Do not attribute this HEAD's first-boot failure to the prior HEAD's `ConnectionRefusedError` without matching new logs/artifacts. The 32 passing PG18 cases do not override failing acceptance, native gate, or first-boot. No physical LS5 PostgreSQL identity, migration state or role grants have been observed.

## Codex requirements

1. Independently download exact run/attempt artifacts and verify ZIP SHA256, JUnit counters, test identities, source manifest hashes and 26 first-boot stage receipts.
2. Reproduce `BLOCKED_SOURCE_HASH_MISSING` in a synthetic negative fixture; repair the source manifest producer/coverage without disabling the validator or inserting placeholder digests.
3. Trace first-boot stage ordering, PostgreSQL provider identity, container health, loopback port ownership, worker connections and cleanup from **this exact HEAD**.
4. Require no production DSN, role/DB mutation, service restart, physical network change or real-host access. Do not interpret hosted smoke as LS5 G1 authorization.
5. Add exact-head independent evidence checks after substantive fix; no rerun solely to obtain green status.

## Readiness
Hosted PR240 PG18: PASS. Integrated PR244 PostgreSQL testcases: PASS; acceptance: FAIL; first boot: BLOCKED; native: FAIL. Physical LS5/PC4: 0/10 NOT_RUN. G0 owner inventory UNKNOWN; G1 NOT_AUTHORIZED; deployment NO-GO.
