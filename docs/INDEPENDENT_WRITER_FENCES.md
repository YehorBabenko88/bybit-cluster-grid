# Independent writer publication gates

ML and strategy subprocesses use their own pools. CONTROL's pool wrapper alone
cannot fence these writers. Leased ML publication now locks its job row, reads
`clock_timestamp()` after the lock, validates owner/generation/status, and keeps
the lease deadline active through COMMIT. Strategy result emission applies the
same guard to assigned node and the current attempt. Attempts are returned by
UPDATE RETURNING, passed to the child process, and required for completion and
requeue. A stale child cannot bind itself to a newer attempt by fetching its ID.

`StrategyContext.fetch` executes in a PostgreSQL read-only transaction. This is
an API guarantee for cooperative plugins, not a sandbox for arbitrary Python:
plugins still receive a process environment and can access Python objects.
Production isolation requires restricted DB roles and trusted plugin review.
Unleased standalone research training retains its existing CANDIDATE path.
Neither a candidate nor a strategy result authorizes live trading.

No schema or result payload changes. The strategy runner and subprocess runtime
must be upgraded together: the runtime requires GRID_STRATEGY_NODE and
GRID_STRATEGY_ATTEMPT. Older callers of finish_job/requeue_job must supply these
identities; missing identities fail closed. Stop older independent writers before
activating a new runtime. Old binaries with writable DB access remain a bypass.

Transaction cancellation is tested using real deferred PostgreSQL triggers.
These tests do not establish lossless behavior under server crashes, power loss,
network partitions during an uncertain COMMIT, or malicious code with write
privileges. Resolve uncertain outcomes by reading stable result IDs and current
job ownership, never by silently treating a failed request as a committed result.

Reproducers: tests/test_raw_writer_fences_postgres.py (disposable CI DB only) and
tests/test_raw_writer_readonly.py. Before the fix, all three initial PostgreSQL
scenarios failed on tests-first head fb76b5bd7173ab3ed82732691c6348f409106439.
