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
$release=$null
foreach($name in @("current.version","previous.version")){
    $marker=Join-Path $InstallRoot $name
    if(!(Test-Path $marker)){continue}
    $v=(Get-Content $marker -Raw).Trim()
    if(!$v){continue}
    $candidate=Join-Path (Join-Path $InstallRoot "releases") $v
    if(Test-Path (Join-Path $candidate "grid\archive_service.py")){$release=$candidate;break}
}
if(!$release){
    $currentMarker=Join-Path $InstallRoot "current.version"
    if(Test-Path $currentMarker){
        $cv=(Get-Content $currentMarker -Raw).Trim()
        if($cv){
            $replaced=Join-Path (Join-Path $InstallRoot "releases") ($cv+".replaced")
            if(Test-Path (Join-Path $replaced "grid\archive_service.py")){$release=$replaced}
        }
    }
}
if(!$release){$release=Join-Path $InstallRoot "bootstrap"}
if(!(Test-Path (Join-Path $release "grid\archive_service.py"))){throw "No ArchivePipeline module found"}
$WaitDb=Join-Path $release "installer\\wait-grid-postgres.ps1"
if(Test-Path $WaitDb){ & $WaitDb -DataRoot $DataRoot -TimeoutSeconds 120 }
Set-Location $release
$watch=Join-Path $env:ProgramData "BybitClusterGrid\installer\release-health.ps1"
$version=Split-Path $release -Leaf
$started=[DateTime]::UtcNow
& $Python -m grid.archive_service
$code=$LASTEXITCODE
$runtime=[int]([DateTime]::UtcNow-$started).TotalSeconds
if(Test-Path $watch){
  & $watch -InstallRoot $InstallRoot -Phase AfterExit -Version $version -RuntimeSeconds $runtime -ExitCode $code
  if($LASTEXITCODE -eq 75){exit 75}
}
exit $code
