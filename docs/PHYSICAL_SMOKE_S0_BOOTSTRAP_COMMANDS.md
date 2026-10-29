# Initial S0 ZIP bootstrap commands

NOT_AUTHORIZED. This is preparation, not permission. Independently review these
literal lines against exact Git HEAD before pasting into a fresh non-elevated
local Windows PowerShell 5.1 console. Never execute an extracted script to
establish its own trust. WDAC, constrained language or execution policy failure
means STOP; there is no bypass.

Obtain the inner ZIP SHA256 and exact HEAD from independent artifact evidence,
not from the same unauthenticated download. Outer artifact SHA256 is different.
The literal loader captures inert ZIP bytes without write/delete sharing,
authenticates them before loading native code, then checks full manifest and
parent custody. Plan writes nothing. Stage publishes a new protected UUID root
without replacing any object; partial transactions remain for separate review.
Administrators, SYSTEM and the operator remain trusted.

```powershell
$DiagnosticStages = $false # optional fixed read-only progress; no authority
$Action = 'Plan'
$Approved = $false
$SourceZip = Read-Host 'Absolute inert original inner package ZIP path'
$ExpectedSha256 = Read-Host 'Independently authenticated inner ZIP SHA256'
$ExpectedHead = Read-Host 'Independently authenticated exact HEAD'
$ExpectedSid = Read-Host 'Independently matched local operator SID'
$TargetRoot = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)) ('GridS0Package-'+[Guid]::NewGuid().ToString('D'))
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($DiagnosticStages -and $Action -ne 'Plan') { throw 'S0_DIAGNOSTIC_PLAN_ONLY' }
if ($Action -eq 'Stage' -and -not $Approved) { throw 'S0_BOOTSTRAP_NOT_AUTHORIZED' }
if ('GridS0.Bootstrap' -as [type]) { throw 'S0_BOOTSTRAP_FRESH_CONSOLE_REQUIRED' }
Add-Type -AssemblyName System.IO.Compression
$file = $null; $hash = $null; $memory = $null; $archive = $null
try {
    # No write/delete sharing; capture once and authenticate before loading code.
    if ($DiagnosticStages) { [Console]::Out.WriteLine('S0_BOOTSTRAP_OPEN'); [Console]::Out.Flush() }
    $file = [IO.File]::Open($SourceZip,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    if ($file.Length -le 0 -or $file.Length -gt 536870912) { throw 'S0_ZIP_SIZE' }
    $bytes = New-Object byte[] ([int]$file.Length)
    $offset = 0
    while ($offset -lt $bytes.Length) {
        $count = $file.Read($bytes,$offset,$bytes.Length-$offset)
        if ($count -le 0) { throw 'S0_ZIP_SHORT_READ' }
        $offset += $count
    }
    if ($file.ReadByte() -ne -1) { throw 'S0_ZIP_CHANGED' }
    if ($DiagnosticStages) { [Console]::Out.WriteLine('S0_BOOTSTRAP_CAPTURED'); [Console]::Out.Flush() }
    $hash = [Security.Cryptography.SHA256]::Create()
    $actual = [BitConverter]::ToString($hash.ComputeHash($bytes)).Replace('-','').ToLowerInvariant()
    if ($actual -cne $ExpectedSha256) { throw 'S0_ZIP_SHA256' }
    if ($DiagnosticStages) { [Console]::Out.WriteLine('S0_BOOTSTRAP_HASHED'); [Console]::Out.Flush() }
    $memory = New-Object IO.MemoryStream(,$bytes)
    $archive = New-Object IO.Compression.ZipArchive($memory,[IO.Compression.ZipArchiveMode]::Read,$true)
    if ($DiagnosticStages) { [Console]::Out.WriteLine('S0_BOOTSTRAP_ARCHIVE'); [Console]::Out.Flush() }
    $entries = @($archive.Entries | Where-Object FullName -CEQ 'native/S0Launcher.dll')
    if ($entries.Count -ne 1 -or $entries[0].Length -le 0 -or $entries[0].Length -gt 4194304) { throw 'S0_NATIVE_MEMBER' }
    $input = $entries[0].Open(); $output = New-Object IO.MemoryStream
    try {
        $buffer = New-Object byte[] 65536
        $total = 0
        while (($count = $input.Read($buffer,0,$buffer.Length)) -gt 0) {
            $total += $count
            if ($total -gt $entries[0].Length -or $total -gt 4194304) { throw 'S0_NATIVE_SIZE' }
            $output.Write($buffer,0,$count)
        }
        $helper = $output.ToArray()
    } finally { $input.Dispose(); $output.Dispose() }
    if ($helper.Length -ne $entries[0].Length) { throw 'S0_NATIVE_SIZE' }
    if ($DiagnosticStages) { [Console]::Out.WriteLine('S0_BOOTSTRAP_LOAD'); [Console]::Out.Flush() }
    [void][Reflection.Assembly]::Load($helper)
    if ($DiagnosticStages) { [Console]::Out.WriteLine('S0_BOOTSTRAP_LOADED'); [Console]::Out.Flush() }
    # PlanPackage validates the complete manifest and parent custody without writes.
    if ($DiagnosticStages) { [Console]::Out.WriteLine('S0_BOOTSTRAP_VALIDATE'); [Console]::Out.Flush() }
    if ($DiagnosticStages) { $plan = [GridS0.Bootstrap]::PlanPackageDiagnostic($bytes,$ExpectedSha256,$ExpectedHead,$TargetRoot,$ExpectedSid) }
    else { $plan = [GridS0.Bootstrap]::PlanPackage($bytes,$ExpectedSha256,$ExpectedHead,$TargetRoot,$ExpectedSid) }
    if ($DiagnosticStages) { [Console]::Out.WriteLine('S0_BOOTSTRAP_VALIDATED'); [Console]::Out.Flush() }
    if ($Action -eq 'Stage') {
        [GridS0.Bootstrap]::StagePackage($bytes,$ExpectedSha256,$ExpectedHead,$TargetRoot,$ExpectedSid,$true)
    } elseif ($Action -eq 'ObserveToken') {
        $facts = [GridS0.TokenObserver]::RequireStandard($ExpectedSid)
        # Full SID/group evidence stays in console memory; never upload host facts.
        [pscustomobject]@{ Status='STANDARD_MEDIUM_OBSERVED_NOT_AUTHORIZATION'; Pid=$facts.Pid; CreationFileTime=$facts.CreationFileTime; Integrity=$facts.Integrity; Elevated=$facts.Elevated; GroupCount=$facts.Groups.Length; EnabledPrivileges=$facts.EnabledPrivileges; Execute=$false; Cleanup=$false }
    } else { $plan }
} finally {
    if ($archive) { $archive.Dispose() }; if ($memory) { $memory.Dispose() }
    if ($hash) { $hash.Dispose() }; if ($file) { $file.Dispose() }
}
```

Each action requires a fresh console and unchanged independently approved pins.
ObserveToken is read-only and returns aggregate primary-token facts; raw SID,
groups and privileges stay in memory. It does not attest an SSH token or peer.
After independent review and separate owner staging permission ONLY, repeat
with Action Stage and Approved true. That permission covers new package objects,
not input preparation, transfer, Execute, Stop, Evidence or Cleanup.

## Ordered phases and required authorization

1. LS5 local standard console: ObserveToken, Plan, then separately approved Stage.
2. PC4 existing PC4\ls4 non-elevated LOCAL console: independently repeat these.
3. LS5 protected plan-input staging and Prepare require their own reviewed fresh
   input mechanism and authorization; missing exact-head evidence means BLOCKED.
4. SSH transfer carries ONLY six PC4 files from LS5 PairRoot/PC4 through the
   existing pinned encrypted channel into fresh protected PC4 input. No plain
   scp/shared folder/inherited-ACL extraction workaround. Until the concrete
   protected receiver/transfer has independent tests, command remains BLOCKED.
5. PC4 Prepare, both Preflight, Execute, Status, Stop, Evidence: commands in
   PHYSICAL_SMOKE_S0.md apply only after preceding blockers and separate approvals.
   PairRoot is LocalAppData\GridS0-<run UUID>; RoleRoot is its LS5 or PC4 child.

STOP on any host/token/pin/manifest mismatch, existing target, unsafe ancestor,
reparse/hardlink, unknown API result, partial write, wrong SSH peer/fingerprint,
occupied listener or unexpected endpoint. Do not repair ACLs, accounts, SSH,
firewall, services or PostgreSQL to continue. No cleanup command is supplied.

All twenty G1 phases BLOCKED/null argv. Physical 0/10 NOT_RUN.
Execute/Cleanup NOT_AUTHORIZED. Deployment NO-GO. Hosted PASS is not physical PASS.

## Initial LS5 plan input (separate preparation approval)

After the literal loader has completed Plan in the same fresh standard console,
construct the already independently reviewed canonical JSON plan in memory.
This input contains private machine/account identities; do not publish it.
These method calls are proposed commands, NOT executed observations.

```powershell
$RunId = Read-Host 'Approved fresh UUID4 run identity'
$PlanBytes = [Text.Encoding]::UTF8.GetBytes((Read-Host 'Reviewed canonical compact sorted-key plan JSON'))
$InputRoot = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)) ('GridS0Input-'+[Guid]::NewGuid().ToString('D'))
$h = [Security.Cryptography.SHA256]::Create()
try { $PlanSha = [BitConverter]::ToString($h.ComputeHash($PlanBytes)).Replace('-','').ToLowerInvariant() } finally { $h.Dispose() }
[GridS0.Bootstrap]::PlanInput($PlanBytes,$PlanSha,$ExpectedHead,$RunId,$InputRoot,$ExpectedSid)
# Only with SEPARATE explicit owner approval of this exact new input root/hash:
# [GridS0.Bootstrap]::StagePlanInput($PlanBytes,$PlanSha,$ExpectedHead,$RunId,$InputRoot,$ExpectedSid,$true)
```

Then the separately approved LS5 Prepare uses `$InputRoot/s0-plan.json` and the
fresh PairRoot from the runbook. Native StageRoleImport similarly accepts an
independently hashed six-file ZIP and atomically publishes a fresh PC4 input
root. It does not obtain that private ZIP safely across hosts by itself.
The native sender/receiver now have hosted fixture tests; actual OpenSSH/SFTP
interoperability and physical custody remain UNVERIFIED. PC4 import and later
phases remain BLOCKED pending that evidence; no upload of private role keys
to GitHub/chat/CI is allowed. A successful file import is not
certificate semantic verification; existing Python Prepare still checks that.

Publication uses held source and parent identities and native
NtSetInformationFile FileRenameInformation (10), with ReplaceIfExists false.
There is no path-based move/copy or overwrite fallback. Windows API failures
remain BLOCKED; hosted success is required before asking to stage physically.
Reference: https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/nf-ntifs-ntsetinformationfile


## Concrete transfer and role command manifest (proposal, never authorization)

All variables are private operator inputs from independently reviewed G0 and the
ONE canonical PowerShell 5.1 CI package. Do not mix packages across hosts.
`ExpectedHead`, `ExpectedPackageSha`, `ExpectedSid`, `PackageRoot` and `PackageZip`
come from the reviewed literal loader above. Do not fetch code to establish its
own trust. The package root must be new and Stage must have separate approval.
Use the existing **local non-elevated** account console on each host, not the
administrative SSH session. `ObserveToken`/`RequireStandard` reads the actual
primary token; no account, logon, token creation or privilege adjustment occurs.

```powershell
# READ ONLY, same fresh standard console after authenticating the helper:
[GridS0.TokenObserver]::RequireStandard($ExpectedSid)
$Local = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
$PairRoot = Join-Path $Local ('GridS0-'+$RunId)
$Role = Read-Host 'Reviewed local role, exactly LS5 or PC4'
if ($Role -cnotin @('LS5','PC4')) { throw 'S0_ROLE_BLOCKED' }
$RoleRoot = Join-Path $PairRoot $Role
$Wrapper = Join-Path $PackageRoot 'installer/physical-smoke-s0.ps1'
$PowerShell51 = Join-Path ([Environment]::SystemDirectory) 'WindowsPowerShell/v1.0/powershell.exe'
```

**M1, separately approved fresh package/input preparation.** Use the literal
Plan/StagePackage and LS5 PlanInput/StagePlanInput calls above. Then:

```powershell
# LS5 ONLY; MUTATES exclusively the fresh PairRoot and its role files.
# Requires approval of PairRoot, plan digest, operators, addresses and port.
& $PowerShell51 -NoProfile -File $Wrapper -Root $PairRoot -PackageRoot $PackageRoot -PackageZip $PackageZip -Config (Join-Path $InputRoot 's0-plan.json') -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Action Prepare -Approved
```

**M2, transfer rehearsal first: PUBLIC, NO KEYS.** Actual SSH/SFTP behavior is not
proved by FileStream fixtures. Do not send a private role archive until this
rehearsal is separately approved, completed and reviewed. Obtain host IP, exact
ed25519 SSH wire blob and full SHA256 fingerprint independently from private G0;
never trust a key learned from the proposed connection itself.

```powershell
# LS5: READ ONLY proposal; Stage is a separate mutation approval.
$ExportRoot = Join-Path $Local ('GridS0Input-'+[Guid]::NewGuid().ToString('D'))
[GridS0.Bootstrap]::PlanTransferProbe($ExpectedHead,$RunId,$Pc4IP,$Pc4HostKeyBlob,$Pc4Fingerprint,$ExportRoot,$ExpectedSid)
# ONLY after M2 preparation approval:
# $Export = [GridS0.Bootstrap]::StageTransferProbe($ExpectedHead,$RunId,$Pc4IP,$Pc4HostKeyBlob,$Pc4Fingerprint,$ExportRoot,$ExpectedSid,$true)
```

For a **later separate private transfer approval**, replace the probe with:

```powershell
# LS5: reads ONLY the six PC4 role files; never the LS5 private key/marker.
[GridS0.Bootstrap]::PlanTransferExport((Join-Path $PairRoot 'PC4'),$ExpectedHead,$RunId,$ExpectedPackageSha,$ExportRoot,$ExpectedSid)
# $Export = [GridS0.Bootstrap]::StageTransferExport((Join-Path $PairRoot 'PC4'),$ExpectedHead,$RunId,$ExpectedPackageSha,$ExportRoot,$ExpectedSid,$true)
# $Known = [GridS0.Bootstrap]::StageTransferKnownHosts($ExportRoot,$Export.Materialization.RootIdentity,$Export.PayloadSha256,$ExpectedHead,$RunId,$Pc4IP,$Pc4HostKeyBlob,$Pc4Fingerprint,$ExpectedSid,$true)
# Probe already contains known_hosts; do NOT call StageTransferKnownHosts on it.
```

**M3, PC4 fresh receiver and bounded channel.** PC4 local console independently
checks head/run/hash/length received over the authorized review channel. It
creates only a fresh `GridS0Input-UUID/incoming.zip` plus `slot.json`. Opening
the separately approved lease creates protected CREATE_NEW `lease.json`, which
blocks reopening even after a crash or truncation to zero. Start the
lease immediately before the approved transfer and keep that console alive.

```powershell
# PC4: Plan is read only; Stage requires independent M3 approval.
$ReceiveRoot = Join-Path $Local ('GridS0Input-'+[Guid]::NewGuid().ToString('D'))
[GridS0.Bootstrap]::PlanTransferSlot($ExpectedHead,$RunId,$PayloadSha,$PayloadSize,$ReceiveRoot,$ExpectedSid)
# $Slot = [GridS0.Bootstrap]::StageTransferSlot($ExpectedHead,$RunId,$PayloadSha,$PayloadSize,$ReceiveRoot,$ExpectedSid,$true)
# $Receiver = [GridS0.Bootstrap]::OpenTransferSlot($ReceiveRoot,$Slot.Materialization.RootIdentity,$Slot.IncomingIdentity,$ExpectedHead,$RunId,$PayloadSha,$PayloadSize,$ExpectedSid,$true)
```

The private transfer plan is produced by the pure, non-executing
`tools/s0_ssh_transfer_plan.py::build_transfer_plan(record)`. Its closed input
contract requires the observed full receiver root/file identities, approved
existing key path, stock ssh/scp binary paths and hashes, exact host key and
private source/receiver paths. Output is always `BLOCKED`, `argv=null` and all
permissions false. Independently review **every proposed_argv element** and the
actual executable/key/parent custody before separate transfer approval.
The proposed stock `scp` uses pinned `known_hosts`, `-F NUL`, no agent, passwords,
forwarding, proxy, connection reuse, preserve or recursive flags. It does not
modify sshd, PATH, accounts, system known_hosts or existing keys. Do not use
legacy `scp -O`, change SSH policy or fix PATH to make this pass.

```powershell
# LS5, ONLY after explicit transfer approval; Plan object is privately supplied,
# never evaluate a command string or use Invoke-Expression.
# $Sender = [GridS0.Bootstrap]::OpenTransferSender($ExportRoot,$Export.Materialization.RootIdentity,$Export.PayloadSha256,$KnownHostsSha,$ExpectedSid)
# try {
#   $Sender.Verify()
#   $Scp = $TransferPlan.proposed_argv[0]
#   $ScpArgs = @($TransferPlan.proposed_argv | Select-Object -Skip 1)
#   & $Scp @ScpArgs
#   if ($LASTEXITCODE -ne 0) { throw 'S0_TRANSFER_FAILED' }
#   $Sender.Verify()
# } finally { $Sender.Dispose() }
# PC4, within 300 seconds, after scp has closed all writers:
# $Receiver.Verify() # nonsecret DTO only, never returns the private ZIP bytes
```

Unknown binary/key custody, SFTP open/truncate behavior, metadata ACL changes,
PATH `$_` source, fingerprint, expired lease, sharing error or surviving writer
means **STOP/BLOCKED**. The probe intentionally fails role-import validation;
**do not import a public probe**. It only establishes the tested transfer facts.
No automatic retry, adoption or cleanup exists. Reboot/crash loses the handles;
claimed leftover slots cannot be reopened/adopted as a new transfer. This is
not an anti-rollback guarantee against the trusted owner/admin restoring state.

**M4, private PC4 import and Prepare**, only after private transfer approval:

```powershell
# PC4, with the original live receiver lease, after verified private transfer:
$Pc4InputRoot = Join-Path $Local ('GridS0Input-'+[Guid]::NewGuid().ToString('D'))
# [GridS0.Bootstrap]::PlanTransferImport($Receiver,$ExpectedHead,$RunId,$ExpectedPackageSha,$Pc4InputRoot,$ExpectedSid)
# [GridS0.Bootstrap]::StageTransferImport($Receiver,$ExpectedHead,$RunId,$ExpectedPackageSha,$Pc4InputRoot,$ExpectedSid,$true)
# $Receiver.Dispose() # releases only held handles; does NOT remove resources
# & $PowerShell51 -NoProfile -File $Wrapper -Root $PairRoot -PackageRoot $PackageRoot -PackageZip $PackageZip -Config (Join-Path $Pc4InputRoot 'PC4/config.json') -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Action Prepare -Approved
```

Import captures immutable verified bytes internally, atomically consumes its
in-process lease and publishes a new input root. It grants no execution authority.
A failed import remains consumed; no retry on the same slot. Python Prepare
independently checks TLS semantics and creates the local prepared marker.

**M5, both Preflight (read-only), then separate S0 Execute approval:**

```powershell
$Config = Join-Path $RoleRoot 'config.json'
& $PowerShell51 -NoProfile -File $Wrapper -Root $RoleRoot -PackageRoot $PackageRoot -PackageZip $PackageZip -Config $Config -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Action Preflight
# Only after BOTH preflights, G0 and human acceptance; LS5 foreground first,
# then PC4 within the registration deadline. Execute runs at most 300 seconds.
# & $PowerShell51 -NoProfile -File $Wrapper -Root $RoleRoot -PackageRoot $PackageRoot -PackageZip $PackageZip -Config $Config -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Action Execute -Approved
```

**M6, status/controlled stop/evidence**, separate consoles with exact own RoleRoot:

```powershell
& $PowerShell51 -NoProfile -File $Wrapper -Root $RoleRoot -PackageRoot $PackageRoot -PackageZip $PackageZip -Config $Config -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Action Status
# Stop mutates ONLY the owned stop.json; no PID termination by this command.
# & $PowerShell51 -NoProfile -File $Wrapper -Root $RoleRoot -PackageRoot $PackageRoot -PackageZip $PackageZip -Config $Config -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Action Stop -Approved
# Evidence creates an owned bounded archive, excluding private key material.
# & $PowerShell51 -NoProfile -File $Wrapper -Root $RoleRoot -PackageRoot $PackageRoot -PackageZip $PackageZip -Config $Config -ExpectedHead $ExpectedHead -ExpectedPackageSha $ExpectedPackageSha -Action Evidence -Approved
```

Every commented mutation remains NOT_AUTHORIZED. Human approvals must identify
exact head/package/run/host/SID/resources/actions/expiry, not merely say "CI PASS".
Creation-time ACLs apply only to new owned objects; existing ACLs never change.
Partial roots and private archives remain protected for manual review; **Cleanup
is not implemented or authorized**. This scope does not provide G1 sandboxing,
OS network confinement, durable anti-rollback or protection from trusted local
administrators/the authorized user's malicious same-SID processes.


Handle custody requests GENERIC_READ (including directory list access), not only
READ_CONTROL/READ_ATTRIBUTES, with no FILE_SHARE_DELETE. Windows sharing semantics
exclude attribute-only access; hosted replacement negatives must demonstrate the
actual refusal. AccessDenied from the stronger read request stays BLOCKED.
Reference: https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
The transfer claim is persisted with FlushFileBuffers and CREATE_NEW, not a proof
of storage survival after power loss. Any reboot, interrupted write, missing claim
or uncertain storage state stops this attempt; no recovery/adoption is authorized.
