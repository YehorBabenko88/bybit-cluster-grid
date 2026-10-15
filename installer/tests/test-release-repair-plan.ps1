#Requires -Version 5.1
param([Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference='Stop'
$planner=Join-Path $PSScriptRoot '../assess-release-repair.ps1'
$fixture=Join-Path $PSScriptRoot 'release_repair_fixture.py'
$root=Join-Path ([IO.Path]::GetTempPath()) ('grid-repair-plan-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($root)
$global:RepairTasks=@();$global:RepairProcesses=@([pscustomobject]@{Name='System';CommandLine=$null})
$global:RepairTaskFailure=$false;$global:RepairProcessFailure=$false
function Get-ScheduledTask {
 [CmdletBinding()]param()
 if($global:RepairTaskFailure){throw 'DO_NOT_LOG_SECRET'}
 $global:RepairTasks
}
function Get-CimInstance {
 [CmdletBinding()]param($ClassName,$OperationTimeoutSec)
 if($global:RepairProcessFailure){throw 'DO_NOT_LOG_SECRET'}
 $global:RepairProcesses
}
function Snapshot($p){
 @(Get-ChildItem -LiteralPath $p -Recurse -Force|Sort-Object FullName|ForEach-Object {
  $digest=if($_.PSIsContainer){'DIRECTORY'}else{(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash}
  $_.FullName.Substring($p.Length)+':'+$digest
 }) -join "`n"
}
Add-Type -TypeDefinition @"
using System;
using System.Threading;
public static class RepairLockHolder {
 public static AutoResetEvent Ready=new AutoResetEvent(false), Done=new AutoResetEvent(false);
 public static Thread Worker;
 public static void Start() {
  Worker=new Thread(() => { using(var m=new Mutex(false,@"Global\BybitClusterGridReleaseSwitch")) {
   m.WaitOne(); Ready.Set(); Done.WaitOne(); m.ReleaseMutex();
  }}); Worker.Start(); Ready.WaitOne();
 }
 public static void Stop() { Done.Set(); Worker.Join(); }
}
"@
$count=0
foreach($phase in @('prepared','committed','none')){
 foreach($role in @('CONTROL','WORKER')){
  foreach($case in @('valid','task','process','unknown-process','task-failure','process-failure','journal','manifest','pending','apply','mutex')){
   $p=Join-Path $root ([guid]::NewGuid().ToString('N'))
   & $Python -B $fixture $p $phase $role
   if($LASTEXITCODE){throw 'Fixture generator failed'}
   $global:RepairTasks=@([pscustomobject]@{TaskName='BybitClusterGridCoordinator';State='Disabled'})
   $global:RepairProcesses=@([pscustomobject]@{Name='System';CommandLine=$null})
   $global:RepairTaskFailure=$false;$global:RepairProcessFailure=$false
   if($case -eq 'task'){$global:RepairTasks=@([pscustomobject]@{TaskName='BybitClusterGridAgent';State='Running'})}
   if($case -eq 'process'){$global:RepairProcesses=@([pscustomobject]@{Name='python.exe';CommandLine='python -m grid.worker'})}
   if($case -eq 'unknown-process'){$global:RepairProcesses=@([pscustomobject]@{Name='python.exe';CommandLine=$null})}
   if($case -eq 'task-failure'){$global:RepairTaskFailure=$true}
   if($case -eq 'process-failure'){$global:RepairProcessFailure=$true}
   if($case -eq 'journal'){[IO.File]::WriteAllText((Join-Path $p 'switch-journal.json'),'{invalid')}
   if($case -eq 'manifest'){[IO.File]::WriteAllText((Join-Path $p ('releases/'+('a'*40)+'/grid/control_runtime.py')),'corrupt')}
   if($case -eq 'pending'){[IO.File]::WriteAllText((Join-Path $p 'pending.version'),('c'*40))}
   $before=Snapshot $p;$blocked=$false;$response=$null
   $argsPlan=@{InstallRoot=$p;ReviewedVersion=('a'*40);SchemaEvidence=(Join-Path $p 'schema-evidence.json');Role=$role;Python=$Python}
   if($case -eq 'apply'){$argsPlan['Apply']=$true}
   if($case -eq 'mutex'){[RepairLockHolder]::Start()}
   try {$response=(& $planner @argsPlan)|ConvertFrom-Json} catch {$blocked=$true}
   finally {if($case -eq 'mutex'){[RepairLockHolder]::Stop()}}
   if($case -eq 'valid'){
    if($blocked -or $response.status -cne 'PLAN_ONLY' -or $response.activation_authorized -ne $false -or
       $response.repair_authorized -ne $false -or $response.marker_removal_authorized -ne $false -or
       $response.runtime_inventory -cne 'STOPPED_SNAPSHOT_UNDER_MUTEX'){throw 'Invalid read-only plan'}
    $again=(& $planner @argsPlan)|ConvertFrom-Json
    if(($response|ConvertTo-Json -Depth 10 -Compress) -cne ($again|ConvertTo-Json -Depth 10 -Compress)){throw 'Assessment not deterministic'}
   } elseif(!$blocked){throw "Unsafe evidence accepted: $phase/$role/$case"}
   if((Snapshot $p) -cne $before){throw 'Assessment modified fixture'}
   $global:LASTEXITCODE=0
   $count++
  }
 }
}
Write-Output "Release repair plan integration passed: $count cases; synthetic OS/files; no DB, pointer writes or activation"
