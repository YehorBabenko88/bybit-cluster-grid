# Read-only rollout and rollback review — 2026-10-13

This is a preparation/runbook artifact. No live inventory, exchange request,
database mutation, service stop/start, deployment, merge or rollback was executed
by this audit. Actual fleet membership, deployed SHAs, DB roles, free space and
Tailscale reachability remain UNKNOWN. The machine inventory template must cover
EVERY CONTROL, worker, observer, archive process and independent research writer;
an unlisted/offline machine is a blocker, not evidence that it is stopped.

## Inventory evidence and preconditions

Use ALL_MACHINE_INVENTORY_TEMPLATE.csv. One row per machine/process role, including
powered-off PCs and duplicate manual processes. Required evidence: host and node
identity, role, observed UTC time, selected release SHA and manifest digest,
Python version, process IDs, launcher version, scheduled task MultipleInstances
policy, all WAL roots and their owning PID, disk space and pending bytes,
CONTROL candidates, PostgreSQL writer roles, migration maximum, ownership session,
lease generation, quarantine bytes/count/oldest receipt and known rollback target.
Private addresses, tokens, DSNs and credentials must stay out of published files.

Example read-only Windows inspections (operator executes; audit did not run them):

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Select-Object ProcessId,ParentProcessId,ExecutablePath
Get-ScheduledTask | Where-Object TaskName -Like 'BybitClusterGrid*' |
  Select-Object TaskName,State,@{n='MultipleInstances';e={$_.Settings.MultipleInstances}}
Get-Volume | Select-Object DriveLetter,Size,SizeRemaining
```

Inspect selected release/manifest hashes without reading environment files or
printing process command lines. Operator-owned Tailscale inventory may be read
and redacted; do not assume SSH reachability means the task is fenced or stopped.
WAL inspection must not instantiate SegmentWAL against a running production root:
its recovery can repair tails. Inspect metadata or a separately authorized copy.

Read-only database evidence, against an operator-selected connection only:

```sql
BEGIN READ ONLY;
SELECT version,name FROM schema_migrations ORDER BY version;
SELECT service_key,owner,lease_until,metadata FROM service_leases;
SELECT symbol,owner,session,generation,lease_until FROM collection_ownership;
SELECT disposition,count(*),min(created_at),
       sum(pg_column_size(payload)) AS payload_bytes
  FROM collection_ingest_receipts GROUP BY disposition;
SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolcanlogin FROM pg_roles;
ROLLBACK;
```

On a schema below47, the last two ownership queries may not exist; record this
and stop that check. Large exact counts can burden PostgreSQL: obtain a query
budget from the operator, otherwise use catalog size estimates. No CREATE,
ALTER, UPDATE, DELETE, migration function or live WAL recovery belongs to this
read-only phase.

## Version and mixed-runtime gates

1. Review exact PR head SHA and workflow head_sha; a green older run is invalid.
2. Confirm #173 runtime fencing, migration47 catalogue support, ownership protocol1,
   #174 OS WAL ownership and supervised failure behavior in every selected binary.
3. #175 requires runner and strategy child upgrade together: original attempt and
   assigned node must be passed. Unknown/missing identity fails closed. Arbitrary
   plugins with writable DSNs can bypass Python API guards; restrict DB roles.
4. #176 requires CONTROL capture_evidence_protocol1, /ingest/capture, evidence-only
   quarantine receipts and sender version checks. New worker + old CONTROL has no
   live grants and capture replay retains WAL on404. Old worker + new CONTROL is
   compatible with existing protocol1 but has no pre-aggregation capture guarantee.
5. Optional COORDINATOR_CANDIDATES is a JSON array of at most eight explicit
   HTTP(S) origins. All candidates must expose fresh health owner+epoch metadata.
   Empty list retains the single-endpoint behavior, which does not provide routing
   HA. Credentials are sent only to an explicitly configured selected origin.
6. Before any separately approved rollout: prove old unfenced CONTROL and all
   old raw DB writers are stopped. Windows IgnoreNew and the new advisory OS lock
   do not constrain legacy binaries that ignore them. Check manual process launches
   and all disconnected/rejoining PCs. Stop-old-CONTROL is a hard precondition.

The architecture remains cooperative. Injected FencedPool cannot constrain
unmodified binaries or arbitrary direct SQL. ArchivePipeline has its own raw pool
and can materialize canonical candles; inventory and the separate raw-writer
review must account for this process, not just coordinator/worker roles.

## Staged review gates before deployment authorization

Phase A: collect read-only inventory and establish every machine's status. Review
all writer roles, backups, rollback artifact SHA and matching Python/runtime.
Unknown/offline old writer or missing inventory prevents advancing.

Phase B: in disposable CI schemas, apply actual migrations1–46, seed canonical
data, apply47 concurrently and verify retention. Replay legacy WAL into quarantine.
Present a pre47 migration catalogue: it must refuse unknown47 without deleting
data. Reapply47 idempotently. Unit schema guards alone are insufficient.

Phase C: use synthetic two-CONTROL election, takeover, expired epochs, row-lock
waits, deferred COMMIT, PostgreSQL transport failure, process-kill WAL recovery,
pre-aggregation evidence and mixed-version replay tests. Run Linux Python3.11/3.12
and Windows gates at the reviewed SHAs. CI is not a production HA certificate.

Phase D: benchmark source frame rate, fsync latency, WAL/quarantine growth and
CONTROL throughput using synthetic recorded messages. One fsync per frame has
not been fleet-benchmarked. Demonstrate capacity for the intended outage horizon
and leave an explicit reserve. Check external Strattester/Terminan read-only
contracts using synthetic packages; research output never grants trading rights.

Phase E: prepare a concrete release and per-machine sequence for owner review.
Future deployment requires separate authorization. No release pointers, tasks,
DBs or fleet commands are changed by this document or audit.

## Observability and stop criteria

Use configured thresholds, not newly invented production guarantees. Existing
CONTROL lease20s / renew5s and symbol lease30s are defaults; inventory overrides.
Current source/WAL guarantees stop at successful fsync; receipt guarantees stop
at committed digest-bound storage. An uncertain COMMIT needs idempotent readback.

| Signal | Review/stop criterion | Evidence |
| --- | --- | --- |
| CONTROL health | More than one active candidate, no active candidate, or missing owner/epoch: admit no managing request | Uncached read-only health and lease evidence |
| Singleton cleanup | Any cleanup failure: old runtime stays unready; no restart until cleanup completes | leader_loss_retry_failed / runtime state |
| Ownership | Any duplicate live symbol owner or stale generation accepted: stop gate | DB lease/receipt and concurrency tests |
| WAL | Faulted spool, duplicate/regressive ID, owner-lock contention or critical ratio: no new admission | spool_faulted, spool_ratio, wal pressure logs |
| Heartbeat | Assignment freshness must remain below configured expiry; no lease extension from delayed response | request-start and ownership deadline tests |
| Quarantine | Growth crosses operator-approved budget/reserve: stop new capture/collection, retain pending WAL | bytes/count/oldest age and projected fill time |
| DB/transport | 503/507, repeated ingest failures or rising backlog: retain WAL, lower workload, investigate | db_write_failed / request logs |
| Raw writers | Any unreviewed writable role/process: rollout blocked | Complete inventory and DB privileges |

Existing disk policy defaults are soft35GB, hard20GB and emergency8GB thresholds
(verify current configuration; these are not a throughput benchmark). Quarantine
budget alerts proposed below are design values to approve, not active settings.

## Bounded quarantine and reconciliation design (not implemented purge)

Measure total receipt table/index bytes as well as JSON bytes, growth rate,
oldest age and ingest/replay lag. Capacity estimate: observed encoded bytes/sec ×
outage horizon × safety margin plus measured index/WAL/database overhead. Reserve
must cover CONTROL operations and worker pending WAL; payload bytes alone are
insufficient. Suggested review levels: warn50%, inhibit new capture80%, hard stop
admission90% of an explicitly configured evidence budget. Validate with measured
growth; do not treat these proposed percentages as current enforcement.

When full: stop admission/new collection and retain existing records. Do not
delete oldest quarantine, ACK uncommitted evidence, silently truncate a payload,
or relabel historical source as LIVE. Ordered WAL may block aggregates behind
capture failures; this is an explicit availability tradeoff, requiring sizing.

Read-only reconciliation produces a manifest of node/kind/delivery ID, immutable
SHA-256, original session/generation, receive/source timestamp, reason/status,
schema/release SHA and source sequence/trade IDs. Detect duplicate IDs with
different hashes, missing ranges, malformed timestamps and stale grants. Work
from snapshots and output a proposed research-only dataset with completeness
labels; never automatically overwrite canonical candles/features. A manual
decision ledger, exports with SHA-256 and separately authorized archival retention
are future work. There is no automatic purge or canonical repair in these PRs.

## Rollback review

Rollback code only to a catalogue that recognizes47 and the relevant receipt
and WAL protocols. Migration47 is additive; retain its tables and records.
Pre47 code refuses the upgraded schema. Never DROP tables, erase schema_migrations,
rewrite generations or purge WAL to make an old release start.

Preserve ProgramData/WAL/quarantine/artifacts outside release folders. Verify
selected-release hash and compatibility before changing a release pointer in a
separately approved procedure. Capture workers replay only to /ingest/capture;
older CONTROL404 retains records. This can stop ordered replay: retaining evidence
is intentional. Old unfenced CONTROL must not be revived as a rollback target.
If a compatible rollback is unavailable, stop collection and retain state for
operator recovery. Physical Windows reboot, power loss, Tailscale/SSH outage,
detached deployment processes and all actual machine states remain unverified.
