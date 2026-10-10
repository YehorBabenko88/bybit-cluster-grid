#Requires -RunAsAdministrator
param(
 [Parameter(Mandatory=$true)][string]$ReleaseDir,
 [Parameter(Mandatory=$true)][string]$Python,
 [ValidateSet("CONTROL","PILOT","NORMAL")][string]$Mode="NORMAL"
)
$ErrorActionPreference="Stop"
$TaskName="BybitClusterGridAgent"
$ArchiveTaskName="BybitClusterGridArchivePipeline"
$CoordinatorTaskName="BybitClusterGridCoordinator"
$InstallRoot="$env:ProgramFiles\BybitClusterGrid"
$DataRoot="$env:ProgramData\BybitClusterGrid"
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
$ArchiveArg='-NoProfile -ExecutionPolicy Bypass -File "'+$ArchiveLauncher+'" -Python "'+$Python+'" -InstallRoot "'+$InstallRoot+'"'
$ArchiveAction=New-ScheduledTaskAction -Execute "powershell.exe" -Argument $ArchiveArg -WorkingDirectory $InstallRoot
# Archive/backfill owns direct PostgreSQL work and therefore belongs on CONTROL.
# PILOT/NORMAL agents are intentionally DB-less and must never start this service.
if($Mode -eq "CONTROL"){
  Register-ScheduledTask -TaskName $ArchiveTaskName -Action $ArchiveAction -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
}else{
  Unregister-ScheduledTask $ArchiveTaskName -Confirm:$false -ErrorAction SilentlyContinue
}

if($Mode -eq "CONTROL"){
  if(!(Test-Path $CoordinatorLauncher)){throw "CONTROL launcher missing"}
  $CoordArg='-NoProfile -ExecutionPolicy Bypass -File "'+$CoordinatorLauncher+'" -Python "'+$Python+'" -InstallRoot "'+$InstallRoot+'"'
  $CoordAction=New-ScheduledTaskAction -Execute "powershell.exe" -Argument $CoordArg -WorkingDirectory $InstallRoot
  Register-ScheduledTask -TaskName $CoordinatorTaskName -Action $CoordAction -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
  Unregister-ScheduledTask $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  Disable-TaskExecutionLimit $CoordinatorTaskName
  Disable-TaskExecutionLimit $ArchiveTaskName
  Start-ScheduledTask $CoordinatorTaskName
  Start-ScheduledTask $ArchiveTaskName
}else{
  Unregister-ScheduledTask $CoordinatorTaskName -Confirm:$false -ErrorAction SilentlyContinue
  Unregister-ScheduledTask $ArchiveTaskName -Confirm:$false -ErrorAction SilentlyContinue
  Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
  Disable-TaskExecutionLimit $TaskName
  Start-ScheduledTask $TaskName
}
Write-Host "Bybit Cluster Grid installed in $Mode mode."
