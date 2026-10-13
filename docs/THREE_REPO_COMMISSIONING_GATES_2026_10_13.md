# Three-repository commissioning gates (2026-10-13)

Scope: Bybit Cluster Grid + Strattester + Terminan. This is a **read-only commissioning plan**, not authorization to deploy or trade.

## Baseline and integration blocker

The proposed stack consists of PR #173 and draft PRs #174–#178. The latter are **not a linear stack**:
- #174 is based on #173
- #175 is based on #173
- #176 is based on #174
- #177 is based on #173
- #178 is based on #175

Consequently, merging #178 or checking its green CI does **not** incorporate #176/#177. A separate composed HEAD and its own Actions runs are mandatory. Resolve overlap in `grid/micro_event_storage.py`, `.github/workflows/preflight.yml`, and `.github/workflows/windows-bundle.yml` without dropping either implementation.

Required composed behavior:
1. Evidence capture uses **/ingest/capture**, strict finite JSON and protocol-1 **QUARANTINED** hash-bound durable receipts; never fall back to `/ingest/event`.
2. Active CONTROL discovery chooses the endpoint **before** sending to the evidence path; discovery does not grant write permission. Never blindly retry uncertain POSTs.
3. CI retains raw writer, migration 47, WAL ownership, source quarantine, process-kill, CONTROL fencing, and independent writer gates; retain Python 3.11/3.12 Windows matrix gates and standalone bundle checks.
4. PostgreSQL migration 47 is additive. Older CONTROL/worker binaries that bypass cooperative fencing must be stopped before upgrading. No downgrade to a pre-47 writer while quarantine is active.
5. `ArchivePipeline` standalone activation is intentionally fail-closed until a fenced caller is implemented; do not bypass this gate to restore availability.

## Gate 0 — repository/CI

- [ ] Record exact immutable SHAs for Grid, Strattester and Terminan and pin them in a signed or reviewed manifest.
- [ ] Build composed integration branch without touching Codex's draft branches; compare effective diffs and review conflicts.
- [ ] Run complete Linux Python 3.11/3.12, Windows Python 3.11/3.12, and PostgreSQL integration tests against the **composed** HEAD. Zero mandatory skipped tests.
- [ ] Run cross-repo consumer/provider contract tests against those exact SHAs, not only synthetic substitutes.
- [ ] Produce Windows install artifacts tied to the composed commit SHA and verify hashes before installation.
- [ ] Confirm no live trading/order submission endpoints are enabled.

## Gate 1 — non-destructive fleet inventory

For **each** PC record hostname, Tailscale identity, roles, service/task names, Python and PostgreSQL versions, DB host/port, code release SHA, WAL roots, disk free, backup location, firewall policy, SSH route, process IDs, service credentials, and rollback release. Do not store passwords/tokens in the inventory. Never infer these values from old logs.

- [ ] Prove administrative access via the intended jump host and independent break-glass recovery.
- [ ] Enumerate all legacy processes, scheduled tasks and raw SQL writers, including optional plugins and archival jobs.
- [ ] Check read-only consumer credentials: Terminan/Strattester must not write canonical Grid market data.
- [ ] Establish disk headroom and measured per-symbol trade/book capture throughput; choose and enforce a bounded WAL/quarantine admission policy **before** prolonged capture.

## Gate 2 — backup, migrations, rollback

- [ ] Verify a restorable PostgreSQL backup in an isolated test instance, including schema and roles.
- [ ] Replay migrations 1–46 then 47 with existing candle, footprint and quarantine rows, concurrency and idempotence; compare row counts/checksums.
- [ ] Preserve external runtime data/secrets/logs and versioned releases separately.
- [ ] Exercise interrupted install and rollback. A rollback that starts an incompatible old writer is a **failure**, not success.
- [ ] Block deployment if backup verification, free space, schema compatibility or version manifest checks fail.

## Gate 3 — one Windows test PC

- [ ] Start in read-only/simulation mode, no order keys or trade execution.
- [ ] Validate service startup, graceful stop, detached SSH deployment, reboot autostart and local event logs.
- [ ] Kill worker during open trade/book bucket; validate durable evidence, unique monotonic WAL IDs, quarantine receipts and no premature canonical promotion.
- [ ] Inject disk-full, fsync uncertainty, malformed/nonfinite frames, DB loss and network loss; require fail-closed behavior and explicit operator alerts.
- [ ] Verify Strattester research outputs and Terminan chart/footprint data against source timestamps, symbols, volumes and schema versions.

## Gate 4 — two-node failover

- [ ] Start two CONTROL candidates with a single authoritative fenced leader; test network partition, lease expiry and stale-epoch writes.
- [ ] Route health/ingest/ML to active CONTROL; ensure no duplicate uncertain POST and no standby-only outage.
- [ ] Power-cycle leader and worker (not just process kill); validate recovery, old-writer exclusion and no dual WAL ownership.
- [ ] Measure recovery time, loss windows, backlog and disk usage; distinguish accepted frames from frames lost before durable append.

## Gate 5 — soak and rollout decision

- [ ] At least 24-hour non-trading soak with latency, throughput, reconnects, CPU/RAM/disk, WAL backlog, quarantine counts, ingest errors, leader transitions and data-quality dashboards.
- [ ] Define explicit pass/fail thresholds **from measured capacity** and verify alert delivery.
- [ ] Reconcile quarantine with a reviewed operator workflow; never auto-promote to canonical market statistics or purge without evidence retention policy.
- [ ] Record test evidence, operator approval, release SHA manifest and rollback drill before any fleet-wide rollout.

## Stop conditions

Any dual leader, stale writer accepted, ACK before durable evidence, unexpected canonical promotion, unbounded disk growth, missing backup, incompatible rollback, trading-capable credentials in test mode, or loss of an auditable event trail is a **NO-GO**. Do not silently waive a failed gate.

## Current evidence / limitations

Codex's local composition reported 1,130 offline passed, 26 skipped and 9 synthetic cross-repository tests; five mandatory PostgreSQL modules were excluded from that local run. Separate PR CI success does not establish composed-head CI. Physical Windows reboot, power loss, full-fleet inventory, real network, capture capacity, durable quarantine reconciliation and production HA remain unverified. This document makes no claim that any physical gate has passed.
