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
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null

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
  Start-ScheduledTask $CoordinatorTaskName
  Start-ScheduledTask $ArchiveTaskName
}else{
  Unregister-ScheduledTask $CoordinatorTaskName -Confirm:$false -ErrorAction SilentlyContinue
  Start-ScheduledTask $TaskName
}
Write-Host "Bybit Cluster Grid installed in $Mode mode."
