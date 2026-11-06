# Event-ordered v3: isolated lifecycle adapter

ROOT selected NEW profile `unified.authority.event-ordered.v3` in Unified PR26
`f3bde56c889ebd5e15665a05e113213f511f2b2a`. Existing strict drafts, v1
checkpoint and existing Grid mutators/startup remain unchanged. This module is
not production admission, storage publication, a worker permit or an executor.

## Python contract and authority records

`EventAuthority(authority: ConsulSessionAuthority, generation: str,
principal_provider=None)` uses the existing authority instance/leader; it creates
no election/store/listener. Provider `require_current(context, action,
assignment_id)` must return current `actor_id`, integer `grant_revision` and
frozenset capability `authority.lifecycle`. Missing provider denies even receipt
lookup. Synthetic test providers are not real identity qualification.

Canonical owner-managed generation is READ from existing
`<namespace>/commands/generation`, not a second independent generation.
Additive records under `<namespace>/event-v3/` are:

* `principals/<actor>`: exact actor_id, decimal grant_revision, state ADMITTED,
  capabilities `[authority.lifecycle]`; checked index fences policy revocation.
* `workers/<worker>`: exact worker_id, incarnation UUID, state ADMITTED;
  registration index is a transaction predicate.
* `candidates/<actual-session-UUID>`: generation, assignment_id, actor_id,
  session_id. Created by current fenced authority after native session creation.
* `leases/<assignment-UUID>`: native Consul KV lock bound to actual lease session.
* `assignments/<assignment-UUID>`: generation, worker/incarnation, lease session,
  decimal internal revision, ACTIVE/RENEW_PENDING/REVOKED/COMPLETED and UNWIRED.
* `receipts/<SHA256(canonical([generation,actor,request_id]))>`: immutable full
  intent digest and historical result. Same request/different intent conflicts.

Runtime does not provision generation, principal or worker records. The isolated
harness provisions synthetic records only. Production provisioning/ACL ownership
and current provider are unqualified; no Boolean/caller dictionary mints them.

`await prepare_session(leader, context, assignment_id) -> actual_session_uuid`
creates an inert candidate with TTL60 in the real harness (configured existing
TTL elsewhere). It grants no effects. Native creation can be ambiguous; do not
auto-remint after lost response. On candidate-record failure a known UUID is
attached as `candidate_session_id` to CoordinationUnavailable; preserve it and
reconcile rather than destroy a possibly committed session. Unknown server-side
session IDs are orphan candidates with no assignment rights; TTL cleanup is not
accounting credit or effect containment. Dedicated lease session cannot equal
the leader session and candidate binding prevents cross-assignment reuse.

`await submit(leader, intent, context) -> receipt_or_outcome` accepts EXACT keys:
schema=`unified.authority.lifecycle.v3`, request_id, generation, actor_id,
assignment_id, worker_id, worker_incarnation, lease_session_id, action and
expected_revision. Counters are bounded canonical decimal strings; intent4096B,
stored record8192B, transaction<=32operations/16384encoded bytes. Experimental
local limits, not load-qualified common publication limits. GRANT requires
revision0 and unique assignment; RENEW/REVOKE/COMPLETE require current revision.
Terminal assignment IDs cannot be regranted. No supersession/replacement or
publication action is exposed in this first module.

## Renewal and UNKNOWN

GRANT atomically checks current leader session/index, generation, actor/worker,
candidate and absent assignment/lease/receipt, locks the lease and writes
assignment+receipt. RENEW first atomically changes ACTIVE revisionN to
RENEW_PENDING revisionN+1, binding exact request/digest. Only then calls native
session renew. Finally a separately fenced CAS activates revisionN+1 and writes
receipt. OLD revisionN is durably invalid before any native lifetime extension.
Unknown/failed intermediate state stays RENEW_PENDING, never ACTIVE. Exact same
intent resumes pending state after restart; another intent cannot adopt it.
REVOKE/COMPLETE may terminally close an ACTIVE or RENEW_PENDING current revision,
even if the native lease session already invalidated. Finalizer predicates then
reject. Session renewal by a stale finalizer can extend only an inert pending
session, not old grant authority. No downstream consumer is presently admitted.

Only successful consistent receipt reconciliation yields COMMITTED. Ambiguous
transport, invalid storage or unavailable quorum yields UNKNOWN; it is not a
NO_QUORUM oracle. Conflict may be REJECTED only after consistent receipt lookup
rules out this same committed intent at that linearizable observation. The
existing HTTP transport may retry a transaction that already applied, producing
409; adapter checks receipt rather than claiming rejection automatically.
UNKNOWN never generates another request/session identity or executes an effect.
Current provider authorization is required for historical reads; old leader
ownership is not required to observe an already committed receipt.

`authority_modify_index` is the actual receipt KV ModifyIndex encoded as decimal,
not Raft term, lease epoch, logical assignment revision or exact UTC. Receipts
have no fabricated committed_at; all effect_status values are UNWIRED. This
internal lifecycle `revision` is NOT automatically the common-wire
assignment_revision/lease_epoch/grant_revision tuple. Exact common wire and new
checkpoint schema mapping must be reviewed before a domain consumer is wired.

## Qualification

`tests/coordination/test_event_ordered_v3.py` uses an explicitly labelled HTTP
predicate MODEL, not Consul or crash durability. Dedicated CI runs offline tests
on Linux/Windows with raw exact-HEAD/tree verification, explicit case inventory
and no skips. Separate hosted ephemeral Linux harness starts three persistent
real Consul voters at the existing immutable image pin, tests durable receipts,
actual Raft leader kill, logical owner replacement, session invalidation,
two-voter loss and all-process restart. It uses synthetic identity, plaintext
owned internal network, and is NOT Windows physical HA/TLS/ACL/real provider or
Storage publication evidence. Missing Docker/hosted prerequisites fail; no skip
is treated as pass. Harness refuses local Windows/office use and inspects owned
container/volume/network IDs before operations/cleanup.

Current local results and exact commit are reported separately in Agent2 outputs;
this document does not preclaim hosted PASS. Production endpoints, external
writer/socket containment, closure/GC/accounting, checkpoint mapping and real
Windows quorum remain separate NO-GO gates.
