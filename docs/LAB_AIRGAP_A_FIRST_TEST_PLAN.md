# First-test dry-run protocol — future only

**NOT_RUN / BLOCKED.** This is a tabletop protocol and evidence specification,
not an executor, installation recipe or permission to create a VM. No commands
are provided. Schema-2 remains disabled; no SQL/initdb/PostgreSQL/services.

## Human checkpoints

| Gate | Evidence required before a future separately approved activity | Current state |
|---|---|---|
| L1 architecture | Explicit provisional A direction; two independent human reviews of exact plan/SHA, concerns and decisions | Direction only; zero reviews; NO-GO |
| L2 resources | Owner approves exact dedicated host/images/fixtures, scope, custody, topology, quotas and recovery/STOP plan; PGDATA mapping resolved where applicable | None verified or authorized; NO-GO |
| L3 observations | Separate permission for native identity/ACL/token/handle collection; tool provenance, private evidence handling and independently trusted collectors | NOT_RUN |
| L4 negative tests | Separate explicit permission for each disposable guest fixture, case schedule, time/capacity limits, expected deny and STOP controls | All twelve NOT_RUN |
| L5 canary | New review/authorization after evidence acceptance; no inference from L4 | NO-GO |

The first proposed session is an **offline ACL/ownership experiment only**, first
one case at a time on a bounded disposable fixture. It cannot certify freshness,
host-admin resistance or durable anti-rollback. Unknown PGDATA mapping blocks
any actual PGDATA scenario; a generic empty surrogate is not PGDATA compatibility
evidence. Even dedicated lab hardware needs approval; names do not prove ownership.

## Future native evidence plan (not collected)

Both observers must independently bind collector/tool SHA, host/image identity,
run/case/attempt, owned volume/fixture, and expected scope. Record actual effective
thread/process tokens: TokenUser, groups including deny-only groups, privileges
and enabled state, elevation, integrity and impersonation. Names/SID syntax alone
are insufficient. Owner/verifier/adversary must have distinct effective SIDs and
no shared privileged administration. Unexpected privilege or identity means STOP.

Record security descriptor owner, DACL, inheritance and relevant access checks;
do not mutate ACLs to make preflight pass. Bind lexical intent, final native path,
volume/file identity, reparse/ancestor chain, handle access/share flags, lifetime
and pre/post identity. Missing CommandLine/identity/permissions or inventory errors
are BLOCKED. Data obtained through the compromised host alone is not independent.

PGDATA requires both reviewed plan layouts, versioned mapping and native handle
identity proof; no normalization or path rewrite bridges the current schema-1
mismatch. No production directories, WAL, services, scheduled tasks or databases
may be used. The planned fixtures must be explicitly allocated and confirmed
empty/owned later; uncertainty stops the test, never triggers deletion.

## Twelve scenarios — canonical vm_lab_plan vocabulary

Every row is **NOT_RUN**. No sampled success or synthetic record is a physical
PASS. Each future run needs baseline/precondition evidence, independent captures,
expected and actual result, race schedule, postcondition and STOP disposition.
All unexpected write/delete/permission changes, fixture escape or uncertain
identity stop the entire session. A verifier refusal is safe but not proof of an
untested OS guarantee; mismatched preconditions invalidate that run.

| ID / case | Proposed stimulus, only after L4 approval | Required safe result and evidence |
|---|---|---|
| VMNEG01 `write` | Unprivileged adversary attempts data/file/child write | Access denied; before/after contents and native denial; any write => STOP |
| VMNEG02 `delete` | Attempt delete and delete-child within owned fixture | Denied; target/parent identity retained; any deletion => STOP |
| VMNEG03 `write_dac` | Request WRITE_DAC using adversary effective token | Denied; DACL unchanged; unexpected grant/change => STOP |
| VMNEG04 `write_owner` | Request WRITE_OWNER without privileges | Denied; owner unchanged; any ownership change => STOP |
| VMNEG05 `acl_mutation` | Controlled adversarial DACL change schedule in fixture | Denied or verifier refuses session on ambiguity; no permission auto-repair; unexpected live acceptance => STOP |
| VMNEG06 `acl_aba` | Bounded change/restore race around validation barrier | Demonstrate limits explicitly; sampled equality never PASS. Unobserved interval/uncertain ABA => BLOCKED and STOP; not a claim of universal ABA prevention |
| VMNEG07 `inherited_acl` | Fixture includes unexpected inherited ACE | Preflight/verifier refuses; no repair; continued acceptance => STOP |
| VMNEG08 `junction` | Bounded reparse substitution within disposable guest volume | Reject or hold previously proven identity without redirected operation; capture held handles/final IDs; escape/uncertainty => STOP |
| VMNEG09 `ancestor` | Ancestor rename/substitution before/during pinned session | Reject or preserve proven identity; capture pre/post ancestor identities and handles; ambiguity => STOP |
| VMNEG10 `existing_mapping` | Declare pre-existing writable mapping/handle | Explicit exclusion cannot be independently ruled out => refuse; never infer absence from incomplete enumeration; no mapping accepted silently |
| VMNEG11 `privileges` | Present known privileged/elevated effective token; no exploit | Block before experiment; retain privilege/group facts; no mutation/exploit required |
| VMNEG12 `distinct_token` | Reuse effective SID or hide impersonation context | Block; independently captured actual token identities, not account labels; missing identity => STOP |

## Proposed session and failure recovery

At start, operator and both observers verify gates, exact SHA, dedicated ownership,
boundaries, quota and STOP authority. STOP custodian confirms all participants can
halt locally without relying on a network or production control. Failure to contact
an observer or retain evidence blocks the session. Each case receives a distinct
attempt ID and sealed baseline. Only that case's approved stimulus is in scope.

On unexpected result, identity mismatch, disk/quota warning, power loss, process
crash, missing handle cleanup, boundary change or broken custody: stop further
stimuli, preserve evidence and pending records, and classify the attempt ABORTED /
UNVERIFIED under human review. No automatic restart, retry, VM restore or cleanup.
Failed cleanup blocks re-entry; an old singleton process/session must not resume.
Teardown/rollback needs a separate resource-ownership review and explicit approval.
Restoring a snapshot does not restore trust or permission. Never downgrade schema,
erase WAL or touch another installation to recover a trial.

After independent review, retain both raw observations and disputes outside the
lab. No result advances an admission gate automatically. Lost or conflicting
anchors mean continuity unprovable; a new session requires new explicit approval
and must disclose the break. Guest destruction must not erase external history.

## Tabletop currently permitted

Offline JSON/schema validation, negative metadata tests, documentation review and
hosted static CI only. These cannot substitute for any row above. Use the empty
[evidence template](lab-airgap-a/evidence-template.json); do not fill PASS from CI.
