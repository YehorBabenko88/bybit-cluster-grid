#Requires -Version 5.1
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Push-Location $root
try {
    $fixture=Join-Path $PSScriptRoot 'vm-lab-plan.example.json'
    # Only the checked-in synthetic fixture is read; no observer or VM is invoked.
    $lines=@(& $Python -B -c "import json,sys; from pathlib import Path; from installer.vm_lab_json import load; from installer.vm_lab_evidence import draft,inspect_evidence; p=load(Path(sys.argv[1]).read_text(encoding='utf-8')); print(json.dumps(inspect_evidence(json.dumps(draft(p,'55555555-5555-4555-8555-555555555555')),p)))" $fixture)
    if($LASTEXITCODE -ne 0){throw 'VM_DRAFT_EVIDENCE_FAILED'}
    $r=($lines -join "`n")|ConvertFrom-Json
    if($r.status -cne 'BLOCKED' -or $r.integrity -cne 'MATCH_METADATA_ONLY' -or
       $r.authentication -cne 'UNVERIFIED' -or $r.execution_authorized -ne $false -or
       $r.physical_ready -ne $false -or $r.readiness_passed -ne $false -or
       $r.verified_safety_cases -ne 0 -or @($r.negative_cases).Count -ne 12){throw 'VM_DRAFT_EVIDENCE_PROMOTION'}
    foreach($case in $r.negative_cases){
        if($case.execution -cne 'NOT_RUN' -or $case.assurance -cne 'BLOCKED_UNPROVEN'){throw 'VM_DRAFT_CASE_PROMOTION'}
    }
    Write-Output 'VM draft integrity only: authentication UNVERIFIED; 12 NOT_RUN cases; readiness false'
} finally { Pop-Location }
