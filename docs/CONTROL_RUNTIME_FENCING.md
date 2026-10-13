# CONTROL runtime fencing

`run_coordinator.py` continues to serve the same FastAPI app. Startup performs
serialized/idempotent schema bootstrap, wraps the existing Database pool, and
starts the existing FloatingLeader election loop. It does not initialize singleton
services before gaining a lease. Each CONTROL process uses a unique owner ID.

The elected epoch initializes the existing universe/rebalance, Telegram, retention,
maintenance, ML and scientific tasks. Tasks inherit an immutable epoch context.
Loss revokes its token before cancelling/joining services. Cleanup failures retain
handles and block restarting services. PR #169 is a base dependency rather than
another copy of its cleanup patch.

Every runtime pool acquisition checks owner, epoch and database-clock lease under
a shared lease-row lock, starts an encompassing transaction, and checks again
before commit. Its lease timeout covers COMMIT and deferred constraints. Nested
SQL remains on the same connection. Renewal uses the raw pool and a separate
post-lock database-clock check. Startup, SQL and cleanup are bounded.

Pure ASGI middleware binds the current epoch. Followers return 503 for management
and ingestion; health remains read-only and reports actual DB leadership. Control
POST responses are held until the enclosing fence transaction commits (2 MiB
response limit). Ingest independently commits its full fenced transaction before
publishing analytical caches or returning a durable receipt. Telegram command
side effects use the same effect guard. No FastAPI BaseHTTPMiddleware task hop or
uncommitted successful response is used.

## Compatibility and operating limits

- Existing read-only market tables and research schemas are unchanged.
- R2 ownership protocol and additive migration47 require coordinated rollout.
  A downgrade target must know migration47; old binaries fail closed rather than
  treating unknown schema or unfenced payloads as live. No destructive downgrade
  migration is provided.
- Raw schema bootstrap is intentionally not a managing singleton effect.
- Lease/share locks and bounded transactions prioritize safety over availability.
  Initialization that exceeds half the 20-second lease is cancelled and retried.
- This PR does not configure a floating network endpoint, client leader discovery,
  Tailscale routes or Windows services. Clients still need a route to the active
  CONTROL. A standby URL returns 503 safely; it does not redirect to an unverified
  host.
- External HTTP notifications and detached deployment/SSH processes cannot gain
  exactly-once delivery or OS-level cancellation from a DB transaction. Launches
  are guarded; remote job/result fencing and existing update safeguards remain
  separate. Physical reboot, fsync/power-loss uncertainty and release installation
  have not been production-certified.
- Quarantined WAL remains durable and explicitly excluded from live statistics.
  Automatic historical reconciliation/garbage collection is not enabled.
- Filesystem maintenance checks its conservative local epoch deadline immediately
  before each unlink/rmdir, so a blocked event loop cannot admit subsequent deletes
  after expiry. One already admitted OS syscall may finish after the deadline;
  takeover stays blocked by the lease-row lock until its guard exits. Recursive
  release-tree cleanup has no per-file cancellation boundary and is deferred to
  the stopped-service/offline update path while CONTROL runs.

Tests cover two election runtimes, takeover, revoked and stale task epochs,
synthetic PostgreSQL transport outage/recovery, long transactions, deferred COMMIT,
actual HTTP ingestion and real candle/footprint/feature/POC/cache rollback. CI must
pass on the exact PR head; these tests do not prove production HA.
