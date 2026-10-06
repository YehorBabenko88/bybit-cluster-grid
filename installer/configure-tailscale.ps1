#Requires -RunAsAdministrator
param(
  [string]$AuthKey="",
  [string]$AdvertiseTags="tag:grid-node"
)
$ErrorActionPreference="Stop"
$exe=Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
if(!(Test-Path $exe)){
  $winget=Get-Command winget.exe -ErrorAction SilentlyContinue
  if(!$winget){throw "Tailscale is not installed and winget is unavailable for automatic installation."}
  Write-Host "Installing official Tailscale Windows client..."
  & $winget.Source install --id Tailscale.Tailscale --exact --silent --accept-package-agreements --accept-source-agreements
  if($LASTEXITCODE -ne 0){throw "Automatic Tailscale installation failed"}
  if(!(Test-Path $exe)){throw "Tailscale installation completed but tailscale.exe was not found"}
}
# Never persist or print AuthKey. Existing authenticated nodes need no key.
$status=& $exe status --json 2>$null
$backend=""
if($LASTEXITCODE -eq 0 -and $status){
  try{$backend=([string](($status|ConvertFrom-Json).BackendState))}catch{}
}
if($backend -ne "Running"){
  if(!$AuthKey){throw "Tailscale is not authenticated and no one-time AuthKey was supplied."}
  & $exe up --auth-key=$AuthKey --advertise-tags=$AdvertiseTags
  if($LASTEXITCODE -ne 0){throw "Tailscale authentication failed"}
}
# Windows unattended mode keeps the tailnet reachable after sign-out/reboot.
& $exe set --unattended=true
if($LASTEXITCODE -ne 0){throw "Failed to enable Tailscale unattended mode"}
$status=& $exe status --json | ConvertFrom-Json
if([string]$status.BackendState -ne "Running"){throw "Tailscale is not Running"}
Write-Host "Tailscale ready in unattended mode."
