#Requires -RunAsAdministrator
param(
  [Parameter(Mandatory=$true)][ValidatePattern("^https://")][string]$BundleUrl,
  [Parameter(Mandatory=$true)][ValidatePattern("^[A-Fa-f0-9]{64}$")][string]$BundleSha256,
  [Parameter(Mandatory=$true)][ValidatePattern("^https?://")][string]$CoordinatorUrl,
  [Parameter(Mandatory=$true)][string]$EnrollmentToken
)
$ErrorActionPreference="Stop"
$work=Join-Path $env:TEMP ("BybitClusterGrid-Onboard-"+[guid]::NewGuid().ToString("N"))
$zip=Join-Path $work "bundle.zip"
$expanded=Join-Path $work "expanded"
try {
  New-Item -ItemType Directory -Force -Path $work,$expanded | Out-Null
  Invoke-WebRequest -UseBasicParsing -Uri $BundleUrl -OutFile $zip
  $actual=(Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
  if($actual -ne $BundleSha256.ToLowerInvariant()){ throw "Bundle SHA256 mismatch" }
  Expand-Archive $zip $expanded -Force
  $bootstrap=Join-Path $expanded "installer\bootstrap.ps1"
  if(!(Test-Path $bootstrap)){ throw "Bundle does not contain installer/bootstrap.ps1" }
  & $bootstrap -CoordinatorUrl $CoordinatorUrl -EnrollmentToken $EnrollmentToken -AgentMode AUTO -BundlePath $zip
  if($LASTEXITCODE -ne 0){ throw "Grid bootstrap failed" }
} finally {
  Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}
