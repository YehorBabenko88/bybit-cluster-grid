#Requires -Version 5.1
<# Offline preparation adapter only. No installation/runtime/SQL execution.
Prepare and Rollback require the exact PlanOnly approval token. Rollback preserves resources. #>
[CmdletBinding()]
param(
 [ValidateSet('PlanOnly','Prepare','Rollback')][string]$Mode='PlanOnly',
 [Parameter(Mandatory=$true)][string]$LabParent,
 [Parameter(Mandatory=$true)][string]$RunId,
 [Parameter(Mandatory=$true)][string]$NodeId,
 [ValidateSet('CONTROL','WORKER')][string]$Role='CONTROL',
 [Parameter(Mandatory=$true)][string]$Version,
 [Parameter(Mandatory=$true)][string]$Branch,
 [int]$PostgresPort=23001,[int]$CoordinatorPort=23002,
 [string]$Approval=''
)
$ErrorActionPreference='Stop'
try {
 . (Join-Path $PSScriptRoot 'isolated-deployment-core.ps1')
 $plan=New-GridLabPlan -LabParent $LabParent -RunId $RunId -NodeId $NodeId -Role $Role -Version $Version -Branch $Branch -PostgresPort $PostgresPort -CoordinatorPort $CoordinatorPort
 if($Mode -eq 'PlanOnly'){
  [ordered]@{schema=1;status='PLAN_ONLY';plan=$plan;prepare_approval=('PREPARE:'+$plan.plan_sha256);rollback_approval=('RETIRE:'+$plan.plan_sha256);activation_authorized=$false}|ConvertTo-Json -Depth 12 -Compress
 }else{
  Invoke-GridLabPreparation -Plan $plan -Mode $Mode -Approval $Approval|ConvertTo-Json -Depth 8 -Compress
 }
}catch{
 $code='GRID_LAB_OPERATION_BLOCKED'
 if($_.Exception.Message -cmatch '^(GRID_LAB|GRID_RUNTIME)_[A-Z_]+$'){$code=$_.Exception.Message}
 [ordered]@{schema=1;status='BLOCKED';code=$code;activation_authorized=$false}|ConvertTo-Json -Compress
 throw $code
}
