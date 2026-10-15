#Requires -Version 5.1
[CmdletBinding()]
param(
 [ValidateSet('PlanOnly','PreflightReadOnly')][string]$Mode='PlanOnly',
 [Parameter(Mandatory=$true)][string]$DataRoot,[Parameter(Mandatory=$true)][string]$RunId,
 [Parameter(Mandatory=$true)][string]$NodeId,[Parameter(Mandatory=$true)][int]$Port,
 [Parameter(Mandatory=$true)][string]$Commit,[Parameter(Mandatory=$true)][string]$PlanSha256,
 [Parameter(Mandatory=$true)][string]$OwnerSid
)
$ErrorActionPreference='Stop'
if($Commit -cnotmatch '^[0-9a-f]{40}$' -or $PlanSha256 -cnotmatch '^[0-9a-f]{64}$'){
 [ordered]@{schema=1;status='BLOCKED';code='PG_READ_ONLY_IDENTITY_INVALID';execution_authorized=$false;physical_ready=$false}|ConvertTo-Json -Compress
 throw 'PG_READ_ONLY_IDENTITY_INVALID'
}
if($Mode -eq 'PlanOnly'){
 [ordered]@{schema=1;status='PLAN_ONLY';execution_authorized=$false;physical_ready=$false;commit_sha=$Commit;asserted_plan_sha256=$PlanSha256;blockers=@('ADAPTER_LAYOUT_INCOMPATIBLE','NO_INITDB_EXECUTOR','FRESH_HOST_INVENTORY_REQUIRED');
  probes=@('shared Runtime Guard under release mutex','fixed local disk and physical ancestors','absent PGDATA/run/node roots','protected owner ACL','PostgreSQL services/processes/tasks','TCP/UDP observation only; NOT reservation')}|ConvertTo-Json -Depth 5 -Compress
 return
}
. (Join-Path $PSScriptRoot 'isolated-postgres-readonly-core.ps1')
$r=Get-GridPostgresEvidence -DataRoot $DataRoot -RunId $RunId -NodeId $NodeId -Port $Port -Commit $Commit -PlanSha256 $PlanSha256 -OwnerSid $OwnerSid
$r|ConvertTo-Json -Depth 10 -Compress
if($r.status -ne 'SNAPSHOT_ONLY'){throw 'PG_READ_ONLY_BLOCKED'}
