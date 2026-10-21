# PC4 local SID/ACL test package — preparation only

**Physical execution NOT_RUN / NOT_AUTHORIZED in this development task.**
Default is PlanOnly. No SSH/Tailscale connection, remote command, account change,
VM, PostgreSQL/SQL/initdb, installer, service, network or production operation is
performed. No Grid deployment or L1/L2 GO follows from this package or CI.

Base: PR215 `4d0569d64763eba358c58d47211c5bb0165f78cb`. Existing principal binding,
native ownership threat boundaries, commissioning and schema-1/PGDATA intent
contracts are reused as constraints, not wired to this new standalone harness.
Physical host SID/ACL experiments are a different scope from the 12 VM cases;
those remain NOT_RUN. This is neither a PGDATA test nor air-gap evidence.

## Owner-reported PC4 baseline (not independently collected)

Windows 11 Pro, Ryzen 7 7800X3D, 32 GB; SSH/Tailscale available. C:\GridLab and
C:\GridLab\Secure exist. GridLabCollector SID suffix1003 and GridLabStorage
suffix1004, both disabled/non-admin; Collector/Storage have respective Modify and
SYSTEM/Administrators Full Control. Exact full SIDs, folder locations, owner,
inheritance, token rights, file system and account logon eligibility are unverified.
The proposal assumes role parents `C:\GridLab\Secure\Collector` and `...\Storage`.
If actual paths differ, stop for review; no path override/implicit mapping exists.

SID suffix is not identity. Execution requires full canonical local-account SIDs
and exact Get-LocalUser SID match; suffix-only inputs are refused. Disabled users
block before credentials/fixture writes. The package never enables users or
changes membership, ACL, policies, user rights, services or execution policy.

## Separate plan needed before a physical attempt

Owner must approve, separately from this PR:

1. Exact PC4 resources and operations, code SHA/artifact manifest hash, observer,
   STOP authority, allowed time window, bounded run IDs and evidence custody.
2. Account lifecycle plan: privately verify full SIDs, local logon eligibility,
   disabled baseline, who may enable the two existing accounts for the trial and
   who restores disabled state afterward. This document supplies **no account-
   enablement command or authority**. Do not reset passwords or alter policy to
   make a failure pass. If required rights/services are unavailable, remain BLOCKED.
3. Explicit staging/ownership of `C:\GridLab\Harness\PC4SidAcl` and an admin-only
   `C:\GridLab\Evidence` base. These must already exist with reviewed ACLs;
   this harness does not create or repair those base directories. Role parent
   DACLs must be protected and contain exactly SYSTEM/Admin FullControl and the
   respective full SID Modify, inherited to files/subfolders; unknown ACEs block.
4. Trust model: honest elevated bootstrap controller and reviewed immutable actor
   code; two non-admin test accounts. Hostile local administrator/SYSTEM, hostile
   same-SID code, compromised host/kernel, transient ACL ABA and previously open
   writable mappings are outside these tests' guarantees. Parent token-query
   access must work without this package adjusting privileges; otherwise BLOCKED.
5. Local secure credential entry; no password argument, environment variable,
   credential file, transcript or GitHub secret is required. Use a local console,
   not a remote session whose logon/credential semantics have not been reviewed.

The account-plan-reference argument is only an operator-provided private record
reference, not authenticated approval. Execute/cleanup switches acknowledge scope;
they do not replace owner approval or independent reviews.

## Package and build provenance

Files: Invoke-Pc4SidAcl.ps1, Actor.ps1, Common.ps1, TokenFacts.cs and hosted-built
TokenFacts.dll. `package.sha256.json` binds exact source SHA and all five file
hashes; `PACKAGE_MANIFEST_SHA256.txt` provides the manifest digest. Independently
pin it against the reviewed CI artifact/run, not just the same untrusted download.
Hashes detect inconsistent bytes, not malicious provenance or host compromise.

Build-OfflinePackage.ps1 compiles only under disposable hosted CI guards. It does
not invoke native token/handle APIs. PC4 loads the prebuilt DLL after hash/ACL
checks: **no C# compilation on PC4**. PowerShell execution policy and signing
requirements must be satisfied normally; never use Bypass/Unrestricted to run it.
Do not invoke Actor.ps1 or the build script manually on PC4.

## Future local commands — examples only, not authorization

After a separately authorized staging step, PlanOnly remains read-only metadata:

```powershell
& 'C:\GridLab\Harness\PC4SidAcl\Invoke-Pc4SidAcl.ps1'
```

Only after all human gates above, use a local elevated **64-bit Windows PowerShell
5.1** controller. It is a setup/observation token, never the actor's isolation
proof. Actor executables are explicitly 64-bit Windows PowerShell 5.1, NoProfile,
NonInteractive, no execution-policy override and LoadUserProfile=false.

```powershell
# FUTURE ONLY. Full SIDs and record reference are private inputs, not passwords.
$runId = [guid]::NewGuid().ToString('D')
$collectorSid = Read-Host 'Owner-verified full Collector SID'
$storageSid = Read-Host 'Owner-verified full Storage SID'
$packageHash = Read-Host 'Independently pinned package manifest SHA256'
$planRef = Read-Host 'Approved private account/fixture-plan reference'
& 'C:\GridLab\Harness\PC4SidAcl\Invoke-Pc4SidAcl.ps1' `
  -Execute -ApproveFixtureCreation -RunId $runId `
  -CollectorSid $collectorSid -StorageSid $storageSid `
  -AccountPlanReference $planRef -ExpectedPackageManifestSha256 $packageHash
```

Two Get-Credential dialogs collect PSCredentials locally; ProcessStartInfo.Password
uses SecureString and no password appears in Arguments. This is not a claim that
Windows never materializes credentials internally. No network-only logon token
is used: full local user context is required. Logon failure or disabled accounts
is BLOCKED, not an excuse to start Secondary Logon or change security policy.

## Process/token and I/O protocol

1. Validate fixed PC4 machine name, 64-bit process, trusted controller/code/base
   ACLs, pinned package, complete SIDs and enabled existing accounts. Inventory
   errors, access denied/unknown resources and existing GUID paths block.
2. Prompt securely, then create only fresh `sid-acl-<UUIDv4>` child directories in
   each role parent and a private Evidence child. CreateNew prevents overwriting
   known files. Existing account/folder contents are never cleaned or reused.
3. Open directory handles without delete sharing to pin declared lab ancestors
   and run directories during the session. These reduce ordinary rename races,
   not DACL mutation/admin/mapping/namespace-wide TOCTOU guarantees.
4. Launch actual processes with separate local credentials. Each actor reads its
   actual TokenUser, TokenGroups (including deny-only Administrators membership),
   TokenElevation, integrity and privileges using GetTokenInformation. Current
   thread impersonation blocks. No token impersonation/privilege adjustment is
   performed. Controller independently reads each live child PID token before
   creating the per-run go.flag. PID/identity uncertainty blocks; no admin actor
   can substitute for a failed non-admin process.
5. Require exact expected SID; Administrators absent (even deny-only), elevation
   false, integrity RID <=8192, no impersonation, and only a strict benign
   privilege list. Only SeChangeNotifyPrivilege may be enabled. A dangerous
   privilege present but disabled still blocks. Unknown privileges are not waived.
6. Two positive cases per role: CreateNew own.txt with run/role content, actual
   object-owner SID check, then read back identical content. Two negative cases:
   open the other role's existing canary for Read and separately Write. PASS only
   for Win32 access denied 5. Missing file/path, sharing violation, timeout or any
   other error is FAIL. Unexpected write-open is FAIL without modifying the peer
   canary. Original canary bytes and parent owner/SDDL must remain unchanged.

Ten expected local case results: token + own_write + own_read + foreign_read_denied
+ foreign_write_denied, for Collector and Storage. A failed actor/token blocks the
aggregate; no fallback token, automatic retry or synthetic physical PASS exists.

## Evidence and failures

Private `C:\GridLab\Evidence\sid-acl-<run>` retains manifest/package hashes,
parent-observed child token JSON, ACL before/after, actor JSONL, combined results,
JUnit and SHA256 index. JSONL includes run, role, PID, fixed case/error code and
native token facts. Native observations are **local reports, not independent
authenticated attestation**. SIDs/SDDL are private evidence; do not upload actual
host dumps, credentials or sensitive identifiers to GitHub.

Partial runs retain initial manifest, launch-intent/PID records and per-role raw logs in owned fixtures,
failure JSONL, failing one-case JUnit and partial hash index where evidence writes
remain possible. If even evidence writes fail, no success is emitted; preserve
remaining directories for manual investigation. No exception details/passwords
are copied into public diagnostics. sha256.json covers JSONL/JUnit/other existing
files at its creation, excluding itself and the later completion marker; do not
trust completed.json alone. Rehash and check the index before review/transfer.

`installer.pc4_sid_acl_evidence.validate` validates untrusted JSONL against expected
full SIDs/run/hash and formats JUnit; it never authenticates the collector. A
forger can manufacture consistent evidence. Its physical_attestation and airgap
flags are always false. Unit fixtures are explicitly synthetic, not PC4 results.

## Repeat, failure and cleanup

Same run ID refuses existing fixture/evidence, even if interrupted or apparently
complete. No resume/delete-to-retry option. Investigate, preserve evidence and get
approval for a new run ID. Account state restoration is handled by the separate
human plan, never by an unattended finally block.

Actors time out their initial gate after 45 seconds. Controller waits are bounded;
on failure it writes a per-run stop.flag where possible, never kills arbitrary
PIDs or starts/restarts services. A child still running, reused PID or failed process
inventory blocks cleanup. Check the failed state privately before another attempt.

Cleanup requires separate approval and the original private manifest/controller:

```powershell
# FUTURE ONLY; evidence retained. No automatic/recursive removal.
& 'C:\GridLab\Harness\PC4SidAcl\Invoke-Pc4SidAcl.ps1' `
  -Cleanup -ApproveFixtureCleanup -RunId $runId `
  -ExpectedPackageManifestSha256 $packageHash
```

It checks exact GUID, manifest hash/index and original package version, marker, known flat file names, reparse absence
and process absence before first deletion. Unknown entry, subdirectory, missing
marker or inventory error blocks. Only enumerated files and empty owned GUID
directories may be removed; no recursive delete, ACL repair, Evidence deletion,
parent directory deletion or old installation cleanup. Launch intent without a
persisted PID is an uncertain outcome and blocks cleanup even when ready.json is
missing. A missing hash index after a hard crash likewise needs manual review.
Successful repeat cleanup
with both GUID roots already absent is a no-op. Interrupted cleanup with marker
removed but directory deletion failed deliberately needs manual review; no
names-only recovery or automatic marker recreation is permitted. Hostile admin or
same-account active tampering is not defeated by a marker/pinned handle alone.

## Explicit write boundary and remaining physical blockers

Application-created/tested data is limited to the two new GUID children and one
new Evidence child. Script never requests PostgreSQL, SSH/Tailscale, service,
policy, account/group or old-data changes. Code review and path checks enforce
intended I/O scope; **no whole-host non-mutation proof exists**. Windows may write
security/audit logs, runtime/profile/cache metadata outside GridLab on process
logon/load even with LoadUserProfile=false. If literal zero host changes outside
GridLab is mandatory, this process-logon experiment is NO-GO; use a separately
approved disposable OS boundary. Do not claim a directory watcher proves absence.

Unverified: PC4 full SIDs/ACL/owner/inheritance, enabled/logon plan, package/base
staging and security, parent token-query rights, effective token behavior, process
start compatibility, handle lifetime/cleanup under real failure and independent
custody. No physical run occurred. Tailscale/SSH working means this is **not an
air-gap experiment**. VM/PGDATA/witness/freshness/durable anti-rollback and prior
human L1/L2 gates remain separate and blocked; no schema-2 activation occurs.

## Verification scope and primary references

CI performs Python synthetic format/refusal tests, pure PowerShell policy tests,
syntax parsing, compilation and DLL load only. It never invokes Actor.ps1,
TokenFacts.Read/PinDirectory or controller Execute/Cleanup, and never accesses PC4.
PowerShell 5.1/7 policy/parse/load success does not certify a physical PS7 controller.

- [GetTokenInformation](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-gettokeninformation)
- [CreateProcessWithLogonW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createprocesswithlogonw)
- [File security/access rights](https://learn.microsoft.com/en-us/windows/win32/fileio/file-security-and-access-rights)
