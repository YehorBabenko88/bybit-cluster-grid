#Requires -Version 5.1
# CI-only algorithm fixture; never a production bootstrap/ACL authorization path.
param([Parameter(Mandatory=$true)][string]$RuntimeRoot)
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
 $env:RUNNER_OS -cne 'Windows' -or $env:GITHUB_REPOSITORY -cne 'YehorBabenko88/bybit-cluster-grid' -or
 $env:GITHUB_JOB -cne 'build-windows-bundle' -or $env:GITHUB_RUN_ID -cnotmatch '^[1-9][0-9]*$'){
 throw 'OWNED_ML_CI_FIXTURE_ONLY'
}
$temp=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')
$root=[IO.Path]::GetFullPath($RuntimeRoot)
if((Split-Path $root -Parent) -cne $temp -or (Split-Path $root -Leaf) -cnotmatch '^grid-ml-ci-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'){
 throw 'ML_FIXTURE_SCOPE_BLOCKED'
}
if((Get-Item -LiteralPath $temp -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'ML_TEMP_REPARSE'}
$item=Get-Item -LiteralPath $root -Force -ErrorAction Stop
if(!$item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'ML_ROOT_REPARSE'}
$marker=Get-Content -LiteralPath (Join-Path $root 'ci-owner.json') -Raw -ErrorAction Stop | ConvertFrom-Json
$head=(& git rev-parse HEAD).Trim()
if($LASTEXITCODE -ne 0 -or $marker.run_id -cne $env:GITHUB_RUN_ID -or $marker.attempt -cne $env:GITHUB_RUN_ATTEMPT -or $marker.head -cne $head){throw 'ML_FIXTURE_OWNER_MISMATCH'}
foreach($i in Get-ChildItem -LiteralPath $root -Recurse -Force -ErrorAction Stop){
 if($i.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'ML_CHILD_REPARSE'}
}
$release=Join-Path $temp 'BybitClusterGrid'
$python=(Get-Command python -ErrorAction Stop).Source
# Run the existing dependency/lock/recovery algorithm only in this newly owned
# disposable fixture. Keep production entry-point refusal intact. This CI code
# assumes no hostile concurrent runner administrator; it is not custody proof.
$source=Get-Content -LiteralPath (Join-Path (Split-Path $PSScriptRoot -Parent) 'bootstrap-ml.ps1') -Raw
$start=$source.IndexOf('$Req=Join-Path $ReleaseDir')
if($start -lt 0 -or $source.LastIndexOf('$Req=Join-Path $ReleaseDir') -ne $start){throw 'ML_ALGORITHM_MARKER_INVALID'}
$body=$source.Substring($start).Replace('exit 0','return')
$block=[scriptblock]::Create('param($Python,$BasePython,$ReleaseDir,$RuntimeRoot,$Mode)'+"`n"+$body)
& $block $python $python $release $root 'PILOT'
$global:LASTEXITCODE=0
