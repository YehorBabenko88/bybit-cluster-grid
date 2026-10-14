#Requires -Version 5.1
<#
.SYNOPSIS
Safely switch the release pointer to an already verified, locally installed release.
.DESCRIPTION
Requires explicit -Apply; defaults to plan-only. This script never restarts a
service, migrates a database, downloads code or removes a release. The operator
or fleet orchestrator must coordinate service restart and post-switch health.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$Version,
    [string]$InstallRoot = "$env:ProgramFiles\BybitClusterGrid",
    [ValidateSet('WORKER','CONTROL')][string]$Role = 'WORKER',
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
if ($Version -cnotmatch '^[0-9a-f]{40}$') { throw 'Invalid candidate release SHA: expected lowercase hexadecimal' }
# An exclusive cross-process lock prevents concurrent promotions on this host.
$lockName = 'Global\BybitClusterGridReleaseSwitch'
$mutex = [System.Threading.Mutex]::new($false, $lockName)
$lockHeld = $false
try {
    try { $lockHeld = $mutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $lockHeld = $true }
    if (-not $lockHeld) { throw 'Another Grid release switch is already running' }
# Refuse reparse points in the installation path to avoid redirecting pointer writes.
$installFull = [IO.Path]::GetFullPath($InstallRoot)
$pathCursor = $installFull
while ($pathCursor) {
    if (Test-Path -LiteralPath $pathCursor) {
        $item = Get-Item -LiteralPath $pathCursor -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "InstallRoot traverses a reparse point: $pathCursor"
        }
    }
    $parent = [IO.Directory]::GetParent($pathCursor)
    if ($null -eq $parent) { break }
    $pathCursor = $parent.FullName
}
$releaseRoot = Join-Path $InstallRoot 'releases'
$release = Join-Path $releaseRoot $Version
# Release directories must be physical directories, not redirected junctions.
foreach ($releasePath in @($releaseRoot, $release)) {
    if (Test-Path -LiteralPath $releasePath) {
        $releaseItem = Get-Item -LiteralPath $releasePath -Force
        if (($releaseItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Release path is a reparse point: $releasePath"
        }
    }
}
$required = if ($Role -eq 'CONTROL') { 'grid\coordinator.py' } else { 'run_worker.py' }
if (-not (Test-Path -LiteralPath (Join-Path $release $required) -PathType Leaf)) {
    throw "Candidate release lacks required entry point: $required"
}
$manifestPath = Join-Path $release 'release-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw 'Candidate release manifest missing'
}
if ((Get-Item -LiteralPath $manifestPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'Candidate release manifest is a reparse point'
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.version -cne $Version) { throw 'Candidate release manifest version mismatch' }
# Validate manifest paths and hashes before any pointer changes.
if ($null -eq $manifest.files -or @($manifest.files.PSObject.Properties).Count -eq 0) {
    throw 'Release manifest has no file checksums'
}
# A checksum manifest must cover the executable entry point for this role.
$requiredKey = $required.Replace([char]92, '/')
if ($null -eq $manifest.files.PSObject.Properties[$requiredKey]) {
    throw "Release manifest omits required entry point: $requiredKey"
}
$releaseFull = [IO.Path]::GetFullPath($release).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
foreach ($entry in $manifest.files.PSObject.Properties) {
    $relative = [string]$entry.Name
    $expectedHash = [string]$entry.Value
    if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)' -or
        $relative -match '^[a-zA-Z]:' -or $expectedHash -notmatch '^[0-9a-fA-F]{64}$') {
        throw "Invalid manifest entry: $relative"
    }
    $target = [IO.Path]::GetFullPath((Join-Path $release ($relative.Replace('/', [IO.Path]::DirectorySeparatorChar))))
    if (-not $target.StartsWith($releaseFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Manifest path escapes release directory: $relative"
    }
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
        throw "Manifest file missing: $relative"
    }
    # A normal file can still be reached through a redirected parent directory.
    $parentCursor = [IO.Path]::GetDirectoryName($target)
    while ($parentCursor -and $parentCursor.Length -ge $releaseFull.TrimEnd([IO.Path]::DirectorySeparatorChar).Length) {
        if ((Get-Item -LiteralPath $parentCursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Manifest path traverses a reparse point: $relative"
        }
        if ($parentCursor -ieq $releaseFull.TrimEnd([IO.Path]::DirectorySeparatorChar)) { break }
        $parentCursor = [IO.Path]::GetDirectoryName($parentCursor)
    }
    if ((Get-Item -LiteralPath $target -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Manifest file is a reparse point: $relative"
    }
    $actualHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedHash) {
        throw "Manifest checksum mismatch: $relative"
    }
}
# Refuse to promote a release containing unverified Python source files.
# Runtime-generated caches and virtual environments are outside this source check.
$manifestKeys = @{}
foreach ($entry in $manifest.files.PSObject.Properties) {
    $manifestKeys[[string]$entry.Name.Replace([char]92, '/')] = $true
}
Get-ChildItem -LiteralPath $release -Recurse -File -Filter '*.py' | ForEach-Object {
    $relativePath = $_.FullName.Substring($releaseFull.Length).Replace([char]92, '/')
    if (-not $manifestKeys.ContainsKey($relativePath)) {
        throw "Release manifest omits Python source: $relativePath"
    }
}
$failedMarker = Join-Path $InstallRoot 'failed.version'
if (Test-Path -LiteralPath $failedMarker) {
    if (-not (Test-Path -LiteralPath $failedMarker -PathType Leaf)) {
        throw 'Invalid failed.version type; manual review required'
    }
    $failedVersion = (Get-Content -LiteralPath $failedMarker -Raw).Trim()
    if ($failedVersion -cnotmatch '^[0-9a-f]{40}$') { throw 'Invalid failed.version; manual review required' }
    if ($failedVersion -eq $Version) {
        throw 'Candidate was previously rolled back as failed; manual review required'
    }
}
# Refuse another promotion while a previous switch is awaiting confirmation.
$pendingMarker = Join-Path $InstallRoot 'pending.version'
if (Test-Path -LiteralPath $pendingMarker) {
    if (-not (Test-Path -LiteralPath $pendingMarker -PathType Leaf)) {
        throw 'Invalid pending.version type; manual recovery required'
    }
    $pendingVersion = (Get-Content -LiteralPath $pendingMarker -Raw).Trim()
    throw 'Pending release marker exists; resolve or remove it through the recovery procedure before switching again'
}
# An interrupted transaction must be recovered before any new promotion,
# including when the journal exists but the pending marker is absent.
$journalPath = Join-Path $InstallRoot 'switch-journal.json'
if (Test-Path -LiteralPath $journalPath) {
    throw 'Release switch journal exists; run recovery before switching again'
}
$marker = Join-Path $InstallRoot 'current.version'
if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { throw 'current.version missing' }
$current = (Get-Content -LiteralPath $marker -Raw).Trim()
if ($current -cnotmatch '^[0-9a-f]{40}$') { throw 'Invalid current.version' }
if ($current -eq $Version) {
    Write-Output "ALREADY_CURRENT=$Version"
    return
}
$currentDir = Join-Path $releaseRoot $current
if (-not (Test-Path -LiteralPath (Join-Path $currentDir $required) -PathType Leaf)) {
    throw 'Current release cannot serve as a rollback target'
}
Write-Output "CURRENT=$current"
Write-Output "CANDIDATE=$Version"
Write-Output "ROLE=$Role"
if (-not $Apply) {
    Write-Output 'PLAN_ONLY=true; no files changed'
    return
}
function Write-Atomic([string]$Path,[string]$Value) {
    $tmp = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
    try {
        [IO.File]::WriteAllText($tmp, $Value, [Text.UTF8Encoding]::new($false))
        if ([IO.File]::Exists($Path)) {
            # File.Replace uses the Windows replace-file primitive rather than
            # removing the destination before renaming the temporary file.
            $backup = "$Path.$([guid]::NewGuid().ToString('N')).bak"
                try {
                    [IO.File]::Replace($tmp, $Path, $backup, $true)
                } finally {
                    if ([IO.File]::Exists($backup)) { [IO.File]::Delete($backup) }
                }
        } else {
            [IO.File]::Move($tmp, $Path)
        }
    } finally {
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force }
    }
}
# A journal is written before the first marker mutation. If power fails,
# launchers can distinguish prepared vs committed promotions on next boot.
$journalPath = Join-Path $InstallRoot 'switch-journal.json'
if (Test-Path -LiteralPath $journalPath -PathType Leaf) {
    throw 'Unresolved switch journal exists; recovery required before promotion'
}
$journal = [ordered]@{ schema=1; previous=$current; candidate=$Version; phase='prepared' } | ConvertTo-Json -Compress
. (Join-Path $PSScriptRoot 'release-runtime-guard.ps1')
Assert-GridRuntimeStopped
Write-Atomic $journalPath $journal
# Preserve rollback before promoting the new current pointer.
Write-Atomic (Join-Path $InstallRoot 'previous.version') $current
Write-Atomic (Join-Path $InstallRoot 'pending.version') $Version
Write-Atomic $marker $Version
# Mark the transaction committed only after the current pointer was persisted.
$journal = [ordered]@{ schema=1; previous=$current; candidate=$Version; phase='committed' } | ConvertTo-Json -Compress
Write-Atomic $journalPath $journal
Write-Output "PENDING_SWITCH=$Version"
Write-Output 'No service was started. An orchestrator must start and verify the release.'

} finally {
    if ($lockHeld) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
