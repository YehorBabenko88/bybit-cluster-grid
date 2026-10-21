# Independent LSA JSON consumer audit

2026-10-21; baseline Draft #223: `a2cff9b81bb460a022df785586fc2c300c99590e`.
Dedicated branch `audit/lsa-json-contract-20261021`, stacked [Draft #224](https://github.com/YehorBabenko88/bybit-cluster-grid/pull/224).
Original #216/#223 branches unchanged. Physical **0/10 NOT_RUN**, Execute
**NOT_AUTHORIZED**. No CollectLocal, native LSA calls, LS5/PC4 connections,
physical SID/ACL tests, account/ACL/service/policy changes, merge or deployment.

## Consumer findings

All tracked baseline text files, including hidden workflows, docs, tests and
retained artifacts, were searched for the five requested literals and for the
producer/type paths. Counts: schema 1 match/1 file, effective_rights 4/4,
direct_allow 1/1, NO_DIRECT_ASSIGNMENTS 4/3, execution_authorized 286/112.
The complete baseline match inventory is exported as JSON with file/line/text.
Reproduce with `git grep -n -I -F -e grid-lsa-readonly-1 -e effective_rights
-e direct_allow -e NO_DIRECT_ASSIGNMENTS -e execution_authorized
a2cff9b81bb460a022df785586fc2c300c99590e -- .`.

| Existing location | Actual role | Authority behavior |
|---|---|---|
| lab/lsa-readonly/Get-LocalLogonRights.ps1:7-11,45-52 | Produces LSA JSON; consumes managed C# Reader results before serialization | Always BLOCKED, UNKNOWN, execution false; no actor launch |
| lab/lsa-readonly/Test-Offline.ps1:75-79 | Parses its own newly produced PlanOnly JSON and applies a subset smoke assertion | Not an untrusted-input validator, no physical launch |
| lab/lsa-readonly/LsaRights.cs:80 and MockTests.cs:51,67 | Managed result code and internal tests | Not JSON report consumers |
| tests/test_lsa_readonly.py | Reads source contracts | Does not consume external diagnostic JSON |
| .github/workflows/pc4-sid-acl-offline.yml | Invokes hosted compilation/mocks and default PlanOnly | No CollectLocal or native/physical entry point |
| lab/pc4/Invoke-Pc4SidAcl.ps1 | Separate physical controller with its own manifest/PID/token/actor formats | No LSA report input or reference |
| installer/pc4_sid_acl_evidence.py | Strict separate ten-record physical-format parser, unauthenticated | LSA JSON, repeated mock JSONL and validator output all rejected, zero reported passes |
| Other execution_authorized matches | VM/PGDATA/integration/publication schemas, invariant producers, validators, tests/docs/artifacts | Shared key spelling does not imply LSA ingestion; no LSA execution adapter found |

No existing consumer that promotes LSA report data to physical authorization was
found. The finding is limited to this repository and baseline: outside scripts
or human interpretation cannot be enumerated from the repository.

## Proven defects, gaps and disposition

| Priority | Proven finding | Action |
|---|---|---|
| P0/P1 | No demonstrated production authorization bypass or physical promotion path | No speculative edits to physical controller or unrelated consumers |
| P2 | Existing PlanOnly smoke guard uses PowerShell truthiness for execution_authorized; a synthetic numeric 0 passes that guard | Reproduced by extracting/evaluating only its AST condition with synthetic JSON. New validator requires literal false; negative test pins rejection of 0/null/string. Specialized CI applies the validator to the actual PlanOnly JSON on PS5.1/7. Existing smoke script remains unchanged and is explicitly not a general validator |
| P2 | No standalone versioned LSA JSON consumption boundary/specification; source/managed mocks did not test hostile JSON combinations | Added strict standalone offline validator, formal profile and pinned negative test inventory |
| Inherent limitation | Valid-shaped mock and host JSON are byte-indistinguishable; redacted aliases cannot prove actual membership completeness | Output always UNAUTHENTICATED_DIAGNOSTIC_ONLY/BLOCKED, no authority, no verified physical pass; documented instead of inventing attestation |

The local RED test demonstrated the new CLI was absent; it was a missing feature,
not evidence of an existing production exploit. Local test development also hit
Windows environment-size errors from oversized parametrized IDs; fixed by short
explicit test IDs. Final local scoped suite: **575 passed**, no skips/failures.

## Implementation and negative evidence

`installer/lsa_report_contract.py` reuses only the existing bounded pure JSON
parser and standard library. It accepts bounded UTF-8 JSON from stdin, emits a
new review schema and exit 0 only for admissible diagnostic metadata, exit 2 for
rejection. CLI success and contract_valid=true never mean GO. No file input
paths, writes, processes, host/network/native calls, physical harness imports or
execution option are present. No generic downstream schemas were modified.

Exact required keys, case-sensitive schema/enums, duplicate-key rejection,
literal booleans, empty errors, record alias uniqueness, observable inventory
requirements, uint32 Win32 types and NTSTATUS/code consistency are enforced.
UNKNOWN records, cleanup failures, missing fields, extra/promotional metadata,
malformed arrays and fabricated physical PASS fields are rejected. Relevant
empty right lists remain valid with ENUMERATED because unrelated native
privileges are filtered by the producer. No-direct-assignment requires its exact
not-found status, mapped error 2, no cleanup failure and empty right lists.

All outputs, including admissible direct grants/denies, no-direct-assignment,
PlanOnly, errors and valid-looking mocks, hardcode execution_authorized=false,
readiness_passed=false, physical_attestation=false, physical_passes=0,
physical_tests="0/10 NOT_RUN", effective_rights="UNKNOWN" and status="BLOCKED".
No allow-minus-deny or token-membership inference is implemented.

The new tests cover **107 cases**: missing top/record fields, unknown schema and
state/code, numeric/null authority flags, inconsistent primary statuses, all five
UNKNOWN error branches, cleanup/rights contradictions, partial inventory,
duplicates, malformed JSON/Unicode/bounds/nonfinite values, nested duplicate
keys, mock laundering, legitimate aliases/direct groups/filtered privileges and
PlanOnly compatibility. Three negative tests exercise the existing pure physical
format parser without invoking any physical harness. A byte comparison verifies
all twelve tracked LSA/physical source and parser files unchanged from #223.

## Verification, commits and CI evidence

Implementation/test commit: `2a97bc2e07eb0afa5d9f610e8baa72405ae4c85a`.
The initial [CI run 39654073586](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/39654073586)
passed the Python contract suite on all four matrix jobs but failed PS5.1
PlanOnly-to-CLI transport. A local PlanOnly-only reproduction showed that PS5.1
UTF8Encoding with a preamble sends `efbbbf` before JSON; strict parsing correctly
rejects it. Explicit UTF8Encoding(false) fixed that local transport case but
[run 39654585419](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/39654585419)
still rejected the hosted PS5.1 input, so BOM was not established as the hosted
failure's cause. Limited byte-prefix/type diagnostics were added to investigate
the actual boundary rather than relaxing validation. BOM-prefixed input remains
in the negative inventory. Both CI failures are preserved in the final evidence;
neither produces authorization or physical evidence.

Specialized CI adds exact-head checks, separate `lsa-contract.xml` and
`lsa-contract-events.json` receipts. Events must match the committed 107-node
inventory and actual successful call identities; JUnit must match every expected
case with zero errors/failures/skips/xfail. Ubuntu/Windows Python 3.11/3.12 each
run that suite, the original 464-case inventory and four source contracts.
Both Windows jobs also test actual default PlanOnly JSON through the CLI on
PS5.1/7, retaining 49 C# fake API cases, 24 synthetic inventory cases, PlanOnly,
39 physical-package pure/mock policy cases, parsing and hosted-only compilation.
Fifteen inherited workflows are intentionally SKIPPED, never counted as PASS.
Only branch-selection exclusions are extended outside specialized CI.

The exported final report includes exact final HEAD, run links, downloaded
receipt verification and their hashes after CI completes. Full local unrestricted
pytest is intentionally not run: native ownership/physical/integration tests are
outside authorization. The 575-case scoped suite uses the committed offline
inventory plus the new contract/source tests.

## GO/NO-GO matrix

| Evidence / action | Decision | Reason |
|---|---|---|
| Offline strict JSON admission and software tests | GO for diagnostic/code review only | Format and blocked-state invariants; no provenance |
| Consistent direct allow/deny/no-direct-assignment | NO-GO for effective logon conclusions | Candidate groups and direct policy are not a complete future token |
| Missing/contradictory fields, errors, unknown state, cleanup failure, partial snapshot | Reject diagnostic admission; physical NO-GO | No partial success or numeric-zero override |
| Mock success, green JUnit or validator exit 0 | Physical NO-GO, 0/10 NOT_RUN | Cannot authenticate a host or synthesize physical evidence |
| CollectLocal on LS5/PC4 | NOT_AUTHORIZED / NO-GO | Explicit user prohibition; protected staging and host review unresolved |
| Physical execution, rights/ACL/service repair, merge/deploy | NOT_AUTHORIZED | Separate approvals and original L1/L2 gates remain required |

Read [the formal profile](PC4_LSA_REPORT_CONSUMPTION_CONTRACT.md) for full input,
output, parser budgets, observable partial-inventory checks and non-provable
properties. No automatic execution adapter is created. Rollback is reverting
this dedicated branch's changes; no host state was provisioned.
