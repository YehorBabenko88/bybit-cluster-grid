# Assignment/native producer candidate review1 — no positive wiring ACK

Frozen base be6335a2e8cfac9483213a6a215bc29e32808b0c. NEW allocated module authority_assignment_v1.py and own tests/docs only. Existing Root identity-record.v1, six Mux operations, lifecycle receipts and be633 helper bytes unchanged. There is currently NO supported positive assignment/publication endpoint or native issuer; public execute/reconcile remain unavailable until exact co-approved binding. Private actual Consul primitives are implementation progress, not issued grant/native proof.

## Candidate async consumer ABI
`AssignmentAuthority(existing_Grid_ConsulSessionAuthority,generation_uuid,native_provider=actual_Root_provider_or_None)`:
- `await execute(original_request_bytes, *, context, leader)`
- `await reconcile(original_request_bytes, *, context)`
- `await verify_outcome(original_request_bytes, observed_outcome, *, context)` (not yet implemented)
- `await require_dispatch(original_request_bytes, observed_outcome, *, context)` (not yet implemented)
- `await commit_storage(original_intent_bytes, *, context, leader)` and `await reconcile_storage(original_intent_bytes, *, context)` (not yet implemented)

context is actual Root-owned in-process native request/caller capability; never JSON, readiness, caller-selected paths/indices/ops, proof bytes, bool or None-as-proof. leader is a real existing Grid ConsulLease owned by SAME Grid instance and currently validated, no reconstructed observed token. No acquire/election/worker spawn is performed by an HTTP command. These are PROPOSALS needing exact A4/A5/Root ACK, not current supported grant/publication ports.

## New native actor/delegation schema and issuer
New closed runtime-actor-policy-review1.schema.json is a data proposal. State ACTIVE is necessary but insufficient; native Root source/provider verification mandatory. Existing four Root identity records remain unchanged. New policy key N/runtime-v1/security/policies/<runtime-policyUUID>. New policy explicitly binds cluster, native principal/session/enrollment/actor-node and existing identity_policy_id, namespace, revision, stable partition dataset/source/partition, sorted unique allowed job IDs and sorted unique operation inventory. No wildcards, hostname/UUID aliases, caller paths, timestamps or JSON-number revisions. Revision positive u63 and canonical encoding/namespace equality are runtime semantic requirements in addition to structural schema.

Proposed closed operations: ASSIGN, DISPATCH, PUBLISH, READ_ASSIGNMENT, READ_PUBLICATION, RENEW_BEGIN, RENEW_FINALIZE, REVOKE, VERIFY_ASSIGNMENT. They do NOT extend existing Mux GET_COMMAND policy. Policy stable partition/job rights permit authorized historical original-generation reads; current generation is separately checked on new effects. No history receipt grants current dispatch. Scope values retain full six-field provenance; actual partition KEY remains frozen be633 C3 preimage excluding job/generation.

Root actual provider proposal (NEW internal ABI, no implementation/admission claimed):
- `async require_current(context, operation, immutable_full_scope) -> RuntimeActor(identity_binding, runtime_policy_id, native_handle)` from actual native source/current actor/session, exact typed IDs. Dataclass construction is not identity.
- `async verify_records(context, actor, operation, immutable_full_scope, identity_records, runtime_policy_record) -> None` only after actual current native SID/LUID/source/session/expiry/RBAC/delegation comparisons; raise on denial/uncertainty, every non-None result rejected. Neither method shape nor None return qualifies an implementation. No await under live impersonation; Root owns actual IPC/key/process/handle lifecycle and bounded native calls.

Only the SAME Root native issuer/commissioner may write/revoke this runtime policy; A2 effect endpoint never self-issues policies or accepts client records. Creation/write authorization must be actual qualified Root authority, scoped existing Consul ACL/mTLS and native commissioning; currently absent. Policy revocation changes its actual native ModifyIndex and must be checked in SAME transaction with four fixed identity indices, current leader/session/generation, immutable operation/original-command preimage and effect indices. Never reuse lifecycle capability or GET/OPEN as ASSIGN/PUBLISH. Actual native expiry/logoff vs commit ordering remains Root qualification; record fencing alone cannot infer an instantaneous external event.

## New storage key candidates — no frozen-helper reinterpretation
N = existing unified/<canonical clusterUUID>, prefix N/runtime-v1/. Keys are backend-derived only.
- global storage-reservations/<reservationUUID>/issuance immutable; same UUID/lifecycle current mutable.
- storage-budget-bases/<basisUUID>/<issuance_budget_revision> immutable; basis digest and revision independently checked.
- storage/<storage_nodeUUID>/<volumeUUID>/<storage_instanceUUID>/policies/<policyUUID>/<policy_revision> immutable.
- same triple/policy-current actual current selector; same triple/accounting current ledger.
- physical allocation/attribution keys PENDING A4 exact object identity/dedup/attribution schema; no fabricated compressed root/child-proof shortcut.

All UUIDs/revisions canonical and explicit (no default revision1). A5 storage_budget_revision maps exact A4 immutable issuance_budget_revision only; policy/accounting/lifecycle/nativeIndex remain distinct. A4 storage node means storage participant, compound fence node_id means EXECUTION worker; do not assert equality for remote storage without explicit typed mapping. Native execution_attempt_id is checked separately because compound10 lacks it. Old allocated/uncertain debt survives supersession/revoke/rejoin. Complete closure/current-allocation/coverage/eligibility/hold/head/checkpoint/outbox/receipt checks/debits belong in ONE actual native transaction; exact <=64ops/32768encoded bytes measured before send, no split/truncation.

## Actual substrate implemented vs missing producer
Private actual consistent native reads, leader/session/generation checks, bounded native transactions and new distinct key derivation are implemented. They provide no public arbitrary-KV API or execution grant. Four default-denial/layout unit contracts began with ModuleNotFoundError RED. Isolated actual Consul stale/generation/supersession/noquorum/restart tests bind raw untrusted probe records, not issued Assignment/security proof. A5 request/issued profile plus A4 review3 budget/closure + exact result/preimage/native-child/freshness and common-index integration still need joint ACK before positive execute/publication wiring. No native/Windows/provider/office effects, second consensus or policy weakening.

## Root review correction / exact successor
Review1 schema8f739947 is WITHDRAWN FOR SEMANTIC USE and its bytes preserved. Root structural probe accepted13terminalLF mutations due dollar anchor. Executable13LF RED reproduced; NEW runtime-actor-policy-review2.schema.json strict-end patterns plus exact positiveu63 bounds and canonical runtime fullmatch reject them. No prior runtime/native bypass is claimed. Root REVOKE permission means ASSIGNMENT revocation only, never policy issuance/revocation or permission changes. A2 endpoint does not write policy keys; Root actual commissioner/native issuer and explicit server-side Consul ACL write authority remain unimplemented/unqualified dependencies. Four Root identity records/OPS unchanged; async/native call ordering and actual external expiry semantics still need actual Root source qualification, not None-return metadata.
