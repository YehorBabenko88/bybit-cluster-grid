param(
  [Parameter(Mandatory=$true)][string]$Python,
  [string]$BasePython="",
  [Parameter(Mandatory=$true)][string]$ReleaseDir,
  [Parameter(Mandatory=$true)][string]$RuntimeRoot,
  [ValidateSet("CONTROL","PILOT","NORMAL")][string]$Mode="NORMAL"
)
$ErrorActionPreference="Stop"
$Req=Join-Path $ReleaseDir "requirements-ml.txt"
if(!(Test-Path $Req)){throw "Missing ML requirements: $Req"}
if(!(Test-Path -LiteralPath $Python)){throw "Missing ML Python runtime: $Python"}
New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
# Heavy dependencies must never mutate the market-data worker venv.
$MLVenv=Join-Path $RuntimeRoot "ml-venv"
$MLPython=Join-Path $MLVenv "Scripts\python.exe"
if(!$BasePython){$BasePython=$Python}
$State=Join-Path $RuntimeRoot "ml-requirements.sha256"
$Journal=Join-Path $RuntimeRoot "ml-bootstrap.json"
$Hash=(Get-FileHash -Algorithm SHA256 $Req).Hash.ToLowerInvariant()
$Old=if(Test-Path $State){(Get-Content $State -Raw).Trim()}else{""}

# CONTROL orchestrates ML and PILOT is allowed to validate compute capability.
# NORMAL collectors stay lightweight until promoted/assigned as compute nodes.
$ShouldInstall=$Mode -in @("CONTROL","PILOT")
if(!$ShouldInstall){
  [ordered]@{status="skipped";mode=$Mode;reason="collector-only node";at=(Get-Date).ToUniversalTime().ToString("o")} |
    ConvertTo-Json | Set-Content -Encoding UTF8 $Journal
  Write-Host "Heavy ML runtime skipped on NORMAL collector."
  exit 0
}

# Mark the environment unavailable before touching a potentially incomplete venv.
[ordered]@{status="installing";mode=$Mode;hash=$Hash;started_at=(Get-Date).ToUniversalTime().ToString("o")} |
  ConvertTo-Json | Set-Content -Encoding UTF8 $Journal
try {
  $Recreate=!(Test-Path -LiteralPath $MLPython)
  if(!$Recreate){
    & $MLPython -c "import sys; assert sys.prefix != sys.base_prefix" 2>$null
    if($LASTEXITCODE -ne 0){$Recreate=$true}
  }
  if($Recreate){
    if(!(Test-Path -LiteralPath $BasePython)){throw "Missing base Python for isolated ML environment"}
    if(Test-Path -LiteralPath $MLVenv){Remove-Item -LiteralPath $MLVenv -Recurse -Force}
    & $BasePython -m venv $MLVenv
    if($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $MLPython)){throw "Failed to recreate isolated ML environment"}
  }
} catch {
  [ordered]@{status="failed";mode=$Mode;error=$_.Exception.Message;failed_at=(Get-Date).ToUniversalTime().ToString("o")} |
    ConvertTo-Json | Set-Content -Encoding UTF8 $Journal
  throw
}
$Python=$MLPython
$CoreReq=Join-Path $ReleaseDir "requirements.txt"
if(!(Test-Path $CoreReq)){throw "Missing core requirements for ML environment"}
$CoreHash=(Get-FileHash -Algorithm SHA256 $CoreReq).Hash.ToLowerInvariant()
$Hash=("{0}:{1}" -f $CoreHash,$Hash)
$Need=($Hash -ne $Old) -or $Recreate
if(!$Need){
  # A cached ML environment must also contain the worker protocol dependencies.
  & $Python -c "import aiohttp,asyncpg,psutil,pydantic,httpx,websockets,numpy,scipy,sklearn,joblib,xgboost,lightgbm" 2>$null
  if($LASTEXITCODE -ne 0){$Need=$true}
}
if(!$Need){
  # Import success alone does not prove native ML wheels can train a model.
  # Revalidate the DLL/native execution path even for fingerprint cache hits.
  & $Python -c "import numpy as np,xgboost as xgb,lightgbm as lgb; X=np.array([[0.],[1.],[2.],[3.]]); y=np.array([0.,0.,1.,1.]); xgb.XGBRegressor(n_estimators=1,max_depth=1,n_jobs=1).fit(X,y); lgb.LGBMRegressor(n_estimators=1,n_jobs=1,verbosity=-1).fit(X,y)" 2>$null
  if($LASTEXITCODE -ne 0){$Need=$true}
}
if(!$Need){
  # A previous interrupted repair may leave a valid fingerprint but no journal.
  # Restore the durable ready record without reinstalling healthy packages.
  [ordered]@{status="ready";mode=$Mode;hash=$Hash;verified_at=(Get-Date).ToUniversalTime().ToString("o")} |
    ConvertTo-Json | Set-Content -Encoding UTF8 $Journal
  Write-Host "ML runtime already healthy and matches fingerprint."
  exit 0
}

[ordered]@{status="installing";mode=$Mode;hash=$Hash;started_at=(Get-Date).ToUniversalTime().ToString("o")} |
  ConvertTo-Json | Set-Content -Encoding UTF8 $Journal
try {
  & $Python -m pip install --disable-pip-version-check --retries 8 --timeout 60 --prefer-binary --upgrade -r $CoreReq -r $Req
  if($LASTEXITCODE -ne 0){throw "ML dependency installation failed after retries"}
  & $Python -c "import numpy,scipy,sklearn,joblib,xgboost,lightgbm; print('ML runtime OK')"
  if($LASTEXITCODE -ne 0){throw "ML runtime import validation failed"}
  # Basic native-library smoke tests catch broken wheels/DLL dependencies now,
  # before an unattended training job receives a lease.
  & $Python -c "import numpy as np,xgboost as xgb,lightgbm as lgb; X=np.array([[0.],[1.],[2.],[3.]]); y=np.array([0.,0.,1.,1.]); xgb.XGBRegressor(n_estimators=1,max_depth=1,n_jobs=1).fit(X,y); lgb.LGBMRegressor(n_estimators=1,n_jobs=1,verbosity=-1).fit(X,y); print('ML native smoke OK')"
  if($LASTEXITCODE -ne 0){throw "ML native-library smoke test failed"}
  [System.IO.File]::WriteAllText($State,$Hash,[System.Text.Encoding]::ASCII)
  [ordered]@{status="ready";mode=$Mode;hash=$Hash;completed_at=(Get-Date).ToUniversalTime().ToString("o")} |
    ConvertTo-Json | Set-Content -Encoding UTF8 $Journal
} catch {
  [ordered]@{status="failed";mode=$Mode;hash=$Hash;error=$_.Exception.Message;failed_at=(Get-Date).ToUniversalTime().ToString("o")} |
    ConvertTo-Json | Set-Content -Encoding UTF8 $Journal
  throw
}
