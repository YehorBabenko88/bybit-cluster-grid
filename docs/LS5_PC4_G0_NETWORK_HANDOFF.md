# LS5 ↔ PC4 network G0 read-only handoff (2026-10-24)

**PLAN_ONLY / physical G1 NOT_AUTHORIZED.** Exact source inputs: PR241 `152be6404d4764ec1bba041c679a5719746e8dbc`; PR244 `38e6ab40928cbdd6a2d6d84cbb05b4628167258f`. Historical tailnet IPs are unverified: LS5 `100.103.160.110`, PC4 `100.91.48.20`. Do not run these commands from ChatGPT or remotely; operator must first approve read-only inventory scope and redact credentials/hostnames as appropriate.

## Intended connectivity (not observed)

| Origin | Destination | Port/protocol | Purpose | G0 result |
|---|---|---|---|---|
| PC4 Worker | LS5 Coordinator | TCP 8765 | HTTP enroll/heartbeat/ingest | NOT_TESTED; no firewall opening authorized |
| LS5 operator | PC4 | TCP 22 | Existing SSH administration | NOT_TESTED |
| PC4 operator | LS5 | TCP 22 | Optional reverse SSH diagnostics | NOT_TESTED |
| LS5 Coordinator | LS5 disposable PostgreSQL | TCP 55432 proposed, loopback only | DB for *future* disposable test; must verify actual DSN/port | NOT_TESTED |
| PC4 Worker | PostgreSQL | none | Worker must not receive PG DSN | DENY by design |
| Any external/public network | LS5 test Coordinator | none | No public ingress | DENY by design |
| Either host | Bybit production endpoints | none | Synthetic-only G1 | DENY by design |

## G0 commands — read-only, owner-reviewed, execute manually on each specified machine

```powershell
# On LS5 and PC4 separately: inventory only, no configuration mutation
hostname
Get-Date -Format o
tailscale version
tailscale status --json | ConvertFrom-Json | Select-Object -ExpandProperty Self | Select-Object HostName,TailscaleIPs,Online
Get-Service Tailscale,sshd -ErrorAction SilentlyContinue | Select-Object Name,Status,StartType
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -in 22,8765,55432 } |
  Select-Object LocalAddress,LocalPort,OwningProcess
# Inspect local installed runtime without revealing credential values:
Get-Process -Name python,python3,uvicorn -ErrorAction SilentlyContinue | Select-Object ProcessName,Id
```

```powershell
# Optional ONLY after owner authorizes read-only network probing as G0.
# These are active probes, not configuration changes; do NOT run as G1 without approval.
Test-NetConnection 100.103.160.110 -Port 8765 -InformationLevel Detailed  # from PC4
Test-NetConnection 100.91.48.20 -Port 22 -InformationLevel Detailed     # from LS5
```

Do not execute `tailscale up`, `tailscale set`, `ssh` login, `New-NetFirewallRule`, `Set-NetFirewallRule`, `netsh`, `docker run`, `CREATE DATABASE`, `uvicorn` bind or any service/task modification in G0. Existing listener 0.0.0.0:8765 must be reported as **risk**, not silently modified. A successful TCP connection alone is not authentication/TLS evidence.

## Coordinator and Worker source contracts

PR244 `grid/config.py`: default coordinator URL `http://127.0.0.1:8765`; heartbeat 10s; rebalance 30s; **default REST/WS URLs point to real Bybit**, therefore any G1 requires explicit synthetic URL overrides, no inheritance of .env and fail-closed endpoint assertions. `integration/first_boot_policy.py` overrides REST/WS to local synthetic feed, sets coordinator URL to loopback and candidates empty, strips most secrets; it also preserves `LD_LIBRARY_PATH`, a separate audit concern. The real first-boot child imports `grid.worker.Worker` and binds Uvicorn explicitly to loopback. This CI-only harness is **not** automatically a safe two-host LS5/PC4 physical launcher: its `require_ci()` restricts hosted Linux and its Python audit guard blocks non-loopback sockets.

Enrollment: POST `/enroll` with one-time `enrollment_token,node_id` yields per-node credential; Worker uses `X-Node-Credential` for POST `/heartbeat`, ingest and commands. `node_auth` currently falls back to `X-Grid-Token` CONTROL token. Never put fleet CONTROL token on PC4; cross-node credential spoofing and fallback must be resolved before G1. `/nodes/{id}/acceptance` requires matching credential and considers heartbeat stale after >2× interval; assignment eligibility and coordinator in-memory state require independent restart checks.

## Hosted integration failure and required corrective contract

Issue #243 independent raw-artifact QA for PR244 run 40081972021 / attempt1 reports first boot 9 PASS / 17 BLOCKED, 32 PG JUnit tests passed, and actual Worker failure `FIRST_BOOT_UNIX_NETWORK_BLOCKED` in `integration/first_boot_policy.py` socket audit hook. This blocks two-Worker E2E acceptance. **Do not weaken network isolation broadly.** Codex must identify actual socket audit event/address and permit only the narrowly justified local socket behavior, with regression cases for AF_UNIX socketpair/pipe and denial of external AF_UNIX pathname sockets, external TCP, DNS and bind. Require re-run with real Worker, JUnit, JSONL, exact SHA and raw artifacts. No fix to PR244 is made from PR241.

## Owner approval gates

G0: host/IP/process/listener/firewall/SSH/Tailscale facts from read-only operator evidence, redacted and timestamped; do not infer current connectivity from historical IPs. G1: separately approved exact command manifest with disposable DB/ports/roles, process containment, synthetic feed, cleanup, no production endpoints and explicit rollback. **Physical G1 = NO-GO** until owner approval plus hosted E2E failure resolution.

## PR244 physical planning compatibility delta — 2026-10-24

New PR244 exact HEAD `297fcb7cd12c2d1eaf819242abd3267fa7bd5ee0` adds `docs/LS5_PC4_G0_READINESS.md`, `docs/LS5_PC4_G1_RUNBOOK.md`, `docs/LS5_PC4_PR_COMPATIBILITY.md`, `integration/physical_program.py` and local read-only observer `installer/collect-physical-g0.ps1`. Its G0 status is **BLOCKED** (no LS5/PC4 snapshots), and G1 remains **NOT_AUTHORIZED**. PR244's frozen compatibility matrix includes **earlier** PR241 HEAD `152be6404d4764ec1bba041c679a5719746e8dbc`, so it is stale relative to this PR's current HEAD; regenerate pinned comparison before integration.

**Do not substitute** PR241's `grid-network-offline-1` historical Tailscale address/port policy for PR244's physical G0 observations. The old policy only validates a bounded model with historical addresses and proposed port55432; it always returns `BLOCKED`, `host_verified=false`, `execution_authorized=false`. The new physical G1 runbook explicitly requires fresh IP/identity/port collision evidence, nonreserved owned test ports, isolated coordinator process and database, and explicit owner approval. Do not loosen old fail-closed validator to accept unknown physical hosts.

**Do not run** production `run_coordinator.py` or `run_worker.py` as G1 launchers: PR239 audit reports shared .env/token and Apply recovery, and the production coordinator wildcard bind `0.0.0.0:8765`. A loopback-only hosted CI harness is not a two-host Windows runner; a physical network route needs a separate reviewed transport/authentication/bind contract. No external bind, firewall opening, Tailscale/SSH change or physical probe is authorized here.

**Network handoff acceptance matrix:** (1) trusted exact checkout and redacted local G0 snapshots from both machines; (2) Tailscale IP and approved host-key identities freshly observed; (3) existing listeners and port collisions reviewed; (4) PC4→LS5 API reachability and TLS/node credential checks **only after separately authorized probe**; (5) wrong-node credential, token replay, stale heartbeat, reconnect, duplicate delivery and coordinator restart with **real Worker**, no mocks; (6) independent raw evidence/JUnit/JSONL and exact HEAD/run/attempt; (7) fail-closed on unknown or mismatch. All physical entries remain **NOT_RUN/BLOCKED**.

## Hosted CI checkpoint — source/evidence scope

For PR241 exact HEAD `ccd420038aa8da02a319ebab82bf346bba88d936`, GitHub workflow run [40089326453](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/40089326453) reports **COMPLETED SUCCESS** in all four jobs: Ubuntu/Windows × Python3.11/3.12. Four JUnit ZIP artifact records are present, with GitHub-reported SHA256 digests:

| Job | Artifact ID | GitHub-reported ZIP digest |
|---|---:|---|
| Windows 3.11 | 12558685923 | b808e400ed512a08f1534ad1597ecc2bb309e1c7a6d37fa0a4dfdd8fea294e2b |
| Windows 3.12 | 12558421058 | 92a70b2dbb57a388aa8893ccd5c6acfc726e059eda5d9ce637704f95af5045a4 |
| Ubuntu 3.11 | 12558282802 | 2b7b0c23ba8c20a0a1cf485054fdccb9f0330aee7058d21a12f308fc5e325f44 |
| Ubuntu 3.12 | 12558267868 | 22c02a99ee86d25b563bfdc07afa33ad3887a36f052f30410f733cce106b9442 |

The workflow verifies actual checkout SHA before pytest; Windows AST parse-only step is successful. These are GitHub API job/metadata observations, **not independent ZIP-byte/JUnit-content reinspection**. Neither CI success nor synthetic network policy validates actual Tailscale routes, host SSH keys, physical Windows security, two real Workers or G1 authority. Physical G0 remains BLOCKED and G1 NOT_AUTHORIZED.

## 2026-10-24 latest HEAD CI and integration drift

PR241 `9181f51c8963811002322eadff8b2ceed07975fe`: [network workflow 40090107925](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/40090107925) **COMPLETED SUCCESS**, four of four hosted matrix jobs SUCCESS. GitHub artifact metadata:

| Matrix | ID | GitHub-reported SHA256 |
|---|---:|---|
| Windows 3.11 | 12559160456 | ada111cab76741a4be2a9f2236b0ad6c1b80fd3024d785c1b5d4759aac78e980 |
| Windows 3.12 | 12558344131 | 1aee0a0ef7c34a4735d157822f5d8cc6affc61404c7f9a0e8e98d530ebab2c4e |
| Ubuntu 3.11 | 12557734867 | aeb20e7323b79c3145aaaaeaf0687d5866be0e285825cf4cb40867433fbfdef6 |
| Ubuntu 3.12 | 12558247971 | 5c89edd331421b1e047a03028e97b5fdeacc0a819b9c849bdaf6dadee5ed6a73 |

Independent ZIP-byte inspection remains **NOT_DONE**. PR244 has advanced to `9efa0b947ea7f588437bb562da6f2b3729283709`. At that exact source HEAD, `integration/first_boot_policy.py` still explicitly rejects non-tuple Unix socket addresses and non-loopback IP addresses; this source fact alone does **not** establish whether the prior real Worker heartbeat failure is resolved. The `docs/LS5_PC4_PR_COMPATIBILITY.md` frozen matrix still pins old PR241 `152be640...` and old PR244 `38e6ab40...`; it is a historical snapshot, not current composition acceptance. Codex must regenerate it and check runtime/API semantics and current hosted artifacts before G1. No physical G0 observation or G1 permission has been granted.

## Preflight regression closed by hosted CI

For exact source HEAD `b5b38426d3507356b649aeb14caf6845fec521e7`, [global preflight run 40094507994](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/40094507994) is **COMPLETED SUCCESS**. Both Python3.11 and Python3.12 preflight jobs succeeded. This closes the six previously reproduced inherited-workflow branch-exclusion assertions at that exact HEAD; the earlier [failed run 40090656704](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/40090656704) remains historical evidence of the regression. The same exact HEAD's [network run 40094508000](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/40094508000) is 4/4 hosted jobs SUCCESS. GitHub's preflight run exposed no downloadable artifact records in its first page; its successful job status is not a raw JUnit evidence audit. Source/CI PASS cannot promote physical G0/G1.
