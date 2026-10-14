$ErrorActionPreference='Stop'
$root=Join-Path ([IO.Path]::GetTempPath()) ('grid-rollback-fixture-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($root)
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '..\rollback-release.ps1') -Destination (Join-Path $root 'rollback-release.ps1')
[IO.File]::WriteAllText((Join-Path $root 'switch-release.ps1'), 'param($Version,$InstallRoot,$Role,[switch]$Apply);$global:GridSwitchCalls++;$global:GridSwitchApplied=[bool]$Apply')
$global:GridSwitchCalls=0;$global:GridSwitchApplied=$false;$global:GridSyntheticExit=0
$global:GridSyntheticTasks=@();$global:GridSyntheticProcesses=@()
function Invoke-SyntheticPreflight {$global:LASTEXITCODE=$global:GridSyntheticExit;'{}'}
function Get-ScheduledTask {[CmdletBinding()]param() $global:GridSyntheticTasks}
function Get-CimInstance {[CmdletBinding()]param($ClassName) $global:GridSyntheticProcesses}
$script=Join-Path $root 'rollback-release.ps1'
1..2 | ForEach-Object {& $script -ReviewedVersion ('a'*40) -Python Invoke-SyntheticPreflight -InstallRoot $root -DataRoot $root}
if($global:GridSwitchCalls -ne 2 -or $global:GridSwitchApplied){throw 'Rollback plan was not repeatable/read-only'}
$global:GridSyntheticExit=2
$rejected=$false
try {& $script -ReviewedVersion ('a'*40) -Python Invoke-SyntheticPreflight -InstallRoot $root -DataRoot $root -Apply} catch {$rejected=$true}
if(!$rejected -or $global:GridSwitchCalls -ne 2){throw 'Failed preflight did not block rollback'}
$global:GridSyntheticExit=0
$global:GridSyntheticTasks=@([pscustomobject]@{TaskName='BybitClusterGridCoordinator';State='Running'})
$rejected=$false
try {& $script -ReviewedVersion ('a'*40) -Python Invoke-SyntheticPreflight -InstallRoot $root -DataRoot $root -Apply} catch {$rejected=$true}
if(!$rejected -or $global:GridSwitchCalls -ne 2){throw 'Running task did not block rollback'}
$global:GridSyntheticTasks=@()
$global:GridSyntheticProcesses=@([pscustomobject]@{CommandLine='python run_coordinator.py'})
$rejected=$false
try {& $script -ReviewedVersion ('a'*40) -Python Invoke-SyntheticPreflight -InstallRoot $root -DataRoot $root -Apply} catch {$rejected=$true}
if(!$rejected -or $global:GridSwitchCalls -ne 2){throw 'Old coordinator process did not block rollback'}
$global:GridSyntheticProcesses=@()
$global:GridSyntheticProcesses=@([pscustomobject]@{Name='python.exe';CommandLine=$null})
$rejected=$false
try {& $script -ReviewedVersion ('a'*40) -Python Invoke-SyntheticPreflight -InstallRoot $root -DataRoot $root -Apply} catch {$rejected=$true}
if(!$rejected -or $global:GridSwitchCalls -ne 2){throw 'Unreadable Python process identity did not block rollback'}
$global:GridSyntheticProcesses=@()
& $script -ReviewedVersion ('a'*40) -Python Invoke-SyntheticPreflight -InstallRoot $root -DataRoot $root -Apply
if($global:GridSwitchCalls -ne 3 -or !$global:GridSwitchApplied){throw 'Verified explicit pointer switch was not invoked'}
Write-Output 'Rollback fixture passed; all task/process/switch providers synthetic'
