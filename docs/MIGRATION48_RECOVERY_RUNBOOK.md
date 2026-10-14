# Recovery after schema 48 (review plan only)

No commands in this document were executed against installed systems. Any maintenance,
service changes, database repair or pointer activation requires separate authorization.

## Safety invariants

- LegacyRollback supports database catalogue 1–47 only. Database 48 must fail closed,
  including when historical source catalogue 1–34 passes source integrity validation.
- Never delete migration48 from schema_migrations, automatically downgrade, edit an
  historical manifest, remove fencing modules, or activate an historical unfenced runtime.
- Preserve releases, local WAL, manifests, pending markers, journal and database evidence.
  A filesystem recovery success is not permission to start the pointed-to runtime.

## Staged recovery

1. Obtain separate maintenance authorization. Quiesce every Grid runtime and prevent
   scheduled restarts across the fleet. Verify Runtime Guard, active gates and ownership
   lease expiry; retain backups and WAL before any approved repair.
2. Inspect the trusted switch journal and manifests using the reviewed recovery tools.
   Recovery runs under the existing mutex and Runtime Guard. A prepared journal restores
   the previous pointer; a committed journal retains the committed candidate. Repeated
   recovery must leave the same file state. These operations do not change the database.
3. Keep runtimes disabled if the resulting pointer is incompatible with schema48.
   Select a separately reviewed schema48-aware release retaining collection ownership
   and CONTROL fencing. Rebuild and verify its complete release/bundle manifests.
4. Run its read-only modern commissioning checks and plan-only switch/rollback review.
   Require exact migration names/history, schema48 physical index validity, runtime
   quiescence and all existing lease/fencing checks. LegacyRollback is not an escape hatch.
5. After separate approval of the exact plan, perform only the approved pointer repair
   and validation. Starting any service or activating the candidate requires explicit
   authorization beyond this local audit.

## Cases requiring additional tooling/review

A committed recovery targeting an historical release preserves pending.version. The
ordinary switch correctly refuses while that marker exists. Do not manually delete it
or start the historical runtime to clear health checks. This is BLOCKED pending a
separately reviewed offline pointer repair plan/tool. The current patch does not claim
an automated exit from that state. Prepared recovery can clear its transaction state,
but a restored historical pointer still must not be activated against schema48.

If an older migration runner already recorded48 with an incorrect index, the new runner
and modern preflight reject it. Preserve evidence and obtain a separately reviewed,
authorized database repair; this patch never drops/rebuilds an existing conflicting index.

## Local synthetic evidence

LegacyRollback: 52 cases per PowerShell5.1/7: original36 plus schema48 plan/apply,
prepared/committed recovery, repeated recovery and rejected retry for both historical
SHAs and both roles. Schema48 refusal must specifically report catalogue mismatch.
Committed pending-marker refusal is asserted. Runtime Guard:195 and packaging:10 per
engine. Providers are mocked; no historical runtime or installed PostgreSQL is executed.
