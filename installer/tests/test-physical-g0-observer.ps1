#Requires -Version 5.1
# All host providers mocked. This is not a physical observation.
$ErrorActionPreference='Stop'
Import-Module Microsoft.PowerShell.Utility
Import-Module Microsoft.PowerShell.Management
$global:G0Calls=0;$global:G0HashCalls=0;$global:G0Fault='none'
function Touch-G0 { $global:G0Calls++;if($global:G0Fault -eq 'provider'){throw 'PRIVATE_PROVIDER_VALUE'} }
function Get-CimInstance {[CmdletBinding()]param($ClassName,$OperationTimeoutSec)
 Touch-G0
 switch($ClassName){
 'Win32_OperatingSystem' {[pscustomobject]@{Version='10.0.26100';OSArchitecture='64-bit'}}
 'Win32_ComputerSystem' {[pscustomobject]@{TotalPhysicalMemory=32GB}}
 'Win32_Processor' {[pscustomobject]@{NumberOfLogicalProcessors=16}}
 'Win32_LogicalDisk' {[pscustomobject]@{DeviceID='C:';DriveType=3;FreeSpace=100GB}}
 'Win32_Service' {[pscustomobject]@{Name='sshd';State='Running';StartMode='Auto'}}
 'Win32_Process' {[pscustomobject]@{Name='python.exe';ProcessId=123;ParentProcessId=99;ExecutablePath='C:\Users\PrivateUser\python.exe';CreationDate=[datetime]::UtcNow;CommandLine=$(if($global:G0Fault -eq 'unknown'){$null}else{'python run_worker.py --token PRIVATE_TOKEN_VALUE'})}}
 default {throw 'UNEXPECTED_PROVIDER'}
 }
}
function Get-ItemProperty {[CmdletBinding()]param($LiteralPath,$Name) Touch-G0;[pscustomobject]@{MachineGuid='SYNTHETIC_GUID'}}
function Get-Command {[CmdletBinding()]param($Name,$CommandType) Touch-G0;[pscustomobject]@{Source='C:\fixture\tool.exe'}}
function Test-Path {[CmdletBinding()]param($LiteralPath,$PathType) Touch-G0;return $true}
function Get-Item {[CmdletBinding()]param($LiteralPath,[switch]$Force) Touch-G0;[pscustomobject]@{Attributes=$(if($global:G0Fault -eq 'reparse'){[IO.FileAttributes]::ReparsePoint}else{[IO.FileAttributes]::Directory});VersionInfo=[pscustomobject]@{ProductVersion='3.12.10'}}}
function Get-FileHash {[CmdletBinding()]param($LiteralPath,$Algorithm) $global:G0HashCalls++;Touch-G0;[pscustomobject]@{Hash=('a'*64)}}
function Get-NetTCPConnection {[CmdletBinding()]param($State) Touch-G0;[pscustomobject]@{LocalAddress='127.0.0.1';LocalPort=8765;OwningProcess=123}}
function Get-ScheduledTask {[CmdletBinding()]param() Touch-G0;[pscustomobject]@{TaskName='BybitClusterGridCoordinator';State='Running';Settings=[pscustomobject]@{Enabled=$true};Principal=[pscustomobject]@{UserId='SYSTEM'}}}
function Get-NetFirewallRule {[CmdletBinding()]param($Enabled) Touch-G0;[pscustomobject]@{Action='Allow';Direction='Inbound';Profile='Private'}}
function Get-LocalUser {[CmdletBinding()]param($Name) Touch-G0;[pscustomobject]@{Name=$Name;SID=[Security.Principal.SecurityIdentifier]::new('S-1-5-21-1-2-3-1003');Enabled=$false}}
function Get-LocalGroupMember {[CmdletBinding()]param($SID) Touch-G0;@()}
function Get-Acl {[CmdletBinding()]param($LiteralPath) Touch-G0;[pscustomobject]@{Owner='SYSTEM';AreAccessRulesProtected=$true;Access=@()}}
function Get-ChildItem {[CmdletBinding()]param($LiteralPath) Touch-G0;[pscustomobject]@{Name='POSTGRES_DSN';Value='PRIVATE_TOKEN_VALUE'}}
$path=Join-Path $PSScriptRoot '../collect-physical-g0.ps1'
$argsG0=@{NodeId='LS5';Head=('a'*40);RunId=('b'*32);SourcePath='C:\fixture-source'}
$tokens=$null;$parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$parseErrors)
if($parseErrors.Count){throw 'G0_SOURCE_PARSE_FAILED'}
$allowed=@('Set-StrictMode','ConvertTo-Json','Row','Observe','Get-ItemProperty','Digest','Get-CimInstance','Measure-Object','Where-Object','ForEach-Object','Get-Command','Get-Item','Public-Path','Get-NetTCPConnection','Get-ScheduledTask','Get-NetFirewallRule','Join-Path','Test-Path','Get-Acl','Get-LocalGroupMember','Get-LocalUser','Get-ChildItem','Get-FileHash','Require-LocalPath')
foreach($cmd in $ast.FindAll({param($n) $n -is [Management.Automation.Language.CommandAst]},$true)){
 $name=$cmd.GetCommandName()
 if($null -eq $name){if($cmd.CommandElements[0].Extent.Text -cne '$Provider'){throw 'UNREVIEWED_DYNAMIC_COMMAND'}}
 elseif($name -notin $allowed){throw 'UNREVIEWED_G0_COMMAND'}
}
foreach($type in $ast.FindAll({param($n) $n -is [Management.Automation.Language.TypeExpressionAst]},$true)){
 if($type.TypeName.FullName -match '(?i)(Diagnostics[.]Process|Net[.]|IO[.]File(Stream)?)$'){throw 'G0_PROCESS_NETWORK_OR_WRITE_TYPE'}
}
$r=(& $path @argsG0)|ConvertFrom-Json
if($r.status -ne 'PLAN_ONLY' -or $global:G0Calls -ne 0){throw 'DEFAULT_PERFORMED_HOST_OBSERVATION'}
$r=(& $path @argsG0 -Mode ReadOnly)|ConvertFrom-Json
if($r.status -ne 'BLOCKED' -or $global:G0Calls -ne 0){throw 'MISSING_APPROVAL_NOT_BLOCKED'}
$count=3
foreach($case in @('none','provider','unknown','reparse','unc-source')){
 $global:G0Fault=$case;$global:G0HashCalls=0
 $argsG0.SourcePath=if($case -eq 'unc-source'){'\\untrusted\share'}else{'C:\fixture-source'}
 $raw=(& $path @argsG0 -Mode ReadOnly -G0Approved|Out-String)
 if($raw -match 'PRIVATE_TOKEN_VALUE|PRIVATE_PROVIDER_VALUE|PrivateUser'){throw 'PRIVATE_DATA_LEAK'}
 $r=$raw|ConvertFrom-Json
 if($r.g1_authorized -ne $false -or $r.g2_authorized -ne $false){throw 'FALSE_AUTHORITY'}
 if($case -eq 'provider' -and $r.checks.processes.status -ne 'BLOCKED'){throw 'PROVIDER_FAILED_OPEN'}
 if($case -eq 'unknown' -and $r.checks.processes.status -ne 'BLOCKED'){throw 'UNKNOWN_PROCESS_FAILED_OPEN'}
 if($case -eq 'reparse' -and $r.checks.paths.status -ne 'FAIL'){throw 'REPARSE_FAILED_OPEN'}
 if($case -in @('unc-source','reparse') -and $global:G0HashCalls -ne 0){throw 'UNTRUSTED_SOURCE_WAS_HASHED'}
 if($case -eq 'none' -and $r.checks.processes.data[0].grid_candidate -ne $true){throw 'GRID_PROCESS_NOT_CLASSIFIED'}
 $count++
}
Write-Output "G0 mocked-provider cases passed: $count; no host observations or process execution"
