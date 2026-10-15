# Issue185: read-only schema48 release repair assessment

Base:245c6691574bd1f13dba4221cc600af8b7c3d488 from audit/migration48-ci-20261014.
Branch:audit/codex-schema48-recovery-plan. No main/stacked history rewrite.

## Delivered scope

The new assess-release-repair.ps1 wrapper holds the existing release mutex, invokes
the existing Runtime Guard and runs the trusted release_repair_plan.py with -B.
Only explicit copied-install/evidence paths are accepted. There is no Apply parameter,
no database/configuration access and no invocation of switch/recover/rollback or target
Python. Successful inspection produces PLAN_ONLY with no proposed changes or mutation,
marker-removal or activation authority. Every report retains mandatory review blockers.

The assessor validates every referenced release manifest and file hash, full Python
coverage and both historical catalogue profiles; verifies exact modern48 migrations
source; parses strict/bounded JSON and canonical pointers; detects conflicting state;
rechecks full release integrity and captured metadata before returning a deterministic
snapshot digest. A prepared journal can precede the previous.version write: an older
fallback is accepted only at current=journal.previous,pending absent, and still requires
full integrity validation. Other contradictory fallbacks fail closed.

Schema47/48 snapshots are explicitly unauthenticated/offline, not proof of live DB or
lease state. A historical source catalogue34 is the separately reviewed historical
schema47 rollback profile, not a fenced schema48 runtime. It is never started here.

## Reproduction and local evidence

Test-first baseline:25 failed/23 passed before implementing safe assessment.
Independent static review then found missing final content revalidation; added a
reproducer that mutates an entry point after initial validation. Added a second red
case for the initial prepared journal boundary. Both failed before their fixes.
The reviewer rechecked the fixes and found no remaining concrete P1/P2 (static only).

Final offline Python3.12:1352 passed,46 skipped,7 subtests,4 existing FastAPI warnings.
Five PostgreSQL-only modules remain excluded; DSN and disposable-CI opt-in are unset.
The new Python assessment suite has61 cases; new PowerShell fixtures have66 per engine.
PowerShell5.1/7 use synthetic providers/files only. Static parser, compileall, actionlint
and diff whitespace checks pass. These results do not claim a real DB or installed
release recovery run.

A pre-existing test flake surfaced with the longer suite: four server_pilot negative
cases constructed heartbeat timestamps during collection. After30 seconds they tested
"offline" rather than the intended integrity/operator/trade checks. The test now creates
its heartbeat at execution time. Runtime heartbeat thresholds and safety code are unchanged.

## CI requirements

The exact new audit branch is added to the five existing push-trigger allowlists.
No original job/gate is removed. PostgreSQL remains GitHub-hosted/postgres16 behind
the inherited mandatory isolation gate. New61 tests run in the full Python3.11/3.12
suite. New66-case integration runs in both PowerShell engines in windows-commissioning,
and FROM THE BUILT BUNDLE with bundled runtime/python.exe in windows-bundle (PS5.1).
The fixture generator lives under installer/tests and is recursively packaged; existing
historical fixture/manifest packaging gates remain mandatory.

Actual Actions results must be recorded for the exact published head after execution;
no green claim is made by this pre-publication evidence document. Final run URLs and
conclusions are supplied in the completion report.

## Remaining operational blockers

This completes the requested assessment, not a mutating recovery implementation.
Committed pending.version remains intact and normal switch continues to refuse it.
A separately reviewed offline mutation tool, fresh fleet/DB/lease evidence and explicit
maintenance approval are required before any repair or activation. Snapshot consistency
is a point-in-time/cooperative check under the mutex, not protection against arbitrary
post-inspection edits by an administrator and not a reusable apply token.

See MIGRATION48_RECOVERY_RUNBOOK.md for the complete input/output and state contract.
