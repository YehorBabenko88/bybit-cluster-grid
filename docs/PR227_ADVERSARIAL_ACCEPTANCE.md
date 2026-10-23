# PR227 independent engineering acceptance

Reviewed baseline: `da69209af86567232fb3038a899580fe2e061a0b`.
Dependencies: PR226 `f99f401aa11b5f0e0ed75046960801f882540216`,
PR225 `217904071394ab8a84e5a180822081ff8e25e1e9`.
PR229 `62e3e180da35fc8d6eb6c11ec1f0bf2d04f93cd7` was inspected:
its prefix-only workflow fix is partial; this branch uses branch-independent safe
PR/dispatch gates and a required-evidence aggregator instead. No source branches
were changed. This is AI engineering review, not independent human acceptance.

## Defects and reproducible checks

Real SQL reproduction is restricted to `tools/check_pr227_adversarial_ci.py` on
the attested disposable GitHub-hosted PG18 provider. It exports the exact baseline
with `git archive`, imports Grid from that export, and then runs the identical
12 probes against the candidate. Separate JUnit/events distinguish
`baseline-vulnerability-reproduced` (NOT security acceptance) from
`candidate-rejection`. No local or physical SQL is needed or authorized.

| ID/severity | File and cause | Reproduction / expected vs original behavior | Candidate remedy |
|---|---|---|---|
| A / P1 | `grid/schema_contract.py`: incomplete effective privileges | Grant app TRIGGER on market_events; verifier should block, but accepts; app can CREATE TRIGGER with a builtin trigger function. TRUNCATE, REFERENCES, MAINTAIN and sequence UPDATE also escape the minimal profile. | Reject extra table/column/sequence authority across non-system namespaces. |
| B / P1 | same: parameter ACLs and callable foreign SECURITY DEFINER omitted | Grant SET on session_replication_role; verifier accepts and app can set replica, bypassing constraint triggers. Grant ALTER SYSTEM is also accepted (test queries authority only; NEVER executes ALTER SYSTEM). A foreign-schema owner function callable by app performs CREATE TABLE after accepted startup. | Reject extra parameter ACLs, non-origin replication state and callable non-system SECURITY DEFINER routines. |
| C / P2 | same: pg_rewrite omitted from digest | Owner creates DELETE DO INSTEAD NOTHING rule; verifier and repeated preparation accept unchanged digest despite altered delete semantics. | Fingerprint rule definition and enabled state. |
| D / P1 | same: seal/registry issuer and other grantees omitted | Grant RO UPDATE(catalog_sha256), transfer seal to RO and reseal, or install UPDATE default ACL before preparation. Original verifier trusts these metadata writers; source hash is public and does not authenticate issuer. | Require database-owner metadata ownership and forbid non-owner write/column ACLs, in preparation and runtime. Dirty default ACL causes the entire preparation transaction to roll back. |
| E / P2 | `tools/check_ddl_free_ci.py`: Git blobs hashed without checking executed checkout | Modify a tracked source file while HEAD remains exact; original receipt still hashes original blob. | Verify exact HEAD and clean tracked/index state before collection and after tests; reject untracked executable inputs. Four disposable Git-fixture regressions. This is not defense against a malicious runner or concurrent administrator. |
| F / P1 acceptance | `.github/workflows/ddl-free-runtime.yml`, Issue228 | Rename the PR branch: original mandatory runtime/PG jobs are SKIPPED. PR229 only broadens one branch prefix. | Branch-independent PR/dispatch scope for these safe hosted jobs. `acceptance` requires all five terminal successes, matching SHA/run/attempt, complete artifacts, JUnit/inventory and source/output SHA256. Skipped/missing/old-attempt jobs BLOCK. Repository branch-protection configuration is external and was not changed. |
| G / P1 physical blocker | `grid/runtime_gate.py`, `grid/fleet_control.py`, PC4 runbook | `test_pr227_authorization_boundary.py` proves persisted ACTIVE allows market work with an empty HTTP token; empty RESUME targets can set ACTIVE without ACKs. Schema validation does not prove current operator authority. | Runtime authorization redesign remains BLOCKED; G5 runbook has an unconditional blocking throw before the reference launch command. No new authorization flag or physical approval is invented. |

## Startup, dependencies and lifecycle audit

Coordinator startup calls `service.prepare_database` (connect, verify, fail-close
and close pool), wraps the pool in `FencedPool`, then starts `ControlRuntime`.
Leader startup builds the feature/derived/scientific services and the refresh,
Telegram, retention, maintenance and ML tasks. Explicit schema ensurers and
migrations are called by `schema_preparation`, not those runtime paths.
Workers use remote ingest; the three DB-pool constructors (db/storage/strategy)
pin `pg_catalog,public` on acquisition. Strategy subprocess verifies before
loading plugin code; plugins are trusted Python, **not sandboxed** by this check.
Legacy importer uses transactional typed-array DML, no temporary-table DDL.
The static SQL/AST gate and the 32 original real PG cases remain mandatory.

Preparation retains its advisory lock across baseline, migrations 1–48,
supplemental schema and seal, in one transaction. Preparation cancellation,
SQL failure, concurrent preparation, missing/unsealed/partial registries,
constraints/index48 and runtime reconnection are exercised by the original PG
inventory. Runtime never repairs them. Existing exception swallowing in polling
loops means health/liveness under repeated operational failure still needs
physical fault evidence; a green startup is not an HA guarantee.

Fingerprint/source verification is a startup snapshot. A trusted DB owner or
administrator can change functions, grants, schema or data afterwards. No client
startup check can revoke that authority. Source custody, loader/dependencies,
trusted DBA and exclusive change control are preconditions, not proven by the
seal. This change alters source/catalog digests: old sealed DBs fail closed;
there is no automatic reseal, in-place upgrade or downgrade.

## Evidence and gates

Original evidence was independently re-downloaded (not copied from author files):
[runtime run39814736275](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/39814736275),
[staging run39814736230](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/39814736230).
`tools/verify_pr227_original_evidence.py` checks 9 artifacts / 49 files / 61
source Git blobs, exact inventories and zero skipped/failed/error cases:
284 runtime offline + 695 staging/plan per Windows/Ubuntu × Python3.11/3.12;
32 actual PG18 cases. Download ZIP hashes and the runner trust boundary are not
independently authenticated by that script.

Candidate evidence must be read from its own exact-head Actions; original green
results never transfer to this branch. Expected candidate runtime inventory:
313 offline cases per matrix cell, 32 original PG cases, 12 baseline reproductions
and 12 candidate rejection cases. Baseline-vulnerability PASS is deliberately
not candidate security PASS. The baseline staging matrix remains 89+575+31=695.
Runtime Guard195 and LegacyRollback52 are synthetic tests in fresh PowerShell5.1
processes on Windows; PowerShell5.1/7 parse installer scripts. None observes PC4.

| Gate | Acceptance |
|---|---|
| Code/SQL regression checks | PASS only after candidate exact-head terminal CI and complete evidence |
| Actual Windows SID/ACL, protected source/token, PGDATA custody | BLOCKED; 0/10 NOT_RUN |
| Continuous schema/privilege immutability against owner/admin | BLOCKED; outside startup snapshot guarantee |
| Current operator authorization, process-level market quarantine | BLOCKED; required before PC4 runtime |
| Trading and physical execution | NOT_AUTHORIZED / NO-GO |

No VM, host connections, install, SQL/bootstrap, service/ACL change, deployment
or merge is part of this audit. Schema-2 and physical permitting flags remain
unchanged. Physical SID/ACL: **0/10 NOT_RUN. Execute NOT_AUTHORIZED.**
