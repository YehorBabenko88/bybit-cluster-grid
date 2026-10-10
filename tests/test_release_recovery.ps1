$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\installer\recover-release.ps1'
$root = Join-Path ([IO.Path]::GetTempPath()) ("grid-recovery-test-" + [guid]::NewGuid().ToString('N'))
$a = 'a' * 40
$b = 'b' * 40
function Assert([bool]$Condition,[string]$Message) { if (-not $Condition) { throw $Message } }
function Journal([string]$Phase) {
    $json = [ordered]@{ schema=1; previous=$a; candidate=$b; phase=$Phase } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText((Join-Path $root 'switch-journal.json'), $json)
}
try {
    foreach ($version in @($a,$b)) {
        $dir = Join-Path $root "releases\$version"
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        Set-Content -LiteralPath (Join-Path $dir 'run_worker.py') -Value '# test'
    }
    $current = Join-Path $root 'current.version'
    $pending = Join-Path $root 'pending.version'
    Set-Content -LiteralPath $current -Value $b
    Set-Content -LiteralPath $pending -Value $b
    Journal 'prepared'
    $plan = & $script -InstallRoot $root -Role WORKER
    Assert ($plan -contains 'PLAN_ONLY=true') 'Recovery must default to plan-only'
    Assert (((Get-Content $current -Raw).Trim()) -eq $b) 'Plan changed current'
    & $script -InstallRoot $root -Role WORKER -Apply | Out-Null
    Assert (((Get-Content $current -Raw).Trim()) -eq $a) 'Prepared recovery did not restore previous'
    Assert (-not (Test-Path $pending)) 'Prepared recovery left pending marker'
    Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Prepared recovery left journal'
    Set-Content -LiteralPath $current -Value $a
    Journal 'committed'
    & $script -InstallRoot $root -Role WORKER -Apply | Out-Null
    Assert (((Get-Content $current -Raw).Trim()) -eq $b) 'Committed recovery did not retain candidate'
    Assert (((Get-Content $pending -Raw).Trim()) -eq $b) 'Committed recovery lost pending'
    Assert (((Get-Content (Join-Path $root 'previous.version') -Raw).Trim()) -eq $a) 'Committed recovery lost rollback target'
    # CONTROL uses a different required entry point; verify both recovery phases.
    foreach ($version in @($a,$b)) {
        $control = Join-Path $root "releases\$version\grid"
        New-Item -ItemType Directory -Force -Path $control | Out-Null
        Set-Content -LiteralPath (Join-Path $control 'coordinator.py') -Value '# test'
    }
    Set-Content -LiteralPath $current -Value $b
    Set-Content -LiteralPath $pending -Value $b
    Journal 'prepared'
    & $script -InstallRoot $root -Role CONTROL -Apply | Out-Null
    Assert (((Get-Content $current -Raw).Trim()) -eq $a) 'CONTROL prepared recovery failed'
    Assert (-not (Test-Path $pending)) 'CONTROL prepared recovery left pending'
    Set-Content -LiteralPath $current -Value $a
    Journal 'committed'
    & $script -InstallRoot $root -Role CONTROL -Apply | Out-Null
    Assert (((Get-Content $current -Raw).Trim()) -eq $b) 'CONTROL committed recovery failed'
    Assert (((Get-Content $pending -Raw).Trim()) -eq $b) 'CONTROL committed recovery lost pending'
    # Reject a committed candidate whose CONTROL entry point is missing.
    Remove-Item -LiteralPath (Join-Path $root "releases\$b\grid\coordinator.py") -Force
    Journal 'committed'
    $missingBlocked = $false
    try { & $script -InstallRoot $root -Role CONTROL -Apply | Out-Null } catch { $missingBlocked = $true }
    Assert $missingBlocked 'Missing committed CONTROL candidate must fail closed'
    Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Missing candidate removed journal'
    # Simulate power loss at each pointer-write boundary of a prepared switch.
    foreach ($currentValue in @($a,$b)) {
        foreach ($pendingExists in @($false,$true)) {
            Set-Content -LiteralPath $current -Value $currentValue
            Set-Content -LiteralPath (Join-Path $root 'previous.version') -Value $a
            if ($pendingExists) {
                Set-Content -LiteralPath $pending -Value $b
            } elseif (Test-Path -LiteralPath $pending) {
                Remove-Item -LiteralPath $pending -Force
            }
            Journal 'prepared'
            & $script -InstallRoot $root -Role WORKER -Apply | Out-Null
            Assert (((Get-Content $current -Raw).Trim()) -eq $a) 'Prepared partial switch did not restore old release'
            Assert (-not (Test-Path $pending)) 'Prepared partial switch retained pending marker'
            Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Prepared partial switch retained journal'
            & $script -InstallRoot $root -Role WORKER -Apply | Out-Null
            Assert (((Get-Content $current -Raw).Trim()) -eq $a) 'Repeated recovery changed restored pointer'
        }
    }
    Journal 'invalid'
    $blocked = $false
    try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $blocked = $true }
    Assert $blocked 'Invalid journal must fail closed'
    Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Invalid journal was deleted'
    # Corrupt or truncated journals must never modify release pointers.
    foreach ($badJournal in @('', '{', 'null', '[]',
        '{"schema":1,"previous":"not-a-sha","candidate":"bbbb","phase":"prepared"}',
        ('{"schema":1,"previous":"' + $a + '","candidate":"' + $b + '","phase":"unknown"}'))) {
        Set-Content -LiteralPath $current -Value $b
        Set-Content -LiteralPath $pending -Value $b
        [IO.File]::WriteAllText((Join-Path $root 'switch-journal.json'), $badJournal)
        $rejected = $false
        try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $rejected = $true }
        Assert $rejected 'Corrupt journal must fail closed'
        Assert (((Get-Content $current -Raw).Trim()) -eq $b) 'Corrupt journal changed current'
        Assert (((Get-Content $pending -Raw).Trim()) -eq $b) 'Corrupt journal changed pending'
        Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Corrupt journal was removed'
    }
    Write-Output 'PASS: prepared, committed, plan-only and invalid-journal recovery'
} finally {
    if (Test-Path $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
