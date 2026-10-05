param(
 [Parameter(Mandatory=$true)][string]$Python,
 [Parameter(Mandatory=$true)][string]$InstallRoot
)
$ErrorActionPreference="Stop"
$DataRoot="$env:ProgramData\\BybitClusterGrid"
$EnvFile=Join-Path $env:ProgramData "BybitClusterGrid\.env"
if(Test-Path $EnvFile){
    foreach($line in Get-Content $EnvFile){
        $x=$line.Trim()
        if(!$x -or $x.StartsWith("#")){continue}
        $i=$x.IndexOf("=")
        if($i -le 0){continue}
        $key=$x.Substring(0,$i).Trim()
        $value=$x.Substring($i+1)
        [Environment]::SetEnvironmentVariable($key,$value,"Process")
    }
}
$marker=Join-Path $InstallRoot "current.version"
$release=$null
if(Test-Path $marker){
    $v=(Get-Content $marker -Raw).Trim()
    if($v){$release=Join-Path (Join-Path $InstallRoot "releases") $v}
}
if(!$release -or !(Test-Path (Join-Path $release "grid\archive_service.py"))){
    $release=Join-Path $InstallRoot "bootstrap"
}
if(!(Test-Path (Join-Path $release "grid\archive_service.py"))){throw "No ArchivePipeline module found"}
$WaitDb=Join-Path $release "installer\\wait-grid-postgres.ps1"
if(Test-Path $WaitDb){ & $WaitDb -DataRoot $DataRoot -TimeoutSeconds 120 }
Set-Location $release
& $Python -m grid.archive_service
exit $LASTEXITCODE
