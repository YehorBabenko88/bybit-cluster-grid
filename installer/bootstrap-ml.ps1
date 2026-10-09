param(
  [Parameter(Mandatory=$true)][string]$Python,
  [Parameter(Mandatory=$true)][string]$ReleaseDir,
  [Parameter(Mandatory=$true)][string]$RuntimeRoot,
  [ValidateSet("CONTROL","PILOT","NORMAL")][string]$Mode="NORMAL"
)
$ErrorActionPreference="Stop"
$Req=Join-Path $ReleaseDir "requirements-ml.txt"
if(!(Test-Path $Req)){throw "Missing ML requirements: $Req"}
if(!(Test-Path -LiteralPath $Python)){throw "Missing ML Python runtime: $Python"}
New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
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

$Need=($Hash -ne $Old)
if(!$Need){
  & $Python -c "import numpy,scipy,sklearn,joblib,xgboost,lightgbm" 2>$null
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
  & $Python -m pip install --disable-pip-version-check --retries 8 --timeout 60 --prefer-binary --upgrade -r $Req
  if($LASTEXITCODE -ne 0){throw "ML dependency installation failed after retries"}
  & $Python -c "import numpy,scipy,sklearn,joblib,xgboost,lightgbm; print('ML runtime OK')"
  if($LASTEXITCODE -ne 0){throw "ML runtime import validation failed"}
  # Basic native-library smoke tests catch broken wheels/DLL dependencies now,
  # before an unattended training job receives a lease.
  & $Python -c "import numpy as np,xgboost as xgb,lightgbm as lgb; X=np.array([[0.],[1.],[2.],[3.]]); y=np.array([0.,0.,1.,1.]); xgb.XGBRegressor(n_estimators=1,max_depth=1,n_jobs=1).fit(X,y); lgb.LGBMRegressor(n_estimators=1,n_jobs=1,verbosity=-1).fit(X,y); print('ML native smoke OK')"
  if($LASTEXITCODE -ne 0){throw "ML native-library smoke test failed"}
  Set-Content -Encoding ascii -NoNewline $State $Hash
  [ordered]@{status="ready";mode=$Mode;hash=$Hash;completed_at=(Get-Date).ToUniversalTime().ToString("o")} |
    ConvertTo-Json | Set-Content -Encoding UTF8 $Journal
} catch {
  [ordered]@{status="failed";mode=$Mode;hash=$Hash;error=$_.Exception.Message;failed_at=(Get-Date).ToUniversalTime().ToString("o")} |
    ConvertTo-Json | Set-Content -Encoding UTF8 $Journal
  throw
}
