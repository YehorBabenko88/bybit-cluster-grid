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
    $invalid = $false
    try { & $script -Version ('c' * 40) -InstallRoot $root -Role WORKER | Out-Null }
    catch { $invalid = $true }
    Assert $invalid 'Missing release must fail'
    $manifestPath = Join-Path $root "releases\$b\release-manifest.json"
    $hash = (Get-FileHash -LiteralPath (Join-Path $root "releases\$b\run_worker.py") -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath $manifestPath -Value ('{"version":"' + $a + '","files":{"run_worker.py":"' + $hash + '"}}')
    $invalid = $false
    try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null }
    catch { $invalid = $true }
    Assert $invalid 'Mismatched manifest must fail'
    Assert (((Get-Content (Join-Path $root 'current.version') -Raw).Trim()) -eq $a) 'Failed plan changed current'
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
    Remove-Item -LiteralPath (Join-Path $root 'failed.version') -Force
    Set-Content -LiteralPath (Join-Path $root 'pending.version') -Value $b
    $blocked = $false
    try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null }
    catch { $blocked = $true }
    Assert $blocked 'Existing pending switch must block another promotion'
    Remove-Item -LiteralPath (Join-Path $root 'pending.version') -Force
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
    Assert (-not (Test-Path (Join-Path $root 'pending.version'))) 'Committed recovery left pending marker'
    Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Committed recovery left journal'
    $secondRecovery = & $recover -InstallRoot $root -Role WORKER -Apply
    Assert ($secondRecovery -contains 'NO_JOURNAL=true') 'Repeated recovery was not idempotent'
    Assert (((Get-Content (Join-Path $root 'current.version') -Raw).Trim()) -eq $b) 'Repeated recovery changed current release'
    Assert (@(Get-ChildItem -LiteralPath $root -File -Filter '*.bak').Count -eq 0) 'Recovery leaked backup files'
    Write-Output 'PASS: release switch plan, missing release, manifest mismatch, failed-release quarantine, concurrent-switch lock'
} finally {
    if (Test-Path $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
