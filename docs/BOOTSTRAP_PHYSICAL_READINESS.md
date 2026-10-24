# BOOTSTRAP_PHYSICAL_READINESS — independent GPT-1 verdict

Reviewed source: PR239 (own branch), PR244 exact HEAD `3808cb9f6ecd2f42d5d0c758145b427a58a010e8` at assessment. The result is **BLOCKED / NO-GO** for LS5→PC4 physical G1. This is an offline source and model assessment, not a host attestation.

## Mandatory invariants

1. Existing LS5 Coordinator and PG18 processes, ports, credentials, release pointers, .env, ProgramData and database remain untouched.
2. Never use production `coordinator-launcher.ps1` or `launcher.ps1` for G1: they read shared ProgramData, can invoke recovery -Apply, and Coordinator binds wildcard 8765.
3. Candidate must be separately staged in a fresh protected root; owner SID, every ancestor ACL/DELETE_CHILD, file IDs, no reparse/hardlinks and open-writer state must be independently attested. Unknown means STOP, not create/fix ACL.
4. Runtime closure must include exact Python executable, pyvenv.cfg, .pth, sitecustomize, packages, native DLL imports, PowerShell modules, manifest, config and search paths. No ambient PYTHONPATH/PATH/PG secrets or existing shared tokens.
5. A future Windows controller must own real process handles and job objects; PID and creation timestamp are diagnostic only. PID reuse, foreign parent, unknown child or token mismatch means **no signal and no cleanup**.
6. Graceful shutdown: cooperative owned control → bounded wait → independently verified child exit; timeout or unknown process identity means STOP and retain evidence, never taskkill by name/port/PID.
7. Staging journal and rollback require immutable run nonce, release identity, volume/file ID and signed custody. Interrupted stage, partial rollback or unknown handle leaves resources retained.
8. Cleanup is a **separately authorized operation**, never inferred from offline PASS. Only objects with independently verified creation receipt, stable handle and full containment may be considered by a future executor.

## Offline adversarial coverage

`installer/ls5_coexistence_safety.py` is a pure classifier; it never performs host reads, process signals or filesystem writes. `tests/test_ls5_coexistence_safety.py` covers foreign process owner, PID reuse/missing creation time, unexpected descendants, missing parent proof, shared/aliased paths, reparse, unknown owner/ACL, stale run marker, unknown journal, attempted forged cleanup permission and coexistence assertions. It always returns `execute_authorized=false`, `cleanup_authorized=false`, `bootstrap_physical_readiness=NO-GO`, even for `OFFLINE_MODEL_PASS`.

This is not a real Windows Job Object or ACL test. The independently reviewed native controller/observer from PR238 and physical program in PR244 must prove all live properties before G1.

## G0 commands (operator review only, no execution by GPT-1)

```powershell
powershell.exe -NoProfile -NonInteractive -File .\installer\ls5-g0-readonly-preflight.ps1 -Role CONTROL
powershell.exe -NoProfile -NonInteractive -File .\installer\ls5-g0-readonly-preflight.ps1 -Role WORKER
```

Do not run both on the same host as a substitute for distinct LS5/PC4 observations. Output is observation only, not authorization. Existing listeners or enabled tasks are STOP. Do not change existing tasks, ACL, services, users, firewall, SSH, Tailscale or PostgreSQL.

## G1 future contract for Codex (NOT AUTHORIZED)

A new per-run protected source root, independently verified executable closure, unique loopback-only ports, new disposable PG18 instance and generated credentials, approved SSH tunnel, synthetic feed, stable Windows process handles/job, independent read-only observer and protected creation journal are required. No fallback to production release or shared ProgramData. No PID-only stop, no recursive path deletion and no cleanup when any owner/child/handle is unknown. See `docs/LS5_PC4_G1_RUNBOOK.md` in PR244 for proposed stages; those templates are not executable authorization.

## P0/P1/P2 and readiness

- **P0:** real host source custody, writable old LS5 ACLs, production launcher shared state, native process/ACL/handle proof not accepted; physical execution not authorized.
- **P1:** Windows job/process tree and cooperative shutdown proof, interrupted staging/partial rollback, full runtime/DLL closure and new exact-head integration evidence.
- **P2:** hash-locked CI dependencies, long-term evidence retention and Windows Unicode path normalization review.

**BOOTSTRAP_PHYSICAL_READINESS = BLOCKED. G0 = READ_ONLY_PLAN. G1 = NOT_AUTHORIZED. Physical PC4 = 0/10 NOT_RUN. Execute/Cleanup = NOT_AUTHORIZED. Deployment = NO-GO.**
