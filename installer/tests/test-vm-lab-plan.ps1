#Requires -Version 5.1
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Push-Location $root
$savedOutputEncoding=$OutputEncoding
try {
    # Hosted PS5.1 can prepend a UTF-8 BOM to native stdin. Keep strict JSON;
    # normalize this test's transport and restore the caller's encoding.
    $OutputEncoding=New-Object System.Text.UTF8Encoding($false)
    $bad=@('{"schema":1,"schema":1}' | & $Python -B -m installer.vm_lab_plan)
    if($LASTEXITCODE -ne 2 -or ($bad -join "`n") -notmatch 'VM_PLAN_REJECTED'){throw 'VM_PLAN_INVALID_JSON_ACCEPTED'}
    $fixture=Join-Path $PSScriptRoot 'vm-lab-plan.example.json'
    $lines=@(Get-Content -LiteralPath $fixture -Raw | & $Python -B -m installer.vm_lab_plan)
    if($LASTEXITCODE -ne 0){throw 'VM_PLAN_STATIC_FIXTURE_FAILED'}
    $r=($lines -join "`n")|ConvertFrom-Json
    if($r.status -cne 'BLOCKED' -or $r.mode -cne 'PlanOnly' -or $r.assurance -cne 'STATIC_METADATA_ONLY' -or
       $r.execution_authorized -ne $false -or $r.physical_ready -ne $false -or
       $r.readiness_passed -ne $false -or $r.verified_safety_cases -ne 0 -or
       @($r.negative_cases).Count -ne 12){throw 'VM_PLAN_UNSAFE_EVIDENCE'}
    foreach($case in $r.negative_cases){
        if($case.execution -cne 'NOT_RUN' -or $case.assurance -cne 'BLOCKED_UNPROVEN'){throw 'VM_PLAN_GUEST_TEST_NOT_ATTESTED'}
    }
    Write-Output 'VM lab PlanOnly metadata: 12 NOT_RUN/BLOCKED_UNPROVEN guest cases; invalid JSON refused; no execution'
} finally { $OutputEncoding=$savedOutputEncoding; Pop-Location }
