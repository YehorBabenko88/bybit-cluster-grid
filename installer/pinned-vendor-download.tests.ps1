param([Parameter(Mandatory=$true)][string]$PackageFile)
$ErrorActionPreference='Stop'
$module=Import-Module (Join-Path $PSScriptRoot 'PinnedVendorDownload.psm1') -Force -PassThru
$artifact=[pscustomobject]@{component='nssm';url='https://www.nssm.cc/ci/nssm-2.24-101-g897c7ad.zip';filename='nssm-2.24-101-g897c7ad.zip';sha256='99f5045fffbffb745d67fe3a065a953c4a3d9c253b868892d9b685b0ee7d07b8';max_bytes=16777216;expected_bytes=$null}
$root=Join-Path ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($PackageFile))) ('transport-tests-'+[Guid]::NewGuid().ToString('N'));$null=New-Item -ItemType Directory -Path $root
$outer='6c6b1e287fb2ac6b04cfd32be2b9ed54a283cf0847fab2326e1b3961b512d340'
Expand-PinnedNssmPackage -PackageFile $PackageFile -Destination (Join-Path $root 'actual.zip') -MirrorOuterSha256 $outer
if((Get-FileHash (Join-Path $root 'actual.zip') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $artifact.sha256){throw 'INNER_PIN'}
foreach($status in @(200,301,400,401,403,404,0)) {
  if(Test-NssmMirrorEligibility $artifact $status $outer){throw 'INVALID_STATUS_FALLBACK'}
}
foreach($status in @(408,429,500,502,503,504)) {
  if(!(Test-NssmMirrorEligibility $artifact $status $outer)){throw 'AVAILABILITY_REJECTED'}
}
if(Test-NssmMirrorEligibility $artifact 503 ('0'*64)){throw 'WRONG_CALLER_PIN'}
$accepted=$false
try {Expand-PinnedNssmPackage -PackageFile $PackageFile -Destination (Join-Path $root 'bad-outer') -MirrorOuterSha256 ('0'*64);$accepted=$true} catch {}
if($accepted){throw 'OUTER_PIN_WEAKENED'}
# Test-only network seam: failures originate in the production downloader;
# neither HTTP bodies nor exception strings may qualify for fallback.
& $module {
  function script:Receive-BoundedHttps {throw [InvalidOperationException]::new('private HTTP 503 secret=DO_NOT_PRINT')}
}
$accepted=$false
try {$null=Save-PinnedVendorArtifact -Artifact $artifact -Destination (Join-Path $root 'bad-primary') -MirrorOuterSha256 $outer;$accepted=$true} catch {
 if($_.Exception.Message -cne 'VENDOR_PRIMARY_REJECTED'){throw 'PRIVATE_EXCEPTION_LEAK'}
}
if($accepted){throw 'NON_HTTP_FAILURE_FALLBACK'}
# Exercise the production orchestration with an offline HTTP-availability seam.
& $module {
 param($fixture)
 $script:FixturePackage=$fixture;$script:Calls=0
 function script:Receive-BoundedHttps {
   param($Url,$Destination,$MaxBytes,$Sha256,$ExpectedBytes,[switch]$ExactUrl)
   $script:Calls++
   if($Url -ceq $script:PrimaryUrl) {
     $e=[InvalidOperationException]::new('private primary outage')
     $e.Data['VendorHttpStatus']=503;throw $e
   }
   if($Url -cne $script:MirrorUrl -or !$ExactUrl -or $ExpectedBytes -ne 417537 -or $MaxBytes -ne 417537 -or $Sha256 -cne $script:OuterSha){throw 'MIRROR_ARGUMENTS'}
   [IO.File]::Copy($script:FixturePackage,$Destination,$false)
 }
} $PackageFile
$receipt=Save-PinnedVendorArtifact -Artifact $artifact -Destination (Join-Path $root 'fallback.zip') -MirrorOuterSha256 $outer
if($receipt.transport -cne 'HTTPS_MIRROR_PACKAGE_BYTE_IDENTICAL' -or $receipt.primary_status -ne 503 -or $receipt.origin -cne $artifact.url -or $receipt.sha256 -cne $artifact.sha256 -or $receipt.native_execution -cne 'NOT_RUN'){throw 'PUBLIC_RECEIPT'}
if((& $module {$script:Calls}) -ne 2){throw 'REQUEST_BUDGET'}
& $module {
 $script:Calls=0
 function script:Receive-BoundedHttps {$script:Calls++;throw [InvalidOperationException]::new('VENDOR_EXACT_BYTES_MISMATCH')}
}
$accepted=$false
try {$null=Save-PinnedVendorArtifact -Artifact $artifact -Destination (Join-Path $root 'bad-primary-bytes') -MirrorOuterSha256 $outer;$accepted=$true} catch {}
if($accepted -or (& $module {$script:Calls}) -ne 1){throw 'INVALID_PRIMARY_BYTES_HIDDEN'}
# Equal-length outer corruption must fail before writing any inner artifact.
$corrupt=Join-Path $root 'corrupt.nupkg';[IO.File]::Copy($PackageFile,$corrupt,$false)
$stream=[IO.File]::OpenWrite($corrupt);$stream.WriteByte(0);$stream.Dispose()
$accepted=$false
try {Expand-PinnedNssmPackage -PackageFile $corrupt -Destination (Join-Path $root 'corrupt-inner.zip') -MirrorOuterSha256 $outer;$accepted=$true} catch {}
if($accepted -or (Test-Path -LiteralPath (Join-Path $root 'corrupt-inner.zip'))){throw 'CORRUPTION_ACCEPTED'}
Write-Output 'PASS real official package/inner pin; status-only orchestration and public receipt; private/nonHTTP and invalid-primary rejection; corrupt outer denied; no scripts/native execution'


