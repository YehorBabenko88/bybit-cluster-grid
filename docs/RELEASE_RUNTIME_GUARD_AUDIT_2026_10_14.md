# Release runtime guard audit — 2026-10-14

Scope: offline code and isolated fixtures only. No LS5 installation, runtime inventory, task/service state, PostgreSQL, trading or Telegram changed. No merge/deployment. Branch `audit/codex-release-runtime-guard-20261014` builds on PR182 HEAD `b18a9d7969e61b2f17b6c57541050cd6a6ec82ec`; PR181/composed changes remain inherited without modifying their branches.

## Confirmed defects

| Severity | Reproducer before fix | Root cause | Fix/files |
|---|---|---|---|
| P1 | Synthetic Coordinator task Running, both releases valid, switch Apply changes pointer; new `test-release-runtime-guard.ps1 -OnlyCase task-running` fails `Expected switch/WORKER rejection for task-running` on base | switch/recovery never inspect tasks | common `installer/release-runtime-guard.ps1`; switch/recover invoke immediately before first atomic write |
| P1 | Python with missing CommandLine, `python -m grid.worker`, direct run_coordinator.py outside default path, console uvicorn or archive/launcher survives old narrow query | filtered Python-only query discards unknown identity and misses alternative entry points; inventory errors not reliably fail-closed | full unfiltered Win32_Process query; reject unknown Python/versioned/free-threaded/launcher identity, malformed/empty/partial inventory and provider errors; stable secret-free errors |
| P2 | rollback provider evidence gathered before switch lock, duplicated checks drift from other paths | no common transaction guard or wrapper mutex | rollback shares guard/mutex; switch independently rechecks after wrapper evidence immediately at write |

The first genuine red test was recorded after removing an incidental mock rejection of the old filtered query. A passing negative test caused by an unrelated error was not accepted as reproduction evidence.

## Safety invariants and compatibility

- Installed tasks named BybitClusterGridAgent, BybitClusterGridCoordinator and BybitClusterGridArchivePipeline, in any task folder, must all be Disabled. Ready/Queued/Running/unknown state or conflicting Enabled setting blocks. Missing tasks are allowed only after successful full task enumeration (worker/offline installations need not have all three).
- Full process inventory must succeed and contain valid process rows. All Python executable identities, including pythonw, versioned/free-threaded variants, py/pyw, plus known shell/uvicorn launchers require readable CommandLine. Known Grid modules, direct Grid script paths, run_worker/run_coordinator, imports and launcher scripts block irrespective of host executable name. Unrelated readable Python is allowed.
- Provider errors/diagnostic stream records block; raw provider diagnostics and command lines are not emitted. Missing common helper blocks Apply before any transaction mutation.
- Existing Global\BybitClusterGridReleaseSwitch stays owned through guard and transaction. Rollback holds it across its guard and nested switch; Windows same-thread recursive mutex semantics preserve both ownership levels. Tests probe ownership from another thread.
- Switch first write remains schema1 journal phase prepared. Existing previous/pending/current atomic writes and committed journal remain unchanged. Recovery first write remains previous.version, then prepared restores previous or committed finishes candidate, removes journal. File.Replace/File.Move and reparse/hash checks remain intact.
- Read-only switch/recovery plans, ALREADY_CURRENT and NO_JOURNAL paths do not mutate files or need runtime evidence. Rollback plans retain the stronger stopped-runtime requirement. No startup/stop/re-registration is performed by guard.
- Installer stages the helper before replacing persistent recover-release.ps1. New guarded recovery requires this helper alongside it; incomplete staging fails closed. Bundles already include the whole installer directory.
- An unfinished journal encountered from an enabled/running Scheduler launcher intentionally blocks automatic recovery. Recover offline with tasks separately disabled and runtime stopped; no exemption for the calling task. No-journal startup is unaffected.
- No database schema, protocol, Strattester/Terminan contract, WAL or release-manifest schema change.

## Verification

New isolated fixture: 189 counted cases (150 negative task/process cases over switch and both recovery phases/roles, 36 intermediate recovery combinations with repeated no-op recovery, rollback late-task recheck, two missing-helper refusals), plus positive switch and read-only planning assertions. Every refused operation compares the complete fixture file/hash snapshot. Synthetic providers only; no real Scheduler/CIM calls. Covers inventory errors/partial diagnostics, unknown identities and active alternative entrypoints. Existing switch/recovery/rollback fixtures remain and are now fully isolated from host providers.

Local Windows PowerShell5.1 and PowerShell7 execute the new fixture and existing switch/recovery/rollback fixtures successfully. Process-only ExecutionPolicy Bypass used for PS5.1 fixtures; system policy unchanged. CI parses all installer/tests PowerShell sources using the actual PS5.1 parser and runs fixtures under both engines. Elevated install-Apply fixture is reserved for disposable CI runner, never elevated locally.

Local Python3.12 offline suite: 1181 passed, 29 skipped, 7 subtests. Five PostgreSQL integration modules excluded locally; no local DB used. CI runs them against disposable PostgreSQL16. Existing FastAPI on_event deprecation warnings remain. actionlint checks workflows. Final exact HEAD/run results are attached to the Draft PR and exported audit report; local or earlier-head green checks are not final-head CI evidence.

Reproduce in a disposable checkout, with TEMP/TMP pointing to a writable test directory:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File installer/tests/test-release-runtime-guard.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/test_release_switch.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/test_release_recovery.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File installer/tests/test-rollback-plan.ps1
```

## Remaining risks and rollback plan

These checks are conservative local runtime evidence, not production HA proof or a security sandbox. Uncooperative administrators/launchers can start a process or re-enable a task after a snapshot without observing this mutex. Arbitrarily renamed/obfuscated/interpreted code cannot be proved absent from a command-line signature. Maintain an offline maintenance window and protected installer/release directories; no such live enforcement was changed here. Unreadable unrelated Python/shell processes deliberately block availability rather than assume safety. Real power-loss durability, provider permission coverage and production recovery are unverified.

Nothing was activated, so no runtime rollback is needed. To abandon this change, close the Draft PR and retain the base branch. If later approved for deployment, retain the reviewed helper/recovery/switch tooling together and all old releases/WAL. Under a separately approved maintenance window: disable all installed Grid tasks, stop Grid runtimes, obtain successful inventory, use guarded recovery first for any journal, run trusted rollback-release.ps1 plan for an explicitly reviewed previous SHA, then Apply only with explicit deployment approval. Do not delete journal/markers to bypass a refusal, revert to the old permissive guard, start tasks, downgrade PostgreSQL/schema or delete data. Every step remains fail-closed; investigation precedes retry on an unknown state.
