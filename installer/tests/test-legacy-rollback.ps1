#Requires -Version 5.1
param([string]$Python=(Join-Path $PSScriptRoot '..\..\runtime\python.exe'))
$ErrorActionPreference='Stop'
if(!(Test-Path -LiteralPath $Python -PathType Leaf)){throw 'Explicit or bundled Python executable required'}
if(!(Test-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\tests\fixtures\legacy_rollback_migrations.txt') -PathType Leaf)){throw 'Bundled legacy migration fixture missing'}
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
 $output=& $global:LegacyPython -B $global:LegacyDriver @($args | Select-Object -Skip 2)
 $code=$LASTEXITCODE
 $global:LegacyLastCodes='PRECHECK_REPORT_UNAVAILABLE'
 try {
  $parsed=($output -join "`n")|ConvertFrom-Json
  $global:LegacyLastCodes=@($parsed.checks.PSObject.Properties|Where-Object {$_.Value.status -ne 'PASS'}|ForEach-Object {$_.Value.code}) -join ','
 } catch {}
 $global:LASTEXITCODE=$code
 $output
}
function Snapshot($p){
 @(Get-ChildItem -LiteralPath $p -Recurse -File|Sort-Object FullName|ForEach-Object{
  $_.FullName.Substring($p.Length)+':'+(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
 }) -join "`n"
}
$count=0
foreach($sha in @('9ab1f5b85ec471ea21ec89f1b76740c0b01537b6','2017ed4fd16b0b222173a6d42b5bf24b2beb73ac')){
 foreach($role in @('CONTROL','WORKER')){
  foreach($case in @('plan','success','schema','corrupt','process','task','explicit','prepared','missing-manifest','schema48-plan','schema48-apply','schema48-prepared','schema48-committed')){
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
   $after48=$case.StartsWith('schema48-')
   if($after48){$env:GRID_SYNTHETIC_EVIDENCE='schema48'}
   if($case -in @('schema48-prepared','schema48-committed')){
    $phase=if($case -eq 'schema48-prepared'){'prepared'}else{'committed'}
    @{schema=1;previous=$a;candidate=$sha;phase=$phase}|ConvertTo-Json -Compress|Set-Content -LiteralPath (Join-Path $p 'switch-journal.json') -Encoding UTF8
    [IO.File]::WriteAllText((Join-Path $p 'current.version'),$sha)
    [IO.File]::WriteAllText((Join-Path $p 'pending.version'),$sha)
   }
   $before=Snapshot $p;$rejected=$false
   try {
    & (Join-Path $installer 'rollback-release.ps1') -ReviewedVersion $sha -Python Invoke-LegacyPreflight -InstallRoot $p -DataRoot $p -Role $role -LegacyRollback:($case -ne 'explicit') -Apply:($case -notin @('plan','schema48-plan')) | Out-Null
   } catch {$rejected=$true}
   if($after48 -or $case -in @('schema','corrupt','process','task','explicit')){
    if(!$rejected -or (Snapshot $p) -cne $before){throw "Legacy rollback failed closed invariant: $case/$role/$sha"}
    if($after48 -and $global:LegacyLastCodes -notmatch '(^|,)MIGRATION_CATALOGUE_MISMATCH(,|$)'){throw 'Schema48 refused for an incidental reason'}
   } else {
    if($rejected){throw "Legacy rollback unexpectedly blocked: $case/$role/$sha; codes=$global:LegacyLastCodes"}
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
   if($case -in @('schema48-prepared','schema48-committed')){
    # Recovery repairs only files while runtime stays disabled; it never downgrades SQL.
    & (Join-Path $installer 'recover-release.ps1') -InstallRoot $p -Role $role -Apply | Out-Null
    $expected=if($case -eq 'schema48-prepared'){$a}else{$sha}
    if((Get-Content -LiteralPath (Join-Path $p 'current.version') -Raw).Trim() -cne $expected){throw 'Schema48 offline recovery violated journal'}
    $after=Snapshot $p
    & (Join-Path $installer 'recover-release.ps1') -InstallRoot $p -Role $role -Apply | Out-Null
    if((Snapshot $p) -cne $after){throw 'Schema48 repeated offline recovery changed files'}
    $blocked=$false
    try {& (Join-Path $installer 'rollback-release.ps1') -ReviewedVersion $sha -Python Invoke-LegacyPreflight -InstallRoot $p -DataRoot $p -Role $role -LegacyRollback -Apply | Out-Null} catch {$blocked=$true}
    if(!$blocked -or (Snapshot $p) -cne $after -or $global:LegacyLastCodes -notmatch 'MIGRATION_CATALOGUE_MISMATCH'){throw 'Offline recovery bypassed schema48 legacy refusal'}
    if($case -eq 'schema48-committed'){
     $blocked=$false;$pendingReason=$false
     try {& (Join-Path $installer 'switch-release.ps1') -Version $a -InstallRoot $p -Role $role -Apply | Out-Null} catch {$blocked=$true;$pendingReason=$_.Exception.Message -match 'Pending release marker exists'}
     if(!$blocked -or !$pendingReason -or (Snapshot $p) -cne $after){throw 'Forward switch bypassed unresolved pending marker'}
    }
   }
   $count++
  }
 }
}
Write-Output "Legacy rollback integration passed: $count cases; synthetic DB and OS providers; real preflight/switch/recovery"
