$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\installer\switch-release.ps1'
$root = Join-Path ([IO.Path]::GetTempPath()) ("grid-release-test-" + [guid]::NewGuid().ToString('N'))
$a = 'a' * 40
$b = 'b' * 40
function Assert([bool]$Condition,[string]$Message) {
    if (-not $Condition) { throw $Message }
}
try {
    foreach ($version in @($a,$b)) {
        $dir = Join-Path $root "releases\$version"
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        Set-Content -LiteralPath (Join-Path $dir 'run_worker.py') -Value '# test'
        $hash = (Get-FileHash -LiteralPath (Join-Path $dir 'run_worker.py') -Algorithm SHA256).Hash.ToLowerInvariant()
        [IO.File]::WriteAllText((Join-Path $dir 'release-manifest.json'), ('{"version":"' + $version + '","files":{"run_worker.py":"' + $hash + '"}}'))
    }
    Set-Content -LiteralPath (Join-Path $root 'current.version') -Value $a
    $output = & $script -Version $b -InstallRoot $root -Role WORKER
    Assert ($output -contains 'PLAN_ONLY=true; no files changed') 'Default mode must be plan-only'
    Assert (((Get-Content (Join-Path $root 'current.version') -Raw).Trim()) -eq $a) 'Plan changed current'
    Assert (-not (Test-Path (Join-Path $root 'pending.version'))) 'Plan created pending marker'
    # CONTROL manifests use forward slashes while its required path uses Windows separators.
    $previousControl = Join-Path $root "releases\$a\grid\coordinator.py"
    New-Item -ItemType Directory -Force -Path (Split-Path $previousControl -Parent) | Out-Null
    Set-Content -LiteralPath $previousControl -Value '# previous control rollback'
    $controlFile = Join-Path $root "releases\$b\grid\coordinator.py"
    New-Item -ItemType Directory -Force -Path (Split-Path $controlFile -Parent) | Out-Null
    Set-Content -LiteralPath $controlFile -Value '# control test'
    $controlHash = (Get-FileHash -LiteralPath $controlFile -Algorithm SHA256).Hash.ToLowerInvariant()
    $controlManifest = Join-Path $root "releases\$b\release-manifest.json"
    $workerManifest = Get-Content -LiteralPath $controlManifest -Raw
    [IO.File]::WriteAllText($controlManifest, ('{"version":"' + $b + '","files":{"grid/coordinator.py":"' + $controlHash + '"}}'))
    $controlPlan = & $script -Version $b -InstallRoot $root -Role CONTROL
    Assert ($controlPlan -contains 'PLAN_ONLY=true; no files changed') 'Valid CONTROL manifest must be accepted'
    Assert (-not (Test-Path (Join-Path $root 'pending.version'))) 'CONTROL plan created pending'
    [IO.File]::WriteAllText($controlManifest, $workerManifest)
    $invalid = $false
    try { & $script -Version ('c' * 40) -InstallRoot $root -Role WORKER | Out-Null }
    catch { $invalid = $true }
    Assert $invalid 'Missing release must fail'
    # PowerShell ValidatePattern is case-insensitive; enforce canonical SHA explicitly.
    $uppercaseRejected = $false
    try { & $script -Version ($b.ToUpperInvariant()) -InstallRoot $root -Role WORKER | Out-Null } catch { $uppercaseRejected = $true }
    Assert $uppercaseRejected 'Uppercase candidate SHA must be rejected'
    Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Uppercase candidate created journal'
    # The current pointer must be a lowercase hexadecimal SHA.
    foreach ($badCurrent in @( ('A' * 40), ('g' * 40), '../../bad' )) {
        Set-Content -LiteralPath (Join-Path $root 'current.version') -Value $badCurrent
        $rejectedCurrent = $false
        try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null } catch { $rejectedCurrent = $true }
        Assert $rejectedCurrent "Invalid current.version must fail closed: $badCurrent"
        Assert (-not (Test-Path (Join-Path $root 'pending.version'))) 'Invalid current created pending marker'
        Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Invalid current created journal'
    }
    Set-Content -LiteralPath (Join-Path $root 'current.version') -Value $a
    $manifestPath = Join-Path $root "releases\$b\release-manifest.json"
    $hash = (Get-FileHash -LiteralPath (Join-Path $root "releases\$b\run_worker.py") -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath $manifestPath -Value ('{"version":"' + $a + '","files":{"run_worker.py":"' + $hash + '"}}')
    $invalid = $false
    try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null }
    catch { $invalid = $true }
    Assert $invalid 'Mismatched manifest must fail'
    Assert (((Get-Content (Join-Path $root 'current.version') -Raw).Trim()) -eq $a) 'Failed plan changed current'
    Set-Content -LiteralPath $manifestPath -Value ('{"version":"' + $b + '","files":{"run_worker.py":"' + $hash + '"}}')
    # A manifest with a noncanonical version must not match by case folding.
    Set-Content -LiteralPath $manifestPath -Value ('{"version":"' + $b.ToUpperInvariant() + '","files":{"run_worker.py":"' + $hash + '"}}')
    $uppercaseManifestRejected = $false
    try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null } catch { $uppercaseManifestRejected = $true }
    Assert $uppercaseManifestRejected 'Uppercase manifest SHA must be rejected'
    Assert (-not (Test-Path (Join-Path $root 'pending.version'))) 'Uppercase manifest created pending'
    Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Uppercase manifest created journal'
    # Malformed manifest content must fail before any release pointer changes.
    foreach ($badManifest in @(
        '{',
        'null',
        '{}',
        ('{"version":"' + $b + '","files":{"../escape.py":"' + $hash + '"}}'),
        ('{"version":"' + $b + '","files":{"run_worker.py":"not-a-sha256"}}')
    )) {
        Set-Content -LiteralPath $manifestPath -Value $badManifest
        $badManifestRejected = $false
        try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null } catch { $badManifestRejected = $true }
        Assert $badManifestRejected 'Malformed release manifest must fail closed'
        Assert (((Get-Content (Join-Path $root 'current.version') -Raw).Trim()) -eq $a) 'Bad manifest changed current'
        Assert (-not (Test-Path (Join-Path $root 'pending.version'))) 'Bad manifest created pending'
        Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Bad manifest created journal'
    }
    Set-Content -LiteralPath $manifestPath -Value ('{"version":"' + $b + '","files":{"run_worker.py":"' + $hash + '"}}')
    # Reject a manifest that references a nonexistent file, even if the hash is valid.
    Set-Content -LiteralPath $manifestPath -Value ('{"version":"' + $b + '","files":{"missing.py":"' + $hash + '"}}')
    $missingManifestFileRejected = $false
    try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null } catch { $missingManifestFileRejected = $true }
    Assert $missingManifestFileRejected 'Missing manifest file must block promotion'
    Assert (-not (Test-Path (Join-Path $root 'pending.version'))) 'Missing manifest file created pending'
    Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Missing manifest file created journal'
    Set-Content -LiteralPath $manifestPath -Value ('{"version":"' + $b + '","files":{"run_worker.py":"' + $hash + '"}}')


    # A manifest listing only another valid file must not leave the entry point unchecked.
    $otherFile = Join-Path $root "releases\$b\other.py"
    Set-Content -LiteralPath $otherFile -Value '# other'
    $otherHash = (Get-FileHash -LiteralPath $otherFile -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath $manifestPath -Value ('{"version":"' + $b + '","files":{"other.py":"' + $otherHash + '"}}')
    $unverifiedEntrypointRejected = $false
    try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null } catch { $unverifiedEntrypointRejected = $true }
    Assert $unverifiedEntrypointRejected 'Manifest omitting worker entry point must fail closed'
    Assert (-not (Test-Path (Join-Path $root 'pending.version'))) 'Unverified entry point created pending'
    Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Unverified entry point created journal'
    Set-Content -LiteralPath $manifestPath -Value ('{"version":"' + $b + '","files":{"run_worker.py":"' + $hash + '"}}')

    # A manifest cannot point outside the release root via absolute paths.
    foreach ($unsafePath in @('C:\\Windows\\win.ini', '/tmp/outside.py', '..\\escape.py')) {
        Set-Content -LiteralPath $manifestPath -Value ('{"version":"' + $b + '","files":{"' + ($unsafePath.Replace('\\','\\\\')) + '":"' + $hash + '"}}')
        $unsafeRejected = $false
        try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null } catch { $unsafeRejected = $true }
        Assert $unsafeRejected "Unsafe manifest path must fail closed: $unsafePath"
        Assert (-not (Test-Path (Join-Path $root 'pending.version'))) 'Unsafe manifest created pending'
        Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Unsafe manifest created journal'
    }
    Set-Content -LiteralPath $manifestPath -Value ('{"version":"' + $b + '","files":{"run_worker.py":"' + $hash + '"}}')
    Set-Content -LiteralPath (Join-Path $root "releases\$b\run_worker.py") -Value '# tampered'
    $blocked = $false
    try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null }
    catch { $blocked = $true }
    Assert $blocked 'Tampered release must be blocked'
    Set-Content -LiteralPath (Join-Path $root "releases\$b\run_worker.py") -Value '# test'
    Set-Content -LiteralPath (Join-Path $root 'failed.version') -Value $b
    $blocked = $false
    try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null }
    catch { $blocked = $true }
    Assert $blocked 'Previously failed release must be blocked'
    # Corrupted quarantine metadata must not silently allow a new promotion.
    foreach ($badFailed in @('', 'not-a-sha', ('B' * 40), '../../bad')) {
        Set-Content -LiteralPath (Join-Path $root 'failed.version') -Value $badFailed
        $rejectedFailed = $false
        try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null } catch { $rejectedFailed = $true }
        Assert $rejectedFailed 'Malformed failed.version must block promotion'
        Assert (((Get-Content (Join-Path $root 'current.version') -Raw).Trim()) -ceq $a) 'Bad failed marker changed current'
        Assert (-not (Test-Path (Join-Path $root 'pending.version'))) 'Bad failed marker created pending'
        Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Bad failed marker created journal'
    }
    Remove-Item -LiteralPath (Join-Path $root 'failed.version') -Force
    Set-Content -LiteralPath (Join-Path $root 'pending.version') -Value $b
    $blocked = $false
    try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null }
    catch { $blocked = $true }
    Assert $blocked 'Existing pending switch must block another promotion'
    Remove-Item -LiteralPath (Join-Path $root 'pending.version') -Force
    foreach ($badPending in @('', 'not-a-sha', ('A' * 40))) {
        Set-Content -LiteralPath (Join-Path $root 'pending.version') -Value $badPending
        $blockedBadPending = $false
        try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null } catch { $blockedBadPending = $true }
        Assert $blockedBadPending 'Corrupt pending marker must block promotion'
        Assert (((Get-Content (Join-Path $root 'current.version') -Raw).Trim()) -eq $a) 'Bad pending marker changed current'
        Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Bad pending marker created journal'
        Remove-Item -LiteralPath (Join-Path $root 'pending.version') -Force
    }
    # A stale journal without pending.version must still prevent another switch.
    $journalFile = Join-Path $root 'switch-journal.json'
    foreach ($staleJournal in @('', '{', ('{"schema":1,"previous":"' + $a + '","candidate":"' + $b + '","phase":"prepared"}'))) {
        [IO.File]::WriteAllText($journalFile, $staleJournal)
        $blockedStaleJournal = $false
        try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null } catch { $blockedStaleJournal = $true }
        Assert $blockedStaleJournal 'Unresolved switch journal must block promotion'
        Assert (((Get-Content (Join-Path $root 'current.version') -Raw).Trim()) -eq $a) 'Stale journal changed current'
        Assert (Test-Path $journalFile) 'Blocked switch removed recovery journal'
        Assert (-not (Test-Path (Join-Path $root 'pending.version'))) 'Stale journal created pending marker'
        Remove-Item -LiteralPath $journalFile -Force
    }
    $mutex = [System.Threading.Mutex]::new($false, 'Global\BybitClusterGridReleaseSwitch')
    $held = $mutex.WaitOne(0)
    Assert $held 'Could not acquire test mutex'
    try {
        $blocked = $false
        $job = Start-Job -ScriptBlock {
            param($Script,$Version,$Root)
            & $Script -Version $Version -InstallRoot $Root -Role WORKER
        } -ArgumentList $script,$b,$root
        try {
            Wait-Job $job -Timeout 30 | Out-Null
            Assert ($job.State -eq 'Failed') 'Concurrent switch must fail'
            $blocked = $true
        } finally { Remove-Job $job -Force -ErrorAction SilentlyContinue }
        Assert $blocked 'Mutex did not block concurrent switch'
    } finally {
        $mutex.ReleaseMutex()
        $mutex.Dispose()
    }
    # Exercise a real pointer promotion after all negative cases and verify
    # the committed journal is recoverable without leaving backup debris.
    $promoted = & $script -Version $b -InstallRoot $root -Role WORKER -Apply
    Assert ($promoted -contains "PENDING_SWITCH=$b") 'Successful switch did not report pending candidate'
    Assert (((Get-Content (Join-Path $root 'current.version') -Raw).Trim()) -eq $b) 'Apply did not promote candidate'
    Assert (((Get-Content (Join-Path $root 'previous.version') -Raw).Trim()) -eq $a) 'Apply lost rollback version'
    Assert (((Get-Content (Join-Path $root 'pending.version') -Raw).Trim()) -eq $b) 'Apply lost pending marker'
    $journal = Get-Content -LiteralPath (Join-Path $root 'switch-journal.json') -Raw | ConvertFrom-Json
    Assert ($journal.phase -eq 'committed') 'Apply did not commit journal'
    Assert ($journal.previous -eq $a -and $journal.candidate -eq $b) 'Apply wrote inconsistent journal'
    Assert (@(Get-ChildItem -LiteralPath $root -File -Filter '*.bak').Count -eq 0) 'Apply leaked File.Replace backup'
    # Complete the committed transaction through the real recovery script.
    $recover = Join-Path $PSScriptRoot '..\\installer\\recover-release.ps1'
    & $recover -InstallRoot $root -Role WORKER -Apply | Out-Null
    Assert (((Get-Content (Join-Path $root 'current.version') -Raw).Trim()) -eq $b) 'Committed recovery reverted promoted release'
    Assert (((Get-Content (Join-Path $root 'previous.version') -Raw).Trim()) -eq $a) 'Committed recovery lost rollback pointer'
    Assert (((Get-Content (Join-Path $root 'pending.version') -Raw).Trim()) -eq $b) 'Committed recovery lost unconfirmed pending release'
    Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Committed recovery left journal'
    $secondRecovery = & $recover -InstallRoot $root -Role WORKER -Apply
    Assert ($secondRecovery -contains 'NO_JOURNAL=true') 'Repeated recovery was not idempotent'
    Assert (((Get-Content (Join-Path $root 'current.version') -Raw).Trim()) -eq $b) 'Repeated recovery changed current release'
    Assert (@(Get-ChildItem -LiteralPath $root -File -Filter '*.bak').Count -eq 0) 'Recovery leaked backup files'
    # A committed but unconfirmed release must not be promoted again.
    $blockedUnconfirmed = $false
    try { & $script -Version $a -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $blockedUnconfirmed = $true }
    Assert $blockedUnconfirmed 'Unconfirmed committed release allowed another switch'
    Assert (((Get-Content (Join-Path $root 'current.version') -Raw).Trim()) -eq $b) 'Blocked switch changed current release'
    Assert (((Get-Content (Join-Path $root 'pending.version') -Raw).Trim()) -eq $b) 'Blocked switch changed pending release'
    Assert (((Get-Content (Join-Path $root 'previous.version') -Raw).Trim()) -eq $a) 'Blocked switch changed rollback release'
    Write-Output 'PASS: release switch plan, missing release, manifest mismatch, failed-release quarantine, concurrent-switch lock'
} finally {
    if (Test-Path $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
