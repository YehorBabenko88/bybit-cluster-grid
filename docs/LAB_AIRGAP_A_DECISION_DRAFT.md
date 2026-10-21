# Air-gap A provisional decision (L1 draft)

**PROPOSED / UNVERIFIED. L1 NO-GO; L2 and physical execution NO-GO.**
Owner direction: A, provisional; registered independent human reviews: zero.
This is not a completed architecture/security approval. All authority/readiness
flags remain false; schema-2 off; all twelve guest scenarios NOT_RUN.

Base PR #213: `612a9daac26360886e0571ec9fe55c3a557c5da3`.
PR #211/#212/#213 and prior RC are frozen. This new planning branch changes no
runtime, installer, adapter, migration, native verifier or physical resource.

## Scope and decision

The first proposed lab is physically disconnected from production, Tailscale and
external networks. Its goal is to design disposable negative ACL/token/PGDATA
experiments; it is **not durable anti-rollback or live freshness certification**.
Dedicated hardware is owner-provided and unverified. Variant B is not a fallback.
No hidden gateway, return channel, general-purpose removable-media import or
automatic evidence approval is introduced to make A appear functional.

This stage produces a bounded machine-checked public proposal and human review
packet. Validation means shape only. The full closed schema is the symbolic
`lab-airgap-a.example.json`, checked by `installer.lab_airgap_a`. No hostnames,
CIDRs, private addresses, actual SIDs, key material, native evidence, approvals,
commands or execution reports are accepted. Wrong types, duplicate/unknown JSON
fields, A/B ambiguity, missing second reviewer and fabricated readiness fail
closed. Unknown hardware/time/PGDATA are explicit blockers even when shape-valid.
This schema cannot register real reviews or promote itself to GO. An approved
future private contract would require a separately reviewed change.

## Trust and non-guarantees

The operator controls the lab but cannot author their own independent evidence.
Two observers and the STOP custodian have separate proposed custody domains;
names in JSON do not prove identity or independence. An observer controlled by
the host administrator, sharing credentials, root keys or snapshot storage is
not independent. CI and AI are not human reviewers or witnesses.

Normal unprivileged adversary tokens can be tested against Windows access
checks in future isolated fixtures. A privileged host administrator can replace
guests, falsify captures and roll back all local state. Handles, ACLs, file IDs,
SID syntax, signed guest data and matching digests cannot defeat that actor.
Suspected host/admin compromise means STOP and loss of local evidence trust.

Trusted time is UNVERIFIED. Host/guest clock, filesystem mtime and copied receipt
time are not authorities. An external signed timestamp says what its signer
asserted under its policy; it does not prove collection, arrival or live
freshness. Outbound-only transfer cannot deliver a fresh witness challenge into
the lab. No two-second freshness, online lease, live trading or production HA
claim can follow from this offline design.

Replay rejection needs exact run/case/attempt IDs, plan/candidate digests, observer
identity, artifact digest, sequence and prior-receipt binding, plus an independently
retained accepted-ID ledger. This ledger is a **future design**, not implemented
by the pure validator. Reused IDs, conflicting same-ID digests, unknown prior
receipt and uncertain ordering must block acceptance. A new arbitrary ID does
not prove a rolled-back lab is fresh. The external archive may detect an exact
duplicate, but that is weaker than durable monotonic lab-state continuity.

Durable anti-rollback remains NOT_IMPLEMENTED without an independently durable,
provably monotonic anchor and trusted time. Rolling back checkpoint, witness
history and all anchors together can be indistinguishable from history that
never progressed. This is a hard blocker for continuity/freshness certification.
No file shuttle is an external witness. A hash only checks equality against a
trusted digest, not provenance, freshness, custody or safe content.

## Resource and approval boundaries

See [topology](LAB_AIRGAP_A_TOPOLOGY.md),
[transfer](LAB_AIRGAP_A_EVIDENCE_TRANSFER.md),
[first-test protocol](LAB_AIRGAP_A_FIRST_TEST_PLAN.md) and
[risk/owner checklist](LAB_AIRGAP_A_RISK_OWNER_CHECKLIST.md).
These are proposed observations and gates, never a performed inventory.

L1 requires two independent human architecture/security reviews of this exact
plan/SHA with concerns and explicit decisions, plus reconciled resource, custody,
transfer and PGDATA assumptions. Please provide those reviews in the new Draft
PR; approvals must come from the humans themselves. Do not post secrets, SID
dumps, private IPs or key material. Use a private review mechanism for real
identities, hardware evidence and enrollment material; public comments can cite
symbolic roles and redacted evidence references. Current review status is NOT_REVIEWED.

L2 requires a separate owner authorization for specific dedicated resources and
operations after L1; it does not authorize L3 native observations, L4 adversarial
tests or L5 canary. Durable/freshness certification remains a distinct blocked
goal even if a future offline ACL-only experiment is separately permitted.

## Recovery policy

Power loss, disputed evidence, unknown token/storage identity, missing observer,
boundary breach or interrupted custody means STOP. Preserve journals, evidence
and external receipts. No automatic restore, retry, cleanup or acceptance.
Guest snapshot restore cannot restore authority. Reconcile surviving independent
history under two-owner review; unknown continuity requires a declared new
enrollment/experiment with explicit authorization, not a fabricated next epoch.
Never downgrade schemas automatically or delete WAL/history to repair a test.

The PostgreSQL schema-1 path mismatch remains unresolved: PowerShell intent
`<parent>\<run>_<node>\postgres\data` versus adapter intent
`<parent>\<run>\<node>\pgdata`. No rewriting, historical manifest edits or
schema-2 bypass. Actual PGDATA experiments are blocked until a reviewed binding
of plan intent and native identity exists. No SQL/initdb/PostgreSQL is run here.
