# Isolated PostgreSQL16: offline preflight and unresolved adapter contract

Source: PR191 comment6200720425, exact base `2c29a72c3a275a34effa8110557782f0a8d95341`. This layer is read-only preparation review, not PostgreSQL provisioning. No physical executor is included or enabled. No initdb, pg_ctl, SQL, port binding, service/task changes, artifact installation or deletion is performed.

## Architecture stop: incompatible layouts

| Contract | Required path |
| --- | --- |
| PR191 PostgreSQL schema1 validator | `<parent>\GridLab\<run>\<node>\pgdata` |
| Existing isolated deployment adapter | `<parent>\GridLab\<run>_<node>\postgres\data` |

These cannot be treated as the same resource. Schema1 ownership must not be inferred from the adapter's journal, nor may an existing adapter-created directory be adopted as a new PGDATA. The report always retains `ADAPTER_LAYOUT_INCOMPATIBLE`; physical provisioning is blocked. No path conversion, extra schema acceptance, journal rewrite or weakening of either contract has been introduced.

Additional source mismatches were unsafe permissiveness rather than valid new protocols: node case/length, port range, loopback addresses and path aliases. Schema1 validation now accepts only uppercase node IDs up to15 characters, port20000–49999, explicit127.0.0.1, canonical backslash paths with uppercase drive and exact GridLab/run/node/pgdata tail. It rejects protected components (including Program Files(x86)), aliases, reserved devices, ADS syntax, wildcard characters, trailing dot/space, repeated separators, UNC/device paths and traversal. Existing installed ports5432/55432/55433 are excluded. These stricter rules do NOT resolve the layout contradiction.

A future versioned contract needs its own review and tests, a single canonical PGDATA definition, explicit adapter journal/resource ownership semantics, migration/compatibility rules and typed reservation ownership. Do not silently update deployed manifests or infer support from absent modules.

## Modes and trust boundary

`installer/isolated_postgres_preflight.py` defaults to PlanOnly. It reads bounded regular input JSON files with duplicate-key/nonfinite-number rejection, rejects redirected/hardlinked input and emits JSON to stdout. Run with trusted Python `-B`. It does not spawn children, invoke shell commands, import target runtime, open network connections, bind ports, create files or run SQL.

- PlanOnly validates metadata, hashes the canonical original plan (sorted keys, compact UTF8 JSON), records the exact candidate commit and describes blockers. It refuses host evidence in this mode. `operator_approved=true` remains a legacy input-validation field, NOT execution permission. A preview with known architectural blockers may exit0; this is not a readiness PASS. Invalid inputs/reservations exit2.
- PreflightReadOnly consumes an explicitly supplied metadata snapshot and approved-owner SID. It validates exact schema/types, plan/commit/run/node/path binding, UTC timestamp age0–30seconds, absent resources, complete inventory, protected owner ACLs, disallowed writers, PostgreSQL identities, tasks, TCP/UDP observations and reservation claims. Input snapshots are unauthenticated metadata; even a matching valid snapshot never authorizes execution. Stale/future/malformed evidence blocks.
- Reports always set execution_authorized=false and physical_ready=false. PreflightReadOnly exits2 while the integration layout is incompatible. This expected blocker must not be turned into a successful physical commissioning claim.
- Reservation claims are checked for malformed/duplicate node-port identities and any pre-existing target claim. An observed-free port is explicitly `OBSERVED_ONLY_NOT_RESERVED`; no reservation is created. Empty external claims do not prove a free/reserved resource.

`installer/isolated-postgres-readonly.ps1` also defaults to PlanOnly and calls zero providers. Explicit PreflightReadOnly holds the existing release mutex and reuses Runtime Guard plus adapter physical-path helpers. It gathers only local metadata: computer identity, fixed disk, physical ancestors, absence of PGDATA/run/node resources, owner/protected/canonical ACL, allowed writer SIDs, services/processes/tasks and TCP/UDP endpoints. It does not start a child Python process or version probe. It emits sanitized SNAPSHOT_ONLY data or a stable BLOCKED code, never CommandLine, DSN, credentials, provider exception text or environment values.

The collector blocks LS5/LS7, wrong node identity, mapped/network/removable/unknown disks, redirects, existing resources (including files/hardlinks), null/unsafe/inherited/foreign-writable ACLs, unknown inventory and any observed PostgreSQL identity. It neither stops nor contacts an installed PostgreSQL server. Snapshot-only success means the observed metadata passed these checks; it is not provenance, future atomic ownership or startup authority.

## Review commands (not authorization to run on a physical PC)

Use a separately approved review workspace. JSON inputs already exist; the tools do not save output files. Redirection/saving evidence is a separately approved file write. No physical inventory command was executed during this audit.

```powershell
# Offline preview: reads only review JSON, prints hashes and blockers.
& <trusted-python.exe> -B ./installer/isolated_postgres_preflight.py `
  --plan <pg-plan.json> --adapter-plan <adapter-plan.json> --commit <exact-40-character-sha>

# Collector PREVIEW only: no providers, files, processes or ports created.
& ./installer/isolated-postgres-readonly.ps1 `
  -DataRoot '<canonical-schema1-path>' -RunId '<32-lowercase-hex>' -NodeId '<UPPERCASE-LAB-NODE>' `
  -Port 25432 -Commit '<exact-sha>' -PlanSha256 '<preview-plan-hash>' -OwnerSid '<reviewed-owner-SID>'
```

Only a separately authorized operator on a named disposable Windows PC may add `-Mode PreflightReadOnly` to the collector. It still makes no resource changes. Do not run it on LS5/LS7. Feed a snapshot to Python with `--mode PreflightReadOnly --evidence <snapshot.json> --owner-sid <reviewed-SID>` and optionally `--reservations <reviewed-claims.json>`. The resulting integration assessment remains BLOCKED until the contract mismatch is resolved. Never automatically pipe output into an executor.

## Ownership, ACL and failure semantics

The approved GridLab parent must already be a reviewed physical local directory with a canonical protected DACL and exact owner SID. Only that SID, SYSTEM and Administrators may have allow-write rights; unfamiliar write grants conservatively block even if another deny ACE might reduce effective access. Null DACLs, unreadable ACLs or unknown identities block. No ACL/account is changed. PGDATA and its new run/node ancestors must not already exist. The result reports `ABSENT_UNOWNED`, not verified ownership of a cluster.

Kernel resources can change immediately after a read-only snapshot. Mutexes coordinate Grid tooling only; they do not lock out unrelated programs/administrators. A future executor must atomically establish ownership, recheck identities at actual creation/startup boundaries, bind an approved port without a gap and retain rollback evidence. A30second timestamp does not solve TOCTOU.

No new staging executor was added: bridging the incompatible layouts would manufacture ownership. Existing adapter fixtures are the disposable fixture-only staging surface. All file writes occur in a new GUID test tree with mocked host/GitHub boundaries. Tests exercise interrupted prepare, torn receipts, re-entry refusal, competing exclusive handles, writer denial during append, ownership replacement/tree mutation, hardlinks and preserved rollback. They do not run a PostgreSQL executable or use the PostgreSQL schema1 path on any real machine. Existing prepared/committed release journals, atomic pointers, schema checks and production staging policy are untouched.

## Future approvals — distinct and exact

Before any real provisioning, separately review and approve:

1. Named disposable target host, source commit, resolved versioned adapter/PGDATA contract and each operation.
2. PostgreSQL16 binary provenance, complete distribution hashes/signatures and dependency inventory; a plan's major=16 is not binary proof.
3. Dedicated restricted account, parent/data ACLs and ownership marker, excluding existing installations and clusters.
4. Authentication/TLS design, certificate and secret storage; never credentials in arguments/logs.
5. Exact isolated directory/cluster creation, port binding/reservation identity and resource limits.
6. Independently reviewed startup/task registration and shutdown; no implicit startup after preparation.
7. Preservation/rollback and explicit cleanup approval, with no automatic deletion or schema downgrade.

Until those gates are implemented, reviewed and separately approved, the physical executor remains absent/disabled. No merge, deployment, existing service, production database or WAL operation is authorized.

## Reproducible synthetic checks

```powershell
python -B -m pytest -q tests/test_isolated_postgres_plan.py tests/test_isolated_postgres_preflight.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File installer/tests/test-isolated-postgres-readonly.ps1
pwsh -NoProfile -File installer/tests/test-isolated-postgres-readonly.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File installer/tests/test-isolated-deployment.ps1 -Python <trusted-python.exe>
pwsh -NoProfile -File installer/tests/test-isolated-deployment.ps1 -Python <trusted-python.exe>
```

CI adds Python3.11/3.12 offline tests inside a fresh Linux network namespace, with no PostgreSQL service/driver installed by the new workflow. Windows jobs cover both Python versions and both PowerShell engines. The bundle gate runs mocked read-only snapshot and existing adapter failure fixtures from the built bundle. Existing required CI remains intact. Record exact HEAD, actual counts and run IDs; skipped tests and synthetic success are not physical HA evidence.
