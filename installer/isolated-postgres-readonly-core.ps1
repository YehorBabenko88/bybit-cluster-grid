#Requires -Version 5.1
# Host metadata only. Never starts child processes, binds ports, writes files, calls SQL or changes services.
function Get-GridPostgresEvidence {
 [CmdletBinding()]
 param([string]$DataRoot,[string]$RunId,[string]$NodeId,[int]$Port,[string]$Commit,[string]$PlanSha256,[string]$OwnerSid)
 $mutex=$null;$held=$false
 try {
  . (Join-Path $PSScriptRoot 'isolated-deployment-core.ps1')
  if($Commit -cnotmatch '^[0-9a-f]{40}$' -or $Commit -eq ('0'*40) -or $PlanSha256 -cnotmatch '^[0-9a-f]{64}$' -or $OwnerSid -cnotmatch '^S-1-5-21-[0-9]+-[0-9]+-[0-9]+-[0-9]+$'){throw 'PG_READ_ONLY_IDENTITY_INVALID'}
  if($DataRoot -cnotmatch '^[A-Z]:\\' -or $RunId -cnotmatch '^[0-9a-f]{32}$' -or $NodeId -cnotmatch '^[A-Z][A-Z0-9_-]{0,14}$' -or $NodeId -in @('LS5','LS7')){throw 'PG_READ_ONLY_PATH_INVALID'}
  $tail='\'+$RunId+'\'+$NodeId+'\pgdata'
  if(!$DataRoot.EndsWith($tail,[StringComparison]::Ordinal) -or [IO.Path]::GetFullPath($DataRoot) -cne $DataRoot){throw 'PG_READ_ONLY_PATH_INVALID'}
  $parent=$DataRoot.Substring(0,$DataRoot.Length-$tail.Length)
  # Reuse adapter lexical parent/identity/port rules only; NEVER translate its layout or claim shared ownership.
  $otherPort=if($Port -eq 20000){20001}else{20000}
  [void](New-GridLabPlan -LabParent $parent -RunId $RunId -NodeId $NodeId -Version $Commit -Branch audit/codex-readonly-metadata -PostgresPort $Port -CoordinatorPort $otherPort)
  $mutex=[Threading.Mutex]::new($false,'Global\BybitClusterGridReleaseSwitch')
  try {$held=$mutex.WaitOne(0)}catch [Threading.AbandonedMutexException]{$held=$true}
  if(!$held){throw 'PG_READ_ONLY_MUTEX_BUSY'}
  . (Join-Path $PSScriptRoot 'release-runtime-guard.ps1')
  Assert-GridRuntimeStopped
  $systems=@(Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop *>&1)
  if($systems.Count -ne 1 -or $systems[0].Name -cne $NodeId){throw 'PG_READ_ONLY_HOST_IDENTITY_INVALID'}
  $drive=$DataRoot.Substring(0,2)
  $disks=@(Get-CimInstance -ClassName Win32_LogicalDisk -Filter ("DeviceID='"+$drive+"'") -ErrorAction Stop *>&1)
  if($disks.Count -ne 1 -or [string]$disks[0].DriveType -cne '3'){throw 'PG_READ_ONLY_FIXED_LOCAL_DRIVE_REQUIRED'}
  # A directory-backed drive-letter alias must not masquerade as a physical volume.
  $volumes=@(Get-CimInstance -ClassName Win32_Volume -Filter ("DriveLetter='"+$drive+"'") -ErrorAction Stop *>&1)
  if($volumes.Count -ne 1 -or $volumes[0].DriveLetter -ine $drive -or [string]$volumes[0].DriveType -cne '3' -or
     $volumes[0].DeviceID -isnot [string] -or $volumes[0].DeviceID -notmatch '^\\\\\?\\Volume\{[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\}\\$'){throw 'PG_READ_ONLY_VOLUME_IDENTITY_UNKNOWN'}
  Assert-GridLabPhysical $parent
  $parentItem=Get-GridLabItem $parent
  if(!$parentItem.PSIsContainer -or $parentItem.LinkType -eq 'HardLink'){throw 'PG_READ_ONLY_PARENT_IDENTITY_INVALID'}
  foreach($path in @($DataRoot,([IO.Directory]::GetParent($DataRoot).FullName),(Join-Path $parent $RunId))){
   if($null -ne (Get-GridLabItem $path)){throw 'PG_READ_ONLY_EXISTING_RESOURCE_REFUSED'}
  }
  $acl=Get-Acl -LiteralPath $parent -ErrorAction Stop
  $raw=[Security.AccessControl.RawSecurityDescriptor]::new($acl.GetSecurityDescriptorBinaryForm(),0)
  if($null -eq $raw.DiscretionaryAcl -or !$acl.AreAccessRulesCanonical -or !$acl.AreAccessRulesProtected){throw 'PG_READ_ONLY_ACL_UNSAFE'}
  $owner=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
  if($owner -cne $OwnerSid){throw 'PG_READ_ONLY_ACL_OWNER_MISMATCH'}
  foreach($ace in $raw.DiscretionaryAcl){
   if($ace -isnot [Security.AccessControl.CommonAce] -or $ace.IsCallback -or $ace.AceQualifier -notin @([Security.AccessControl.AceQualifier]::AccessAllowed,[Security.AccessControl.AceQualifier]::AccessDenied)){throw 'PG_READ_ONLY_ACL_ACE_UNSUPPORTED'}
   $rights=[long]$ace.AccessMask -band 4294967295
   # Only FILE_ALL_ACCESS plus generic read/write/execute/all are understood.
   if(($rights -bor 4028563967) -ne 4028563967){throw 'PG_READ_ONLY_ACL_RIGHTS_UNSUPPORTED'}
  }
  # Include GENERIC_WRITE and GENERIC_ALL: raw ACLs need not have mapped generic rights.
  $writers=@();$writeMask=2 -bor 4 -bor 16 -bor 64 -bor 256 -bor 65536 -bor 262144 -bor 524288 -bor 1073741824 -bor 268435456
  foreach($rule in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
   if($rule.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and ([long]$rule.FileSystemRights -band $writeMask)){
    $sid=[string]$rule.IdentityReference.Value
    if($sid -cnotin @($OwnerSid,'S-1-5-18','S-1-5-32-544')){throw 'PG_READ_ONLY_ACL_UNTRUSTED_WRITER'}
    $writers+=,$sid
   }
  }
  $tasks=@(Get-ScheduledTask -ErrorAction Stop *>&1)
  foreach($task in $tasks){
   if(!$task.TaskName -or $task -is [Management.Automation.ErrorRecord] -or $null -eq $task.Actions -or @($task.Actions).Count -eq 0){throw 'PG_READ_ONLY_TASK_IDENTITY_UNKNOWN'}
   foreach($action in $task.Actions){
    $execute=$action.Execute;$classId=$action.ClassId
    if(($execute -isnot [string] -or [string]::IsNullOrWhiteSpace($execute)) -and ($classId -isnot [string] -or $classId -notmatch '^\{?[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\}?$')){throw 'PG_READ_ONLY_TASK_IDENTITY_UNKNOWN'}
    foreach($field in @('Execute','Arguments','WorkingDirectory','Data')){
     $text=$action.$field
     if($null -ne $text -and $text -isnot [string]){throw 'PG_READ_ONLY_TASK_IDENTITY_UNKNOWN'}
     if(([string]$text).IndexOf($RunId,[StringComparison]::OrdinalIgnoreCase) -ge 0 -or [string]$text -match '(?i)(^|[\s"\x27\\/])(postgres|pg_ctl|initdb)([.]exe)?($|[\s"\x27])'){throw 'PG_READ_ONLY_EXISTING_POSTGRES_TASK'}
    }
   }
  }
  $services=@(Get-CimInstance -ClassName Win32_Service -ErrorAction Stop *>&1)
  if(!$services.Count){throw 'PG_READ_ONLY_SERVICE_INVENTORY_EMPTY'}
  foreach($service in $services){
   if(!$service.Name -or $service.PathName -isnot [string] -or [string]::IsNullOrWhiteSpace($service.PathName)){throw 'PG_READ_ONLY_SERVICE_IDENTITY_UNKNOWN'}
   if($service.Name -match '(?i)postgres|pg_ctl|initdb' -or $service.PathName -match '(?i)(^|[\s"\x27\\/])(postgres|pg_ctl|initdb)([.]exe)?($|[\s"\x27])' -or $service.PathName.IndexOf($RunId,[StringComparison]::OrdinalIgnoreCase) -ge 0){throw 'PG_READ_ONLY_EXISTING_POSTGRES_SERVICE'}
  }
  $processes=@(Get-CimInstance -ClassName Win32_Process -OperationTimeoutSec 10 -ErrorAction Stop *>&1)
  if(!$processes.Count){throw 'PG_READ_ONLY_PROCESS_INVENTORY_EMPTY'}
  foreach($process in $processes){
   if(!$process.Name -or ($null -ne $process.CommandLine -and $process.CommandLine -isnot [string])){throw 'PG_READ_ONLY_PROCESS_IDENTITY_UNKNOWN'}
   if($process.Name -match '^(?i:postgres|pg_ctl|initdb)([.]exe)?$'){throw 'PG_READ_ONLY_EXISTING_POSTGRES_PROCESS'}
   # Observer identity is the current process only; Runtime Guard still checks it above.
   if($process.ProcessId -ne $PID -and (([string]$process.CommandLine).IndexOf($RunId,[StringComparison]::OrdinalIgnoreCase) -ge 0 -or [string]$process.CommandLine -match '(?i)(^|[\s"\x27\\/])(postgres|pg_ctl|initdb)([.]exe)?($|[\s"\x27])')){throw 'PG_READ_ONLY_EXISTING_POSTGRES_PROCESS'}
  }
  $ports=@()
  foreach($transport in @('tcp','udp')){
   $endpoints=if($transport -eq 'tcp'){@(Get-NetTCPConnection -ErrorAction Stop *>&1)}else{@(Get-NetUDPEndpoint -ErrorAction Stop *>&1)}
   foreach($endpoint in $endpoints){
    if($endpoint -is [Management.Automation.ErrorRecord] -or $null -eq $endpoint.LocalPort -or [string]$endpoint.LocalPort -notmatch '^[0-9]+$' -or [int]$endpoint.LocalPort -lt 1 -or [int]$endpoint.LocalPort -gt 65535){throw 'PG_READ_ONLY_PORT_INVENTORY_INVALID'}
    if([int]$endpoint.LocalPort -eq $Port){throw 'PG_READ_ONLY_PORT_OCCUPIED'}
    $ports+=@{transport=$transport;port=[int]$endpoint.LocalPort}
   }
  }
  [pscustomobject][ordered]@{schema=1;status='SNAPSHOT_ONLY';execution_authorized=$false;physical_ready=$false;commit_sha=$Commit;plan_sha256=$PlanSha256;
   node_id=$NodeId;run_id=$RunId;data_root=$DataRoot;captured_at=[DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ss'Z'");
   inventory_complete=$true;runtime_stopped=$true;local_fixed_disk=$true;path_physical=$true;root_absent=$true;
   new_ancestors_absent=$true;hardlinks_absent=$true;postgres_identities_absent=$true;tasks_clear=$true;ports=@($ports);
   acl=@{owner_sid=$owner;protected=$true;writable_sids=@($writers|Sort-Object -Unique);sha256=(Get-GridLabHash $acl.GetSecurityDescriptorSddlForm([Security.AccessControl.AccessControlSections]::All))}}
 }catch{
  $code='PG_READ_ONLY_INVENTORY_FAILED'
  if($_.Exception.Message -cmatch '^(PG_READ_ONLY|GRID_RUNTIME|GRID_LAB)_[A-Z_]+$'){$code=$_.Exception.Message}
  [pscustomobject]@{schema=1;status='BLOCKED';code=$code;execution_authorized=$false;physical_ready=$false}
 }finally{if($held){$mutex.ReleaseMutex()};if($null -ne $mutex){$mutex.Dispose()}}
}
