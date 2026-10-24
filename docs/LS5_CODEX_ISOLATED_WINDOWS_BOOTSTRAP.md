# Codex first isolated Windows bootstrap — handoff contract

**Scope:** disposable Windows VM only. This is a test contract, not permission to run production Apply, change LS5/PC4, install actual Scheduled Tasks or alter machine ACLs. Base PR #237 HEAD `e25197b169ef0e5f37b5bd0030ee4a97b13965e2`; PR #238 native observer HEAD `7df22d1c5cdc60bcf4e3414dacd35d23fdec7149`. Integration requires fresh exact HEAD checks.

## Real entrypoint inventory (source audit)

| Role | Task / launcher | Executable chain |
| --- | --- | --- |
| CONTROL | `BybitClusterGridCoordinator` / `installer/coordinator-launcher.ps1` | PowerShell → protected Python → `grid.release_supervisor` → `python -m uvicorn grid.coordinator:app --host 0.0.0.0 --port 8765` |
| WORKER | `BybitClusterGridAgent` / `installer/launcher.ps1` | PowerShell → protected Python → `grid.release_supervisor` → `run_worker.py` |
| ARCHIVE | `BybitClusterGridArchivePipeline` / `installer/archive-launcher.ps1` | Standalone archive task intentionally fenced off by installer |
| Release discovery | `installer/stage-github-release.ps1` | GitHub CLI → CI gate discovery; `-Download` deliberately BLOCKED |
| Recovery | `installer/recover-release.ps1`, `release-runtime-guard.ps1` | Release pointer/journal recovery; **never call `-Apply`** in this scope |

`installer/bootstrap.ps1 -Apply`, `installer/install.ps1 -Apply`, and `installer/stage-github-release.ps1 -Download` are deliberately blocked. Do not bypass their guards or execute unreachable legacy mutation paths.

## Isolated commands

From a clean checkout of PR #239 exact HEAD in a disposable, non-production Windows VM:

```powershell
$ErrorActionPreference = 'Stop'
py -3.11 -m venv .isolated-bootstrap-venv
$Py = '.\.isolated-bootstrap-venv\Scripts\python.exe'
& $Py -m pip install pytest
& $Py -m py_compile installer/trusted_bootstrap.py installer/ls5_bootstrap_ci_evidence.py installer/ls5_disposable_release_model.py tests/test_ls5_trusted_bootstrap.py tests/test_ls5_bootstrap_ci_evidence.py tests/test_ls5_disposable_release_model.py
& $Py -m pytest -q -ra tests/test_ls5_trusted_bootstrap.py tests/test_ls5_bootstrap_ci_evidence.py tests/test_ls5_disposable_release_model.py --junitxml=junit.xml
if ($LASTEXITCODE -ne 0) { throw 'STOP: isolated synthetic suite failed' }
$env:LS5_EXACT_HEAD = (git rev-parse HEAD).Trim()
$env:GITHUB_SHA = $env:LS5_EXACT_HEAD
$env:GITHUB_RUN_ID = 'local-isolated'
$env:GITHUB_RUN_ATTEMPT = '1'
$env:RUNNER_OS = 'Windows'
& $Py installer/ls5_bootstrap_ci_evidence.py junit.xml evidence
if ($LASTEXITCODE -ne 0) { throw 'STOP: evidence generation failed' }
Get-FileHash evidence/junit.xml, evidence/evidence.jsonl -Algorithm SHA256
```

Expected: all synthetic tests PASS with 0 errors/failures/skips; `evidence/junit.xml`, `evidence/evidence.jsonl`, `evidence/hashes.json` produced and hashes match. Every offline policy assessment still returns `status=BLOCKED`, `host_verified=false`, `execute_authorized=false`, `cleanup_authorized=false`, `deployment_authorized=false`.

For **read-only** PowerShell guard checks, run only with no `-Apply` or `-Download` and no production paths:

```powershell
powershell.exe -NoProfile -File installer/bootstrap.ps1
powershell.exe -NoProfile -File installer/protect-service.ps1
```

Expected: `PLAN_ONLY` and no host changes. Treat any unexpected mutation or task registration as immediate STOP.

## External integration dependencies

- Codex disposable VM and source checkout pinned to reviewed SHA; no reuse of LS5/PC4 secrets, database or task names.
- Native ACL observer PR #238: independent SID/DACL/ancestor/handle identity and nonce/manifest binding. A proposed handoff schema is in `docs/LS5_TRUSTED_SOURCE_HANDOFF.md`; **PR #238 has not accepted or implemented this interface**.
- Source custody: independent signed/reviewed release artifact, full Python/DLL/import/.pth/sitecustomize closure, environment allowlist, trusted directories and task XML hashes.
- Synthetic release-state model is not a Windows filesystem transaction or crash durability proof. Separate disposable Windows filesystem and native handle tests remain required.

## STOP conditions

Unknown source provenance, mismatch of exact HEAD or manifest, unexpected file, DLL, .pth, Python import root, environment override, reparse point, hardlink, writable ancestor, active writer, task state mismatch, journal conflict, partial staging, lost handle, incomplete JUnit, missing artifact, skipped CI, or any unreviewed Apply request → STOP/BLOCKED. Do not recover by falling back to `previous.version` or `bootstrap` without independent hash and custody proof.

## Gate status

G0 hosted exact-HEAD CI and artifacts: pending. G1 cross-PR integrated behavior: NOT_RUN. Real Windows install/start/stop/restart/rollback and physical crash recovery: NOT_RUN. LS5/PC4 untouched. PC4 0/10 NOT_RUN. Deployment NO-GO.

## PR244 release identity compatibility (2026-10-24)

The original offline assessor assumed one historical hardcoded release ID. It now validates any **exact 40-character lowercase commit ID**, but requires the matching coordinator executable path and all listed inventory hashes to agree with that same release. The integration candidate PR244 HEAD is `38e6ab40928cbdd6a2d6d84cbb05b4628167258f`; this value is a test fixture, **not** a trusted signed source or approval to activate. Both the candidate and its manifest must be independently verified. A release version change without updating the inventory must fail closed.

The PR244 full-system foreground entrypoint is `python -m integration.first_boot --execute-ci`, subject to its own CI-only gates and disposable PG18/native prerequisites. Do not substitute the standalone offline assessor or disposable release-state model for that E2E execution. Neither this PR nor PR244 authorizes physical bootstrap, release switching, Scheduled Task creation or production service startup.

## G0 physical host inventory: read-only only, owner/operator execution

After explicit operator confirmation that read-only G0 may run, on **each** host from a trusted checkout, run:

```powershell
# LS5, CONTROL
powershell.exe -NoProfile -NonInteractive -File .\installer\ls5-g0-readonly-preflight.ps1 -Role CONTROL
# PC4, WORKER
powershell.exe -NoProfile -NonInteractive -File .\installer\ls5-g0-readonly-preflight.ps1 -Role WORKER
```

Output JSON contains host, UTC time, task name/state, selected process PID/name/creation timestamp and listeners on 8765/55432. It intentionally does **not** read or print command lines, task actions, tokens, env, credentials or production database contents. Output `OBSERVATION_ONLY` is not READY/GO. `EXISTING_LISTENER_DO_NOT_REUSE` forbids reusing a port; `*_INVENTORY_UNAVAILABLE` requires STOP, not a guess. No process is killed, no service/task changed. PID alone is not process identity; native signed handle/token observer in PR238 is separately required to defend PID reuse.

## G1 disposable staging design — not authorized for physical hosts

Use unique, owner-reviewed isolated absolute directories on **each host**, with no overlap or reparse ancestor to installed Grid or PostgreSQL. Select different ephemeral loopback-only ports after read-only collision checks; never reuse 8765/55432 or existing coordinator credentials, service data, database or Tailscale interfaces. New staging paths and ports require G1 owner approval before any physical writes or bind. Pin SHA256 for each file, manifest, runtime binary and dependencies; verify closed Python import/.pth/sitecustomize/DLL paths and read-only native source custody. Do not use existing `coordinator-launcher.ps1` for G1: its hardcoded `0.0.0.0:8765`, ProgramData .env import and auto-token write violate isolation. Do not use existing `launcher.ps1` either: it imports ProgramData .env and invokes release recovery with `-Apply`. Both are production task launchers, not disposable lab entrypoints.

Foreground CI-only entrypoint is PR244 `python -m integration.first_boot --execute-ci` under its own attested disposable PG18 and synthetic loopback feed; first verify it does not bind existing listeners, use production credentials or access physical services. Required runbook phases: source/hash readback → isolated directory and ownership attestation → port check → disposable PG18 role/database (separate G1 approval) → foreground Coordinator and Worker children → stop only tracked children by stable handle+creation time → hash/manifest/journal re-read → interrupt staging fault tests → rollback only owned paths → verify all child processes exited → record JUnit/JSONL/SHA256. **Never cleanup by PID alone, prefix match, or recursive deletion without trusted owner marker + native path containment and reparse checks.** Any unknown child, stale handle, changed path identity, existing listener or uncertain database owner => STOP and retain evidence, not delete.

## Source compatibility matrix

| Boundary | PR239 | PR238 / PR244 | Result |
| --- | --- | --- | --- |
| Release identity | Dynamic 40-hex pinned inventory; never grants execution | PR244 integration HEAD pinned separately | Offline model compatible; native signature pending |
| Process identity | G0 PID+creation timestamp observation only | PR238 native token/handle custody | Native proof not integrated, G1 BLOCKED |
| Foreground launch | Existing task launchers unsafe for disposable isolation | PR244 uses `integration.first_boot --execute-ci` | Use PR244 harness only after independent source check |
| PostgreSQL | No DB mutations | PR244 disposable PG18 / 32 tests | Hosted PG JUnit reported PASS, whole job FAIL; no G1 authorization |
| Worker heartbeat | No network mutations | PR244 17 BLOCKED due to socket audit guard | P1 E2E fix and fresh exact-head artifact required |
| Windows native | No ACL writes | PR238 observer TOKEN_SIZE_UNKNOWN | Native G2 BLOCKED |
