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
