# Independent disposable-laboratory E2E acceptance (Issue #243)

**Scope:** review of an isolated Codex lab run; no physical LS5/PC4 connection,
no production SQL, no real Bybit orders, no deployment/merge. Codex self-report
is untrusted producer input, not independent acceptance.

## Architecture and entrypoint discovery

Verified in PR #237 base README: coordinator discovers linear contracts and
assigns symbols; workers advertise CPU/RAM/disk headroom and consume publicTrade
streams; coordinator reassigns when a node disappears; PostgreSQL persists
`candles_1m` and `footprint_1m`. This README is an architectural description,
**not proof of a runnable executable or validated CLI**. Before E2E execution,
independently identify the actual coordinator/agent launch modules, API endpoints,
schema/migrations, DB adapters, spool path, shutdown and restart command in the
pinned integration commit; record exact file path, CLI args, executable SHA256 and
environment. Do not infer entrypoints from a developer narrative.

## Required E2E phases (all ordered, exact run/attempt)

| Phase | Independent oracle / evidence | STOP condition |
|---|---|---|
| Coordinator start | external process PID, bound listener, authenticated health, start log | listener missing or PID/health conflict |
| Agent registration | coordinator roster versus agent self-report; unique node identity | duplicate/stale identity |
| Assignment | coordinator assignment snapshot and agent subscriptions | overlap, missing symbols or unauthorized nodes |
| Synthetic ingestion | deterministic seeded input with input SHA256, no external orders | non-deterministic or real external write |
| PostgreSQL commit | independent read-only SQL queries for rows, schema, transactions | missing/duplicate/partial rows |
| Storage readback | recompute 1m buy/sell, delta, POC and row counts from seed | mismatched sums or POC |
| Shutdown | process exit, drained writes, closed handles, DB consistency | orphan writer, premature ACK |
| Restart | fresh PID/epoch, lease fencing, resume checkpoint | stale lease or replay |
| Recovery readback | independently compare persisted rows and assignment state | loss, duplicate or silent corruption |

## Negative matrix (each needs injection and independent oracle)

| Fault | Expected property |
|---|---|
| Crash / kill -9 | durable committed rows only; no false ACK |
| Timeout | bounded retry and explicit failure |
| Network loss | assignment fencing; no dual owners |
| PostgreSQL restart | retry/reconnect and no partial transaction |
| Corrupted spool | quarantine, checksum rejection, no silent skip |
| Duplicate messages | idempotent keys and exactly-once persisted effects |
| Invalid configuration | fail before side effects; no secret disclosure |
| Descriptor drift / PID reuse | revoke trust, require fresh identity |
| Interrupted journal | ordered intent replay or STOP; never blind cleanup |
| Cleanup boundary | only newly created disposable owned paths |
| Rollback boundary | restore owned fixture only; preserve pre-existing resources |

## Five-stream integration G0/G1

- #238: native ACL observer/custody; prove handle-bound identity, journal crash
  boundaries and negative spoofing.
- #239: bootstrap provenance; prove pinned source/release and fail-closed recovery.
- #240: PostgreSQL 18; prove disposable backup/restore, transactional recovery,
  schema contract and independent readback.
- #241: network; prove deny-by-default, timeout/loss/reconnect, authentication.
- #242: evidence/acceptance; independently verify ZIP bytes, per-entry SHA256,
  JUnit and JSONL semantics, exact HEAD/run/attempt, provenance and all required
  jobs; queued/skipped/absent artifacts cannot PASS.

The offline `installer/ls5_e2e_acceptance.py` inspector accepts untrusted
E2E receipts and verifies ZIP byte/hash consistency and five-PR metadata.
Its output **always** denies lab GO and deployment GO because it cannot
independently establish origin or runtime behavior. Self-consistent ZIPs can
be forged; separate GitHub artifact API ID, run attempt, artifact download,
immutable commit and independent SQL/OS observations are required.

## First lab-run report (as of 2026-10-24)

No independently obtained complete coordinator→agents→assignment→synthetic
data→storage→shutdown→restart evidence bundle or Codex integration PR has
been identified and validated in this review. All nine E2E phases and eleven
fault injections are **NOT_RUN/UNVERIFIED for independent acceptance**;
do not relabel producer assertions as PASS. Hosted profile Actions remain
queued; no verified complete artifact matrix. **LAB NO-GO (evidence
insufficient)**; G0 BLOCKED, G1 NOT_RUN.

## Future physical gates

G2 reviewed native custody and trusted source recovery; G3 explicit owner
authorization for LS5 read-only inspection; G4 separate owner authorization
for remediation with journal, STOP and independent rollback evidence; G5
separate coordinator/network/database activation approval; G6 separate PC4
preparation and ten real SID/ACL cases. Each requires independent immutable
evidence and fresh authorization. PC4 0/10 NOT_RUN; Execute/Cleanup
NOT_AUTHORIZED; Deployment NO-GO.
