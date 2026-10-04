param(
 [string]$ServiceName="BybitClusterGrid",
 [string]$GridRoot="C:\ProgramData\BybitClusterGrid"
)
$ErrorActionPreference="Stop"
if (-not (Test-Path $GridRoot)) { New-Item -ItemType Directory -Path $GridRoot -Force | Out-Null }

# Ordinary service resilience: restart after crashes/stops; never hides the process or blocks administrators.
sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
sc.exe failureflag $ServiceName 1 | Out-Null
sc.exe config $ServiceName start= delayed-auto | Out-Null

# Users may read/execute Grid files, but routine non-admin accounts cannot accidentally modify them.
# SYSTEM and Administrators retain full control so the software remains normally removable/manageable.
icacls $GridRoot /inheritance:r | Out-Null
icacls $GridRoot /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" "Users:(OI)(CI)RX" | Out-Null

Write-Output "Grid service recovery and conservative ACLs configured."

# Never make the service undeletable or hostile to administrators. Windows SCM remains
# the authority: an Administrator can stop, repair, update or uninstall it normally.
# Recovery only covers accidental crashes/reboots.
