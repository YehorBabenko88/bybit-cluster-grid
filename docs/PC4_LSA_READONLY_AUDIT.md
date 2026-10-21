# Independent LSA read-only audit for Draft #216

Date: 2026-10-21. Baseline: `b0d31eaaa2221da357ef6127fca3f0207c4248e2`.
Dedicated branch: `audit/lsa-failclosed-20261021`; stacked [Draft #223](https://github.com/YehorBabenko88/bybit-cluster-grid/pull/223)
targets the original [Draft #216](https://github.com/YehorBabenko88/bybit-cluster-grid/pull/216).
No merge, deployment, LS5/PC4 connection, native LSA execution, physical SID/ACL
test, or ACL/account/service/policy change was performed. Local work was source
inspection, Git operations, AST parsing, Python source contracts and synthetic
inventory providers. C# compilation/execution used disposable hosted CI only.

## Decision and severity

**GO for code review of the diagnostic fixes; NO-GO for CollectLocal/physical
execution. Effective logon rights remain UNKNOWN. Physical tests: 0/10 NOT_RUN.**

| Priority | Finding | Evidence and disposition |
|---|---|---|
| P0 operational blocker | Reported source staging is writable by `LS5\LS-5`; shared TEMP grants Modify to sandbox group and an unresolved SID. Elevated source compilation cannot trust these paths. | LS5 observations supplied by owner, not measured here. Protected staging design prepared; no provisioning. NO-GO remains. This is not a demonstrated privilege escalation exploit. |
| P1 | Inventory accepted two distinct SIDs both labelled GridLabCollector, omitting Storage without an error. | Synthetic regression failed on baseline; unique required names and canonical SIDs now enforced. |
| P1 | Inventory preserved partial candidates after provider failure; malformed group/member SID data could become candidate evidence or disappear during matching. Explicit nonterminating errors could be lost under permissive caller preferences. | Transactional discard on every error, provider stderr inspection, local Stop preference, group/member SID validation and duplicate-group rejection. 24 synthetic cases. |
| P1 | STATUS_SUCCESS with zero rights was labelled ENUMERATED/DIRECT_ONLY. This included a non-null buffer with zero count. | Microsoft documents success when at least one right is found. RED hosted regression; zero-count success now UNKNOWN/API_OR_DATA_ERROR. This was false direct enumeration evidence, not proof of effective logon access. |
| P2 fixed | Specialized CI omitted new branch's ref_name for manual workflow_dispatch. | Independent review caught it; both PR head_ref and manual ref_name now select offline jobs. Other inherited jobs retain their existing exclusions, extended to this audit branch. |
| P2 limitation retained | Cleanup collapses Free/Close errors/exceptions to CLEANUP_FAILED; Status/Win32Error describe the preceding Open/Enumerate result, and defaults can be zero after exceptions. | Correct fail-closed behavior already existed. Tests now cover combined failures and order. Do not interpret numeric zero without State/Code. Per-cleanup numeric provenance is not exposed; no result is promoted to success. |

No proven native write-API or effective-rights fail-open defect was found. The
native import allowlist and access mask were preserved; Get-LocalLogonRights.ps1
requires no code change. Changes do not retrofit security to untrusted sources.

## Complete branch disposition

| Boundary / input | Result | Resource behavior / evidence |
|---|---|---|
| Invalid/noncanonical/null SID | UNKNOWN, API_OR_DATA_ERROR, no rights | No Open call; five managed invalid-SID fixtures |
| Open nonzero NTSTATUS, including not-found | UNKNOWN, OPEN_FAILED | No enumeration; close any returned nonzero handle |
| Open succeeds with null handle | UNKNOWN, INVALID_HANDLE | No enumerate or close |
| Open/Enumerate throws after assigning outputs | UNKNOWN, API_OR_DATA_ERROR | Finally releases received buffer/handle |
| Enumerate success, 1..256 valid unique strings | DIRECT_ONLY, ENUMERATED | Copy managed names, free buffer, then close handle |
| Enumerate success with zero count, null buffer, oversized count, duplicate/malformed strings | UNKNOWN, API_OR_DATA_ERROR | Discard rights; release all received resources |
| Exact 0xC0000034, zero count, null buffer | DIRECT_ONLY, NO_DIRECT_ASSIGNMENTS | Convert status and close handle; still no effective-rights claim |
| Not-found plus nonempty/contradictory outputs | UNKNOWN, ENUMERATE_FAILED | Free returned buffer if present, close handle |
| Other error/warning/informational NTSTATUS, including integer 2 | UNKNOWN, ENUMERATE_FAILED | Only exact NTSTATUS selects absence branch; Win32 2 is not NTSTATUS not-found |
| Win32 conversion returns 0, 5, 317, or throws | Nonzero native status never becomes success; exception gives UNKNOWN/API_OR_DATA_ERROR | Primary status retained if returned; cleanup still attempted |
| Free/Close returns nonzero or throws, alone or together | UNKNOWN, CLEANUP_FAILED; no rights | Close attempted even if Free fails/throws; no retry/double free |
| Parse error plus cleanup failure / primary error plus cleanup failure | UNKNOWN, CLEANUP_FAILED; no rights | Primary numeric status remains, cleanup_failed=true; cleanup code takes precedence |
| Users/groups/members throws or emits explicit nonterminating error after records | Inventory error, all inventory candidates discarded | No partial snapshot accepted; fixed error text only |
| Empty group list / valid direct memberships | Candidate-only inventory; completeness UNKNOWN | Never proves complete nested/domain/dynamic/token groups |
| Conditional well-known SID after inventory error | Independent conditional candidate only | Collector retains inventory error; no reconstructed account membership |
| Default script invocation | PlanOnly, BLOCKED, no records | Returns before Add-Type, providers or NativeApi |

Parser checks counted UTF-16 length (nonzero/even/bounded), maximum length,
non-null string pointer, right-name syntax, embedded NUL and duplicate names.
It trusts OS-owned pointers: arbitrary invalid-address dereference, hostile
kernel memory and fatal process failures are outside this managed error model.
All resources received are released best-effort, not a guarantee that a failing
native cleanup freed them. Mock fixture memory is separately released by tests.

## Evidence matrix

| Assertion | Evidence | What it does not establish |
|---|---|---|
| Six baseline files matched pinned commit | Owner's supplied 6/6 SHA256/blob check; this audit independently checked out exact baseline and reviewed all six | Continued source custody or protected ACLs |
| PowerShell AST clean | Owner baseline: zero errors; hosted PS5.1/7 parsing on tested code | Runtime host compatibility or permissions |
| Regression detects old behavior | `c4b65d260401220f8b37f32c254452b14b765e48`, [RED run 39651083785](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/39651083785), both Windows PS5.1 steps fail MOCK_ASSERTION_FAILED at empty-success case; local synthetic duplicate-name check also RED | Physical LSA failure behavior |
| Fix/test commit | `94cebeeda0917a53b35bf870004715e1659bd3b7`, [GREEN run 39651528889](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/39651528889): all five jobs SUCCESS | Real host isolation |
| Native error/data/lifetime tests | 49 fake C# cases per PowerShell version per Windows Python 3.11/3.12 job | Native DLL execution against LSA; actual cleanup success |
| Inventory and PlanOnly | 24 synthetic provider cases +1 PlanOnly per PowerShell version per Windows job | Actual local identities, group completeness or tokens |
| Python inherited suite | 464 passed on each Ubuntu/Windows Python 3.11/3.12 job; four source contracts also pass on each | Physical SID/ACL evidence |
| Downloaded receipts verified | Four artifact event files bind SHA, exact collected/called node IDs and no bad reports; four JUnits match committed 464-case inventory; source JUnits contain four cases, zero errors/failures/skips | Cryptographic attestation of runner or PC4 |
| Existing physical package preserved | Source-contract SHA256 comparison of all seven pinned files at `1067b36e81e3ff613a68dd54d3dd186128666ab7`; 39 pure/mock policy cases per PS version per Windows job | Any of ten physical cases running |
| Static checks and compilation | Hosted actionlint, diff-check, PS parsing, DLL compilation and PS7 load pass | Compiler staging ACL isolation or a native invocation |
| Inherited workflow status | 15 unrelated workflows SKIPPED on fix head, not PASS. Initial RED head also triggered unrelated hosted checks; six cancellation requests issued, others completed/skipped | Whole-repository CI or release/deployment readiness |

The unrestricted repository-wide test command was deliberately not run locally:
the repository includes native ownership/adversarial tests and opt-in integration
paths outside this authorization. Verification uses the existing committed
offline inventory rather than invoking physical/native test suites.

## Remaining GO/NO-GO gates

1. Explicit separate authorization for any local LSA diagnostic or physical
   experiment. Neither these commits nor green CI supplies it.
2. Provision and independently verify the [protected Source/TEMP design](PC4_LSA_PROTECTED_STAGING_DESIGN.md),
   full exact SIDs, trusted separate operator, owner/DACL/ancestor custody,
   compiler search paths and protected evidence custody. Current reported paths
   remain NO-GO; no automatic remediation is included.
3. Owner review of required logon type and rights. Direct SeBatchLogonRight does
   not establish interactive logon; review applicable denies, actual token groups,
   service prerequisites and policy timing separately. Do not grant rights or
   start services as a workaround.
4. Real PC4 physical observations remain absent: 0/10 NOT_RUN. Mock success must
   never be entered into those ten physical cases. L1/L2 and human approvals remain
   separate gates; no host isolation, air-gap or effective-rights proof is claimed.
5. Accept possible Windows audit/profile/cache and compiler temporary writes
   under a future approved procedure. A literal zero-host-write requirement is
   incompatible with the present on-host compilation approach.

References: [enumeration contract](https://learn.microsoft.com/en-us/windows/win32/api/ntsecapi/nf-ntsecapi-lsaenumerateaccountrights),
[local policy access](https://learn.microsoft.com/en-us/windows/win32/api/ntsecapi/nf-ntsecapi-lsaopenpolicy),
[cleanup status contract](https://learn.microsoft.com/en-us/windows/win32/api/ntsecapi/nf-ntsecapi-lsafreememory).
No source changes to runtime, installer, database schema, physical harness or
previous PR branches. Rollback is reverting this dedicated branch's changes;
there is no provisioned host state to undo.
