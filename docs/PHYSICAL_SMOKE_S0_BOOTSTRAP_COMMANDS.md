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
$Action = 'Plan'
$Approved = $false
$SourceZip = Read-Host 'Absolute inert original inner package ZIP path'
$ExpectedSha256 = Read-Host 'Independently authenticated inner ZIP SHA256'
$ExpectedHead = Read-Host 'Independently authenticated exact HEAD'
$ExpectedSid = Read-Host 'Independently matched local operator SID'
$TargetRoot = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)) ('GridS0Package-'+[Guid]::NewGuid().ToString('D'))
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($Action -eq 'Stage' -and -not $Approved) { throw 'S0_BOOTSTRAP_NOT_AUTHORIZED' }
if ('GridS0.Bootstrap' -as [type]) { throw 'S0_BOOTSTRAP_FRESH_CONSOLE_REQUIRED' }
Add-Type -AssemblyName System.IO.Compression
$file = $null; $hash = $null; $memory = $null; $archive = $null
try {
    # No write/delete sharing; capture once and authenticate before loading code.
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
    $hash = [Security.Cryptography.SHA256]::Create()
    $actual = [BitConverter]::ToString($hash.ComputeHash($bytes)).Replace('-','').ToLowerInvariant()
    if ($actual -cne $ExpectedSha256) { throw 'S0_ZIP_SHA256' }
    $memory = New-Object IO.MemoryStream(,$bytes)
    $archive = New-Object IO.Compression.ZipArchive($memory,[IO.Compression.ZipArchiveMode]::Read,$true)
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
    [void][Reflection.Assembly]::Load($helper)
    # PlanPackage validates the complete manifest and parent custody without writes.
    $plan = [GridS0.Bootstrap]::PlanPackage($bytes,$ExpectedSha256,$ExpectedHead,$TargetRoot,$ExpectedSid)
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

## Ordered phases and unresolved commands

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
Until the SSH sender/receiver and incoming-file custody are independently
implemented/tested, PC4 import and later phases remain BLOCKED; no upload of
private role keys to GitHub/chat/CI is allowed. A successful file import is not
certificate semantic verification; existing Python Prepare still checks that.
