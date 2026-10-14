#Requires -Version 5.1
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ReviewedVersion,
 [Parameter(Mandatory=$true)][string]$Python,
 [string]$InstallRoot="$env:ProgramFiles\BybitClusterGrid",
 [string]$DataRoot="$env:ProgramData\BybitClusterGrid",
 [ValidateSet('CONTROL','WORKER')][string]$Role='CONTROL',
 [switch]$Apply
)
$ErrorActionPreference='Stop'
if($ReviewedVersion -cnotmatch '^[0-9a-f]{40}$'){throw 'Invalid reviewed release SHA'}
$release=Join-Path (Join-Path $InstallRoot 'releases') $ReviewedVersion
# Use this reviewed checker, never execute the rollback target's installer code.
$checker=Join-Path $PSScriptRoot 'windows_preflight.py'
$argsCheck=@('-B',$checker,'--release-dir',$release,'--expected-sha',$ReviewedVersion,'--role',$Role,'--env-file',(Join-Path $DataRoot '.env'))
if($Role -eq 'CONTROL'){$argsCheck+='--check-db'}
$report=& $Python @argsCheck
if($LASTEXITCODE -ne 0){throw 'Rollback blocked by read-only release/schema/runtime checks'}
# Require task state evidence even for plan generation. Never stop/start tasks.
$tasks=@(Get-ScheduledTask -ErrorAction Stop | Where-Object {$_.TaskName -in @('BybitClusterGridAgent','BybitClusterGridCoordinator','BybitClusterGridArchivePipeline')})
if(@($tasks | Where-Object {$_.State -ne 'Disabled'}).Count){throw 'Grid tasks must be disabled through a separately approved operation'}
$processes=@(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
 $_.CommandLine -and $_.CommandLine -match '(grid\.(coordinator|archive_service|release_supervisor)|run_(worker|coordinator)\.py)'
})
if($processes.Count){throw 'Grid process is running; rollback refused'}
$switch=Join-Path $PSScriptRoot 'switch-release.ps1'
if($Apply){& $switch -Version $ReviewedVersion -InstallRoot $InstallRoot -Role $Role -Apply}
else {& $switch -Version $ReviewedVersion -InstallRoot $InstallRoot -Role $Role}
# Retains schema 47, WAL, previous release and pending markers. No task activation.
Write-Output 'Rollback pointer plan completed; schema/WAL retained; no service started'
