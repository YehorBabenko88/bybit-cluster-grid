# Implemented internal native job negative path

Scope: NEGATIVE_PATH only, not scientific E2E or positive NativeJobAdmission.
Root explicitly requested an executable authenticated native handler rather than
a callback, fake capacity, new broker or another authority. Existing reviewed
lab13 bytes and P2 source are retained. No new SID wire envelope is necessary.

Actual module: `grid.authority_assignment_v1`.

```python
ResearchLabAuthority(authority, generation, *, broker)
async ResearchLabAuthority.submit(original_lab13_bytes, *, context, leader, owned_attempt=None)
async ResearchLabAuthority.lookup(original_lab13_bytes, *, context)
```

Constructor requires exact existing ConsulSessionAuthority and exact existing
ResearchIdentityBroker bound to the SAME authority/generation. It creates no
broker, session, voter, campaign, queue or separate consensus. `context` must be
the genuine current context from that broker's actual mTLS session. `leader` is
the existing Grid ConsulLease; callers cannot substitute a JSON actor/session.

The handler validates the closed original lab13, calls the fixed broker methods
for current SUBMIT_RESEARCH or READ_RESEARCH identity, requires target-bound P2,
and checks original actor/quota/profile/cluster/generation bindings. It derives
keys itself, reads ALL captured identity rows plus the existing leader and
planned-job key in ONE actual consistent Consul transaction, and compares exact
indices/raw bytes/native sessions. Submit checks current leader generation and
session/index. Both paths recheck the fixed broker capture and local peer/expiry
after awaits. No post-read current check is a Raft commit-time UTC assertion.

Returned `ResearchAdmissionResult` is frozen observation DATA, publicly
constructible and NEVER a capability, receipt or issuer-owned proof. Fields:
`outcome`, `reason`, `original_intent_sha256`, `commit_status`,
`effect_permitted`. All current returns have `commit_status=NOT_ATTEMPTED`
(this invocation attempted NO mutation) and `effect_permitted=False`.
`owned_attempt` currently cannot grant anything, including when non-None.

Submit with absent planned-job row returns DENIED /
NATIVE_WORKER_RESOURCE_API_UNQUALIFIED. This states that the actual native
worker/resource API has not been qualified, not that measured free capacity is
zero. With an existing row it returns UNKNOWN /
JOB_RECONCILIATION_API_UNQUALIFIED, without exposing its payload or claiming a
verified commit. Lookup always returns UNKNOWN /
JOB_RECONCILIATION_API_UNQUALIFIED after current authenticated consistent reads.
Absence never becomes proof of never-committed/NOT_FOUND. Prior commits are not
erased/refunded, originals are not rewritten, and no replacement permit exists.

Malformed originals fail validation; invalid/revoked/expired identity raises the
actual broker exception; lost leader, changed snapshot/generation or no quorum
raises the actual authority/unavailable exception. These failures are NOT
converted into successful resource-gate observations. In particular, no caller
callback, bool, JSON, missing provider or None can establish permission.

Disposable invocation (use only the actual source-owned provisioned objects):

```python
native = ResearchLabAuthority(consul_authority, generation, broker=research_broker)
observation = await native.submit(original_lab13_bytes,
    context=actual_broker_context, leader=actual_existing_grid_lease)
assert observation.effect_permitted is False
read_observation = await native.lookup(original_lab13_bytes,
    context=actual_broker_context)
```

Reproducible real disposable invocation is also implemented in
`tests/coordination/assignment_v1/test_native_job_negative.py`. It reuses pinned
Unified1f6 actual mTLS/Root-commissioned profile/principal/policy fixture, creates
actual owned Consul sessions, and NEVER seeds issued job/Assignment/hold/receipt
rows. Five new cases cover valid deterministic negative submit/unknown lookup,
forged context/changed original, destroyed leader, actual policy revocation and
actual one-of-three no quorum. The existing20 tests remain required; new runner
requires25 exact unique IDs. Initial RED5266620d0c28d746499a597885ece426a025e541
ran25 tests:20 prior PASS and5 missing ResearchLabAuthority AttributeError.
Primary raw/OID guards execute before and after, including on this failed suite;
final source identities/logs/qualification are reported separately.

Pinned support remains Unified1f6b0b5c231853607f5bec780f1544cd32bf577d;
Core coordination and runtime/layout remain unchanged. Root canonical manifest
at Unified3af06455b601a328e94339327a0597eada802c38 is a SOURCE assembly with
Grid40e catalog; this new component is NOT silently substituted into that pin.
Positive worker/attempt API, quota/ledger/assignment mutation, receipt resolver,
dispatch/effect consume, publication/current artifact access remain unqualified
and require actual native dependencies plus owner co-ACK before implementation.
Public submit DENY; physical/production NO-GO. No services/deployment/merge.
