#Requires -Version 5.1
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Push-Location $root
try {
    $lines=@(& $Python -B -m installer.ownership_threat_boundary)
    if($LASTEXITCODE -ne 0){throw 'THREAT_BOUNDARY_REPORT_FAILED'}
    $reports=($lines -join "`n")|ConvertFrom-Json
    if($reports.Count -ne 2){throw 'THREAT_BOUNDARY_MODELS_MISSING'}
    foreach($r in $reports){
        if($r.schema -ne 1 -or $r.status -cne 'BLOCKED' -or $r.assurance -cne 'EVIDENCE_ONLY' -or
           $r.evidence_only -ne $true -or $r.execution_authorized -ne $false -or $r.physical_ready -ne $false -or
           @($r.matrix).Count -ne 7){throw 'THREAT_BOUNDARY_UNSAFE_REPORT'}
        foreach($row in $r.matrix){if($row.verification -cne 'BLOCKED'){throw 'THREAT_BOUNDARY_UNPROVEN_GUARANTEE'}}
    }
    if($reports[0].model -cne 'A' -or $reports[0].decision -cne 'BLOCKED_PROVISIONING_UNPROVEN' -or
       $reports[1].model -cne 'B' -or $reports[1].decision -cne 'STOP_OS_BOUNDARY_REQUIRED'){throw 'THREAT_BOUNDARY_DECISION_INVALID'}
    Write-Output 'Threat boundary matrix validated: 2 models, 14 BLOCKED rows; no readiness authorization'
} finally { Pop-Location }
