# Auxiliary writer lifecycle gate

ArchivePipeline's standalone service_loop previously bootstrapped a raw Database
and could write candles_1m/footprint_1m without the CONTROL runtime epoch. The
entry point now fails closed before database bootstrap, filesystem creation or
exchange discovery unless an existing FencedPool database is injected. Its first
filesystem admission also requires the current epoch context. The historical
algorithms and schemas are unchanged; no automatic archive-to-CONTROL relocation
or new canonical-data background task is enabled by this PR.

Operational change: the standalone Windows ArchivePipeline task cannot safely
run this writer after upgrade. It will refuse; this is an intentional capability
gate, not a transparent availability-preserving migration. Stop old standalone
archive binaries as part of the stop-old-writers precondition. Enabling a fenced
caller is separate reviewed work; do not bypass the check or revive an old raw
writer to restore archival availability. This audit did not stop any actual task.
Python guards do not constrain arbitrary SQL with write privileges. Low-level
archive functions remain usable for isolated/offline tests with synthetic pools;
unreviewed external callers and deployed DB roles remain inventory risks.

Independent train_job also always raised AttributeError at cleanup because
Database.close did not exist. That masked both successful publication and the
original training error, causing misleading failure/retry outcomes and leaked
pools. Database.close now releases the pool and clears its reference on success.
Deterministic tests exercise the actual train_job function with synthetic backend
and pool; both successful result and original error are preserved.

No live schema, task, exchange, deployment or trading action is performed.
Windows Python3.11/3.12 unit gates and disposable PostgreSQL publication gates
remain separate evidence, not a certificate of production HA or complete raw-SQL
privilege isolation.
