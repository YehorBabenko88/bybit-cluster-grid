# Issue #290 — canonical Grid market-data boundary (audit baseline)

Status: **NO_GO / SOURCE-ONLY / NOT DEPLOYED**. Parent: https://github.com/YehorBabenko88/unified-system/issues/111. This document does not certify live Bybit connectivity, security, Windows acceptance or any release.

## Immutable references (2026-11-19)
- Grid main: `d537d525296ef34f727996e240ae6c60102c6082`.
- Inspected candidate PR #288: `a2495825a2c8f412749b62bb9ebda6f4f79fd8d4` (stacked on `feature/agent5-collector-lifecycle-20261112`, **not main**).
- Candidate PRs #283–#288 are separate/stacked source changes. No assumption that they form one releasable head.
- Exact-head #288 Actions: PASS Portable Windows SDK qualification, history-integration, readonly-gateway-contract, source-provenance, windows-bundle; FAIL preflight, Agent2 unqualified worker DATA contract, Mission3 disposable source qualification. This is an observed run summary, not a diagnosis.

## Ownership decision requested from MASTER
| Capability | Proposed single authority | Grid rule |
| --- | --- | --- |
| Public Bybit REST/WS acquisition, request planning, symbol registry, normalized market events | Grid | Grid is sole public market acquisition producer; no exchange orders |
| Market-data storage and immutable custody | **Pending MASTER**: Grid writer adapter versus Unified A4 ObjectStore/Journal | Exactly one writer per dataset; do not silently introduce Grid + Unified concurrent writes |
| Cross-service admission, fencing and deployment | Unified | Grid worker follows authorized leases; no independent global supervisor |
| Strategy backtest/experiment lifecycle | Strattester | Grid publishes versioned, immutable market-data reads |
| Scientific numerical kernels | Math | Existing exact-byte Grid copies remain until pinned parity and consumer migration |
| Market-specific derived analytics | Meta Analyse | Read-only data consumption, distinct analytical outputs |
| End-user charts/controls | Terminan | No Grid-owned second general terminal |

## Source candidates requiring import/call-path inventory
- `grid/bybit.py`, `grid/bybit_request_plan.py`: public provider and bounded request planning.
- `grid/archive_worker.py`, `grid/worker.py`, `grid/owned_worker_service.py`: capture and lifecycle.
- `grid/storage.py`, `grid/micro_event_storage.py`: data writes, retention and provenance.
- `grid/instrument_profile.py`, `grid/instrument_lifecycle.py`, `grid/instrument_resilience.py`: identity and resilience.
- `grid/history_export.py`, `grid/history_export_v11.py`, `grid/history_snapshot.py`: historical handoff and snapshots.
- `grid/nonlinear_research.py`, `grid/position_sizing_research.py`, `grid/stochastic_research.py`, `grid/timeseries_research.py`: reported exact-byte copies of Math kernels; classify USED/ARCHIVAL/UNKNOWN before migration.
- `scripts/history_ci.py`: reported exact-byte Grid/Math duplicate, potentially independent CI fixture.
These paths were observed on PR #288's source tree; runtime reachability and equivalence are **not yet proven**.

## Proposed read-only market event contract v0 (proposal; not implemented)
Required: `schema_version`, `exchange`, `category`, `symbol`, `instrument_id`, `event_kind`, `event_time_ms`, `received_time_ms`, `source_kind`, `source_ref`, `ingest_generation`, `event_identity`, `quality`, `payload`.
- `instrument_id` MUST distinguish exchange, category and symbol, not symbol alone.
- Event times are UTC milliseconds. Store original source timestamp separately from receive time.
- `source_kind` distinguishes verified public REST, public WS, archive, replay and synthetic fixtures. Never label synthetic or stale data LIVE.
- `event_identity` is stable across retries and reconnects; append must be idempotent.
- `ingest_generation` and a fenced single-writer lease prevent stale worker publication.
- `quality` represents coverage, gap/duplicate checks, source confidence and finality; incomplete bars cannot be silently presented as closed.
- Read APIs MUST be scoped by instrument, UTC range, data kind, schema and provenance; no arbitrary SQL/DB credentials in Terminan.
- Producer MUST not use authenticated trading/order endpoints for research acceptance.

## Acceptance gates (all outstanding unless independently evidenced)
1. Exact-head lint, unit, source provenance, dependency/security and Windows workflows green, including three #288 failures.
2. Fully fetched all-refs Git secret scan (history, PR heads, LFS/binaries, workflows); report redacted findings only. No security clearance from filename-only checks.
3. Deterministic backfill and replay tests: reverse-order provider pages, overlap dedup, sparse gaps, closed-bar correctness, restart/resume and no data loss.
4. Real-source public REST/WS acceptance: per-symbol continuity, rate-limit/reconnect/backoff, stale-source detection, gap repair, receipt with timestamps/source. Offline fixture tests do not qualify.
5. Prove one writer and fenced generation under worker race, crash, restart, lease expiry and partial persistence; immutable readback/hash verification.
6. Versioned consumer contract and integration checks with Strattester, Math, Meta Analyse, Terminan and Unified.
7. Independent security and physical Windows end-to-end sign-off; simulated/paper only. No main merge, branch deletion, real order or destructive database changes before approval.

## Preservation and removal decisions
KEEP: all existing main, feature PR heads, raw data, snapshots, experiment evidence and historical fixtures. 
REVIEW: exact-byte Math kernels, overlapping collectors and worker/supervisor interfaces.
DELETE: **none approved**. Future removal requires import map, parity test, migration receipt, rollback and MASTER sign-off.

## Current blockers
- Three exact-head #288 CI failures; causes not yet established.
- Writer/custody split with Unified A4 unresolved.
- No full-history security clearance.
- No verified live REST→WS physical continuity, crash recovery, Windows E2E or six-repo contract sign-off.
