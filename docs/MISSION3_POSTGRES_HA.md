# Mission 3 PostgreSQL recovery boundary

Source implementation reuses Grid orchestration rather than adding another fleet
scheduler. `PromotionController` accepts async independent DCS, fencing and durable
acknowledged-LSN verifiers plus an asyncpg-compatible `PostgresAdapter`. Candidate
identity/epoch must bind to the external lease and to this database connection.
A PostgreSQL lease cannot independently elect a replacement for its own failed
primary. Unknown quorum, old-writer fence, durable checkpoint or insufficient
replay denies promotion. The fence provider must prevent the old writer restarting
throughout promotion; a stopped-process observation alone is insufficient on an
uncontrolled host. Lease/fence are revalidated before and after `pg_promote`.

DCS alternatives considered: a PostgreSQL-only lease creates a circular recovery
dependency; SQLite is not consensus; Patroni introduces its own orchestration and
additional service stack. The parallel Grid DCS work selects Consul Session/KV
with five Raft voters and consistent reads. Windows binary availability does not
establish Windows production qualification. The source callbacks deliberately
permit a verified DCS adapter without treating caller-supplied vote lists as proof.

Five PostgreSQL roles use one primary and four streaming standbys with synchronous
`ANY 2` and `remote_apply`. Two standby losses retain the required two replicas;
three losses stop acknowledgement. Primary plus one standby loss additionally
requires a caught-up candidate, verified durable checkpoint, independent live DCS
quorum, old-primary hard fencing and repointing survivors. No RPO0 claim follows
from a sampled LSN, and cancelling a synchronous commit wait does not roll back
an already locally committed transaction: clients must reconcile unknown outcomes.

`BackupScheduler` executes bounded create/manifest/isolated-restore adapters.
`BackupPolicy` schedules due intervals and proposes conservative retention; it
protects the latest restored copies, all unverified backups and explicitly required
PITR base chains. It never deletes files. A production archive backend must retain
all WAL required from the oldest protected base through each recovery target,
verify checksums, enforce quotas without deleting sole history and alert on failed
archive/restore. The actual cloud lab uses pg_basebackup, pg_verifybackup, archived
WAL and an application-level named-target restore check rather than declaring
restore success from backup exit status.

Run the owned-cloud lab explicitly:

```
python scripts/lab_ha_postgres.py --output /workspace/.onboarding/mission3/pg-ha-UNIQUE
```

It only creates uniquely labeled containers and an internal Docker network on the
managed local daemon. It never accepts an external DSN, publishes no database port
and uses a pinned PG18 image. Its trust authentication is confined to disposable
unexposed resources. Resources and failed-attempt evidence are retained for review.
No office PC, service, real database, Tailscale or deployment mutation is authorized.

Observed five-role cloud result: `/workspace/.onboarding/mission3/pg-ha-lab-5nodes-followable/evidence.json`.
Real basebackup verification, WAL PITR (before-target rows1,2 present, after-target3
absent), one/two standby-loss commits, three-loss acknowledgement blocking and
standby restart/recovery passed. This is database recovery evidence, not a completed
HA admission. Automatic DCS/fenced primary failover is separately recorded; physical
and Windows compatibility remain NOT_RUN and production NO_GO.

The promotion boundary also requires an emergency candidate fence callback. Any
unknown pg_promote outcome, cancellation or post-promotion validation failure
invokes that callback before propagating failure. Long-running operation still
requires the existing Grid lease-loss guard to fence the writer after admission;
a one-shot successful promotion is not continuous lease supervision. The cloud
promotion experiment stops its candidate before releasing its lease.


Actual primary-loss experiment passed at
`/workspace/.onboarding/mission3/pg-ha-promotion-2/evidence.json`: the independent
five-voter Consul lease and its atomic durable checkpoint bound candidate/epoch,
system identifier and container identities. Unfenced promotion was rejected.
After old-primary plus one standby loss, the caught-up candidate promoted and
two survivors followed; a synchronous ANY2 application write committed. Both
old-primary fence and DCS lease were revalidated. Releasing the actual DCS lease
then caused the local writer watchdog to stop the promoted writer. The lab leaves
no active promoted writer depending on a released lease. This demonstrates the
owned-cloud failure model; independent physical power/storage fencing, service
watchdogs, Windows compatibility, authenticated production DCS and signed host
admission remain unqualified.
