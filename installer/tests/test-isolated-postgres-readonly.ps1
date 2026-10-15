#Requires -Version 5.1
param([switch]$EmitSnapshot,[string]$EvidencePlanHash=('b'*64))
$ErrorActionPreference='Stop'
$core=Join-Path $PSScriptRoot '../isolated-postgres-readonly-core.ps1'
if(!(Test-Path -LiteralPath $core)){throw 'PG_READ_ONLY_MODULE_MISSING'}
. $core
$global:PgCase='safe';$global:PgProbes=0
$sid='S-1-5-21-100-200-300-1001'
$run='a'*32;$root='C:\GridLab\'+$run+'\LAB01\pgdata'
function Get-ScheduledTask {[CmdletBinding()]param()
 $global:PgProbes++
 if($global:PgCase -eq 'task-error'){throw 'PRIVATE_SECRET'}
 if($global:PgCase -eq 'active'){[pscustomobject]@{TaskName='BybitClusterGridAgent';State='Ready'}}
 if($global:PgCase -eq 'task-pg-noext'){[pscustomobject]@{TaskName='Other';State='Disabled';Actions=@([pscustomobject]@{Execute='C:\pg\postgres';Arguments='';WorkingDirectory=''})}}
 if($global:PgCase -eq 'task-pg'){[pscustomobject]@{TaskName='Other';State='Disabled';Actions=@([pscustomobject]@{Execute='C:\pg\postgres.exe';Arguments='';WorkingDirectory=''})}}
}
function Get-CimInstance {[CmdletBinding()]param($ClassName,$Filter,$OperationTimeoutSec)
 $global:PgProbes++
 if($global:PgCase -eq 'cim-error'){throw 'PRIVATE_SECRET'}
 switch($ClassName){
 'Win32_ComputerSystem' {[pscustomobject]@{Name=$(if($global:PgCase -eq 'wrong-node'){'LS5'}else{'LAB01'})}}
 'Win32_LogicalDisk' {[pscustomobject]@{DriveType=$(if($global:PgCase -eq 'mapped'){4}else{3})}}
 'Win32_Volume' {
  if($global:PgCase -eq 'volume-error'){throw 'PRIVATE_SECRET'}
  if($global:PgCase -eq 'subst'){return}
  [pscustomobject]@{DriveLetter='C:';DriveType=3;DeviceID=$(if($global:PgCase -eq 'volume-identity'){'C:\production'}else{'\\?\Volume{12345678-1234-1234-1234-123456789abc}\'})}
 }
 'Win32_Process' {
  if($global:PgCase -eq 'pg-process'){[pscustomobject]@{Name='postgres.exe';CommandLine='postgres -D C:\unrelated';ProcessId=123}}
  elseif($global:PgCase -eq 'unknown-python'){[pscustomobject]@{Name='python.exe';CommandLine=$null;ProcessId=123}}
  else{[pscustomobject]@{Name='System';CommandLine=$null;ProcessId=4}}
 }
 'Win32_Service' {
  if($global:PgCase -eq 'service-error'){throw 'PRIVATE_SECRET'}
  [pscustomobject]@{Name='Other';PathName=$(if($global:PgCase -eq 'pg-service-noext'){'C:\pg\pg_ctl runservice'}elseif($global:PgCase -eq 'pg-service'){'C:\pg\pg_ctl.exe runservice'}elseif($global:PgCase -eq 'unknown-service'){$null}else{'C:\Windows\other.exe'})}
 }
 default {throw 'UNEXPECTED_PROVIDER'}
 }
}
function Get-NetTCPConnection {[CmdletBinding()]param()
 $global:PgProbes++
 if($global:PgCase -eq 'tcp-error'){throw 'PRIVATE_SECRET'}
 if($global:PgCase -eq 'port'){[pscustomobject]@{LocalPort=25432}}
}
function Get-NetUDPEndpoint {[CmdletBinding()]param()
 $global:PgProbes++
 if($global:PgCase -eq 'udp-error'){throw 'PRIVATE_SECRET'}
}
function Get-Item {[CmdletBinding()]param($LiteralPath,[switch]$Force)
 $global:PgProbes++
 if($global:PgCase -eq 'path-error'){throw 'PRIVATE_SECRET'}
 if($LiteralPath -like 'C:\GridLab\*'){
  if($global:PgCase -notin @('existing','hardlink')){throw [Management.Automation.ItemNotFoundException]::new('fixture absent')}
 }
 [pscustomobject]@{FullName=$LiteralPath;PSIsContainer=($global:PgCase -ne 'hardlink');
  LinkType=$(if($global:PgCase -eq 'hardlink'){'HardLink'}else{''});
  Attributes=$(if($global:PgCase -eq 'junction' -and $LiteralPath -eq 'C:\GridLab'){[IO.FileAttributes]::ReparsePoint}else{[IO.FileAttributes]::Directory})}
}
function Get-Acl {[CmdletBinding()]param($LiteralPath)
 $global:PgProbes++
 if($global:PgCase -eq 'acl-error'){throw 'PRIVATE_SECRET'}
 $acl=[Security.AccessControl.DirectorySecurity]::new()
 if($global:PgCase -in @('generic-write','generic-all','unsupported-right')){
  $right=if($global:PgCase -eq 'generic-write'){'GW'}elseif($global:PgCase -eq 'unsupported-right'){'0x02000000'}else{'GA'}
  $acl.SetSecurityDescriptorSddlForm(('O:'+$sid+'G:SYD:P(A;;'+$right+';;;WD)'));return $acl
 }
 $acl.SetOwner([Security.Principal.SecurityIdentifier]::new($(if($global:PgCase -eq 'owner'){'S-1-5-18'}else{$sid})))
 $acl.SetAccessRuleProtection(($global:PgCase -ne 'inherited'),$false)
 $writer=if($global:PgCase -eq 'everyone'){'S-1-1-0'}else{$sid}
 $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new($writer),[Security.AccessControl.FileSystemRights]::Modify,[Security.AccessControl.AccessControlType]::Allow))
 $acl
}
$argsPg=@{DataRoot=$root;RunId=$run;NodeId='LAB01';Port=25432;Commit=('a'*40);PlanSha256=$EvidencePlanHash;OwnerSid=$sid}
$entry=Join-Path $PSScriptRoot '../isolated-postgres-readonly.ps1'
$p=(& $entry @argsPg)|ConvertFrom-Json
if($p.status -ne 'PLAN_ONLY' -or $global:PgProbes -ne 0){throw 'Default mode probed host'}
$r=Get-GridPostgresEvidence @argsPg
if($r.status -ne 'SNAPSHOT_ONLY' -or !$r.root_absent -or $r.acl.owner_sid -ne $sid -or $r.commit_sha -ne ('a'*40)){throw ('Safe metadata fixture failed: '+$r.code)}
if($EmitSnapshot){$r|ConvertTo-Json -Depth 10 -Compress;return}
$count=2
foreach($case in @('task-error','active','task-pg','cim-error','wrong-node','mapped','pg-process','unknown-python','pg-service','unknown-service','service-error','tcp-error','udp-error','port','path-error','existing','hardlink','junction','acl-error','owner','inherited','everyone','generic-write','generic-all','unsupported-right','subst','volume-error','volume-identity','task-pg-noext','pg-service-noext')){
 $global:PgCase=$case
 $r=Get-GridPostgresEvidence @argsPg
 if($r.status -ne 'BLOCKED' -or ($r|ConvertTo-Json -Depth 10) -match 'PRIVATE'){throw ('Unsafe snapshot or leaked diagnostic: '+$case)}
 $count++
}
Write-Output "PostgreSQL read-only snapshot fixtures passed: $count; all host/ACL providers mocked; no writes or child processes"

