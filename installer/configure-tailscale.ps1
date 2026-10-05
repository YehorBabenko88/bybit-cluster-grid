#Requires -RunAsAdministrator
param(
  [string]$AuthKey="",
  [string]$AdvertiseTags="tag:grid-node"
)
$ErrorActionPreference="Stop"
$exe=Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
if(!(Test-Path $exe)){
  throw "Tailscale is not installed. Install the official Windows client, then rerun Grid bootstrap."
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
