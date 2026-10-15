#Requires -Version 5.1
<# Read-only diagnostics only after explicit Mode=ReadOnly. No executable probes,
SQL, remote commands, output files, service changes or resource ownership claims. #>
[CmdletBinding()]
param(
 [ValidateSet('PlanOnly','ReadOnly')][string]$Mode='PlanOnly',
 [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z][A-Za-z0-9_-]{0,15}$')][string]$NodeId,
 [Parameter(Mandatory=$true)][string]$PlannedRoot,
 [Parameter(Mandatory=$true)][string]$Address,
 [ValidateSet('CONTROL','WORKER')][string]$Role='WORKER'
)
$ErrorActionPreference='Stop'
if($Mode -eq 'PlanOnly'){
 [ordered]@{schema=1;status='PLAN_ONLY';execution_authorized=$false;node_id=$NodeId;probes=@('Runtime Guard','existing commissioning inventory','CPU/RAM/disk/Windows','binary version metadata only','SSH/Tailscale availability; connectivity NOT tested')}|ConvertTo-Json -Depth 5 -Compress
 return
}
$mutex=[Threading.Mutex]::new($false,'Global\BybitClusterGridReleaseSwitch');$held=$false
try {
 try {$held=$mutex.WaitOne(0)} catch [Threading.AbandonedMutexException] {$held=$true}
 if(!$held){throw 'PHYSICAL_INVENTORY_MUTEX_BUSY'}
 if($NodeId.ToUpperInvariant() -in @('LS5','LS7')){throw 'PHYSICAL_PROTECTED_NODE'}
 if($PlannedRoot -cnotmatch ('^[A-Za-z]:\\GridLab\\[0-9a-f]{32}\\'+[regex]::Escape($NodeId)+'$')){throw 'PHYSICAL_LAB_ROOT_REQUIRED'}
 $ancestor=[IO.Path]::GetFullPath($PlannedRoot)
 while($ancestor){
  if(Test-Path -LiteralPath $ancestor){
   if((Get-Item -LiteralPath $ancestor -Force -ErrorAction Stop).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'PHYSICAL_ROOT_REDIRECTED'}
  }
  $parent=[IO.Directory]::GetParent($ancestor)
  if($null -eq $parent){break};$ancestor=$parent.FullName
 }
 if(Test-Path -LiteralPath $PlannedRoot){throw 'PHYSICAL_ROOT_ALREADY_EXISTS'}
 . (Join-Path $PSScriptRoot 'release-runtime-guard.ps1')
 Assert-GridRuntimeStopped
 # The existing inventory is informational, not a substitute for strict guard/hardware providers.
 $base=(& (Join-Path $PSScriptRoot 'collect-commissioning-inventory.ps1') -GridRoot $PlannedRoot|Out-String|ConvertFrom-Json)
 $os=Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
 $cs=Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
 $cpus=@(Get-CimInstance -ClassName Win32_Processor -ErrorAction Stop)
 $drive=[IO.Path]::GetPathRoot($PlannedRoot).Substring(0,2)
 $disk=Get-CimInstance -ClassName Win32_LogicalDisk -Filter ("DeviceID='"+$drive+"'") -ErrorAction Stop
 $services=@(Get-CimInstance -ClassName Win32_Service -ErrorAction Stop)
 if($cs.Name -ine $NodeId -or !$os.Version -or !$cpus.Count -or $null -eq $disk.FreeSpace -or !$cs.TotalPhysicalMemory){throw 'PHYSICAL_HARDWARE_INCOMPLETE'}
 function Tool-Version([string]$Name){
  $cmd=Get-Command -Name $Name -ErrorAction Stop
  $version=[string](Get-Item -LiteralPath $cmd.Source -ErrorAction Stop).VersionInfo.ProductVersion
  if($version -cnotmatch '^[0-9]+([.][0-9]+){0,3}$'){throw 'PHYSICAL_TOOL_VERSION_UNKNOWN'}
  $version
 }
 $py=Tool-Version 'python.exe';$pg=Tool-Version 'psql.exe'
 $ssh=Tool-Version 'ssh.exe';$ts=Tool-Version 'tailscale.exe'
 $tsRunning=@($services|Where-Object {$_.Name -eq 'Tailscale' -and $_.State -eq 'Running'}).Count -eq 1
 $node=[ordered]@{id=$NodeId;role=$Role;address=$Address;windows_major=([version]$os.Version).Major;
  cpu_logical=[int](($cpus|Measure-Object NumberOfLogicalProcessors -Sum).Sum);ram_bytes=[long]$cs.TotalPhysicalMemory;
  disk_free_bytes=[long]$disk.FreeSpace;python_version=$py;postgres_major=[int]($pg.Split('.')[0]);
  ssh_available=$true;tailscale_available=$tsRunning;runtime_stopped=$true;inventory_complete=$true;
  test_root=$PlannedRoot;test_root_exists=$false;disposable_cluster_confirmed=$false}
 [ordered]@{schema=1;status='SNAPSHOT_ONLY';execution_authorized=$false;node=$node;
  diagnostics=@{python='FILE_VERSION_ONLY';postgres='CLIENT_METADATA_ONLY_NO_SQL';ssh_version=$ssh;tailscale_version=$ts;
   connectivity='NOT_PROBED';address='OPERATOR_SUPPLIED_UNVERIFIED';existing_services='UNOWNED_DO_NOT_MODIFY';python_architecture='NOT_PROBED'};
  informational_inventory=$base}|ConvertTo-Json -Depth 10 -Compress
} catch {
 $code='PHYSICAL_INVENTORY_FAILED'
 if($_.Exception.Message -cmatch '^(GRID_RUNTIME|PHYSICAL)_[A-Z_]+$'){$code=$_.Exception.Message}
 [ordered]@{schema=1;status='BLOCKED';code=$code;execution_authorized=$false}|ConvertTo-Json -Compress
 throw $code
} finally {
 if($held){$mutex.ReleaseMutex()};$mutex.Dispose()
}
