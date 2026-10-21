# Separate local LSA diagnostic — preparation only

Physical tests: **0/10 NOT_RUN. Execute NOT_AUTHORIZED.** L1/L2 remain
NO-GO. This diagnostic neither runs nor approves the physical experiment.
The physical package and runbook pinned to
`1067b36e81e3ff613a68dd54d3dd186128666ab7` remain unchanged. This new source
directory is not a replacement for the pinned package or its manifest.

## Reported baseline and unresolved blocker

Coordinator comment 6322105451 reports a preparatory PlanOnly BLOCKED result,
enabled non-admin Collector/Storage accounts (RID 1003/1004), protected parent
DACLs, direct SeBatchLogonRight on both accounts, no direct local memberships,
and seclogon Stopped/Manual. These are owner-reported observations, not measurements
performed by this change. They supersede the earlier reported account state;
this change does not enable or otherwise modify either account.

The existing .NET ProcessStartInfo credential launch ultimately requires a
local interactive logon. SeBatchLogonRight alone does not establish
SeInteractiveLogonRight. Do not grant rights, start seclogon, change the launch
controller, or enable Execute to bypass this mismatch. The owner must separately
review logon type, required rights, applicable denies and service prerequisites.

## Future use, only after separate owner approval

Default (safe offline, no compilation, provider or native queries):

```powershell
powershell.exe -NoProfile -File .\lab\lsa-readonly\Get-LocalLogonRights.ps1
```

The following is a **future, NOT AUTHORIZED** diagnostic command, not an instruction
to run now. Use a fresh Windows PowerShell 5.1 x64 process from reviewed source in
a locally protected directory; verify its Git commit and hashes through a trusted
channel before any execution. Do not overlay the physical package directory.

```powershell
# Only after separate owner approval; local console, no remote execution.
powershell.exe -NoProfile -File .\lab\lsa-readonly\Get-LocalLogonRights.ps1 -CollectLocal
```

LSA lookup may require administrator access. That is a diagnostic reader token,
never evidence of an ordinary user's isolation. No credentials are accepted or
processes launched by the collector. Its only native imports are LsaOpenPolicy,
LsaEnumerateAccountRights, LsaNtStatusToWinError, LsaFreeMemory and LsaClose.
Policy opens locally (NULL SystemName), with POLICY_LOOKUP_NAMES (0x800), without
write access. SID bytes are managed/canonicalized and marshalled for the call;
LSA result memory and handles are released even on errors and parsing failures.
Cleanup failure invalidates the corresponding result. STATUS_OBJECT_NAME_NOT_FOUND
means no direct assignment, not an effective grant. Other failures stay UNKNOWN.
Only OS-owned LSA pointers are parsed; this is not a hostile kernel/pointer defence.

**Policy-read-only is not zero-write:** Add-Type compiles trusted source and may
create compiler temporaries; Windows can write auditing/cache data. Redirecting
stdout creates an output file by operator choice. No assertion of zero host writes
is made. Compilation and fake-API tests run only in disposable hosted CI here.

The reported writable LS5 source staging and shared TEMP are **NO-GO** for an
elevated diagnostic. Do not treat matching hashes as continuing source custody.
The [protected Source/TEMP design](PC4_LSA_PROTECTED_STAGING_DESIGN.md) specifies
future minimum ACLs, separate trusted operator identity, ancestor ownership,
reparse/path and compiler custody requirements. It is not provisioned or
physically verified by this change; no ACL changes are performed.

## Interpretation and privacy

The JSON report contains redacted aliases, direct relevant allows/denies, numeric
NTSTATUS/Win32 status and fixed error codes. It emits no full SID, SDDL, credential,
token or exception message. Group aliases are per-snapshot and cannot establish
identity continuity. Do not publish unreviewed real host output.

The collector queries both named local accounts, direct local group membership
and candidate well-known SIDs: Everyone, Authenticated Users, local-account
groups, Users/Administrators, Batch/Interactive/Network/Service/RemoteInteractive,
This Organization and Local/Console Logon. Conditional candidates are explicitly
not membership assertions. Get-LocalGroupMember can fail on unresolved members;
that failure is retained, never interpreted as an empty membership set. Windows
name resolution may consult configured identity providers; this is not an air-gap
or no-network guarantee. Do not run if those lookups are prohibited.

Inventory validation is transactional: duplicate account names/SIDs, invalid or
noncanonical SIDs, malformed groups/members, duplicate group identities and
terminating/nonterminating provider errors discard all inventory candidates and
emit a fixed inventory error. An empty group list still establishes no token
completeness. Conditional well-known candidate queries remain independent of
inventory and do not reconstruct either account's groups after inventory failure.
Successful LSA enumeration with zero rights is rejected as contradictory data;
only the documented not-found status with empty outputs reports no direct
assignments. No Win32 conversion (including zero) turns another NTSTATUS into
success. Cleanup failure always clears rights and sets UNKNOWN. Numeric status
fields describe the last returned Open/Enumerate result, not cleanup status;
zero alone is not proof that parsing, conversion or cleanup succeeded.

Nested/domain/dynamic/logon-specific/deny-only/restricted groups and a future
actual token are not exhaustively established. Queries are separate snapshots,
not an atomic policy/token view; policy could change before launch. A candidate's
deny is a diagnostic finding, not proof it applies to either future token. No
direct deny does not prove no effective deny. `effective_rights=UNKNOWN`,
`group_completeness=UNKNOWN`, `readiness=BLOCKED` and
`execution_authorized=false` are invariant, even on successful enumeration.
No attestation, replay protection, air-gap proof or SID/ACL isolation proof results.

## Offline evidence and remaining decisions

Mandatory CI: four Python source-contract tests (including pinned package byte
comparison), 49 fake LSA/parser/lifetime cases, 24 fake group inventory cases,
and one PlanOnly case on each Windows PowerShell 5.1/PowerShell 7 runner. Existing
464 Python and 39-per-version physical-package policy checks remain intact.
No mock case queries local LSA or tokens; fake buffers are freed separately by
the fixture, including simulated LsaFreeMemory failures. Hosted compilation is
not validation against a real policy. A physical test count cannot increase here.

Before future physical work the owner needs: independently verified complete local
identities and group/token/logon-right evidence, review of all applicable logon
denies, an approved service/logon prerequisite plan, protected diagnostic sources,
private evidence custody, a separately approved account/experiment plan, and explicit
authorization. No ACL/policy/account repair or cleanup is implemented. Rollback of
this development change is reverting its commit; no host state was provisioned.

See [independent audit and evidence matrix](PC4_LSA_READONLY_AUDIT.md) for severity,
error-branch disposition, exact tested commits and remaining GO/NO-GO gates.

References: [LsaEnumerateAccountRights](https://learn.microsoft.com/en-us/windows/win32/api/ntsecapi/nf-ntsecapi-lsaenumerateaccountrights),
[LsaOpenPolicy](https://learn.microsoft.com/en-us/windows/win32/api/ntsecapi/nf-ntsecapi-lsaopenpolicy),
[CreateProcessWithLogonW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createprocesswithlogonw).
