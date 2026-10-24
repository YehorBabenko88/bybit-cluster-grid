#Requires -Version 5.1
<#
.SYNOPSIS
Read-only G0 snapshot of Grid task, process and port identities.
No secrets, command lines, environment variables, task actions, SQL or file mutations.
#>
[CmdletBinding()]
param([ValidateSet('CONTROL','WORKER')][string]$Role='CONTROL')
$ErrorActionPreference='Stop'
$ports=@(8765,55432)
$result=[ordered]@{
 schema='grid-g0-readonly-1'; role=$Role; host=$env:COMPUTERNAME
 utc=[DateTime]::UtcNow.ToString('o'); status='BLOCKED'
 process_inventory='UNKNOWN'; task_inventory='UNKNOWN'; port_inventory='UNKNOWN'
 tasks=@(); listeners=@(); processes=@(); stop_reasons=@()
}
try {
 $tasks=@(Get-ScheduledTask -ErrorAction Stop | Where-Object { $_.TaskName -in @('BybitClusterGridCoordinator','BybitClusterGridAgent','BybitClusterGridArchivePipeline') })
 $result.tasks=@($tasks | ForEach-Object { [ordered]@{name=$_.TaskName;state=[string]$_.State} })
 if (@($tasks | Where-Object { [string]$_.State -ne 'Disabled' }).Count -gt 0) {
   $result.stop_reasons+= 'GRID_TASK_PRESENT_NOT_DISABLED_DO_NOT_MUTATE'
 }
 $result.task_inventory='OBSERVED'
} catch { $result.stop_reasons+= 'TASK_INVENTORY_UNAVAILABLE' }
try {
 $processes=@(Get-CimInstance Win32_Process -OperationTimeoutSec 10 -ErrorAction Stop)
 $result.processes=@($processes | Where-Object {
   $_.Name -match '^(python|pythonw|powershell|pwsh|uvicorn)([.]exe)?$'
 } | ForEach-Object {
   [ordered]@{pid=[int]$_.ProcessId;name=[string]$_.Name;creation_utc=([string]$_.CreationDate)}
 })
 $result.process_inventory='OBSERVED'
} catch { $result.stop_reasons+= 'PROCESS_INVENTORY_UNAVAILABLE' }
try {
 $listeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalPort -in $ports })
 $result.listeners=@($listeners | ForEach-Object {
   [ordered]@{local_address=[string]$_.LocalAddress;port=[int]$_.LocalPort;pid=[int]$_.OwningProcess}
 })
 $result.port_inventory='OBSERVED'
} catch { $result.stop_reasons+= 'PORT_INVENTORY_UNAVAILABLE' }
if ($result.listeners.Count -gt 0) { $result.stop_reasons+= 'EXISTING_LISTENER_DO_NOT_REUSE' }
# This observer cannot establish source provenance, trusted process identity or port freedom
# outside its narrow inventory. Never interpret an empty listener list as G1 authorization.
if ($result.stop_reasons.Count -eq 0) { $result.status='OBSERVATION_ONLY' }
$result | ConvertTo-Json -Depth 6
