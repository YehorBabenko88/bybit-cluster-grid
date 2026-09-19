#Requires -RunAsAdministrator
$TaskName="BybitClusterGridAgent"
$InstallRoot="$env:ProgramFiles\BybitClusterGrid"
$DataRoot="$env:ProgramData\BybitClusterGrid"
Stop-ScheduledTask $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $InstallRoot -ErrorAction SilentlyContinue
if ($args -contains "--purge-data") { Remove-Item -Recurse -Force $DataRoot -ErrorAction SilentlyContinue }
Write-Host "Agent removed; data preserved unless --purge-data was supplied."
