#Requires -Version 5.1
# Preparation only. No SQL, process execution, task registration, release activation or deletion.
$script:GridLabInstallerRoot=$PSScriptRoot
function Get-GridLabHash([string]$Text){
 $h=[Security.Cryptography.SHA256]::Create()
 try {([BitConverter]::ToString($h.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()}
}
function New-GridLabPlan {
 [CmdletBinding()]
 param([string]$LabParent,[string]$RunId,[string]$NodeId,[ValidateSet('CONTROL','WORKER')][string]$Role='CONTROL',
 [string]$Version,[string]$Branch,[int]$PostgresPort=23001,[int]$CoordinatorPort=23002)
 if($RunId -cnotmatch '^[0-9a-f]{32}$' -or $NodeId -cnotmatch '^[A-Z][A-Z0-9_-]{0,14}$' -or $NodeId -in @('LS5','LS7')){throw 'GRID_LAB_IDENTITY_INVALID'}
 if($Version -cnotmatch '^[0-9a-f]{40}$' -or $Version -eq ('0'*40)){throw 'GRID_LAB_VERSION_INVALID'}
 if($Branch -cne 'main' -and $Branch -cnotmatch '^audit/codex-[a-z0-9-]+$'){throw 'GRID_LAB_STAGING_POLICY_BRANCH_BLOCKED'}
 if($PostgresPort -lt 20000 -or $PostgresPort -gt 49999 -or $CoordinatorPort -lt 20000 -or $CoordinatorPort -gt 49999 -or $PostgresPort -eq $CoordinatorPort){throw 'GRID_LAB_PORTS_INVALID'}
 if($LabParent -cnotmatch '^[A-Za-z]:\\' -or $LabParent -match '[<>"|?*''/~\x00-\x1f]' -or $LabParent.Substring(2).Contains(':')){throw 'GRID_LAB_PARENT_INVALID'}
 foreach($part in $LabParent.Substring(3).Split('\')){
  if(!$part -or $part -match '(^[.]+$|[. ]$|^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])([.]|$))' -or $part -in @('Windows','Program Files','Program Files (x86)','ProgramData')){throw 'GRID_LAB_PARENT_INVALID'}
 }
 $parent=[IO.Path]::GetFullPath($LabParent)
 if([IO.Path]::GetFileName($parent) -cne 'GridLab' -or $parent.Length -gt 140){throw 'GRID_LAB_PARENT_INVALID'}
 $root=Join-Path $parent ($RunId+'_'+$NodeId)
 $prefix='BybitClusterGridLab_'+$RunId+'_'+$NodeId
 $p=[ordered]@{schema=1;kind='ISOLATED_PREPARATION';parent=$parent;root=$root;run_id=$RunId;node_id=$NodeId;role=$Role;version=$Version;branch=$Branch;
  postgres_port=$PostgresPort;coordinator_port=$CoordinatorPort;database=('grid_lab_'+$RunId+'_'+$NodeId.ToLowerInvariant());
  tasks=@(($prefix+'_Agent'),($prefix+'_Coordinator'),($prefix+'_ArchivePipeline'));
  activation_authorized=$false;database_initialization_authorized=$false;tasks_registered=$false;
  staging_policy='installer/stage-github-release.ps1';rollback='RETIRE_AND_PRESERVE';
  blockers=@('DATABASE_INITIALIZATION_REQUIRES_SEPARATE_REVIEW','RELEASE_STAGING_AND_MANIFEST_PREFLIGHT_REQUIRED','TASK_REGISTRATION_AND_ACTIVATION_NOT_IMPLEMENTED','FRESH_PHYSICAL_EVIDENCE_AND_OPERATOR_APPROVAL_REQUIRED')}
 $digest=Get-GridLabHash ($p|ConvertTo-Json -Depth 10 -Compress)
 $p.plan_sha256=$digest
 [pscustomobject]$p
}
function Get-GridLabItem([string]$Path){
 try {Get-Item -LiteralPath $Path -Force -ErrorAction Stop}
 catch [System.Management.Automation.ItemNotFoundException] {return $null}
}
function Assert-GridLabPhysical([string]$Path){
 $cursor=[IO.Path]::GetFullPath($Path)
 while($cursor){
  $item=Get-GridLabItem $cursor
  if($null -eq $item -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'GRID_LAB_PATH_UNAVAILABLE_OR_REDIRECTED'}
  $parent=[IO.Directory]::GetParent($cursor);if($null -eq $parent){break};$cursor=$parent.FullName
 }
}
function Assert-GridLabStagingPolicy {
 param($Plan)
 # Read-only discovery through the existing policy, never accept local provenance or override its branch/CI rules.
 $output=@(& (Join-Path $script:GridLabInstallerRoot 'stage-github-release.ps1') -Branch $Plan.branch -Commit $Plan.version -AllowAuditCandidate *>&1)
 if($output -notcontains ('Verified CI gates for commit '+$Plan.version) -or $output -notcontains 'Read-only discovery complete. Pass -Download to stage the verified bundle.'){throw 'GRID_LAB_STAGING_POLICY_BLOCKED'}
}
function Assert-GridLabHost {
 param($Plan)
 . (Join-Path $script:GridLabInstallerRoot 'release-runtime-guard.ps1')
 Assert-GridRuntimeStopped
 $systems=@(Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop *>&1)
 if($systems.Count -ne 1 -or $systems[0].Name -cne $Plan.node_id -or $systems[0].Name -in @('LS5','LS7')){throw 'GRID_LAB_HOST_IDENTITY_BLOCKED'}
 $drive=$Plan.parent.Substring(0,2)
 $disks=@(Get-CimInstance -ClassName Win32_LogicalDisk -Filter ("DeviceID='"+$drive+"'") -ErrorAction Stop *>&1)
 if($disks.Count -ne 1 -or $disks[0] -is [Management.Automation.ErrorRecord] -or [string]$disks[0].DriveType -cne '3'){throw 'GRID_LAB_FIXED_LOCAL_DISK_REQUIRED'}
 $tasks=@(Get-ScheduledTask -ErrorAction Stop *>&1)
 foreach($t in $tasks){
  if(!$t.TaskName -or $t -is [Management.Automation.ErrorRecord] -or $t.TaskName -in $Plan.tasks){throw 'GRID_LAB_TASK_COLLISION_OR_UNKNOWN'}
  if($null -eq $t.Actions -or @($t.Actions).Count -eq 0){throw 'GRID_LAB_TASK_ACTION_UNKNOWN'}
  foreach($action in $t.Actions){
   $execute=$action.Execute;$classId=$action.ClassId
   $knownExecute=($execute -is [string] -and ![string]::IsNullOrWhiteSpace($execute))
   $knownCom=($classId -is [string] -and $classId -match '^\{?[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\}?$')
   if(!$knownExecute -and !$knownCom){throw 'GRID_LAB_TASK_ACTION_UNKNOWN'}
   foreach($field in @('Execute','Arguments','WorkingDirectory','Data')){
    $value=$action.$field
    if($null -ne $value -and $value -isnot [string]){throw 'GRID_LAB_TASK_ACTION_UNKNOWN'}
    if(([string]$value).IndexOf($Plan.root,[StringComparison]::OrdinalIgnoreCase) -ge 0 -or ([string]$value).IndexOf($Plan.run_id,[StringComparison]::OrdinalIgnoreCase) -ge 0){throw 'GRID_LAB_TASK_ROOT_REFERENCED'}
   }
  }
 }
 $services=@(Get-CimInstance -ClassName Win32_Service -ErrorAction Stop *>&1)
 if(!$services.Count){throw 'GRID_LAB_SERVICE_INVENTORY_EMPTY'}
 foreach($s in $services){if(!$s.Name -or $s -is [Management.Automation.ErrorRecord] -or $s.Name -in $Plan.tasks -or ([string]$s.PathName).IndexOf($Plan.root,[StringComparison]::OrdinalIgnoreCase) -ge 0){throw 'GRID_LAB_SERVICE_COLLISION_OR_UNKNOWN'}}
 $processes=@(Get-CimInstance -ClassName Win32_Process -OperationTimeoutSec 10 -ErrorAction Stop *>&1)
 if(!$processes.Count){throw 'GRID_LAB_PROCESS_INVENTORY_EMPTY'}
 foreach($p in $processes){
  if(!$p.Name -or $p -is [Management.Automation.ErrorRecord] -or ($p.Name -match '^(postgres|pg_ctl|initdb)([.]exe)?$' -and [string]::IsNullOrWhiteSpace([string]$p.CommandLine)) -or ([string]$p.CommandLine).IndexOf($Plan.root,[StringComparison]::OrdinalIgnoreCase) -ge 0){throw 'GRID_LAB_PROCESS_COLLISION_OR_UNKNOWN'}
 }
 foreach($e in @((Get-NetTCPConnection -ErrorAction Stop *>&1)) + @((Get-NetUDPEndpoint -ErrorAction Stop *>&1))){
  if($e -is [Management.Automation.ErrorRecord] -or $null -eq $e.LocalPort -or [string]$e.LocalPort -notmatch '^[0-9]+$' -or [int]$e.LocalPort -lt 1 -or [int]$e.LocalPort -gt 65535 -or [int]$e.LocalPort -in @($Plan.postgres_port,$Plan.coordinator_port)){throw 'GRID_LAB_PORT_COLLISION_OR_UNKNOWN'}
 }
 Assert-GridLabPhysical $Plan.parent
 # Enumeration is mandatory: access denied or a failed provider is never interpreted as absence.
 $children=@(Get-ChildItem -LiteralPath $Plan.parent -Force -ErrorAction Stop)
 $matches=@($children|Where-Object {$_.Name -ieq [IO.Path]::GetFileName($Plan.root)})
 if($matches.Count -gt 1){throw 'GRID_LAB_ROOT_AMBIGUOUS'}
}
function Write-GridLabNewFile {
 param([string]$Path,[string]$Text)
 $stream=[IO.FileStream]::new($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
 try {$bytes=[Text.UTF8Encoding]::new($false).GetBytes($Text);$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
}
function Get-GridLabRecord($Plan,[string]$State){
 ([ordered]@{schema=1;plan_sha256=$Plan.plan_sha256;state=$State}|ConvertTo-Json -Compress)+"`n"
}
function Assert-GridLabSingleLink($Stream){
 if(-not ('GridLabFileIdentity' -as [type])){
  Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class GridLabFileIdentity {
 [StructLayout(LayoutKind.Sequential)] public struct Info {
  public uint Attributes, CreationLow, CreationHigh, AccessLow, AccessHigh, WriteLow, WriteHigh;
  public uint Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
 }
 [DllImport("kernel32.dll", SetLastError=true)]
 public static extern bool GetFileInformationByHandle(SafeFileHandle handle, out Info info);
}
'@ -ErrorAction Stop
 }
 $info=New-Object GridLabFileIdentity+Info
 if(![GridLabFileIdentity]::GetFileInformationByHandle($Stream.SafeFileHandle,[ref]$info) -or $info.Links -ne 1 -or ($info.Attributes -band 1024)){throw 'GRID_LAB_JOURNAL_LINKED_OR_UNKNOWN'}
}
function Add-GridLabRecord($Plan,[string]$State,[string]$ExpectedJournal){
 $path=Join-Path $Plan.root 'owner.jsonl'
 # Validate and append using the SAME exclusively held handle, including idempotent retirement.
 $stream=[IO.FileStream]::new($path,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
 try {
  Assert-GridLabSingleLink $stream
  $item=Get-GridLabItem $path
  if($null -eq $item -or $item.LinkType -eq 'HardLink' -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'GRID_LAB_JOURNAL_LINKED_OR_UNKNOWN'}
  $expected=[Text.Encoding]::UTF8.GetBytes($ExpectedJournal)
  if($stream.Length -ne $expected.Length -or $stream.Length -gt 4096){throw 'GRID_LAB_JOURNAL_CHANGED'}
  $actual=New-Object byte[] $expected.Length;$offset=0
  while($offset -lt $actual.Length){$read=$stream.Read($actual,$offset,$actual.Length-$offset);if($read -le 0){throw 'GRID_LAB_JOURNAL_CHANGED'};$offset+=$read}
  if([Convert]::ToBase64String($actual) -cne [Convert]::ToBase64String($expected)){throw 'GRID_LAB_JOURNAL_CHANGED'}
  if($State){$bytes=[Text.Encoding]::UTF8.GetBytes((Get-GridLabRecord $Plan $State));$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}
 }finally{$stream.Dispose()}
}
function Get-GridLabFiles($Plan){
 # Templates are intentionally NOT .env/current.version/task XML: no launcher can adopt them.
 $pgdata=(Join-Path $Plan.root 'postgres\data').Replace('\','/')
 [ordered]@{
 'deployment-plan.json'=($Plan|ConvertTo-Json -Depth 10 -Compress)
 'isolated.env.template'=("# NOT ACTIVE; no secrets; never use production environment fallback`nGRID_DATA_DIR="+(Join-Path $Plan.root 'data')+"`nWAL_DIR="+(Join-Path $Plan.root 'data\wal')+"`nGRID_RUNTIME_STATE=INFRA_ONLY`n# PostgreSQL: new cluster only, loopback port "+$Plan.postgres_port+"; database "+$Plan.database+"`n# Trading/Telegram/runtime activation not provisioned`n")
 'postgresql.conf.template'=("# NOT ACTIVE: new cluster not initialized`nlisten_addresses = '127.0.0.1'`nport = "+$Plan.postgres_port+"`ndata_directory = '"+$pgdata+"'`nssl = on`n")
 'tasks.plan.json'=([ordered]@{names=$Plan.tasks;enabled=$false;registered=$false;actions=@();triggers=@();startup_authorized=$false}|ConvertTo-Json -Depth 5 -Compress)
 }
}
function Assert-GridLabOwned($Plan){
 Assert-GridLabPhysical $Plan.root
 $record=Join-Path $Plan.root 'owner.jsonl'
 $item=Get-GridLabItem $record
 if($null -eq $item -or $item.Length -gt 4096 -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'GRID_LAB_OWNERSHIP_UNPROVEN'}
 $journal=[IO.File]::ReadAllText($record,[Text.Encoding]::UTF8)
 $start=Get-GridLabRecord $Plan 'PREPARED';$commit=Get-GridLabRecord $Plan 'COMMITTED';$retire=Get-GridLabRecord $Plan 'RETIRED'
 if($journal -cnotin @($start,($start+$commit),($start+$retire),($start+$commit+$retire))){throw 'GRID_LAB_JOURNAL_INVALID'}
 $expected=Get-GridLabFiles $Plan
 $dirs=@('releases','data','data\wal','postgres','postgres\data')
 $queue=[Collections.Generic.Queue[string]]::new();$queue.Enqueue($Plan.root)
 while($queue.Count){
  $directory=$queue.Dequeue()
  foreach($entry in @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)){
   if($entry.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'GRID_LAB_OWNERSHIP_REDIRECTED'}
   $rel=$entry.FullName.Substring($Plan.root.Length+1)
   if($entry.PSIsContainer){if($rel -cnotin $dirs){throw 'GRID_LAB_FOREIGN_RESOURCE'};$queue.Enqueue($entry.FullName)}
   elseif($rel -cne 'owner.jsonl'){
    if(!$expected.Contains($rel) -or $entry.Length -gt 65536 -or [IO.File]::ReadAllText($entry.FullName,[Text.Encoding]::UTF8) -cne $expected[$rel]){throw 'GRID_LAB_RESOURCE_CHANGED_OR_FOREIGN'}
   }
  }
 }
 if($journal.Contains($commit)){
  foreach($name in $expected.Keys){if($null -eq (Get-GridLabItem (Join-Path $Plan.root $name))){throw 'GRID_LAB_COMMITTED_RESOURCE_MISSING'}}
  foreach($dir in $dirs){Assert-GridLabPhysical (Join-Path $Plan.root $dir)}
 }
 [pscustomobject]@{retired=$journal.EndsWith($retire,[StringComparison]::Ordinal);journal=$journal}
}
function Invoke-GridLabPreparation {
 [CmdletBinding()]
 param($Plan,[ValidateSet('Prepare','Rollback')][string]$Mode,[string]$Approval)
 $locks=@();$held=@()
 try {
  $again=New-GridLabPlan -LabParent $Plan.parent -RunId $Plan.run_id -NodeId $Plan.node_id -Role $Plan.role -Version $Plan.version -Branch $Plan.branch -PostgresPort $Plan.postgres_port -CoordinatorPort $Plan.coordinator_port
  if(($again|ConvertTo-Json -Depth 10 -Compress) -cne ($Plan|ConvertTo-Json -Depth 10 -Compress)){throw 'GRID_LAB_PLAN_CHANGED'}
  $verb=if($Mode -eq 'Prepare'){'PREPARE:'}else{'RETIRE:'}
  if($Approval -cne ($verb+$Plan.plan_sha256)){throw 'GRID_LAB_EXPLICIT_APPROVAL_REQUIRED'}
  foreach($name in @('Global\BybitClusterGridReleaseSwitch','Global\BybitClusterGridTaskPreparation')){
   $m=[Threading.Mutex]::new($false,$name);$locks+=,$m;$owns=$false
   try {$owns=$m.WaitOne(0)}catch [Threading.AbandonedMutexException]{$owns=$true}
   if(!$owns){throw 'GRID_LAB_MUTEX_BUSY'};$held+=,$m
  }
  Assert-GridLabHost $Plan
  if($Mode -eq 'Prepare'){
   if($null -ne (Get-GridLabItem $Plan.root)){throw 'GRID_LAB_EXISTING_ROOT_REFUSED'}
   Assert-GridLabStagingPolicy $Plan
   # Recheck immediately before the first filesystem write, under both existing mutexes.
   Assert-GridLabHost $Plan
   if($null -ne (Get-GridLabItem $Plan.root)){throw 'GRID_LAB_EXISTING_ROOT_REFUSED'}
   New-Item -ItemType Directory -Path $Plan.root -ErrorAction Stop|Out-Null
   Write-GridLabNewFile -Path (Join-Path $Plan.root 'owner.jsonl') -Text (Get-GridLabRecord $Plan 'PREPARED')
   foreach($dir in @('releases','data','data\wal','postgres','postgres\data')){New-Item -ItemType Directory -Path (Join-Path $Plan.root $dir) -ErrorAction Stop|Out-Null}
   $files=Get-GridLabFiles $Plan
   foreach($name in $files.Keys){Write-GridLabNewFile -Path (Join-Path $Plan.root $name) -Text $files[$name]}
   [void](Assert-GridLabOwned $Plan)
   Add-GridLabRecord $Plan 'COMMITTED' (Get-GridLabRecord $Plan 'PREPARED')
   [pscustomobject]@{schema=1;status='PREPARED_OFFLINE';plan_sha256=$Plan.plan_sha256;activation_authorized=$false;database_initialized=$false;tasks_registered=$false}
  }else{
   $owned=Assert-GridLabOwned $Plan
   # No pointer/DB rollback is inferred. Existing recovery requires a separate reviewed operation.
   Assert-GridLabHost $Plan
   $owned=Assert-GridLabOwned $Plan
   $state=if($owned.retired){''}else{'RETIRED'}
   Add-GridLabRecord $Plan $state $owned.journal
   [pscustomobject]@{schema=1;status='RETIRED_PRESERVED';plan_sha256=$Plan.plan_sha256;activation_authorized=$false;resources_deleted=$false}
  }
 }catch{
  $code='GRID_LAB_OPERATION_BLOCKED'
  if($_.Exception.Message -cmatch '^(GRID_LAB|GRID_RUNTIME)_[A-Z_]+$'){$code=$_.Exception.Message}
  throw $code
 }finally{
  for($i=$held.Count-1;$i -ge 0;$i--){$held[$i].ReleaseMutex()}
  foreach($m in $locks){$m.Dispose()}
 }
}
