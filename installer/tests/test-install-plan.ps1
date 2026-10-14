param([string]$ScriptPath=(Join-Path $PSScriptRoot '..\install.ps1'))
$ErrorActionPreference='Stop'
# Execute the historical script under mocked providers, never administrator OS operations.
$source=(Get-Content -LiteralPath $ScriptPath -Raw) -replace '(?m)^#Requires -RunAsAdministrator\s*',''
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('grid-install-plan-'+[guid]::NewGuid().ToString('N')+'.ps1')
[IO.File]::WriteAllText($fixture,$source)
$global:GridInstallMutation=$false
function New-Item {param($ItemType,[switch]$Force,$Path) $global:GridInstallMutation=$true;throw 'Unexpected default mutation'}
function Register-ScheduledTask {$global:GridInstallMutation=$true;throw 'Unexpected task registration'}
function Start-ScheduledTask {$global:GridInstallMutation=$true;throw 'Unexpected task start'}
function Unregister-ScheduledTask {$global:GridInstallMutation=$true;throw 'Unexpected task removal'}
$result=& $fixture -ReleaseDir 'C:\fixture\release' -Python 'C:\fixture\python.exe' -Mode CONTROL
if($global:GridInstallMutation -or ($result | Out-String) -notmatch 'PLAN_ONLY') {throw 'Installer default must be plan-only'}
Write-Output 'Installer plan fixture passed; no OS state changed'
