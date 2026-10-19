# Authenticated-attestation adversarial audit and replay/crash MODEL

Base: PR200 `5d18b2810a8b1b22ce59e46334d35e07f55c46c7`.
Scope: TEST-KEY-only verifier hardening and PURE MEMORY model. No durable store,
filesystem journal, registry, SQL/database, network authority, service, VM or real
issuer exists. No production/LS5/LS7 operations. Schema2 remains disabled.

## Reproduced defects / regressions

P2 protocol consistency: verifier re-read caller-owned challenge at replay consume.
A mutation injected after evidence inspection changed nonce/sequence from those
actually signed, so the wrong nonce was consumed and sequence high-water could be
poisoned. This demonstrated state corruption/denial of future test use, NOT a
production authorization or proven double-acceptance bypass. Plan mutation at the
same boundary also changed the evidence being inspected. Entry now detaches bounded
canonical JSON copies of plan/challenge; consume uses the validated private context.
A test proves the consumed nonce/sequence exactly match the original signed values.

P2 diagnostics: unexpected crypto backend RuntimeError propagated raw backend text;
a damaged replay-state dictionary produced AttributeError. Backend failures now map
to fixed VM_TEST_CRYPTO_FAILURE / VM_TEST_CRYPTO_UNAVAILABLE without payload text;
known invalid-signature errors retain VM_TEST_SIGNATURE_INVALID. State types/bounds
are checked under lock; invalid state maps to VM_TEST_STATE_CORRUPT. Budget failure
cannot mutate the ledger. Copy-before-replace avoids allocation failures after
partially changing seen/sequence collections; interrupted replacement poisons state.

Caller could shadow consume with an instance attribute. Slots reject that accidental
method replacement. They are NOT hostile same-process memory protection. Module
monkeypatching, private-state mutation, class replacement, lock interference, caller
clock/challenge fabrication and process control remain outside this trusted-test
boundary. Snapshots are not an atomic cross-object OS transaction: concurrently
mutated contexts may be refused or captured, and must still match signed bindings.
No sandbox or privileged-admin protection is claimed.

## Signature audit and exact prior gate

Two public TEST roots, Ed25519 algorithm, role/key/protocol/canonicalization headers
and payload stay pinned/signed. No private-key API is imported by verifier; signing
is confined to the explicitly public fixture generator. No crypto primitives or
fallback hash-as-signature were added. Both signatures and semantic bindings must
pass before ledger consumption. Invalid first or second signer, duplicate/noncanonical
JSON, floats, oversized/deep inputs, role/key substitution and caller mutations do
not authorize anything. Unexpected backend exceptions are contained only around
library import/verification; BaseException termination is not falsely reported as
successful verification. Fatal interpreter/resource/output failures cannot promise
a report; no physical capability exists regardless.

Exactly34 original crypto tests remain mandatory and unchanged, zero skips. Nine
new adversarial cases test deterministic mutation hooks, partial signers, backend
faults, state corruption/budget, seeded JSON mutation and no private-key import.
Roundtrip compares bounded-loader output with stdlib JSON decoding/canonical bytes.
These share the stdlib parser: this is NOT independent-parser confirmation. No new
parser/crypto dependency was introduced just to claim independence. Published test
seeds remain public and authenticate no real actor. Positives TEST_KEY_ONLY/BLOCKED;
zero verified safety cases and all twelve guest cases NOT_RUN/BLOCKED_UNPROVEN.

## Replay model: state and bindings

`vm_replay_model.py` is an executable specification in Python memory only. Frozen
Image/Record/Claim/Witness/Checkpoint values represent hypothetical storage states.
Inputs are strict bounded metadata; binding is detached before use. It contains
TEST-only audience, plan/image/code/artifact digests, host/VM UUIDs and policy epoch.
These are declarations, not measured identities or protected authority.

Model roles are literal issuer / policy-authority labels, NOT authenticated callers.
AssumedValidation explicitly represents the axiom that observer+approval validation
already passed for one exact nonce/claimant/fence/key-policy-epoch context, binding and evidence digest. Anyone can construct that model
value; it is not a verifier receipt, signature, approval or runtime capability. The
model is intentionally NOT wired into the crypto verifier or an executor.

- ISSUE: role/policy/CAS/clock/budget checked, monotonic issuance counter advances,
  record is committed before nonce is returned. Deterministic hash(counter,binding)
  creates reproducible model IDs, NOT unpredictable real nonce issuance. No eviction;
  at64 records the model stops rather than forget replay history.
- CLAIM: compare-and-set revision allows one competing winner; record fence increases,
  claimant and bounded lease are recorded. A takeover after expiry increases fencing;
  stale verifier or transaction arriving after lease cannot consume.
- CONSUME: current epoch, challenge expiry, claim fence/claimant/lease, expected revision
  and assumed two-role validation context/binding must match. A validation event from another issuance or prior claim fence is refused. Commit CONSUMED only after these
  checks; no simulated physical task occurs. Postcommit lost ACK still rejects replay.
- ROTATE: policy-authority transition increments key and policy epoch. Outstanding old
  challenges/claims are revoked; stale consume cannot reactivate them. No actual keys,
  trust root or revocation store is changed.

A per-instance lock models serialized transactions; expected revision provides CAS,
per-record generation fences claims. Separate model replicas with separate locks are
not a distributed store. Future implementation would need a single authoritative
transactional linearization point and durable fencing, not this Python lock.

Model time uses integer observed and reference inputs, drift<=2 and nondecreasing
committed high-water. Neither is an actual trusted clock. If both lie/roll back, that
assumption fails. Record TTL60 and claim lease5 are model constants, not deployment
recommendations or measured Windows behavior.

## Commit / crash / recovery invariants and assumptions

The abstract persistence contract commits an immutable image, revision and independent
nonrollback witness before acknowledging success. This is a MODEL AXIOM, NOT a real
atomic durability implementation. A future backend must establish write/fsync/commit
and anchor ordering; no journal/database design has been approved here.

| Injected stage | Stable model outcome / recovery |
| --- | --- |
| before_prepare | No new committed effect, old checkpoint recoverable |
| after_prepare | Pending state discarded; retry allowed, no acknowledged effect lost |
| after_commit | Effect is committed despite missing ACK; consume cannot repeat |
| after_ack | Restart retains effect; no second consume |
| torn_commit | Image/witness/anchor disagreement: BLOCKED, no automatic repair |

recover(checkpoint, independent_current_anchor) validates structural bounds, image
fingerprint/revision and both witness/anchor matches. Old image with fresh anchor,
missing anchor, corrupt image or torn state fails closed. No automatic rollback,
nonce reuse, repair or cleanup is performed. A hash protects consistency only; it
does not authenticate an anchor. All objects still reside in test-process memory.

The critical counterexample is tested: if checkpoint AND witness AND supplied anchor
are coherently rolled back, recovery cannot distinguish the stale world and can
repeat modeled consumption. Likewise no trusted issuer/key/clock truth is established
by literal fields. Report therefore retains INDEPENDENT_NONROLLBACK_ANCHOR_ASSUMED,
ATOMIC_DURABILITY_ASSUMED, AUTHORITY_AND_CLOCK_ASSUMED and deterministic-nonce blocker.
Real power loss, filesystem reordering, fsync behavior, multi-host partition recovery,
root compromise and durable replay are NOT tested or implemented. Future integration
must fail closed on uncertain acknowledgement/anchor state, even at availability cost.

## Test / CI / stop matrix

Twenty-six pure model tests exercise issuance/consume crash boundaries, restart,
old snapshot and missing anchor, torn commit, correlated rollback limitation, delayed
consume, takeover, concurrent CAS, epoch revocation, clock drift/high-water, invalid
roles/bindings/evidence, budgets and seeded scope mutation. New nine crypto tests run
separately from original34 with zero-skip gates. Python3.11/3.12 Linux/Windows,
PS5.1/7 and built-bundle memory-model smoke gates preserve dependency isolation/hash
pins from PR200. No native test is executed locally; hosted native GUID tests remain
separate and do not prove guest token separation or authenticated observation.

All model reports: MODEL_ONLY, durable_storage=NOT_IMPLEMENTED, status=BLOCKED,
readiness/physical_ready/execution_authorized=false, verified_safety_cases0 and twelve
NOT_RUN cases. Passing model tests prove only the stated transition assertions under
axioms. STOP before real use: protected key custody, actual observer/approval identity,
real principal/token provenance, trusted time, durable ledger/anchor/revocation,
actual guest isolation/tests, hostile host-admin boundary, ACL ABA and kernel exhaustion
remain unresolved. No physical approval follows from signatures or green CI.
Rollback is reviewed source revert only; no production/resource state changed.


Review strengthened an initially binding-only validation event: two RED regressions
showed it could be reused for a different nonce or takeover fence with the same
metadata. AssumedValidation now embeds the exact immutable Claim context; both
cases are rejected without a state change. A takeover needs a newly scoped model
validation event. This fixes the MODEL contract, not a production attestation bypass.
