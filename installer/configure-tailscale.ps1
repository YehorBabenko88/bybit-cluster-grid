#Requires -RunAsAdministrator
param(
  [string]$AuthKey="",
  [string]$AdvertiseTags="tag:grid-node",
  [string]$MsiPath=""
)
$ErrorActionPreference="Stop"
$exe=Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
if(!(Test-Path $exe)){
  if($MsiPath -and (Test-Path $MsiPath)){
    Write-Host "Installing bundled official Tailscale MSI silently..."
    $p=Start-Process msiexec.exe -ArgumentList @(
      "/i",('"'+$MsiPath+'"'),"/qn","/norestart",
      "TS_NOLAUNCH=1","TS_UNATTENDEDMODE=always",
      "TS_ONBOARDING_FLOW=hide","TS_UPDATEMENU=hide"
    ) -Wait -PassThru
    if($p.ExitCode -notin @(0,3010)){throw "Silent Tailscale MSI installation failed: $($p.ExitCode)"}
  } else {
    $winget=Get-Command winget.exe -ErrorAction SilentlyContinue
    if(!$winget){throw "Tailscale is not installed; provide an approved MSI or install Tailscale first."}
    Write-Host "Installing official Tailscale Windows client silently..."
    & $winget.Source install --id Tailscale.Tailscale --exact --silent --accept-package-agreements --accept-source-agreements
    if($LASTEXITCODE -ne 0){throw "Automatic Tailscale installation failed"}
  }
  if(!(Test-Path $exe)){throw "Tailscale installation completed but tailscale.exe was not found"}
}
# System policy: service remains available but the interactive tray client is
# unnecessary on dedicated Grid nodes. Do not kill tailscaled/service.
$policy="HKLM:\SOFTWARE\Policies\Tailscale"
New-Item -Path $policy -Force | Out-Null
New-ItemProperty -Path $policy -Name "UnattendedMode" -Value "always" -PropertyType String -Force | Out-Null
New-ItemProperty -Path $policy -Name "OnboardingFlow" -Value "hide" -PropertyType String -Force | Out-Null
New-ItemProperty -Path $policy -Name "UpdateMenu" -Value "hide" -PropertyType String -Force | Out-Null
New-ItemProperty -Path $policy -Name "AdminConsole" -Value "hide" -PropertyType String -Force | Out-Null
New-ItemProperty -Path $policy -Name "NetworkDevices" -Value "hide" -PropertyType String -Force | Out-Null
New-ItemProperty -Path $policy -Name "PreferencesMenu" -Value "hide" -PropertyType String -Force | Out-Null
New-ItemProperty -Path $policy -Name "ExitNodesPicker" -Value "hide" -PropertyType String -Force | Out-Null
New-ItemProperty -Path $policy -Name "RunExitNode" -Value "hide" -PropertyType String -Force | Out-Null
New-ItemProperty -Path $policy -Name "TestMenu" -Value "hide" -PropertyType String -Force | Out-Null

# Prevent the per-user tray executable from auto-starting where present. This
# does not disable the Tailscale Windows service or networking.
Get-ScheduledTask -ErrorAction SilentlyContinue |
  Where-Object {$_.TaskName -match "Tailscale" -and $_.TaskPath -notmatch "BybitClusterGrid"} |
  ForEach-Object {
    $actions=@($_.Actions | ForEach-Object {[string]$_.Execute})
    if($actions -match "tailscale-ipn.exe"){Disable-ScheduledTask -InputObject $_ -ErrorAction SilentlyContinue | Out-Null}
  }
Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue |
  Where-Object {$_.Command -match "tailscale-ipn.exe"} | Out-Null

$status=& $exe status --json 2>$null
$backend=""
if($LASTEXITCODE -eq 0 -and $status){
  try{$backend=([string](($status|ConvertFrom-Json).BackendState))}catch{}
}
if($backend -ne "Running"){
  if(!$AuthKey){throw "Tailscale is not authenticated and no bootstrap AuthKey was supplied."}
  # AuthKey is never written to disk or shell history by this script.
  & $exe up --auth-key=$AuthKey --advertise-tags=$AdvertiseTags
  if($LASTEXITCODE -ne 0){throw "Tailscale authentication failed"}
}
& $exe set --unattended=true
if($LASTEXITCODE -ne 0){throw "Failed to enable Tailscale unattended mode"}
# Apply local device policies immediately on modern clients and make policy
# mistakes visible during commissioning rather than silently accepting them.
& $exe syspolicy reload 2>$null | Out-Host
$status=& $exe status --json | ConvertFrom-Json
if([string]$status.BackendState -ne "Running"){throw "Tailscale is not Running"}
Write-Host "Tailscale ready in unattended headless mode."
