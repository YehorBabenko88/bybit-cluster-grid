#Requires -Version 5.1
$ErrorActionPreference='Stop'
$collector=Join-Path $PSScriptRoot '../collect-physical-node.ps1'
$global:PhysicalCase='plan';$global:PhysicalCalls=0
function Get-ScheduledTask {[CmdletBinding()]param() $global:PhysicalCalls++;if($global:PhysicalCase -eq 'task'){[pscustomobject]@{TaskName='BybitClusterGridAgent';State='Running'}}}
function Get-CimInstance {
 [CmdletBinding()]param($ClassName,$OperationTimeoutSec,$Filter)
 $global:PhysicalCalls++
 if($global:PhysicalCase -eq 'provider'){throw 'PRIVATE_DIAGNOSTIC_MUST_NOT_LEAK'}
 switch($ClassName){
 'Win32_Process' {if($global:PhysicalCase -eq 'process'){[pscustomobject]@{Name='python.exe';CommandLine=$null}}else{[pscustomobject]@{Name='System';CommandLine=$null}}}
 'Win32_OperatingSystem' {[pscustomobject]@{Version='10.0.26100';OSArchitecture='64-bit'}}
 'Win32_ComputerSystem' {[pscustomobject]@{Name='LAB0';TotalPhysicalMemory=[long](8GB)}}
 'Win32_Processor' {[pscustomobject]@{NumberOfLogicalProcessors=4}}
 'Win32_LogicalDisk' {[pscustomobject]@{FreeSpace=[long](40GB)}}
 'Win32_Service' {[pscustomobject]@{Name='Tailscale';State='Running';StartMode='Auto'}}
 default {throw 'Unexpected class'}
 }
}
function Get-PSDrive {[CmdletBinding()]param($Name,$PSProvider) @{Free=40GB;Used=1GB}}
function Get-Command {[CmdletBinding()]param($Name)
 $global:PhysicalCalls++
 if($global:PhysicalCase -eq 'tool'){throw 'PRIVATE_DIAGNOSTIC_MUST_NOT_LEAK'}
 [pscustomobject]@{Source=('C:\fixture-tools\'+$Name)}
}
function Get-Item {[CmdletBinding()]param($LiteralPath,$Path,[switch]$Force)
 $v=if(($LiteralPath+$Path) -match 'psql'){'16.4'}else{'3.12.10'}
 $attrs=if($global:PhysicalCase -eq 'reparse' -and ($LiteralPath+$Path) -eq 'C:\GridLab'){[IO.FileAttributes]::ReparsePoint}else{[IO.FileAttributes]::Normal}
 [pscustomobject]@{Attributes=$attrs;VersionInfo=[pscustomobject]@{ProductVersion=$v}}
}
function Test-Path {
 [CmdletBinding()]param($LiteralPath,$Path,$PathType)
 if($LiteralPath -eq 'C:\GridLab'){return $true}
 if($LiteralPath -like 'C:\GridLab\*'){return $false}
 Microsoft.PowerShell.Management\Test-Path @PSBoundParameters
}
$env:COMPUTERNAME='LAB0'
$run='1234567890abcdef1234567890abcdef'
$planned='C:\GridLab\'+$run+'\LAB0'
$argsCollect=@{NodeId='LAB0';PlannedRoot=$planned;Address='100.64.0.1';Role='CONTROL'}
$r=(& $collector @argsCollect)|ConvertFrom-Json
if($r.status -cne 'PLAN_ONLY' -or $global:PhysicalCalls -ne 0){throw 'Default mode probed host'}
$count=1
foreach($case in @('valid','task','process','provider','tool','reparse')){
 $global:PhysicalCase=$case
 $blocked=$false;$r=$null
 try {$r=(& $collector @argsCollect -Mode ReadOnly)|ConvertFrom-Json} catch {$blocked=$true;if($_.Exception.Message -match 'PRIVATE'){throw 'Provider leaked diagnostics'}}
 if($case -eq 'valid'){
  if($blocked -or $r.status -cne 'SNAPSHOT_ONLY' -or $r.node.cpu_logical -ne 4 -or $r.node.postgres_major -ne 16 -or $r.execution_authorized -ne $false){throw 'Invalid inventory snapshot'}
 } elseif(!$blocked){throw "Unsafe inventory accepted:$case"}
 $count++
}
Write-Output "Physical inventory safety fixtures passed: $count; all OS/tool providers mocked"

