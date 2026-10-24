# LS5 -> PC4 independent physical acceptance (2026-10-24)

**NO-GO. Physical PC4 SID/ACL 0/10 NOT_RUN; Execute NOT_AUTHORIZED;
Cleanup NOT_AUTHORIZED; Deployment NO-GO.** This branch is an independent
metadata-only QA proposal from PR #237 exact HEAD
`e25197b169ef0e5f37b5bd0030ee4a97b13965e2`, not a physical test.

## Independent baseline and Actions

PR #237 Actions on that exact SHA: 9 successful workflow conclusions
(integration-evidence-audit, physical-deployment-harness,
ls5-acl-remediation, commissioning-manifest, composed-safety-gate,
isolated-postgres-offline, preflight, windows-commissioning, windows-bundle)
and six **SKIPPED** workflows (pgdata-intent-offline, windows-lab-planning,
pc4-sid-acl-offline, lab-airgap-a, lab-witness-l1, offline-rc-review).
Do not count skipped workflows as success. PR #237 author reports 130
offline tests per Ubuntu/Windows Python 3.11/3.12, 16 structural hosted
Windows cases per PowerShell 5.1/7 and 14 PlanOnly per shell; independent
acceptance must download and rehash artifacts and compare exact JUnit
test node IDs, source HEAD and run attempt before treating these counts
as independently verified. No GitHub-hosted runner is LS5 or PC4.

PR #238 exact HEAD `116bc11bb4c661c8b77be69c64b88f48a529968a`
is a design-only native ACL observer/executor stage, **not** a working
authorized Apply/Rollback executor. Neither PR repairs LS5 host ACLs.

## Acceptance vocabulary

* `SYNTHETIC_PASS`: deterministic offline model/hosted fixture success,
  never a host assertion.
* `HOST_READONLY_PASS`: independently sourced protected-host read-only
  observation with bounded scope; not authorization to write or execute.
* `PHYSICAL_PASS`: independently witnessed, separately authorized physical
  operation with original native evidence and approved custody. No such
  status exists today.
* `DEPLOYMENT_GO`: separate final owner decision after all mandatory
  gates, rollback proof and review; never derived from CI or receipts.
* `BLOCKED`: required authorization, custody, integrity or proof absent.
  `FAIL`: verified invariant violation. `UNKNOWN`: unobserved or
  inconclusive. `NOT_RUN`: physical action did not occur.

## Formal stage matrix and independent approvals

| Gate | Mandatory evidence | STOP / recovery | Current |
| --- | --- | --- | --- |
| G0 LS5 read-only inventory | Host identity, exact processes/tasks/services, command lines, six releases, paths/ancestors, owner/SID/SDDL, effective rights, baseline hashes | Unknown identity, writable executable closure, unclassified task -> STOP; preserve baseline, no repair | BLOCKED |
| G1 ACL remediation authorization | Owner-signed exact scope, trusted observer, source/package hashes, writer exclusion, rollback owner | Missing handle custody, open writer, inherited delete rights -> STOP; no Apply | NOT_AUTHORIZED |
| G2 trusted bootstrap/rebuild | Off-tree trusted toolchain, interpreter/DLL/import closure, pinned release, secrets exposure response | Poisoned runtime or unknown source -> STOP; reconstruct only under separate approval | BLOCKED |
| G3 PostgreSQL readiness | Independent PGDATA owner and ACL, cluster/service inventory, version, WAL/backups, restore rehearsal on disposable environment | Existing data, owner mismatch or unknown path -> STOP; no SQL/initdb | BLOCKED |
| G4 network preflight | Tailscale/SSH identities, port/service/firewall inventory, approved paths and trust boundaries | Untrusted endpoint/route, ACL gap -> STOP; no automatic firewall repair | BLOCKED |
| G5 coordinator start authorization | G0–G4 reviewed, trusted code, fixed service principal, run window, STOP/rollback plan | Missing approval or unknown tasks -> STOP; remain disabled | NOT_AUTHORIZED |
| G6 PC4 provisioning | Separate owner plan, full SIDs, account/logon rights, protected staging, approved GUID fixtures | Unknown effective token/rights, existing path, unpinned package -> STOP | BLOCKED |
| G7 custody verification | Independent exact package manifest, artifact ZIP + internal SHA, protected evidence destination, original file identities | Mismatch, reparse, mutable parent or custody break -> STOP | BLOCKED |
| G8 CollectLocal authorization | Fresh owner scope, read-only native observer, private redaction/custody and STOP authority | No explicit approval, policy uncertainty -> STOP | NOT_AUTHORIZED |
| G9 PC4 10 SID/ACL tests | For each role token/own-write/own-read/foreign-read-denied/foreign-write-denied; original native token/ACL, JUnit/JSONL and witness | Foreign access success -> FAIL; missing canary, timeout, unknown PID -> BLOCKED; retain all evidence | 0/10 NOT_RUN |
| G10 limited pilot | G9 physical review, bounded workload, monitoring, safe shutdown and separate activation permission | Any drift, wrong PID, data/port mismatch -> STOP; isolate, no auto-restart | NO-GO |
| G11 rollback | Separate approved per-object recovery, immutable journal, original descriptor and native file IDs, data preservation | Missing receipt, uncertain child or restoring vulnerable ACL -> BLOCKED/manual forensic review | NOT_AUTHORIZED |

Each gate has its own human authorization; success of one is not a
credential for another. Recovery of code, host ACL and PostgreSQL
are separate procedures. Existing release recovery is **not** ACL
rollback. Restore must not silently reopen Users write access.

## Evidence contracts

* **HEAD:** exact PR head and base SHA; GitHub default merge checkout is
  insufficient. Pin run ID/attempt, runner OS and Python/PowerShell matrix.
* **JUnit:** exact ordered test node-ID inventory per pinned source, explicit
  test/failure/error/skip counters, no duplicate/unknown/omitted tests,
  skipped workflows marked BLOCKED. A success conclusion alone is not JUnit.
* **JSONL:** strict UTF-8 LF, duplicate-key and nonfinite rejection, ordered
  events, source SHA, run/attempt and fixed codes; partial/truncated is BLOCKED.
* **SHA256:** rehash downloaded artifact ZIP and each inner file against
  independently pinned receipts. Index integrity is not signer provenance.
* **Custody:** preserve original source, trusted signer/witness identity,
  private native SIDs/SDDL and raw logs. Public CI must not expose secrets.
  Self-reported `physical_pass=true`, copied attestation fields or matched
  hashes do not establish physical observation.
* **Mock promotion:** no `SYNTHETIC_PASS` or `HOST_READONLY_PASS` can
  automatically become `PHYSICAL_PASS` or `DEPLOYMENT_GO`.
* **Replay:** durable checkpoint+anchor coordinated rollback is unresolved.
  No production anti-rollback or native attestation claims are accepted.

## Prioritized findings

**P0:** LS5 SYSTEM-executable inputs reportedly writable by Users and
secret configuration readable by Users; native ACL remediation/exclusive
custody and trusted rebuild unproven. Execute/cleanup/deployment forbidden.

**P1:** Independent host identities, open handles, full code/DLL closure,
effective Windows principal rights, PostgreSQL ownership, network boundaries,
operator authorization, original artifact custody and recovery receipts
not yet independently established. Six skipped workflows must never be
treated as green gates.

**P2:** CI cross-PR provenance, exact JUnit inventory and ZIP receipt
verification require continuous independent refresh; metadata-only gate
cannot authenticate forged internally consistent receipts or protect
against coordinated replay rollback.

## Implementation scope

`installer/ls5_physical_acceptance.py` is a read-only offline checker.
It validates **untrusted metadata** and exact JUnit/JSONL/SHA256 internal
consistency and deliberately returns no physical or deployment authority.
`tests/test_ls5_physical_acceptance.py` includes negative cases for
forged PASS, wrong HEAD, schema-2 aliases, duplicate JSON keys, missing,
reordered or duplicate test cases, JUnit mismatch, SHA mismatch and fake
PHYSICAL_PASS. No host connections, native calls, SQL, ACL, service/task
changes, VM, deployment, merge or physical testing.

## Exact-head workflow coverage audit

`audit_workflow_runs` checks strict workflow records containing name, exact
commit SHA, run ID, attempt, lifecycle status and conclusion. It rejects
duplicate workflow names, mixed HEADs, invalid attempts and contradictory
completed/conclusion states. It requires ten relevant workflow names,
including the independent acceptance workflow; missing, queued, skipped,
cancelled or failed required workflows prevent `offline_ci_complete`.

Even when all required workflow conclusions are success, the output is
**BLOCKED**, with `artifacts_independently_verified=false`,
`physical_pass=false`, and `deployment_go=false`. This helper audits a
caller-supplied manifest, **not GitHub's authenticated API**: independent
fetching of the actual workflow runs and downloaded artifacts is mandatory.
A skipped unrelated workflow is listed, never counted as a successful test.
