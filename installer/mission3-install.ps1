[CmdletBinding()]
param(
 [ValidateSet('Prepare','EphemeralCI')][string]$Mode='Prepare',
 [Parameter(Mandatory=$true)][string]$PackageRoot,
 [Parameter(Mandatory=$true)][string]$InstallRoot,
 [Parameter(Mandatory=$true)][string]$SecurityModule,
 [Parameter(Mandatory=$true)][string]$SecurityModuleSha256,
 [Parameter(Mandatory=$true)][string]$PublisherSha256,
 [ValidateSet('control','worker','presentation')][string]$Role='worker',
 [Parameter(Mandatory=$true)][string]$Python,
 [Parameter(Mandatory=$true)][string]$PythonSha256,
 [Parameter(Mandatory=$true)][string]$UnifiedRoot,
 [Parameter(Mandatory=$true)][string]$UnifiedSourceHead,
 [Parameter(Mandatory=$true)][string]$UnifiedSourceTree,
 [Parameter(Mandatory=$true)][string]$PreflightSha256,
 [Parameter(Mandatory=$true)][string]$SourceGuardSha256,
 [Parameter(Mandatory=$true)][string]$GitExecutable,
 [Parameter(Mandatory=$true)][string]$GitSha256,
 [Parameter(Mandatory=$true)][string]$CacheRoot,
 [switch]$AuthorizeEphemeralWindowsCI
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
function Assert-Mission3LocalPath([string]$Path) {
 if ($Path -notmatch '^[A-Za-z]:\\' -or $Path.Substring(2).Contains(':') -or $Path.Contains('/') -or $Path.Contains('..')) { throw 'Absolute local drive namespace required' }
 $full=[IO.Path]::GetFullPath($Path)
 $driveRoot=[IO.Path]::GetPathRoot($full)
 $volume=[IO.DriveInfo]::new($driveRoot)
 if ($volume.DriveType -ne [IO.DriveType]::Fixed) {throw 'Fixed local drive required'}
 $drive=Get-PSDrive -Name ($driveRoot.Substring(0,1)) -ErrorAction Stop
 if ($drive.Provider.Name -cne 'FileSystem' -or $drive.Root.TrimEnd('\') -ine $driveRoot.TrimEnd('\')) {throw 'Drive provider namespace mismatch'}
 $ancestors=New-Object 'System.Collections.Generic.List[string]'
 $cursor=$full
 while ($cursor) {
  $ancestors.Add($cursor)
  $parent=[IO.Path]::GetDirectoryName($cursor.TrimEnd('\'))
  if ($parent -eq $cursor) {break};$cursor=$parent
 }
 for ($i=$ancestors.Count-1;$i -ge 0;$i--) {
  $current=$ancestors[$i]
  try {$item=Get-Item -LiteralPath $current -Force -ErrorAction Stop}
  catch [Management.Automation.ItemNotFoundException] {return}
  catch {throw 'Local namespace unavailable'}
  if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {throw 'Reparse namespace forbidden'}
  if ($current -ine $full -and !$item.PSIsContainer) {throw 'Non-directory ancestor forbidden'}
 }
}
$preflight=Join-Path $UnifiedRoot 'unified_system\package_preflight.py'
$sourceGuard=Join-Path $UnifiedRoot 'integration\source_guard.py'
foreach($path in @($PackageRoot,$InstallRoot,$SecurityModule,$Python,$UnifiedRoot,$preflight,$sourceGuard,$GitExecutable,$CacheRoot)){Assert-Mission3LocalPath $path}
# No office targets or remote endpoints are accepted by this entry point.
if ($env:COMPUTERNAME -match '^(?i:LS5|PC4|ADMINIT)$') { throw 'Physical office execution prohibited' }
if ($SecurityModuleSha256 -cnotmatch '^[0-9a-f]{64}$' -or $PublisherSha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'External tooling/publisher pins required' }
if ((Get-FileHash -LiteralPath $SecurityModule -Algorithm SHA256).Hash.ToLowerInvariant() -cne $SecurityModuleSha256) { throw 'Trusted security helper mismatch' }
# These are external owner pins, never learned from candidate release metadata.
foreach($pair in @(@($Python,$PythonSha256),@($preflight,$PreflightSha256),@($sourceGuard,$SourceGuardSha256),@($GitExecutable,$GitSha256))) {
 if ($pair[1] -cnotmatch '^[0-9a-f]{64}$' -or (Get-FileHash -LiteralPath $pair[0] -Algorithm SHA256).Hash.ToLowerInvariant() -cne $pair[1]) {throw 'External preflight runtime/source pin mismatch'}
}
if ($UnifiedSourceHead -cnotmatch '^[0-9a-f]{40}$' -or $UnifiedSourceTree -cnotmatch '^[0-9a-f]{40}$') {throw 'Exact external Unified source identity required'}
$security=Import-Module $SecurityModule -Force -PassThru
$manifest=Join-Path $PackageRoot 'release.json'
$signature=Join-Path $PackageRoot 'release.p7s'
foreach($path in @($manifest,$signature)){Assert-Mission3LocalPath $path}
# Reuse the trusted security helper's bounded reader. Keep the SAME byte array
# for CMS verification and the digest compared with the isolated preflight.
[byte[]]$manifestBytes=& $security {param($p) Read-BoundedBytes $p 1048576} $manifest
[byte[]]$signatureBytes=& $security {param($p) Read-BoundedBytes $p 262144} $signature
Test-UnifiedPackageSignature -Bytes $manifestBytes -SignatureBytes $signatureBytes -PublisherSha256 $PublisherSha256
$sha=[Security.Cryptography.SHA256]::Create()
try {$verifiedManifestSha=([BitConverter]::ToString($sha.ComputeHash($manifestBytes))).Replace('-','').ToLowerInvariant()} finally {$sha.Dispose()}
# Raw script path: no -c, -m, PATH interpreter, package initializer or ambient
# bytecode may execute before the pinned helper establishes its source fence.
$output=@(& $Python -I -S -B $preflight --source-root $UnifiedRoot --source-head $UnifiedSourceHead --source-tree $UnifiedSourceTree --source-guard-sha256 $SourceGuardSha256 --git-executable $GitExecutable --git-sha256 $GitSha256 --package-root $PackageRoot --publisher-sha256 $PublisherSha256 --cache-root $CacheRoot)
if ($LASTEXITCODE -ne 0 -or $output.Count -ne 1 -or ([string]$output[0]).Length -gt 16384) {throw 'Isolated six-module preflight rejected'}
$result=([string]$output[0]) | ConvertFrom-Json
$keys=@('schema','mode','signature','modules','manifest_sha256','release_id','source_head','source_tree','services','physical','execution_authority','trading_authorized','physical_deployment_allowed')
if (@(Compare-Object (@($result.PSObject.Properties.Name) | Sort-Object) ($keys | Sort-Object) -CaseSensitive).Count -ne 0) {throw 'Preflight result schema mismatch'}
if ($result.schema -cne 'unified.package-preflight.v1' -or $result.mode -cne 'PREPARE_ONLY' -or $result.signature -cne 'EXTERNAL_CMS_REQUIRED' -or $result.services -cne 'NOT_INSTALLED' -or $result.physical -cne 'NOT_AUTHORIZED') {throw 'Preflight outcome mismatch'}
if (($result.modules -isnot [int] -and $result.modules -isnot [long]) -or $result.modules -ne 6 -or $result.manifest_sha256 -cne $verifiedManifestSha -or $result.source_head -cne $UnifiedSourceHead -or $result.source_tree -cne $UnifiedSourceTree) {throw 'Preflight verified-byte/source/roster binding mismatch'}
foreach($flag in @('execution_authority','trading_authorized','physical_deployment_allowed')) {
 if ($result.$flag -isnot [bool] -or $result.$flag) {throw 'Preflight cannot grant execution authority'}
}
if ($Mode -eq 'Prepare') { Write-Output 'PREPARE_ONLY; services=NOT_INSTALLED; enrollment=NOT_PERFORMED; physical=NOT_AUTHORIZED';return }
if (!$AuthorizeEphemeralWindowsCI -or [Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or $env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or $env:RUNNER_OS -cne 'Windows' -or !$env:RUNNER_TEMP) { throw 'Explicit ephemeral hosted Windows CI required' }
$root=[IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')+'\'
$temp=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')+'\'
if (!$root.StartsWith($temp,[StringComparison]::OrdinalIgnoreCase)) { throw 'Installer target must be disposable runner namespace' }
# Enrollment and activation require existing Grid server-issued credentials and
# fenced update permit. This installer cannot synthesize either authority.
Write-Output 'VERIFIED_EPHEMERAL_PACKAGE; activation=REQUIRES_GRID_ENROLLMENT_AND_FENCED_PERMIT; services=NOT_INSTALLED'
