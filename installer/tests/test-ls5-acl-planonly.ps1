#Requires -Version 5.1
# Pure entry-point tests: no host providers may be invoked.
$ErrorActionPreference='Stop';$script:count=0;$script:prohibited=0
function Check([bool]$Ok){if(!$Ok){throw 'PLAN_ONLY_ASSERT_FAILED'};$script:count++}
function Reject([scriptblock]$Action,[string]$Code){
 $message='';try{& $Action|Out-Null}catch{$message=$_.Exception.Message}
 Check ($message.Contains($Code))
}
function New-Item {$script:prohibited++;throw 'FORBIDDEN_HOST_CALL'}
function Get-Acl {$script:prohibited++;throw 'FORBIDDEN_HOST_CALL'}
function Set-Acl {$script:prohibited++;throw 'FORBIDDEN_HOST_CALL'}
function Get-ScheduledTask {$script:prohibited++;throw 'FORBIDDEN_HOST_CALL'}
function Get-LocalUser {$script:prohibited++;throw 'FORBIDDEN_HOST_CALL'}
$root=Split-Path $PSScriptRoot -Parent
foreach($name in @('bootstrap.ps1','bootstrap-ml.ps1','protect-service.ps1')){
 $result=@(& (Join-Path $root $name));Check ($result.Count -eq 1 -and $result[0].StartsWith('PLAN_ONLY'))
 Reject {& (Join-Path $root $name) -Apply} 'LS5_ACL_EXECUTE_NOT_AUTHORIZED'
}
$result=@(& (Join-Path $root 'install.ps1') -ReleaseDir 'X:\SYNTHETIC' -Python 'X:\SYNTHETIC\python.exe')
Check ($result.Count -eq 1 -and $result[0].StartsWith('PLAN_ONLY'))
Reject {& (Join-Path $root 'install.ps1') -ReleaseDir 'X:\SYNTHETIC' -Python 'X:\SYNTHETIC\python.exe' -Apply} 'LS5_ACL_EXECUTE_NOT_AUTHORIZED'
Reject {& (Join-Path $root 'stage-github-release.ps1') -Download} 'LS5_ACL_EXECUTE_NOT_AUTHORIZED'
$result=& (Join-Path $root 'ls5-acl-remediation.ps1')
Check ($result.mode -ceq 'PlanOnly' -and $result.status -ceq 'BLOCKED' -and !$result.host_verified)
Reject {& (Join-Path $root 'ls5-acl-remediation.ps1') -Apply} 'EXECUTE_NOT_AUTHORIZED'
Reject {& (Join-Path $root 'ls5-acl-remediation.ps1') -Rollback} 'ROLLBACK_NOT_AUTHORIZED'
Check ($script:prohibited -eq 0)
Write-Output ('LS5_PLAN_ONLY_CASES='+$script:count+'; NO_HOST_OBSERVATIONS; NO_AUTHORITY')
