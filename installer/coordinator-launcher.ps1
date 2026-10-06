param(
 [Parameter(Mandatory=$true)][string]$Python,
 [Parameter(Mandatory=$true)][string]$InstallRoot
)
$ErrorActionPreference="Stop"
$DataRoot="$env:ProgramData\BybitClusterGrid"
$EnvFile=Join-Path $DataRoot ".env"
# Upgrade-safe migration: old CONTROL installations may predate the
# administrative shared token. Generate it locally before importing .env so
# the coordinator can fail closed without operator downtime.
if(Test-Path $EnvFile){
  $hasShared=Select-String -Path $EnvFile -Pattern '^GRID_SHARED_TOKEN=.+
  foreach($line in Get-Content $EnvFile){
    $x=$line.Trim(); if(!$x -or $x.StartsWith("#")){continue}
    $i=$x.IndexOf("="); if($i -le 0){continue}
    [Environment]::SetEnvironmentVariable($x.Substring(0,$i).Trim(),$x.Substring($i+1),"Process")
  }
}
$VersionFile=Join-Path $InstallRoot "current.version"
$Release=if(Test-Path $VersionFile){Join-Path (Join-Path $InstallRoot "releases") ((Get-Content $VersionFile -Raw).Trim())}else{Join-Path $InstallRoot "bootstrap"}
if(!(Test-Path $Release)){throw "Grid CONTROL release not found: $Release"}
$WaitDb=Join-Path $Release "installer\\wait-grid-postgres.ps1"
if(Test-Path $WaitDb){ & $WaitDb -DataRoot $DataRoot -TimeoutSeconds 120 }
Set-Location $Release
& $Python -m uvicorn grid.coordinator:app --host 0.0.0.0 --port 8765
exit $LASTEXITCODE
 -Quiet -ErrorAction SilentlyContinue
  if(!$hasShared){
    $bytes=New-Object byte[] 32
    $rng=[System.Security.Cryptography.RandomNumberGenerator]::Create()
    try{$rng.GetBytes($bytes)}finally{$rng.Dispose()}
    $token=($bytes | ForEach-Object {$_.ToString("x2")}) -join ""
    Add-Content -Encoding UTF8 $EnvFile ("GRID_SHARED_TOKEN="+$token)
    $token=$null; $bytes=$null
  }
}
if(Test-Path $EnvFile){
  foreach($line in Get-Content $EnvFile){
    $x=$line.Trim(); if(!$x -or $x.StartsWith("#")){continue}
    $i=$x.IndexOf("="); if($i -le 0){continue}
    [Environment]::SetEnvironmentVariable($x.Substring(0,$i).Trim(),$x.Substring($i+1),"Process")
  }
}
$VersionFile=Join-Path $InstallRoot "current.version"
$Release=if(Test-Path $VersionFile){Join-Path (Join-Path $InstallRoot "releases") ((Get-Content $VersionFile -Raw).Trim())}else{Join-Path $InstallRoot "bootstrap"}
if(!(Test-Path $Release)){throw "Grid CONTROL release not found: $Release"}
$WaitDb=Join-Path $Release "installer\\wait-grid-postgres.ps1"
if(Test-Path $WaitDb){ & $WaitDb -DataRoot $DataRoot -TimeoutSeconds 120 }
Set-Location $Release
& $Python -m uvicorn grid.coordinator:app --host 0.0.0.0 --port 8765
exit $LASTEXITCODE
