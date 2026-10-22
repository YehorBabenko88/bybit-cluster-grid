# PC4 DDL-free integration candidate — future operator runbook

**NOT AUTHORIZED TO EXECUTE. Physical SID/ACL 0/10 NOT_RUN.** This document
authorizes no connection, role activation, SQL, ACL change, service, installation,
deployment or trade. L1/L2 and physical deployment remain NO-GO. Owner-reported
PC4 facts are not independent host evidence. GitHub-hosted disposable PostgreSQL
tests are software integration evidence only.

Baseline: PR226 `f99f401aa11b5f0e0ed75046960801f882540216`, parent PR225
`217904071394ab8a84e5a180822081ff8e25e1e9`. Use this candidate's reviewed exact
commit, never a mutable branch name, before any future test. Previous planning
documents' DDL-startup blocker is superseded by this candidate's explicit split;
their physical authorization, integrity, rollback and identity gates remain.

## Startup audit and invariant

| Entry/path | Before | Candidate |
|---|---|---|
| Coordinator startup → service.prepare_database | baseline DDL and 1–48 migrations, retry forever | connect, read-only schema/role verification, fatal failure |
| elected start_leader_services | eight supplementary CREATE/ALTER helpers | DML-only initialization after verification |
| fleet lifecycle/reconcile | lazy fleet table/index creation per operation | existing prepared tables only |
| runtime gate state setter | lazy CREATE plus default INSERT | UPDATE only; missing gate blocks startup |
| stable rollout | lazy rollout_nodes CREATE | existing prepared table only |
| bootstrap_runtime | apply_migrations before discovery | shared read-only verification before discovery |
| direct ML training | raw connect without validation | shared verified startup |
| direct local Storage | raw pool before feature startup | shared verification and cleanup on rejection |
| DB-less Worker / MicroEventStorage | remote ingest/WAL | still DB-less, unchanged fencing/receipts |
| standalone ArchivePipeline | rejects unfenced database | rejection preserved |
| legacy import / pilot | TEMP CREATE, COPY, TRUNCATE | bounded typed-array DML; atomic conflicting-value rejection |
| schema_preparation --execute | new explicit trusted process | baseline, migrations 1–48, **all nine** supplementary helpers and owner-only seal |

DDL retained in `Database.ensure_schema`, migrations and `ensure_*` functions is
preparation code, not runtime startup. No migration SQL/name/order is rewritten.
Schema preparation uses the existing migration advisory-lock key across the
entire transaction, including baseline/supplementary objects and seal. A failure
or cancellation rolls back all of them. The nested migration lock is balanced.
Re-entry checks the seal before doing any DDL. Unknown/unsealed existing schemas
are BLOCKED: this is deliberately **not** an in-place adoption/upgrade command.

The owner-written contract binds normalized source files and a structural catalog
digest, including columns/defaults/types, constraints/validation, indexes/status,
sequences, relation owners/options/RLS, routines, triggers and policies. Runtime
also checks the exact 1–48 registry, the full migration48 index postcondition and
the runtime gate row. The seal/registry must be read-only to app, including column
grants. App must have no memberships, ownership, superuser/role/database creation,
replication/bypass-RLS authority, database CREATE/TEMP or user-schema CREATE.
Required table DML and sequence USAGE must exist. Session identity changes are
rejected. Every pool acquisition pins `search_path=pg_catalog,public` to prevent
role/DSN defaults redirecting unqualified DML.

This is a trusted-owner preparation assertion, **not** protection against a DB
owner/superuser or privileged Windows administrator. The digest is not durable
anti-rollback or a signature. No schema-2/physical isolation claim is enabled.
Runtime verification occurs at startup; it cannot freeze a malicious owner's
future DDL. Re-verify after maintenance; coordinate owner changes with shutdown.

## Commands and gates — future local PC4 session only

Every command below requires separate owner authorization. Do not run these from
SSH/Tailscale or the current Codex session. Never use transcripts, `psql -a/-e`,
credential-bearing command arguments, shell history containing passwords or
uploaded `.env`/passfiles. PostgreSQL `postgres`/`user`, other databases, PGDATA
`C:\Program Files\PostgreSQL\18\data`, its NetworkService identity, existing ACLs
and services must not be repurposed. No initdb/server upgrade is included.

### G0 — independent security and target approval

PASS requires independently verified full SIDs/tokens, new-object ACL design,
ancestor custody, Source/TEMP/evidence custody, Python/toolchain provenance,
PostgreSQL build/driver decision, stopped Grid tasks/processes and an exact SHA.
The 18.4 patch-security decision from PR226 remains open. Unknown observation is
BLOCKED; an unexpected writer, junction or identity is FAIL. The currently
wide-write `C:\GridLab\Runtime`, `PostgreSQL` and `Fixtures` are **not trusted Source**.

Proposed **new** root: `C:\Program Files\GridIntegrationLab\<approved-run-UUID>`.
It must not exist before separately approved provisioning; never adopt an
existing directory. A custodian creates and proves the new root, Source,
Toolchain, Config, State, Temp and Evidence. Do not alter existing directory ACLs.
Source/Toolchain: app read/execute only, custodian maintenance only while stopped;
State/Temp: app Modify, no executable resolution; Config: app read of its own
credentials only; Evidence: append producer plus independent custody, no overwrite.
Ancestors need protection against replacement/DELETE_CHILD, not merely a leaf ACL.
An empty/new name is not proof of custody. No ACL-provisioning shortcut is supplied.

### G1 — protected checkout and runtime

After independent provisioning, use a reviewed PowerShell process/token:

```powershell
$ErrorActionPreference='Stop'
$ExpectedSha=Read-Host 'Approved full 40-character candidate SHA'
if ($ExpectedSha -notmatch '^[0-9a-f]{40}$') { throw 'BLOCKED_SHA' }
$Root=Read-Host 'Approved new protected run root'
$Source=Join-Path $Root 'Source'
$Python=Join-Path $Root 'Toolchain\python.exe'
$Psql='C:\Program Files\PostgreSQL\18\bin\psql.exe'
Set-Location -LiteralPath $Source
if ((git rev-parse HEAD) -ne $ExpectedSha) { throw 'FAIL_CHECKOUT_SHA' }
if (git status --porcelain) { throw 'FAIL_DIRTY_CHECKOUT' }
& $Python --version
& $Psql --version
& $Python -m pip check
if ($LASTEXITCODE) { throw 'FAIL_DEPENDENCIES' }
& $Python -m grid.schema_preparation
if ($LASTEXITCODE) { throw 'FAIL_PLAN_ONLY' }
```

Last command is plan-only and makes **no database connection**. PASS requires
reviewed dependencies and approved Python 3.11/3.12; installed Python 3.14 is not
evidence of compatibility. Do not resolve new dependencies under app authority.
Unknown ACL, signature/hash, dependency or root is BLOCKED. Do not use the global
system Python or writable Source/TEMP as executable search paths.

### G2 — target identity and isolated resources

Use PR226 `planning/pc4-pg18/00_readonly.sql` with local interactive psql (`-X -W`)
to independently pin system identifier and record the non-secret receipt. Existing
role/database names must not be adopted. Follow its `10_bootstrap.sql` PlanOnly
then independently approved Execute contract, UUID, exact OIDs and cluster pins.
The only proposed database is `grid_integration_test` with separate `_owner`,
`_app` and `_ro` roles. Their NOLOGIN and connection-limit-zero staging are
intentional. No password is supplied in SQL or GitHub. All collisions, foreign
dependencies, concurrent clients and partial/unmarked resource creation BLOCK.

New root/resource creation remains a separate operation: this runbook does not
authorize that operation merely because a validation command passed. PUBLIC
access to unrelated databases cannot be removed by grants on this database;
strict cluster-wide isolation requires a separately approved design.

### G3 — trusted owner preparation (separate terminal/token)

Supply a separately provisioned protected libpq passfile for the trusted local
admin login; its content is never printed, hashed into artifacts or passed as argv.
The owner remains NOLOGIN. The trusted connection assumes it for object ownership:

```powershell
$env:PGPASSFILE=Read-Host 'Protected admin passfile absolute path'
$env:POSTGRES_DSN='postgresql://postgres@127.0.0.1:5432/grid_integration_test?role=grid_integration_test_owner'
& $Python -m grid.schema_preparation --execute --database grid_integration_test
if ($LASTEXITCODE) { throw 'FAIL_SCHEMA_PREPARATION_PRESERVE_DATABASE' }
Remove-Item Env:POSTGRES_DSN
Remove-Item Env:PGPASSFILE
```

PASS: first run PREPARED, second ALREADY_PREPARED; registry exactly 1–48 and same
source/catalog seal. No automatic repair/adoption/downgrade exists. A different
source seal is BLOCKED pending reviewed schema upgrade, not permission to reseal.
The trusted prep connection may be admin→owner; runtime must authenticate directly
as app and rejects session-user/current-user substitution.

### G4 — privileges and separate activation approval

Run the reviewed `20_privileges.sql` using PR226 cluster/OID/UUID pins and explicit
approval. This candidate revokes app writes to both registry and contract after
general DML grants. Default privileges do not override these existing revocations.
Re-run after reviewed future schema changes, never grant owner membership/TEMP.

The following are future **separately approved** local interactive psql statements,
not part of bootstrap or startup. A custodian must verify exact resource receipts:

```sql
ALTER ROLE grid_integration_test_app LOGIN;
ALTER ROLE grid_integration_test_ro LOGIN;
ALTER DATABASE grid_integration_test CONNECTION LIMIT 6;
\password grid_integration_test_app
\password grid_integration_test_ro
```

psql prompts privately; do not put values in scripts, environment logs or GitHub.
Provision separate protected app/RO passfiles through the approved secret process.
Leave owner NOLOGIN; do not reuse `postgres`/`user` as runtime identities.
Using local interactive app/RO connections, test SELECT and DML in a transaction
that is rolled back. CREATE TABLE, TEMP, ALTER/DROP, registry/seal UPDATE must fail
as app. RO may SELECT only candles_1m/footprint_1m/derivatives_metrics, cannot read
agent_credentials or write even with read-only setting off. PASS requires actual
permission failures, not inferred role labels. Missing evidence is BLOCKED.

### G5 — foreground loopback-only Coordinator

Use a new verified non-admin app-token terminal, not the trusted preparer's shell.
No Scheduler/service entry is installed or run. Independently exclude conflicting
ports/tasks/processes using existing read-only Runtime Guard; do not bypass it.

```powershell
Set-Location -LiteralPath $Source
$env:POSTGRES_DSN='postgresql://grid_integration_test_app@127.0.0.1:5432/grid_integration_test'
$env:PGPASSFILE=Read-Host 'Protected app passfile absolute path'
$env:ProgramData=Join-Path $Root 'State'
$env:TEMP=Join-Path $Root 'Temp'
$env:TMP=$env:TEMP
$env:ARCHIVE_ROOT=Join-Path $Root 'State\archive-cache'
$env:ML_ARTIFACT_ROOT=Join-Path $Root 'State\ml-artifacts'
$env:RETENTION_ENABLED='false'
$env:TELEGRAM_BOT_TOKEN=''
$env:TELEGRAM_ALLOWED_CHAT_IDS=''
$env:ENROLLMENT_TOKEN=''
$env:TAILSCALE_OAUTH_CLIENT_ID=''
$env:TAILSCALE_OAUTH_CLIENT_SECRET=''
& $Python -m uvicorn grid.coordinator:app --host 127.0.0.1 --port 8765 --workers 1 --no-access-log
```

Do not use `run_coordinator.py` or existing launcher: their all-interface binding
is outside this loopback-only procedure. No Worker/enrollment/Telegram/ACTIVE-state
or exchange/trading credentials are enabled. PASS requires prepared schema,
restricted app, INFRA_ONLY, exactly one effective CONTROL lease and loopback
listener only. Any other listener or market activation is FAIL/STOP. Unknown token,
protected paths, secrets custody or task inventory is BLOCKED before this command.

### G6 — health, fencing, WAL and controlled recovery

In a second approved local terminal:

```powershell
$h=Invoke-RestMethod -Uri 'http://127.0.0.1:8765/health'
if (!$h.ok -or !$h.control_leader -or $h.runtime_state -ne 'INFRA_ONLY') { throw 'FAIL_HEALTH_GATE' }
```

Record non-secret SHA/run ID/time provenance/health epoch, restricted-role results
and hash-listed evidence. Do not treat PID/epoch alone as trusted attestation.
Future synthetic WAL tests must use new GUID-owned fixtures, never production WAL.
Orderly restart must preserve schema seal, data and pending records; old epoch
writes must fail after takeover. Concurrent CONTROL, kill/reconnect, disk/checkpoint
failure and WAL replay need separately approved fixture plans; do not physically
interrupt PostgreSQL, network, Windows services or real data. CI already exercises
software-level restricted startup/restart/concurrency and existing WAL regressions;
that does not mark PC4 recovery scenarios PASS.

### G7 — stop and retain evidence

Ctrl+C in the owning foreground terminal, wait for graceful shutdown and verify
its loopback listener ended. Preserve database, State/WAL and evidence. Never kill
unidentified processes or stop the PostgreSQL service. Remove only this shell's
POSTGRES_DSN/PGPASSFILE variables; no password deletion/rotation is automated.
PASS requires singleton cleanup and retained evidence; timeout/unknown ownership
means STOP/BLOCKED, not automatic forced cleanup.

## Rollback and remaining blockers

Code rollback is plan-only until runtime/tasks are proven stopped under the
existing mutex/Runtime Guard and release manifests are verified. Schema48 cannot
be downgraded automatically, and historical LegacyRollback's schema47 check remains
unchanged: an older binary is not authorized on schema48. This new source seal also
rejects a different preparer/runtime checkout. Preserve the DB; restore a compatible
reviewed backup only through a separate recovery plan. `30_rollback.sql` deliberately
retains any existing database; it never claims incomplete catalog checks prove
safe deletion. No automatic deletion of directories, databases or roles is added.

| Gate | Current physical state | Required next evidence |
|---|---|---|
| G0 identity/ACL/custody | BLOCKED | independent SID/token/ACL/ancestor review; physical harness 0/10 |
| G1 protected code/toolchain | BLOCKED | new protected tree and exact candidate/hash/dependency approval |
| G2 resources/cluster | BLOCKED | independent cluster/OID/run receipts and authorization |
| G3 schema | BLOCKED | explicitly authorized owner prep on isolated target |
| G4 minimum grants | BLOCKED | actual app/RO negative tests and private secret custody |
| G5 runtime | BLOCKED | loopback/start authorization, tasks stopped, no market activation |
| G6 recovery | BLOCKED | separately approved synthetic physical tests/evidence |
| G7 stop/retention | BLOCKED | observed graceful stop and preserved evidence |

P0: none demonstrated by offline audit. P1 physical blockers: all gates above;
no in-place unsealed-database upgrade path; PostgreSQL18.4 patch/build decision;
Windows SID/ACL not physically tested; external-services/market execution not
authorized. P2: runtime dependency ranges remain unpinned for deployment, launchers
still bind all interfaces, trusted-owner schema mutation after startup is outside
the seal guarantee, and cleanup requires independent resource provenance.

References: [PostgreSQL privileges](https://www.postgresql.org/docs/18/ddl-priv.html),
[role identity](https://www.postgresql.org/docs/18/functions-info.html),
[official image PG18 directory layout](https://hub.docker.com/_/postgres).
