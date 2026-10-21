#Requires -Version 5.1
# Pure policy tests. No native DLL, accounts, credentials, processes or resources.
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')
$script:count=0
function Check([bool]$Ok){if(!$Ok){throw 'OFFLINE_ASSERT_FAILED'};$script:count++}
function Reject([scriptblock]$Action){$failed=$false;try{& $Action|Out-Null}catch{$failed=$true};Check $failed}
$run='77777777-7777-4777-8777-777777777777'
$plan=& (Join-Path $PSScriptRoot 'Invoke-Pc4SidAcl.ps1')
Check ($plan.mode -ceq 'PlanOnly' -and $plan.execution_authorized -eq $false)
Reject {& (Join-Path $PSScriptRoot 'Invoke-Pc4SidAcl.ps1') -PlanOnly -Execute}
Reject {& (Join-Path $PSScriptRoot 'Invoke-Pc4SidAcl.ps1') -PlanOnly -Cleanup}
Reject {& (Join-Path $PSScriptRoot 'Invoke-Pc4SidAcl.ps1') -Execute -Cleanup}
Check ((Get-Pc4Paths $run 'Collector').Root -ceq ('C:\GridLab\Secure\Collector\sid-acl-'+$run))
Reject {Get-Pc4Paths '..\other' 'Collector'}
Reject {Get-Pc4Paths $run 'Other'}
Reject {Assert-Pc4Sid '1003' '1003'}
$facts=[pscustomobject]@{sid='S-1-5-21-1-2-3-1003';admin_group=$false;elevated=$false;integrity_rid=8192;impersonating=$false;privileges=@([pscustomobject]@{name='SeChangeNotifyPrivilege';enabled=$true})}
Check (Test-Pc4Facts $facts $facts.sid)
Check (!(Test-Pc4Facts $facts 'S-1-5-21-1-2-3-1004'))
foreach($key in @('admin_group','elevated','impersonating')){$facts.$key=$true;Check (!(Test-Pc4Facts $facts $facts.sid));$facts.$key=$false}
$facts.integrity_rid=12288;Check (!(Test-Pc4Facts $facts $facts.sid));$facts.integrity_rid=8192
$facts.privileges=@([pscustomobject]@{name='SeDebugPrivilege';enabled=$false});Check (!(Test-Pc4Facts $facts $facts.sid))
$marker=[pscustomobject]@{kind='PC4_DISPOSABLE_FIXTURE';run_id=$run;role='Collector'}
$entries=@([pscustomobject]@{Name='fixture.json';PSIsContainer=$false;Attributes=0},[pscustomobject]@{Name='canary.txt';PSIsContainer=$false;Attributes=0})
Check (@(Get-Pc4CleanupNames $run 'Collector' $marker $entries $true).Count -eq 1)
# Partial cleanup: remaining marker alone is safe to plan; missing marker blocks.
Check (@(Get-Pc4CleanupNames $run 'Collector' $marker @($entries[0]) $true).Count -eq 0)
Reject {Get-Pc4CleanupNames $run 'Collector' $marker @($entries[1]) $true}
Reject {Get-Pc4CleanupNames $run 'Collector' $marker $entries $false}
Reject {Get-Pc4CleanupNames $run 'Storage' $marker $entries $true}
Reject {Get-Pc4CleanupNames $run 'Collector' $marker @($entries[0],$entries[1],$entries[1]) $true}
$entries[1].Name='existing-production.data';Reject {Get-Pc4CleanupNames $run 'Collector' $marker $entries $true}
$entries[1].Name='canary.txt';$entries[1].Attributes=1024;Reject {Get-Pc4CleanupNames $run 'Collector' $marker $entries $true}
$entries[1].Attributes=0;$entries[1].PSIsContainer=$true;Reject {Get-Pc4CleanupNames $run 'Collector' $marker $entries $true}
foreach($v in @('false',0,$null)){Reject {Get-Pc4CleanupNames $run 'Collector' $marker $entries $v}}
$null=Assert-Pc4FreshScope $true $true $true;Check $true
Reject {Assert-Pc4FreshScope $false $true $true}
Reject {Assert-Pc4FreshScope $true $false $true}
Reject {Assert-Pc4FreshScope $true $true $false}
Reject {Assert-Pc4FreshScope 'true' $true $true}
Write-Output ('OFFLINE_POLICY_CASES='+$script:count+'; NO_NATIVE_EXECUTION; NO_PHYSICAL_EVIDENCE')
