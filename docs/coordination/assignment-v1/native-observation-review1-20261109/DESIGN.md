# Native target OBSERVATION v1 — admission-only proposal

2026-11-09. DATA/DOCS/PURE-HARNESS ONLY. DESIGN_PENDING / NO_GO.
No actual Consul, broker, target, worker, scheduler, public route or publication call. No Root/shared runtime/schema edit. Current positive Assignment APIs are still CLOSED. Mapping direction ACKs do not approve this new schema.

## Choice and exact predecessor

Prefer a CLOSED admission-only wrapper over existing lab-observation review2, not a new universal lifecycle/status enum and not a direct-target success alias. Alternative future storage/publication/projection variants would require actual owner codecs and proofs; they are deliberately excluded from v1. Root/A5 prefer this narrower first contract.

PROPOSED-native-observation.schema.json defines unified.gateway.native-target-observation.v1-review1, the exact result-schema name already PROPOSED in mapping26e native20. No native result schema was approved by that mapping. Existing direct result unified.gateway.direct-target-result.v1 remains separate, unchanged and unaccepted by this schema. No direct-v1/local Journal/stand-context upgrade.

Pinned predecessor originals/observation.schema.json SHA736acca970bd392f46530cda94acd97701e879b18889c429a2c2113e04810e4c stays unchanged. Its nine closed native observation alternatives and original $defs are embedded with local refs correctly resolving in the new wrapper. Current/UNKNOWN policy variants remain distinct. Original phase-receipt schema is retained for provenance; the wrapper exports receipt observations, not decoded receipt bodies or opaque proof objects.

## Closed top-level fields

| Field | Meaning / source requirement |
|---|---|
|schema|NEW native-observation profile, not a direct result or approval.|
|classification|Fixed OBSERVATION_DATA_ONLY_NOT_AUTHORITY. A tag cannot qualify its own source.|
|disclosure|Fixed CURRENT_READ_AUTHORIZATION_REQUIRED_NOT_PROVEN_BY_JSON. Actual same-owner current READ rights must be checked before exposing any history/error.|
|requested_operation|Fixed READ_RESEARCH view of the retained original job. Not submit/cancel command acknowledgment or a scope grant.|
|original_binding|Exact retained original/namespace/actor/quota/job/H/S/D and strict base64 native20 bytes; DATA correlation only.|
|snapshot_status|CONSISTENT_NATIVE_SNAPSHOT / LAST_KNOWN_REFRESH_UNKNOWN / UNRESOLVED. Distinguishes actual current native snapshot from retained durable history.|
|refresh_reason|Closed NONE/NO_QUORUM/TRANSPORT_UNKNOWN/INCOMPLETE_RECORDS/CLOCK_UNCERTAIN/BINDING_CORRUPTION/SOURCE_UNAVAILABLE. Never a NOT_FOUND or retry authorization.|
|native_observation|Existing closed lab review2 native facts, including its independent policy_qualification and operation_observation, immutable admission versus phase/computed observations.|
|computation|NO_COMPUTATION_EVIDENCE or METADATA_COMMITTED_PAYLOAD_NOT_INCLUDED, derived from native_observation.computed. Payload null; retrieval NOT_ESTABLISHED; scientific payload not revalidated by this envelope.|
|publication|Fixed status NOT_AUTHORIZED, receipt null, location null. No COMMITTED branch.|
|projection|Fixed status NOT_AVAILABLE, receipt null. No DURABLE/PENDING/COMPLETED extension.|
|result_completion|Fixed NOT_ESTABLISHED. No COMPLETED or DIRECT_TARGET_PASS branch.|
|commit_time_status|Fixed UNKNOWN_COMMIT_INSTANT. No inferred UTC-at-Raft-commit claim.|
|permissions|dispatch/publish/retry/release_hold all false. Serialized JSON never authorizes an effect. Actual dispatch permits are nonserializable same-owner objects from a separately qualified issuer.|

## Original binding and canonical joins

original_binding is CLOSED with cluster_id, cluster_generation, realm_id, request_id, idempotency_key, planned_job_id, actor_principal_id, quota_owner_id, target_request_sha256 H, target_request_schema_sha256, target_request_canonical_base64, commissioned_profile_sha256 S and lab_submit_sha256 D. The actual producer derives them from trusted retained original target/profile/lab bytes, not caller-selected paths or echoed values. Compare against the consumer's same retained original; arbitrary JSON/hash equality is not origin authentication.

T/H/P/S/lab13/D are exactly the mapping26e DAG: strict canonical target20 raw bytes T and H; immutable commissioned profile P with lossless T binding and hash S; original native13 with S and digest D. The observation adds no mutation or issuer. Job is planned_job_id while native state is UNKNOWN, not a fabricated admitted job. job_id != experiment_id; actor != quota owner; Meta target_version != Strattester producer_head; H != A7 c548 input SHA != local33d5 dataset identity != S != D. Native generation/realm and actual actor/policy/quota joins remain separately mandatory.

Require strict base64 decode/reencode equality, exact T raw SHA, pinned native20 schema, exact raw type/canonical checks and full original identities. At data-correlation level, embedded original_submit_request_id equals binding.request_id, embedded original_submit_intent_sha256 equals D, and embedded job_id equals planned_job_id. Missing/mismatching data refuses; never normalize a dotted idempotency key into lab's different grammar.

The copied native20/P/lab samples are uncommissioned design DATA only. No process/actor/cert or job is issued by their existence. Old immutable mapping26e remains unchanged.

## Native facts, policy and refresh — separate axes

| Native evidence | Snapshot / policy | Required observation |
|---|---|---|
|Actual admission receipt/job snapshot resolved|CONSISTENT_NATIVE_SNAPSHOT, policy CURRENT|ADMITTED, admission receipt plus matching ADMISSION phase; operation CONFIRMED refers to qualified native observation, not child execution or current permission.|
|Same known admission but requested operation policy uncertain|Consistent native snapshot, policy UNKNOWN|Keep ADMITTED and receipts; operation UNKNOWN. Do not erase a known commit.|
|Known RUNNING dispatch commit|Current or retained snapshot|RUNNING is a native phase, NOT proof an OS child started/alive/completed or that a permit was delivered. No new permit on replay.|
|Known COMPUTED metadata receipt|Current or retained snapshot, even policy UNKNOWN|Keep COMPUTED metadata/receipt/hash/byte count; computation METADATA_COMMITTED_PAYLOAD_NOT_INCLUDED. No payload retrieval, publication or completion claim.|
|Known cancellation request|Current or retained snapshot|CANCEL_REQUESTED is not CANCELLED/child-exit/refund. A prior computed observation may remain retained independently.|
|A prior complete snapshot remains but refresh fails|LAST_KNOWN_REFRESH_UNKNOWN|Keep last known native phase/sequence/receipts, force policy UNKNOWN and operation UNKNOWN; non-NONE refresh reason. Do not claim these are latest cluster state.|
|No complete original native outcome resolved|UNRESOLVED|Existing UNKNOWN branch; planned job identity retained, assignment/attempt/admission/current/computed null; policy and operation UNKNOWN. No absence or re-execution inference.|

The predecessor field native_observation.current means the phase WITHIN the represented snapshot. For LAST_KNOWN_REFRESH_UNKNOWN it is explicitly historical, not the currently latest cluster phase. Rendering must show the snapshot status with that phase and preserve UNKNOWN; hiding refresh uncertainty would misrepresent history as current. The actual observer must preserve the last COMPLETE verified snapshot if a later read is incomplete, rather than fabricate a hybrid of different reads or discard previously known admission.

A CONSISTENT_NATIVE_SNAPSHOT requires an actual same-authority consistent native record set/transaction, complete original/profile/Assignment/job/receipt joins and verified raw row indices. Individual sequential reads are not automatically one snapshot. LAST_KNOWN history must have prior verified native provenance and retained original receipt data; a local Journal does not establish that provenance. JSON schema cannot establish source provenance. No proof is created by constructing a dataclass, constructor, scope string or receipt-shaped object.

The first profile is READ_RESEARCH only. It may describe committed admission/cancel history, but is not acknowledgment of a current submit/cancel command. A separately correlated command outcome must bind its own request UUID/intent digest/common binding; especially a cancel has a different original command. No such command-outcome wire is invented here. Root may include an authorized observation view after a command only under its separately reviewed command response contract; operation_observation CONFIRMED never proves that current command succeeded.

policy_qualification is qualification for this READ view as observed, distinct from fresh actual READ authority required for disclosure. A CURRENT output label does not establish current read rights or strict UTC-at-commit. When current disclosure rights are absent, keep internal native facts but withhold this envelope; Root's separately reviewed error/disclosure contract applies. Do not leak known history merely because it once committed. Capture remains read evidence, not execution permission. No await under impersonation or permission callback is introduced.

## Receipt, phase and computation semantics

Every receipt reference contains receipt_id, ACTUAL positive native ModifyIndex as a bounded decimal string, and bytes_sha256 of EXACT immutable KV Value bytes AFTER base64 decode, not reconstructed JSON, wrapper, its own hash or a leader token. Native ModifyIndex is not Raft term, domain job sequence, Assignment revision or worker fence. Admission and current phase remain separate observations. ADMITTED current.phase_receipt must equal admission; COMPUTED current.phase_receipt must equal computed.receipt. CANCEL_REQUESTED may retain a distinct prior computed receipt. These data equality checks supplement, never replace, actual receipt-body/source checks.

Before constructing any native view, actual owner must resolve all immutable command/common bindings, original T/H/P/S/lab13/D, admission and current phase bodies, assignment/attempt/job IDs, phase kind/sequence, exact source request/digest, actor/quota/generation/realm and actual raw record indices/session at the same selected snapshot. Receipt observations alone cannot prove these omitted raw joins. Incomplete/corrupt/inconsistent sets are unresolved or retained-history UNKNOWN, not guessed ADMITTED or NOT_FOUND.

The first fixed Meta profile's metadata is artifact SHAf4997d7d26211676cd8664e53d7999f8b71f203510f3b9a275b439c403e03940 /2070 bytes and descriptor SHA664d34f06721b3d62404ea2f05b6b929a59b9e3eeecc281a71d2ca927c802cda. These may be correlated to a native computed receipt only after actual source validation. Matching golden digests is not payload possession, replicas or publication. This envelope includes no artifact bytes, A7 descriptor payload or download URL, and performs no statistical/scientific revalidation. A6 must not draw computed levels/signals from metadata-only observation.

A7 scientific scopes, synthetic whole-window semantics, clocks/units, unavailable finance, source-authenticity UNKNOWN/NOT_EVALUATED and false trading/training/inner execution flags are never changed by native job admission. If actual payload retrieval is later approved, it requires its own exact codec/descriptor/input/units/digest/current-read contract, not filling computation.payload in this v1. The local dataset label/revision remains LOCAL, not A4 manifest/replica evidence.

## Publication, projection, result completion

They are separate CLOSED axes with only conservative values in v1. The proposed schema does not contain positive publication/closure/projection proof-shaped alternatives. COMPUTED and native history can be known while all three remain unavailable. A future new exact schema/profile needs A2 sole native publication order and immutable receipt codec, A4 actual eligible two-domain protected closure/retention, A7 durable idempotent projection identity/receipt, Root/A5 original/completion bindings and A6 consumer/read rights ACK. No COMPLETE/publication label may be added to v1 by ignoring unknown fields or inferring from golden artifact bytes.

This intentionally cannot represent an actually published/completed result. Such a future response must use a separately reviewed version; v1 refuses it rather than silently stripping known positive facts into NOT_AUTHORIZED. Root must not select this first admission-only profile for an operation whose authorized response requires a different codec. Existing mapping ACKs do not approve that future version or this one.

## Wire/preparse bounds and restart

Proposed wire is canonical compact sorted ASCII C3-style metadata <=16384 encoded bytes/depth12, no duplicate keys, JSON numeric literals, noncanonical encodings, NaN/Infinity, trailing LF, extra/missing fields or implicit defaults. Native indices/sequences are bounded u63 decimal STRINGS. T remains its separate target codec inside canonical base64, preserving original numeric preflight limits and raw SHA; do not convert it into native strings. Base64's structural cap21848 is not permission to emit an overlarge envelope. Complete encoded observation must fit its bound; refuse without truncation, omission or hash-only replacement. Sample maximum4441 bytes is not workload/native transaction qualification.

Upon restart, reacquire actual identity/current read rights and resolve original same-authority records. Never reconstruct serialized opaque handles or adopt direct Journal state as native history. Preserve exact original UUID/key/job/T/H/P/S/lab13/D and holds. No new profile, UUID, key, target invocation, dispatch permit, debit, refund, GC or counter reset follows from UNKNOWN. Known history remains known when a new attempt or policy/refresh is uncertain, but current disclosure still requires actual current rights. Conservative debt/verified child exit/release remain separate unimplemented gates.

## Owner review gates / current status

Root owns native20/result/wire/disclosure selection and future adapter, A2 native observation producer/issuer and same-authority transaction/receipt/source checks, A5 job/Assignment/attempt/resource/lease semantics, A4 provenance/storage/publication boundaries, A7 actual scientific/source/result identity and projection, A6 schema-driven renderer that clears stale views on unsupported/invalid/UNKNOWN data. All must review exact candidate schema/hash and required semantic joins. No caller JSON/profile, read capture or arbitrary method-shaped provider can qualify these roles.

Native issuer/positive API, broker profile-v2 parser/commissioner, strict UTC-at-Raft-commit, qualified worker quota/headroom/containment, same target CAS, full transaction serialization, storage two-domain/projection, hosted CI, native-human/physical admission remain unqualified and independent. An observed native commit is not a permission, completion or GO. Public submit remains DENY; scheduler BLOCKED. No physical/service/network-provider operations authorized here.

Published mapping ACK registry addendum is Grid7e01b9a0ff5c40780acc0a8ee1c970ad4e068eb7 at docs/coordination/assignment-v1/target-native-mapping-scoped-acks-20261109/ACK-REGISTRY.json. Original A4 04ec0d and A7 776218 receipts/text are retained unchanged. Their scopes cover mapping input/provenance/storage/UNKNOWN/byte-bound direction ONLY; native observation result schema was explicitly NOT RECEIVED/ACKed. Earlier A2-SCOPED-ACK-RECEIPT with A7=PENDING is retained historical evidence, not the current registry.

## Pure probe evidence

build_probe.py imports only stdlib/jsonschema, never Grid/broker/Root runtime. It embeds the pinned predecessor data schema and verifies14 synthetic structural positives,116 structural denials,186 data-correlation negative vectors and8 raw-codec negatives. No aggregate native/contract execution PASS is claimed. Invented receipt IDs/hashes are labelled SAMPLE-DATA-NOT-NATIVE; sample artifacts' known golden metadata do not make them real native receipts or issued rows. All sample canonical files are exact bytes with no LF. Schema validation and pure correlation controls are not current source/authorization/proof verification.

Zero Consul/broker/target/worker/scheduler calls, zero native profiles/Assignments/publications. New result schema and semantics are PROPOSED / REVIEW_PENDING only. No shared contract freeze or positive wiring is authorized.