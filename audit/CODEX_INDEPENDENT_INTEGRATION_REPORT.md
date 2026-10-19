# Independent integration and security audit — 2026-10-19

## Verdict and scope

**BLOCKED_UNPROVEN.** No production authorization bypass was demonstrated in the reviewed implementation. This is source/offline evidence, not proof of physical isolation. Readiness and execution remain false, schema 2 remains disabled, and all 12 physical VM cases remain NOT_RUN. No VM, PostgreSQL server, initdb, service, deployment, production, LS5 or LS7 operation was performed by this audit.

PR #206 was fetched directly from GitHub before creating the independent branch. Base: `bcc06ecdb900e29a4f0d65786b300e90397c11fc` (the requested historical base `5d18b2810a8b1b22ce59e46334d35e07f55c46c7` was not substituted for the PR head). Reviewed and locally tested implementation SHA: `6ba42df4ca845abd060da7655bb990bd94add098`. Later documentation commits do not change this implementation; their CI evidence must still be checked separately.

Pinned comparison refs fetched with the clone:

| Branch | SHA |
|---|---|
| parallel/vm-principal-isolation-20261019 | cb9db5b6594d4f831b2e5436df1965cc32db9d0a |
| parallel/postgres-adapter-contract-20261019 | 635e133f9cafea1cdaeeae6288c11fba5f3c6057 |
| parallel/integration-ci-audit-20261019 | bcc06ecdb900e29a4f0d65786b300e90397c11fc |

Three independent agents reviewed VM, PG ownership, and CI boundaries. Parent reviewed changes and independently reran tests. No AGENTS.md was found in the repository.

## Findings and disposition

Severity concerns assurance and integration decisions; none of these findings demonstrates authorized physical execution.

| Severity | Finding and evidence | Disposition |
|---|---|---|
| High | `workflow_attestation.assess([], sha, required=frozenset())` bypassed all mandatory workflow coverage and returned CI_VERIFIED_ONLY. | Fixed: the required set cannot be changed. Negative regression test added. |
| High | Caller-authored dictionaries could obtain CI_VERIFIED_ONLY without authenticated GitHub provenance, run/attempt identity or individual job execution checks (`audit/integration_ci/workflow_attestation.py`). A successful aggregate run can contain skipped critical jobs. Manifest source and synthetic flags are also assertions. | Renamed to CI_METADATA_ONLY; explicit provenance/job blocker in integration report and documentation. Trusted collector and required-job policy remain absent: do not use these functions as security authority. |
| Medium | Missing, empty or nonstring ownership sessions compared equal in `cross_contracts.py`; no actual attestation/session binding was established. | Fixed nonempty string validation; negative cases cover None, empty string, list and integer. Equality is still model-only, not authenticated runtime binding. |
| Medium | Both workflow and manifest checks accepted nonhex 40-character SHA values. | Fixed lowercase hexadecimal validation and negative tests. |
| Medium | Unhashable VM IDs and workflow names raised TypeError instead of explicit denial. | Fixed validation ordering/type checks; negative tests. |
| Medium | Branch path checker allowed Windows traversal, drive paths, actual NUL and noncanonical aliases. | Fixed canonical relative slash-path validation; five negative path cases. This checker remains path-only and does not prove semantic compatibility. |
| Medium | Parallel PG cross-contract expects fabricated journal fields (`installer/pgdata_cross_contract.py:25` on pinned PG branch). Actual `Get-GridLabRecord` emits schema/plan_sha256/state JSONL (`installer/isolated-deployment-core.ps1:99`). It also omits commit/digest/freshness/transition binding. | Integration blocker reported; other branch left untouched. Requires tests with actual bounded journal bytes, not invented dictionaries. Unconditional BLOCKED prevents promotion. |
| Medium | Actual adapter root is RUN_NODE with postgres/data; PG schema-1 expects RUN/NODE/pgdata (`isolated-deployment-core.ps1:22`, `isolated_postgres_plan.py:43`). | Existing safe refusal retained; no automatic layout mapping introduced. |
| Medium | Parallel VM auxiliary model lacks declared-versus-actual SID comparison and dedicated elevated/group rejection (`vm_principal_lab/offline_principals.py:36`); completeness accepts arbitrary nonempty field values (`evidence_completeness.py:24`). | Branch-only diagnostic gaps reported, not changed. Both retain BLOCKED_UNPROVEN and false authority. |
| Medium | Integration workflow default checkout could test a PR merge SHA while evidence was labeled with head SHA. | Explicit head-SHA checkout added; credentials persistence disabled. Other workflows already select head explicitly. |
| Low | Invalid attestation input omitted explicit readiness/execution denial fields. | Fixed and tested. |

No Critical finding established. High residual risk is false confidence in untrusted evidence, not a discovered deployment capability.

## Actual contracts examined

- `vm_lab_plan.py:78` requires PlanOnly, PreserveOnly and schema2=false. Lines 113–138 validate declared role/SID separation and return BLOCKED, false readiness/execution and 12 NOT_RUN. Actual token/ACL observations are not claimed.
- `vm_lab_evidence.py:35` reconstructs expected draft, refusing forged facts even after rehashing. Hash integrity is explicitly not authentication.
- `vm_test_attestation.py:14` pins public synthetic roots; lines 64–91 enforce challenge, bounded validity, both signatures, then process-local nonce/sequence consumption. Ledger resets across processes; caller supplies time/challenge. Lines 92–94 explicitly deny real authority and durable replay protection. Signed fixture tests establish test-key behavior only.
- `isolated_postgres_preflight.py:27` checks serialized snapshot commit/digest/run/node/path/age, but snapshots are unauthenticated. Lines 74–75 unconditionally reject schema 2. `isolated-ownership-contract.ps1:8` and `:60` retain BLOCKED for even matching journal bytes.
- `ownership_session.py:1` and `:178` describe synthetic session fixtures. They are not a production PGDATA capability. `ownership_threat_boundary.py:25` documents ACL replace/restore limitations.
- Comparison of the three parallel branches found incompatible real APIs despite nonoverlapping file paths. Main VM modules are identical on the VM branch; newly added auxiliary models are not integrated enforcement.

## Verification

Local CPython 3.12, isolated audit venv, pytest 9.1.1 and hash-pinned binary cryptography 50.0.2/cffi/pycparser from the repository test lock:

```text
python -B -m pytest -q -p no:cacheprovider --basetemp=../audit-parent-tmp
  tests/test_vm_lab_plan.py tests/test_vm_lab_evidence.py
  tests/test_vm_lab_robustness.py tests/test_vm_test_attestation.py
  tests/test_isolated_postgres_plan.py tests/test_isolated_postgres_preflight.py
  tests/test_isolated_postgres_mapping.py tests/test_isolated_ownership_contract.py
  tests/test_ownership_session_prototype.py tests/test_ownership_threat_boundary.py
  tests/test_ownership_adversarial_model.py
355 passed (GRID_REQUIRE_TEST_ATTESTATION=1; no skips)

python -m unittest discover -s tests -p 'test_integration_*.py' -v
35 passed
```

Seven new boundary test methods first reproduced four failures and two errors, with five failing path subcases; all pass after correction. Original passing tests were retained; only the misleading CI label expectation was updated.

Windows PowerShell 5.1 and PowerShell 7 each passed these seven reviewed offline wrappers: test-vm-lab-plan, test-vm-lab-evidence, test-isolated-postgres-readonly (32 mocked cases), test-isolated-ownership-contract (60 in-memory checks), test-ownership-session-prototype (10 model cases), test-ownership-threat-boundary (14 blocked rows), test-vm-test-attestation. No Native switch or host provider was used. Earlier agent runs lacked crypto or encountered temp-directory permission failures; the independent final run used pinned crypto and a workspace basetemp and supersedes those incomplete runs.

Local Python 3.11 is unavailable. It is tested only by the dispatched GitHub matrix, subject to checking actual job completion. Full project suite and service-backed integration tests were deliberately not run.

## GitHub Actions evidence

Baseline exact SHA bcc06ec has eight historical completed-success runs fetched read-only: commissioning 39273268420; composed 39273268306; integration 39273268337; isolated PG 39273268219; synthetic physical harness 39273268398; preflight 39273268256; Windows commissioning 39273268510; bundle 39273268223. These are historical runs, not launched by this audit and not physical VM proof. Historical integration jobs 118130865555/118130866083 match the SHA and succeeded. Other historical individual jobs were not exhaustively authenticated.

Audit implementation run: [39274400345](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/39274400345), workflow_dispatch, exact SHA 6ba42df4ca845abd060da7655bb990bd94add098. Final job conclusions are recorded in the PR/issue follow-up after API verification.

All audit commits use [skip ci] to prevent PR-triggered service/installation workflows prohibited by this assignment. Only integration-evidence-audit is explicitly dispatched; it installs Python and runs offline unittest checks. No gate YAML is removed, weakened or marked PASS. The remaining workflows are UNVERIFIED on this branch, and the required-check suite must not be interpreted as complete. Cancelled, queued and skipped runs are not successful evidence.

Observed historical Windows commissioning workflow name is `.github/workflows/windows-commissioning.yml`, whereas metadata fixtures use `windows-commissioning`. Resolve workflow identity using trusted workflow ID/path in any future collector; do not silently normalize caller strings to PASS.

## Integration recommendations and blockers

1. Incorporate the validation fixes and metadata-only status deliberately into PR #206; external consumers of CI_VERIFIED_ONLY must migrate. No merge performed.
2. Keep physical readiness blocked pending independently authenticated actual SID/token/ACL evidence, protected durable anti-replay state and trusted freshness/approval roots.
3. Replace invented PG journal/adapter envelopes with contract fixtures generated by the real PowerShell producer; require exact commit/plan digest, legal journal transitions, session lifetime and read-only mapping. Never convert synthetic session equality into authorization.
4. Build a read-only trusted GitHub collector that binds repository, workflow ID/path, event, exact source SHA, run ID/attempt and all required jobs/matrix members. Treat missing/skipped/cancelled jobs and stale evidence as blocked.
5. Preserve source scanners as heuristics only. No obfuscation resistance, complete static safety proof, live PostgreSQL contract, real VM principal isolation or production scenario was established.

Final invariant: status=BLOCKED_UNPROVEN; readiness_passed=false; execution_authorized=false; schema_2_enabled=false; physical_vm_cases=12; every physical_vm_case_status=NOT_RUN.

Verified implementation run outcome: 39274400345 completed-success. Both actual jobs completed-success: 118134814781 (Python 3.12), 118134815552 (Python 3.11); exact API head_sha 6ba42df4ca845abd060da7655bb990bd94add098. Independent fresh review found no actionable regression and reproduced original boundary failures by loading base modules. Final documentation-head rerun is tracked in PR/Issue #203 rather than claiming the implementation run covers a different SHA.
