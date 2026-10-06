#Requires -RunAsAdministrator
param(
 [Parameter(Mandatory=$true)][string]$EnvelopePath,
 [string]$BundlePath="",
 [string]$TailscaleMsiPath=""
)
$ErrorActionPreference="Stop"
if(!(Test-Path $EnvelopePath)){throw "Bootstrap envelope not found"}
$full=[IO.Path]::GetFullPath($EnvelopePath)
try {
    $e=Get-Content $full -Raw | ConvertFrom-Json
    if([int]$e.schema -ne 1){throw "Unsupported bootstrap envelope schema"}
    $expiry=[DateTimeOffset]::Parse([string]$e.expires_at)
    if($expiry -le [DateTimeOffset]::UtcNow){throw "Bootstrap envelope expired"}
    if(!$e.coordinator_url -or !$e.enrollment_token -or !$e.tailscale_auth_key){
        throw "Bootstrap envelope is incomplete"
    }
    & (Join-Path $PSScriptRoot "bootstrap.ps1") `
      -CoordinatorUrl ([string]$e.coordinator_url) `
      -EnrollmentToken ([string]$e.enrollment_token) `
      -TailscaleAuthKey ([string]$e.tailscale_auth_key) `
      -TailscaleTags ([string]$e.tailscale_tags) `
      -TailscaleMsiPath $TailscaleMsiPath `
      -BundlePath $BundlePath `
      -AgentMode AUTO
    if($LASTEXITCODE -ne 0){throw "Grid bootstrap failed"}
} finally {
    # Envelope contains two bootstrap-only credentials. Never retain it.
    Remove-Item $full -Force -ErrorAction SilentlyContinue
    $e=$null
}
