$ErrorActionPreference="Stop"
param([Parameter(Mandatory=$true)][string]$ReleaseDir)
$Python=(Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (!$Python) { $Python=Join-Path $ReleaseDir "runtime\python.exe" }
if (!(Test-Path $Python)) { throw "Python runtime missing" }
& $Python -m compileall -q (Join-Path $ReleaseDir "grid")
if ($LASTEXITCODE -ne 0) { throw "Python compileall failed" }
& $Python -c "import aiohttp,asyncpg,psutil,websockets,pydantic,fastapi"
if ($LASTEXITCODE -ne 0) { throw "Dependency import check failed" }
Write-Host "Preflight OK"
