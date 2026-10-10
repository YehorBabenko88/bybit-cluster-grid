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
  $hasShared=Select-String -Path $EnvFile -Pattern '^GRID_SHARED_TOKEN=.+$' -Quiet -ErrorAction SilentlyContinue
  if(!$hasShared){
    $bytes=New-Object byte[] 32
    $rng=[System.Security.Cryptography.RandomNumberGenerator]::Create()
    try{$rng.GetBytes($bytes)}finally{$rng.Dispose()}
    $token=($bytes | ForEach-Object {$_.ToString("x2")}) -join ""
    Add-Content -Encoding UTF8 $EnvFile ("GRID_SHARED_TOKEN="+$token)
    $token=$null
    $bytes=$null
  }
}

if(Test-Path $EnvFile){
  foreach($line in Get-Content $EnvFile){
    $x=$line.Trim()
    if(!$x -or $x.StartsWith("#")){continue}
    $i=$x.IndexOf("=")
    if($i -le 0){continue}
    [Environment]::SetEnvironmentVariable($x.Substring(0,$i).Trim(),$x.Substring($i+1),"Process")
  }
}

# Resolve an interrupted promotion before selecting the service release.
$journalPath = Join-Path $InstallRoot 'switch-journal.json'
if (Test-Path -LiteralPath $journalPath -PathType Leaf) {
    $recovery = Join-Path $PSScriptRoot 'recover-release.ps1'
    if (-not (Test-Path -LiteralPath $recovery -PathType Leaf)) {
        throw 'Release switch journal exists but recovery script is missing'
    }
    & $recovery -InstallRoot $InstallRoot -Role CONTROL -Apply
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw 'Release journal recovery failed'
    }
    if (Test-Path -LiteralPath $journalPath -PathType Leaf) {
        throw 'Release journal remains unresolved; refusing service startup'
    }
}
$Release=$null
foreach($name in @("current.version","previous.version")){
  $marker=Join-Path $InstallRoot $name
  if(!(Test-Path $marker)){continue}
  $v=(Get-Content $marker -Raw).Trim()
  if($v -notmatch '^[0-9a-f]{40} (Join-Path $InstallRoot "releases") $v
  if(Test-Path (Join-Path $candidate "grid\coordinator.py")){$Release=$candidate;break}
}
if(!$Release){
    $currentMarker=Join-Path $InstallRoot "current.version"
    if(Test-Path $currentMarker){
        $cv=(Get-Content $currentMarker -Raw).Trim()
        if($cv -match '^[0-9a-f]{40}Join-Path (Join-Path $InstallRoot "releases") ($cv+".replaced")
            if(Test-Path (Join-Path $replaced "grid\coordinator.py")){$Release=$replaced}
        }
    }
}
if(!$Release){$Release=Join-Path $InstallRoot "bootstrap"}
if(!(Test-Path (Join-Path $Release "grid\coordinator.py"))){throw "No runnable Grid CONTROL release found"}
$WaitDb=Join-Path $Release "installer\wait-grid-postgres.ps1"
if(Test-Path $WaitDb){ & $WaitDb -DataRoot $DataRoot -TimeoutSeconds 120 }
Set-Location $Release
$version=Split-Path $Release -Leaf
& $Python -m grid.release_supervisor --install-root $InstallRoot --version $version --cwd $release --readiness coordinator -- $Python -m uvicorn grid.coordinator:app --host 0.0.0.0 --port 8765
exit $LASTEXITCODE
){continue}
  $candidate=Join-Path (Join-Path $InstallRoot "releases") $v
  if(Test-Path (Join-Path $candidate "grid\coordinator.py")){$Release=$candidate;break}
}
if(!$Release){
    $currentMarker=Join-Path $InstallRoot "current.version"
    if(Test-Path $currentMarker){
        $cv=(Get-Content $currentMarker -Raw).Trim()
        if($cv){
            $replaced=Join-Path (Join-Path $InstallRoot "releases") ($cv+".replaced")
            if(Test-Path (Join-Path $replaced "grid\coordinator.py")){$Release=$replaced}
        }
    }
}
if(!$Release){$Release=Join-Path $InstallRoot "bootstrap"}
if(!(Test-Path (Join-Path $Release "grid\coordinator.py"))){throw "No runnable Grid CONTROL release found"}
$WaitDb=Join-Path $Release "installer\wait-grid-postgres.ps1"
if(Test-Path $WaitDb){ & $WaitDb -DataRoot $DataRoot -TimeoutSeconds 120 }
Set-Location $Release
$version=Split-Path $Release -Leaf
& $Python -m grid.release_supervisor --install-root $InstallRoot --version $version --cwd $release --readiness coordinator -- $Python -m uvicorn grid.coordinator:app --host 0.0.0.0 --port 8765
exit $LASTEXITCODE
){
            $replaced=Join-Path (Join-Path $InstallRoot "releases") ($cv+".replaced")
            if(Test-Path (Join-Path $replaced "grid\coordinator.py")){$Release=$replaced}
        }
    }
}
if(!$Release){$Release=Join-Path $InstallRoot "bootstrap"}
if(!(Test-Path (Join-Path $Release "grid\coordinator.py"))){throw "No runnable Grid CONTROL release found"}
$WaitDb=Join-Path $Release "installer\wait-grid-postgres.ps1"
if(Test-Path $WaitDb){ & $WaitDb -DataRoot $DataRoot -TimeoutSeconds 120 }
Set-Location $Release
$version=Split-Path $Release -Leaf
& $Python -m grid.release_supervisor --install-root $InstallRoot --version $version --cwd $release --readiness coordinator -- $Python -m uvicorn grid.coordinator:app --host 0.0.0.0 --port 8765
exit $LASTEXITCODE
){continue}
  $candidate=Join-Path (Join-Path $InstallRoot "releases") $v
  if(Test-Path (Join-Path $candidate "grid\coordinator.py")){$Release=$candidate;break}
}
if(!$Release){
    $currentMarker=Join-Path $InstallRoot "current.version"
    if(Test-Path $currentMarker){
        $cv=(Get-Content $currentMarker -Raw).Trim()
        if($cv){
            $replaced=Join-Path (Join-Path $InstallRoot "releases") ($cv+".replaced")
            if(Test-Path (Join-Path $replaced "grid\coordinator.py")){$Release=$replaced}
        }
    }
}
if(!$Release){$Release=Join-Path $InstallRoot "bootstrap"}
if(!(Test-Path (Join-Path $Release "grid\coordinator.py"))){throw "No runnable Grid CONTROL release found"}
$WaitDb=Join-Path $Release "installer\wait-grid-postgres.ps1"
if(Test-Path $WaitDb){ & $WaitDb -DataRoot $DataRoot -TimeoutSeconds 120 }
Set-Location $Release
$version=Split-Path $Release -Leaf
& $Python -m grid.release_supervisor --install-root $InstallRoot --version $version --cwd $release --readiness coordinator -- $Python -m uvicorn grid.coordinator:app --host 0.0.0.0 --port 8765
exit $LASTEXITCODE
