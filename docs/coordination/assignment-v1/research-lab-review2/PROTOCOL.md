# ONE-job contract successor review2 — joint freeze requested

Review1 protocol9e220ed2 and measurement1fb6365a remain immutable. Submit13field
schema PRIMARY19357891 and cancel12field schema38069175 unchanged. This successor
adds CLOSED issued/state/result/error schemas and predecessor/phase semantics.
No implementation/native call/grant issued by this packet. Structural DATA only.

## Exact artifacts and byte boundary

11 self-contained schemas: issued-assignment, assignment-counter,
resource-ledger, quota-ledger, resource-hold, lease-lock, original-command,
job-state, phase-receipt, observation, error. Exact hashes in structural-validation
and SHA256 manifest. Native records/requests/responses use frozen Grid C3 bounds:
canonical compact sorted ASCII, no numbers/duplicates/noncanonical bytes,
max16384bytes/depth12. JSON Schema artifacts themselves are ordinary JSON, not
C3 metadata; pin their EXACT bytes, never normalized schema digests by analogy.

receipt_observation.bytes_sha256 = SHA256 EXACT immutable native KV Value bytes
after base64 decoding, before parsing/reconstruction. It excludes HTTP/KV wrapper,
ModifyIndex and itself. modify_index is ACTUAL captured positive native receipt
ModifyIndex, not leader/domain/job counter and not a field embedded in receipt.
These JSON observations never authorize anything or mint a proof.

## Original admission versus current phase

Job schema records immutable original submit request/digest/assignment and
admission_receipt_id; server-generated dispatch/computed event IDs persist at
admission. Mutable sequence/previous_sequence/state/phase_kind/phase_ref bind the
LATEST committed phase at a consistent snapshot, not an admission receipt reused
as proof of later computation. Kind mapping is CLOSED:

| Native state | Phase kind | Receipt locator, derived by owner |
|---|---|---|
|ADMITTED|ADMISSION|N/runtime-v1/receipts/<admission_receipt_id>|
|RUNNING|DISPATCH|L/dispatch-receipts/<dispatch_event_id>|
|COMPUTED|COMPUTED_METADATA|L/computed-receipts/<computed_event_id>|
|CANCEL_REQUESTED|CANCEL_REQUEST|N/runtime-v1/receipts/<cancel request UUID>|

N/L remain exact review1 backend-derived namespace/realm families. No caller path.
Phase receipts always bind kind/event/source command request+digest, ORIGINAL
submit request+digest, job, assignment, execution attempt and committed job
sequence. For admission/dispatch/computed source_request_id is original submit;
for cancel it is the independent cancel command. Internal event IDs are NOT
global command UUIDs. Cancel is a global command with its own full common binding.
Job.phase_ref equals exact phase receipt event_id and its fixed locator.

observation.schema separates immutable admission receipt evidence from current
job sequence/native ModifyIndex/latest phase receipt. COMPUTED requires its
computed metadata+receipt. Cancel-after-computed may retain that immutable
computed proof; it never rewrites computation history. Current phase and computed
receipt references/indices/hashes MUST resolve exact same-consistent-snapshot
rows. Missing/corrupt/incomplete rows do not become admission from a JSON label.

## Exact semantic joins required in backend code

Original C3 submit cluster/generation/actor/quota/profile/input/producer must match
actual namespace/current commissioned principal/profile and issued assignment.
Assignment request_id/intentsha/job/owner/quota match original common bindings.
Worker node/incarnation/attempt and lease ID/epoch/session match actual owned
worker evidence and native lock/binding. Both binding and assignment bytes agree.
Resource hold matches assignment/job/demands; lease lock matches same lease,
assignment/attempt/actual native worker session. All fields are checked, not only
schema success or equality of caller-provided echoes. Current actual observations,
capacity/containment/pressure and ACL/issuer checks from review1 remain mandatory.

Every current phase source command and original binding/intent/receipt must match;
current.job sequence and native phase receipt.job_sequence agree. ADMITTED
admission evidence equals current phase evidence. COMPUTED current phase evidence
equals its computed receipt evidence. Cancel's original submit binding cannot
adopt another job/attempt. Known histories never require old worker lease current
just to disclose them, but current READ_RESEARCH rights remain required.

## Predecessor / genesis / hold semantics

Counter and ledger revision is a DOMAIN value, never Native ModifyIndex.
Backend reads exact current raw value+ModifyIndex; derives new revision=old+1;
stores previous_revision=old and checks the captured index in SAME transaction.
No caller predecessor; no reset to sample1, wrap, skip or field default. Overflow
refuses before send. Assignment.assignment_revision equals NEW assignment counter;
job sequence is a separate per-job domain. Fresh job starts previous_sequence0,
sequence1 ONLY with checked job absence; later transitions use captured seq+1.
New lease UUID requires checked absence, initial lease_epoch1/grant_revision1;
reuse/adoption/renewal is unsupported, not an implied counter reset.

Commissioned initial counters/ledgers revision0/previous_revisionnull require a
genuinely new lab lineage with no prior issuance/history. Root may provision
actual capacity/observation/empty counters; it may not seed fake issued jobs.
Existing/missing/corrupt restored histories never justify reinitializing counters.
For this one-active-worker profile admit only when active_jobs=uncertain_jobs=0,
both held/uncertain resource vectors zero, quota slot available and genuine current
capacity >= demand with qualified headroom/containment. Admission adds demands,
one active slot and increments both ledgers; it does not overwrite unknown debt.
COMPUTED/cancel request does NOT release/refund holds. Verified child-exit/release
is a separately unapproved operation, so conservative debt persists for now.

## Return/error/proof ABI — exact proposal

ResearchLabAuthority.submit/lookup/record_computed/cancel return observation
matching observation.schema.json or raise ResearchLabDenied/ResearchLabUnavailable
with closed error.schema.json data. Error NOT_ATTEMPTED concerns THIS call only;
it never proves an earlier original request absent. Parsed native409 may say
THIS_ATTEMPT_ROLLED_BACK, not terminal original REJECTED. Other transport/cancel/
timeout/malformed native outcomes are UNCERTAIN. No new identity/refund/rekey.
Unknown native fact has null receipt/assignment/current/computed evidence; all
original bytes/UUID/key/holds remain. Unexpected errors after a native send may
not be relabeled pre-attempt denial. No HTTP status/route imposed on Root.

begin_dispatch returns a NEW owner-only ResearchDispatchAuthorization with an
observation and optional opaque ResearchDispatchPermit, not a JSON proof. Permit
is minted only for the FIRST confirmed live invocation after actual ordered
RUNNING commit and current broker/worker qualification. Root/A5 must invoke FIXED
ResearchLabAuthority.require_dispatch(expected_authority, permit, *, owned_attempt)
with exact same commissioned authority/attempt instance; one successful consume.
Foreign/copy/reconstructed/stale/serialized handles or None/method-shaped providers
deny. Both methods async; no nested run/await under impersonation. Root trusted
composition and actual worker source remain qualification prerequisites.

Replay/lookup of already RUNNING returns observation ONLY, never a fresh start
permit. Crash/timeout between commit and delivery is execution UNKNOWN, no automatic
child restart/resume/regrant. If native dispatch commits before cancel, bounded
residual compute can be stopped cooperatively; no claim that OS start is atomic
with Consul. Final durable effects still require current grant and job CAS.

lookup may offer owner-only ResearchObservationProof after actual consistent
original common bindings/intent/assignment/admission/current phase resolution and
current READ_RESEARCH. Fixed expected authority must verify it; JSON observation
and hashes are not proof. This is NOT a storage publication COMMITTED receipt or
A7 projection capability; no existing completion-schema alias is authorized.

## Expiry decision from Root, strictly bounded scope

Native principal session invalidation/policyCAS is target-authoritative. Local
preflight/timeout cannot prove certificate UTC-at-Raft-commit. Strict UTC-at-commit
remains P0, not closed by this disposable profile. Late or clock-uncertain call
retains original+holds and emits NO child dispatch/publish permit. Observation
separates actual known native state from policy_qualification CURRENT/UNKNOWN;
operation_observation is UNKNOWN when qualification is unknown even if an actual
native receipt was already resolved. Never change known committed native history
to absent/uncommitted. Unresolved native fact uses stateUNKNOWN/null evidence.
Those known facts are internal owner data; no public disclosure without current
read authorization. Fresh authorized historical lookup can resolve them later.

## Updated exact candidate budget, not native/workload qualification

The regenerated full plans validate17 proposed record writes against these
schemas. Computed/cancel-after-running additionally check the current dispatch
phase receipt index, not just job root and old admission receipt.

| Candidate | Ops | Encoded bytes |
|---|---:|---:|
|ADMIT|43|20119|
|BEGIN_DISPATCH|34|9295|
|COMPUTED_METADATA|35|9909|
|CANCEL_REQUEST after RUNNING|26|10658|

Max native index and128char actor quota/key sample retained; example domain
predecessors4->5,7->8,9->10 are semantic BYTE examples, NOT native seeded histories.
Actual first issuance uses genuine genesis or genuine retained history. Runtime
MUST serialize/measure actual complete plan each send; any extra dependency needs
updated ledger, no omit/split to fit. Review1 numbers remain its old schema scope.
No A4 publication/2copy closure/projection plan is fit-qualified here.

34positive/917negative structural vectors plus7 arithmetic controls pass; they
are not authority/worker/Consul tests. Native calls/grants=0. FULL_API_ACK pending
Root/A5 machine joins/errors/proof API, Root research broker/profile registry and
expiry qualification, actual A5 capacity/contained worker. A4/A7 two-domain result
publication/retention/projection remains P0; only COMPUTED metadata is allowed.
