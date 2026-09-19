#Requires -RunAsAdministrator
param(
 [Parameter(Mandatory=$true)][string]$ReleaseDir,
 [Parameter(Mandatory=$true)][string]$Python
)
$ErrorActionPreference="Stop"
$TaskName="BybitClusterGridAgent"
$DataRoot="$env:ProgramData\BybitClusterGrid"
$Run=Join-Path $ReleaseDir "run_worker.py"
$Env:GRID_ENV_FILE=Join-Path $DataRoot ".env"
$Action=New-ScheduledTaskAction -Execute $Python -Argument ('"'+$Run+'"') -WorkingDirectory $ReleaseDir
$Trigger=New-ScheduledTaskTrigger -AtStartup
$Principal=New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$Settings=New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
Start-ScheduledTask $TaskName
Write-Host "Bybit Cluster Grid installed and started."
