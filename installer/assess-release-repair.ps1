#Requires -Version 5.1
<#
.SYNOPSIS
Read-only offline repair assessment. No Apply mode, database access or activation.
.DESCRIPTION
Requires explicit fixture/copied evidence paths. Holds the release mutex while
Runtime Guard and the trusted offline assessor run. Does not invoke switch/recover.
#>
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$InstallRoot,
 [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ReviewedVersion,
 [Parameter(Mandatory=$true)][string]$SchemaEvidence,
 [Parameter(Mandatory=$true)][string]$Python,
 [ValidateSet('CONTROL','WORKER')][string]$Role='CONTROL'
)
$ErrorActionPreference='Stop'
$mutex=[Threading.Mutex]::new($false,'Global\BybitClusterGridReleaseSwitch')
$held=$false
try {
 try {$held=$mutex.WaitOne(0)} catch [Threading.AbandonedMutexException] {$held=$true}
 if(!$held){throw 'GRID_REPAIR_MUTEX_BUSY'}
 . (Join-Path $PSScriptRoot 'release-runtime-guard.ps1')
 Assert-GridRuntimeStopped
 # Never run code from the pointed-to release. -B suppresses bytecode writes.
 $checker=Join-Path $PSScriptRoot 'release_repair_plan.py'
 $output=& $Python -B $checker --install-root $InstallRoot --reviewed-version $ReviewedVersion --schema-evidence $SchemaEvidence --role $Role
 $code=$LASTEXITCODE
 try {$report=($output -join "`n")|ConvertFrom-Json} catch {throw 'GRID_REPAIR_REPORT_INVALID'}
 if($code -ne 0){
  if($report.code -cmatch '^REPAIR_[A-Z_]+$'){throw ([string]$report.code)}
  throw 'GRID_REPAIR_EVIDENCE_REJECTED'
 }
 if($report.schema -ne 1 -or $report.mode -cne 'read-only-plan' -or $report.status -cne 'PLAN_ONLY' -or
    $report.activation_authorized -isnot [bool] -or $report.activation_authorized -ne $false -or
    $report.repair_authorized -isnot [bool] -or $report.repair_authorized -ne $false -or
    $report.marker_removal_authorized -isnot [bool] -or $report.marker_removal_authorized -ne $false -or
    $report.database_checked_live -isnot [bool] -or $report.database_checked_live -ne $false -or
    $null -eq $report.proposed_changes -or @($report.proposed_changes).Count -ne 0){
  throw 'GRID_REPAIR_REPORT_INVALID'
 }
 $report.runtime_inventory='STOPPED_SNAPSHOT_UNDER_MUTEX'
 $report|ConvertTo-Json -Depth 10 -Compress
} finally {
 if($held){$mutex.ReleaseMutex()}
 $mutex.Dispose()
}
