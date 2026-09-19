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
$marker=Join-Path $InstallRoot "current.version"
$release=$null
if(Test-Path $marker){
    $v=(Get-Content $marker -Raw).Trim()
    if($v){$release=Join-Path (Join-Path $InstallRoot "releases") $v}
}
if(!$release -or !(Test-Path (Join-Path $release "run_worker.py"))){
    $release=Join-Path $InstallRoot "bootstrap"
}
$run=Join-Path $release "run_worker.py"
if(!(Test-Path $run)){throw "No runnable Grid release found"}
Set-Location $release
& $Python $run
exit $LASTEXITCODE
