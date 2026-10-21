# Hosted CI only: compilation plus fake APIs, no local LSA/token queries.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'HOSTED_CI_ONLY'
}
$tokens=$null; $errors=$null
foreach ($file in @(Get-ChildItem $PSScriptRoot -Filter '*.ps1')) {
    [void][System.Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors)
    if ($errors.Count) { throw 'PARSE_FAILED' }
}
$sources=@((Get-Content (Join-Path $PSScriptRoot 'LsaRights.cs') -Raw),
    (Get-Content (Join-Path $PSScriptRoot 'MockTests.cs') -Raw))
Add-Type -TypeDefinition ($sources -join "`n") -ErrorAction Stop
$count=[GridLab.LsaReadOnly.Tests.LsaMockTests]::RunAll()
if ($count -ne 30) { throw 'MOCK_COUNT_MISMATCH' }
. (Join-Path $PSScriptRoot 'Inventory.ps1')
$u1=[pscustomobject]@{Name='GridLabCollector';SID=[pscustomobject]@{Value='S-1-5-21-1-2-3-1003'}}
$u2=[pscustomobject]@{Name='GridLabStorage';SID=[pscustomobject]@{Value='S-1-5-21-1-2-3-1004'}}
$g=[pscustomobject]@{SID=[pscustomobject]@{Value='S-1-5-32-545'}}
$r=Get-LsaCandidateInventory -Users {$u1;$u2} -Groups {$g} -Members {param($group) $u1}
if ($r.candidates.Count -ne 3 -or $r.errors.Count -or $r.completeness -ne 'UNKNOWN') { throw 'GROUP_CANDIDATE' }
$r=Get-LsaCandidateInventory -Users {$u1;$u2} -Groups {} -Members {throw 'MUST_NOT_CALL'}
if ($r.candidates.Count -ne 2 -or $r.completeness -ne 'UNKNOWN') { throw 'EMPTY_GROUPS_NOT_EFFECTIVE_PROOF' }
foreach ($scenario in @('users','groups','members','duplicate','missing','invalid')) {
    $r=Get-LsaCandidateInventory -Users {
        if ($scenario -eq 'users') { throw 'synthetic private error' }
        if ($scenario -eq 'missing') { $u1; return }
        if ($scenario -eq 'duplicate') { $u1;$u1;return }
        if ($scenario -eq 'invalid') { [pscustomobject]@{Name='unexpected';SID=$u1.SID};$u2;return }
        $u1;$u2
    } -Groups { if ($scenario -eq 'groups') {throw 'group error'}; $g } -Members {throw 'members error'}
    if ($r.errors.Count -ne 1 -or $r.completeness -ne 'UNKNOWN') {throw 'INVENTORY_ERROR_NOT_BLOCKED'}
}
$plan=& (Join-Path $PSScriptRoot 'Get-LocalLogonRights.ps1') | ConvertFrom-Json
if ($plan.mode -ne 'PlanOnly' -or $plan.readiness -ne 'BLOCKED' -or
    $plan.effective_rights -ne 'UNKNOWN' -or $plan.execution_authorized -or $plan.records.Count) {
    throw 'PLAN_FAILED'
}
'LSA_MOCK_CASES=30; GROUP_CASES=8; PLAN_ONLY=1; NO_NATIVE_EXECUTION; NO_PHYSICAL_EVIDENCE'
