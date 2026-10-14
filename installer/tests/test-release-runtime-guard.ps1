param([string]$OnlyCase='')
$ErrorActionPreference='Stop'
$scripts=Join-Path $PSScriptRoot '..'
$root=Join-Path ([IO.Path]::GetTempPath()) ('grid-runtime-guard-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($root)
$a='a'*40;$b='b'*40
$global:GuardTaskRows=@();$global:GuardProcessRows=@()
$global:GuardTaskFailure=$false;$global:GuardProcessFailure=$false
$global:GuardBlockAtCall=0;$global:GuardCheckMutex=$false;$global:GuardCalls=0;$global:GuardLateTask=$false;$global:GuardTaskPartial=$false;$global:GuardProcessPartial=$false
Add-Type -TypeDefinition @'
using System;
using System.Threading;
public static class GridGuardMutexProbe {
 public static bool AvailableOnOtherThread() {
  bool acquired=false;
  Thread t=new Thread(()=>{using(Mutex m=new Mutex(false,"Global\\BybitClusterGridReleaseSwitch")) {
   try {acquired=m.WaitOne(0);} catch(AbandonedMutexException) {acquired=true;}
   if(acquired) m.ReleaseMutex();
  }});
  t.Start(); if(!t.Join(5000)) throw new Exception("Mutex probe timed out"); return acquired;
 }
}
'@
function Get-ScheduledTask {
 [CmdletBinding()]param()
 $global:GuardCalls++
 if($global:GuardBlockAtCall -and $global:GuardCalls -ge $global:GuardBlockAtCall){$global:GuardTaskRows=@([pscustomobject]@{TaskName="BybitClusterGridCoordinator";State="Running"})}
 if($global:GuardCheckMutex -and [GridGuardMutexProbe]::AvailableOnOtherThread()){throw 'Guard ran outside release mutex'}
 if($global:GuardTaskFailure){Write-Error 'secret-inventory-sentinel';return}
 if($global:GuardTaskPartial){$global:GuardTaskRows; Write-Warning 'secret-inventory-sentinel'; return}
 $global:GuardTaskRows
}
function Get-CimInstance {
 [CmdletBinding()]param($ClassName,$Filter,$OperationTimeoutSec)
 if($global:GuardProcessFailure){Write-Error 'secret-inventory-sentinel';return}
 if($global:GuardLateTask){$global:GuardTaskRows=@([pscustomobject]@{TaskName='BybitClusterGridAgent';State='Ready'})}
 if($Filter){throw 'Filtered inventory is incomplete'}
 if($global:GuardProcessPartial){$global:GuardProcessRows; Write-Warning 'secret-inventory-sentinel'; return}
 $global:GuardProcessRows
}
function Reset-Inventory {
 $global:GuardTaskRows=@([pscustomobject]@{TaskName='BybitClusterGridAgent';State='Disabled'})
 $global:GuardProcessRows=@([pscustomobject]@{Name='System';CommandLine=$null},[pscustomobject]@{Name='python.exe';CommandLine='python.exe -m unrelated_application'})
 $global:GuardTaskFailure=$false;$global:GuardProcessFailure=$false;$global:GuardLateTask=$false;$global:GuardTaskPartial=$false;$global:GuardProcessPartial=$false
}
function Fixture([string]$kind,[string]$phase='prepared',[string]$current='candidate',[string]$pending='candidate') {
 $p=Join-Path $root ([guid]::NewGuid().ToString('N'))
 foreach($v in @($a,$b)){
  $dir=Join-Path $p ('releases\'+$v)
  [void][IO.Directory]::CreateDirectory((Join-Path $dir 'grid'))
  [IO.File]::WriteAllText((Join-Path $dir 'run_worker.py'),'# fixture worker')
  [IO.File]::WriteAllText((Join-Path $dir 'grid\coordinator.py'),'# fixture control')
  $files=@{}
  foreach($entry in @('run_worker.py','grid/coordinator.py')){$files[$entry]=(Get-FileHash -LiteralPath (Join-Path $dir $entry) -Algorithm SHA256).Hash.ToLowerInvariant()}
  @{version=$v;files=$files} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dir 'release-manifest.json') -Encoding UTF8
 }
 if($kind -eq 'switch'){$current='previous';$pending='missing'}
 if($current -ne 'missing'){[IO.File]::WriteAllText((Join-Path $p 'current.version'),$(if($current -eq 'previous'){$a}else{$b}))}
 if($pending -ne 'missing'){[IO.File]::WriteAllText((Join-Path $p 'pending.version'),$(if($pending -eq 'previous'){$a}else{$b}))}
 if($kind -eq 'recover'){@{schema=1;previous=$a;candidate=$b;phase=$phase}|ConvertTo-Json -Compress|Set-Content -LiteralPath (Join-Path $p 'switch-journal.json') -Encoding UTF8}
 return $p
}
function Snapshot([string]$p){
 @((Get-ChildItem -LiteralPath $p -Recurse -File | Sort-Object FullName | ForEach-Object {
  $_.FullName.Substring($p.Length)+':'+(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
 })) -join "`n"
}
function Operation($kind,$p,$role,[bool]$apply=$true){
 if($kind -eq 'switch'){& (Join-Path $scripts 'switch-release.ps1') -InstallRoot $p -Version $b -Role $role -Apply:$apply | Out-Null}
 else {& (Join-Path $scripts 'recover-release.ps1') -InstallRoot $p -Role $role -Apply:$apply | Out-Null}
}
$cases=@('task-running','task-ready','task-queued','task-unknown','task-inventory-error','process-inventory-error','empty-process-inventory','python-unknown','pythonw-unknown','python-version-unknown','entry-module','entry-script','entry-path','entry-uvicorn','entry-archive','entry-import','entry-launcher','shell-unknown','task-partial','process-partial','task-malformed','process-malformed','command-malformed','python-free-threaded-unknown','task-enabled-conflict')
$count=0
foreach($kind in @('switch','recover')){foreach($role in @('WORKER','CONTROL')){foreach($phase in $(if($kind -eq 'recover'){@('prepared','committed')}else{@('prepared')})){foreach($case in $cases){
 if($OnlyCase -and $OnlyCase -ne $case){continue}
 Reset-Inventory
 switch($case){
  'task-running' {$global:GuardTaskRows=@([pscustomobject]@{TaskName='BybitClusterGridCoordinator';State='Running'})}
  'task-ready' {$global:GuardTaskRows=@([pscustomobject]@{TaskName='BybitClusterGridArchivePipeline';State='Ready'})}
  'task-queued' {$global:GuardTaskRows=@([pscustomobject]@{TaskName='BybitClusterGridAgent';State='Queued'})}
  'task-unknown' {$global:GuardTaskRows=@([pscustomobject]@{TaskName='BybitClusterGridCoordinator';State=$null})}
  'task-inventory-error' {$global:GuardTaskFailure=$true}
  'process-inventory-error' {$global:GuardProcessFailure=$true}
  'empty-process-inventory' {$global:GuardProcessRows=@()}
  'python-unknown' {$global:GuardProcessRows=@([pscustomobject]@{Name='python.exe';CommandLine=$null})}
  'pythonw-unknown' {$global:GuardProcessRows=@([pscustomobject]@{Name='pythonw.exe';CommandLine=' '})}
  'python-version-unknown' {$global:GuardProcessRows=@([pscustomobject]@{Name='python3.12.exe';CommandLine=$null})}
  'entry-module' {$global:GuardProcessRows=@([pscustomobject]@{Name='python.exe';CommandLine='python -m grid.worker'})}
  'entry-script' {$global:GuardProcessRows=@([pscustomobject]@{Name='python.exe';CommandLine='python C:\alternate\run_coordinator.py'})}
  'entry-path' {$global:GuardProcessRows=@([pscustomobject]@{Name='python.exe';CommandLine='python C:\alternate\grid\worker.py'})}
  'entry-uvicorn' {$global:GuardProcessRows=@([pscustomobject]@{Name='uvicorn.exe';CommandLine='uvicorn grid.coordinator:app'})}
  'entry-archive' {$global:GuardProcessRows=@([pscustomobject]@{Name='python.exe';CommandLine='python -m grid.archive_service'})}
  'entry-import' {$global:GuardProcessRows=@([pscustomobject]@{Name='python.exe';CommandLine='python -c "from grid import worker"'})}
  'entry-launcher' {$global:GuardProcessRows=@([pscustomobject]@{Name='powershell.exe';CommandLine='powershell -File C:\alternate\coordinator-launcher.ps1'})}
  'task-partial' {$global:GuardTaskPartial=$true}
  'process-partial' {$global:GuardProcessPartial=$true}
  'task-malformed' {$global:GuardTaskRows=@([pscustomobject]@{State='Disabled'})}
  'process-malformed' {$global:GuardProcessRows=@([pscustomobject]@{CommandLine='python -m unrelated'})}
  'command-malformed' {$global:GuardProcessRows=@([pscustomobject]@{Name='python.exe';CommandLine=42})}
  'python-free-threaded-unknown' {$global:GuardProcessRows=@([pscustomobject]@{Name='python3.13t.exe';CommandLine=$null})}
  'task-enabled-conflict' {$global:GuardTaskRows=@([pscustomobject]@{TaskName='BybitClusterGridAgent';State='Disabled';Settings=[pscustomobject]@{Enabled=$true}})}
  'shell-unknown' {$global:GuardProcessRows=@([pscustomobject]@{Name='pwsh.exe';CommandLine=$null})}
 }
 $p=Fixture $kind $phase;$before=Snapshot $p;$rejected=$false;$errorText=''
 try {Operation $kind $p $role} catch {$rejected=$true;$errorText=$_.ToString()}
 if(!$rejected){throw "Expected $kind/$role rejection for $case"}
 if((Snapshot $p) -cne $before){throw "Guard mutated transaction files for $kind/$role/$case"}
 if($errorText -match 'secret-inventory-sentinel'){throw 'Guard exposed provider diagnostics'}
 $count++
}}}}
if($OnlyCase){Write-Output "Runtime guard negative cases passed: $count";return}
# Planning and no-journal recovery must remain read-only even with failed providers.
Reset-Inventory
$global:GuardTaskFailure=$true;$global:GuardProcessFailure=$true
foreach($kind in @('switch','recover')){
 $p=Fixture $kind;$before=Snapshot $p;Operation $kind $p 'WORKER' $false
 if((Snapshot $p) -cne $before){throw 'Plan modified files'}
}
# Positive transitions and interrupted states; second recovery must be a no-op.
$global:GuardCheckMutex=$true
foreach($role in @('WORKER','CONTROL')){
 Reset-Inventory
 $p=Fixture 'switch';Operation 'switch' $p $role
 $j=Get-Content -LiteralPath (Join-Path $p 'switch-journal.json') -Raw|ConvertFrom-Json
 if($j.phase -cne 'committed' -or $j.schema -ne 1 -or $j.previous -cne $a -or $j.candidate -cne $b){throw 'Switch journal contract changed'}
 foreach($phase in @('prepared','committed')){foreach($current in @('previous','candidate','missing')){foreach($pending in @('previous','candidate','missing')){
  $p=Fixture 'recover' $phase $current $pending
  Operation 'recover' $p $role
  $expected=if($phase -eq 'prepared'){$a}else{$b}
  if((Get-Content -LiteralPath (Join-Path $p 'current.version') -Raw).Trim() -cne $expected){throw 'Recovery violated prepared/committed contract'}
  if(Test-Path -LiteralPath (Join-Path $p 'switch-journal.json')){throw 'Recovery retained completed journal'}
  $before=Snapshot $p;Operation 'recover' $p $role
  if((Snapshot $p) -cne $before){throw 'Repeated recovery changed files'}
  $count++
 }}}
}
# Rollback must recheck after its read-only preflight and again at switch's write.
$wrapper=Join-Path $root 'reviewed-installer'
[void][IO.Directory]::CreateDirectory($wrapper)
foreach($file in @('rollback-release.ps1','switch-release.ps1','release-runtime-guard.ps1')){
 Copy-Item -LiteralPath (Join-Path $scripts $file) -Destination $wrapper
}
function Invoke-GuardPreflight {$global:LASTEXITCODE=0;'{}'}
Reset-Inventory
$global:GuardCalls=0;$global:GuardBlockAtCall=2
$p=Fixture 'switch';$before=Snapshot $p;$rejected=$false
try {& (Join-Path $wrapper 'rollback-release.ps1') -ReviewedVersion $b -Python Invoke-GuardPreflight -InstallRoot $p -DataRoot $p -Role WORKER -Apply | Out-Null} catch {$rejected=$true}
if(!$rejected -or $global:GuardCalls -ne 2 -or (Snapshot $p) -cne $before){throw 'Rollback did not recheck immediately before transaction write'}
$global:GuardBlockAtCall=0
$count++
# Missing shared guard must fail before switch/recovery writes, never fall back.
foreach($kind in @('switch','recover')){
 Copy-Item -LiteralPath (Join-Path $scripts ($kind+'-release.ps1')) -Destination $wrapper
 $helper=Join-Path $wrapper 'release-runtime-guard.ps1'
 if(Test-Path -LiteralPath $helper){Remove-Item -LiteralPath $helper}
 Reset-Inventory
 $p=Fixture $kind;$before=Snapshot $p;$rejected=$false
 try {
  if($kind -eq 'switch'){& (Join-Path $wrapper 'switch-release.ps1') -Version $b -InstallRoot $p -Apply | Out-Null}
  else {& (Join-Path $wrapper 'recover-release.ps1') -InstallRoot $p -Apply | Out-Null}
 } catch {$rejected=$true}
 if(!$rejected -or (Snapshot $p) -cne $before){throw 'Missing guard permitted transaction mutation'}
 $count++
}
Write-Output "Runtime guard cases passed: $count; providers mocked, mutex ownership verified, fixture=$root"

