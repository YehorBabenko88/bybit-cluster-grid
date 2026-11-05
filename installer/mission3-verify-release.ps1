[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$Manifest,
 [Parameter(Mandatory=$true)][string]$Signature,
 [Parameter(Mandatory=$true)][string]$PublisherSha256,
 [Parameter(Mandatory=$true)][string]$SecurityModule,
 [Parameter(Mandatory=$true)][string]$SecurityModuleSha256
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if ($SecurityModuleSha256 -cnotmatch '^[0-9a-f]{64}$' -or (Get-FileHash -LiteralPath $SecurityModule -Algorithm SHA256).Hash.ToLowerInvariant() -cne $SecurityModuleSha256) { throw 'Trusted security module pin mismatch' }
if ((Get-Item -LiteralPath $Manifest).Length -gt 1048576 -or (Get-Item -LiteralPath $Signature).Length -gt 262144) { throw 'Signature bounds' }
Import-Module $SecurityModule -Force
Test-UnifiedPackageSignature -Bytes ([IO.File]::ReadAllBytes($Manifest)) -SignatureBytes ([IO.File]::ReadAllBytes($Signature)) -PublisherSha256 $PublisherSha256
Write-Output 'MISSION3_CMS_PIN_VERIFIED'
