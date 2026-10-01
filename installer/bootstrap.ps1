#Requires -RunAsAdministrator
param(
  [string]$CoordinatorUrl="",
  [string]$EnrollmentToken="",
  [string]$LegacyHandoff="",
  [string]$ExistingPostgresDsn="",
  [string]$TelegramBotToken="",
  [string]$TelegramAllowedChatIds="",
  [string]$BundlePath="",
  [ValidateSet("CONTROL","PILOT","NORMAL")][string]$AgentMode="NORMAL"
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

$Bundle=$(if($BundlePath){$BundlePath}else{Join-Path $PSScriptRoot "bybit-cluster-grid.zip"})
if(!(Test-Path $Bundle)){throw "Missing deployment bundle: $Bundle"}
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
        # Copy the runtime contents into OwnedRoot, not the runtime directory itself.
        # Copy-Item <directory> <existing-directory> would create an unwanted
        # ...\\python\\runtime\\python.exe nesting.
        Copy-Item (Join-Path (Split-Path $Bundled -Parent) "*") $OwnedRoot -Recurse -Force
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
$Requirements=Join-Path $Release "requirements.txt"
$ReqHash=(Get-FileHash -Algorithm SHA256 $Requirements).Hash.ToLowerInvariant()
$ReqState=Join-Path $RuntimeRoot "requirements.sha256"
$InstalledHash=if(Test-Path $ReqState){(Get-Content $ReqState -Raw).Trim()}else{""}
$NeedDeps=$RebuildVenv -or ($ReqHash -ne $InstalledHash)
if(!$NeedDeps){
    & $Python -c "import aiohttp,asyncpg,psutil,websockets,pydantic,fastapi,httpx" 2>$null
    if($LASTEXITCODE -ne 0){$NeedDeps=$true}
}
if($NeedDeps){
    & $Python -m pip install --upgrade pip
    if($LASTEXITCODE -ne 0){throw "Failed to update Grid pip"}
    & $Python -m pip install --upgrade -r $Requirements
    if($LASTEXITCODE -ne 0){throw "Failed to install Grid dependencies"}
    Set-Content -Encoding ascii -NoNewline $ReqState $ReqHash
} else {
    Write-Host "Grid dependencies already match requirements fingerprint."
}

$EnvFile=Join-Path $DataRoot ".env"
$DesiredRole=$(if($AgentMode -eq "CONTROL"){"coordinator"}else{"worker"})
if(!(Test-Path $EnvFile)){
    @(
      ("ROLE="+$DesiredRole),
      "GRID_DATA_PATH=$DataRoot",
      "STRATEGY_CACHE_DIR=$DataRoot\\runtime_strategies",
      ("COORDINATOR_URL="+$(if($CoordinatorUrl){$CoordinatorUrl}else{"http://127.0.0.1:8765"}))
    ) | Set-Content -Encoding UTF8 $EnvFile
}else{
    # Repair/upgrade may change node role. Replace only Grid-owned role/URL keys,
    # preserving secrets and PostgreSQL DSN already provisioned on CONTROL.
    $lines=@(Get-Content $EnvFile | Where-Object {$_ -notmatch '^(ROLE|COORDINATOR_URL)='})
    $lines += "ROLE=$DesiredRole"
    $lines += ("COORDINATOR_URL="+$(if($CoordinatorUrl){$CoordinatorUrl}else{"http://127.0.0.1:8765"}))
    $lines | Set-Content -Encoding UTF8 $EnvFile
}

# Optional CONTROL Telegram secrets are supplied locally by the operator.
# Never overwrite an existing secret with an empty value during repair.
if($AgentMode -eq "CONTROL"){
    if($TelegramBotToken){
        $lines=@(Get-Content $EnvFile | Where-Object {$_ -notmatch '^TELEGRAM_BOT_TOKEN='})
        $lines += "TELEGRAM_BOT_TOKEN=$TelegramBotToken"
        $lines | Set-Content -Encoding UTF8 $EnvFile
    }
    if($TelegramAllowedChatIds){
        $lines=@(Get-Content $EnvFile | Where-Object {$_ -notmatch '^TELEGRAM_ALLOWED_CHAT_IDS='})
        $lines += "TELEGRAM_ALLOWED_CHAT_IDS=$TelegramAllowedChatIds"
        $lines | Set-Content -Encoding UTF8 $EnvFile
    }
}

# PostgreSQL is CONTROL-owned logically, but an externally installed instance remains external.
# ExistingPostgresDsn opts into that instance without creating an ownership manifest.
if($AgentMode -eq "CONTROL"){
    if($ExistingPostgresDsn){
        $probe=$ExistingPostgresDsn
        $lines=@(Get-Content $EnvFile | Where-Object {$_ -notmatch '^POSTGRES_DSN='})
        $lines += "POSTGRES_DSN=$probe"
        $lines | Set-Content -Encoding UTF8 $EnvFile
        Write-Host "Using operator-provisioned PostgreSQL; Grid will not claim ownership of the service."
    } else {
        & (Join-Path $PSScriptRoot "provision_postgres.ps1") -DiscoveryPath (Join-Path $DataRoot "discovery.json") -DataRoot $DataRoot
    }
}else{
    Write-Host "Agent mode: PostgreSQL provisioning skipped; data ingress is CONTROL-owned."
}

# Legacy research handoff is staged only. Market/research payload import is forbidden
# before the global runtime gate is explicitly activated with START.
if($LegacyHandoff){
    if(!(Test-Path $LegacyHandoff)){throw "Legacy handoff not found: $LegacyHandoff"}
    $HandoffCopy=Join-Path $DataRoot "bootstrap-handoff.json"
    Copy-Item $LegacyHandoff $HandoffCopy -Force
    $hash=(Get-FileHash -Algorithm SHA256 $HandoffCopy).Hash.ToLowerInvariant()
    [ordered]@{
      schema=1
      status="STAGED"
      sha256=$hash
      staged_at=(Get-Date).ToUniversalTime().ToString("o")
      import_allowed=$false
      reason="Await explicit global START"
    } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $DataRoot "bootstrap-handoff.staged.json")
    Write-Host "Legacy handoff staged only; no market payload imported before START."
}

$CredentialFile=Join-Path $DataRoot "secrets\node.credential"
if($AgentMode -ne "CONTROL"){
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
} else {
    Write-Host "CONTROL node uses local coordinator identity; agent enrollment skipped."
}

try {
    & (Join-Path $PSScriptRoot "preflight.ps1") -ReleaseDir $Release -Python $Python -Mode $AgentMode
    if($LASTEXITCODE -ne 0){throw "Grid preflight failed"}
    & (Join-Path $PSScriptRoot "install.ps1") -ReleaseDir $Release -Python $Python -Mode $AgentMode
    if($LASTEXITCODE -ne 0){throw "Grid service installation failed"}
    @{mode=$Mode;status="installed";completed_at=(Get-Date).ToUniversalTime().ToString("o")} |
        ConvertTo-Json | Set-Content -Encoding UTF8 $StateFile
    $Backup=Join-Path $InstallRoot "bootstrap.previous"
    if(Test-Path $Backup){Remove-Item -Recurse -Force $Backup}
} catch {
    $err=$_.Exception.Message
    @{mode=$Mode;status="failed";error=$err;failed_at=(Get-Date).ToUniversalTime().ToString("o")} |
        ConvertTo-Json | Set-Content -Encoding UTF8 $StateFile
    $Backup=Join-Path $InstallRoot "bootstrap.previous"
    if(Test-Path $Backup){
        if(Test-Path $Release){Remove-Item -Recurse -Force $Release}
        Move-Item $Backup $Release
        Write-Warning "Bootstrap rolled back to previous release."
    }
    throw
}
