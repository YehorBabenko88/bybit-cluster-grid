param([Parameter(Mandatory=$true)][string]$TestAssembly)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if([Environment]::MachineName -ieq 'PC4'){throw 'PC4_BUILD_OR_TEST_EXECUTION_FORBIDDEN'}
[void][Reflection.Assembly]::Load([IO.File]::ReadAllBytes($TestAssembly))
if([GridLab.LsaReadOnly.Tests.LsaMockTests]::RunAll() -ne 30){throw 'LEGACY_MOCKS_FAILED'}
$names=@([GridLab.LsaReadOnly.Tests.G0MockTests]::RunAll());if($names.Count -ne 6){throw 'G0_MOCKS_FAILED'}
$plan=(& (Join-Path $PSScriptRoot 'Read-G0LsaMemory.ps1')|ConvertFrom-Json)
if($plan.mode -cne 'PlanOnly' -or $plan.collection -cne 'BLOCKED' -or $plan.subjects.Count -ne 0 -or $plan.execution_authorized -or $plan.actor_tokens_created){throw 'DEFAULT_NATIVE_CALL'}
# Dot source only the PlanOnly definitions, no native observation or account provider.
[void](. (Join-Path $PSScriptRoot 'Read-G0LsaMemory.ps1'))
$one='S-1-5-21-1-2-3-1003';$two='S-1-5-21-1-2-3-1004'
$cases=@()
foreach($case in @('valid','wrong-sid','wrong-name','missing','partial-error','duplicate','unknown-pin')){
 $r=Get-G0IdentityBinding -CollectorSid $(if($case -ceq 'unknown-pin'){'unknown'}else{$one}) -StorageSid $two -Query {param($n)
  if($case -ceq 'missing'){return};$sid=if($n -ceq 'GridLabCollector'){$one}else{$two};if($case -ceq 'wrong-sid'){$sid=$two};$name=if($case -ceq 'wrong-name'){'other'}else{$n};$u=[pscustomobject]@{Name=$name;SID=[pscustomobject]@{Value=$sid}};$u;if($case -ceq 'duplicate'){$u};if($case -ceq 'partial-error'){throw 'SYNTHETIC_PRIVATE_ERROR'}
 }
 if($r.complete -ne ($case -ceq 'valid') -or (-not $r.complete -and $r.identities.Count -ne 0)){throw 'IDENTITY_NOT_FAIL_CLOSED'};$cases+=('identity-'+$case)
}
[pscustomobject]@{schema=1;kind='SYNTHETIC_FAKE_API_ONLY';legacy_cases=30;cases=@($names)+@($cases)+@('plan-only');physical='0/10 NOT_RUN';execute_authorized=$false;cleanup_authorized=$false;actor_tokens_created=$false}|ConvertTo-Json -Depth 5 -Compress
