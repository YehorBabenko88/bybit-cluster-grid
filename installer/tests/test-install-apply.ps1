$ErrorActionPreference='Stop'
# Run only on administrator Windows CI. Every Scheduler operation is mocked;
# all file writes stay in this newly created fixture. No real .env or services.
$principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if(!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Apply fixture requires elevated Windows CI'}
$root=Join-Path ([IO.Path]::GetTempPath()) ('grid-install-apply-'+[guid]::NewGuid().ToString('N'))
$release=Join-Path $root 'release'
[void][IO.Directory]::CreateDirectory((Join-Path $release 'installer'))
foreach($name in @('release-runtime-guard.ps1','recover-release.ps1','launcher.ps1','archive-launcher.ps1','uninstall.ps1','preflight.ps1','coordinator-launcher.ps1')){
 [IO.File]::WriteAllText((Join-Path $release ('installer\'+$name)),'# fixture only')
}
[IO.File]::WriteAllText((Join-Path $release 'release-manifest.json'),('{"version":"'+('a'*40)+'"}'))
$oldProgramFiles=$env:ProgramFiles;$oldProgramData=$env:ProgramData
$env:ProgramFiles=Join-Path $root 'programfiles';$env:ProgramData=Join-Path $root 'programdata'
$global:GridFixtureTasks=@();$global:GridFixtureRegistrations=0;$global:GridFixturePreflight=2
function Get-ScheduledTask {[CmdletBinding()]param() $global:GridFixtureTasks}
function New-ScheduledTaskAction {param($Execute,$Argument,$WorkingDirectory) @{Execute=$Execute;Argument=$Argument}}
function New-ScheduledTaskTrigger {param([switch]$AtStartup) @{AtStartup=$true}}
function New-ScheduledTaskPrincipal {param($UserId,$LogonType,$RunLevel) @{UserId=$UserId}}
function New-ScheduledTaskSettingsSet {
 param($RestartCount,$RestartInterval,[switch]$StartWhenAvailable)
 [pscustomobject]@{Enabled=$true;DisallowStartIfOnBatteries=$true;StopIfGoingOnBatteries=$true;MultipleInstances='Parallel'}
}
function Register-ScheduledTask {
 [CmdletBinding()]param($TaskName,$Action,$Trigger,$Principal,$Settings,$Xml,[switch]$Force)
 if($TaskName -ne 'BybitClusterGridCoordinator'){throw 'Unexpected task role or archive registration'}
 if(!$Xml -and $Settings.Enabled -ne $false){throw 'Registered task must be disabled'}
 if($Xml -and $Xml -notmatch '<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>'){throw 'Execution duration not verified'}
 $global:GridFixtureRegistrations++
 $global:GridFixtureTasks=@([pscustomobject]@{TaskName=$TaskName;State='Disabled'})
}
function Export-ScheduledTask {[CmdletBinding()]param($TaskName) '<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Settings><Enabled>false</Enabled><ExecutionTimeLimit>PT0S</ExecutionTimeLimit></Settings></Task>'}
function Start-ScheduledTask {throw 'Task must never be started'}
function Unregister-ScheduledTask {throw 'Task must never be removed'}
function Invoke-FixturePython {
 if($args -notcontains '--check-db'){throw 'CONTROL registration omitted read-only DB preflight'}
 $global:LASTEXITCODE=$global:GridFixturePreflight
 '{"status":"BLOCKED"}'
}
$script=Join-Path $PSScriptRoot '..\install.ps1'
try {
 $rejected=$false
 try {& $script -ReleaseDir $release -Python Invoke-FixturePython -Mode CONTROL -Apply} catch {$rejected=$true}
 if(!$rejected -or $global:GridFixtureRegistrations -ne 0 -or (Test-Path -LiteralPath $env:ProgramData)){throw 'Failed preflight caused install mutation'}
 $global:GridFixturePreflight=0
 & $script -ReleaseDir $release -Python Invoke-FixturePython -Mode CONTROL -Apply
 if($global:GridFixtureRegistrations -ne 2){throw 'Expected registration plus execution-limit verification'}
 $rejected=$false
 try {& $script -ReleaseDir $release -Python Invoke-FixturePython -Mode CONTROL -Apply} catch {$rejected=$true}
 if(!$rejected -or $global:GridFixtureRegistrations -ne 2){throw 'Existing task was overwritten or removed'}
 Write-Output 'Apply fixture passed; disabled task registration only; no real Scheduler calls'
} finally {$env:ProgramFiles=$oldProgramFiles;$env:ProgramData=$oldProgramData}
