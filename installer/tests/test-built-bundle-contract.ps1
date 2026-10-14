#Requires -Version 5.1
$ErrorActionPreference='Stop'
$gate=Join-Path $PSScriptRoot 'test-built-bundle.ps1'
$root=Join-Path ([IO.Path]::GetTempPath()) ('grid-bundle-contract-'+[guid]::NewGuid().ToString('N'))
$required=@('runtime/python.exe','installer/tests/test-legacy-rollback.ps1','installer/tests/legacy_rollback_driver.py','installer/tests/test-release-runtime-guard.ps1','tests/fixtures/legacy_rollback_migrations.txt')
foreach($name in $required){$p=Join-Path $root $name;[void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($p));[IO.File]::WriteAllText($p,$name)}
function Manifests {
 $files=@();$release=@{}
 foreach($name in $required){$p=Join-Path $root $name;$hash=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant();$files+=@{path=$name;sha256=$hash};$release[$name]=$hash}
 @{schema=1;files=$files}|ConvertTo-Json -Depth 5|Set-Content (Join-Path $root 'bundle-manifest.json') -Encoding UTF8
 @{version=('a'*40);files=$release}|ConvertTo-Json -Depth 5|Set-Content (Join-Path $root 'release-manifest.json') -Encoding UTF8
}
Manifests
& $gate -BundleRoot $root -VerifyOnly
$count=1
foreach($name in $required){
 $p=Join-Path $root $name;$saved=[IO.File]::ReadAllBytes($p);Remove-Item -LiteralPath $p
 $blocked=$false;try{& $gate -BundleRoot $root -VerifyOnly}catch{$blocked=$true}
 if(!$blocked){throw "Missing bundled dependency accepted: $name"}
 [IO.File]::WriteAllBytes($p,$saved);$count++
}
foreach($manifest in @('bundle-manifest.json','release-manifest.json')){
 Manifests
 $p=Join-Path $root $manifest;$s=Get-Content -LiteralPath $p -Raw
 $fixture='tests/fixtures/legacy_rollback_migrations.txt'
 $hash=(Get-FileHash -LiteralPath (Join-Path $root $fixture) -Algorithm SHA256).Hash.ToLowerInvariant()
 [IO.File]::WriteAllText($p,$s.Replace($hash,('0'*64)))
 $blocked=$false;try{& $gate -BundleRoot $root -VerifyOnly}catch{$blocked=$true}
 if(!$blocked){throw "Wrong hash accepted: $manifest"};$count++
}
foreach($manifest in @('bundle-manifest.json','release-manifest.json')){
 Manifests
 $p=Join-Path $root $manifest;$m=Get-Content -LiteralPath $p -Raw|ConvertFrom-Json
 if($manifest -eq 'bundle-manifest.json'){$m.files=@($m.files|Where-Object {$_.path -cne 'tests/fixtures/legacy_rollback_migrations.txt'})}
 else {$m.files.PSObject.Properties.Remove('tests/fixtures/legacy_rollback_migrations.txt')}
 $m|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $p -Encoding UTF8
 $blocked=$false;try{& $gate -BundleRoot $root -VerifyOnly}catch{$blocked=$true}
 if(!$blocked){throw "Missing fixture hash accepted: $manifest"};$count++
}
Write-Output "Built bundle contract passed: $count cases; no executable/provider invoked"
