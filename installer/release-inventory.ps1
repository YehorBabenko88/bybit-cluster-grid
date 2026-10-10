#Requires -Version 5.1
<#
.SYNOPSIS
Read-only inventory of installed Grid releases and rollback protection.
.DESCRIPTION
No deletion or task changes. Intended as a prerequisite for a future
transactional updater and release garbage collector.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:ProgramFiles\BybitClusterGrid",
    [int]$RetainCount = 3
)
$ErrorActionPreference = 'Stop'
if ($RetainCount -lt 3) { throw 'RetainCount must be at least 3' }
$releaseRoot = Join-Path $InstallRoot 'releases'
if (-not (Test-Path -LiteralPath $releaseRoot -PathType Container)) {
    throw "Release directory missing: $releaseRoot"
}
function Read-Version([string]$Name) {
    $path = Join-Path $InstallRoot $Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    $value = (Get-Content -LiteralPath $path -Raw).Trim()
    if ($value -and $value -notmatch '^[0-9a-f]{40}$') {
        throw "Invalid version marker: $Name"
    }
    return $value
}
$current = Read-Version 'current.version'
$previous = Read-Version 'previous.version'
if (-not $current) { throw 'current.version missing or empty' }
$releases = @(Get-ChildItem -LiteralPath $releaseRoot -Directory |
    Where-Object { $_.Name -match '^[0-9a-f]{40}$' } |
    Sort-Object LastWriteTimeUtc -Descending)
$protected = @{}
$protected[$current] = 'CURRENT'
if ($previous) { $protected[$previous] = 'PREVIOUS' }
foreach ($item in ($releases | Select-Object -First $RetainCount)) {
    if (-not $protected.ContainsKey($item.Name)) {
        $protected[$item.Name] = 'RECENT_BACKUP'
    }
}
Write-Output '=== RELEASE INVENTORY (READ ONLY) ==='
foreach ($item in $releases) {
    $status = if ($protected.ContainsKey($item.Name)) { $protected[$item.Name] } else { 'UNREFERENCED_CANDIDATE' }
    [pscustomobject]@{
        Version = $item.Name
        Status = $status
        LastWriteUtc = $item.LastWriteTimeUtc
    }
}
Write-Output 'No files were deleted. Candidates are NOT approved for deletion until running-process, task, and rollback references are checked.'
