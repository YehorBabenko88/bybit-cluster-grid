# Composed integration audit — 2026-10-13

Draft PR: https://github.com/YehorBabenko88/bybit-cluster-grid/pull/180
Branch: `audit/codex-composed-integration-20261013`; base: PR #173.
This is a synthetic integration audit, **not production HA certification**.
No main merge, deployment, trading, production database, real Windows service,
or source PR branch was changed. PostgreSQL tests use disposable CI PostgreSQL 16.
Inventory regression tests mock machine providers and use an owned temporary fixture.

## Immutable inputs and history

| Input | HEAD SHA | Base |
|---|---|---|
| Grid main | `d537d525296ef34f727996e240ae6c60102c6082` | — |
| #173 CONTROL runtime | `fe9f3f09dd4f950663c2cb782d30da3067546d5a` | #172 |
| #174 WAL ownership | `cbc661a843d1802da5591c965452d673ceaffebb` | #173 |
| #175 raw writer fences | `565106debc697774b4a52f313b957a5d8336ec6e` | #173 |
| #176 source capture | `666ce7bebc93c677a6fd6a7a15a76e6d1d6b101c` | #174 |
| #177 CONTROL routing | `ad63c47f18bc40ad335b606a748c7916c14cd87e` | #173 |
| #178 auxiliary lifecycle | `2f00a1d94134753b9e1bdf19a280c08b03155aef` | #175 |
| #179 commissioning | `865c3af3db320cea8f55336f5ff793d56b64928f` | #178 |
| Strattester main | `37ff7e9d12a4d2dccd788fc493c28557dbe8bcea` | detached test checkout |
| Terminan main | `fee79f4b15fc1f9efcff9ca12c403688b0026260` | detached test checkout |

All source PR HEADs are ancestors of the composed branch: merge #176, #178,
#177, then #179, starting at #173. This also retains #174 and #175 history.
Merge commits: `e67819d9`, `66a6b4dd`, `ab2f36d2`, `557efcd5`.
Publication verifies Git blob/tree SHA equality; merges retain both parents.
User Strattester/Terminan audit branches are not edited. External contract
checkouts are pinned in preflight, with credentials not persisted.

## Conflicts resolved by contract

* `grid/micro_event_storage.py`: retain active CONTROL discovery AND separate
  `/ingest/capture` routing. Capture requires protocol 1, QUARANTINED disposition,
  matching digest, no redirects, and durable receipt before WAL ACK.
* `.github/workflows/preflight.yml`: retain raw writer, collection ownership,
  CONTROL runtime, migration 47, process WAL, capture and failure recovery gates.
  Full pytest remains enabled in both Linux Python matrices with PostgreSQL.
* `.github/workflows/windows-bundle.yml`: retain BOTH collector crash recovery
  and independent writer gates on Python 3.11/3.12, plus bundle build.

Coordinator, worker, storage and segment WAL merged without textual conflicts;
their persistence, collector ownership, writer lifecycle and replay paths were
reviewed together. No security gate or assertion was removed to obtain green CI.

## Safety invariants exercised

1. Assignment alone does not confer write permission: symbol generation/session
   and unexpired authoritative ownership are checked at ingest inside the
   persistence fence. CONTROL epoch is checked within critical transactions.
2. A delayed lease response cannot extend a local transaction deadline. Timeout
   covers deferred COMMIT; an expired transaction must roll back.
3. Capture raw evidence is appended before aggregation. Evidence receives a
   QUARANTINED durable receipt; replay does not automatically promote it LIVE.
4. One delivery ID describes one immutable JSON payload. ACK requires a matching
   receipt digest, and lost ACK replay deduplicates an already committed receipt.
5. A collector's aggregation state belongs to its task/ownership generation;
   takeover cannot relabel old buckets/CVD with a new token.
6. WAL ownership is exclusive between processes. Queue pressure blocks admission;
   configured WAL byte limits reject additional evidence before enqueue.

These are scoped to the tested code paths. The BLOCKER table limits broader claims.

## Confirmed defects and regression evidence

| Severity | Reproducer before fix | Root cause and fix | Files/tests |
|---|---|---|---|
| P1 | 0.4 s lease, 0.2 s delayed TTL response, 0.3 s deferred commit: LIVE could commit after lease expiry | Deadline sampled after response added transport delay to permission. Sample monotonic time before DB call, reject exhausted deadline, cover commit timeout | `grid/fenced_ingest.py`; `test_composed_lease_deadline.py`, real PG `test_composed_recovery_postgres.py` |
| P1 | Cancel generation 1 after qty 7; generation 2 qty 2 produced qty 9 / old buckets and CVD | Global MicroTape reused ownership state. Create task-local aggregator, preserve only reconnect state within same task | `grid/worker.py`; `test_composed_tape_ownership.py`; process harness `test_public_trade_capture.py` |
| P1 | Mutate nested event/minute qty 1 to 99 after WAL append; queued payload differs from recovered WAL | Shallow envelope retained caller-owned objects. Freeze exact JSON model before append/enqueue; reject nonfinite JSON | `grid/collection_ownership.py`; two cases `test_composed_wal_payload_snapshot.py` |
| P2 | Real installer marker fixture reports no current/previous version | Collector used ProgramData root and wrong marker names. Match ProgramFiles root and current.version/previous.version | `installer/collect-commissioning-inventory.ps1`; markers fixture |
| P2 | Concurrent creator after Test-Path has file overwritten | TOCTOU overwrite. FileMode.CreateNew, exclusive sharing, Flush(true), dispose; never remove another writer's file | same collector; race fixture in `installer/tests/test-commissioning-inventory.ps1` |

The lease, tape and payload tests were observed red before their fixes and green
afterward. Inventory markers and race tests were red against the immutable #179
collector and green against the composed collector. The race fixture asserts that
its concurrent creator actually ran. Existing process-crash assertions remain;
only its aggregator injection changes from a global object to a factory.

Additional interaction tests:

* `test_composed_recovery_postgres.py`: actual sender + WAL + discovery + ASGI
  ingest + fenced pool + PostgreSQL. Commit receipt, drop HTTP ACK, transfer
  CONTROL epoch, replay to new CONTROL: exactly one quarantine receipt, zero
  canonical writes, WAL ACK after matching receipt; stale CONTROL write refused.
* Same module: delayed TTL transport plus real deferred PG trigger must roll back
  receipt/canonical write after deadline; existing tests cover PG takeover races.
* `test_composed_capacity_admission.py`: byte budget rejection before admission,
  blocked full queue, cancellation retains durable WAL records.
* `test_composed_cross_repository_contracts.py`: actual pinned scientific export,
  SHA mismatch rejection, signed historical live-capability rejection, handoff
  exact-byte hashing, historical import with no LIVE promotion, actual SQLite
  source read-only enforcement, no invented missing-source data; synthetic psycopg
  adapter checks read-only options, timeout, bound parameters and milliseconds.
  All ten tests forbid socket connections. PG adapter options are tested with a
  fake connection, not a production role/permission audit.

No cross-repository implementation defect requiring another PR was confirmed.
This does not imply all external repository behavior is audited.

## Files changed and commands

Changes above the composed merges: `grid/fenced_ingest.py`, `grid/worker.py`,
`grid/collection_ownership.py`, inventory collector/fixture, both CI workflows,
`tests/test_public_trade_capture.py`, six `tests/test_composed_*` modules and this
report. The complete inherited diff is reproducible with
`git diff --name-only fe9f3f09dd4f950663c2cb782d30da3067546d5a HEAD`.

Local Windows Python 3.12 environment: `GRID_SHARED_TOKEN=test-token`,
`GRID_REQUIRE_COMPOSED_GATES=1`, TEMP/TMP and ProgramData point to workspace test
directories; AUDIT_GRID_ROOT is this checkout, AUDIT_STRATTESTER_ROOT and
AUDIT_TERMINAN_ROOT are detached pinned checkouts listed above.

```text
python -m pytest -q --ignore=tests/test_server_pilot_postgres_integration.py --ignore=tests/test_enrollment_postgres_integration.py --ignore=tests/test_floating_leader_postgres_race.py --ignore=tests/test_ml_dispatch_lock_postgres.py --ignore=tests/test_ml_lease_lifecycle_postgres.py
pwsh -NoProfile -File installer/tests/test-commissioning-inventory.ps1 -Scenario all
python -m compileall -q grid tests run_worker.py run_coordinator.py
git diff --check
```

The local command deliberately excludes five modules requiring PostgreSQL; other
PG tests skip without DSN. This is **not** a full PostgreSQL result. Initial local
composed baseline: 1146 passed, 26 skipped, 7 subtests. Subsequent local result
before final payload/read-only additions: 1159 passed, 28 skipped, 7 subtests.
Final local run: **1163 passed, 28 skipped, 7 subtests passed**, 23.70 s; four
FastAPI lifecycle deprecation warnings. Inventory fixture, compileall and diff
whitespace check pass. Final results and exact-head checks are recorded in PR #180 and the accompanying
final evidence artifact; this tracked report cannot contain its own future SHA.

CI `.github/workflows/preflight.yml` runs unfiltered `python -m pytest -q` on
Linux Python 3.11 AND 3.12 with disposable PostgreSQL 16 and additional explicit
PG/ownership/replay/migration/failure gates. Windows tests are the specified
matrices/subsets, not full PostgreSQL pytest on Windows. Inventory fixture runs
on PowerShell 7 and Windows PowerShell 5.1. Commissioning and composed safety
workflows remain independent. Test skips are reported, not counted as success.

## Actions evidence (first composed cycle, not proof for later HEAD)

All four runs below have exact `head_sha`
`d1f313d3babc68f3cacd6c95be6fbbff0efb03c2`, status completed, conclusion success.
This cycle includes lease/tape/inventory fixes and real PG interaction tests.
Python 3.11 full pytest log: **1178 passed, 12 skipped, 7 subtests passed**.
The PostgreSQL ERROR lines are intentional cancellation/read-only/injected-failure
scenarios; tests pass, not suppressed errors.
Subsequent payload/contract additions require a new full cycle. The final PR
checks/evidence identify its exact HEAD; these earlier runs do not substitute it.

| Workflow | Run ID | Conclusion |
|---|---|---|
| preflight | [38470083040](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/38470083040) | success |
| windows-bundle | [38470083337](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/38470083337) | success |
| commissioning-manifest | [38470083099](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/38470083099) | success |
| composed-safety-gate | [38470083150](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/38470083150) | success |

Source #173–178 checks were green at their snapshot. #179 composed gate was red
(run 38449307989) because its source tree was not composed; that source PR was
not changed, its gate not disabled. Only composed PR results count here.

## Requirement coverage and remaining BLOCKERS

| Requirement | Demonstrated scope | Unproven guarantee / BLOCKER |
|---|---|---|
| 1 raw before aggregation | valid trade/order-book capture and crash tests | B2: no proof of every exchange stream, malformed frame preservation or events lost before append; ticker raw coverage incomplete |
| 2 durable ACK | fsync error uncertainty, receipt/digest gates and replay | B1: actual power-cut, controller cache and filesystem directory durability untested |
| 3 connection loss | lost ACK/long outage/process recovery synthetic gates | B2: upstream disconnect continuity cannot be inferred from WAL durability |
| 4 current CONTROL | discovery + takeover + real sender replay | B6: real Tailscale/SSH/DNS partitions not commissioned |
| 5 stale CONTROL | persisted epoch and PG takeover/deferred commit tests | B4: arbitrary writable DB credentials or old binaries bypassing cooperative fences |
| 6 stale ML/strategy | independent writer fences and lease tests | B4: real fleet/role permissions not inventoried |
| 7 quarantine isolation | receipt/replay tests show no canonical promotion | no production retention/privilege proof; B3/B4 remain |
| 8 replay duplicates | same delivery ID dedup and collision checks | pre-WAL upstream duplicates with distinct IDs not globally deduplicated |
| 9 bounded storage | WAL byte ceiling and bounded queue admission | B3: DB quarantine receipts/retention remain unbounded; disk/fsync/probe throughput capacity unknown |
| 10 archive fencing | stock standalone writer refuses activation; lifecycle tests | B4: direct SQL using arbitrary credentials is not prevented by Python guards; safe activation adapter not enabled |
| 11 migration 47 | upgrade/idempotency/catalogue refusal in disposable PG | actual production migration/recovery is not performed or certified |
| 12 old versions | old endpoint receipts rejected, WAL retained, stale fenced writers refused | B5: rollback scripts do not enforce fencing capabilities of arbitrary legacy releases |

**B1**: process kill is not physical power-loss proof. No real reboot/power-cut run.
**B2**: raw capture is a scoped evidence guarantee, not lossless exchange history.
**B3**: quarantine growth needs an approved retention/admission design and capacity
measurement. No automatic purge, data deletion or canonical rewrite was introduced.
**B4**: commissioning must stop legacy CONTROL/worker/archive writers and enforce
DB role restrictions. A software token is not a security boundary against a role
that can issue arbitrary SQL. Real fleet state and privileges are unknown.
**B5**: rollback only to reviewed migration-47/fencing-compatible releases; arbitrary
old-version deployment cannot be called safe. Do not drop migration rows/tables.
**B6**: manifest validation checks structure and SHA strings, not commit existence,
artifact authenticity or actual production compatibility. Pinned CI checkout is
separate evidence. Network/deployment processes require commissioning.

These blockers prohibit a production-ready claim even with all Actions green.

## Safe one-PC commissioning plan (requires separate external authorization)

1. Use isolated non-trading Windows fixture, disposable PostgreSQL, separate paths
   and test credentials. No production DSN, keys or services. Pin all three SHA
   values, verify artifact hashes, capture inventories with exclusive output files.
2. Review DB roles and stop all legacy fixture writers. Preserve backup, WAL,
   receipt counts and checksums. Verify migration 47 idempotency and restore on the
   disposable copy. Measure free disk and sustained capture/fsync/queue capacity.
3. Run PS 5.1/7 fixtures and Python matrices, two CONTROL processes, lease expiry,
   delayed commit, stale return, killed collector, lost ACK, replay corruption and
   bounded admission. Assert no dual owner/canonical stale write and no automatic
   quarantine promotion. Compare pre/post evidence counts and payload hashes.
4. Real OS reboot/power-cut and filesystem durability tests are a separately
   authorized phase with sacrificial test data/hardware. Record actual observations;
   process termination alone does not close B1. Never clear uncertain WAL.

## Conditions for two-PC tests

One-PC gates and restore evidence must pass first; pinned builds must match;
legacy writers must be confirmed stopped; both machines use one authoritative
PG ownership store and restricted roles; capacity limits must be measured.
Then exercise concurrent candidates, per-symbol transfer with live old lease,
network partition before/during/after delivery, PostgreSQL outage, takeover and
old CONTROL return, lost ACK across machines, replay and delayed COMMIT.
Record process/session/epoch/generation and DB receipt/canonical counts. Actual
Tailscale/SSH configuration or PC service changes require explicit authorization.

## Rollback plan

Stop new admission in the isolated test environment; preserve WAL, DB receipts,
inventory and backups. Drain only through verified receipts; allow authoritative
leases to expire before starting a successor. Select a reviewed migration-47 and
protocol-1 compatible release with verified artifacts. Retain schema/data and
migration ledger; no destructive downgrade or WAL cleanup. A legacy capture
endpoint returning 404/missing protocol must leave WAL unacknowledged. Standalone
archive writer remains disabled. Verify restore and replay on a copy before any
external rollback. Failure of compatibility/ownership checks blocks rollback.

## Complete composed file inventory

```text
.github/workflows/commissioning-manifest.yml
.github/workflows/composed-safety-gate.yml
.github/workflows/preflight.yml
.github/workflows/windows-bundle.yml
docs/ALL_MACHINE_INVENTORY_TEMPLATE.csv
docs/AUDIT_ROLLOUT_READONLY.md
docs/AUXILIARY_WRITER_GATES.md
docs/COMPOSED_INTEGRATION_AUDIT_2026_10_13.md
docs/INDEPENDENT_WRITER_FENCES.md
docs/PRE_AGGREGATION_CAPTURE.md
docs/THREE_REPO_COMMISSIONING_GATES_2026_10_13.md
docs/WAL_PROCESS_OWNERSHIP.md
grid/active_control.py
grid/archive_service.py
grid/collection_ownership.py
grid/config.py
grid/coordinator.py
grid/db.py
grid/fenced_ingest.py
grid/job_write_fence.py
grid/micro_event_storage.py
grid/microstructure.py
grid/ml_training_worker.py
grid/ml_transport_client.py
grid/segment_wal.py
grid/storage.py
grid/strategy_executor.py
grid/strategy_jobs.py
grid/strategy_runner.py
grid/strategy_runtime.py
grid/wal_directory_owner.py
grid/worker.py
installer/collect-commissioning-inventory.ps1
installer/commissioning_manifest.py
installer/tests/test-commissioning-inventory.ps1
tests/test_active_control_routing.py
tests/test_auxiliary_writer_lifecycle.py
tests/test_capture_evidence_postgres.py
tests/test_capture_invalid_json_values.py
tests/test_capture_sender_version_gate.py
tests/test_command_ack_http_status.py
tests/test_commissioning_manifest.py
tests/test_composed_capacity_admission.py
tests/test_composed_cross_repository_contracts.py
tests/test_composed_lease_deadline.py
tests/test_composed_recovery_postgres.py
tests/test_composed_safety_gate.py
tests/test_composed_tape_ownership.py
tests/test_composed_wal_payload_snapshot.py
tests/test_control_runtime_postgres.py
tests/test_coordinator_health.py
tests/test_migration47_upgrade_postgres.py
tests/test_ml_publication_fence.py
tests/test_owned_wal_receipts.py
tests/test_public_trade_capture.py
tests/test_raw_writer_fences_postgres.py
tests/test_raw_writer_readonly.py
tests/test_transport_takeover.py
tests/test_wal_bounded_tail_repair.py
tests/test_wal_process_ownership.py
```
