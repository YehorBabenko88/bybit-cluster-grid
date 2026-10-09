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
# An exclusive cross-process lock prevents concurrent promotions on this host.
$lockName = 'Global\BybitClusterGridReleaseSwitch'
$mutex = [System.Threading.Mutex]::new($false, $lockName)
$lockHeld = $false
try {
    try { $lockHeld = $mutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $lockHeld = $true }
    if (-not $lockHeld) { throw 'Another Grid release switch is already running' }
$releaseRoot = Join-Path $InstallRoot 'releases'
$release = Join-Path $releaseRoot $Version
$required = if ($Role -eq 'CONTROL') { 'grid\coordinator.py' } else { 'run_worker.py' }
if (-not (Test-Path -LiteralPath (Join-Path $release $required) -PathType Leaf)) {
    throw "Candidate release lacks required entry point: $required"
}
$manifestPath = Join-Path $release 'release-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw 'Candidate release manifest missing'
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.version -ne $Version) { throw 'Candidate release manifest version mismatch' }
# Validate manifest paths and hashes before any pointer changes.
if ($null -eq $manifest.files -or @($manifest.files.PSObject.Properties).Count -eq 0) {
    throw 'Release manifest has no file checksums'
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
    $actualHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedHash) {
        throw "Manifest checksum mismatch: $relative"
    }
}
$failedMarker = Join-Path $InstallRoot 'failed.version'
if (Test-Path -LiteralPath $failedMarker -PathType Leaf) {
    $failedVersion = (Get-Content -LiteralPath $failedMarker -Raw).Trim()
    if ($failedVersion -eq $Version) {
        throw 'Candidate was previously rolled back as failed; manual review required'
    }
}
# Refuse another promotion while a previous switch is awaiting confirmation.
$pendingMarker = Join-Path $InstallRoot 'pending.version'
if (Test-Path -LiteralPath $pendingMarker -PathType Leaf) {
    $pendingVersion = (Get-Content -LiteralPath $pendingMarker -Raw).Trim()
    if ($pendingVersion) {
        throw "Unconfirmed pending release $pendingVersion; resolve recovery before switching again"
    }
}
$marker = Join-Path $InstallRoot 'current.version'
if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { throw 'current.version missing' }
$current = (Get-Content -LiteralPath $marker -Raw).Trim()
if ($current -notmatch '^[0-9a-f]{40}$') { throw 'Invalid current.version' }
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
# Fail closed: an updater must stop the owning service first. Refuse to
# change pointers while Grid processes are active on this host.
$gridProcesses = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
    Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -match 'grid\.release_supervisor' -or
            $_.CommandLine -match 'BybitClusterGrid.*run_worker\.py' -or
            $_.CommandLine -match 'uvicorn grid\.coordinator:app'
        )
    })
if ($gridProcesses.Count -gt 0) { throw 'Grid service process still running; refusing switch' }
function Write-Atomic([string]$Path,[string]$Value) {
    $tmp = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
    try {
        [IO.File]::WriteAllText($tmp, $Value, [Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $tmp -Destination $Path -Force
    } finally {
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force }
    }
}
# Preserve rollback before promoting the new current pointer.
Write-Atomic (Join-Path $InstallRoot 'previous.version') $current
Write-Atomic (Join-Path $InstallRoot 'pending.version') $Version
Write-Atomic $marker $Version
Write-Output "PENDING_SWITCH=$Version"
Write-Output 'No service was started. An orchestrator must start and verify the release.'

} finally {
    if ($lockHeld) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
