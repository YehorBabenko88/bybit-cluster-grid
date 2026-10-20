# L0 Windows laboratory commissioning design — DRAFT / physical NO-GO

This is architecture and non-executing metadata validation only. Frozen PR211
HEAD83c7c034668d02ce833e4f9750409b74641b9070 is unchanged. Its run39436629147
verified the bounded offline RC, not a machine. No VM, PostgreSQL/SQL/initdb,
installer, service/task, native SID/ACL query, Tailscale, LS5/LS7 or production
operation is authorized. No merge. Schema2 disabled; all authorization/readiness
flags false; twelve real cases NOT_RUN. Passing this checker does not complete
L0 review or grant L1/L2 approval.

## 1. Purpose, assumptions and options

Goal: a reproducible disposable Windows lab for later one-node then two-node
negative tests, isolated from all real trading, Telegram, Grid data and production
credentials. This document is PROPOSED; each resource is UNVERIFIED; durable
anti-rollback is NOT_IMPLEMENTED. Existing offline RC is VERIFIED_OFFLINE_ONLY.

Options: (A) same-host VMs and model-only witnesses, useful for synthetic failures
but no independent observer/admin boundary; (B) dedicated disposable host plus
separately administered external observer/time/witness appliances; (C) existing
production PCs, forbidden. Proposed target is B; A never gains physical authority.
No hardware or transport is selected or discovered by this PR. If administrator
of the lab host is hostile, assume guest memory/storage/hypervisor evidence can
be rewritten: STOP. Claiming admin resistance would require a separately proved
hardware/attestation boundary, not more same-host VMs.

## 2. Zones, resource separation and safe defaults

* Compute zone: a dedicated nonproduction Windows/Hyper-V host, installation
  media/build/licence and hypervisor provenance reviewed by humans. Two fresh
  guests CONTROL and WORKER, per-run image hashes, unique VM/host/run IDs, off and
  not provisioned by default. CPU/RAM/disk quotas chosen later from measured
  needs; reserve host headroom, no actual disk exhaustion or reboot tests.
* Data-plane zone: proposed private virtual switch, no host-management adapter,
  default gateway, DNS forwarding, NAT/bridge, internet/production/Tailscale,
  guest dual-homing, shared folders, clipboard, enhanced-session or redirected
  host drives. Initial guest addresses UNASSIGNED; operator must prove no overlap
  before assigning any lab-only range. VLAN/name alone is not evidence. Block
  IPv4 AND IPv6 routing, ICS/RRAS/automatic default switches and covert host
  sharing; evidence must cover all adapters/routes/filters, not one interface.
* Trust zone: two independently controlled observers and two durable witnesses
  outside the lab host's snapshot/admin domain; operator keys separate from both.
  They must have no production or Tailscale route either. Their observations
  cannot be vouched for by lab guests or the hypervisor they assess.
* Storage zone: dedicated guest-only volume (example L:, identity UNASSIGNED),
  per-run/node roots, no shared host mounts, production DB/WAL/env or fallback
  directories. Volume/file identities, ACL and exclusive ownership unknown until
  L3. Example IDs/paths/ports are proposals, not allocations or reservations.
* Runtime zone: no services or tasks registered; PostgreSQL16 loopback proposal
  only, coordinator separate proposed port. Worker would communicate only with
  a future lab coordinator endpoint under independently reviewed authentication.
  No real exchange/API keys, live trading or Telegram. Test data synthetic and
  explicitly non-live; no research/metadata result grants trading authorization.

Private Hyper-V switches connect guests on the same host without host-network
connectivity, unlike internal/external/NAT designs: [Microsoft networking](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/plan/plan-hyper-v-networking-in-windows-server).
That is a topology feature, not proof of the actual configuration or a hostile
hypervisor boundary.

**Unresolved trust transport:** a private-switch-only, no-sharing lab has no live
route to external witnesses. Do NOT silently add one. A later reviewed nonrouting
proof mailbox/allowlisted trust transport, independent of host assertions, is
required for real-time challenge/anchor freshness. Untrusted transport may drop,
delay or replay signed records; it must never grant authority or forward arbitrary
traffic. Human-carried evidence can support document review but cannot satisfy a
two-second live freshness budget. Until transport, clock and witness provenance
are demonstrated, L3 timing evidence/L4 replay tests remain blocked. The example
manifest deliberately has null endpoints and no routes; it does not pretend this
design conflict is solved.

## 3. Resource manifest and offline checker

`lab-manifest.example.json` is a closed L0 design schema, not a runtime manifest.
Each resource wrapper's evidence_status=UNVERIFIED applies to EVERY field under
proposal. Proposed safe booleans such as dedicated=true are desired configuration,
not measured facts. Actual SID/token/root/image fingerprints are null; OS/build,
volume, archive and endpoints unassigned. No secret material, live commands or
automatic provisioning/deletion entry points are accepted.

`installer.lab_manifest_design.validate_text` reuses bounded strict JSON parsing
(duplicates, invalid Unicode, excessive nesting/size/types/nonfinite values
rejected), exact fields/types and pure lexical checks. It rejects self-attestation,
authorization flags, reused IDs/SIDs/custody labels, unsafe paths/ports/routes,
existing services/tasks, schema2 aliases, fake PASS and changed case/gate sets.
It performs no filesystem discovery, path resolution, network or native queries.
CLI consumes bounded stdin and prints fixed diagnostics; exit0 means metadata
valid only. Every report remains BLOCKED/NO-GO, verified_safety_cases=0 and flags
false. Matching distinct custody labels is not actual independence.

This checker deliberately does not ingest signed native evidence or accept L2+
approvals; a future separate reviewed evidence/approval format is needed. No
semantic translation into runtime schema2 is implemented.

## 4. Independent identities, tokens, ACLs and operator authority

Proposed roles: operator; observer_a; observer_b; owner; verifier; adversary;
separate host administrator. Distinct IDs/labels alone do not establish control.
Two human custodians must independently verify observer key custody, bootstrap
fingerprints, OS/image/source provenance and the absence of shared admin/reset
authority. Observers on the same mutable lab host are not independent.

Future L3 collectors must obtain effective primary AND impersonation token user,
group attributes (enabled/deny-only), restricted SIDs, privileges and enabled
states, elevation/type, integrity/mandatory policy, logon/authentication/session
IDs and token identity/modified IDs at the actual access boundary. Query errors,
buffer truncation, unknown impersonation or principal mismatch STOP; process
owner name/declared SID/WMI display text is insufficient. Future API design uses
[GetTokenInformation classes](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ne-winnt-token_information_class)
but this PR never invokes them. Use real access checks under the intended token,
not a hand-written approximation from account names or ACE ordering.

Object evidence: native volume/file identity, reparse/hardlink counts, owner SID,
complete DACL/SACL availability, inheritance/protection, generic-right mapping,
WRITE_DAC/WRITE_OWNER/delete-child/backup/restore/impersonation privileges and
effective access. Do not assume DACL deny beats privileged bypass. Pin target,
ancestors and consumer lifetime using reviewed handles; timestamps/path strings
and polling cannot prove absence of ACL ABA or preexisting writable mappings.
Unknown identity/ACL/handle state blocks; no automatic permission repair.

Approval envelope proposal binds lab/run/host/VM/image/source/artifact/manifest
digests, exact resource IDs, named gate/test, nonce/monotonic sequence, policy/key
epochs, trusted issuance/expiry/uncertainty, witness receipts and operator plus
two independent observer signatures. Raw observations and signed digest/collector
version retained separately. Verify signer role, revocation, scope, uniqueness and
freshness; approvals are single-scope and cannot authorize another stage, node or
cleanup. Public test Ed25519 keys and synthetic PASS are explicitly forbidden as
live trust roots. Standard maintained crypto only; no DIY signature protocol here.

## 5. Trusted time and durable anti-rollback proposal

Do not trust guest wall clock, snapshot-restored counters, host time sync or local
NTP setting as authority. Proposed dedicated independent timestamp authorities
provide signed challenge-bound time with bounded uncertainty, pinned policy/root,
nonce and expiry. [RFC3161](https://www.rfc-editor.org/rfc/rfc3161.html) supplies
standard timestamp concepts; a valid token does not establish trusted source
custody, network freshness or nonrollback by itself. Proposed uncertainty bound
two seconds requires measurement and reviewed transport; source unreachable,
drift, stale/future token or uncertain expiry STOP, never fall back to guest time.

Replay ledger proposal outside all lab snapshots: issuance→claim→consume state,
CAS revision, per-symbol/session claimant fencing and lease, key/policy epochs,
global nonce uniqueness and no unsafe eviction. Before ACK, both independent
durable witnesses must append and persist the same nonce/sequence, previous-head
hash and payload/decision digest. Two-of-two is a safety/availability tradeoff,
not a claim of Byzantine consensus. A failed/partitioned witness means STOP;
never degrade to one, advance after uncertain ACK or treat signature as persistence.

Crash design: preserve intent and both witness receipts; before-commit may retry
only the identical intent, after-commit must reject duplicate consumption even if
ACK lost, torn/discordant/unknown commit quarantines. Recovery consults fresh
external monotonic anchor before any replay. Disk flush/atomicity, witness custody,
monotonic hardware/administrative reset resistance and cross-witness recovery need
independent tests. Restoring guest alone must not restore witness state. If ledger,
both witnesses, trust roots and anchor can be rolled back together, reuse cannot be
distinguished: explicit residual limitation, not solved by hash chains/signatures.
Key loss/revocation/anchor reset require out-of-band approved recovery preserving
old revocations/high-water, never zeroing counters. All of this NOT_IMPLEMENTED.

## 6. Native PGDATA compatibility proposal

Source, not the coordinator's swapped shorthand, is authoritative:
PowerShell New-GridLabPlan root=<parent>/<run>_<node> and template PGDATA=root/
postgres/data; isolated_postgres_plan schema1 requires<parent>/<run>/<node>/pgdata.
The source anchors are installer/isolated-deployment-core.ps1:22,139 and
installer/isolated_postgres_plan.py:43 at frozen83c7c03. Both legacy contracts stay
unchanged and incompatible; no old plan/journal is rewritten or cleared.

Proposed `LAB_PGDATA_INTENT_V1_DRAFT` is a new design envelope, NOT runtime schema2:
bind source adapter-plan digest, separate PG-plan digest, run/node/guest/volume
IDs, explicit source layout enum, lexical target and native evidence session,
binary provenance, schema compatibility and operator scope. Future adapter must
accept one explicitly versioned new-cluster intent, never infer mapping from a
suffix/name or accept transferred ownership claims. Owner/current path/ancestors
must be pinned at consumer boundary under existing mutex/fencing; expiry or loss
of evidence aborts before writes. PostgreSQL remains loopback inside guest. No
preexisting cluster, migrations/downgrade, initdb or SQL allowed in this stage.
Until native mapping/identity lifetime is proved, SCHEMA1_ADAPTER_MAPPING_BLOCKED
and physical ownership blockers persist. No mapping executor is included here.

## 7. Twelve planned negative VM cases — all NOT_RUN

These IDs map explicitly to the existing vm_lab_plan.CASES vocabulary, not to the
different principal-model VM-NEG list. Each needs new scoped L4 approval. Common
evidence bundle: two independent collectors' raw token/access/identity/handle
observations, timestamp+nonce, before/after object state and denied API result,
source/image/manifest digests, witness receipts and operator incident record.
Signatures authenticate approved source custody only if independently established.
Expected STOP/BLOCKED on uncertainty does not turn missing evidence into a PASS.

|ID / case|Future fixture stimulus|Expected result / specific evidence|Preservation and recovery|
|---|---|---|---|
|01 write|adversary token attempts file/data/child write|access denied; target bytes/identity unchanged; token-bound access result|preserve fixture/log, quarantine if write observed|
|02 delete|delete and ancestor delete-child attempt|denied; same live pinned object and parent identity|no recreate to hide loss; preserve evidence|
|03 write_dac|request WRITE_DAC/DACL replacement|denied; full DACL snapshot+effective token proof|no automatic ACL repair|
|04 write_owner|owner takeover/WRITE_OWNER attempt|denied; owner unchanged; privilege-state evidence|freeze on ownership change|
|05 acl_mutation|scheduled ACL change before/during consumer|consumer blocks on inconsistency/uncertainty; timeline+held-handle evidence|preserve altered ACL and stop|
|06 acl_aba|change→restore DACL between samples|STOP unless independent evidence proves interval protection; known ABA limit never called PASS|quarantine event; no restore-as-proof|
|07 inherited_acl|inject inherited/generic write ACE|reject before consumer; complete inheritance/generic-mapping evidence|do not remove ACE automatically|
|08 junction|replace path with junction/reparse target|reject; native target/ancestor identity and reparse evidence|leave redirect untouched until reviewed cleanup|
|09 ancestor|rename/substitute ancestor during pin|deny or abort consumer; handle scope and parent identities|stop; no path rewriting|
|10 existing_mapping|preexisting writable handle/mapping before pin|STOP on unknown mappings; exclusion evidence required; cannot infer absence by enumeration alone|no forced handle close or process kill|
|11 privileges|elevated/backup/restore/debug/impersonation token, hostile-admin claim|deny; effective token privileges; hostile host admin→STOP/out-of-scope|preserve VM; no privilege escalation exploit|
|12 distinct_token|reuse actual token/SID or substitute role/approval|deny; separate actual logon/token identities and independently controlled signers|revoke scoped approval in external ledger, retain artifacts|

Cross-cutting schedules for01–12: network isolation unknown, missing/forged observer
proof, duplicate messages/lost ACK, process crash, delayed takeover/stale fence,
clock drift, key revocation, external witness loss, old guest snapshot and correlated
anchor rollback. Bound resource budgets and fault injection; no real disk fill,
production network interruption, forced reboot, privilege exploit or cleanup.
Each schedule remains NOT_RUN and inherits the same preserve-only STOP policy.

## 8. Staged admission matrix — no automatic stage advance

Every future decision binds exact source SHA, image/manifest/evidence digests,
named human custodian, explicit rollback plan and signed scope. All current
gate authorized flags remain false. A text GO criterion is not an approval.

|Gate|Named role responsible|GO criteria for a future separately approved decision|NO-GO / rollback|
|---|---|---|---|
|L0 design review|operator + both observers|architecture/risk/ownership/transport proposal reviewed, freeze source83c7c03 reference|unknown boundary→revise docs only|
|L1 offline contract|observer_a, observer_b review|strict manifest tests, exact offline receipts and zero fabricated evidence; no physical operations|failed/changed digest→stop, preserve source/receipts|
|L2 provisioning approval|operator, separate approver|NEW explicit user consent; dedicated resources/build/media/licence, no production routes, scoped ownership/teardown plan|missing consent or isolation proof→no provisioning; no auto-cleanup|
|L3 read-only evidence|observer_b + independently observer_a|NEW scoped read-only approval; actual SID/token/ACL/native identity, trust transport/time/anchor provenance verified|missing/truncated/contradictory proof→stop/preserve, no repair|
|L4 negative tests|operator + both observers|NEW test-specific approval; reviewed fixtures/budgets/STOP; all12 real results independently correlated|any unexpected write/unknown/ABA/clock/replay→quarantine, no automatic retry|
|L5 limited canary|operator + independent safety owner|separate new approval, all blocking risks resolved, exact candidate/limits/rollback signed; no automatic trading enablement|any unresolved trust/ownership/durability risk→NO-GO; retain stopped state|

## 9. Stop, recovery, removal and evidence retention

This PR contains no stop/provision/delete scripts. Future STOP means stop issuing
new permissions/claims, fail closed at consumer boundary, mark session uncertain
in external ledger, notify named humans and preserve all evidence. Revoking future
work does not prove an existing process stopped. Power/service/network changes
need explicit emergency authority defined before any test; no automatic host kill,
reboot, firewall repair or task deletion. If physically unsafe, follow approved
human emergency procedure, not this document as an execution command.

Recovery: preserve prepared/committed intent, WAL and immutable evidence; consult
fresh external anchors and both observers; never restore time/counters/keys just
to match a snapshot. Unknown durable outcome blocks. Existing Grid release guard,
mutex and atomic pointer journal semantics must remain intact; do not invoke their
scripts here (rollback may query DB even without Apply). No migration downgrade
or fencing regression. No real recovery/rollback was tested in this planning PR.

Removal: no automatic delete, no inferred ownership from path/task/service name,
no production cleanup. Separately approved ownership inventory must cover VM,
virtual disk, every volume/file, task/service, network, key and external ledger
retention. Preserve witness revocations/high-water even after guest destruction.
Unknown/foreign/missing ownership→do nothing and quarantine. Retention30days/10runs
is only an example review budget, not an expiry-triggered deletion policy. Audit
archive requires independent append-only enforcement, access control and verified
restore procedure; currently UNPROVISIONED/UNVERIFIED.

## 10. What humans must prepare before a first lab test

1. Name independent operator, two observer custodians and emergency owner; document
   separation from host admin and verify real signing roots out of band.
2. Select disposable nonproduction hardware, licensed verified Windows/Hyper-V
   versions, image hashes and capacity budgets; do not reuse LS5/LS7 or installed Grid.
3. Review physical network diagram and ALL host/guest routing/sharing paths; allocate
   a collision-free isolated address plan without production/Tailscale connectivity.
4. Supply a separately reviewed trust/time/witness transport and two external durable
   witnesses with reset/backup/key-rotation controls; resolve the current transport
   and two-second freshness blocker. Do not substitute same-host snapshots.
5. Allocate only independently owned disposable guest storage and per-run/node IDs;
   review the new PGDATA intent proposal without changing old schemas or enabling2.
6. Prepare L3 collector source/provenance and raw token/ACL/handle evidence formats,
   quotas, test fixtures and external immutable evidence archive. No live test-key roots.
7. Review each of12 cases, cross-cutting fault schedules, expected denies, emergency
   STOP, recovery, preservation/teardown inventory and retention responsibilities.
8. Freeze candidate/source/image/manifest hashes and independently validate offline
   receipts; sign a NEW narrowly scoped L2 plan. Later L3/L4 each require their own
   explicit permission. This checklist does not grant it.
