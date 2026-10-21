# LSA JSON consumption contract — diagnostic review only

Baseline: Draft #223, `a2cff9b81bb460a022df785586fc2c300c99590e`.
This contract adds no actor, logon, deployment or physical execution path.
Physical tests **0/10 NOT_RUN**. Execute **NOT_AUTHORIZED**.

## Existing consumers and scope

An exact, case-sensitive search of every tracked text file at baseline found:

| Search term | Matches / files | Meaning |
|---|---|---|
| `grid-lsa-readonly-1` | 1 / 1 | Producer schema literal in Get-LocalLogonRights.ps1 |
| `effective_rights` | 4 / 4 | Producer, PlanOnly smoke assertion, source-contract assertion, interpretation documentation |
| `direct_allow` | 1 / 1 | Producer serializes filtered direct assignments |
| `NO_DIRECT_ASSIGNMENTS` | 4 / 3 | C# Reader result, C# mock expectations, diagnostic documentation |
| `execution_authorized` | 286 / 112 | Shared spelling in many unrelated plan/evidence schemas, tests, docs and retained artifacts |

Producer-path searches (`Get-LocalLogonRights`, `lsa-readonly`, `LsaRights`,
`LsaReadOnly`) additionally trace specialized workflow calls, source tests and
the C# build/mock chain. No consumer of LSA JSON that authorizes physical work
was found. This is a repository-scope conclusion, not a claim about external
scripts or humans who might read exported files.

The existing JSON consumer is `lab/lsa-readonly/Test-Offline.ps1:75-79`:
it parses **its own freshly generated PlanOnly** output and checks a subset of
invariants. It is a smoke assertion, not an untrusted-report validator or a
physical gate. Its truthiness check of execution_authorized alone is not a
general exact-boolean check; it must not be reused for untrusted input. New CI
also passes the actual PlanOnly JSON through the strict validator on PS5.1/7.

`Get-LocalLogonRights.ps1:45-52` consumes managed Reader results before JSON
serialization; it does not consume external JSON. MockTests.cs verifies Reader
states; tests/test_lsa_readonly.py reads source, rather than consuming reports.
The physical controller reads its own manifest/launch/PID/token/actor records;
it has no LSA report input. `installer/pc4_sid_acl_evidence.py` expects its own
strict ten-record JSONL schema and rejects an LSA report, ten repeated LSA
reports, and the new validator's result, even with a matching supplied hash.

Other validators (`audit/integration_ci/evidence_gate.py`, cross_contracts.py,
`installer/contract_boundary_audit.py`, pgdata_cross_contract.py,
vm_principal_lab/readiness_audit.py) handle separate VM/PGDATA/integration
schemas and preserve their own blocked authority fields. Common field spelling
does not make them LSA consumers. No integration into those validators is added.
The complete baseline match inventory is exported with the audit receipts.

## Offline interface

`installer.lsa_report_contract.validate(raw: str) -> dict` accepts JSON text.
The CLI reads bounded UTF-8 stdin without BOM, writes one fixed JSON review result to stdout,
and returns 0 for admitted diagnostic metadata, 2 for rejection. No input path,
credentials, host query or execution option exists. It reuses the existing pure
`installer.vm_lab_json.load` parser, without modifying it.
PowerShell native pipelines must explicitly use `System.Text.UTF8Encoding(false)`
for this CLI; PS5.1 UTF8Encoding with a preamble can prepend BOM bytes. This is
a process-local transport setting, not a policy/ACL/host configuration change.
UTF-16 redirected files and BOM-prefixed input are rejected, never guessed or
silently normalized.

For an already-reviewed offline UTF-8 report, `python -m
installer.lsa_report_contract` reads stdin. CLI exit 0 and `contract_valid=true`
mean **only admission under this strict consumption profile**. They never mean
GO, effective rights, authenticated provenance or successful physical tests.
Do not route this exit code to an executor or physical JUnit renderer.

The result is always:

```json
{"schema":"grid-lsa-contract-review-1","status":"BLOCKED",
 "contract_valid":true,"code":"LSA_DIAGNOSTIC_ONLY",
 "evidence_class":"UNAUTHENTICATED_DIAGNOSTIC_ONLY",
 "effective_rights":"UNKNOWN","execution_authorized":false,
 "readiness_passed":false,"physical_attestation":false,
 "physical_tests":"0/10 NOT_RUN","physical_passes":0}
```

Rejection changes only `contract_valid` to false and code to
`LSA_CONTRACT_REJECTED`. No untrusted field, exception text, SID or right list
is echoed into the result. This output has a different schema and is not a new
LSA input report or a physical evidence record.

## Strict input profile

All fields below are required; unknown fields are rejected at every object
level. Exact spellings/case apply. Duplicate keys (including nested keys),
trailing JSON documents, nonfinite numbers, invalid Unicode, nonobjects and
budgets exceeded are rejected. Parser limits are 65,536 UTF-8 bytes, depth 24,
4,096 nodes, 256 elements per container and bounded strings/numbers. CLI reads
at most 65,537 bytes to detect overflow. This profile may reject unusually large
legitimate producer reports; no truncation or silent partial acceptance occurs.

| Top field | Required value/type |
|---|---|
| schema | `grid-lsa-readonly-1` |
| mode | `PlanOnly` or `CollectLocalReadOnly` |
| readiness | `BLOCKED` |
| effective_rights | `UNKNOWN` |
| execution_authorized, actor_token_observed | Literal JSON false, never 0/null/string |
| physical_tests | `0/10 NOT_RUN` |
| group_completeness | `UNKNOWN` |
| errors | Empty array |
| records | Array; empty in PlanOnly |

CollectLocalReadOnly requires at least 16 records (two accounts plus fourteen
known SID candidates in this producer), no more than 256 subject to the parser
budget, distinct aliases and exactly the two LOCAL_ACCOUNT aliases
GridLabCollector/GridLabStorage. CONDITIONAL_CANDIDATE aliases must be one of
the producer's fourteen known aliases. DIRECT_LOCAL_GROUP aliases must match
`local_group_N`, canonical decimal N >= 2. Direct groups may replace conditional
aliases for the same SID; redaction prevents reconstructing that mapping.

Every record requires exactly principal, relation, state, code, ntstatus, win32,
cleanup_failed, direct_allow and direct_deny. Admitted state is DIRECT_ONLY and
cleanup_failed must be literal false. Rights are distinct strings from the five
relevant logon allows or five denies respectively; each array has at most five.
Both allow and deny may coexist as direct policy findings. No aggregation,
membership inference or allow-minus-deny calculation is performed.

| Code | NTSTATUS / Win32 | Rights |
|---|---|---|
| ENUMERATED | `0x00000000` / integer 0 | Relevant arrays may be empty: native enumeration can contain unrelated privileges |
| NO_DIRECT_ASSIGNMENTS | `0xC0000034` / integer 2 | Both arrays empty |

UNKNOWN state, unknown code, OPEN_FAILED, ENUMERATE_FAILED, INVALID_HANDLE,
API_OR_DATA_ERROR and CLEANUP_FAILED are all rejected for consumption. Rejection
does not assert that the producer report is fabricated: it may correctly report
an error. Nonempty errors, cleanup failures and partial inventories remain
blocked and cannot be rehabilitated by other successful records. Primary
NTSTATUS zero does not override a parse/cleanup error. Numeric Win32 values must
be exact integers, not booleans, in the uint32 range.

## Non-provable properties and GO/NO-GO

No timestamp, machine identity, actor token, signature or provenance binding is
present in this schema. A mock can reproduce every admissible byte. An omitted
membership or policy fact cannot always be detected in a redacted fabricated
snapshot. Count/name checks catch observable partial inventories but never prove
actual completeness. An attacker can change an error payload into an apparently
valid one; the output still grants nothing. The validator must not become an
authenticator or an authorization adapter.

| Situation | Diagnostic admission | Physical / Execute |
|---|---|---|
| Valid PlanOnly | Yes, shape/invariants only | NO-GO / NOT_AUTHORIZED |
| Consistent direct allows/denies or no-direct-assignment report | Yes, unauthenticated diagnostic only | NO-GO / NOT_AUTHORIZED |
| Valid-looking synthetic/mock with no origin label | Indistinguishable; always unauthenticated | NO-GO / NOT_AUTHORIZED |
| Missing/unknown fields, contradictory states/statuses, errors, cleanup failure, observable partial inventory | Reject | NO-GO / NOT_AUTHORIZED |
| Explicit mock-to-physical PASS/authorization fields | Reject unknown/promoted fields | NO-GO / NOT_AUTHORIZED |
| Green CI and all mocked cases | Software evidence only | 0/10 NOT_RUN; NO-GO |

Separate owner authorization, protected Source/TEMP/evidence custody, complete
host/logon/token/deny review, existing L1/L2 gates and future physical evidence
remain unresolved. This validator neither provisions these prerequisites nor
changes the diagnostic producer, read-only LSA API, physical harness or previous
PR branches. Offline JUnit records software test outcomes, never physical PASS.
