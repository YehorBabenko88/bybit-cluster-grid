#Requires -RunAsAdministrator
param(
  [string]$CoordinatorUrl="",
  [string]$EnrollmentToken=""
)
$ErrorActionPreference="Stop"
$InstallRoot="$env:ProgramFiles\BybitClusterGrid"
$DataRoot="$env:ProgramData\BybitClusterGrid"
$RuntimeRoot=Join-Path $DataRoot "runtime"
$Venv=Join-Path $RuntimeRoot "venv"
New-Item -ItemType Directory -Force -Path $InstallRoot,$DataRoot,$RuntimeRoot,(Join-Path $DataRoot "logs") | Out-Null

$Discovery=& (Join-Path $PSScriptRoot "discover.ps1") | ConvertFrom-Json
$Discovery | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 (Join-Path $DataRoot "discovery.json")

$Bundle=Join-Path $PSScriptRoot "bybit-cluster-grid.zip"
if(!(Test-Path $Bundle)){throw "Missing bybit-cluster-grid.zip"}
$Release=Join-Path $InstallRoot "bootstrap"
if(Test-Path $Release){Remove-Item -Recurse -Force $Release}
Expand-Archive $Bundle $Release -Force

# Never install packages into an unrelated global Python.
$BasePython=$null
foreach($p in $Discovery.python){
    try {
        $parts=@($p.version.Split(".") | ForEach-Object {[int]$_})
        if($parts[0] -eq 3 -and $parts[1] -ge 11){$BasePython=$p.exe;break}
    } catch {}
}
if(!$BasePython){
    $Bundled=Join-Path $Release "runtime\python.exe"
    if(Test-Path $Bundled){$BasePython=$Bundled}
}
if(!$BasePython){throw "No compatible Python >=3.11. Bundle an isolated Python runtime."}

if(!(Test-Path (Join-Path $Venv "Scripts\python.exe"))){
    & $BasePython -m venv $Venv
}
$Python=Join-Path $Venv "Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install --upgrade -r (Join-Path $Release "requirements.txt")

# Existing PostgreSQL is discovered, never upgraded/reconfigured automatically.
# Provisioning is delegated to provision_postgres.ps1, which creates only Grid-owned DB/user.
& (Join-Path $PSScriptRoot "provision_postgres.ps1") -DiscoveryPath (Join-Path $DataRoot "discovery.json") -DataRoot $DataRoot

$EnvFile=Join-Path $DataRoot ".env"
if(!(Test-Path $EnvFile)){
    @(
      "ROLE=worker",
      "GRID_DATA_PATH=$DataRoot",
      "STRATEGY_CACHE_DIR=$DataRoot\runtime_strategies",
      "COORDINATOR_URL=$CoordinatorUrl",
      "ENROLLMENT_TOKEN=$EnrollmentToken"
    ) | Set-Content -Encoding UTF8 $EnvFile
}

& (Join-Path $PSScriptRoot "preflight.ps1") -ReleaseDir $Release
& (Join-Path $PSScriptRoot "install.ps1") -ReleaseDir $Release -Python $Python
