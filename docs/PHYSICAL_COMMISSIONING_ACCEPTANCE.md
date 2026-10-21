# Physical commissioning acceptance — independent coordinator (Draft)

**Decision: BLOCKED / NO-GO. PC4 0/10 physical cases NOT_RUN; Execute NOT_AUTHORIZED.**
This is a metadata-only acceptance specification, not an executor, installer,
physical attestation, L1/L2 approval, production release or schema-2 gate.
Based on Draft PR #216 at `b0d31eaaa2221da357ef6127fca3f0207c4248e2`.
Keep this coordinator branch separate from PR #216 and its pinned physical package.

## Readiness matrix (2026-10-21)

| Component/host | Evidence | Decision |
| --- | --- | --- |
| PC4 SID/ACL | Offline harness/mock tests; actual actor 0/10 NOT_RUN | BLOCKED |
| PC4 logon | Direct SeBatchLogonRight owner-reported; effective interactive allow/deny UNKNOWN; seclogon reported Stopped/Manual | BLOCKED |
| LS5 | Physical identity, services, ACL, ownership not independently attested | UNKNOWN |
| LS7 | Physical identity, services, ACL, ownership not independently attested | UNKNOWN |
| SSH/Tailscale | Network connectivity does not prove isolation, host authenticity or access-control enforcement | UNKNOWN |
| PostgreSQL/PGDATA | PlanOnly and metadata diagnostics; native owner/layout, backup and restore unproven | BLOCKED |
| VM lab | Twelve actual guest negatives NOT_RUN/BLOCKED_UNPROVEN | BLOCKED |
| Attestation/replay | Test keys and model only; correlated checkpoint+anchor rollback unresolved | BLOCKED |
| Production | No independently approved physical commissioning package | NO-GO |

## Gate DAG and separation

G0 inventory/baseline and protected data -> G1 exact source/artifact provenance,
separate owner authorization, independent reviewers, stop authority -> independent
G2A PC4 SID/ACL, G2B PostgreSQL/PGDATA, G2C Windows network/services, G2D VM
negative cases/attestation -> G3 cross-component evidence reconciliation,
no authority promotion -> G4 distinct production approval.

Parallel offline reviews are allowed. Physical execution in any G2 lane needs its
own explicit owner approval, run scope, immutable baseline and stop/rollback plan.
Passing G2A cannot grant PGDATA ownership; passing network connectivity cannot
grant token isolation; public test-key attestation cannot grant production access.

## Formal outcomes

* PASS: only a **separate approved physical verifier** has verified the exact
  expected tests, native identities, provenance, unmodified baseline and
  independent custody. This module deliberately **cannot issue PASS**.
* FAIL: a verified violation of the expected isolation/integrity property;
  stop dependent execution, preserve evidence.
* BLOCKED: missing authorization, prerequisites, incomplete receipts, unknown
  actor/PID, unproven ownership or absent physical evidence.
* UNKNOWN: no reliable current observation; never treat as PASS.
* NOT_RUN: an individual physical test not executed, not a failed negative ACL test.

PC4 must independently prove exactly ten cases: for each Collector/Storage role,
token, own_write, own_read, foreign_read_denied, foreign_write_denied. Only actual
Win32 ERROR_ACCESS_DENIED=5 on the intended foreign-file open is a negative PASS.
File not found, sharing violation, logon failure, timeout or logger failure is not.

Current launcher uses credentialed ProcessStartInfo / CreateProcessWithLogonW;
SeBatchLogonRight alone does not establish effective SeInteractiveLogonRight.
Applicable group-derived SeDenyInteractiveLogonRight and Secondary Logon service
prerequisites remain unknown. Do not start seclogon or grant rights to make a PASS.

## Evidence bundle contract for a future, separately authorized run

* `manifest.json`: schema/version, unique run ID, exact host/role IDs, reviewed
  source SHA, pinned package manifest SHA256, explicit scope, approvals, STOP owner.
* `events.jsonl`: strict UTF-8/LF, no duplicate keys or nonfinite values,
  ordered per-case append/flush, exact run identity, fixed error codes and
  explicit missing/partial state. JSONL parser is metadata-only.
* `results.xml`: JUnit exact test node-ID inventory bound to source SHA,
  no invented/subset/duplicate test names, zero skips for a claimed complete run;
  failures and incomplete results remain visible. JUnit is not attestation.
* `sha256.json`: rehash every listed artifact and reject missing/unexpected
  files. Exclude the index itself and subsequent completion marker; verify the
  index through a separately pinned manifest/trusted custody chain.
* `approval.json` and `review.json`: independently authenticated approval
  references and review decisions. Merely writing these files is not approval.
* Private original token/SID/SDDL, Windows ACL and service snapshots, process
  intent/PID records, and pre/post ownership observations stay outside public CI.
  Do not log credentials, private SIDs or SDDL in GitHub.

Bind artifacts to **actual** checkout HEAD and original producer bytes; PowerShell
ordered-byte digest is not Python canonical-JSON SHA256. Validate the complete
JUnit node set, not a minimum threshold. Hash consistency cannot establish
independent observer identity or durable replay resistance.

## STOP / recovery / rollback

1. Unknown SID, rights, ACL, owner, package SHA, permissions or host identity:
   STOP as BLOCKED before actor/SQL/service actions; never auto-repair.
2. Unexpected foreign access: FAIL, stop further tests, preserve canaries and
   all receipts. Logon error, missing canary, logger failure: BLOCKED/FAIL
   diagnostic, **never** count as denied-access PASS.
3. Partial or truncated JSONL, hash mismatch, unknown PID/child or launch intent
   without durable PID: BLOCKED, preserve evidence, forbid unattended cleanup.
4. PGDATA ownership/layout mismatch or pre-existing cluster: STOP, no initdb,
   deletion, role/service changes or SQL; separate backup/restore design.
5. Network outage or attestation replay ambiguity: STOP dependent gates; require
   fresh independent identity and continuity evidence, never auto-resume.
6. Cleanup requires separate approval, original manifest, exact GUID fixtures,
   process absence, allowlisted nonrecursive deletion; never remove evidence,
   unknown resources, role parents or pre-existing data.
7. Code rollback is a reviewed revert to a pinned SHA. Host/account restoration
   and PostgreSQL recovery are **separate authorized procedures**; a successful
   Git revert does not restore host state or data.

## Offline implementation

`installer/physical_acceptance.py` accepts **only** synthetic PLAN_ONLY,
BLOCKED receipts. For PC4 it enforces exactly ten ordered NOT_RUN cases; for
VM lab twelve NOT_RUN cases. All positive authority and schema-2 aliases fail
closed. `assess` never authorizes deployment even if all untrusted source
statuses say PASS. `verify_jsonl` validates only bytes/digest/shape/run ID,
not provenance or native ownership. These deliberate limits prevent a forged
metadata report from authorizing physical execution.

No merge, VM, SQL/initdb, service/account/policy/ACL/network changes, deployment,
LS5/LS7 or PC4 physical test has been performed by this coordinator.
