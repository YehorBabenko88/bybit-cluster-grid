#Requires -RunAsAdministrator
param(
  [string]$CoordinatorUrl="",
  [string]$EnrollmentToken=""
)
$ErrorActionPreference="Stop"
$InstallRoot="$env:ProgramFiles\BybitClusterGrid"
$DataRoot="$env:ProgramData\BybitClusterGrid"
$RuntimeRoot=Join-Path $DataRoot "runtime"
$StateFile=Join-Path $DataRoot "install-state.json"
$Mode="fresh"
if(Test-Path $StateFile){$Mode="repair"}
elseif((Test-Path $InstallRoot) -or (Test-Path (Join-Path $DataRoot ".env"))){$Mode="upgrade"}
$Venv=Join-Path $RuntimeRoot "venv"
New-Item -ItemType Directory -Force -Path $InstallRoot,$DataRoot,$RuntimeRoot,(Join-Path $DataRoot "logs") | Out-Null
@{mode=$Mode;status="installing";started_at=(Get-Date).ToUniversalTime().ToString("o")} |
    ConvertTo-Json | Set-Content -Encoding UTF8 $StateFile
Write-Host "Grid install mode: $Mode"

$Discovery=& (Join-Path $PSScriptRoot "discover.ps1") | ConvertFrom-Json
$Discovery | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 (Join-Path $DataRoot "discovery.json")

$Bundle=Join-Path $PSScriptRoot "bybit-cluster-grid.zip"
if(!(Test-Path $Bundle)){throw "Missing bybit-cluster-grid.zip"}
$Release=Join-Path $InstallRoot "bootstrap"
$Stage=Join-Path $InstallRoot "bootstrap.staging"
if(Test-Path $Stage){Remove-Item -Recurse -Force $Stage}
Expand-Archive $Bundle $Stage -Force
if(Test-Path $Release){
    $Backup=Join-Path $InstallRoot "bootstrap.previous"
    if(Test-Path $Backup){Remove-Item -Recurse -Force $Backup}
    Move-Item $Release $Backup
}
Move-Item $Stage $Release

# Prefer an isolated Grid-owned Python runtime. Never mutate system Python.
$OwnedPython=Join-Path $RuntimeRoot "python\python.exe"
$Bundled=Join-Path $Release "runtime\python.exe"
if(!(Test-Path $OwnedPython)){
    if(Test-Path $Bundled){
        $OwnedRoot=Split-Path $OwnedPython -Parent
        New-Item -ItemType Directory -Force -Path $OwnedRoot | Out-Null
        Copy-Item (Split-Path $Bundled -Parent) $OwnedRoot -Recurse -Force
    } else {
        throw "Grid-owned Python runtime is missing from deployment bundle."
    }
}
$BasePython=$OwnedPython
try {
    $ver=& $BasePython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    $vp=$ver.Trim().Split(".")
    if([int]$vp[0] -ne 3 -or [int]$vp[1] -lt 11){throw "Grid Python must be >=3.11"}
} catch {
    throw "Grid-owned Python runtime is damaged or incompatible: $($_.Exception.Message)"
}

$VenvPython=Join-Path $Venv "Scripts\python.exe"
$RebuildVenv=$false
if(!(Test-Path $VenvPython)){$RebuildVenv=$true}
else {
    & $VenvPython -c "import sys; assert sys.version_info >= (3,11)" 2>$null
    if($LASTEXITCODE -ne 0){$RebuildVenv=$true}
}
if($RebuildVenv){
    if(Test-Path $Venv){Remove-Item -Recurse -Force $Venv}
    & $BasePython -m venv $Venv
    if($LASTEXITCODE -ne 0){throw "Failed to create Grid virtual environment"}
}
$Python=$VenvPython
& $Python -m pip install --upgrade pip
if($LASTEXITCODE -ne 0){throw "Failed to update Grid pip"}
& $Python -m pip install --upgrade -r (Join-Path $Release "requirements.txt")
if($LASTEXITCODE -ne 0){throw "Failed to install Grid dependencies"}

$EnvFile=Join-Path $DataRoot ".env"
if(!(Test-Path $EnvFile)){
    @(
      "ROLE=worker",
      "GRID_DATA_PATH=$DataRoot",
      "STRATEGY_CACHE_DIR=$DataRoot\\runtime_strategies",
      "COORDINATOR_URL=$CoordinatorUrl"
    ) | Set-Content -Encoding UTF8 $EnvFile
}

# Existing PostgreSQL is discovered, never upgraded/reconfigured automatically.
& (Join-Path $PSScriptRoot "provision_postgres.ps1") -DiscoveryPath (Join-Path $DataRoot "discovery.json") -DataRoot $DataRoot

$CredentialFile=Join-Path $DataRoot "secrets\node.credential"
if(!(Test-Path $CredentialFile)){
    if(!$CoordinatorUrl -or !$EnrollmentToken){
        throw "Node is not enrolled and CoordinatorUrl/EnrollmentToken were not supplied."
    }
    Push-Location $Release
    try {
        & (Join-Path $PSScriptRoot "enroll.ps1") -CoordinatorUrl $CoordinatorUrl -EnrollmentToken $EnrollmentToken -Python $Python -DataRoot $DataRoot | Out-Null
    } finally { Pop-Location }
} else {
    Write-Host "Existing node credential found; preserving node identity."
}

& (Join-Path $PSScriptRoot "preflight.ps1") -ReleaseDir $Release -Python $Python
& (Join-Path $PSScriptRoot "install.ps1") -ReleaseDir $Release -Python $Python
@{mode=$Mode;status="installed";completed_at=(Get-Date).ToUniversalTime().ToString("o")} |
    ConvertTo-Json | Set-Content -Encoding UTF8 $StateFile
