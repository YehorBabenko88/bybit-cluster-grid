# PC4 Grid / PostgreSQL 18.4 — commands and gates first

**Plan only. No PC4/LS5 connection, SQL execution or installation was performed.**
Physical SID/ACL harness **0/10 NOT_RUN. Execute NOT_AUTHORIZED.** SQL preparation
is not permission to bootstrap, migrate, enable logins, start Grid or trade.

## 1. Exact future commands (local PC4 only, separate approval required)

Run from an independently reviewed, protected checkout at this PR's exact SHA.
`$Psql` is a proposed path, not an observed installed binary. Its signature,
version and provenance are BLOCKED until independently verified. No remote command
or provisioning script is supplied. Existing PostgreSQL services/configuration,
PGDATA, PostgreSQL roles `postgres`/`user`, other databases and networking stay
unchanged. No `initdb`, server upgrade, installer or task/service creation occurs.

```powershell
$Psql = 'C:\Program Files\PostgreSQL\18\bin\psql.exe'
& $Psql --version
& $Psql -X -h 127.0.0.1 -p 5432 -U postgres -d postgres -W `
  -v ON_ERROR_STOP=1 -f .\planning\pc4-pg18\00_readonly.sql
if ($LASTEXITCODE -ne 0) { throw 'READONLY_PREFLIGHT_FAILED' }
```

This reads server version, independently pinnable system identifier, database
names/owners/OIDs, non-system roles/attributes and other-client count. It runs in
a read-only transaction, never prints query text from clients or credential data.
`-X` ignores psqlrc; `-W` prompts in a private terminal. Do not use recording,
transcripts, `-a/-e`, a credential-bearing URI or PGPASSWORD. The script does not
infer authorization from these observations and does not return an automatic GO.

PlanOnly calls (still open a connection; **not authorized to run here**):

```powershell
& $Psql -X -h 127.0.0.1 -p 5432 -U postgres -d postgres -W `
  -v ON_ERROR_STOP=1 -f .\planning\pc4-pg18\10_bootstrap.sql
& $Psql -X -h 127.0.0.1 -p 5432 -U postgres -d postgres -W `
  -v ON_ERROR_STOP=1 -f .\planning\pc4-pg18\30_rollback.sql
```

Only after explicit *database preparation* approval and closed relevant gates:

```powershell
# Not executable instructions for the current stage. Fill independently verified
# non-secret pins; the literals below deliberately fail the SQL guards.
$RunId = '<approved-UUID-v4>'
$ClusterId = '<independently-approved-system-identifier>'
& $Psql -X -h 127.0.0.1 -p 5432 -U postgres -d postgres -W `
  -v ON_ERROR_STOP=1 -v execute=on -v bootstrap_id=$RunId `
  -v expected_system_identifier=$ClusterId `
  -f .\planning\pc4-pg18\10_bootstrap.sql
if ($LASTEXITCODE -ne 0) { throw 'BOOTSTRAP_STOP_PRESERVE_PARTIAL_STATE' }

# Record the returned role/database OIDs privately; never substitute name-only
# identity for these pins. Zero means initially absent, not an existing resource.
$OwnerOid = '<recorded-owner-OID>'
$AppOid = '<recorded-app-OID>'
$RoOid = '<recorded-ro-OID>'
$DbOid = '<recorded-database-OID>'
$Pins = @('-v',"bootstrap_id=$RunId",'-v',"expected_system_identifier=$ClusterId",
  '-v',"expected_owner_oid=$OwnerOid",'-v',"expected_app_oid=$AppOid",
  '-v',"expected_ro_oid=$RoOid",'-v',"expected_db_oid=$DbOid")

# Idempotent verification/retry: same externally retained pins, no name adoption.
& $Psql -X -h 127.0.0.1 -p 5432 -U postgres -d postgres -W `
  -v ON_ERROR_STOP=1 -v execute=on @Pins -f .\planning\pc4-pg18\10_bootstrap.sql
if ($LASTEXITCODE -ne 0) { throw 'BOOTSTRAP_RETRY_BLOCKED' }

# Separate database-scoped privilege preparation. No migrations or login enabling.
& $Psql -X -h 127.0.0.1 -p 5432 -U postgres -d grid_integration_test -W `
  -v ON_ERROR_STOP=1 -v execute=on @Pins -f .\planning\pc4-pg18\20_privileges.sql
if ($LASTEXITCODE -ne 0) { throw 'PRIVILEGE_PREPARATION_BLOCKED' }
```

Pins and approval must come from independent owner review, not blind acceptance of
the first server answering 5432. All mutation scripts require `execute=on`; default
is PlanOnly. Internal `_context.sql`/`_owned.sql` are includes, never entrypoints.
Session-only settings and cooperative advisory locks are not persistent server
configuration. Any unknown ownership/identity/dependency/session causes STOP.

## 2. PASS / FAIL / BLOCKED matrix

PASS means the named check only; it never authorizes the next phase automatically.
FAIL means observed contradiction. BLOCKED means missing authorization/evidence.

| Gate | PASS criteria | FAIL criteria | Current result |
|---|---|---|---|
| G0 authority / host isolation | Separate owner approval, protected checkout/tooling, verified local PC4 context | Unauthorized/unknown operator or untrusted staging | BLOCKED; physical 0/10 |
| G1 server / cluster | Trusted psql, independent system ID, exact 180004, loopback TCP 5432, expected cluster | Mismatch, unexpected endpoint/version, inaccessible metadata | BLOCKED; Running/5432/three DBs/two roles/no clients are supplied historical observations |
| G2 resource provenance | All names absent, or exact marker + externally retained OIDs + owner/attributes | Unmarked names, OID drift, role memberships, foreign dependencies, active clients | BLOCKED; no live observation |
| G3 patch security / driver | Approved patched-version policy and actual pinned Python/asyncpg build tested with chosen PostgreSQL | Known incompatible SQL/protocol or disallowed vulnerable patch | BLOCKED; 18.4 is superseded by security fixes in 18.6, no upgrade performed |
| G4 schema | Baseline tables, exact ordered 1–48 names/SQL, migration48 index validator, runtime/retention/control schemas, ownership/default grants checked | Gap/unknown/name/index mismatch, DDL privilege error, incorrect search_path | BLOCKED; only source catalogue checked offline |
| G5 minimum app / RO | App DML + sequence usage only, owner NOLOGIN, no SET ROLE membership; RO three-table SELECT allowlist | App requires DDL/owner or RO gains control/auth/future-table access | FAIL as a launch candidate: current startup performs DDL; no privilege escalation workaround |
| G6 secrets / environment | Approved private secret delivery, no password in code/URI/logs; exact DSN/db/port; no Telegram/trading credentials | Wrong database, unprotected dotenv/passfile, secret output | BLOCKED; all new roles deliberately NOLOGIN |
| G7 recovery / rollback | Receipt-proven roles with no dependencies and database absent; data preserved | Any existing DB, active client, unknown catalog contents/identity | BLOCKED for database deletion; retain DB, no automatic destructive cleanup |
| G8 runtime / single-node smoke | Separately approved runtime after G0–G7, INFRA_ONLY, health/fencing/leases/WAL proven then approved pilot | Unexpected ACTIVE/trading/Telegram, duplicate owner, data loss | BLOCKED; no runtime started |

## 3. Repository and migration findings

Audited main: `d537d525296ef34f727996e240ae6c60102c6082`, catalogue 1–46.
Planning base: #225 `217904071394ab8a84e5a180822081ff8e25e1e9`, including
#224 `2a93efaab1ec61cc5e2a872b95e47a0a8a227f55`; catalogue 1–48. Open stacked
PRs #188/#211/#216/#223–225 were inspected for candidate context. They are not
merged or production releases; this plan does not promote them into main.
The catalogue receipt `planning/pc4-pg18/migrations.json` pins each name and SQL
SHA256 for this base, not a live database state.

`grid/service.py:prepare_database` calls `Database.ensure_schema` **before**
`apply_migrations`. Migration 1 alters baseline tables, so applying catalogue SQL
alone to an empty database is insufficient. Migrations are individually transactional
and serialized by a session advisory lock; a failed version rolls back its SQL and
version registration, but earlier versions remain committed. There is no global
all-48 transaction, automatic downgrade or schema reset. Do not seed version rows.

Migration 47 establishes collection ownership fencing. Migration 48 creates and
validates the public model_registry(dataset_id) B-tree lookup index, including
operator class, collation, ordering/options and other catalog invariants. No
extension/superuser-only DDL was found in the migration catalogue. This is a source
review, not a PostgreSQL 18 execution result. Modern commissioning reuses the
index validator; legacy rollback remains restricted to schema47 and does not gain
permission to run historical runtimes on schema48. A release-pointer rollback
cannot downgrade a database or solve schema compatibility.

Coordinator leader startup additionally calls instrument/strategy/plugin/control/
update/enrollment/runtime/retention schema creation. Retention includes
analysis_watermarks and retention_runs outside 1–48. Lease/fencing/control and
runtime state matter; a count of 48 version rows is not a complete readiness test.
Current startup repeats CREATE/ALTER statements even after migration completion.
`prepare_database` retries errors, so starting it with insufficient app rights
may loop rather than produce a successful restricted runtime.

**Required architectural decision:** add/review a separate owner-context schema
bootstrap and a genuinely DDL-free app startup/read-only schema verification path.
Do not grant owner membership, superuser or broad CREATE/ALTER to the app to make
startup pass. No runtime changes are made in this PR, and no runnable owner-DSN
workaround is supplied.

## 4. Privileges, idempotence and partial states

New names only: `grid_integration_test`, `grid_integration_test_owner`,
`grid_integration_test_app`, `grid_integration_test_ro`. All roles are NOLOGIN,
NOINHERIT, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION, NOBYPASSRLS.
No memberships are granted. The DB uses template0, UTF8 and CONNECTION LIMIT 0;
only superusers can connect during preparation. PUBLIC DB access and schema access
are revoked only in the new DB. The built-in postgres and existing user role are
not modified. Owner is for explicitly approved migration work, never app login.

App gets public schema USAGE; tables SELECT/INSERT/UPDATE/DELETE and sequence
USAGE/SELECT, including future objects created by the **owner**, not postgres.
No schema CREATE, table ownership, TRUNCATE, role administration or global
pg_read_all_data grant. RO gets only SELECT on existing candles_1m, footprint_1m
and derivatives_metrics; rerun grants after approved migrations. No blanket or
future-table RO grants: enrollment_tokens, agent_credentials and commands remain
excluded. The read-only transaction default is a convenience, not the security
boundary. ACLs/default ACLs are checked for unexpected dedicated-role grants
before privilege preparation; unexpected grants, PUBLIC access to user data and
implicit object ownership by app/RO are blocked rather than repaired. This is
not a complete effective-permission proof against a malicious administrator.

Enabling LOGIN on a cluster-wide role may also inherit PUBLIC CONNECT/TEMP rights
in postgres/template1 or other databases. Grants only in grid_integration_test
cannot deny privileges inherited from PUBLIC elsewhere. No outside database or
pg_hba.conf is altered here. Actual ACL inventory and an approved authentication/
cross-database access policy (or a separately approved isolated instance) are
additional preconditions; there is no claim of strict database-only confinement.
NOLOGIN currently prevents using those potential privileges for authentication.

Resource marker includes a reviewed run UUID and cluster system ID. Existing
names additionally require matching external OID pins, attributes, owner and
no memberships/foreign dependencies. First create is absent-only; repeat with
the same receipt is intended to make no new objects. Missing pins are BLOCKED,
not proof the names belong to Grid. These semantics are reviewed and parsed only;
server-side idempotence/concurrency testing remains NOT_RUN.

CREATE DATABASE is nontransactional. Role creation/comments are transactional;
database marker and hardening are committed together **after** creation. A crash
in that gap leaves an unmarked database: stop, retain it and request independent
manual recovery. Never adopt or delete it automatically. Lost receipt, partial
failure, changed role/login/DB limit, unmarked name or OID replacement also blocks.
Locks only coordinate cooperating sessions in the same database; they do not
defend against another superuser or hostile administrator. Do not run phases
concurrently. All phases recheck other clients; none terminates them.

## 5. Rollback: retain data; clean only proven orphan roles

Automatic DB deletion is deliberately **not implemented**. Independent AI review
found that an initial selected-catalog pristine test could miss a `pgx` schema
(LIKE underscore wildcard) or an unknown FDW/operator/cast. Removing those checks
and retaining every existing DB closes that unsafe deletion path. A full-catalog,
independently approved baseline and database-wide data-retention decision are
required before a future DB-removal implementation. It is a P1 blocker, not
permission to bypass the guard with an approval flag.

If the DB exists, `30_rollback.sql` raises BLOCKED before any deletion. After
separate authorized DB decommissioning, or a bootstrap failure before DB creation,
it can remove only surviving tagged/OID-pinned roles with zero shared dependencies
and zero memberships. It never touches another DB's grants, reassigns ownership,
forces sessions, recursively deletes data or downgrades migrations. Repeating
cleanup when all created resources are absent is a no-op. Safe future command,
requiring **separate role-cleanup approval**, not authorized by this document:

```powershell
& $Psql -X -h 127.0.0.1 -p 5432 -U postgres -d postgres -W `
  -v ON_ERROR_STOP=1 -v execute=on -v approve_role_cleanup=on @Pins `
  -f .\planning\pc4-pg18\30_rollback.sql
if ($LASTEXITCODE -ne 0) { throw 'RETAIN_RESOURCES_MANUAL_REVIEW_REQUIRED' }
```

After Grid ever writes data, stop through a separately approved procedure,
preserve database/WAL/artifacts, back up and verify restoration independently.
Do not roll back schema48 automatically or switch to a schema47-only historical
runtime. Development rollback is reverting this PR; nothing was provisioned.

## 6. Environment and future runtime sequence — currently blocked

`grid/config.py` loads `.env` from the working directory; unknown settings are
ignored. Do not copy `.env.example` unreviewed: it uses port55432 and a different
database, while PC4's reported endpoint is5432. No invented TRADING_ENABLED flag
is treated as a safety gate. Pin/review Python3.12 and exact asyncpg dependency
builds (requirements currently says asyncpg>=0.30, not a lockfile). Existing CI
uses PostgreSQL16; it does not prove 18.4 compatibility.

Future password-free DSN shape:
`postgresql://grid_integration_test_app@127.0.0.1:5432/grid_integration_test`.
Secret delivery remains BLOCKED. A reviewed private asyncpg passfile can be used
outside the checkout, but its content, ACLs, authentication policy, client/server
logging and exact driver support must be approved before credentials are created.
No password creation, LOGIN-enabling SQL, active runtime config or secret file is
provided here. Never use postgres/owner as the application DSN. Do not print env,
dotenv content, DSNs containing credentials or pg_authid.

Once separately approved: require empty Telegram tokens/chat IDs, no Bybit API
key/secret, RETENTION_ENABLED=false for initial integration, explicit private
archive/ML/cache/WAL paths and verified free space. ROLE/NODE_ROLE/URLs/tokens
must match reviewed config; default coordinator endpoint is8765, whereas the old
example uses8787. An empty Telegram token avoids bot activation, not all other
startup side effects. Keep persisted grid_runtime_state INFRA_ONLY, never ACTIVE
as a migration side effect; no automatic /start, enrollment or exchange connection.

Only **after** the DDL/app split, authentication, patch, schema and physical gates
are closed could the proposed first foreground command be reviewed:

```powershell
# BLOCKED / NOT_AUTHORIZED now. No admin DSN; no service installation.
python -m uvicorn grid.coordinator:app --host 127.0.0.1 --port 8765 --workers 1 --no-access-log
```

Do not use run_coordinator.py for first commissioning: it binds0.0.0.0. Start no
worker until coordinator/lease/INFRA_ONLY health is independently accepted. The
later worker entry is run_worker.py, but actual collection requires new approval,
verified node credentials/ownership fencing and WAL/recovery evidence. Database
roles do not prove Windows SID/ACL isolation or air-gap. No such proof is claimed.

## 7. Compatibility and evidence limits

[PostgreSQL18.4 release notes](https://www.postgresql.org/docs/release/18.4/)
establish the requested version exists. [18.6 notes](https://www.postgresql.org/docs/release/18.6/)
describe later security fixes; do not treat18.4 as current security approval.
[Current asyncpg documentation](https://magicstack.github.io/asyncpg/current/)
includes PostgreSQL18 in its supported range, but that does not validate the
repository's unbounded >=0.30 resolution, Windows wheel, or Grid SQL on PC4.
[asyncpg authentication options](https://magicstack.github.io/asyncpg/current/api/index.html)
support passfiles; secret delivery is still outside this plan.
[CREATE DATABASE](https://www.postgresql.org/docs/18/sql-createdatabase.html)
cannot participate in the role transaction; [DROP ROLE](https://www.postgresql.org/docs/18/sql-droprole.html)
must fail if dependencies remain. [Default privileges](https://www.postgresql.org/docs/18/sql-alterdefaultprivileges.html)
are scoped to object creator, not inherited automatically from membership.

Offline tests check the48 catalogue, guards, secret/broad-cleanup absence, RO
scope, retained-DB rollback and SQL/PLpgSQL grammar using pglast8.7 (PG18 parser).
They do not connect to PostgreSQL or prove psql conditional expansion, permissions,
transaction behavior, crash recovery or concurrency. Those checks need separately
approved disposable18.x CI and then owner-approved PC4 observation. No real SQL,
PostgreSQL instance, migration or runtime was run in this task.

**P0:** no concrete new offline P0 found; not a system certification.
**P1:** startup DDL/app separation, security patch decision, full DB rollback
provenance, host staging/physical authority and actual18.4 tests remain open.
**P2:** credential/logging/dependency pinning and scoped ACL drift verification
need independent live confirmation. AI review is not a human or physical review.
**GO:** offline planning/code review only. **NO-GO:** real Grid launch, DB execution,
physical commissioning and destructive DB rollback. Physical0/10 NOT_RUN;
Execute NOT_AUTHORIZED. No merge or deployment.
