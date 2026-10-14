#Requires -Version 5.1
param([string]$Python='python')
$ErrorActionPreference='Stop'
$global:LegacyPython=$Python
$global:LegacyDriver=Join-Path $PSScriptRoot 'legacy_rollback_driver.py'
$root=Join-Path ([IO.Path]::GetTempPath()) ('grid-legacy-rollback-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($root)
$installer=Join-Path $PSScriptRoot '..'
$a='a'*40
$global:LegacyTasks=@();$global:LegacyProcesses=@([pscustomobject]@{Name='System';CommandLine=$null})
function Get-ScheduledTask {[CmdletBinding()]param() $global:LegacyTasks}
function Get-CimInstance {[CmdletBinding()]param($ClassName,$OperationTimeoutSec) $global:LegacyProcesses}
function Invoke-LegacyPreflight {
 # Preserve all actual CLI flags. Only external DB/dependency boundary is synthetic.
 & $global:LegacyPython -B $global:LegacyDriver @($args | Select-Object -Skip 2)
 $global:LASTEXITCODE=$LASTEXITCODE
}
function Snapshot($p){
 @(Get-ChildItem -LiteralPath $p -Recurse -File|Sort-Object FullName|ForEach-Object{
  $_.FullName.Substring($p.Length)+':'+(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
 }) -join "`n"
}
$count=0
foreach($sha in @('9ab1f5b85ec471ea21ec89f1b76740c0b01537b6','2017ed4fd16b0b222173a6d42b5bf24b2beb73ac')){
 foreach($role in @('CONTROL','WORKER')){
  foreach($case in @('plan','success','schema','corrupt','process','task','explicit','prepared','missing-manifest')){
   $p=Join-Path $root ([guid]::NewGuid().ToString('N'))
   foreach($v in @($a,$sha)){
    & $Python -B $global:LegacyDriver --make-fixture (Join-Path $p ('releases\'+$v)) $v
    if($LASTEXITCODE){throw 'Fixture generation failed'}
   }
   [IO.File]::WriteAllText((Join-Path $p 'current.version'),$a)
   [IO.File]::WriteAllText((Join-Path $p '.env'),"GRID_SHARED_TOKEN=fixture`nNODE_CREDENTIAL=fixture`nRETENTION_ENABLED=false`nPOSTGRES_DSN=postgresql://fixture/bybit_cluster_grid`n")
   $global:LegacyTasks=@([pscustomobject]@{TaskName='BybitClusterGridAgent';State='Disabled'})
   $global:LegacyProcesses=@([pscustomobject]@{Name='System';CommandLine=$null})
   $env:GRID_SYNTHETIC_EVIDENCE='valid'
   if($case -eq 'schema'){$env:GRID_SYNTHETIC_EVIDENCE='old-schema'}
   if($case -eq 'corrupt'){[IO.File]::WriteAllText((Join-Path $p ('releases\'+$sha+'\grid\coordinator.py')),'tampered')}
   if($case -eq 'process'){$global:LegacyProcesses=@([pscustomobject]@{Name='python.exe';CommandLine='python -m grid.worker'})}
   if($case -eq 'task'){$global:LegacyTasks=@([pscustomobject]@{TaskName='BybitClusterGridCoordinator';State='Ready'})}
   $before=Snapshot $p;$rejected=$false
   try {
    & (Join-Path $installer 'rollback-release.ps1') -ReviewedVersion $sha -Python Invoke-LegacyPreflight -InstallRoot $p -DataRoot $p -Role $role -LegacyRollback:($case -ne 'explicit') -Apply:($case -ne 'plan') | Out-Null
   } catch {$rejected=$true}
   if($case -in @('schema','corrupt','process','task','explicit')){
    if(!$rejected -or (Snapshot $p) -cne $before){throw "Legacy rollback failed closed invariant: $case/$role/$sha"}
   } else {
    if($rejected){throw "Legacy rollback unexpectedly blocked: $case/$role/$sha"}
    if($case -eq 'plan'){
     if((Snapshot $p) -cne $before){throw 'Default plan modified files'}
    } else {
     $jp=Join-Path $p 'switch-journal.json';$j=Get-Content -LiteralPath $jp -Raw|ConvertFrom-Json
     if($j.schema -ne 1 -or $j.phase -cne 'committed' -or $j.candidate -cne $sha){throw 'Legacy journal contract changed'}
     if($case -eq 'prepared'){$j.phase='prepared';$j|ConvertTo-Json -Compress|Set-Content -LiteralPath $jp -Encoding UTF8}
     if($case -eq 'missing-manifest'){
      Remove-Item -LiteralPath (Join-Path $p ('releases\'+$sha+'\release-manifest.json'))
      $before=Snapshot $p;$blocked=$false
      try {& (Join-Path $installer 'recover-release.ps1') -InstallRoot $p -Role $role -Apply | Out-Null} catch {$blocked=$true}
      if(!$blocked -or (Snapshot $p) -cne $before){throw 'Legacy recovery accepted missing manifest'}
     } else {
      & (Join-Path $installer 'recover-release.ps1') -InstallRoot $p -Role $role -Apply | Out-Null
      $expected=if($case -eq 'prepared'){$a}else{$sha}
      if((Get-Content -LiteralPath (Join-Path $p 'current.version') -Raw).Trim() -cne $expected){throw 'Legacy recovery pointer wrong'}
      $after=Snapshot $p
      & (Join-Path $installer 'recover-release.ps1') -InstallRoot $p -Role $role -Apply | Out-Null
      if((Snapshot $p) -cne $after){throw 'Repeated legacy recovery modified files'}
     }
    }
   }
   $count++
  }
 }
}
Write-Output "Legacy rollback integration passed: $count cases; synthetic DB and OS providers; real preflight/switch/recovery"
