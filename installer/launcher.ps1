param(
 [Parameter(Mandatory=$true)][string]$Python,
 [Parameter(Mandatory=$true)][string]$InstallRoot
)
$ErrorActionPreference="Stop"
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
    if(Test-Path (Join-Path $candidate "run_worker.py")){$release=$candidate;break}
}
if(!$release){
    $currentMarker=Join-Path $InstallRoot "current.version"
    if(Test-Path $currentMarker){
        $cv=(Get-Content $currentMarker -Raw).Trim()
        if($cv){
            $replaced=Join-Path (Join-Path $InstallRoot "releases") ($cv+".replaced")
            if(Test-Path (Join-Path $replaced "run_worker.py")){$release=$replaced}
        }
    }
}
if(!$release){$release=Join-Path $InstallRoot "bootstrap"}
$run=Join-Path $release "run_worker.py"
if(!(Test-Path $run)){throw "No runnable Grid release found"}
Set-Location $release
$version=Split-Path $release -Leaf
& $Python -m grid.release_supervisor --install-root $InstallRoot --version $version --cwd $release -- $Python $run
exit $LASTEXITCODE
