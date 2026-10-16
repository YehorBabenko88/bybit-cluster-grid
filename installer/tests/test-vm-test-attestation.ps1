#Requires -Version 5.1
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Push-Location $root
try {
    $lines=@(& $Python -B -c "import json; from installer.tests.vm_test_attestation_fixture import signed,example_plan,NOW; from installer.vm_test_attestation import verify_test_fixture,TestReplayState; p=example_plan(); e,c=signed(p); print(json.dumps(verify_test_fixture(json.dumps(e),p,c,TestReplayState(),NOW)))")
    if($LASTEXITCODE -ne 0){throw 'VM_TEST_SIGNATURE_FIXTURE_FAILED'}
    $r=($lines -join "`n")|ConvertFrom-Json
    if($r.status -cne 'BLOCKED' -or $r.authentication -cne 'TEST_KEY_ONLY' -or
       $r.signature_result -cne 'VERIFIED_PUBLIC_TEST_FIXTURE' -or $r.readiness_passed -ne $false -or
       $r.execution_authorized -ne $false -or $r.physical_ready -ne $false -or
       $r.verified_safety_cases -ne 0 -or @($r.negative_cases).Count -ne 12){throw 'VM_TEST_SIGNATURE_AUTHORITY_PROMOTION'}
    foreach($case in $r.negative_cases){if($case.execution -cne 'NOT_RUN' -or $case.assurance -cne 'BLOCKED_UNPROVEN'){throw 'VM_TEST_CASE_PROMOTION'}}
    Write-Output 'TEST signatures verified; TEST_KEY_ONLY/BLOCKED; 12 NOT_RUN; no physical authorization'
} finally { Pop-Location }
