# Run only from an independently authenticated protected checkout. For initial
# untrusted ZIP delivery, use the literal loader in the runbook instead.
[CmdletBinding()]
param(
    [ValidateSet('Plan','ObserveToken','Stage')][string]$Action = 'Plan',
    [Parameter(Mandatory=$true)][string]$SourceZip,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedSha256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedHead,
    [Parameter(Mandatory=$true)][string]$ExpectedSid,
    [Parameter(Mandatory=$true)][string]$TargetRoot,
    [switch]$Approved
)
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
