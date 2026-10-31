# ADMINIT PostgreSQL acceptance preparation

Status: PREPARED ONLY. This document grants no connection, installation, service
change or physical test authorization. Current authorization permits cloud
implementation and preparation of this document. Do not connect to ADMINIT,
inspect its databases, copy data, install software or execute these future steps
until the owner separately approves an exact bounded acceptance session after
cloud development. No ADMINIT action was performed to prepare this document.

A single PC can test native Windows process behavior and isolated backup/restore.
It cannot qualify independent failure domains, multi-node quorum, PostgreSQL HA,
network partitions, power fencing, or survival of one/two physical-node failures.
Do not describe several local processes or containers on ADMINIT as physical HA.

## Review package prepared in the cloud

Before requesting physical-session approval, attach the reviewed immutable
release manifest, all six exact source commits/trees, artifact SHA256 inventory,
publisher pin and verified signature evidence, dependency inventory, complete
cloud test reports and rollback instructions. Preserve original recovery bundles.
Download or build source only through approved paths; an unsigned binary or a
local source test is not release admission. Preserve Windows/PowerShell/PG16 or
PG18 test statuses as PASS, FAIL or NOT_RUN independently. Native Windows tests
and any missing hosted matrix cells must not be represented as completed.

Available owned-cloud database evidence:

- Five PostgreSQL 18 roles, synchronous ANY2, real streaming replication,
  pg_verifybackup, archived-WAL named-target restore, one/two standby-loss commits,
  insufficient-standby acknowledgement blocking and restart recovery:
  `/workspace/.onboarding/mission3/pg-ha-lab-5nodes-followable/evidence.json`.
- Independent five-voter Consul exact-session/epoch guarded promotion after old
  primary plus one standby loss, survivor following, new synchronous write and
  lease-release writer fencing:
  `/workspace/.onboarding/mission3/pg-ha-promotion-2/evidence.json`.
- These are disposable Linux cloud observations. They do not prove ADMINIT
  compatibility, owner source admission or a physical fencing provider.

The independent DCS review requires local session deadlines to be rechecked after
network reads. The callback election loop must not be used as a substitute for a
separate writer watchdog: slow initialization, cancellation or failed cleanup must
not leave a writable PostgreSQL instance without authority. Complete source
review and tests before admitting an automatic promotion path. DCS Raft indexes
and PostgreSQL resource epochs are separate fences, not a cross-resource atomic
transaction. Production hard-fence and host-watchdog backends remain separate
qualification requirements.

## Approval record to complete later

| Field | Owner-approved value required |
| --- | --- |
| Target | ADMINIT only; independently verified host identity |
| Session | Named operator, start/end window, stop contact and evidence owner |
| Artifacts | Exact approved release identifier, SHA256 and publisher pin |
| Process model | Dedicated interactive unprivileged acceptance processes; services excluded |
| Software | Exact signed PostgreSQL 18 build; PG16 only as a separately approved compatibility cell |
| Storage | New empty test-only data, archive, backup, restore and evidence directories |
| Listener | Explicit verified-unused loopback-only port for each test process |
| Identity | Dedicated approved test role/account; no existing production credentials |
| Limits | Fixed disk quota/budget, maximum WAL retention, duration and stop thresholds |
| Exclusions | Existing databases, production data, services, firewall/ACL policy and office networking |
| Rollback | Stop owned test PIDs, preserve recovery evidence; delete only separately approved test paths |
| Approval | Owner name, approval reference, exact bounded actions and timestamp |

Missing or ambiguous fields mean BLOCKED. Approval to this document or the source
implementation does not imply approval to connect, install or execute. If services,
new host privileges or network changes become necessary, stop and obtain separate
explicit authorization for those concrete changes.

## Future owner-approved isolated session

1. **Read-only preflight after approval.** Verify host identity, operator identity,
   available space, exact executable hashes/signatures, PostgreSQL versions and
   approved loopback port availability. Inventory only the explicitly approved
   locations; do not probe or enumerate real databases. Confirm each new path is
   empty, local, independently owned and disjoint from existing PostgreSQL data,
   backups, historical stores, release packages and active recovery artifacts.
   Record Windows edition/build and the exact PowerShell 5.1/7 test cell used.
   If a port/path/account conflicts or an administrative restriction blocks the
   session, stop; do not override ACLs, firewall rules, services or operator policy.

2. **Create only the dedicated acceptance cluster.** Initialize a new test-only
   data directory with the approved PostgreSQL build, data checksums and a
   restricted approved test identity. Bind exclusively to 127.0.0.1 on the approved
   unused port. Require explicit authentication; never copy the cloud lab's
   disposable trust rule into an ADMINIT configuration. Start as the approved
   owned foreground process, record PID/start time/executable hash and verify its
   data_directory, server_version, system_identifier and recovery state against
   this session's inventory. A mismatch stops the test. Do not install a Windows
   Service or alter an existing instance, PATH, system environment or startup task.

3. **Seed deterministic synthetic data.** In this cluster alone, create the
   designated acceptance database/schema and rows with known identities and
   content hashes. Record row counts, hashes and a unique marker. Do not ingest
   office/history databases, exchange data, account secrets or real credentials.
   Configure replica-capable WAL and an owner-reviewed archive command confined
   to this session's new archive directory. The command must fail on conflicting
   existing WAL bytes and surface errors; never overwrite a different WAL file.

4. **Take and verify a real base backup.** Use the approved pg_basebackup against
   this explicit loopback test cluster, a new empty backup directory and a bounded
   timeout. Capture exit status and pg_verifybackup output, backup_manifest hash,
   system identifier, timeline and covered WAL range. A backup process exit 0 alone
   is insufficient. Retain the complete base and all required WAL until isolated
   restore and application checks pass. Do not put passwords in commands or logs;
   use only the approved protected credential selector.

5. **Exercise named-target PITR.** After the base backup, insert a known
   before-target row, create a unique named restore point, then insert a different
   after-target row. Record the actual clocks/LSNs and force an archive switch in
   this test cluster. Verify archive completion and file hashes rather than
   assuming a WAL switch means archival succeeded. Restore the base into a second
   new empty directory and start a second loopback process on its own approved
   port using only the session archive. Set the exact recovery target and pause at
   it for inspection. Confirm the expected system identifier and timeline,
   baseline and before-target rows/hashes, and absence of the after-target row.
   Record actual read-only recovery status. Stop on missing/gapped/corrupt WAL,
   target-not-reached, unexpected promotion, wrong identity or data mismatch.
   Preserve the failed restore and logs; do not "repair" by copying newer data.

6. **Check negative paths within approved test directories.** If explicitly in
   the session scope, make a separate copy of the synthetic backup/archive and
   withhold one required WAL file or corrupt a copied backup file. Verify that
   pg_verifybackup or recovery refuses the copy and that the approved original
   recovery chain remains intact. Do not mutate the only backup or active restore.
   Windows process shutdown/timeout tests must address only recorded owned PIDs;
   no broad process-name termination or existing service restart is permitted.

7. **Verify bounded scheduling and retention.** Run one approved backup cycle
   using the source BackupScheduler adapters against this test cluster. Record
   create, manifest and actual restore checks separately. Preview retention with
   the source BackupPolicy; preserve latest verified restores, unverified backups,
   every base/WAL segment needed by protected PITR targets and any active restore.
   Retention is a proposal, not deletion authority. Do not delete files during
   acceptance unless a separate exact test-only deletion list is approved.

8. **Close the session.** Stop the restore process and original test process by
   recorded PID/identity and confirm their owned ports close. Preserve signed
   artifact identities, configuration hashes, timestamps, redacted logs, backup
   manifests, WAL hashes, query results, errors and exit codes. Record any
   remaining test artifacts and cleanup proposals. Keep originals until evidence
   review and separate cleanup approval. No active release, real data, service or
   recovery bundle may be removed.

## Acceptance and reporting template

| Check | Result allowed | Evidence required |
| --- | --- | --- |
| No ADMINIT action before separate approval | PASS/FAIL | Approval and session audit references |
| Exact signed artifacts and source pins | PASS/FAIL/BLOCKED | Manifest, publisher verification, hashes |
| PG18 isolated startup and owned shutdown | PASS/FAIL/NOT_RUN | PID identity, ports, version and logs |
| PS 5.1 and PS7 behavior | Separate PASS/FAIL/NOT_RUN cells | Actual version and executed checks |
| Real basebackup verification | PASS/FAIL/NOT_RUN | pg_verifybackup, manifest and WAL coverage |
| Named-target PITR application invariants | PASS/FAIL/NOT_RUN | Actual restored row hashes and target state |
| Negative backup/WAL corruption denial | PASS/FAIL/NOT_RUN | Separate copied fixture and refusal logs |
| Retention preserves all required recovery chains | PASS/FAIL/NOT_RUN | Preview, protected identities, no deletion claims |
| Multi-node HA and one/two physical-node loss | NOT_QUALIFIED_ON_SINGLE_PC | Requires separately authorized independent nodes |
| Physical fencing and automatic failover | NOT_RUN/BLOCKED here | Requires independent fence/watchdog and multi-node approval |

Current ADMINIT result: **NOT_RUN / BLOCKED pending separate owner approval**.
A successful future isolated session can establish only its executed single-host
Windows backup/restore behaviors. It cannot change the distributed HA, physical
fencing or deployment-admission status by itself.
