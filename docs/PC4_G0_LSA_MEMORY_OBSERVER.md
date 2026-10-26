# PC4 G0 SID-bound native LSA observer

Scope: preparation and policy-read-only observation only. Physical SID/ACL harness0/10NOT_RUN. G1Execute/CleanupNOT_AUTHORIZED. DeploymentNO-GO. Effective rights and group completeness alwaysUNKNOWN; readinessBLOCKED even after a successful direct policy read.

## Safety and source trust

The old Get-LocalLogonRights.ps1 CollectLocal path compiles with Add-Type and is NOT the new memory-only path. Do not invoke it on PC4 for this task. Build-G0Memory.ps1 compiles reviewed LsaRights.cs+SidBoundReader.cs only on the development workstation or disposable hostedCI; build/test scripts explicitly refuse PC4. The production DLL contains no test providers. The memory entry accepts no passwords, creates no tokens, performs no logon, modifies no accounts/policies/DACL/services/network/PG and makes no explicit filesystem writes. Native imports are restricted to System32 advapi32's LsaOpenPolicy(POLICY_LOOKUP_NAMES=0x800), LsaEnumerateAccountRights, LsaFreeMemory, LsaClose and LsaNtStatusToWinError. No privilege escalation or alternate provider fallback.

A supplied DLL and supplied matching hash are NOT independent authentication. Before any CollectMemory invocation an independent verifier must acquire the exact-head workflow/artifact metadata through authenticated GitHub access, verify the original ZIP digest, source blobs, production DLL hash and all required tests. Pin the approved source and binary digests outside the transmitted payload. Do not derive trust only from an accompanying manifest or from a caller-chosen head. If that gate is missing, collection remains BLOCKED/NOT_RUN. Assembly loading can execute managed initializers, so unreviewed arbitrary bytes MUST NOT be passed.

Read-G0LsaMemory.ps1 defaults to PlanOnly, with no assembly load, SAM query or LSA calls. CollectMemory additionally requires G0Approved, Windowsx64 PC4, a40hexsourcehead/32hexrunID, a64hex independent production DLL pin and BOTH exact canonical local account name/SID matches before loading the assembly. Never identify accounts by RID suffix alone. A fresh NoProfile PowerShell process and explicit OS module path avoid PATH/PSModulePath discovery. No -UseWindowsPowerShell compatibility process is launched.

Windows/SSH/CLR may perform ordinary auditing/cache activity; no claim of literally zero OS disk writes is possible. The observer itself has no output-file/temporary compiler/provisioning operations on PC4. Evidence is captured by the originating workstation from stdout; do not redirect it to a PC4 file.

## Rights and failure interpretation

For each pinned account query all direct assignments and explicitly map:

- SeInteractiveLogonRight / SeDenyInteractiveLogonRight
- SeRemoteInteractiveLogonRight / SeDenyRemoteInteractiveLogonRight
- SeNetworkLogonRight / SeDenyNetworkLogonRight
- SeBatchLogonRight / SeDenyBatchLogonRight
- SeServiceLogonRight / SeDenyServiceLogonRight

ASSIGNED_DIRECT and NOT_DIRECTLY_ASSIGNED describe only direct policy entries, never a grant/absence of effective deny. Groups, deny-only/conditional/logon-specific SIDs, actual tokens, policy races and domain policy are not fully resolved. No direct deny does not establish logon capability. PasswordRequired=False does not prove a blank password; missing LastLogon does not prove no historical use. No logon/password attempt is performed.

STATUS_OBJECT_NAME_NOT_FOUND is accepted as no direct assignments only with count0/bufferNULL and Win32error2. AccessDenied, bad status/string/buffer shape, SID/name mismatch, missing identities, incomplete enumeration, cleanup failure and unsupported right names remain UNKNOWN/BLOCKED. Zero-count/non-null buffer was independently reproduced as a prior false DIRECT_ONLY state and is now rejected while freeing the received buffer. Handle/memory release errors invalidate the result.

The pure Python validator pins external head/run/fullSIDs, bounds SID subauthorities toUInt32, rejects duplicate/missing subjects/rights, malformed numeric types and false readiness/physical claims. CI tests use fake APIs and own fixture memory; never real policy enumeration. JUnit identifies synthetic checks, not physical tests.

## Review / future memory-only command contract

Compile production artifacts only offPC4, using the CI workflow pc4-g0-lsa-readonly. Independently verify receipts with:

```powershell
python -B -m tools.g0_lsa_ci verify <downloaded-artifact-directory> <exact-head> <github-run-id> <attempt>
```

The physical command contract is a fresh pinned SSH session invoking the absolute WindowsPowerShell5.1 executable, NoProfile/NonInteractive, with the reviewed script and production DLL streamed through stdin. Parameters: -CollectMemory -G0Approved -AssemblyBytes <verified byte array> -AssemblySha256 <independently pinned digest> -Head <approved exact head> -RunId <fresh GUID N> -CollectorSid <full verified SID> -StorageSid <full verified SID>. No source/DLL/evidence files are copied to PC4. Do not use a generic execution helper or enable G1. If any verification/identity/native query fails, stop, retain UNKNOWN/BLOCKED evidence, and do not retry with elevation or broader policy access.

## 26 October PATH investigation

Two fresh pinned SSH sessions using an explicit absolute PowerShell executable and NoProfile observed identical Process PATH:702characters/21segments, SHA256f2a87cf9d5d1ff6caa10a6e8bdbaf2d019d19a9e3a2b07310f6bcd1ed6f00f5d, System32 present, no literal dollar-underscore. User/Machine PATH fingerprints contained no dollar-underscore. Observed OpenSSH DefaultShell overrides, cmd AutoRun and sshd service Environment entries were missing. The inspected sshd_config had no active matched SetEnv/AcceptEnv/ForceCommand/Include references; profile files were missing or unobservable. These are point-in-time reads, not trusted effective configuration/ancestor custody proof. The original session/command/parent environment was not preserved, so the historical cause is UNRESOLVED, not repaired. Explicit configuration bypass differs from the original alias/wrapper and cannot exclude its effects. No PATH, profile, sshd or service changes were made; full environment, shell histories, SSH keys and credential-bearing lines were not dumped.

References: https://learn.microsoft.com/windows/win32/api/ntsecapi/nf-ntsecapi-lsaenumerateaccountrights ; https://github.com/PowerShell/Win32-OpenSSH/wiki/DefaultShell ; https://github.com/PowerShell/Win32-OpenSSH/wiki/sshd_config .

Independent downloaded-artifact review found an initial P2 acceptance gap: a JSONL event/fake result could carry an unknown authorization/source field if its manifest hash was recomputed. Exact keysets now reject those fields; six new negative regressions failed before correction and pass afterward. The final synthetic gate has52Python tests+25named fake/default/layout/attribute tests+one aggregate for30legacy API checks=78JUnit cases per environment. Neither this count nor receipt consistency authenticates physical isolation. Partial provider warnings are also fail-closed and their payloads are suppressed from stdout.

The first bounded PC4 read stopped before loading the observer DLL: the direct manifest path was absent. Read-only diagnosis found the OS binary module at System32/WindowsPowerShell/v1.0/Modules/Microsoft.PowerShell.LocalAccounts/1.0.0.0/Microsoft.Powershell.LocalAccounts.dll. The loader now accepts exactly one of two explicit OS layouts (direct manifest or this reviewed versioned binary); it never discovers modules through PATH/PSModulePath. Missing/ambiguous layouts, provider errors, reparse file/ancestors and an imported path mismatch block before identity/LSA observation. Unknown future OS versions require review, not an automatic fallback. Five additional fake layout checks cover the contract.

Six additional injected attribute checks cover normal files, reparse files/ancestors, directory substitution, AccessDenied and missing files without creating junctions or touching host configuration.
