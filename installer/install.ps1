#Requires -RunAsAdministrator
$ErrorActionPreference="Stop"
$InstallRoot="$env:ProgramFiles\BybitClusterGrid"
$DataRoot="$env:ProgramData\BybitClusterGrid"
New-Item -ItemType Directory -Force -Path $InstallRoot,$DataRoot,(Join-Path $DataRoot "logs") | Out-Null
$Bundle=Join-Path $PSScriptRoot "bybit-cluster-grid.zip"
if (!(Test-Path $Bundle)) { throw "Missing bybit-cluster-grid.zip" }
$Release=Join-Path $InstallRoot "bootstrap"
if (Test-Path $Release) { Remove-Item -Recurse -Force $Release }
Expand-Archive $Bundle $Release -Force
$Python=(Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (!$Python) { $Python=Join-Path $Release "runtime\python.exe" }
if (!(Test-Path $Python)) { throw "Python runtime missing" }
& $Python -m pip install --disable-pip-version-check --no-input -r (Join-Path $Release "requirements.txt")
$TaskName="BybitClusterGridAgent"
$Run=Join-Path $Release "run_worker.py"
$Action=New-ScheduledTaskAction -Execute $Python -Argument ('"'+$Run+'"') -WorkingDirectory $Release
$Trigger=New-ScheduledTaskTrigger -AtStartup
$Principal=New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$Settings=New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
Start-ScheduledTask $TaskName
Write-Host "Bybit Cluster Grid installed and started."
