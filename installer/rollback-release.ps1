#Requires -Version 5.1
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ReviewedVersion,
 [Parameter(Mandatory=$true)][string]$Python,
 [string]$InstallRoot="$env:ProgramFiles\BybitClusterGrid",
 [string]$DataRoot="$env:ProgramData\BybitClusterGrid",
 [ValidateSet('CONTROL','WORKER')][string]$Role='CONTROL',
 [switch]$LegacyRollback,
 [switch]$Apply
)
$ErrorActionPreference='Stop'
if($ReviewedVersion -cnotmatch '^[0-9a-f]{40}$'){throw 'Invalid reviewed release SHA'}
$release=Join-Path (Join-Path $InstallRoot 'releases') $ReviewedVersion
# Use this reviewed checker, never execute the rollback target's installer code.
$checker=Join-Path $PSScriptRoot 'windows_preflight.py'
$argsCheck=@('-B',$checker,'--release-dir',$release,'--expected-sha',$ReviewedVersion,'--role',$Role,'--env-file',(Join-Path $DataRoot '.env'))
if($Role -eq 'CONTROL' -or $LegacyRollback){$argsCheck+='--check-db'}
if($LegacyRollback){$argsCheck+='--legacy-rollback'}
$report=& $Python @argsCheck
if($LASTEXITCODE -ne 0){throw 'Rollback blocked by read-only release/schema/runtime checks'}
if($LegacyRollback){
 try {$evidence=($report -join "`n") | ConvertFrom-Json} catch {throw 'Legacy rollback preflight report invalid'}
 if($evidence.schema -ne 1 -or $evidence.status -cne 'PASS' -or $evidence.mode -cne 'read-only' -or
    $evidence.activation_authorized -isnot [bool] -or $evidence.activation_authorized -ne $false -or
    $evidence.database_checked -isnot [bool] -or $evidence.database_checked -ne $true -or
    $evidence.legacy_rollback -isnot [bool] -or $evidence.legacy_rollback -ne $true -or
    $evidence.rollback_scope -cne 'offline-pointer-only' -or
    $evidence.checks.release.version -cne $ReviewedVersion -or
    $evidence.checks.release.code -cne 'LEGACY_RELEASE_VERIFIED_OFFLINE_ONLY' -or
    $evidence.checks.database.code -cne 'LEGACY_SCHEMA47_READY_OFFLINE_ONLY'){
   throw 'Legacy rollback requires verified offline schema47 evidence'
 }
 Write-Output 'LEGACY_ROLLBACK_OFFLINE_ONLY=true; activation_authorized=false; schema retained'
}
# Hold the same mutex across evidence collection and the nested switch. Windows
# mutexes are recursive on the owning thread; switch rechecks before its write.
$mutex = [Threading.Mutex]::new($false,'Global\BybitClusterGridReleaseSwitch')
$locked = $false
try {
 try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
 if (-not $locked) { throw 'Another release operation is active' }
 . (Join-Path $PSScriptRoot 'release-runtime-guard.ps1')
 Assert-GridRuntimeStopped
 $switch=Join-Path $PSScriptRoot 'switch-release.ps1'
 if($Apply){& $switch -Version $ReviewedVersion -InstallRoot $InstallRoot -Role $Role -Apply}
 else {& $switch -Version $ReviewedVersion -InstallRoot $InstallRoot -Role $Role}
} finally {
 if ($locked) { $mutex.ReleaseMutex() }
 $mutex.Dispose()
}
# Retains schema 47, WAL, previous release and pending markers. No task activation.
Write-Output 'Rollback pointer plan completed; schema/WAL retained; no service started'
