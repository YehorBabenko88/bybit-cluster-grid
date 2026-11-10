# One bounded strict-time candidate pass: causal post-quorum UTC upper bound

2026-11-10. Candidate CQC-UTC-UB-v1-review1. SOURCE/MODEL HYPOTHESIS ONLY. Not selected, not an implemented API, not permission to modify Consul, clocks, keys or policy. This is the ONE requested candidate pass, not a new loop or another authority. Verdict: conditionally sound historical upper-bound proof; INSUFFICIENT to enforce strict expiry of all native mutations in the current architecture. Option1 remains strict and logical mutations DISABLED.

## Exact event selected

Choose C_i as the existing leader-loop event at which Raft's commitIndex first advances from below i to at least i, in the same leader term T, for a protected transaction entry whose log term is T. Specifically: Raft1.7.3 `runLeader`, `case <-r.leaderState.commitCh`, `oldCommitIndex := r.getCommitIndex()`, `commitIndex := ...getCommitIndex()`, then `r.setCommitIndex(commitIndex)` (raft.go around730–735). This is an actual native commit decision, not a client ACK, wall-clock sample, state application or HTTP receipt timestamp.

The commitment calculation requires a majority of voting members' matched durable indices and the current-term startIndex rule (commitment.go). Let Q_i be the earlier physical instant when the requisite quorum actually finished storing the entry. Under the qualified storage/transport assumptions, Q_i <= C_i. Choosing the implementation commit-decision event is conservative for proving quorum durability before expiry: a valid bound on C_i also bounds Q_i. It does not assert that Q_i and C_i are identical or change the operator's original definition silently. Operator/authority owners must freeze that definition before protocol adoption. No proof is made from leader lastIndex, a lone follower ACK, a raw KV ModifyIndex or a session's presence.

Pinned semantics: [Raft1.7.3 commitment.go](https://github.com/hashicorp/raft/blob/v1.7.3/commitment.go), [raft.go](https://github.com/hashicorp/raft/blob/v1.7.3/raft.go), [future.go](https://github.com/hashicorp/raft/blob/v1.7.3/future.go); Consul1.22.2 [Txn.Apply](https://github.com/hashicorp/consul/blob/71f21bf33d6070fc1522b3ba225b4aac0a390049/agent/consul/txn_endpoint.go) calls raftApply after ACL/pre-checks. Its current response contains transaction results/errors, not this commit event/certificate/current-term hook. Current broker does not implement it.

## Concrete hypothetical witness and exact binding

Proposed native witness runs in the existing authority's protected execution path causally AFTER C_i. It is not a client-supplied time provider, second leader or second consensus service. It must retain a non-forgeable native event handle binding cluster ID, authority generation, active configuration/index/voter-set hash, leader ID, term T, old/new commit indices, exact entry i/term/log-data digest, original N13/D and P/S/T20/H joins. It must establish successful domain transaction application separately from merely committing a rejected transaction log entry. No existing fixed API or adopted record supplies this handle.

The witness obtains one verified UTC interval [L_W,U_W] for an actual sample event W after C_i, then signs a canonical certificate with domain separation and witness key/epoch/source hashes. The certificate includes the exact immutable event binding, calibration/source evidence, interval, strict expiry E, and evidence that the protected hook—not an arbitrary caller—sequenced C_i before W. It must not name U_W as the commit timestamp. An unpredictable nonce alone cannot prove sequencing if the native issuer/source or key is untrusted.

One concrete uncertainty construction to review would require a trusted calibration anchor UTC interval [L_0,U_0], a qualified counter that covers elapsed real time including pauses/suspend, maximum fractional frequency error rho<1, elapsed counter interval Delta and bounded sampling error epsilon. A conservative upper bound can be U_W=U_0+Delta/(1-rho)+epsilon under precisely those physical assumptions. This is an assumption-based derivation, not a value inferred from Windows wall time or a supplied JSON number. Calibration must have authenticated provenance and bounded error including transport asymmetry; source age/holdover, reboot, counter discontinuity, sleep, VM migration or unqualified drift invalidates it. NTP configured, TPM present, GetTickCount/QPC resolution, monotonicity or a2.5s RPC budget alone does not establish these premises.

Required qualification and non-exportable or equivalently protected signing-key custody do not currently exist. All hypothetical interface names and fields here are PROPOSED, not runtime APIs/capabilities. No key/time source/hook/certificate was created or invoked in this pass.

## Conditional proof — what it genuinely establishes

Given validated native binding, actual current-term quorum commit at C_i, causal C_i <= W, trustworthy W <= U_W and U_W < E:

`Q_i <= C_i <= W <= U_W < E`.

Therefore C_i and quorum durability Q_i were before expiry. No equality between ACK/sample/upper bound and C_i is used. No upper latency bound on the prior quorum delay is needed to prove this particular successful historical inequality; the actual verified post-event upper bound does the work. A sample with U_W>=E proves neither that the earlier C_i was late nor that it was early: return UNKNOWN. Missing/unqualified evidence also means UNKNOWN. Exact equality U_W=E is not strict proof.

This is a sound conditional historical proof if its assumptions hold. It improves on pretending a pre-send timestamp certifies the future, but it is not an existing capability. Current sources provide none of the qualified UTC, protected event hook, verified term/log binding, key custody or certificate persistence necessary to instantiate the proof.

## Failover, term and recovery cases

| Case | Required interpretation |
| --- | --- |
| Current-term entry, same term through W, all bindings valid and U_W<E | Conditional before-expiry historical fact. Still no current principal/resource/worker/publication grant. |
| Entry from an old term | Direct candidate rejects/UNKNOWN. A new leader's term or current barrier cannot simply replace the old entry term/time. |
| Current-term barrier could establish a prefix | A separately bound current-term barrier with correct durable log-prefix/configuration proof and post-barrier bound could conservatively bound an old committed prefix. That is not direct proof of the original event's instant, not old-lease renewal and not implemented by this one-pass candidate or vanilla KV response. No automatic resubmit/new barrier is authorized here. |
| Term changes between C_i and W | This direct same-term witness cannot issue a new current-term certificate. Reconcile original history without retry/refund. A valid already-issued immutable old-term historical certificate need not be erased solely because a later leader exists. |
| Sender pauses before/after send | Request can still commit after expiry. Local pause/cancellation does not cancel Raft. No replacing original/request/attempt. |
| Native witness pauses after C_i before W | Qualified time must include that elapsed real time. If U_W reaches E, historical time remains UNKNOWN even for an actually early commit; this is conservative loss of availability, not evidence of a late commit. |
| Witness samples before E, proof delivered after E | An intact verified causal bound may still prove historical C_i<E. Current disclosure/effect eligibility must independently fail closed; proof delivery time is not substituted for C_i, and no expired writer is revived. |
| Log store or storage cache does not meet assumed durability | No qualified durable-quorum claim. A returned StoreLogs/match index cannot substitute for actual platform durability assumptions. |
| Crash loses certificate/key/event handle | Existing committed record may survive while time proof is UNKNOWN. Never mint it again under another term from the old index or roll back/refund/rekey. Current certificate HA durability/replay store is NONE. |
| Snapshot restore/new authority generation | Historical facts may remain historical, but an old generation's proof cannot authorize the restored current authority. Preserve original history and reject stale/current-eligibility use. |

## Decisive enforcement gap: AFTER cannot prevent a late commit

Consider C_i=12, E=10, W=13 and valid U_W=14. The post-event hook correctly refuses a before-expiry certificate. Nevertheless the native transaction has ALREADY committed at12. Returning UNKNOWN/denying the worker does not make this transaction disappear. In vanilla Consul, its domain mutation may still apply; a rejected proof cannot retract a committed log entry or atomically rewind a quota/Assignment.

If the witness is moved BEFORE C_i to reject early, its bound no longer causally upper-bounds a future C_i; a pause/quorum delay can cross expiry afterward. That is the original counterexample. A later certificate-storage transaction introduces another native commit event with its own time/durability semantics; it cannot retroactively certify itself or backdate the first commit. Current term/quorum evidence fixes ordering/durability, not this prevention gap.

Calling an already committed authority mutation merely tentative or checking certificate only before worker start would change the protected state/admission definition. This candidate does NOT approve that reinterpretation, a two-phase protocol, new queue/ledger, weaker Option2 or a second authority. Existing logical writes remain protected by the selected policy; late protected mutations cannot be hidden behind a failed public response.

Accordingly the candidate, as specified, is REJECTED AS AN ENABLING STRICT NATIVE MUTATION PROTOCOL. Its conditional historical theorem is valid but insufficient for the full requested safety property. It cannot turn on logical mutations even if a qualified clock/key/hook were added. This is the bounded pass's result, not a request to approve an unspecified protocol.

## Exact external engineering prerequisites and finite decision

Current availability is NONE for: qualified UTC interval/holdover source; native after-commit event/term/config/log/digest handle; protected witness keys and causal attestation; durable/replayable certificate storage tied to the actual transaction; adopted consistent native enforcement before any late protected state mutation; corresponding security/durability/clock failure evidence. These are engineering dependencies, not source ACKs or missing operator selection of Option1.

Decision record recommended for Root/operator: accept/reject the conditional historical-bound explanation; mark CQC-UTC-UB-v1-review1 insufficient for strict mutation enforcement; retain the existing block. Do not ask again about Option2 or approve a boolean/time-field workaround. Any future viable candidate must first provide an actual deterministic consensus-boundary enforcement/abort proof for late commits and replay/failover, then exact source/security/UTC/custody ownership approval before adoption. A Consul/native protocol change would need separate explicit review; none is implemented or authorized here. There is no current deployable protocol to approve in this pass.

## Executable bounded checks

Eight new pure model tests cover valid conditional historical bound, late native mutation despite no certificate, early commit with late sampling UNKNOWN, valid early proof delivered late (historical only), old/changed term, unqualified or mismatched witness assumptions, expiry equality/pre-event/invalid upper bound, and no actual capability/effect issuance. Together with the previous seven,15 MODEL_ONLY tests pass locally. Assumption booleans and author-supplied coordinates in the model are NOT runtime proof arguments or credential formats. No native clock, signature/key, Raft hook, Consul, worker, SDK/browser, provider, office process or physical fixture is invoked.

This completes ONE bounded candidate pass. Original missing-model setup RED is retained separately (0tests/1setup error); no native RED or native positive PASS is claimed. Existing source/negative integration work and Root's MissionController continue independently. Strict Option1/logical DISABLED/public DENY/implementation base NONE remain unchanged.
