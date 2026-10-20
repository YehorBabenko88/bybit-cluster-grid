# Cross-component contract boundary audit — schema 1

Issue #208; initial base `5d18b2810a8b1b22ce59e46334d35e07f55c46c7`.
Owned by Agent #5, separate read-only offline module and adversarial tests.

## Contract matrix (schema 1)

| Source | Acceptable report status | Positive evidence is NOT |
| --- | --- | --- |
| VM Lab PlanOnly | BLOCKED | a VM or permission |
| VM evidence draft | BLOCKED / UNVERIFIED | verified observer provenance |
| Public test-key attestation | BLOCKED / TEST_KEY_ONLY | independent operator approval |
| Ownership session | BLOCKED / SYNTHETIC_ONLY | ownership of installed adapter tree |
| Isolated PostgreSQL plan | VALIDATED_PLAN_ONLY | schema2 capability |
| Host preflight | BLOCKED | a reserved port / pinned identity |
| Physical deployment harness | BLOCKED | actual guest execution |

The audit returns BLOCKED, schema2=false, execution_authorized=false,
physical_ready=false, readiness_passed=false, zero verified safety cases,
and twelve NOT_RUN/BLOCKED_UNPROVEN guest cases. Missing stages are MISSING_UNPROVEN;
they are not silently omitted from the decision. No input is mutated.

## Explicit boundaries

The validator consumes *untrusted data*, never filesystem handles, a Win32
security token, observer signatures, challenge issuer state, machine time or a
live PostgreSQL connection. It cannot prove a report originated from the named
component. Versioned bindings only detect accidental/hostile misrouting of
serialized metadata; they are not authentication. A forged report that obeys
schema1 can still be accepted as PRESENT_UNTRUSTED_METADATA, never authority.
Cryptographic signed raw envelopes must be verified separately with the
dedicated isolated public-test-key verifier; copying its result is insufficient.

The VM plan uses canonical JSON SHA256. The adapter's PowerShell ordered-byte
hash is **not** interchangeable with that digest. Postgres run_id/node_id/commit
must match explicit caller intent; adapter roots and ownership identity
remain *unproven*. Schema2 is deliberately absent. Test-only identity binding
never establishes an actual SID, a different effective token, host identity,
approval authority or fresh revocation state. All twelve guest cases are
unexecuted and cannot be interpreted as safety PASS.

## Threat coverage and residual risks

Negative cases cover PASS/status injection, false authorization, case-count and
order tampering, schema2, VM token substitution, approval/network integration,
wrong VM/host/image/observer/session/nonce/code/artifact, stale cross-plan hashes,
inconsistent PostgreSQL run/node/commit, and synthetic ownership promotion.

This checker is a *non-authorizing compatibility guard*, not a hardened parser
service or production gate. Untrusted same-process callers can mutate Python
objects or bypass the checker, and separately forged self-consistent metadata
can satisfy checks. No stable trusted clock, durable nonce ledger, independent
identity root, authenticated attestation, native ACL ABA exclusion, host-admin
isolation, global kernel exhaustion guarantee, physical guest evidence or
deployment integration exists. A green CI means only offline regressions passed.

## Rollback and constraints

Rollback is a reviewed revert of Agent #5 new files. Never enable schema2,
merge, deploy, run services, create VM, call SQL/initdb, or access LS5/LS7.
No agent #2/#3/#4 or Codex-owned code is changed.

## CI evidence and acceptance boundaries (2026-10-19)

Draft PR #209 is based on `audit/codex-vm-test-attestation-20261016`.
The exact code revision `2b6e0e4dd0898df426562097357de877d19fcb0c`
passed eight GitHub Actions workflows after cancelled jobs in
`isolated-postgres-offline` (Windows/Python 3.11) and
`commissioning-manifest` were explicitly rerun. A cancellation is not a
PASS; both reruns eventually reported success.

The dedicated `contract-boundary-audit` workflow runs the standalone
adversarial test file on Windows and Linux with Python 3.11 and 3.12.
A successful workflow establishes only the result of those offline tests,
not authenticated provenance or guest safety.

### Explicit acceptance requirements for future integration

1. Validate the *original* signed evidence envelope against the intended
   plan, observer trust root, exact challenge and durable replay ledger.
   A copied `signature_result` field is never acceptable proof.
2. Bind VM identity, effective host principal, ownership session and
   PostgreSQL run/node/commit using independently verified sources;
   never equate an ordinary string match with native OS identity.
3. Reject every missing, contradictory or stale authorization fact.
   `VALIDATED_PLAN_ONLY`, `SYNTHETIC_ONLY` and
   `VERIFIED_PUBLIC_TEST_FIXTURE` must never grant execution.
4. Preserve `BLOCKED`, `execution_authorized=false`,
   `physical_ready=false`, `readiness_passed=false`,
   `schema2=false` and twelve `NOT_RUN/BLOCKED_UNPROVEN` guest
   cases until a separately reviewed real execution contract exists.
5. Require the independent negative CI gate and the other safety
   workflows before considering a reviewed integration. Green CI alone
   is insufficient for production deployment.

### Remaining blockers

The current checker exposes `trust_level=UNVERIFIED_METADATA_ONLY`,
`provenance_verified=false`, `replay_protection_verified=false`,
`cross_component_authority=false`,
`guest_execution_verified=false` and
`test_key_attestation_is_production_proof=false`. It does not
implement cryptographic report provenance, durable anti-replay or
physical execution. All are intentionally outside Agent #5's read-only
audit scope and must remain blocked.


## Codex five-PR P2 R6 integration checkpoint — 2026-10-19

Independent reproduction: [Issue #203 comment 6273850727](https://github.com/YehorBabenko88/bybit-cluster-grid/issues/203#issuecomment-6273850727); coordinator acceptance: [Issue #208 comment 6273913185](https://github.com/YehorBabenko88/bybit-cluster-grid/issues/208#issuecomment-6273913185).

The recursive schema-2 deny scanner rejects producer spellings
`schema2`, `schema2_enabled` (PR205), `schema_2_enabled` (PR206),
plus `schema2_active`, `schema_2_active`, `enable_schema2` and
`enable_schema_2`. Each explicitly present value must be the literal
boolean `false` at every nesting level. Numeric `0`/`1`, strings,
null, arrays/objects and contradictory mixed aliases all fail with
`CONTRACT_SCHEMA2_FORBIDDEN`. The two Codex reproductions are permanent
offline regressions, along with nested/type/multi-component negative cases.

### Explicit producer/consumer compatibility boundaries

| Producer | Metadata-only integration stance |
| --- | --- |
| PR204 Windows principal diagnostics | Frozen diagnostic data and `BLOCKED_UNPROVEN` are **not** native SID/token/ACL attestations and have no authorized direct input stage in this checker |
| PR205 PGDATA cross-contract | `BLOCKED` diagnostic is **not** the original `VALIDATED_PLAN_ONLY` PostgreSQL plan report accepted here; direct injection is refused |
| PR206 CI/JUnit and JSONL reader | Test receipts/PowerShell producer bytes cannot be used as execution evidence or substituted for a `postgres` stage report |
| PR207 test-key/replay model | Public test-key status and abstract checkpoint/anchor rollback are not durable anti-rollback, independent attestation or production approval; private `_challenge`/`_ROOTS` imported by this module require a reviewed stable public contract before integration |

Cross-PR composition is **not** authorization. The two identical
PR205/PR206 copied blobs require exact source-SHA provenance and review
on any future refresh. Native PGDATA ownership, principal isolation,
observer provenance and physical guest evidence remain unproven. In
particular, coordinated rollback of both PR207's checkpoint and anchor
allows modeled replay, so durable replay protection is **NOT IMPLEMENTED**.
Even synthetic `PASS` with two caller-supplied source labels returns
`BLOCKED` and twelve `NOT_RUN/BLOCKED_UNPROVEN` guest cases.

The offline audit/CI is not an executor. It must never normalize old
PGDATA layouts, manufacture adapter or observer credentials, authorize
schema-2, or change deployment/host state.
