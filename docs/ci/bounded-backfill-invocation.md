# Bounded operator backfill invocation

The explicit unmanaged backfill command limits the entire invocation to its literal integer max_pages (1 through 50). Successful chunks consume that shared page budget. A known page or capability error retains the existing retry scheduler state and ends this invocation; only a later explicit invocation retries it. Cancellation still propagates without changing the task to a known failed outcome or synthesizing an acknowledgement. Existing page persistence and launch/coverage policies are unchanged.

Four inert coroutine regression cases exercise the public worker with fake pool/page boundaries and no event loop, provider, PostgreSQL, process, or native operation. These are source-control checks, not operational backfill qualification.
