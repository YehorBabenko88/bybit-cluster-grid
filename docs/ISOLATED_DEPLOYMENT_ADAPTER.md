# Isolated deployment adapter: preparation and recovery

This adapter prepares an offline lab layout for one dedicated Windows PC. It does not install or activate Grid. It does not initialize/start PostgreSQL, run SQL, download/extract a release, register a task, invoke a production launcher or delete anything. These steps remain blocked pending separate review and exact-target approval. LS5/LS7 and production must not be used. PR #189 is the source framework; base SHA e17ab0ca599cebfdb8ce1535a23915f2b5e3acfa.

## Architecture and safety invariants

- `installer/isolated-deployment.ps1` defaults to PlanOnly, with no host providers, GitHub calls or filesystem writes. It emits the complete deterministic plan, its SHA256 and explicit PREPARE/RETIRE approval strings.
- `isolated-deployment-core.ps1` reconstitutes the plan before any operation and rejects altered/extra fields. Approval binds the node, run ID, parent, role, candidate SHA/branch and both ports. An approval token is explicit operator intent, not an authentication credential. Do not pipe a generated token automatically into Prepare.
- Prepare acquires both existing release-switch and task-preparation mutexes. It reuses the shared Runtime Guard without modifying it. It checks the actual computer identity, task actions/names, processes, services and TCP/UDP ports. Provider errors, incomplete identities, unknown PostgreSQL command lines and any resource collision block writes. Existing PostgreSQL instances are never contacted or stopped.
- The parent must already be an operator-reviewed physical local directory named GridLab. The adapter does not create or adopt that parent. Protected path components, short-name aliases, alternate separators, reserved names and redirected ancestors are refused. The run/node leaf must not exist; no resume, overwrite or -Force is supported. Each file uses CreateNew. Parent creation and access-control review need separate approval.
- Before its first write, Prepare calls the unchanged `stage-github-release.ps1` in read-only discovery mode with exact branch/SHA, then repeats host checks under the mutexes. The existing policy is authoritative; failed/unknown latest CI or an unapproved branch blocks preparation. There is no local-artifact provenance flag, policy override or automatic download. The adapter branch follows the existing audit/codex-* allowlist; PR189's audit/physical-deployment-harness branch itself remains disallowed as a staging candidate.
- The layout contains no active .env or release pointer, no executable task actions and no credentials. All configuration files have .template or .plan.json suffixes. Empty PostgreSQL directories are not proof of an initialized or compatible server. No database exists after Prepare.
- Offline integrity preflight delegates to `windows_preflight.validate_release`, the same modern commissioning validator. It never imports target code or checks a database and cannot authorize activation. It does not replace later dependency/schema/runtime checks, bundle verification or staging policy.
- Existing install.ps1, preflight.ps1, release guard, staging, switch, rollback and recovery scripts are unchanged. Production launchers use production environment paths and MUST NOT be used to launch this layout. Future isolated launchers require explicit path plumbing for every storage/artifact/retention path; changing ProgramData globally is forbidden.

## Layout and resource identities

For an approved parent D:\GridLab, unique 32-digit hexadecimal run ID and node LAB0, the leaf is D:\GridLab\<run>_LAB0. It contains:

- owner.jsonl: durable append-only ownership state, separate from the existing release switch journal.
- deployment-plan.json: exact approved identity and blockers.
- isolated.env.template: inert planning hints; not a complete runnable environment.
- postgresql.conf.template: loopback-only proposed port and dedicated PGDATA, not an initialized cluster config. TLS certificates/authentication are not provisioned.
- tasks.plan.json: unique BybitClusterGridLab_<run>_<node> names, disabled/unregistered, no actions/triggers.
- releases, data, data\wal and postgres\data: new empty owned directories.

PostgreSQL and Coordinator ports must differ and lie in 20000–49999; installed/default ports 5432/55432/55433 are excluded. All TCP states and UDP endpoints are checked. Port vacancy is a snapshot, not a reservation; recheck/bind atomically during future approved startup. Database names and task names bind both run and node. No production identity is reused.

## Read-only planning commands

These examples authorize no physical action. Substitute an actually reviewed candidate SHA and branch; placeholders intentionally are not runnable.

```powershell
$arguments = @{
  LabParent = 'D:\GridLab'
  RunId = '<new-32-character-lowercase-hex-run-id>'
  NodeId = 'LAB0'
  Role = 'CONTROL'
  Version = '<exact-40-character-candidate-sha>'
  Branch = 'audit/codex-<reviewed-candidate>'
  PostgresPort = 23001
  CoordinatorPort = 23002
}
& ./installer/isolated-deployment.ps1 @arguments
```

The output remains PLAN_ONLY even if no target parent exists; this mode deliberately does not assert physical readiness. Review the plan and target ownership/ACL evidence separately. A future approved Prepare command uses the same arguments plus `-Mode Prepare -Approval 'PREPARE:<reviewed-plan-sha256>'`. It must not be executed on LS5/LS7 or before exact target authorization. Preparation makes only the new leaf/files; it does not stage a release or create a database.

For a separately approved staged/extracted artifact, offline preflight can be run with a trusted reviewer Python, never with an unverified target interpreter:

```powershell
& <trusted-python.exe> -B ./installer/isolated_release_preflight.py `
  --release-dir <reviewed-artifact-directory> --commit <exact-candidate-sha> --role CONTROL
```

Do not call the production preflight.ps1 automatically: it compiles/imports runtime. Do not call rollback-release.ps1 automatically: CONTROL preflight can connect to a database. Their established integrity/schema rules remain required for any later separately reviewed release operation.

## Partial preparation, retries and rollback

The journal transitions are PREPARED (ownership established), COMMITTED (all inert files/directories verified), and RETIRED. Records bind the exact plan hash. Writes are flushed to disk. This is not the release prepared/committed transaction format; no release pointers are touched.

- Any existing leaf blocks Prepare, including committed, partial, retired and unknown directories. Retries never overwrite or clean up.
- A crash after directory creation but before the first complete receipt leaves an unowned orphan. Automatic recovery refuses it. Operator inspection is required; never manufacture a receipt.
- A partial valid PREPARED layout may be retired only if every present file exactly matches the plan and every directory is expected. Unexpected content, modified files, missing committed resources, reparse points, malformed/truncated journals or unknown inventory block rollback.
- Rollback requires a separate `RETIRE:<plan-sha256>` approval. It only validates and appends RETIRED; it does not delete resources, remove pending files, stop processes, change tasks, switch a release or downgrade a schema.
- The receipt is opened exclusively; its exact expected bytes and native file identity/link count are validated on that same handle immediately before append. A changed, linked or unknown receipt blocks. Repeated valid retirement verifies evidence and performs no journal write.
- Preserve the entire failed leaf and evidence. If it contains a staged release, initialized DB or WAL records, this preparation rollback refuses them as foreign; a separate recovery plan must handle that later lifecycle. Never relax the whitelist to obtain a green rollback.
- All creation is confined to the approved new leaf. The parent must have reviewed restrictive ACLs and no concurrent untrusted writer. The host mutex coordinates Grid tooling, not arbitrary administrators; this adapter does not establish an adversarial filesystem sandbox.

## One-node, then two-node gates

| Stage | Prepared by this adapter | Still required before physical testing |
| --- | --- | --- |
| One-node layout | Unique root, ports, names, empty WAL/PGDATA, inert plans | Exact PC approval, fresh inventory/capacity/architecture, restrictive ACLs and approved parent |
| Release | Existing staging policy discovery only; shared offline validator available | Explicit download/extraction approval, full bundle/manifests/dependencies and exact-head CI |
| Dedicated PostgreSQL | Separate path/name/loopback port planned; no connection | Reviewed PostgreSQL16 binaries, dedicated account/auth/TLS, verified new cluster process/data ownership before initialization or SQL; no installed cluster reuse |
| Runtime/tasks | Unique disabled task identities only, no registration | Reviewed isolated launchers and all data-path overrides; explicit registration/start permission; production environment inheritance prohibited |
| Two nodes | Distinct node roots/database/task identities; separately chosen ports | Approve second PC; satisfy one-node acceptance first, strict SSH host keys/Tailscale identities and bounded two-direction lab connectivity/recovery |
| Physical failure tests | Reuse PR189 synthetic fault framework | Separate scoped approval per injection; no real disk exhaustion, host network outage, forced reboot or production WAL replay |

Readiness remains BLOCKED until every applicable gate is satisfied. General account permission is not physical deployment authorization. No automatic progression or cleanup exists.

## Synthetic verification

The isolated adapter fixture uses real GUID-temp file creation and mocked host/GitHub boundaries. It tests default PlanOnly, approval mismatch, active/alternate tasks, provider errors, PostgreSQL identity, occupied TCP/UDP ports, late runtime arrival, staging-policy denial, complete/partial preparation, refused retry/adoption, modified content, redirected paths, short aliases, plan tampering, journal races, hardlinks and repeat rollback. A real shared preflight validates synthetic target bytes without executing them. All test roots are retained; no cleanup logic is introduced.

CI executes fixtures under PowerShell5.1/7 and additionally from the built Windows bundle with bundled Python. Python regressions cover modern integrity failures. Existing Runtime Guard, LegacyRollback, release recovery, composed contracts and disposable PostgreSQL CI remain unchanged. Record exact commit, workflow IDs and actual test counts; a green run proves only these scoped tests.
