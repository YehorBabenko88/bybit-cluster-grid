#Requires -RunAsAdministrator
param(
 [Parameter(Mandatory=$true)][string]$CoordinatorAdminUrl,
 [Parameter(Mandatory=$true)][string]$AgentCoordinatorUrl,
 [Parameter(Mandatory=$true)][string]$OutputPath,
 [ValidateSet("PILOT","NORMAL")][string]$InstallMode="NORMAL",
 [string]$Label="grid-node",
 [int]$TtlMinutes=20,
 [string]$ControlEnvPath="$env:ProgramData\BybitClusterGrid\.env"
)
$ErrorActionPreference="Stop"
if(!(Test-Path $ControlEnvPath)){throw "CONTROL .env not found"}
$line=Get-Content $ControlEnvPath | Where-Object {$_ -match '^GRID_SHARED_TOKEN=.+$'} | Select-Object -Last 1
if(!$line){throw "GRID_SHARED_TOKEN is not configured on CONTROL"}
$token=$line.Substring("GRID_SHARED_TOKEN=".Length)
$body=@{
  coordinator_url=$AgentCoordinatorUrl
  install_mode=$InstallMode
  label=$Label
  ttl_minutes=$TtlMinutes
} | ConvertTo-Json
try {
  $r=Invoke-RestMethod -Method Post `
    -Uri ($CoordinatorAdminUrl.TrimEnd("/")+"/bootstrap/envelope") `
    -Headers @{"X-Grid-Token"=$token} `
    -ContentType "application/json" -Body $body
  $dir=Split-Path ([IO.Path]::GetFullPath($OutputPath)) -Parent
  if($dir){New-Item -ItemType Directory -Force -Path $dir | Out-Null}
  $r | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $OutputPath
  & icacls $OutputPath /inheritance:r /grant:r "$env:USERNAME:F" "Administrators:F" | Out-Null
  Write-Host "One-time bootstrap envelope created. Transfer it securely and use it before expiry."
} finally {
  $token=$null
  $body=$null
  $r=$null
}
