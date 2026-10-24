# PR244 PostgreSQL 18 exact-head failure triage — 2026-10-24

Scope: independent GPT-3 read of hosted GitHub Actions job logs; **no physical LS5/PC4 work**, production SQL, credential access or merge.

## Exact heads

PR240 `17131da8c617fa2af08c03f1aa767cc83eb60dcc` at review start; PR244 `297fcb7cd12c2d1eaf819242abd3267fa7bd5ee0`. PR240 run `40089355292` SUCCESS (PG18 disposable and static guard workflow); three offline workflows SUCCESS. PR244 run `40088816142` ddl-free-runtime-pg18 overall FAILURE; its PG18 job `120857101231` SUCCESS and log reports **32 passed, 4 warnings in 30.95s**; acceptance job `120858177031` FAILURE. PR244 full-system-first-boot run `40088816153` overall FAILURE; PG18 job `120857101480` FAILURE; native jobs FAILURE.

## Confirmed exact-head log errors

1. `tools/check_ddl_acceptance.py` raises `RuntimeError('BLOCKED_SOURCE_HASH_MISSING')` in acceptance job `120858177031`. This is **evidence provenance/manifest failure**, not a failing PostgreSQL testcase. Inspect required source hashes, manifest inclusion and exact source checkout, without fabricating hashes or bypassing the gate. Retain fail-closed rejection until correct provenance is supplied.
2. First-boot PG18 job `120857101480` records `ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 32768)`, then `core_status=BLOCKED`, and cleanup reports `PG18_CI_PROVIDER_BLOCKED`. **This log alone does not establish whether the connection refusal is cause or consequence of provider lifecycle/cleanup**, or whether it concerns the expected container identity. Investigate ordered timestamps, provider container ID, `docker inspect`, health, process exit and port custody in the exact-head artifact; do not retry against unknown host/port.
3. Artifact IDs from hosted logs: DDL PG18 `12557653221` with reported ZIP SHA256 `7c1fc6c0e7c536925e433e70eaba074d872ad1012fd66524c145cf5da24975cc`; first-boot `12558810048` with reported ZIP SHA256 `46308f0514488247dcdb2ac5e4b354cfcc3cb5d530a942356fa3f04ebdd1a21e`. **Raw bytes have not been independently downloaded or rehashed by this reviewer.**

## Required Codex actions — only PR244 owner

- Read and pin exact HEAD, run ID, attempt and artifacts. Independently SHA256-verify actual ZIP bytes, validate JUnit, manifest, source receipts, and 26 E2E stage inventory.
- Reproduce `BLOCKED_SOURCE_HASH_MISSING` with a synthetic missing-manifest-path fixture and a valid exact-source fixture; repair manifest generation/source inclusion, not the fail-closed validator. Do not use an empty/placeholder hash.
- Trace container lifecycle: start, health, port mapping, first DB connection, shutdown/cleanup. Add negative tests for exited container, port reassignment, stale identity, cleanup double invocation, and failure before successful provider attestation.
- Ensure failed cleanup never drops a foreign DB, never stops a non-owned container and never connects to a production DSN. Require ownership receipts for each mutation.
- Re-run hosted jobs **only after substantive fixes** and independently verify artifacts. No LS5/PC4 access without separately approved G0/G1.

## Readiness

PR240 isolated PG18: **hosted SUCCESS**. PR244 PostgreSQL testcases: **32 PASS**, evidence acceptance **FAIL**. PR244 integrated first boot: **FAIL / BLOCKED**. Physical LS5 PostgreSQL version/roles/DB: **UNKNOWN**; G1 **NOT_AUTHORIZED**, deployment **NO-GO**.

Severity: **P0** integrated provider lifecycle/first-boot failure and physical authorization boundary; **P1** DDL acceptance source-hash missing and evidence provenance; **P2** full Grid restore/crash recovery/RPO/RTO remain open. No change to PR244 source is authorized from this branch.
