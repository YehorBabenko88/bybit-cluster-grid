[CmdletBinding()]
param(
 [ValidateSet('Prepare','EphemeralCI')][string]$Mode='Prepare',
 [Parameter(Mandatory=$true)][string]$PackageRoot,
 [Parameter(Mandatory=$true)][string]$InstallRoot,
 [Parameter(Mandatory=$true)][string]$SecurityModule,
 [Parameter(Mandatory=$true)][string]$SecurityModuleSha256,
 [Parameter(Mandatory=$true)][string]$PublisherSha256,
 [ValidateSet('control','worker','presentation')][string]$Role='worker',
 [string]$Python='python',
 [switch]$AuthorizeEphemeralWindowsCI
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
function Assert-Mission3LocalPath([string]$Path) {
 if ($Path -notmatch '^[A-Za-z]:\\' -or $Path.Substring(2).Contains(':') -or $Path.Contains('/') -or $Path.Contains('..')) { throw 'Absolute local drive namespace required' }
 $cursor=[IO.Path]::GetFullPath($Path)
 while ($cursor) {
  if (Test-Path -LiteralPath $cursor) {
   $item=Get-Item -LiteralPath $cursor -Force
   if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {throw 'Reparse namespace forbidden'}
  }
  $parent=[IO.Path]::GetDirectoryName($cursor.TrimEnd('\'))
  if ($parent -eq $cursor) {break};$cursor=$parent
 }
}
foreach($path in @($PackageRoot,$InstallRoot,$SecurityModule)){Assert-Mission3LocalPath $path}
# No office targets or remote endpoints are accepted by this entry point.
if ($env:COMPUTERNAME -match '^(?i:LS5|PC4|ADMINIT)$') { throw 'Physical office execution prohibited' }
if ($SecurityModuleSha256 -cnotmatch '^[0-9a-f]{64}$' -or $PublisherSha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'External tooling/publisher pins required' }
if ((Get-FileHash -LiteralPath $SecurityModule -Algorithm SHA256).Hash.ToLowerInvariant() -cne $SecurityModuleSha256) { throw 'Trusted security helper mismatch' }
Import-Module $SecurityModule -Force
$manifest=Join-Path $PackageRoot 'release.json'
$signature=Join-Path $PackageRoot 'release.p7s'
Test-UnifiedPackageSignature -Bytes ([IO.File]::ReadAllBytes($manifest)) -SignatureBytes ([IO.File]::ReadAllBytes($signature)) -PublisherSha256 $PublisherSha256
$code=@'
import sys,pathlib,hashlib
from unified_system.release_manifest import parse_manifest
root=pathlib.Path(sys.argv[1]);m=parse_manifest((root/'release.json').read_bytes(),expected_publisher=sys.argv[2])
for x in m['modules'].values():
 a=x['artifact'];p=root/a['path']
 if p.is_symlink() or p.stat().st_size!=a['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=a['sha256']:raise ValueError('module artifact mismatch')
'@
& $Python -c $code $PackageRoot $PublisherSha256
if ($LASTEXITCODE -ne 0) { throw 'Six-module closure rejected' }
if ($Mode -eq 'Prepare') { Write-Output 'PREPARE_ONLY; services=NOT_INSTALLED; enrollment=NOT_PERFORMED; physical=NOT_AUTHORIZED';return }
if (!$AuthorizeEphemeralWindowsCI -or [Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or $env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or $env:RUNNER_OS -cne 'Windows' -or !$env:RUNNER_TEMP) { throw 'Explicit ephemeral hosted Windows CI required' }
$root=[IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')+'\'
$temp=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')+'\'
if (!$root.StartsWith($temp,[StringComparison]::OrdinalIgnoreCase)) { throw 'Installer target must be disposable runner namespace' }
# Enrollment and activation require existing Grid server-issued credentials and
# fenced update permit. This installer cannot synthesize either authority.
Write-Output 'VERIFIED_EPHEMERAL_PACKAGE; activation=REQUIRES_GRID_ENROLLMENT_AND_FENCED_PERMIT; services=NOT_INSTALLED'
