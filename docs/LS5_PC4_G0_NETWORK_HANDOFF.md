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
