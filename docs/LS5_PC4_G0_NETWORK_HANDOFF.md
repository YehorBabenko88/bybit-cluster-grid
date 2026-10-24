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
