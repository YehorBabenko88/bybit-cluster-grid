# S0 dispatcher. Plan is pure: no subprocess, directory creation or configuration access.
[CmdletBinding()]
param(
    [ValidateSet('Plan', 'Preflight', 'Prepare', 'Execute', 'Status', 'Stop', 'Evidence')]
    [string]$Action = 'Plan',
    [string]$Root,
    [string]$PackageRoot,
    [string]$PackageZip,
    [string]$Config,
    [string]$ExpectedHead,
    [string]$ExpectedPackageSha,
    [ValidateSet('LocalAppData','UserProfileV1')][string]$ParentScope = 'LocalAppData',
    [switch]$Approved,
    [switch]$DiagnosticStages
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$missing = @()
foreach ($item in @(@('Root', $Root), @('PackageRoot', $PackageRoot), @('PackageZip', $PackageZip), @('Config', $Config))) {
    if ([string]::IsNullOrWhiteSpace($item[1]) -or -not [System.IO.Path]::IsPathRooted($item[1])) { $missing += $item[0] }
}
if ($ExpectedHead -cnotmatch '^[0-9a-f]{40}$') { $missing += 'ExpectedHead' }
if ($ExpectedPackageSha -cnotmatch '^[0-9a-f]{64}$') { $missing += 'ExpectedPackageSha' }
if ($Action -eq 'Plan') {
    [ordered]@{schema=1; profile='PHYSICAL_SMOKE_S0'; action='plan'; status='BLOCKED'; missing=$missing; command=$null; authority=@{s0_execute=$false;g1_execute=$false;cleanup=$false}} | ConvertTo-Json -Depth 5
    return
}
if ($missing.Count -ne 0) { throw ('S0_REQUIRED_PINS_OR_PATHS: ' + ($missing -join ', ')) }
if ($Action -in @('Prepare', 'Execute', 'Stop', 'Evidence') -and -not $Approved) { throw 'S0_EXPLICIT_APPROVAL_REQUIRED' }
if ($DiagnosticStages -and ($Action -ne 'Prepare' -or [Environment]::GetEnvironmentVariable('GITHUB_ACTIONS','Process') -cne 'true' -or [Environment]::GetEnvironmentVariable('RUNNER_ENVIRONMENT','Process') -cne 'github-hosted' -or [Environment]::GetEnvironmentVariable('GITHUB_JOB','Process') -cne 's0-windows' -or [Environment]::GetEnvironmentVariable('GITHUB_REPOSITORY','Process') -cne 'YehorBabenko88/bybit-cluster-grid' -or [Environment]::GetEnvironmentVariable('EXACT_HEAD_SHA','Process') -cne $ExpectedHead -or [Environment]::MachineName -in @('LS5','PC4'))) { throw 'S0_HOSTED_DIAGNOSTIC_ONLY' }
function Write-S0RuntimeStage([string]$Stage) { if ($DiagnosticStages) { [Console]::Out.WriteLine('S0_RUNTIME_'+$Stage); [Console]::Out.Flush() } }
Write-S0RuntimeStage 'ENTRY'
# The approved, externally staged package must already be in protected custody.
# Python verifies the complete ZIP and extracted closure before action dispatch.
$localData = $null
if ($ParentScope -eq 'LocalAppData') {
    $localData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
    if ([string]::IsNullOrWhiteSpace($localData)) { throw 'S0_PRIVATE_PROFILE_UNKNOWN' }
}
$packageFull = [IO.Path]::GetFullPath($PackageRoot).TrimEnd('\')
if ($ParentScope -eq 'LocalAppData' -and ([IO.Path]::GetDirectoryName($packageFull) -ine $localData -or [IO.Path]::GetFileName($packageFull) -cnotmatch '^GridS0Package-[0-9a-f-]{36}$')) { throw 'S0_PRIVATE_PACKAGE_NAMESPACE_REQUIRED' }
$python = Join-Path $PackageRoot 'runtime/python.exe'
$entrypoint = Join-Path $PackageRoot 'runtime/App/s0.py'
Write-S0RuntimeStage 'PACKAGE_PATHS'
foreach ($path in @($PackageRoot, $PackageZip, $python, $entrypoint)) {
    $item = Get-Item -LiteralPath $path -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'S0_REPARSE_PATH_FORBIDDEN' }
}
Write-S0RuntimeStage 'ZIP_PIN'
if ((Get-FileHash -LiteralPath $PackageZip -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedPackageSha) { throw 'S0_PACKAGE_PIN_MISMATCH' }
$arguments = @('-I', '-S', '-B', $entrypoint, '--action', $Action.ToLowerInvariant(), '--root', $Root, '--package-root', $PackageRoot, '--package-zip', $PackageZip, '--config', $Config, '--expected-head', $ExpectedHead, '--expected-package-sha', $ExpectedPackageSha, '--parent-scope', $ParentScope)
if ($Approved) { $arguments += '--approved' }
function ConvertTo-S0WindowsArgument([string]$Value) {
    # Windows CRT argv quoting, including embedded quotes and trailing slashes.
    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append('"')
    $slashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') { $slashes++; continue }
        if ($character -eq '"') {
            [void]$builder.Append(('\' * (2 * $slashes + 1)))
            [void]$builder.Append('"')
        } else {
            [void]$builder.Append(('\' * $slashes))
            [void]$builder.Append($character)
        }
        $slashes = 0
    }
    [void]$builder.Append(('\' * (2 * $slashes)))
    [void]$builder.Append('"')
    return $builder.ToString()
}
Write-S0RuntimeStage 'ENVIRONMENT'
$start = New-Object System.Diagnostics.ProcessStartInfo
$start.FileName = $python
$start.Arguments = (($arguments | ForEach-Object { ConvertTo-S0WindowsArgument $_ }) -join ' ')
$start.UseShellExecute = $false
$start.CreateNoWindow = $false
$start.WorkingDirectory = $PackageRoot
$start.EnvironmentVariables.Clear()
foreach ($name in @('SystemRoot', 'WINDIR', 'USERPROFILE', 'LOCALAPPDATA', 'USERNAME', 'COMPUTERNAME')) {
    if ($name -eq 'LOCALAPPDATA' -and $ParentScope -eq 'UserProfileV1') { continue }
    $value = [Environment]::GetEnvironmentVariable($name, 'Process')
    if ([string]::IsNullOrWhiteSpace($value)) { throw 'S0_REQUIRED_OS_ENVIRONMENT_MISSING' }
    $start.EnvironmentVariables[$name] = $value
}
# No fallback to shared OS temp: preparation creates this fresh private child.
# Before Prepare it can be absent; a library needing temp must fail closed.
$privateTemp = Join-Path $Root 'temp'
$start.EnvironmentVariables['TEMP'] = $privateTemp
$start.EnvironmentVariables['TMP'] = $privateTemp
$actualSystem = [Environment]::SystemDirectory
$actualWindows = [IO.Directory]::GetParent($actualSystem).FullName
$start.EnvironmentVariables['SystemRoot'] = $actualWindows
$start.EnvironmentVariables['WINDIR'] = $actualWindows
$start.EnvironmentVariables['LOCALAPPDATA'] = if ($ParentScope -eq 'UserProfileV1') { $privateTemp } else { $localData }
# V1 libraries get only an owned cache root; native Known Folder resolution ignores this hint.
$start.EnvironmentVariables['PATH'] = $actualSystem
# Bootstrap trust is established externally before this script is started.
# Load only original-ZIP-pinned helper bytes; no local compile or path DLL load.
function Get-S0BytesSha([byte[]]$Bytes) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
if ([System.IO.Path]::GetFullPath($PackageZip) -cne [System.IO.Path]::GetFullPath((Join-Path $PackageRoot 'source.zip'))) { throw 'S0_SOURCE_ZIP_LOCATION_REQUIRED' }
Write-S0RuntimeStage 'DEPENDENCY'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
Write-S0RuntimeStage 'CAPTURE'
$source = [IO.File]::Open($PackageZip,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
try {
    if ($source.Length -le 0 -or $source.Length -gt 536870912) { throw 'S0_ZIP_SIZE' }
    $captured = New-Object byte[] ([int]$source.Length)
    $offset = 0
    while ($offset -lt $captured.Length) {
        $read = $source.Read($captured,$offset,$captured.Length-$offset)
        if ($read -le 0) { throw 'S0_ZIP_SHORT_READ' }
        $offset += $read
    }
    Write-S0RuntimeStage 'HASH_CAPTURED'
    if ($source.ReadByte() -ne -1 -or (Get-S0BytesSha $captured) -cne $ExpectedPackageSha) { throw 'S0_PACKAGE_PIN_MISMATCH' }
} finally { $source.Dispose() }
function Read-S0OriginalEntry($Archive,[string]$Name) {
    $entries = @($Archive.Entries | Where-Object { $_.FullName -ceq $Name })
    if ($entries.Count -ne 1 -or $entries[0].Length -le 0 -or $entries[0].Length -gt 4194304) { throw 'S0_ORIGINAL_ENTRY_BLOCKED' }
    $content = $entries[0].Open(); $copy = New-Object IO.MemoryStream
    try {
        $buffer = New-Object byte[] 65536; $total = 0
        while (($read = $content.Read($buffer,0,$buffer.Length)) -gt 0) {
            $total += $read
            if ($total -gt $entries[0].Length -or $total -gt 4194304) { throw 'S0_ORIGINAL_ENTRY_SIZE' }
            $copy.Write($buffer,0,$read)
        }
        if ($total -ne $entries[0].Length) { throw 'S0_ORIGINAL_ENTRY_SIZE' }
        return ,$copy.ToArray()
    } finally { $content.Dispose(); $copy.Dispose() }
}
Write-S0RuntimeStage 'ARCHIVE'
$memory = New-Object IO.MemoryStream(,$captured)
$zip = New-Object IO.Compression.ZipArchive($memory,[IO.Compression.ZipArchiveMode]::Read,$true)
try {
    $manifestBytes = Read-S0OriginalEntry $zip 's0-package.json'
    $helperBytes = Read-S0OriginalEntry $zip 'native/S0Launcher.dll'
} finally { $zip.Dispose(); $memory.Dispose() }
$extractedManifest = [System.IO.File]::ReadAllBytes((Join-Path $PackageRoot 's0-package.json'))
if ((Get-S0BytesSha $manifestBytes) -cne (Get-S0BytesSha $extractedManifest)) { throw 'S0_EXTRACTED_MANIFEST_MISMATCH' }
$manifest = [System.Text.Encoding]::UTF8.GetString($manifestBytes) | ConvertFrom-Json
if (($manifest.schema -isnot [int] -and $manifest.schema -isnot [long]) -or $manifest.schema -ne 1 -or $manifest.profile -cne 'PHYSICAL_SMOKE_S0' -or $manifest.head -cne $ExpectedHead) { throw 'S0_ORIGINAL_MANIFEST_CONTEXT_BLOCKED' }
$helperPin = $manifest.files.'native/S0Launcher.dll'
$exePin = $manifest.files.'runtime/python.exe'
if ($helperPin.sha256 -cnotmatch '^[0-9a-f]{64}$' -or $exePin.sha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'S0_NATIVE_PINS_REQUIRED' }
$helperPath = Join-Path $PackageRoot 'native/S0Launcher.dll'
$helperItem = Get-Item -LiteralPath $helperPath -Force
if (($helperItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or $helperItem.Length -gt 67108864) { throw 'S0_NATIVE_FILE_BLOCKED' }
if ($helperBytes.Length -ne $helperPin.size -or (Get-S0BytesSha $helperBytes) -cne $helperPin.sha256) { throw 'S0_NATIVE_PIN_MISMATCH' }
if ('GridS0.ProcessHost' -as [type]) { throw 'S0_NATIVE_ALREADY_LOADED' }
Write-S0RuntimeStage 'HELPER'
[void][System.Reflection.Assembly]::Load($helperBytes)
$operatorSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$seconds = if ($Action -eq 'Execute') { 300 } else { 60 }
$closedEnvironment = @{}
foreach ($key in $start.EnvironmentVariables.Keys) { $closedEnvironment[$key] = $start.EnvironmentVariables[$key] }
Write-S0RuntimeStage 'NATIVE_RUN'
if ($ParentScope -eq 'UserProfileV1' -and $DiagnosticStages) { $result = [GridS0.ProcessHost]::RunDiagnosticAtUserProfileV1($PackageRoot, $start.Arguments, $closedEnvironment, $operatorSid, $exePin.sha256, $ExpectedHead, $seconds, $ExpectedPackageSha) }
elseif ($ParentScope -eq 'UserProfileV1') { $result = [GridS0.ProcessHost]::RunAtUserProfileV1($PackageRoot, $start.Arguments, $closedEnvironment, $operatorSid, $exePin.sha256, $ExpectedHead, $seconds, $ExpectedPackageSha) }
else { $result = [GridS0.ProcessHost]::Run($PackageRoot, $start.Arguments, $closedEnvironment, $operatorSid, $exePin.sha256, $ExpectedHead, $seconds) }
[ordered]@{schema=1; scope=$result.Scope; pid=$result.Pid; creation_filetime=$result.CreationFileTime; exit_code=$result.ExitCode; timed_out=$result.TimedOut; budget_seconds=$seconds; observed_user_sid=$result.ObservedUserSid; observed_elevated=$result.ObservedElevated; observed_integrity=$result.ObservedIntegrity; observed_admin_enabled=$result.ObservedAdminEnabled; job_member=$result.JobMember; job_flags=$result.JobFlags; active_limit=$result.ActiveLimit; g1_execute=$false; cleanup=$false} | ConvertTo-Json
if ($result.TimedOut) { throw 'S0_NATIVE_TIMEOUT_OWN_JOB_CLOSED' }
if ($result.ExitCode -ne 0) { throw 'S0_COMMAND_FAILED' }
