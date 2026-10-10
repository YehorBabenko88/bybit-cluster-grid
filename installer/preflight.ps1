param(
 [Parameter(Mandatory=$true)][string]$ReleaseDir,
 [string]$Python="",
 [ValidateSet("CONTROL","PILOT","NORMAL")][string]$Mode="NORMAL"
)
$ErrorActionPreference="Stop"
if(!$Python){$Python=(Get-Command python.exe -ErrorAction SilentlyContinue).Source}
if(!$Python){$Python=Join-Path $env:ProgramData "BybitClusterGrid\runtime\venv\Scripts\python.exe"}
if(!(Test-Path $Python)){throw "Grid Python runtime missing"}
if($Mode -in @("CONTROL","PILOT")){
    $MLRequirements=Join-Path $ReleaseDir "requirements-ml.txt"
    if(!(Test-Path -LiteralPath $MLRequirements -PathType Leaf)){
        throw "ML requirements missing for $Mode release: $MLRequirements"
    }
}
$ArchiveModule=Join-Path $ReleaseDir "grid\archive_service.py"
$ArchiveLauncher=Join-Path $ReleaseDir "installer\archive-launcher.ps1"
if(!(Test-Path $ArchiveModule)){throw "ArchivePipeline module missing from release"}
if(!(Test-Path $ArchiveLauncher)){throw "ArchivePipeline launcher missing from release"}
$Entry=if($Mode -eq "CONTROL"){Join-Path $ReleaseDir "run_coordinator.py"}else{Join-Path $ReleaseDir "run_worker.py"}
if(!(Test-Path $Entry)){throw "Role entrypoint missing: $Entry"}
& $Python -m compileall -q (Join-Path $ReleaseDir "grid") $Entry
if($LASTEXITCODE -ne 0){throw "Python compileall failed"}
Push-Location $ReleaseDir
try {
    if($Mode -eq "CONTROL"){
        & $Python -c "import aiohttp,asyncpg,psutil,websockets,pydantic,fastapi; import grid.coordinator,grid.config"
    } else {
        & $Python -c "import aiohttp,psutil,websockets,pydantic; import grid.worker,grid.config"
    }
    if($LASTEXITCODE -ne 0){throw "Dependency/import smoke check failed"}
} finally { Pop-Location }
Write-Host "Preflight OK"
