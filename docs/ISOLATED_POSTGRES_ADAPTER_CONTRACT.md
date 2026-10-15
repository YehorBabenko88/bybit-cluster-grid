# Adapter to PostgreSQL ownership contract, revision 1 (BLOCKED)

Scope: PR192 comment 6201388629, base 3ec6786bc6e94f2f478278c1ce9f3f07deaa5447.
This revision documents the mapping; it does not enable schema 2 or provisioning.

## Mapping and canonical representation

The authoritative adapter schema remains 1. New-GridLabPlan validates a local
fixed-drive parent ending in case-sensitive `GridLab`, a lowercase 32-hex run ID
and uppercase node ID (LS5/LS7 excluded). Its root is
`<parent>\<run_id>_<NODE>`. The only prospective PGDATA is
`<revalidated plan.root>\postgres\data`. No second caller-supplied PGDATA is valid.
Do not translate the legacy PostgreSQL schema-1 layout
`<parent>\<run_id>\<NODE>\pgdata`; it remains BLOCKED, including default PlanOnly.
Case-folded equality, slash normalization or Windows path resolution alone is
not proof of canonical spelling or physical identity. UNC, mapped/SUBST drives,
aliases, junctions, reparse points and multiply-linked files must be rejected.

The plan hash is the adapter's ordered compact PowerShell JSON, UTF-8, BEFORE
adding plan_sha256. Python canonical JSON hashes are different metadata and must
never substitute for this hash. Reconstruct with New-GridLabPlan; compare exact
expected plan bytes, hash, root, parent, run, node, commit, role and ports against
independent operator intent. Copying a plan/journal to another root is forbidden.

## Ownership evidence required before schema 2 can exist

Use the existing release and preparation mutexes. A local verifier must pin file
and directory identities, reject hardlinks/reparse points and validate fixed
volume identity and protected owner ACLs, including all ancestors relevant to
replacement. Retain read-only handles denying write/delete for material evidence.
Recheck path identities, membership and bytes after validation and before handing
an in-process mapping to a consumer; invalidate proof when handles are released.
No exported JSON, timestamp, hash claim or snapshot can substitute for this.
Stale and freshly forged reports are equally unauthenticated.

Require EXACT PREPARED + COMMITTED journal records for the reconstructed hash,
with canonical newline/encoding. PREPARED alone, RETIRED (with or without COMMITTED),
torn, duplicated or foreign records block mapping. Require exactly the directories
`releases`, `data`, `data\wal`, `postgres`, `postgres\data` and adapter-generated
`deployment-plan.json`, `isolated.env.template`, `postgresql.conf.template`,
`tasks.plan.json`, plus `owner.jsonl`. Compare templates to Get-GridLabFiles, not
caller-provided hashes. PGDATA must remain empty; unexpected contents block.

## Why this implementation remains blocked

Assert-GridLabOwned verifies journal strings and tree contents but accepts partial
and retired preparations and does not bind all file reads to single-link native
identities across TOCTOU rechecks. It is not an authenticated mapping interface.
The adapter also does not establish the protected ACL prerequisite. Existing
snapshot JSON is deliberately unauthenticated and cannot bridge this gap.

Consequently schema 2 is NOT introduced. Any schema-2 request returns
SCHEMA2_LOCAL_OWNERSHIP_VERIFIER_REQUIRED without deriving a path or probing the
host. Legacy assessments always return BLOCKED and CLI exit 2. The lexical plan
validator remains metadata-only; its VALIDATED_PLAN_ONLY is not commissioning.
The read-only snapshot collector remains diagnostic only and cannot authorize
mapping, staging or execution. Existing staging policy, Runtime Guard, mutex,
journal and mutating adapter code are unchanged.

A follow-up requires a reviewed in-process native handle/ACL verifier and lifetime
contract, synthetic race injection tests on both PowerShell engines, independently
approved root/hash/identity inputs and separate ACL preparation authorization.
No Add-Type compiler process or temporary native build should be hidden inside a
read-only verifier. Keep blocked on unsupported native APIs or unknown identity.

## Evidence and limits

New Python tests reproduce legacy PLAN_ONLY before this change and exercise both
modes with PREPARED/COMMITTED/RETIRED/torn/foreign serialized ownership, future
snapshots, alternate roots and arbitrary PGDATA. These test rejection, NOT actual
filesystem ownership or race exclusion. Existing PS5.1/7 mock fixtures cover
inventory errors, reparse/hardlink claims, volume aliases and ACL failures.
No positive ownership mapping, real provisioning or physical readiness is claimed.
Rollback is reverting this commit in a new reviewed branch; no data/schema/task
changes or cleanup are needed. Do not activate legacy plans during rollback.
