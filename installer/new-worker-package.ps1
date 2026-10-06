#Requires -RunAsAdministrator
param(
 [Parameter(Mandatory=$true)][string]$BundlePath,
 [Parameter(Mandatory=$true)][string]$EnvelopePath,
 [Parameter(Mandatory=$true)][string]$TailscaleMsiPath,
 [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference="Stop"
$out=[IO.Path]::GetFullPath($OutputDirectory)
if(Test-Path $out){Remove-Item $out -Recurse -Force}
New-Item -ItemType Directory -Force -Path $out | Out-Null
Copy-Item $BundlePath (Join-Path $out "grid-bundle.zip") -Force
Copy-Item $EnvelopePath (Join-Path $out "bootstrap-envelope.json") -Force
Copy-Item $TailscaleMsiPath (Join-Path $out "tailscale.msi") -Force
$installerOut=Join-Path $out "installer"
New-Item -ItemType Directory -Force -Path $installerOut | Out-Null
Copy-Item (Join-Path $PSScriptRoot "*") $installerOut -Recurse -Force
# The complete installer directory is included because bootstrap performs
# Tailscale/discovery/enrollment work before the release bundle is published.
$cmd=@'
@echo off
net session >nul 2>&1
if not %errorlevel%==0 (
  powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
  exit /b
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\bootstrap-from-envelope.ps1" -EnvelopePath "%~dp0bootstrap-envelope.json" -BundlePath "%~dp0grid-bundle.zip" -TailscaleMsiPath "%~dp0tailscale.msi"
set EC=%errorlevel%
if %EC%==0 (
  echo Grid installation completed successfully.
) else (
  echo Grid installation failed with code %EC%.
)
pause
exit /b %EC%
'@
Set-Content -Encoding ASCII (Join-Path $out "Install-Grid.cmd") $cmd
& icacls (Join-Path $out "bootstrap-envelope.json") /inheritance:r /grant:r "$env:USERNAME:F" "Administrators:F" | Out-Null
Write-Host "One-click worker package created: $out"
