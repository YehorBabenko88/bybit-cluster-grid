param(
 [Parameter(Mandatory=$true)][string]$ReleaseDir,
 [string]$Python=""
)
$ErrorActionPreference="Stop"
if(!$Python){$Python=(Get-Command python.exe -ErrorAction SilentlyContinue).Source}
if(!$Python){$Python=Join-Path $env:ProgramData "BybitClusterGrid\runtime\venv\Scripts\python.exe"}
if(!(Test-Path $Python)){throw "Grid Python runtime missing"}
$ArchiveModule=Join-Path $ReleaseDir "grid\archive_service.py"
$ArchiveLauncher=Join-Path $ReleaseDir "installer\archive-launcher.ps1"
if(!(Test-Path $ArchiveModule)){throw "ArchivePipeline module missing from release"}
if(!(Test-Path $ArchiveLauncher)){throw "ArchivePipeline launcher missing from release"}
& $Python -m compileall -q (Join-Path $ReleaseDir "grid") (Join-Path $ReleaseDir "run_worker.py")
if($LASTEXITCODE -ne 0){throw "Python compileall failed"}
Push-Location $ReleaseDir
try {
    & $Python -c "import aiohttp,asyncpg,psutil,websockets,pydantic,fastapi; import grid.worker,grid.config,grid.archive_service,grid.archive_discovery,grid.archive_worker"
    if($LASTEXITCODE -ne 0){throw "Dependency/import smoke check failed"}
} finally { Pop-Location }
Write-Host "Preflight OK"
