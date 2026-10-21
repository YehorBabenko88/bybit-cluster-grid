#Requires -Version 5.1
# Compile only on disposable hosted CI. No TokenFacts methods are invoked.
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or !$env:RUNNER_TEMP -or $env:EXACT_HEAD_SHA -cnotmatch '^[0-9a-f]{40}$'){throw 'HOSTED_CI_BUILD_ONLY'}
$out=Join-Path $env:RUNNER_TEMP ('pc4-package-'+[guid]::NewGuid().ToString('D'))
$null=New-Item -ItemType Directory -Path $out -ErrorAction Stop
foreach($name in @('Common.ps1','Actor.ps1','TokenFacts.cs','Invoke-Pc4SidAcl.ps1')){Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $out $name) -ErrorAction Stop}
Add-Type -Path (Join-Path $out 'TokenFacts.cs') -OutputAssembly (Join-Path $out 'TokenFacts.dll') -ErrorAction Stop
$files=[ordered]@{};foreach($name in @('Common.ps1','Actor.ps1','TokenFacts.cs','TokenFacts.dll','Invoke-Pc4SidAcl.ps1')){$files[$name]=(Get-FileHash -LiteralPath (Join-Path $out $name) -Algorithm SHA256).Hash.ToLowerInvariant()}
$utf8=New-Object Text.UTF8Encoding($false,$true)
[IO.File]::WriteAllText((Join-Path $out 'package.sha256.json'),(@{kind='PC4_OFFLINE_BUILT_PACKAGE';source_sha=$env:EXACT_HEAD_SHA;files=$files}|ConvertTo-Json -Depth 5 -Compress),$utf8)
$hash=(Get-FileHash -LiteralPath (Join-Path $out 'package.sha256.json') -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText((Join-Path $out 'PACKAGE_MANIFEST_SHA256.txt'),$hash+"`n",$utf8)
('PC4_PACKAGE_PATH='+$out)|Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
Write-Output ('Compiled only; package manifest SHA256 '+$hash+'; no native methods called')
