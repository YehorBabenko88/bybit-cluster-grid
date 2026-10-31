[CmdletBinding()]
param(
 [ValidateSet('Prepare','InstallEphemeralCI','UninstallEphemeralCI')][string]$Action='Prepare',
 [Parameter(Mandatory=$true)][string]$InstallRoot,
 [Parameter(Mandatory=$true)][string]$Python,
 [Parameter(Mandatory=$true)][string]$PythonSha256,
 [Parameter(Mandatory=$true)][string]$Nssm,
 [Parameter(Mandatory=$true)][string]$NssmSha256,
 [Parameter(Mandatory=$true)][string]$TrustedLauncher,
 [Parameter(Mandatory=$true)][string]$LauncherSha256,
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
foreach($path in @($InstallRoot,$Python,$Nssm,$TrustedLauncher)){Assert-Mission3LocalPath $path}
if ($env:COMPUTERNAME -match '^(?i:LS5|PC4|ADMINIT)$') {throw 'Physical office target prohibited'}
foreach ($pair in @(@($Python,$PythonSha256),@($Nssm,$NssmSha256),@($TrustedLauncher,$LauncherSha256))) {
 if ($pair[1] -cnotmatch '^[0-9a-f]{64}$' -or (Get-FileHash -LiteralPath $pair[0] -Algorithm SHA256).Hash.ToLowerInvariant() -cne $pair[1]) {throw 'External runtime/launcher pin mismatch'}
 if (((Get-Item -LiteralPath $pair[0]).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {throw 'Linked runtime forbidden'}
}
if ($Action -eq 'Prepare') { Write-Output 'SERVICE_PLAN_ONLY; account=LocalService; physical=NOT_AUTHORIZED';return }
if (!$AuthorizeEphemeralWindowsCI -or $env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or $env:RUNNER_OS -cne 'Windows' -or !$env:RUNNER_TEMP) {throw 'Explicit disposable Windows hosted CI required'}
$root=[IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')+'\';$temp=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')+'\'
if (!$root.StartsWith($temp,[StringComparison]::OrdinalIgnoreCase)) {throw 'Disposable service root required'}
$service='Mission3LabUnified' # Fixed isolated namespace; never Grid/office services.
function Invoke-Nssm([string[]]$Arguments) { & $Nssm @Arguments; if ($LASTEXITCODE -ne 0) {throw 'NSSM operation failed'} }
$ownership=Join-Path $InstallRoot 'service-ownership.json'
$expectedParameters='"'+$TrustedLauncher+'" --install-root "'+$InstallRoot.TrimEnd('\')+'"'
function Read-Nssm([string]$Setting) {
 $value=(& $Nssm get $service $Setting) -join "`n"
 if ($LASTEXITCODE -ne 0) {throw 'Owned service configuration unavailable'}
 return $value.Trim()
}
function Assert-OwnedService {
 if (!(Test-Path -LiteralPath $ownership)) {throw 'Owned installation receipt required'}
 $receipt=Get-Content -LiteralPath $ownership -Raw | ConvertFrom-Json
 if ($receipt.schema -cne 'mission3.lab-service.v1' -or $receipt.service -cne $service -or $receipt.root -cne $root -or $receipt.python_sha256 -cne $PythonSha256 -or $receipt.nssm_sha256 -cne $NssmSha256 -or $receipt.launcher_sha256 -cne $LauncherSha256) {throw 'Installation ownership mismatch'}
 $scm=Get-CimInstance -ClassName Win32_Service -Filter "Name='Mission3LabUnified'"
 if ($null -eq $scm -or $scm.PathName.Trim('"') -ine [IO.Path]::GetFullPath($Nssm) -or $scm.StartName -ine 'NT AUTHORITY\LocalService') {throw 'SCM identity mismatch'}
 if ((Read-Nssm 'Application') -ine [IO.Path]::GetFullPath($Python) -or (Read-Nssm 'AppDirectory').TrimEnd('\') -ine $root.TrimEnd('\') -or (Read-Nssm 'AppParameters') -cne $expectedParameters) {throw 'Live service does not belong to this root'}
}
if ($Action -eq 'UninstallEphemeralCI') {
 Assert-OwnedService
 # The agent persists administrative STOP before service removal. Preserve all
 # state/history/release/credential namespaces; never recursive-delete roots.
 if (!(Test-Path -LiteralPath (Join-Path $InstallRoot 'deployment-state.json'))) {throw 'Persisted administrative STOP required'}
 $state=Get-Content -LiteralPath (Join-Path $InstallRoot 'deployment-state.json') -Raw | ConvertFrom-Json
 if ($state.admin_stopped -isnot [bool] -or !$state.admin_stopped) {throw 'Administrative STOP not persisted'}
 Invoke-Nssm -Arguments @('stop',$service);Invoke-Nssm -Arguments @('remove',$service,'confirm')
 Write-Output 'REMOVED_LAB_SERVICE; history_and_recovery=PRESERVED';return
}
if (Get-Service -Name $service -ErrorAction SilentlyContinue) {throw 'Existing service namespace; explicit recovery required'}
if (Test-Path -LiteralPath $ownership) {throw 'Existing ownership receipt; explicit recovery required'}
$created=$false
# Launcher is a separately reviewed exact-hash local entrypoint, never an argv
# array, URL or shell command supplied by an untrusted release manifest.
try {
Invoke-Nssm -Arguments @('install',$service,$Python)
$created=$true
Invoke-Nssm -Arguments @('set',$service,'AppParameters',$expectedParameters)
Invoke-Nssm -Arguments @('set',$service,'ObjectName','NT AUTHORITY\LocalService')
Invoke-Nssm -Arguments @('set',$service,'Start','SERVICE_DEMAND_START')
Invoke-Nssm -Arguments @('set',$service,'AppDirectory',$InstallRoot)
Invoke-Nssm -Arguments @('set',$service,'AppExit','Default','Exit') # Admin stop cannot trigger restart.
Invoke-Nssm -Arguments @('set',$service,'AppStopMethodConsole','10000')
# Activation/start and bounded crash recovery remain Grid supervisor-owned.
# Deliberately install stopped until enrollment + fenced permit + health checks.
 $receipt=[ordered]@{schema='mission3.lab-service.v1';service=$service;root=$root;python_sha256=$PythonSha256;nssm_sha256=$NssmSha256;launcher_sha256=$LauncherSha256}
 $bytes=(New-Object Text.UTF8Encoding($false)).GetBytes(($receipt | ConvertTo-Json -Compress))
 $stream=[IO.File]::Open($ownership,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
 try {$stream.Write($bytes,0,$bytes.Length)} finally {$stream.Dispose()}
 Assert-OwnedService
} catch {
 if ($created) { & $Nssm remove $service confirm | Out-Null }
 throw
}
Write-Output 'INSTALLED_STOPPED_LAB_SERVICE; activation=GRID_AUTHORITY_REQUIRED; physical=NOT_AUTHORIZED'
