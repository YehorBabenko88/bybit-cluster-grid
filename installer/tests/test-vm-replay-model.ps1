#Requires -Version 5.1
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Push-Location $root
try {
    $lines=@(& $Python -B -c "import json; from installer.vm_replay_model import ReplayModel; m=ReplayModel(); n=ReplayModel.recover(m.checkpoint(),m.anchor); print(json.dumps(n.report()))")
    if($LASTEXITCODE -ne 0){throw 'VM_MEMORY_MODEL_FAILED'}
    $r=($lines -join "`n")|ConvertFrom-Json
    if($r.status -cne 'BLOCKED' -or $r.mode -cne 'MODEL_ONLY' -or $r.durable_storage -cne 'NOT_IMPLEMENTED' -or
       $r.execution_authorized -ne $false -or $r.physical_ready -ne $false -or
       $r.readiness_passed -ne $false -or $r.verified_safety_cases -ne 0 -or @($r.negative_cases).Count -ne 12){throw 'VM_MEMORY_MODEL_AUTHORITY_PROMOTION'}
    foreach($case in $r.negative_cases){if($case.execution -cne 'NOT_RUN' -or $case.assurance -cne 'BLOCKED_UNPROVEN'){throw 'VM_MEMORY_CASE_PROMOTION'}}
    Write-Output 'Memory replay model only: durability NOT_IMPLEMENTED/BLOCKED; 12 NOT_RUN'
} finally { Pop-Location }
