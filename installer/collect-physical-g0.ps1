#Requires -Version 5.1
<# Metadata-only LOCAL G0 observer. Default PLAN_ONLY; stdout JSON only.
No executable probes, sockets, SQL, subprocesses, output files, mutex, ACL changes,
service/task mutations, registry writes, account changes or remote commands.
-G0Approved is an operator assertion, not authorization evidence or G1 permission. #>
[CmdletBinding()]
param(
 [ValidateSet('PlanOnly','ReadOnly')][string]$Mode='PlanOnly',
 [ValidateSet('LS5','PC4')][string]$NodeId,
 [ValidatePattern('^[0-9a-f]{40}$')][string]$Head,
 [ValidatePattern('^[0-9a-f]{32}$')][string]$RunId,
 [string]$SourcePath='',
 [switch]$G0Approved
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if($Mode -eq 'PlanOnly'){
 [ordered]@{schema='grid-g0-plan-1';status='PLAN_ONLY';g1_authorized=$false;g2_authorized=$false;host_calls=0}|ConvertTo-Json -Compress
 return
}
if(!$G0Approved -or !$NodeId -or !$Head -or !$RunId){
 [ordered]@{schema='grid-g0-plan-1';status='BLOCKED';reason='OWNER_G0_ACCESS_REQUIRED';g1_authorized=$false;g2_authorized=$false}|ConvertTo-Json -Compress
 return
}
function Digest([string]$Text){
 $h=[Security.Cryptography.SHA256]::Create()
 try{return ([BitConverter]::ToString($h.ComputeHash([Text.Encoding]::UTF8.GetBytes($RunId+':'+$Text)))).Replace('-','').ToLowerInvariant()}
 finally{$h.Dispose()}
}
function Public-Path([string]$Path){return ($Path -replace '(?i)([A-Z]:\\Users\\)[^\\]+','$1[USER]')}
function Row([string]$Status,[string]$Reason,$Data){return [ordered]@{status=$Status;reason=$Reason;data=@($Data)}}
$checks=[ordered]@{}
foreach($name in @('authorization','os','resources','python','dotnet','powershell','postgres','listeners','processes','services','tasks','tailscale','ssh','firewall','paths','environment','source','accounts','acl','health','connectivity','database_metadata')){
 $checks[$name]=Row 'BLOCKED' 'NOT_OBSERVED' @()
}
function Observe([string]$Name,[scriptblock]$Provider){
 try{
  $items=@(& $Provider *>&1)
  if($items.Count -ne 1 -or $items[0] -is [Management.Automation.ErrorRecord] -or $items[0] -isnot [Collections.IDictionary]){throw 'PROVIDER_SHAPE'}
  $checks[$Name]=$items[0]
 }catch{$checks[$Name]=Row 'BLOCKED' 'PROVIDER_FAILED_OR_UNKNOWN' @()}
}
$hostId=$null
try{$guid=(Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Cryptography' -Name MachineGuid -ErrorAction Stop).MachineGuid;if(!$guid){throw 'MISSING_ID'};$hostId=Digest ([string]$guid)}catch{}
Observe 'os' {
 $o=Get-CimInstance -ClassName Win32_OperatingSystem -OperationTimeoutSec 10 -ErrorAction Stop
 if(!$o.Version -or !$o.OSArchitecture){throw 'MISSING_OS'}
 Row 'PASS' 'METADATA_ONLY' @([ordered]@{version=[string]$o.Version;architecture=[string]$o.OSArchitecture})
}
Observe 'resources' {
 $cs=Get-CimInstance -ClassName Win32_ComputerSystem -OperationTimeoutSec 10 -ErrorAction Stop
 $cpu=@(Get-CimInstance -ClassName Win32_Processor -OperationTimeoutSec 10 -ErrorAction Stop)
 $disks=@(Get-CimInstance -ClassName Win32_LogicalDisk -OperationTimeoutSec 10 -ErrorAction Stop|Where-Object {$_.DriveType -eq 3})
 if(!$cs.TotalPhysicalMemory -or !$cpu.Count -or !$disks.Count){throw 'MISSING_RESOURCES'}
 $rows=@($disks|ForEach-Object {if($null -eq $_.FreeSpace){throw 'UNKNOWN_DISK'};[ordered]@{logical_cpu=[int](($cpu|Measure-Object NumberOfLogicalProcessors -Sum).Sum);ram_bytes=[long]$cs.TotalPhysicalMemory;drive=[string]$_.DeviceID;free_bytes=[long]$_.FreeSpace}})
 Row 'PASS' 'METADATA_ONLY' $rows
}
foreach($pair in @(@('python','python.exe'),@('dotnet','dotnet.exe'),@('powershell','pwsh.exe'))){
 $label=$pair[0];$tool=$pair[1]
 Observe $label {
  $cmd=Get-Command -Name $tool -CommandType Application -ErrorAction Stop
  $item=Get-Item -LiteralPath $cmd.Source -Force -ErrorAction Stop
  if($item.Attributes -band [IO.FileAttributes]::ReparsePoint -or !$item.VersionInfo.ProductVersion){throw 'UNTRUSTED_TOOL'}
  $version=[regex]::Match([string]$item.VersionInfo.ProductVersion,'^[0-9]+([.][0-9]+){1,3}').Value
  if(!$version){throw 'VERSION_UNKNOWN'}
  Row 'BLOCKED' 'FILE_VERSION_NOT_EXECUTED_OR_CUSTODY_VERIFIED' @([ordered]@{path=(Public-Path $cmd.Source);file_version=$version})
 }
}
Observe 'processes' {
 $all=@(Get-CimInstance -ClassName Win32_Process -OperationTimeoutSec 10 -ErrorAction Stop)
 if(!$all.Count){throw 'EMPTY_PROCESS_INVENTORY'}
 $out=@();$unknown=$false
 foreach($p in $all){
  if(!$p.Name){throw 'INVALID_PROCESS'}
  if($p.Name -notmatch '^(python[^\\/\s]*|pyw?|pwsh|powershell|uvicorn|postgres|pg_ctl|tailscale|sshd)([.]exe)?$'){continue}
  $known=$p.CommandLine -is [string] -and ![string]::IsNullOrWhiteSpace($p.CommandLine)
  if(!$known){$unknown=$true}
  # Read only for classification; NEVER serialize CommandLine, arguments or credentials.
  $candidate=$known -and $p.CommandLine -match '(?i)(\bgrid[.]\w+|\brun_(worker|coordinator)([.]py)?\b|coordinator-launcher[.]ps1|archive-launcher[.]ps1)'
  $out += [ordered]@{pid=[int]$p.ProcessId;parent_pid=[int]$p.ParentProcessId;name=[string]$p.Name;path=(Public-Path ([string]$p.ExecutablePath));created_utc=$(if($p.CreationDate){([datetime]$p.CreationDate).ToUniversalTime().ToString('o')}else{$null});grid_candidate=[bool]$candidate;identity_known=[bool]$known}
  if($out.Count -gt 128){throw 'PROCESS_LIMIT'}
 }
 if($unknown){Row 'BLOCKED' 'PROCESS_IDENTITY_UNKNOWN' $out}else{Row 'PASS' 'INFORMATIONAL_NOT_OWNERSHIP_PROOF' $out}
}
Observe 'services' {
 $rows=@(Get-CimInstance -ClassName Win32_Service -OperationTimeoutSec 10 -ErrorAction Stop|Where-Object {$_.Name -match '^(postgresql|BybitClusterGrid|Tailscale|sshd)'}|ForEach-Object {[ordered]@{service=[string]$_.Name;state=[string]$_.State;start_mode=[string]$_.StartMode}})
 if($rows.Count -gt 128){throw 'SERVICE_LIMIT'}
 Row 'PASS' 'INFORMATIONAL_UNOWNED_DO_NOT_MODIFY' $rows
}
foreach($pair in @(@('postgres','^postgresql'),@('tailscale','^Tailscale$'),@('ssh','^sshd$'))){
 $label=$pair[0];$pattern=$pair[1]
 Observe $label {
  $rows=@(Get-CimInstance -ClassName Win32_Service -OperationTimeoutSec 10 -ErrorAction Stop|Where-Object {$_.Name -match $pattern}|ForEach-Object {[ordered]@{service=[string]$_.Name;state=[string]$_.State;start_mode=[string]$_.StartMode}})
  if(!$rows.Count){throw 'SERVICE_NOT_OBSERVED'}
  Row 'BLOCKED' 'SERVICE_STATE_NOT_VERSION_OR_ROUTE_PROOF' $rows
 }
}
Observe 'listeners' {
 $rows=@(Get-NetTCPConnection -State Listen -ErrorAction Stop|ForEach-Object {[ordered]@{address=[string]$_.LocalAddress;port=[int]$_.LocalPort;pid=[int]$_.OwningProcess}})
 if($rows.Count -gt 128){throw 'LISTENER_LIMIT'}
 Row 'PASS' 'POINT_IN_TIME_ONLY_PORT_REUSE_UNPROVEN' $rows
}
Observe 'tasks' {
 $all=@(Get-ScheduledTask -ErrorAction Stop);$rows=@()
 foreach($t in $all){
  if(!$t.TaskName){throw 'INVALID_TASK'}
  if($t.TaskName -notmatch '(?i)(grid|bybit)'){continue}
  $kind=if([string]$t.Principal.UserId -in @('SYSTEM','S-1-5-18')){'SYSTEM'}else{'OTHER_OR_UNKNOWN'}
  $rows += [ordered]@{name=[string]$t.TaskName;state=[string]$t.State;enabled=$t.Settings.Enabled;principal_kind=$kind}
 }
 if($rows.Count -gt 128){throw 'TASK_LIMIT'}
 Row 'PASS' 'INFORMATIONAL_EXISTING_TASKS_NOT_MODIFIED' $rows
}
Observe 'firewall' {
 $rules=@(Get-NetFirewallRule -Enabled True -ErrorAction Stop)
 if($rules.Count -gt 2000){throw 'FIREWALL_LIMIT'}
 Row 'BLOCKED' 'EFFECTIVE_FIREWALL_AND_EGRESS_NOT_VERIFIED' @()
}
$paths=@((Join-Path $env:ProgramData 'BybitClusterGrid'),(Join-Path $env:ProgramFiles 'BybitClusterGrid'),'C:\GridLab\Secure','C:\GridLab\Runtime','C:\GridLab\PostgreSQL','C:\GridLab\Fixtures',('C:\GridLab\FirstBoot\'+$RunId+'\'+$NodeId))
Observe 'paths' {
 $rows=@();$redirected=$false
 foreach($path in $paths){
  $exists=Test-Path -LiteralPath $path -ErrorAction Stop;$reparse=$false
  $ancestor=$path
  while($ancestor){
   if(Test-Path -LiteralPath $ancestor -ErrorAction Stop){$item=Get-Item -LiteralPath $ancestor -Force -ErrorAction Stop;if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){$reparse=$true;$redirected=$true}}
   $parent=[IO.Directory]::GetParent($ancestor);if($null -eq $parent){break};$ancestor=$parent.FullName
  }
  $rows += [ordered]@{path=(Public-Path $path);exists=[bool]$exists;reparse=[bool]$reparse}
 }
 if($redirected){Row 'FAIL' 'REPARSE_REQUIRES_STOP' $rows}else{Row 'BLOCKED' 'CUSTODY_AND_DESCENDANTS_UNVERIFIED' $rows}
}
Observe 'acl' {
 $rows=@()
 foreach($path in $paths){
  if(!(Test-Path -LiteralPath $path -ErrorAction Stop)){continue}
  $acl=Get-Acl -LiteralPath $path -ErrorAction Stop
  $rows += [ordered]@{path=(Public-Path $path);owner_digest=(Digest ([string]$acl.Owner));protected=[bool]$acl.AreAccessRulesProtected;ace_count=@($acl.Access).Count;reparse=[bool]((Get-Item -LiteralPath $path -Force -ErrorAction Stop).Attributes -band [IO.FileAttributes]::ReparsePoint)}
 }
 Row 'BLOCKED' 'METADATA_NOT_EFFECTIVE_SID_DACL_HANDLE_PROOF' $rows
}
Observe 'accounts' {
 $admins=@(Get-LocalGroupMember -SID 'S-1-5-32-544' -ErrorAction Stop);$rows=@()
 foreach($name in @('GridLabCollector','GridLabStorage','grid_pg_test')){
  $u=Get-LocalUser -Name $name -ErrorAction Stop
  $isAdmin=$null
  if(@($admins|Where-Object {$_.SID.Value -eq $u.SID.Value}).Count){$isAdmin=$true}
  $rows += [ordered]@{name=$name;sid_digest=(Digest $u.SID.Value);enabled=[bool]$u.Enabled;administrator=$isAdmin}
 }
 Row 'BLOCKED' 'DIRECT_GROUPS_NOT_EFFECTIVE_TOKEN_PROOF' $rows
}
Observe 'environment' {
 $allowed=@('POSTGRES_DSN','NODE_ROLE','NODE_ID','COORDINATOR_URL','COORDINATOR_CANDIDATES','BYBIT_REST_URL','BYBIT_WS_URL','BYBIT_ARCHIVE_BASE_URL','GRID_SHARED_TOKEN','NODE_CREDENTIAL','TELEGRAM_BOT_TOKEN','TELEGRAM_ALLOWED_CHAT_IDS','ProgramData','ProgramFiles')
 $rows=@(Get-ChildItem -LiteralPath Env: -ErrorAction Stop|Where-Object {$_.Name -in $allowed}|ForEach-Object {[ordered]@{name=[string]$_.Name}})
 Row 'BLOCKED' 'NAMES_ONLY_NO_VALUES_OR_DOTENV_READ' $rows
}
Observe 'source' {
 if(!$SourcePath){throw 'SOURCE_NOT_SUPPLIED'}
 $rows=@()
 foreach($name in @('grid\coordinator.py','grid\worker.py','grid\schema_contract.py','grid\schema_preparation.py','grid\migrations.py','requirements.txt')){
  $p=Join-Path $SourcePath $name;$h=Get-FileHash -LiteralPath $p -Algorithm SHA256 -ErrorAction Stop
  $rows += [ordered]@{path=$name;sha256=([string]$h.Hash).ToLowerInvariant()}
 }
 Row 'BLOCKED' 'HASHES_NOT_TRUSTED_HEAD_OR_ANCESTOR_CUSTODY_PROOF' $rows
}
$checks.authorization=Row 'BLOCKED' 'HOST_BINDING_AND_OWNER_ACCESS_NOT_ATTESTED' @()
$checks.health=Row 'BLOCKED' 'NO_NETWORK_OR_HEALTH_PROBES_PERFORMED' @()
$checks.connectivity=Row 'BLOCKED' 'SSH_TAILSCALE_ROUTE_NOT_PROBED' @()
$checks.database_metadata=Row 'BLOCKED' 'NO_DATABASE_CONNECTION_OR_SQL_PERFORMED' @()
[ordered]@{schema='grid-g0-observation-1';node=$NodeId;head=$Head;run_id=$RunId;host_id=$hostId;observed_utc=[DateTime]::UtcNow.ToString('o');observation_kind='UNATTESTED_READ_ONLY';g1_authorized=$false;g2_authorized=$false;checks=$checks}|ConvertTo-Json -Depth 10 -Compress
