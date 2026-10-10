#Requires -Version 5.1
<#
.SYNOPSIS
Recover an interrupted release pointer transaction while the service is stopped.
.DESCRIPTION
Plan-only by default. With -Apply, a prepared transaction restores the previous
version; a committed transaction retains the candidate and its rollback marker.
No service is started or stopped.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:ProgramFiles\BybitClusterGrid",
    [ValidateSet('WORKER','CONTROL')][string]$Role = 'WORKER',
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$mutex = [System.Threading.Mutex]::new($false, 'Global\BybitClusterGridReleaseSwitch')
$held = $false
try {
    try { $held = $mutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $held = $true }
    if (-not $held) { throw 'Another Grid release operation is running' }
    $journalPath = Join-Path $InstallRoot 'switch-journal.json'
    if (-not (Test-Path -LiteralPath $journalPath)) {
        Write-Output 'NO_JOURNAL=true'
        return
    }
    if (-not (Test-Path -LiteralPath $journalPath -PathType Leaf)) {
        throw 'Invalid release switch journal type; manual recovery required'
    }
    $j = Get-Content -LiteralPath $journalPath -Raw | ConvertFrom-Json
    if ($null -eq $j -or $j -isnot [pscustomobject] -or
        @($j.PSObject.Properties.Match('schema')).Count -ne 1 -or
        @($j.PSObject.Properties.Match('previous')).Count -ne 1 -or
        @($j.PSObject.Properties.Match('candidate')).Count -ne 1 -or
        @($j.PSObject.Properties.Match('phase')).Count -ne 1) {
        throw 'Invalid release switch journal structure; manual recovery required'
    }
    if ($j.schema -isnot [long] -and $j.schema -isnot [int] -or $j.previous -isnot [string] -or
        $j.candidate -isnot [string] -or $j.phase -isnot [string]) {
        throw 'Invalid release switch journal field types; manual recovery required'
    }
    if ($j.schema -ne 1 -or $j.previous -cnotmatch '^[0-9a-f]{40}$' -or
        $j.candidate -cnotmatch '^[0-9a-f]{40}$' -or
        $j.phase -cnotin @('prepared','committed') -or $j.previous -eq $j.candidate) {
        throw 'Invalid release switch journal; manual recovery required'
    }
    $required = if ($Role -eq 'CONTROL') { 'grid\coordinator.py' } else { 'run_worker.py' }
    $previousDir = Join-Path (Join-Path $InstallRoot 'releases') $j.previous
    if (-not (Test-Path -LiteralPath (Join-Path $previousDir $required) -PathType Leaf)) {
        throw 'Rollback target missing; manual recovery required'
    }
    $currentPath = Join-Path $InstallRoot 'current.version'
    if ((Test-Path -LiteralPath $currentPath) -and
        -not (Test-Path -LiteralPath $currentPath -PathType Leaf)) {
        throw 'Invalid current release pointer type; manual recovery required'
    }
    $current = if (Test-Path -LiteralPath $currentPath) { (Get-Content -LiteralPath $currentPath -Raw).Trim() } else { '' }
    if ((Test-Path -LiteralPath $currentPath) -and -not $current) {
        throw 'Empty current release pointer; manual recovery required'
    }
    if ($current -and ($current -cnotmatch '^[0-9a-f]{40}$')) {
        throw 'Invalid current release pointer; manual recovery required'
    }
    if ($current -and ($current -cne $j.previous) -and ($current -cne $j.candidate)) {
        throw 'Current pointer conflicts with journal; manual recovery required'
    }
    # previous.version is rewritten during recovery; refuse to overwrite a directory.
    $previousMarkerPath = Join-Path $InstallRoot 'previous.version'
    if ((Test-Path -LiteralPath $previousMarkerPath) -and
        -not (Test-Path -LiteralPath $previousMarkerPath -PathType Leaf)) {
        throw 'Invalid previous release pointer type; manual recovery required'
    }
    # Never erase a pending marker belonging to another transaction.
    $pendingPath = Join-Path $InstallRoot 'pending.version'
    if (Test-Path -LiteralPath $pendingPath) {
        if (-not (Test-Path -LiteralPath $pendingPath -PathType Leaf)) {
            throw 'Invalid pending release marker; manual recovery required'
        }
        $pendingValue = (Get-Content -LiteralPath $pendingPath -Raw).Trim()
        if ($pendingValue -cne $j.candidate -and $pendingValue -cne $j.previous) {
            throw 'Pending release pointer conflicts with journal; manual recovery required'
        }
    }
    # A prepared transaction may already have written the candidate pointer
    # before the power loss. A committed transaction must retain the candidate.
    # The journal is authoritative; no new promotion is attempted here.
    $target = if ($j.phase -eq 'prepared') { $j.previous } else { $j.candidate }
    if ($j.phase -eq 'committed') {
        $candidateDir = Join-Path (Join-Path $InstallRoot 'releases') $j.candidate
        if (-not (Test-Path -LiteralPath (Join-Path $candidateDir $required) -PathType Leaf)) {
            throw 'Committed candidate missing; manual recovery required'
        }
    }
    # Verify executable integrity when a release manifest is available.
    # Legacy installed releases without a manifest remain supported.
    $targetDir = Join-Path (Join-Path $InstallRoot 'releases') $target
    $targetManifestPath = Join-Path $targetDir 'release-manifest.json'
    if (Test-Path -LiteralPath $targetManifestPath) {
        if (-not (Test-Path -LiteralPath $targetManifestPath -PathType Leaf)) {
            throw 'Recovery target manifest is not a file; manual recovery required'
        }
        $targetManifest = Get-Content -LiteralPath $targetManifestPath -Raw | ConvertFrom-Json
        $requiredKey = $required.Replace([char]92, '/')
        if ($null -eq $targetManifest -or $targetManifest -isnot [pscustomobject] -or
            $targetManifest.version -cne $target -or
            $null -eq $targetManifest.files -or $targetManifest.files -isnot [pscustomobject]) {
            throw 'Invalid recovery target manifest; manual recovery required'
        }
        $entry = $targetManifest.files.PSObject.Properties[$requiredKey]
        if ($null -eq $entry -or $entry.Value -isnot [string] -or
            $entry.Value -cnotmatch '^[0-9a-fA-F]{64}$') {
            throw 'Recovery target entry point checksum missing; manual recovery required'
        }
        $targetFull = [IO.Path]::GetFullPath($targetDir).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
        foreach ($fileEntry in $targetManifest.files.PSObject.Properties) {
            $relative = [string]$fileEntry.Name
            if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)' -or
                $relative -match '^[a-zA-Z]:' -or $fileEntry.Value -isnot [string] -or
                $fileEntry.Value -cnotmatch '^[0-9a-fA-F]{64}$') {
                throw 'Invalid recovery manifest file entry; manual recovery required'
            }
            $filePath = [IO.Path]::GetFullPath((Join-Path $targetDir ($relative.Replace('/', [IO.Path]::DirectorySeparatorChar))))
            if (-not $filePath.StartsWith($targetFull, [StringComparison]::OrdinalIgnoreCase) -or
                -not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
                throw 'Recovery manifest file missing or outside release; manual recovery required'
            }
            $fileHash = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash
            if ($fileHash -cne $fileEntry.Value.ToUpperInvariant()) {
                throw 'Recovery manifest file checksum mismatch; manual recovery required'
            }
        }
    }
    if (Test-Path -LiteralPath $targetManifestPath -PathType Leaf) {
        $manifestKeys = @{}
        foreach ($fileEntry in $targetManifest.files.PSObject.Properties) {
            $manifestKeys[[string]$fileEntry.Name.Replace([char]92, '/')] = $true
        }
        Get-ChildItem -LiteralPath $targetDir -Recurse -File -Filter '*.py' | ForEach-Object {
            $relativePath = $_.FullName.Substring($targetFull.Length).Replace([char]92, '/')
            if (-not $manifestKeys.ContainsKey($relativePath)) {
                throw "Recovery manifest omits Python source: $relativePath; manual recovery required"
            }
        }
    }
    # In a committed switch, previous.version remains the rollback fallback.
    # Reject a known-corrupt rollback entry point when its manifest is available.
    if ($j.phase -eq 'committed') {
        $previousManifestPath = Join-Path $previousDir 'release-manifest.json'
        if (Test-Path -LiteralPath $previousManifestPath) {
            if (-not (Test-Path -LiteralPath $previousManifestPath -PathType Leaf)) {
                throw 'Rollback manifest is not a file; manual recovery required'
            }
            $previousManifest = Get-Content -LiteralPath $previousManifestPath -Raw | ConvertFrom-Json
            $previousKey = $required.Replace([char]92, '/')
            if ($null -eq $previousManifest -or $previousManifest -isnot [pscustomobject] -or
                $previousManifest.version -cne $j.previous -or
                $null -eq $previousManifest.files -or $previousManifest.files -isnot [pscustomobject]) {
                throw 'Invalid rollback manifest; manual recovery required'
            }
            $previousHash = $previousManifest.files.PSObject.Properties[$previousKey]
            if ($null -eq $previousHash -or $previousHash.Value -isnot [string] -or
                $previousHash.Value -cnotmatch '^[0-9a-fA-F]{64}$' -or
                (Get-FileHash -LiteralPath (Join-Path $previousDir $required) -Algorithm SHA256).Hash -cne
                    $previousHash.Value.ToUpperInvariant()) {
                throw 'Rollback entry point checksum mismatch; manual recovery required'
            }
            $previousFull = [IO.Path]::GetFullPath($previousDir).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
            foreach ($fileEntry in $previousManifest.files.PSObject.Properties) {
                $relative = [string]$fileEntry.Name
                if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)' -or
                    $relative -match '^[a-zA-Z]:' -or $fileEntry.Value -isnot [string] -or
                    $fileEntry.Value -cnotmatch '^[0-9a-fA-F]{64}$') {
                    throw 'Invalid rollback manifest file entry; manual recovery required'
                }
                $filePath = [IO.Path]::GetFullPath((Join-Path $previousDir ($relative.Replace('/', [IO.Path]::DirectorySeparatorChar))))
                if (-not $filePath.StartsWith($previousFull, [StringComparison]::OrdinalIgnoreCase) -or
                    -not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
                    throw 'Rollback manifest file missing or outside release; manual recovery required'
                }
                if ((Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash -cne $fileEntry.Value.ToUpperInvariant()) {
                    throw 'Rollback manifest file checksum mismatch; manual recovery required'
                }
            }
        }
    }
    Write-Output "RECOVERY_PHASE=$($j.phase)"
    Write-Output "RECOVERY_TARGET=$target"
    if (-not $Apply) { Write-Output 'PLAN_ONLY=true'; return }
    $processes = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
        Where-Object { $_.CommandLine -and (
            $_.CommandLine -match 'grid\.release_supervisor' -or
            $_.CommandLine -match 'BybitClusterGrid.*run_worker\.py' -or
            $_.CommandLine -match 'uvicorn grid\.coordinator:app'
        ) })
    if ($processes.Count -gt 0) { throw 'Grid process is active; refusing recovery' }
    function Write-Atomic([string]$Path,[string]$Value) {
        $tmp = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
        try {
            [IO.File]::WriteAllText($tmp,$Value,[Text.UTF8Encoding]::new($false))
            if ([IO.File]::Exists($Path)) {
                $backup = "$Path.$([guid]::NewGuid().ToString('N')).bak"
                try {
                    [IO.File]::Replace($tmp, $Path, $backup, $true)
                } finally {
                    if ([IO.File]::Exists($backup)) { [IO.File]::Delete($backup) }
                }
            } else {
                [IO.File]::Move($tmp, $Path)
            }
        } finally {
            if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force }
        }
    }
    Write-Atomic (Join-Path $InstallRoot 'previous.version') $j.previous
    if ($j.phase -eq 'prepared') {
        Write-Atomic $currentPath $j.previous
        $pendingPath = Join-Path $InstallRoot 'pending.version'
        if (Test-Path -LiteralPath $pendingPath) { Remove-Item -LiteralPath $pendingPath -Force }
    } else {
        Write-Atomic (Join-Path $InstallRoot 'pending.version') $j.candidate
        Write-Atomic $currentPath $j.candidate
    }
    Remove-Item -LiteralPath $journalPath -Force
    Write-Output "RECOVERED=$target"
} finally {
    if ($held) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
