# VM Lab authenticated-attestation architecture and TEST verifier v1

Base: PR199 `8d9c818788b4b7e4a8988410c424c7f9990e9f0a`.
Scope: DESIGN and entirely offline public-test-key signature harness. No VM,
observer/principal provisioning, SQL/initdb, service, production, host trust store,
PKI fetch, network attestor, physical executor, schema2 or deployment is added.
No embedded production private keys. Public deterministic test seeds in the fixture
are deliberately known bytes and cannot serve as authority. Never reuse them.

## Architecture / trust boundaries for a future implementation

Separate verifier/policy authority, independent observer and approval authority.
Pre-provision their role-scoped public trust roots out of band from the evidence,
with reviewed key IDs, algorithms, scope, validity and revocation policy. No trust
on first use, inline supplied public key, OS-store mutation or automatic PKI fetch.
An immutable policy decision binds authority role and observer identity, not only a
valid signature. Distinct signer keys and roles do not prove distinct human operators.

Trusted host/hypervisor/admin/image and trusted observer code are prerequisites.
Actual host/VM identity must come from a trusted observer/measurement boundary,
not a guest-provided UUID, hostname or signed unverified declaration. The observer
must establish effective token SID, impersonation context, groups, elevation,
privileges and process/code identity for three independent principals. Raw token
handles/credentials must never be exported as evidence. Guest local administrator
can subvert an in-guest observer; place decisions outside that control or exclude
that actor. Hostile host admin remains STOP_OS_BOUNDARY_REQUIRED. A VM on an
adversary-controlled host is not the proposed trust boundary.

Future observer payload needs schema/canonicalization/domain versions; immutable
plan/image/artifact/observer-code digests; actual host/VM/session identity and
measurement provenance; token/SID provenance; exact case attempts/results and
postconditions; independently signed operator approval scope. These require a NEW
executed-evidence schema, not promotion of this draft. Signature authenticates a
key's statement, not truth or freshness of measured facts.

A future trusted authority issues unpredictable single-use nonce/session challenges
bound to plan, verifier/audience, immutable policy and code/artifact identities.
Reserve sequence/session state durably and atomically; prevent concurrent reuse,
crash/rollback/restart replay, cross-plan/cross-VM/cross-verifier reuse and stale
policy/revocation epochs. Trusted time must reject expired/future claims with an
explicit bounded validity/skew policy. Time source, restart state and monotonic
counter recovery are separate obligations. No such durable issuer/ledger/clock is
implemented here, and no challenge generation is implied by a caller's fields.

Rotation/revocation requires independently approved root policy updates, key validity
and compromise response, freshness deadlines and revocation epochs. If an offline
verifier lacks a sufficiently current authenticated revocation snapshot, STOP.
No automatic fallback to revoked/older/unknown keys or algorithm negotiation.
Approval authority and observer policy/code compromise must be modeled independently.
Host admin, key custody, policy authority and signing infrastructure cannot all be
controlled by the same adversary and still constitute independent attestation.

## Synthetic protocol implemented here

`installer/vm_test_attestation.py` accepts only TEST schema1, domain
GRID_VM_LAB_TEST_ATTESTATION_V1 and canonicalization GRID_JSON_INTEGER_V1. Existing
bounded JSON loader rejects duplicate keys/deep/large/nonfinite/surrogate inputs.
Signature input additionally rejects ALL JSON float values. Exact integers and
bool remain distinct in schemas. Canonical bytes are sorted-key compact ensure_ascii
JSON (no floats) with explicit version/domain prefix and NUL separator. Headers
(key_id, role, algorithm), protocol fields and entire payload are signed together.
Array order is significant; whitespace/key order outside canonical representation
is irrelevant. This is a documented narrow JSON profile, not a JCS compliance claim.

Two Ed25519 signatures are mandatory, with exact test-observer-v1 / test-approval-v1
roles and fixed public keys pinned in verifier source. Unknown, old/revoked-style
IDs, supplied keys, other algorithms or role confusion are rejected. No production
keys or configurable authority entry point is accepted. Ed25519 verification is
provided by PyCA cryptography, never hand-written math, hash-as-signature or fallback.
Correctly signed PUBLIC fixture statements are TEST_KEY_ONLY, not authenticated
observation or independent approval.

Payload binds prior draft (immutable plan, VM/host/image, quotas and exactly twelve
NOT_RUN/BLOCKED_UNPROVEN cases), pinned observer/approval IDs, caller-supplied test
challenge session UUID/nonce/sequence and code/artifact digests, issued/expires UTC.
Challenge must match the trusted test caller's expected context exactly. Timestamps
use YYYY-MM-DDTHH:MM:SSZ only, zero clock skew in this deterministic harness,
issued<=now<expires and TTL<=300seconds. Caller supplies test time; system clock
is not read and is NOT attested. Test fixture dates are synthetic, not live evidence.

A bounded in-memory ledger consumes nonce/monotonic session sequence only AFTER
both signatures and all semantic checks. A mutex prevents concurrent test reuse;
invalid input cannot burn a nonce. The ledger holds at most1024 successful test
entries. Sequence monotonicity applies inside a session and the one ledger only.
Fresh object/process/restart or caller-controlled time/challenge defeats its scope:
NO durable replay/freshness guarantee is claimed. Caller-owned plan/challenge/state
and in-process code are trusted test inputs; hostile same-process memory mutation
is outside this harness boundary. No database, file ledger or physical resource is used.

All returns preserve statusBLOCKED, readiness_passed=false, physical_ready=false,
execution_authorized=false, verified_safety_cases0 and twelve NOT_RUN cases.
Authentication=TEST_KEY_ONLY; signature_result=VERIFIED_PUBLIC_TEST_FIXTURE.
Public test keys cannot be real signing authority because their private seeds are
published. Neither valid signatures nor green CI enable any capability or schema2.
False PASS/token/approval results remain rejected even when signed by test keys.

## Dependency isolation and provenance limits

`installer/tests/requirements-vm-attestation.txt` pins cryptography50.0.2,
cffi2.1.1 and pycparser3.11, with reviewed PyPI wheel SHA256 for CPython3.11/3.12
Windows/Linux x64. Install requires --only-binary=:all: --require-hashes. Unsupported
platform/missing wheel/hash/version fails closed; no source builds or fallback.
Hashes were obtained from versioned PyPI JSON metadata over TLS, not independently
signed project provenance. Pins constrain supply-chain input, not prove absence of
vulnerabilities or a formal crypto/security certification. Dependency update requires
fresh review/hashes/tests. Main Grid requirements and bundled production runtime
are NOT modified. New crypto dependencies are installed only in disposable test venvs;
Windows bundle test uses a separate runner-temp venv and imports the bundled verifier.

No crypto dependency in a normal offline checkout means the OPTIONAL test module is
explicitly skipped. Dedicated mandatory CI sets GRID_REQUIRE_TEST_ATTESTATION=1 and
requires exactly34 executed tests with zero skips/errors/failures on Linux/Windows
Python3.11/3.12. Missing/mismatched crypto version blocks verification. Positive fixture
runs in PowerShell5.1/7 and from built Windows bundle; never initializes a Grid runtime.
All crypto is local; network namespace is disabled for Linux verification after setup.

Primary sources: [PyCA Ed25519 API](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/),
[cryptography50.0.2](https://pypi.org/project/cryptography/50.0.2/),
[cffi2.1.1](https://pypi.org/project/cffi/2.1.1/),
[pycparser3.11](https://pypi.org/project/pycparser/3.11/).

## Negative tests / audit and stop conditions

Tests cover valid blocked double-signature fixture; exact-message key substitution;
unknown/revoked-style keys; algorithm/role/inline-key confusion; missing signature;
protocol/version/canonicalization mismatch; post-sign tampering and rehashed/resigned
plan/host/VM/image/code/artifact/token/PASS/approval/case order or omission; nonce/
sequence mismatch, replay and concurrent replay; invalid/expired/future timestamps,
TTL and float ambiguity; duplicate JSON and readiness injection. Successful verifier
assertions are synthetic crypto evidence only, not actual different-token tests.

STOP before real attestation: no real protected signing roots/key custody, independent
observer, authenticated approval, actual token/principal provenance, hardware/host
identity assurance, durable challenge/replay state, trusted clock, fresh revocation
policy, or executed guest negative cases. Native ACL ABA and global kernel exhaustion
remain open. Under hostile host-admin objective require a separately administered
trust boundary or STOP. No automatic resource creation, repair, activation or cleanup.
Rollback is reviewed source revert; no production/resource state changed.
