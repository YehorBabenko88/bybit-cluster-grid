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
separately reviewed mutating offline pointer repair tool. Issue185 adds a read-only
assessment, described below; it does not implement or authorize an automated exit. Prepared recovery can clear its transaction state,
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


## Issue185: offline assessment (no repair)

The trusted `installer/assess-release-repair.ps1` is always read-only. It has no Apply
parameter and no default installed root. It never calls switch/rollback/recover, starts
services, changes markers/journals, reads an .env, connects to PostgreSQL or executes
any code from the assessed release. Use copied installation/evidence on an audit host,
not LS5/LS7 installed releases. Keep the originals, WAL and manifests intact.

The wrapper acquires Global\BybitClusterGridReleaseSwitch and invokes the existing
Runtime Guard before starting the trusted Python assessor with -B (no bytecode writes).
Active/enabled tasks, active Grid processes, unknown Python identities, failed inventories
and a busy mutex block assessment. The final report records only a point-in-time local
runtime inventory, never fleet quiescence or service restart permission.

Required parameters:
- InstallRoot: the copied installation containing releases and version/journal files.
- ReviewedVersion: explicit SHA of a separately reviewed modern fenced schema48 candidate.
- SchemaEvidence: a previously captured windows_preflight JSON report for that candidate.
- Python: explicit trusted Python3.11/3.12 executable, not a target release executable.
- Role: CONTROL or WORKER, defaults to CONTROL.

The snapshot must have schema1, mode=read-only, activation_authorized=false,
database_checked=true, status=PASS, matching RELEASE_VERIFIED version, and DATABASE_READY
with migration47 or48 and a quiescent runtime_state. Each included check must pass.
Legacy rollback evidence cannot substitute. This tool does not generate new database
evidence or instruct the operator to connect to production to obtain it. Snapshot input
is unauthenticated and may be stale: every result retains fresh DB/lease review as a
blocker. A file supplied by an operator is never proof of current PostgreSQL state.

All referenced releases require complete existing manifest/hash validation, including
both allowlisted historical identities and literal1–34 catalogue validation. The proposed
modern candidate must retain fencing modules and byte-identical reviewed migrations.py.
Unknown identities/profiles, wrong/missing files, unverified Python, duplicate JSON keys,
invalid field types, foreign/conflicting markers and changed snapshots are rejected.
No old release is imported to discover its schema or missing modules.

Recognized states:
| State | Journal target reported | Assessment behavior |
|---|---|---|
| prepared journal, partial pointer writes | journal.previous | Report only; no prepared cleanup |
| committed journal | journal.candidate | Report only; preserve pending and journal |
| committed recovery already removed journal, current=pending, previous present | current | Report only; pending remains |
| prepared recovery completed, no pending/journal | current | Report only; no activation permission |
| conflicting, incomplete or malformed evidence | none authorized | BLOCKED |

Successful inspection returns PLAN_ONLY, not PASS for repair. It always has
repair_authorized=false, activation_authorized=false, marker_removal_authorized=false,
proposed_changes=[], database_checked_live=false and explicit remaining blockers.
The output includes a deterministic snapshot hash for comparison only, not a signature
or reusable execution token. Re-running assessment changes no inputs. A changed input
requires a new assessment/review. The Python CLI alone reports runtime inventory NOT_CHECKED;
use the PowerShell wrapper to obtain guarded local inventory under the mutex.

A historical pointer remains an offline-only, unfenced runtime even when its historical
schema47 rollback profile is compatible. At schema48 the legacy rollback profile is
incompatible. In either case do not start it. Existing LegacyRollback47, fencing and
release transaction semantics are unchanged.

Synthetic verification commands (fixtures under process TEMP, no live providers):
```
powershell.exe -NoProfile -ExecutionPolicy Bypass -File installer/tests/test-release-repair-plan.ps1 -Python <trusted-python.exe>
pwsh.exe -NoProfile -File installer/tests/test-release-repair-plan.ps1 -Python <trusted-python.exe>
python -m pytest -q tests/test_release_repair_plan.py
```
The PS suite runs66 cases per engine, including every phase/role, repeated assessment,
active task/process, unknown identity, inventory errors, mutex contention, corrupt
manifest/journal, foreign pending marker and rejection of -Apply. All test OS providers
are synthetic; no installed service is inspected or altered.

Remaining operational blocker: a separately reviewed mutating pointer repair tool and
explicit maintenance authorization are still required. This assessment deliberately
does not delete pending.version to unblock normal switch.
