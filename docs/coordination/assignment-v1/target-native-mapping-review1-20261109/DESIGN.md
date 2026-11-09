# TargetAdapter20 → native lab13: lossless binding proposal

2026-11-09. DESIGN_PENDING / NOT AN ADMISSION OR WIRE-CONTRACT ACK.
ROOT authorizes pure contract work only. This packet makes zero Consul/broker/target/scheduler calls and changes no Root/shared runtime file. All SAMPLE files are uncommissioned DATA, never certificates, principals, native sessions, issued Assignments or permits.

## Pinned inputs and choice

Root Draft PR54 current cf7dad91bf0d3a24073c91e0d3e326e6d9e7d2db has the actual direct-target module SHA775976b3d344409d6c25ba96f2a475f5085695edf9947f482440c263355d6a8f and request schema SHA2a7a9370eedc43b76b03fa13252e86606162ae8f494a362fd69d5b22a85858fe. Runtime-tested a84 evidence is separate. Original request schema has EXACT20 fields including schema. Frozen lab submit has EXACT13 fields, SHA19357891fc022a87831009f17c663304ab72d88ed6ea344bb65c6bc325a321cc from PR47 3e498de973536c2d6393f83abe7d59cb1452a9b4. Native lease-format successor SHA9bdb1084004fcc6cfb76fa0f1bce0013b6a26a9b288cbb71c82db621feb4f4d0 does not add lost target identity fields to lab13.

Existing lab13 cannot directly express outer dataset/experiment/strategy/result identity or outer canonical SHA. Merely dropping these fields, calling parameters_digest the outer hash, rewriting idempotency, or asserting equality of role labels is rejected.

Two credible designs: (A) new native command envelope nesting all20/raw plus lab13, requiring a new command codec/common-binding profile; (B) actual Root-commissioned SINGLE-JOB profile v2 at the existing profile selector, binding full20/raw+outerSHA, with UNCHANGED lab13 referencing that profile's raw SHA. Recommend B for this ONE-job lab: the existing 13-field schema/intent can remain byte-for-byte unchanged in shape, while every outer byte participates in its profile selector and intent digest. Tradeoff: each original job requires explicit trusted commissioning; it is not a general dynamic submit solution. A remains an alternative if Root rejects per-job commissioning. Neither is currently implemented or approved.

## Separate input profile — never upgrade direct v1

PROPOSED-native-outer.schema.json describes a new Root-owned candidate schema unified.gateway.target-native-request.v1-review1 and execution_mode NATIVE_RESEARCH_ADMISSION_REQUEST_NOT_PERMISSION. This packet does NOT change Root's schema or permit Root to execute it. Exactly the same20 field names are retained, but native principal/quota/generation are assertions against actual commissioned identity; result schema is a NEW native observation profile, not direct success. Pre-issuance assignment_revision/fencing_token/result_artifact_ref remain null; actual issued values exist only in the later backend-issued grant/outcome, never rewritten into the immutable original request.

Current unified.gateway.target-request.v1 / DIRECT_DISPOSABLE_SYNTHETIC, LOCAL_TEST_ONLY quota/local principal, null native fields and stand-local opaque context MUST fail DIRECT_PROFILE_NOT_ADMISSIBLE. There is no automatic conversion function. An operator's later explicit native request is a separate profile/action/original identity; an earlier direct Journal receipt is not adopted as native intent, job history or authority. Historical direct correlation, if needed, requires a separately reviewed provenance field; none is silently added to these20 fields.

## Exact canonical/hash closure

T = EXACT original canonical ASCII target request bytes, 1..16384 bytes under Root's pinned JSON codec (numeric preflight limits are preserved as numeric bytes). Reject duplicate keys/noncanonical bytes/extra or missing fields, numeric bool/float aliases and unsupported profile before mapping. H = SHA256(T), lowercase64. A caller-supplied outer SHA must equal H, never replace recomputation.

The immutable profile P uses Grid canonical compact sorted ASCII C3 metadata. Store T losslessly as canonical base64 under P.target_binding.target_request_canonical_base64, plus H and the EXACT native outer schema-file SHA. Decode with strict base64 validation, reencode equality, exact byte cap, then parse T with its separately pinned target codec. The target's numbers are never converted to C3 strings or silently rounded. P is bounded <=16384 raw bytes; base64 expansion means some allowed-size target requests are unrepresentable and MUST fail before commissioning/send, never truncate.

S = SHA256(C3(P)), with NO terminal newline or self-hash in P. Existing selector L/profile-registry/S stores exact C3(P), where L=unified/<cluster>/runtime-v1/research-lab-v1/<realm>/. No second registry or consensus store. Profile v2 has one additional closed target_binding object; P includes no lab intent digest, target result or issued grant, so no self-reference cycle. Actual Root commissioner alone writes this immutable record with checked absence/default-deny ACL. Target/client/broker admission route cannot self-commission. Profile's principal registry and native policy remain the SAME authority source, not a second identity map.

Dependency DAG is T -> (base64(T),H) -> P -> S -> lab13 -> D. The20-field T contains NO profile selector S, job_id, lab13 digest D or actual issued grant; its authority_generation is a prior actual generation claim, and assignment_revision/fencing_token are null pre-issuance. P has no own S or D. Native principal/policy rows may reference S AFTER P is fixed; their hashes/indices are not inside P. Broker constructor selects S from trusted commissioning, outside immutable T. There is therefore no required fixed point. Do NOT add S or post-issued values back into T without a separately versioned design.

Bounded lifecycle: one P binds exactly ONE original request UUID/idempotency key/planned job UUID/actor/quota/generation/realm and exact T. Planned job_id is not experiment_id, nor a reservation or issued job. Commissioned expires_utc <= min(actual cert expiry, current policy expiry, commission time+900s). Native principal TTL10s with local9s safety bound, actual UTC AND monotonic deadline and post-await checks remain required. No automatic profile/session renewal, reuse, adoption or restart extension. These are proposed limits, not proof of strict UTC-at-native-commit.

Only actual Root's qualified commissioner ACL may create checked-absent immutable profiles and current identity policies. Broker/target ACL cannot create/update profiles; clients cannot choose or write S. Revocation changes current native policy/session ownership, with captured indices/session checked in the same mutation. Expired/revoked profiles cannot authorize fresh admission/dispatch; original profile bytes remain retained for historical verification. Never delete/reset a profile/counter/hold just because time elapsed, a local stand restarted, or a result was COMPUTED. Retention/GC is a separate A4/Root-approved lifecycle gate; until then retain. Original global request UUID/common actor+quota+idem bindings enforce the same single original intent; no new profile-key index, job registry or automatic retry service is introduced.

Lab13.commissioned_profile_sha256 = S. D = SHA256(GridC3(lab13)); D is the native original lab intent digest, NOT H. Existing global command/common idem bindings must check D and S together with actual stored original/profile/identity/job records. A change to ANY of the20 fields changes T→H→P→S→lab13→D. Hash algebra binds bytes; it does not authenticate, commission, issue a job or prove collision resistance by testing.

## All20 field mapping — no dropped values

Every row is retained verbatim in T/base64 and H/S/D closure. The additional semantic use below does not replace exact retention.

| Outer field | Native semantic mapping/check |
|---|---|
|schema|Must be NEW approved native schema, exact schema-file SHA in profile binding; direct v1 denied.|
|request_id|Copied unchanged to lab13.request_id and P.target_binding.request_id; same original global command identity.|
|target_kind|Preserved and compared to commissioned capability, currently MetaAnalyse only; no arbitrary entrypoint.|
|target_capability|Preserved exact meta.ohlcv.untouched_levels.v1; A7/target owner approves exact actual callable/source.|
|target_version|Preserved exact Meta source HEAD, separate from lab producer_head (Strattester HEAD); both required.|
|dataset_manifest_id|Preserved local-sha256 identifier with its LOCAL meaning; cannot label it A4 committed manifest. Need exact owner-approved input/dataset bridge before any broader admission.|
|dataset_revision|Preserved LOCAL_FIXTURE_1; not A4 revision or Meta dataset digest. No identifier aliasing.|
|experiment_id|Preserved exact fixture.gateway.btc.levels; compare actual bound A7 input experiment identity; no ledger/registry created.|
|strategy_version|Preserve null as null for this analysis; not missing, empty string or inferred strategy. Non-null strategy needs a different approved target/profile.|
|parameters_digest|Preserve current semantic: SHA of WHOLE original A7 request c548..., not params-only or outer SHA. Re-read actual original A7 bytes and verify. Map to lab13.input_request_sha256 only for this fixed profile; H remains distinct.|
|execution_mode|New native-admission-request claim, never execution permission; direct mode denied.|
|resource_budget|Preserve all4 numeric preflight caps and exact types. Compare with fixed target limits. NO conversion to CPU-millicores/RSS; lab13.resources comes from separately qualified server profile.|
|quota_owner|Exact equality with current actual broker quota and P binding, then lab13.quota_owner_id. A JSON quota label grants/reserves nothing.|
|principal_id|Exact equality with current actual broker actor, profile registry and P binding, then lab13.original_actor_principal_id. No local/READ principal upgrade.|
|authority_generation|Native UUID assertion equals captured actual generation, P binding and lab13.cluster_generation. A caller generation is not authority.|
|assignment_revision|Null at first issuance; any caller supplied revision denied. Actual counter/issued revision comes only from native CAS and subsequent opaque grant.|
|fencing_token|Null at first issuance; caller token denied. Leader token is not compound worker/resource fence; actual fence originates in issued Assignment/lease.|
|idempotency_key|Copy exact bytes to lab13 and profile binding ONLY if BOTH codecs accept. Root permits dot; frozen lab pattern excludes dot. Dot example MUST fail MAPPING_NOT_REPRESENTABLE, not hash/escape/normalize/rekey it.|
|result_schema|Preserved NEW native observation profile, independently Root/A4/A5/A6/A7 ACKed. Direct result envelope is not native status/publication/COMPLETED.|
|result_artifact_ref|Null at submission; caller result handle cannot establish computed artifact/publication. Future actual result bytes/receipt/closure are independently checked and observed.|

## Exact13 mapping

| lab13 field | Source |
|---|---|
|schema|UNCHANGED unified.gateway.lab-job-submit.v1-review1; schema-file SHA19357891... remains pinned.|
|operation|Fixed SUBMIT_RESEARCH, server-selected operation plus actual current broker scope.|
|cluster_id|Actual same authority namespace/profile, server-derived; no field from20 can override it.|
|cluster_generation|Actual captured generation equals new outer assertion and P binding.|
|request_id|Exact original T.request_id.|
|job_id|Server-selected planned job UUID in Root-commissioned single-job binding, not caller grant or seeded issued job. Persist/recover the same plan; never generate a new job on uncertain retry.|
|original_actor_principal_id|Actual current broker actor == T.principal_id == P registry/binding.|
|quota_owner_id|Actual current broker quota == T.quota_owner == P binding; common idem key remains frozen.|
|idempotency_key|Exact T key accepted by both grammars.|
|commissioned_profile_sha256|S computed from exact immutable P; actual selector/raw/index verified.|
|input_request_sha256|Original fixed A7 input SHA c548e2ffcd542d5d741682303694b3c6d06507740f158a6e30089b2d5355f648, not H or normalized JSON.|
|producer_head|Actual approved Strattester aed8a7c8a952f96803c207d5e90b133969a47f04, not Meta target_version.|
|resources|Actual qualified server native demands, currently frozen trial1000/268435456/1048576 strings; schema shape is not resource qualification. No conversion from4 preflight caps.|

Actual current namespace/realm/actor/service/quota/policy/generation/profile/request/idem/job/input/source joins must all agree. Native worker/attempt/lease/hold and phase joins are additional backend checks, not fields erased by mapping. All current captured indices/session and existing leader/gen/resource/worker/job/original bindings must be checked in the SAME actual target transaction. Read capture, H/S/D, matching JSON, stand scope, constructor/provider method presence or None returns cannot replace those checks or an actual one-use permit.

## Closed errors (proposal, not shared wire enums)

PROPOSED-admission-error.schema.json has exact fields schema/code/request_id/target_request_sha256/lab_submit_sha256/this_attempt/native_original_state/execution_permitted/retry_permitted/hold_release_permitted. IDs/hashes may be null if not validly established. No raw request/paths/secrets or arbitrary error strings. Public serialization still requires current read rights; internal known native history is not automatically disclosed after auth failure.

Closed codes: DIRECT_PROFILE_NOT_ADMISSIBLE; PROFILE_NOT_COMMISSIONED; MAPPING_NOT_REPRESENTABLE; TARGET_BINDING_MISMATCH; IDENTITY_SCOPE_DENIED; INPUT_BINDING_NOT_ADMITTED; RESOURCE_QUOTA_NOT_QUALIFIED; WORKER_LEASE_FENCE_NOT_QUALIFIED; UTC_AT_COMMIT_NOT_QUALIFIED; PUBLICATION_NOT_QUALIFIED; IDEMPOTENCY_CONFLICT; CONSENSUS_UNAVAILABLE; NATIVE_OUTCOME_UNKNOWN.

this_attempt is NOT_ATTEMPTED_THIS_CALL / THIS_ATTEMPT_ROLLED_BACK / UNCERTAIN. First concerns ONLY this invocation, not original absence. Parsed native409 only rolls back this attempt, not a prior original. Any potentially sent timeout/cancellation/malformed response is UNCERTAIN; preserve original/profile/holds, no new ID/debit/refund. native_original_state separately preserves actual known ADMITTED/RUNNING/COMPUTED/CANCEL_REQUESTED or UNKNOWN; never turn known commit into absence because expiry/projection/transport is unknown. All three permission booleans are false. These errors cannot authorize auto retry, hold release, dispatch or publication.

## Restart UNKNOWN — no second journal/ledger

1. Direct stand STARTED/FINISHED/UNKNOWN is LOCAL_ONLY. Never convert it into native job state or resubmit automatically.
2. Restore exact T,H,P,S,lab13,D and original UUID/idem/job from original authority records after fresh actual identity/current read authorization. Root may retain original plan bytes in its EXISTING custody mechanism; that is not distributed evidence. Never reconstruct serializable opaque permits/captures or infer native existence from local Journal.
3. Consistent native lookup must resolve actual original common bindings/intent/receipt/Assignment/job/phase; old frozen worker lease need not be current for authorized historical observation, but current READ authority remains mandatory. A future historical-read profile/API is still missing; current expired broker profile cannot magically perform it.
4. Original unresolved/no-quorum/transport race/corrupt/incomplete history => UNKNOWN. No new UUID/job/profile/idem, no automatic resubmit/adopt/regrant/resume/debt reset. Missing at one observation is not proof of never-committed.
5. Known ADMITTED is observation only until fresh actually qualified dispatch. Known RUNNING or unknown dispatch delivery never yields a new start permit. COMPUTED is durable metadata, not publication/COMPLETED. CANCEL_REQUESTED is not child exit/refund. Original holds/uncertain debt remain until a separate approved verified-exit/release contract.
6. Restart of coordinator uses SAME existing Grid Consul authority and native retained counters/generation. Root/worker/target release decisions require actual source/handle incarnation and SAME target checks; this packet does not implement them.

## Owner ACK and positive-operation gates

| Positive | Required owners/gates still missing |
|---|---|
|Commission profile v2|Root owns new native20 schema/canonical codec and trusted commissioner/ACL; A2 broker profile-v2 parser/source pin/lifetime; A5 exact13/native-key/job/quota joins. New profile-schema registration in existing authority only. Current broker-v1 CLOSED fields reject v2.|
|Admit one native job|Root/A2/A5 exact ABI and issuer implementation, genuine current broker capture, qualified input/source/units A7 plus A3/A4 bridge where claiming their dataset; actual quota/worker capacity/headroom/containment/ledger CAS; leader/quorum/gen/session checks. Strict UTC-at-Raft-commit remains P0 unless operator explicitly approves a separately bounded native-invalidation semantics profile. No inferred approval.|
|Dispatch|A2/A5 actual issued Assignment/attempt/worker session+lease/fence/hold, verified same-owner one-use permit and actual contained child custody. OS start not atomic with Consul; cancel/dispatch CAS ordering and residual-compute policy required.|
|Observe/cancel/restart|Root/A2/A5 actual authoritative APIs/original binding and current identity scope; cancel own-command/job CAS; fresh history-read profile; UNKNOWN handling; release requires child-exit proof. None implemented.|
|Publish/complete|A2 sole native publication transaction; A4 actual two distinct eligible storage failure domains/full retention/protection closure; A7 durable idempotent projection; A5/A6 observed result identity/schema/units/current read ACK. Two-copy publication is a SEPARATE gate, not evidence obtained from this fixed local input or COMPUTED metadata.|
|Hosted/physical|Actual terminal Windows/Linux CI and separate operator physical quorum acceptance. The workflow-only31e0351 fix has no new native15 qualification. No office services/firewall/Tailscale actions authorized here.|

Existing review2 <=64op/32768 native serialized candidate budgets do NOT transfer to this profile. Full Root commissioning and actual admission plans must be separately fully serialized/measured with all added profile/identity/dependency bytes/indices. The sample profile is2748 raw bytes, not a native transaction measurement. No omit/split/hash-only unchecked-summary shortcut.

## Pure probe evidence and decision

build_contract_probe.py generates CLOSED proposed native20/profilev2/error schemas, DATA-only outer/profile/lab samples and pure-contract-verification.json. Checks include direct-profile rejection, exact13 schema compatibility,25 structural negatives,13 error-code structural positives and20 one-field hash-sensitivity controls. The20 sensitivity mutations are deliberately INVALID admission vectors used only for byte-binding algebra; they are not20 successful native jobs. Zero actual Consul calls, broker contexts, issued Assignments, target calls or scheduler dispatches. No claim of contract approval, resource containment, native UTC, storage publication, hosted CI or physical HA.

Source originals copied as base64-decoded exact GitHub blob bytes; original SHA256 and Git blob OIDs recomputed. Earlier newline-normalized draft copies were replaced before this packet's final hash manifest; no published source evidence was rewritten. Primary originals are identified by source commits/blobs, not copied file timestamps.

Decision requested from Root/A2/A5: single-job commissioned profile v2 binding direction, exact20/13/codec/key/profile/error/restart semantics and independent owner gates. Until exact co-ACK and implementation/qualification: DESIGN_PENDING / NO_GO, public submit DENY, actual scheduler BLOCKED. No shared contract or source code is changed by this proposal.
