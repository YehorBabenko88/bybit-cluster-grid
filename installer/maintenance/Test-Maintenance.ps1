#Requires -Version 5.1
# Synthetic fixture only: no host observations or native token code.
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Maintenance.Core.ps1')
$run='12345678-1234-4234-8234-123456789abc';$head='a'*40;$tree='b'*40
$cases=0;$caseNames=New-Object 'Collections.Generic.List[string]'
$plan=(& (Join-Path $PSScriptRoot 'GridMaintenance.ps1'))|ConvertFrom-Json
if($plan.status -ne 'PLAN_ONLY' -or $plan.host_calls -ne 0){throw 'PLAN_FAILED'};$cases++;$caseNames.Add('plan_no_calls')
foreach($action in @('Stage','Prepare','Execute','Cleanup','Inventory','Preflight','Evidence')){
 $result=(& (Join-Path $PSScriptRoot 'GridMaintenance.ps1') -Action $action)|ConvertFrom-Json
 if($result.status -ne 'BLOCKED' -or $result.execute -ne $false -or $result.cleanup -ne $false){throw 'ACTION_FAILED_OPEN'};$cases++;$caseNames.Add('action_'+$action)
}
foreach($fault in @('none','throw','empty','many','status','reason','shape')){
 $provider={param($gate)
  switch($fault){
   'throw' {throw 'PRIVATE_PASSWORD'}
   'empty' {return}
   'many' {New-MaintenanceRow 'PASS' 'SYNTHETIC';New-MaintenanceRow 'PASS' 'SYNTHETIC';return}
   'status' {return [ordered]@{status='UNKNOWN';reason='SYNTHETIC';data=@()}}
   'reason' {return [ordered]@{status='PASS';reason='PRIVATE password';data=@()}}
   'shape' {return 'PRIVATE_PASSWORD'}
  }
  New-MaintenanceRow 'PASS' 'SYNTHETIC_COMPLETE'
 }
 $s=New-MaintenanceSnapshot LS5 $head $tree $run $provider 'SYNTHETIC_OFFLINE'
 $raw=$s|ConvertTo-Json -Depth 12 -Compress
 if($raw -match 'PRIVATE_PASSWORD|PRIVATE password'){throw 'SECRET_LEAK'}
 foreach($row in $s.checks.Values){if($fault -eq 'none'){if($row.status -ne 'PASS'){throw 'MODEL_BAD'}}elseif($row.status -ne 'BLOCKED'){throw 'FAULT_FAILED_OPEN'}}
 if($s.execute -ne $false -or $s.cleanup -ne $false -or $s.deployment -ne 'NO-GO'){throw 'FALSE_AUTHORITY'};$cases++;$caseNames.Add('provider_'+$fault)
}
# Preserve exact task identity and never serialize its principal or action.
function Get-ScheduledTask {[CmdletBinding()]param() [pscustomobject]@{TaskName='GridS0-G0-TokenObserver';TaskPath='\';State='Ready'}}
$r=Get-MaintenanceObservation tasks PC4 '' '' ''
if($r.data[0].diagnostic_task -ne $true -or $r.data[0].disposition -ne 'PRESERVE_UNOWNED_TASK'){throw 'TASK_NOT_PRESERVED'};$cases++;$caseNames.Add('task_preserved')
# API failures, disabled residual rules and token pin absence must remain blocked.
function Get-NetFirewallRule {[CmdletBinding()]param($PolicyStore) @(
 [pscustomobject]@{Name='PRIVATE_RULE_ID';DisplayName='Old Grid';Enabled='False';Direction='Inbound';Action='Allow'},
 [pscustomobject]@{Name='OTHER_PRIVATE_ID';DisplayName='Bybit old';Enabled='True';Direction='Inbound';Action='Allow'})}
$r=Get-MaintenanceObservation firewall LS5 '' '' ''
if($r.status -ne 'BLOCKED' -or $r.data.Count -ne 2 -or ($r|ConvertTo-Json -Depth 8) -match 'PRIVATE_RULE_ID|OTHER_PRIVATE_ID'){throw 'FIREWALL_REDACTION_OR_DISABLED_OMISSION'}
$cases++;$caseNames.Add('firewall_disabled_and_redacted')
function Get-NetFirewallRule {[CmdletBinding()]param($PolicyStore) throw 'PRIVATE_ACCESS_DENIED'}
$r=New-MaintenanceSnapshot LS5 $head $tree $run {param($gate) if($gate -eq 'firewall'){Get-MaintenanceObservation $gate LS5 '' '' ''}else{New-MaintenanceRow 'BLOCKED' 'SYNTHETIC_NOT_OBSERVED'}} 'SYNTHETIC_OFFLINE'
if($r.checks.firewall.status -ne 'BLOCKED' -or ($r|ConvertTo-Json -Depth 12) -match 'PRIVATE_ACCESS_DENIED'){throw 'API_FAILED_OPEN'}
$cases++;$caseNames.Add('firewall_api_failure')
try{Get-MaintenanceToken '' '' '';throw 'MISSING_PIN_ACCEPTED'}catch{if($_.Exception.Message -ne 'TOKEN_PIN_REQUIRED'){throw}}
$cases++;$caseNames.Add('token_missing_pin')
[ordered]@{scope='SYNTHETIC_OFFLINE_NOT_PHYSICAL';cases=$cases;names=@($caseNames.ToArray());status='PASS';execute=$false;cleanup=$false}|ConvertTo-Json -Compress

exit 0
