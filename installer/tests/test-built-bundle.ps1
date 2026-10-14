#Requires -Version 5.1
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$BundleRoot,[switch]$VerifyOnly)
$ErrorActionPreference='Stop'
$BundleRoot=[IO.Path]::GetFullPath($BundleRoot)
$required=@('runtime/python.exe','installer/tests/test-legacy-rollback.ps1','installer/tests/legacy_rollback_driver.py','installer/tests/test-release-runtime-guard.ps1','tests/fixtures/legacy_rollback_migrations.txt')
foreach($name in $required){if(!(Test-Path -LiteralPath (Join-Path $BundleRoot $name) -PathType Leaf)){throw "Required bundled integration dependency missing: $name"}}
$bm=Get-Content -LiteralPath (Join-Path $BundleRoot 'bundle-manifest.json') -Raw|ConvertFrom-Json
$rm=Get-Content -LiteralPath (Join-Path $BundleRoot 'release-manifest.json') -Raw|ConvertFrom-Json
foreach($name in $required){
 $entry=@($bm.files|Where-Object {$_.path -ceq $name})
 $releaseEntry=$rm.files.PSObject.Properties[$name]
 $hash=(Get-FileHash -LiteralPath (Join-Path $BundleRoot $name) -Algorithm SHA256).Hash.ToLowerInvariant()
 if($entry.Count -ne 1 -or $entry[0].sha256 -cne $hash -or $null -eq $releaseEntry -or $releaseEntry.Value -cne $hash){throw "Bundled dependency manifest coverage/hash mismatch: $name"}
}
if($VerifyOnly){Write-Output 'Built bundle dependency hashes verified';return}
# Run the shipped scripts from the shipped directory. No checkout/system Python fallback.
Push-Location -LiteralPath $BundleRoot
try {
 $python=Join-Path $BundleRoot 'runtime/python.exe'
 & (Join-Path $BundleRoot 'installer/tests/test-legacy-rollback.ps1') -Python $python
 & (Join-Path $BundleRoot 'installer/tests/test-release-runtime-guard.ps1')
} finally {Pop-Location}
Write-Output 'Built bundle integrations passed: LegacyRollback36 and RuntimeGuard195'
