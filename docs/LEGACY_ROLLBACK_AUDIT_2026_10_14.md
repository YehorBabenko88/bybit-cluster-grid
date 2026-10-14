# Version-aware historical rollback audit — 2026-10-14

Branch `audit/codex-legacy-rollback-20261014`, based on PR183 HEAD `f6047276b9be3caad190b4f68ee7945d11641b42`. Audited rollback-release.ps1, switch-release.ps1, recover-release.ps1 and windows_preflight.py. Related open PRs and actual source HEAD read first. No installed LS5 files, services, tasks, production database, release pointers, trading or Telegram changed. No merge/deployment.

## Findings and reproduction

**P2: modern protocol requirement rejects valid historical rollback targets.** Both `9ab1f5b85ec471ea21ec89f1b76740c0b01537b6` and `2017ed4fd16b0b222173a6d42b5bf24b2beb73ac` legitimately lack grid/control_runtime.py and grid/collection_ownership.py. Default preflight reports RELEASE_PROTOCOL_FILES_MISSING on intact synthetic packages from these identities. This is a protocol capability mismatch, not evidence that an old package is corrupted. New explicit profile has a red-first regression before implementation; both roles/identities now pass integrity verification under the legacy flag while default modern checks remain strict.

Historical Git objects were read without executing them. Both migration catalogues contain exactly migrations1–34 and equal the reviewed current catalogue prefix including SQL statements. SHA256 of LF migration source in both is `092c39b895ca06a6af6d05ace5b0302c9aa4fb0f925e5c4eb3e069a30c23cff2`. Test fixture is this original text, not executable test imports. Synthetic test manifests are newly created test data; no installed/historical manifest is rewritten.

**P1: historical recovery silently accepts missing manifest.** Existing generic recovery permits manifest-less older installs. A new real-switch/recovery test demonstrated that removing the reviewed historical candidate manifest after committed switch still allowed recovery writes. Requiring the manifest for either reviewed historical target/fallback makes this test green without modifying the journal or atomic write logic. Other pre-existing manifest-less compatibility is unchanged.

## Implemented contract

- `rollback-release.ps1 -LegacyRollback` is the explicit supported historical path. Python receives `--legacy-rollback`; missing modules never automatically select it. Only the two complete reviewed SHAs are accepted. Unknown SHA fails closed. Both CONTROL and WORKER must check the database; missing DB evidence blocks even a plan.
- Target integrity still requires full manifest SHA256 verification, role entry point and grid role module coverage, migrations/db/retention source coverage, physical paths and no unverified Python. Duplicate JSON keys now block. Old manifests are neither expanded nor rewritten to invent missing modules.
- Legacy migration source is parsed as an AST literal, never imported/run. Its34 tuples including names and SQL must exactly match trusted migrations1–34. Current trusted catalogue must have47 entries. No target installer/migration is executed.
- DB check uses only a read-only transaction: correct Grid database identity, full trusted catalogue1–47 including names, current required table/column types, quiescent gate, plus no unexpired collection ownership or service leases. Missing/unknown schema, permission/error, active gate/lease fail closed. No downgrade, deletion, DDL or runtime state mutation.
- Output explicitly says `rollback_scope=offline-pointer-only`, `legacy_rollback=true`, `activation_authorized=false`. Wrapper validates this evidence before allowing the existing switch path. Exit0 is not authorization to start an old runtime lacking fencing. Runtime compatibility of old collection/CONTROL code on a live modern fleet is not claimed.
- Existing common Runtime Guard remains unchanged: all installed three named tasks Disabled; full process inventory; active Grid or unreadable Python identity/inventory errors refuse. It still runs under the existing mutex immediately before first write. Plan-only remains the default.
- switch-release.ps1 required no changes: it already verifies historical role entry points/manifests without demanding new protocol modules. It remains a low-level guarded file transaction, not the schema-aware rollback entry point. Operators must use the reviewed rollback wrapper for this legacy operation.
- Journal schema1 prepared/committed and File.Replace/File.Move remain unchanged. Prepared recovery restores previous; committed completes candidate; repeated recovery is a no-op. No automatic service restart, activation or release cleanup.

## Tests and evidence

Python3.12 offline suite:1199 passed,29 skipped,7 subtests; five PG-specific modules excluded locally and remaining DB tests skipped without disposable DSN. No local DB contacted. Targeted Python legacy/current preflight tests32 passed. Existing FastAPI deprecation warnings retained.

Actual Windows PowerShell5.1 and PowerShell7 each run36 synthetic integration cases through real Python preflight/rollback/switch/recovery: both SHAs/roles, successful default plan and explicit pointer Apply, schema34 rejection, corrupt package, active process, Ready task, missing explicit flag, prepared interruption, committed recovery and repeated recovery, absent legacy manifest. DB and OS providers are synthetic; no real Scheduler/CIM/DB call. No target code runs. Existing switch/recovery/rollback and195 Runtime Guard cases also pass both engines; PS5.1 parses installer/test sources. actionlint verifies workflows.

Disposable PostgreSQL CI extends existing random-schema test: clean/repeated schema47 bootstrap, successful read-only legacy check, active lease refusal, incompatible catalogue refusal, sentinel rows and47 migration records retained. CI—not a production DB—executes test setup/teardown. All final-head workflow/run evidence is recorded in PR and exported final report; earlier/local results do not substitute for exact-head checks.

## Reviewed commands (not executed against LS5)

Run from a separately reviewed current bundle/tools directory using its trusted Python/checker, never from the historical target installer. After separately approved offline maintenance has disabled all installed Grid tasks and stopped runtime, use the wrapper **without Apply first**:

```powershell
# Substitute one of the two complete reviewed SHAs explicitly.
.\installer\rollback-release.ps1 -ReviewedVersion '9ab1f5b85ec471ea21ec89f1b76740c0b01537b6' -Python '.\runtime\python.exe' -Role CONTROL -LegacyRollback
# Alternative reviewed identity: 2017ed4fd16b0b222173a6d42b5bf24b2beb73ac
```

Do not add Apply or start services without separate deployment approval. Resolve an existing switch journal through the reviewed recover-release.ps1 first, with runtime disabled/stopped. Do not remove journal/markers or regenerate an installed manifest to force a pass. Missing/corrupt historical integrity evidence requires investigation. Existing Telegram/trading credentials or insufficient DB permissions remain legitimate blocking conditions; this change does not edit them.

## Remaining risks and rollback of this change

Legacy rollback here restores only the offline release pointer. Old code lacks the modern fencing/ownership capability; activating it on a live fleet remains prohibited pending a separate compatibility/operational review. The DB and OS observations are snapshots: an uncooperative external launcher or remote node could change state afterward. Maintain an exclusive maintenance window; this read-only change creates no distributed DB lock or operational enforcement. Manifest hashes assume a trusted reviewed package/installer and protected directories; they are not a signature authenticity system. Dependency checks validate the trusted preflight runtime, not a promise that the historical runtime is production-safe. Actual installed artifacts, physical power loss and LS5 recovery remain untested.

Nothing was deployed, so abandoning this change means closing the Draft PR. Retain PR183 runtime guard and all releases/WAL/schema47. After any future separately approved pointer operation, use existing guarded recovery before another switch; use the reviewed wrapper and reviewed prior compatible SHA to restore a pointer. Do not downgrade migrations, delete data, weaken guard or enable tasks to bypass a refusal.
