#Requires -RunAsAdministrator
param(
 [Parameter(Mandatory=$true)][string]$ReleaseDir,
 [Parameter(Mandatory=$true)][string]$Python,
 [ValidateSet("PILOT","NORMAL")][string]$Mode="NORMAL"
)
$ErrorActionPreference="Stop"
$TaskName="BybitClusterGridAgent"
$ArchiveTaskName="BybitClusterGridArchivePipeline"
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
$arg='-NoProfile -ExecutionPolicy Bypass -File "'+$Launcher+'" -Python "'+$Python+'" -InstallRoot "'+$InstallRoot+'"'
$Action=New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arg -WorkingDirectory $InstallRoot
$Trigger=New-ScheduledTaskTrigger -AtStartup
$Principal=New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$Settings=New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null

$ArchiveArg='-NoProfile -ExecutionPolicy Bypass -File "'+$ArchiveLauncher+'" -Python "'+$Python+'" -InstallRoot "'+$InstallRoot+'"'
$ArchiveAction=New-ScheduledTaskAction -Execute "powershell.exe" -Argument $ArchiveArg -WorkingDirectory $InstallRoot
if($Mode -eq "NORMAL"){
  Register-ScheduledTask -TaskName $ArchiveTaskName -Action $ArchiveAction -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
}else{
  Unregister-ScheduledTask $ArchiveTaskName -Confirm:$false -ErrorAction SilentlyContinue
}

Start-ScheduledTask $TaskName
if($Mode -eq "NORMAL"){ Start-ScheduledTask $ArchiveTaskName }
Write-Host "Bybit Cluster Grid installed in $Mode mode."
