#Requires -Version 5.1
param(
 [Parameter(Mandatory=$true)][string]$ReleaseDir,
 [Parameter(Mandatory=$true)][string]$Python,
 [ValidateSet("CONTROL","PILOT","NORMAL")][string]$Mode="NORMAL",
 [switch]$Apply,
 [switch]$StartServices
)
$ErrorActionPreference="Stop"
$TaskName="BybitClusterGridAgent"
$ArchiveTaskName="BybitClusterGridArchivePipeline"
$CoordinatorTaskName="BybitClusterGridCoordinator"
$InstallRoot="$env:ProgramFiles\BybitClusterGrid"
$DataRoot="$env:ProgramData\BybitClusterGrid"
if($StartServices -and !$Apply){throw 'StartServices requires explicit Apply'}
if(!$Apply){
 Write-Output ('PLAN_ONLY; role='+$Mode+'; tasks=disabled; archive=refused; no files changed')
 return
}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=[Security.Principal.WindowsPrincipal]::new($identity)
if(!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Apply requires an administrator'}
$mutex=[Threading.Mutex]::new($false,'Global\BybitClusterGridTaskPreparation')
$held=$false
try {
try {$held=$mutex.WaitOne(0)} catch [Threading.AbandonedMutexException] {$held=$true}
if(!$held){throw 'Another Grid task preparation is running'}
foreach($value in @($ReleaseDir,$Python,$InstallRoot)){
 if($value -match '["\r\n]'){throw 'Invalid task action path'}
}
# Never replace/remove an existing installation's tasks during preparation.
# A separately reviewed stop/upgrade procedure owns existing tasks.
$existing=@(Get-ScheduledTask -ErrorAction Stop | Where-Object {$_.TaskName -in @($TaskName,$ArchiveTaskName,$CoordinatorTaskName)})
if($existing.Count){throw 'Existing Grid tasks require reviewed upgrade; left unchanged'}
$manifest=Get-Content -LiteralPath (Join-Path $ReleaseDir 'release-manifest.json') -Raw | ConvertFrom-Json
$role=if($Mode -eq 'CONTROL'){'CONTROL'}else{'WORKER'}
$checker=Join-Path $ReleaseDir 'installer\windows_preflight.py'
$checkArgs=@('-B',$checker,'--release-dir',$ReleaseDir,'--expected-sha',[string]$manifest.version,'--role',$role,'--env-file',(Join-Path $DataRoot '.env'))
if($Mode -eq 'CONTROL'){$checkArgs+='--check-db'}
# Inherit credentials only through the protected env file, never task arguments.
$preflight=& $Python @checkArgs
if($LASTEXITCODE -ne 0){throw 'Read-only commissioning preflight blocked registration'}
if($StartServices){throw 'Permanent activation requires a separate reviewed commissioning action'}
$InstallerRoot=Join-Path $DataRoot "installer"
New-Item -ItemType Directory -Force -Path $InstallerRoot | Out-Null
# Both worker and CONTROL launchers depend on the persistent recovery script.
# Verify and stage recovery before replacing any existing launcher files.
$RecoverySource = Join-Path $ReleaseDir "installer\recover-release.ps1"
if (!(Test-Path -LiteralPath $RecoverySource -PathType Leaf)) {
  throw "Release missing required recovery script: $RecoverySource"
}
Copy-Item -LiteralPath $RecoverySource -Destination (Join-Path $InstallerRoot "recover-release.ps1") -Force
if (!(Test-Path -LiteralPath (Join-Path $InstallerRoot "recover-release.ps1") -PathType Leaf)) {
  throw "Recovery script staging failed"
}
Copy-Item (Join-Path $ReleaseDir "installer\launcher.ps1") (Join-Path $InstallerRoot "launcher.ps1") -Force
Copy-Item (Join-Path $ReleaseDir "installer\archive-launcher.ps1") (Join-Path $InstallerRoot "archive-launcher.ps1") -Force
Copy-Item (Join-Path $ReleaseDir "installer\uninstall.ps1") (Join-Path $InstallerRoot "uninstall.ps1") -Force
Copy-Item (Join-Path $ReleaseDir "installer\preflight.ps1") (Join-Path $InstallerRoot "preflight.ps1") -Force
$Launcher=Join-Path $InstallerRoot "launcher.ps1"
$ArchiveLauncher=Join-Path $InstallerRoot "archive-launcher.ps1"
$CoordinatorLauncher=Join-Path $InstallerRoot "coordinator-launcher.ps1"
if(Test-Path (Join-Path $ReleaseDir "installer\coordinator-launcher.ps1")){ Copy-Item (Join-Path $ReleaseDir "installer\coordinator-launcher.ps1") $CoordinatorLauncher -Force }
$arg='-NoProfile -ExecutionPolicy Bypass -File "'+$Launcher+'" -Python "'+$Python+'" -InstallRoot "'+$InstallRoot+'"'
$Action=New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arg -WorkingDirectory $InstallRoot
$Trigger=New-ScheduledTaskTrigger -AtStartup
$Principal=New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$Settings=New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
# Grid services are long-running. Task Scheduler defaults to a 72-hour limit;
# explicitly disable it so healthy workers/coordinators are not terminated.
# Windows Task Scheduler requires the ISO-8601 duration PT0S, not 00:00:00.
# Apply this via task XML after registration, before starting the service.
function Disable-TaskExecutionLimit([string]$Name) {
  [xml]$xml = Export-ScheduledTask -TaskName $Name -ErrorAction Stop
  $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
  $ns.AddNamespace("t", "http://schemas.microsoft.com/windows/2004/02/mit/task")
  $node = $xml.SelectSingleNode("/t:Task/t:Settings/t:ExecutionTimeLimit", $ns)
  if($null -eq $node) {
    $settings = $xml.SelectSingleNode("/t:Task/t:Settings", $ns)
    if($null -eq $settings) { throw "Task settings missing: $Name" }
    $node = $xml.CreateElement("ExecutionTimeLimit", $ns.LookupNamespace("t"))
    [void]$settings.AppendChild($node)
  }
  $node.InnerText = "PT0S"
  Register-ScheduledTask -TaskName $Name -Xml $xml.OuterXml -Force -ErrorAction Stop | Out-Null
  [xml]$verify = Export-ScheduledTask -TaskName $Name -ErrorAction Stop
  $actual = $verify.SelectSingleNode("/t:Task/t:Settings/t:ExecutionTimeLimit", $ns)
  if($null -eq $actual -or $actual.InnerText -ne "PT0S") {
    throw "Task execution limit verification failed for $Name"
  }
}
# Dedicated/remote nodes must recover after mains loss even when Windows reports
# battery/UPS power. Power source must not suppress or terminate Grid services.
$Settings.DisallowStartIfOnBatteries=$false
$Settings.StopIfGoingOnBatteries=$false
# Never overlap service instances during slow shutdown, restart retries, or cold boot.
# A second coordinator/worker/archive process would duplicate sockets, leases and work.
$Settings.MultipleInstances="IgnoreNew"
$Settings.Enabled=$false
$ArchiveArg='-NoProfile -ExecutionPolicy Bypass -File "'+$ArchiveLauncher+'" -Python "'+$Python+'" -InstallRoot "'+$InstallRoot+'"'
$ArchiveAction=New-ScheduledTaskAction -Execute "powershell.exe" -Argument $ArchiveArg -WorkingDirectory $InstallRoot
# Archive/backfill owns direct PostgreSQL work and therefore belongs on CONTROL.
# PILOT/NORMAL agents are intentionally DB-less and must never start this service.
# Standalone ArchivePipeline is intentionally fenced off; never register/start it.

if($Mode -eq "CONTROL"){
  if(!(Test-Path $CoordinatorLauncher)){throw "CONTROL launcher missing"}
  $CoordArg='-NoProfile -ExecutionPolicy Bypass -File "'+$CoordinatorLauncher+'" -Python "'+$Python+'" -InstallRoot "'+$InstallRoot+'"'
  $CoordAction=New-ScheduledTaskAction -Execute "powershell.exe" -Argument $CoordArg -WorkingDirectory $InstallRoot
  Register-ScheduledTask -TaskName $CoordinatorTaskName -Action $CoordAction -Trigger $Trigger -Principal $Principal -Settings $Settings -ErrorAction Stop | Out-Null
  Disable-TaskExecutionLimit $CoordinatorTaskName
}else{
  Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -ErrorAction Stop | Out-Null
  Disable-TaskExecutionLimit $TaskName
}
Write-Host "Bybit Cluster Grid task prepared disabled in $Mode mode; no service started."
} finally {if($held){$mutex.ReleaseMutex()};$mutex.Dispose()}
