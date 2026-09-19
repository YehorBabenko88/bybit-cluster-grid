param(
 [Parameter(Mandatory=$true)][string]$Python,
 [Parameter(Mandatory=$true)][string]$InstallRoot
)
$ErrorActionPreference="Stop"
$DataRoot="$env:ProgramData\BybitClusterGrid"
$EnvFile=Join-Path $DataRoot ".env"
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
Set-Location $Release
& $Python -m uvicorn grid.coordinator:app --host 0.0.0.0 --port 8765
exit $LASTEXITCODE
