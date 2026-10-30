#Requires -Version 5.1
# Safe dispatcher: stdout only; no installer, subprocess, socket or mutation executor.
[CmdletBinding()]
param(
 [ValidateSet('Inventory','PlanOnly','Preflight','Stage','Prepare','Execute','Evidence','Cleanup')][string]$Action='PlanOnly',
 [ValidateSet('LS5','PC4')][string]$Node,
 [string]$Head,[string]$Tree,[string]$RunId,
 [switch]$ReadOnlyApproved,
 [string]$ExpectedSid,[string]$TokenObserverDll,[string]$TokenObserverSha256
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if($Action -eq 'PlanOnly'){
 [ordered]@{schema='grid-maintenance-plan-1';status='PLAN_ONLY';host_calls=0;execute=$false;cleanup=$false;deployment='NO-GO';g1_phases='20/20 BLOCKED';mutating_argv=$null}|ConvertTo-Json -Compress
 return
}
if($Action -notin @('Inventory','Preflight','Evidence') -or !$ReadOnlyApproved){
 [ordered]@{schema='grid-maintenance-plan-1';status='BLOCKED';reason='NO_AUTHENTICATED_ACTION_SPECIFIC_EXECUTOR';execute=$false;cleanup=$false;deployment='NO-GO';mutating_argv=$null}|ConvertTo-Json -Compress
 exit 2
}
if([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or !$Node -or [Environment]::MachineName -ine $Node){
 [ordered]@{status='BLOCKED';reason='HOST_IDENTITY_MISMATCH';execute=$false;cleanup=$false;deployment='NO-GO'}|ConvertTo-Json -Compress
 exit 2
}
. (Join-Path $PSScriptRoot 'Maintenance.Core.ps1')
try{
 $provider={param($gate) Get-MaintenanceObservation $gate $Node $TokenObserverDll $TokenObserverSha256 $ExpectedSid}
 New-MaintenanceSnapshot -Node $Node -Head $Head -Tree $Tree -RunId $RunId -Provider $provider|ConvertTo-Json -Depth 12 -Compress
}catch{
 [ordered]@{status='BLOCKED';reason='INCOMPLETE_OBSERVATION';execute=$false;cleanup=$false;deployment='NO-GO'}|ConvertTo-Json -Compress
}

# Observations remain unverified; a successful provider is not host authorization.
exit 2
