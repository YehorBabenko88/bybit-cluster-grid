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
 $modes=if($case -ceq 'partial-error'){@('throw','warning')}else{@('none')}
 foreach($failureMode in $modes){
 $r=Get-G0IdentityBinding -CollectorSid $(if($case -ceq 'unknown-pin'){'unknown'}else{$one}) -StorageSid $two -Query {param($n)
  if($case -ceq 'missing'){return};$sid=if($n -ceq 'GridLabCollector'){$one}else{$two};if($case -ceq 'wrong-sid'){$sid=$two};$name=if($case -ceq 'wrong-name'){'other'}else{$n};$u=[pscustomobject]@{Name=$name;SID=[pscustomobject]@{Value=$sid}};$u;if($case -ceq 'duplicate'){$u};if($case -ceq 'partial-error'){if($failureMode -ceq 'warning'){Write-Warning 'SYNTHETIC_PARTIAL_WARNING'}else{throw 'SYNTHETIC_PRIVATE_ERROR'}}
 }
 if($r.complete -ne ($case -ceq 'valid') -or (-not $r.complete -and $r.identities.Count -ne 0)){throw 'IDENTITY_NOT_FAIL_CLOSED'}
 };$cases+=('identity-'+$case)
}
$layouts=@()
foreach($layout in @('manifest','versioned-binary','missing','ambiguous','provider-error')){
 $selected=$null;$blocked=$false
 try{$selected=Get-G0OsModulePath -TestFile {param($p) if($layout -ceq 'provider-error'){throw 'SYNTHETIC_ACCESS_DENIED'};if($layout -ceq 'ambiguous'){return $true};if($layout -ceq 'manifest'){return $p.EndsWith('.psd1')};if($layout -ceq 'versioned-binary'){return $p.EndsWith('1.0.0.0\Microsoft.Powershell.LocalAccounts.dll')};return $false}}catch{$blocked=$true}
 if($layout -cin @('manifest','versioned-binary')){if($blocked -or -not $selected){throw 'SUPPORTED_LAYOUT_BLOCKED'}}else{if(-not $blocked){throw 'UNKNOWN_LAYOUT_ACCEPTED'}}
 $layouts+=('module-'+$layout)
}
$attributeCases=@()
foreach($attributeCase in @('normal','file-reparse','ancestor-reparse','file-directory','access-denied','file-missing')){
 $ok=$false;$blocked=$false
 try{$ok=Test-G0OsModuleFile -Path 'C:\G0Fake\module.dll' -ReadAttributes {param($p)
  if($attributeCase -ceq 'access-denied'){throw [UnauthorizedAccessException]::new('SYNTHETIC')}
  if($attributeCase -ceq 'file-missing'){throw [IO.FileNotFoundException]::new('SYNTHETIC')}
  if($p.EndsWith('module.dll')){if($attributeCase -ceq 'file-reparse'){return [IO.FileAttributes]::ReparsePoint};if($attributeCase -ceq 'file-directory'){return [IO.FileAttributes]::Directory};return [IO.FileAttributes]::Normal}
  if($attributeCase -ceq 'ancestor-reparse'){return ([IO.FileAttributes]::Directory -bor [IO.FileAttributes]::ReparsePoint)}
  return [IO.FileAttributes]::Directory
 }}catch{$blocked=$true}
 if($attributeCase -ceq 'normal'){if($blocked -or -not $ok){throw 'NORMAL_ATTRIBUTE_BLOCKED'}}elseif($attributeCase -ceq 'file-missing'){if($blocked -or $ok){throw 'MISSING_ATTRIBUTE_NOT_FALSE'}}else{if(-not $blocked){throw 'UNSAFE_ATTRIBUTE_ACCEPTED'}}
 $attributeCases+=('module-file-'+$attributeCase)
}
[pscustomobject]@{schema=1;kind='SYNTHETIC_FAKE_API_ONLY';legacy_cases=30;cases=@($names)+@($cases)+@('plan-only')+@($layouts)+@($attributeCases);physical='0/10 NOT_RUN';execute_authorized=$false;cleanup_authorized=$false;actor_tokens_created=$false}|ConvertTo-Json -Depth 5 -Compress
