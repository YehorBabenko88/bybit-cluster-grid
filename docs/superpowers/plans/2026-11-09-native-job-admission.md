# Native Job Admission / Research E2E Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first disposable native job on the existing Grid Consul authority, with durable original ownership, quota/Assignment/lease fencing, recovery and co-approved worker/storage seams.

**Architecture:** SINGLE-JOB PROFILE-V2 losslessly binds original target20 T/H through immutable P/S into unchanged lab13/D. The sole existing Consul authority commits all control changes atomically; opaque same-instance broker/worker/publication capabilities do not survive serialization/restart. Current unknown resource, worker, UTC or storage qualification denies the affected positive operation.

**Tech Stack:** Python 3.12.10, existing httpx/cryptography and pinned Consul 1.22.2; existing hash-locked test environment; Windows and Linux disposable loopback stands only.

**Spec:** Existing `docs/coordination/assignment-v1/target-native-mapping-review1-20261109/DESIGN.md`, review2/nativeSID-successor contract and observation895 proposal; NEW Root NativeJobAdmission/ResearchE2E directive 2026-11-09 selects direction B but does not approve unqualified runtime proofs or silently resolve UTC.

## Exact ownership and bases

- Grid base e3a71a19a58c5fbe59835c4062e1d25ded696285 / tree fb714b1c3f4e773840b40b425d02003388ed7cb3; runtime remains 40e9c8dc274a2746018bc1aa08d103cd0187cecc. Remote branch matched before creation.
- Own Grid branch `feature/agent2-native-job-admission-20261109`, separate worktree `work/native-job-admission-20261109`.
- ONLY `grid/authority_assignment_v1.py`, `tests/coordination/assignment_v1/**`, `docs/**`, and own workflow. No transport, storage engine, placement, UI or Root adapter/CI edits.
- Broker base 31e0351b9f21ac53f3eb47a23bf45d06a58e1fe1 / tree 787be69ece1b533dff284195bbedd34a0ae5196e; module1e9f4bb... is runtime651. Separate Unified branch `feature/agent2-research-profile-v2-20261109`, `work/research-profile-v2-20261109`.
- Unified owns existing `unified_system/gateway_research_identity.py`, its tests/docs and owned workflow. Read module840 stays unchanged.
- Managed worktree attempt returned neither path nor operationId and registered no worktree; stopped waiting and used previously authorized Git fallback after inventory. No old worktree removed/reset.

## Global constraints

- Consul/Raft is the ONLY consensus/authority. No second scheduler, ledger, election or caller-provided raw KV endpoint.
- Lab submit13 schema193 remains unchanged; direct v1 cannot upgrade. All actual issuer/original/native row identities must agree.
- Genuine Root commissioning may create policy/profile/enrollment/genesis; it may not seed issued Assignment/job/hold/receipt proof.
- Each complete actual transaction measured <=64 operations and <=32768 encoded bytes; metadata <=16384/depth12 C3, no omissions/splits to fit.
- Native Session IDs preserve strict canonical server UUID without forced version; client/job/realm/Assignment UUIDv4 stays strict.
- UNKNOWN retains original bytes/UUID/key/job/profile/holds; no automatic replay, rekey, refund, debt reset or reconstructed opaque permit.
- Public submit DENY, production/physical BLOCKED. Only owned loopback processes/temp roots. No diagnostic PR52 execution, office services/firewall/ESET/Tailscale/provider operations.
- Proposed APIs below are NOT actual until implemented/source-qualified; co-ACK exact records/broker/worker/publication ABI before shared freeze/wiring.

## Review focus

- Fully rebound T/H/P/S/D with wrong registry actor or numeric 3.0/bool aliases must deny, not pass hash/schema equality.
- Concurrent original UUID/key collisions, timed-out committed writes and restart must never create a second job or debit.
- Stale policy/principal/worker session, no quorum and old leader must fail SAME native mutation checks, not just preflight heartbeat.
- Native RUNNING commit followed by crash/permit delivery loss cannot mint another OS start; cancel request is not verified child exit.
- Known history survives policy/refresh uncertainty; disclosure needs current actual read authority and complete same-snapshot native provenance.

## Task 1 — Broker profile-v2 actual principal source (independent executable slice)

**Files:** Unified owned broker; `tests/gateway_research_identity/test_native_profile_v2.py`; `docs/intelligence/research-identity/native-profile-v2-20261109/**`; own workflow.

**Interfaces:** Existing constructor/open_session/capture_current/fixed require_capture. New profile-v2 accepted only with exact target20/base64/H/P13 semantic joins; no job/worker grant. READ accepts exact original lab13, CANCEL scope requires exact cancel12/original submit digest, not arbitrary bytes.

- [x] Verify bases/ownership and existing three boundary-unit baseline PASS; no claim baseline native15 rerun at31.
- [ ] Commit first failing real-voter test/fixture + plan while broker source still1e9; record exact RED HEAD/test/module hashes and original log.
- [ ] Run valid actual mTLS/Root-commissioned profile2 against old broker; expect denial (missing P2 support), no issued job rows.
- [ ] Implement bounded canonical target20/profile2 validation, strict actual actor/quota/gen/realm/profile/request/job/idem/input/source/resource joins; preserve v1 behavior.
- [ ] Actual native tests: valid session/capture, foreign/unbound lab bytes, direct-profile promotion, fully rebound numeric/actor mismatch, cancel original binding, revocation/session loss/no quorum, UTC/mono expiry and cleanup.
- [ ] Independent source review; fresh primary OID/raw pre/post qualified exact IDs/zero skip; Windows/Linux workflow uses valid step-level runner context. Commit/source pin and report source scope.

## Task 2 — Real native job/original/resource issuer

**Files:** `grid/authority_assignment_v1.py`; owned assignment tests/docs/workflow.

**Proposed interfaces (co-ACK required):** `ResearchLabAuthority(authority,generation,*,broker,worker_inventory=None)`; async `submit(original_lab13_bytes,*,context,leader,worker_capture)` and `lookup(original_lab13_bytes,*,context)`.

- [ ] Agree closed current worker enrollment/policy/observation/session/capacity ledger record keys and A5 fixed sealed capture/class API. No source boolean/callback/raw ops.
- [ ] RED real quorum: genuine commissioning/current principal and worker source, no seeded issued records; default unknown worker/UTC/source must deny before mutation.
- [ ] Derive all keys/predecessors/server IDs. Single native transaction checks leader/gen+ALL broker/worker/profile/quota/current rows/absence/common identity and writes immutable original/common bindings, next counters/ledgers, hold, Assignment, actual worker-session lease LOCK, job+receipt.
- [ ] Positive only when actual qualified worker and explicitly accepted expiry requirement are available; do not substitute fake native evidence just to pass.
- [ ] Real duplicate same original => same observed native job/receipt/no second debit. Same UUID/key with altered bytes => conflict. 409 only rolls back this attempt; ambiguous send => UNKNOWN with no new identity.
- [ ] Full per-send native serialization and parser/error normalization; independent review/commit pin.

## Task 3 — Consistent lookup/restart and admission-only observations

- [ ] RED actual consistent original/common/profile/Assignment/job/phase snapshot reads, corruption/incomplete history/no quorum and fresh READ rights.
- [ ] Produce closed observation895 with exact original20/H/S/D correlations and raw receipt hashes/external ModifyIndices. Last complete known history + policy/refresh UNKNOWN remains visible only under separately current authorized disclosure.
- [ ] Native all-node restart/recovery preserves durable originals/counters/holds; opaque handles are reacquired through actual sources, never deserialized. No automatic RUNNING resume/regrant.
- [ ] Original result schema remains admission-only: no payload/chart/publication/projection/COMPLETED.

## Task 4 — Native cancel / one-use dispatch / metadata

**Proposed interfaces:** async `cancel(original_cancel12_bytes,*,context,leader)`; `begin_dispatch(original_lab13_bytes,*,context,leader,owned_attempt)`; fixed async `require_dispatch(expected_instance,permit,*,owned_attempt)`; `record_computed(original_lab13_bytes,*,context,leader,owned_attempt,output_capture)`.

- [ ] Co-ACK actual A5 inventory/owned-attempt/output-capture fixed classes and retained Windows process/thread/job handles/source/incarnation. No method-shaped success.
- [ ] RED real ADMITTED→RUNNING and cancel CAS race; cancel has its own global command identity, source UUID/digest separate from original submit.
- [ ] Mint dispatch permit only after FIRST live confirmed ordered native RUNNING mutation and current actual qualified sources. Consume once bound same instance/attempt before actual Resume. Replay RUNNING/unknown delivery yields observation only.
- [ ] Actual stale leader/worker/session rejection/no quorum/epoch update; child quiescence is separate from cancel request. Holds remain until separately approved verified exit/release.
- [ ] Metadata accepts actual owned output source and current original/fence/job CAS; digest claims alone do not establish computation/publication.

## Task 5 — A4/A7 publication/receipt/projection seam

**Proposed only:** `commit_storage(original_publication_bytes,*,context,leader,closure_capture)`, `reconcile_storage(original_publication_bytes,*,context)`; later fixed sealed `capture_committed_publication`/`require_committed_publication` bound to actual A7 store/current read source.

- [ ] Exact A4 closure record inventory/schema/key/byte retention/domain eligibility/hold/pin/protection/accounting and source-class co-ACK. A4 returns bounded readonly captured facts, never raw native operations.
- [ ] Implement bounded same-authority snapshot reader derived by A2 from approved identifiers/families. No arbitrary paths/caller-selected index or unchecked aggregate root.
- [ ] Native publication checks/writes ALL current Assignment/job/cancel/worker/replica/incarnation/domain/reservation/protection/debit/original/receipt/outbox dependencies in ONE measured transaction.
- [ ] Actual two independent domains currently NONE: positive publication stays closed; same-host directories are not independent domains. Negative/UNKNOWN/interruption tests can proceed.
- [ ] A7 existing ResultStore projection only after actual A2 COMMITTED opaque capability/immutable raw receipt+actual index+A4 closure. Durable idempotent replay SAME receipt, never second native commit/rekey. Fresh authorized historical receipt lookup does not require old worker lease current.

## Task 6 — Fault matrix/source/CI and Draft PRs

- [ ] Own real three-voter tests: 1/2 and2/1 partitions, stale leader/worker, coordinator crash/restart/all restart, original commit response loss, duplicate/cancel/dispatch races. Kill/wait only owned Popen handles; retain original native/election/log/cleanup evidence.
- [ ] Review exact final source, raw pre/post primary OIDs and mandatory unique IDs/no skip in fresh no-hardlink sources. New exact Windows/Linux workflow pins actual Grid+broker/A5/A4/A7 source/dependencies/binary; valid runner context at step level. Hosted queue is not PASS.
- [ ] Draft PRs/exact HEAD/tree, semantic/failure matrix and P0/P1/P2 report; no merge/deployment/physical acceptance claim.

## UTC-at-commit provenance / fail-closed policy

Original Agent2 human task explicitly requires majority, leases, fencing and stale rejection; the text available in this chat does NOT state certificate-wallclock-at-Raft-commit. Existing A2 research review2 section “Expiry decision from Root” records Root qualification gate: native principal invalidation/policyCAS target-authoritative, strict UTC-at-commit remains P0. Mapping/observation designs and scoped owner ACKs repeat that design gate and explicitly do NOT approve replacing a strict operator requirement with bounded native invalidation semantics.

Exact prior original human OWNER requirement outside this available source is NOT established by repetition in a design. Root must identify that source or explicitly choose the bounded disposable requirement before affected positive job mutations are enabled. This audit neither invents a human requirement nor silently relaxes an existing one.

Current Consul transaction API checks native indices/sessions; it has no certificate UTC wall-clock comparison at the actual Raft commit instant. Local preflight/postflight or TTL grace cannot prove that property. Epoch/session/policy fencing establishes native committed revocation ordering, not strict external clock simultaneity.

Fail-closed: strict/unknown requirement => no affected positive native job/publication send and no dispatch/release permit. A possibly sent/late operation retains known native history and original holds, marks policy/operation UNKNOWN and never emits a current effect permit; do not erase or “roll back” an actual commit by assertion. Broker's genuine principal session tests do not close this job mutation gate. Any explicit experimental bounded mode must be Root/operator-owned, separately co-ACKed and documented, never a caller JSON grant/boolean.
