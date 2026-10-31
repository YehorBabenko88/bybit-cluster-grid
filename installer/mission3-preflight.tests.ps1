[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$UnifiedRoot,[Parameter(Mandatory=$true)][string]$Python,[Parameter(Mandatory=$true)][string]$GitExecutable)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or !$env:RUNNER_TEMP) {throw 'Actual disposable Windows runner required'}
if ($env:COMPUTERNAME -match '^(?i:LS5|PC4|ADMINIT)$') {throw 'Physical office execution prohibited'}
$UnifiedRoot=[IO.Path]::GetFullPath($UnifiedRoot)
$fixtureRoot=Join-Path $env:RUNNER_TEMP ('mission3-preflight-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixtureRoot | Out-Null
$rsa=[Security.Cryptography.RSA]::Create(2048);$cert=$null
$oldPath=$env:PYTHONPATH;$oldCache=$env:PYTHONPYCACHEPREFIX
function Hash([string]$File) {return (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant()}
function Reject([scriptblock]$Action) {
 $failed=$false;try {& $Action | Out-Null} catch {$failed=$true}
 if (!$failed) {throw 'Expected strict preflight rejection'}
 if (Test-Path -LiteralPath (Join-Path $fixtureRoot 'UNTRUSTED_CODE_EXECUTED')) {throw 'Untrusted code executed before rejection'}
}
function Sign-Manifest([byte[]]$Bytes) {
 [IO.File]::WriteAllBytes((Join-Path $package 'release.json'),$Bytes)
 $cms=New-Object Security.Cryptography.Pkcs.SignedCms((New-Object Security.Cryptography.Pkcs.ContentInfo(,$Bytes)),$true)
 $signer=New-Object Security.Cryptography.Pkcs.CmsSigner($cert)
 $signer.DigestAlgorithm=New-Object Security.Cryptography.Oid('2.16.840.1.101.3.4.2.1')
 $cms.ComputeSignature($signer)
 [IO.File]::WriteAllBytes((Join-Path $package 'release.p7s'),$cms.Encode())
}
function Assert-Prepare {
 $output=@(& (Join-Path $PSScriptRoot 'mission3-install.ps1') @common)
 if (-not $?) {throw 'Prepare failed'}
 if ($output.Count -ne 1 -or $output[0] -cne 'PREPARE_ONLY; services=NOT_INSTALLED; enrollment=NOT_PERFORMED; physical=NOT_AUTHORIZED') {throw 'Inert Prepare result required'}
 if (Test-Path -LiteralPath $common.InstallRoot) {throw 'Prepare created an install target'}
 if (@(Get-ChildItem -LiteralPath $cacheRoot -Force).Count -ne 0) {throw 'Private preflight cache not cleaned'}
 if (Test-Path -LiteralPath (Join-Path $fixtureRoot 'UNTRUSTED_CODE_EXECUTED')) {throw 'Poisoned import or cache was executed'}
}
try {
 Add-Type -AssemblyName System.Security
 if ($PSVersionTable.PSEdition -eq 'Core') {Add-Type -AssemblyName System.Security.Cryptography.Pkcs}
 $request=New-Object Security.Cryptography.X509Certificates.CertificateRequest('CN=Synthetic Preflight CI Only',$rsa,[Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pkcs1)
 $cert=$request.CreateSelfSigned([DateTimeOffset]::UtcNow.AddDays(-1),[DateTimeOffset]::UtcNow.AddDays(1))
 $sha=[Security.Cryptography.SHA256]::Create()
 try {$publisher=([BitConverter]::ToString($sha.ComputeHash($cert.RawData))).Replace('-','').ToLowerInvariant()} finally {$sha.Dispose()}
 # These hashes are independent CI test-owner inputs, not production publisher
 # admission. Candidate package data never chooses the Python/Git/helper pins.
 $pythonPin=Hash $Python;$gitPin=Hash $GitExecutable
 & $Python -I -S -B (Join-Path $PSScriptRoot '..\tests\windows\mission3_preflight_fixture.py') --root $fixtureRoot --upstream $UnifiedRoot --git $GitExecutable --publisher $publisher
 if ($LASTEXITCODE -ne 0) {throw 'Disposable fixture generation failed'}
 $source=Join-Path $fixtureRoot 'trusted-source';$package=Join-Path $fixtureRoot 'package'
 $cacheRoot=Join-Path $fixtureRoot 'private-cache';New-Item -ItemType Directory -Path $cacheRoot | Out-Null
 $policy=Get-Content -LiteralPath (Join-Path $fixtureRoot 'policy.json') -Raw | ConvertFrom-Json
 $security=Join-Path $UnifiedRoot 'scripts\SecurityPackage.psm1'
 $common=@{PackageRoot=$package;InstallRoot=(Join-Path $fixtureRoot 'never-installed');SecurityModule=$security;SecurityModuleSha256=(Hash $security);PublisherSha256=$publisher;Python=$Python;PythonSha256=$pythonPin;UnifiedRoot=$source;UnifiedSourceHead=$policy.source_head;UnifiedSourceTree=$policy.source_tree;PreflightSha256=$policy.preflight_sha256;SourceGuardSha256=$policy.guard_sha256;GitExecutable=$GitExecutable;GitSha256=$gitPin;CacheRoot=$cacheRoot}
 [byte[]]$valid=[IO.File]::ReadAllBytes((Join-Path $fixtureRoot 'valid-manifest.json'))
 Sign-Manifest $valid
 Assert-Prepare
 # Both hostile ambient lookup routes must be ignored BEFORE project imports.
 $env:PYTHONPATH=Join-Path $fixtureRoot 'ambient';$env:PYTHONPYCACHEPREFIX=Join-Path $fixtureRoot 'poisoned-cache'
 Assert-Prepare
 $env:PYTHONPATH=$oldPath;$env:PYTHONPYCACHEPREFIX=$oldCache
 $changed=$common.Clone();$changed.Python='python'
 Reject {& (Join-Path $PSScriptRoot 'mission3-install.ps1') @changed}
 $changed=$common.Clone();$changed.Python=Join-Path $fixtureRoot 'fake-python.cmd'
 Reject {& (Join-Path $PSScriptRoot 'mission3-install.ps1') @changed}
 $entry=Join-Path $source 'unified_system\package_preflight.py'
 [byte[]]$entryOriginal=[IO.File]::ReadAllBytes($entry)
 [IO.File]::WriteAllBytes($entry,[IO.File]::ReadAllBytes((Join-Path $fixtureRoot 'fake-preflight.py')))
 Reject {& (Join-Path $PSScriptRoot 'mission3-install.ps1') @common}
 [IO.File]::WriteAllBytes($entry,$entryOriginal)
 $guard=Join-Path $source 'integration\source_guard.py'
 [byte[]]$guardOriginal=[IO.File]::ReadAllBytes($guard)
 [IO.File]::WriteAllBytes($guard,[IO.File]::ReadAllBytes((Join-Path $fixtureRoot 'fake-preflight.py')))
 Reject {& (Join-Path $PSScriptRoot 'mission3-install.ps1') @common}
 [IO.File]::WriteAllBytes($guard,$guardOriginal)
 $init=Join-Path $source 'unified_system\__init__.py'
 [byte[]]$initOriginal=[IO.File]::ReadAllBytes($init)
 [IO.File]::WriteAllBytes($init,[IO.File]::ReadAllBytes((Join-Path $fixtureRoot 'fake-preflight.py')))
 Reject {& (Join-Path $PSScriptRoot 'mission3-install.ps1') @common}
 [IO.File]::WriteAllBytes($init,$initOriginal)
 foreach($file in @('missing-module.json','wrong-schema.json','noncanonical.json')) {
  # Actual valid CMS over malformed canonical/schema/roster candidates: signature
  # success MUST NOT bypass the shared parse_manifest contract.
  Sign-Manifest ([IO.File]::ReadAllBytes((Join-Path $fixtureRoot $file)))
  Reject {& (Join-Path $PSScriptRoot 'mission3-install.ps1') @common}
 }
 Sign-Manifest $valid
 $artifact=Join-Path $package 'modules\meta_analyse.zip'
 [byte[]]$artifactOriginal=[IO.File]::ReadAllBytes($artifact)
 [IO.File]::WriteAllBytes($artifact,[byte[]]@(1,2,3))
 Reject {& (Join-Path $PSScriptRoot 'mission3-install.ps1') @common}
 [IO.File]::WriteAllBytes($artifact,$artifactOriginal)
 $changed=$common.Clone();$changed.PublisherSha256='0'*64
 Reject {& (Join-Path $PSScriptRoot 'mission3-install.ps1') @changed}
 Assert-Prepare
 Write-Output "PASS SYNTHETIC_SIGNED_ISOLATED_PREFLIGHT ($($PSVersionTable.PSVersion)); source_capsule_activation=NOT_RUN; services=NOT_INSTALLED; physical=NOT_AUTHORIZED"
} finally {
 $env:PYTHONPATH=$oldPath;$env:PYTHONPYCACHEPREFIX=$oldCache
 if ($null -ne $cert) {$cert.Dispose()};$rsa.Dispose()
 # Only this freshly created disposable fixture namespace is removed.
 if ([IO.Directory]::Exists($fixtureRoot)) {Remove-Item -LiteralPath $fixtureRoot -Recurse -Force}
}
