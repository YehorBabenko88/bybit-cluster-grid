#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'installer/ls5-g0-readonly-preflight.ps1'
function Assert-G0([string]$expected, [string]$reason) {
    $raw = & $scriptPath -Role CONTROL
    $data = $raw | ConvertFrom-Json
    if ($data.status -ne $expected) { throw "G0_EXPECTED_$expected GOT_$($data.status)" }
    if ($reason -and @($data.stop_reasons) -notcontains $reason) { throw "G0_REASON_MISSING_$reason" }
}
function Get-ScheduledTask { @() }
function Get-CimInstance { @() }
function Get-NetTCPConnection { @() }
Assert-G0 'OBSERVATION_ONLY' ''
function Get-ScheduledTask { [pscustomobject]@{TaskName='BybitClusterGridCoordinator'; State='Ready'} }
Assert-G0 'BLOCKED' 'GRID_TASK_PRESENT_NOT_DISABLED_DO_NOT_MUTATE'
function Get-ScheduledTask { [pscustomobject]@{TaskName='BybitClusterGridCoordinator'; State='Disabled'} }
Assert-G0 'OBSERVATION_ONLY' ''
function Get-NetTCPConnection { [pscustomobject]@{LocalPort=8765;LocalAddress='0.0.0.0';OwningProcess=42} }
Assert-G0 'BLOCKED' 'EXISTING_LISTENER_DO_NOT_REUSE'
function Get-NetTCPConnection { throw 'mock unavailable' }
Assert-G0 'BLOCKED' 'PORT_INVENTORY_UNAVAILABLE'
function Get-ScheduledTask { throw 'mock unavailable' }
Assert-G0 'BLOCKED' 'TASK_INVENTORY_UNAVAILABLE'
function Get-CimInstance { throw 'mock unavailable' }
Assert-G0 'BLOCKED' 'PROCESS_INVENTORY_UNAVAILABLE'
Write-Output 'G0_MOCKED_OFFLINE_PASS'
