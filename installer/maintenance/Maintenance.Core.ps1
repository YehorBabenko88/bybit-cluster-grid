#Requires -Version 5.1
# Internal provider seam for fixture tests; the public dispatcher never accepts a provider.
Set-StrictMode -Version Latest
function New-MaintenanceRow([string]$Status,[string]$Reason,$Data=@()) {
 [ordered]@{status=$Status;reason=$Reason;data=@($Data)}
}
function Get-MaintenanceDigest([string]$Text) {
 $hash=[Security.Cryptography.SHA256]::Create()
 try { ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-','').ToLowerInvariant() } finally {$hash.Dispose()}
}
function Get-MaintenanceToken([string]$Dll,[string]$Sha,[string]$ExpectedSid) {
 if(!$Dll -or $Sha -cnotmatch '^[0-9a-f]{64}$' -or $ExpectedSid -cnotmatch '^S-1-5-21-([0-9]+-){3}[0-9]+$'){throw 'TOKEN_PIN_REQUIRED'}
 if($Dll -cnotmatch '^[A-Za-z]:\\' -or $Dll.Substring(2) -match '[:*?"<>|/]' -or $Dll -match '(^|\\)[.]{1,2}(\\|$)'){throw 'LOCAL_DLL_REQUIRED'}
 $item=Get-Item -LiteralPath $Dll -Force -ErrorAction Stop
 if($item.PSIsContainer -or $item.Length -le 0 -or $item.Length -gt 4194304){throw 'DLL_BOUND'}
 $ancestor=$item.FullName
 while($ancestor){
  if((Get-Item -LiteralPath $ancestor -Force -ErrorAction Stop).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'DLL_REPARSE'}
  $parent=[IO.Directory]::GetParent($ancestor);if(!$parent){break};$ancestor=$parent.FullName
 }
 # Hash the exact captured bytes which are loaded, not a separate file-hash pass.
 $bytes=[IO.File]::ReadAllBytes($item.FullName);if($bytes.Length -gt 4194304){throw 'DLL_BOUND'}
 $h=[Security.Cryptography.SHA256]::Create()
 try{$actual=([BitConverter]::ToString($h.ComputeHash($bytes))).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()}
 if($actual -cne $Sha -or ('GridS0.TokenObserver' -as [type])){throw 'DLL_PIN_OR_COLLISION'}
 [void][Reflection.Assembly]::Load($bytes)
 $facts=[GridS0.TokenObserver]::Read()
 if($facts.Sid -cne $ExpectedSid){throw 'SID_MISMATCH'}
 $groups=@($facts.Groups|ForEach-Object {[ordered]@{sid_sha256=(Get-MaintenanceDigest $_.Sid);attributes=[uint32]$_.Attributes}})
 $privileges=@($facts.Privileges|ForEach-Object {if($_.Name -cnotmatch '^Se[A-Za-z]+Privilege$'){throw 'PRIVILEGE_NAME'};[ordered]@{name=$_.Name;attributes=[uint32]$_.Attributes}})
 if($groups.Count -gt 256 -or $privileges.Count -gt 128){throw 'TOKEN_BOUND'}
 $data=[ordered]@{sid_sha256=(Get-MaintenanceDigest $facts.Sid);expected_sid_match=$true;pid=[uint32]$facts.Pid;creation_filetime=[long]$facts.CreationFileTime;integrity=[string]$facts.Integrity;elevated=[bool]$facts.Elevated;standard=[bool]$facts.Standard;groups=$groups;privileges=$privileges}
 # Session origin/local console is not established by a Medium IL token alone.
 New-MaintenanceRow 'BLOCKED' 'TOKEN_OBSERVED_LOCAL_SESSION_AND_CUSTODY_NOT_ATTESTED' @($data)
}
function Get-MaintenanceObservation([string]$Kind,[string]$Node,[string]$TokenDll,[string]$TokenSha,[string]$ExpectedSid) {
 switch($Kind) {
 'host' {
  $os=Get-CimInstance Win32_OperatingSystem -OperationTimeoutSec 10 -ErrorAction Stop
  if([Environment]::MachineName -ine $Node){return (New-MaintenanceRow 'FAIL' 'HOST_IDENTITY_MISMATCH')}
  if(!$os.Version -or !$os.OSArchitecture){throw 'OS_UNKNOWN'}
  New-MaintenanceRow 'BLOCKED' 'HOSTNAME_NOT_MACHINE_IDENTITY_ATTESTATION' @([ordered]@{hostname=$Node;os_version=[string]$os.Version;architecture=[string]$os.OSArchitecture;ps_version=$PSVersionTable.PSVersion.ToString()})
 }
 'resources' {
  $cs=Get-CimInstance Win32_ComputerSystem -OperationTimeoutSec 10 -ErrorAction Stop
  $cpu=@(Get-CimInstance Win32_Processor -OperationTimeoutSec 10 -ErrorAction Stop)
  if(!$cs.TotalPhysicalMemory -or !$cpu.Count){throw 'RESOURCES_UNKNOWN'}
  $logical=($cpu|Measure-Object NumberOfLogicalProcessors -Sum).Sum
  if(!$logical){throw 'CPU_UNKNOWN'}
  New-MaintenanceRow 'PASS' 'POINT_IN_TIME_METADATA' @([ordered]@{logical_cpu=[int]$logical;ram_bytes=[long]$cs.TotalPhysicalMemory})
 }
 'python' {
  $cmd=Get-Command python.exe -CommandType Application -ErrorAction Stop
  if($cmd.Source -cnotmatch '^[A-Za-z]:\\'){throw 'PYTHON_LOCAL_REQUIRED'}
  $file=Get-Item -LiteralPath $cmd.Source -Force -ErrorAction Stop
  if($file.Attributes -band [IO.FileAttributes]::ReparsePoint -or !$file.VersionInfo.ProductVersion){throw 'PYTHON_VERSION_UNKNOWN'}
  $version=[regex]::Match([string]$file.VersionInfo.ProductVersion,'^[0-9]+([.][0-9]+){1,3}').Value
  if(!$version){throw 'PYTHON_VERSION_UNKNOWN'}
  New-MaintenanceRow 'BLOCKED' 'FILE_VERSION_NOT_EXECUTED_OR_SOURCE_CUSTODY_PROOF' @([ordered]@{version=$version;path_sha256=(Get-MaintenanceDigest $cmd.Source)})
 }
 'token' { Get-MaintenanceToken $TokenDll $TokenSha $ExpectedSid }
 {$_ -in @('postgres','ssh','tailscale','services')} {
  $all=@(Get-CimInstance Win32_Service -OperationTimeoutSec 10 -ErrorAction Stop)
  $pattern=switch($Kind){'postgres' {'^postgresql'} 'ssh' {'^sshd$'} 'tailscale' {'^Tailscale$'} default {'(?i)(grid|bybit|postgresql|sshd|tailscale)'}}
  $rows=@($all|Where-Object {$_.Name -match $pattern}|ForEach-Object {
   if(!$_.Name -or !$_.State){throw 'SERVICE_UNKNOWN'}
   [ordered]@{name_sha256=(Get-MaintenanceDigest ([string]$_.Name));state=[string]$_.State;ownership='UNOWNED_DO_NOT_MODIFY'}
  })
  if($rows.Count -gt 128){throw 'SERVICE_BOUND'}
  New-MaintenanceRow 'BLOCKED' 'SERVICE_METADATA_NOT_DATABASE_OR_CONNECTIVITY_PROOF' $rows
 }
 'firewall' {
  $all=@(Get-NetFirewallRule -PolicyStore ActiveStore -ErrorAction Stop)
  if($all.Count -gt 20000){throw 'FIREWALL_BOUND'}
  $rows=@($all|Where-Object {$_.Name -match '(?i)(grid|bybit)' -or $_.DisplayName -match '(?i)(grid|bybit)'}|ForEach-Object {
   if(!$_.Name){throw 'RULE_ID_UNKNOWN'}
   [ordered]@{name_sha256=(Get-MaintenanceDigest ([string]$_.Name));enabled=[string]$_.Enabled;direction=[string]$_.Direction;action=[string]$_.Action;disposition='REVIEW_ONLY_NO_DELETION'}
  })
  New-MaintenanceRow 'BLOCKED' 'CANDIDATES_NOT_EFFECTIVE_RULE_OR_OWNERSHIP_PROOF' $rows
 }
 'tasks' {
  $all=@(Get-ScheduledTask -ErrorAction Stop)
  if($all.Count -gt 20000){throw 'TASK_BOUND'}
  $rows=@($all|Where-Object {$_.TaskName -match '(?i)(grid|bybit)'}|ForEach-Object {
   if(!$_.TaskName -or !$_.TaskPath){throw 'TASK_ID_UNKNOWN'}
   [ordered]@{identity_sha256=(Get-MaintenanceDigest ($_.TaskPath+$_.TaskName));state=[string]$_.State;diagnostic_task=($_.TaskName -ceq 'GridS0-G0-TokenObserver');disposition='PRESERVE_UNOWNED_TASK'}
  })
  New-MaintenanceRow 'BLOCKED' 'TASKS_NOT_OWNERSHIP_PROOF_NEVER_REMOVE' $rows
 }
 'directories' {
  $rows=@();$unknown=$false;$present=$false
  foreach($path in @('C:\ProgramData\BybitClusterGrid','C:\Program Files\BybitClusterGrid','C:\GridLab')){
   # No recursion and no traversal through a reparse ancestor.
   $parent=[IO.Directory]::GetParent($path).FullName
   while($parent){
    $p=Get-Item -LiteralPath $parent -Force -ErrorAction Stop
    if($p.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'ANCESTOR_REPARSE'}
    $next=[IO.Directory]::GetParent($parent);if(!$next){break};$parent=$next.FullName
   }
   try {
    $entry=Get-Item -LiteralPath $path -Force -ErrorAction Stop
    $present=$true;$reparse=[bool]($entry.Attributes -band [IO.FileAttributes]::ReparsePoint)
    $rows += [ordered]@{path=$path;presence='PRESENT';reparse=$reparse;disposition='REVIEW_ONLY_NO_DELETION'}
   } catch [Management.Automation.ItemNotFoundException] {
    $rows += [ordered]@{path=$path;presence='ABSENT_AT_OBSERVATION';reparse=$false;disposition='NO_ACTION'}
   }
  }
  New-MaintenanceRow 'BLOCKED' 'FIXED_PATHS_ONLY_NO_COMPLETE_CLEANUP_ATTESTATION' $rows
 }
 'source' {
  $rows=@()
  foreach($leaf in @('GridMaintenance.ps1','Maintenance.Core.ps1')){
   $p=Join-Path $PSScriptRoot $leaf
   $h=Get-FileHash -LiteralPath $p -Algorithm SHA256 -ErrorAction Stop
   if($h.Hash -cnotmatch '^[0-9a-fA-F]{64}$'){throw 'SOURCE_HASH_UNKNOWN'}
   $rows += [ordered]@{path=('installer/maintenance/'+$leaf);sha256=$h.Hash.ToLowerInvariant()}
  }
  New-MaintenanceRow 'BLOCKED' 'SOURCE_PINS_REQUIRE_INDEPENDENT_GIT_HEAD_COMPARISON' $rows
 }
 'package' { New-MaintenanceRow 'BLOCKED' 'ORIGINAL_S0_ZIP_AND_CORE20_RUNTIME2_VERIFIER_REQUIRED' }
 default {throw 'UNKNOWN_GATE'}
 }
}
function New-MaintenanceSnapshot {
 param([string]$Node,[string]$Head,[string]$Tree,[string]$RunId,[scriptblock]$Provider,[string]$Scope='UNATTESTED_READ_ONLY')
 if($Node -cnotin @('LS5','PC4') -or $Head -cnotmatch '^[0-9a-f]{40}$' -or $Tree -cnotmatch '^[0-9a-f]{40}$' -or $RunId -cnotmatch '^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'){throw 'CONTEXT_BLOCKED'}
 $checks=[ordered]@{}
 foreach($gate in @('host','resources','python','token','postgres','ssh','tailscale','firewall','services','tasks','directories','source','package')){
  try {
   $items=@(& $Provider $gate)
   if($items.Count -ne 1 -or $items[0] -isnot [Collections.IDictionary]){throw 'PROVIDER_SHAPE'}
   $row=$items[0]
   if(@($row.Keys).Count -ne 3 -or !$row.Contains('status') -or !$row.Contains('reason') -or !$row.Contains('data') -or $row.status -cnotin @('PASS','FAIL','BLOCKED') -or $row.reason -cnotmatch '^[A-Z0-9_]{1,100}$' -or @($row.data).Count -gt 2000){throw 'PROVIDER_UNKNOWN'}
   $checks[$gate]=$row
  } catch {$checks[$gate]=New-MaintenanceRow 'BLOCKED' 'PROVIDER_FAILED_OR_UNKNOWN'}
 }
 [ordered]@{schema='grid-maintenance-1';head=$Head;tree=$Tree;run_id=$RunId;node=$Node;scope=$Scope;observed_utc=[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ');checks=$checks;execute=$false;cleanup=$false;deployment='NO-GO'}
}
