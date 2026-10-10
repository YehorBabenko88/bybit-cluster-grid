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
    # A conflicting active pointer must stop recovery without changing markers.
    Journal 'prepared'
    Set-Content -LiteralPath $current -Value ('c' * 40)
    Set-Content -LiteralPath $pending -Value $b
    $conflictBlocked = $false
    try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $conflictBlocked = $true }
    Assert $conflictBlocked 'Conflicting current pointer must fail closed'
    Assert (((Get-Content $current -Raw).Trim()) -eq ('c' * 40)) 'Conflict recovery changed current'
    Assert (((Get-Content $pending -Raw).Trim()) -eq $b) 'Conflict recovery changed pending'
    Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Conflict recovery removed journal'
    # Foreign, empty, and noncanonical pending markers must never be overwritten.
    foreach ($phaseCase in @('prepared','committed')) {
        foreach ($foreignPending in @(('c' * 40), '', ('B' * 40))) {
            Journal $phaseCase
            Set-Content -LiteralPath $current -Value $a
            Set-Content -LiteralPath $pending -Value $foreignPending
            $foreignRejected = $false
            try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $foreignRejected = $true }
            Assert $foreignRejected 'Conflicting pending pointer must fail closed'
            Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Conflicting pending removed journal'
            Assert (((Get-Content $pending -Raw).Trim()) -ceq $foreignPending) 'Conflicting pending pointer was modified'
            Assert (((Get-Content $current -Raw).Trim()) -ceq $a) 'Conflicting pending changed current'
        }
    }
    # A tampered executable with a valid manifest must block committed recovery.
    Journal 'committed'
    Set-Content -LiteralPath $current -Value $a
    Set-Content -LiteralPath $pending -Value $b
    $candidateEntry = Join-Path $root "releases\$b\run_worker.py"
    $candidateManifest = Join-Path $root "releases\$b\release-manifest.json"
    $originalEntry = Get-Content -LiteralPath $candidateEntry -Raw
    $originalHash = (Get-FileHash -LiteralPath $candidateEntry -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText($candidateManifest, ('{"version":"' + $b + '","files":{"run_worker.py":"' + $originalHash + '"}}'))
    Set-Content -LiteralPath $candidateEntry -Value '# tampered'
    $tamperedRejected = $false
    try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $tamperedRejected = $true }
    Assert $tamperedRejected 'Tampered recovery executable must be rejected'
    Assert (((Get-Content $current -Raw).Trim()) -ceq $a) 'Tampered executable changed current'
    Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Tampered executable removed journal'
    [IO.File]::WriteAllText($candidateEntry, $originalEntry)
    Remove-Item -LiteralPath $candidateManifest -Force
    # Malformed and incomplete target manifests must block recovery before writes.
    foreach ($badTargetManifest in @(
        '{',
        'null',
        ('{"version":"' + $b + '","files":{}}'),
        ('{"version":"' + $a + '","files":{"run_worker.py":"' + $originalHash + '"}}'),
        ('{"version":"' + $b + '","files":{"run_worker.py":"bad-hash"}}')
    )) {
        Journal 'committed'
        Set-Content -LiteralPath $current -Value $a
        Set-Content -LiteralPath $pending -Value $b
        [IO.File]::WriteAllText($candidateManifest, $badTargetManifest)
        $badTargetRejected = $false
        try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $badTargetRejected = $true }
        Assert $badTargetRejected 'Malformed recovery manifest must fail closed'
        Assert (((Get-Content $current -Raw).Trim()) -ceq $a) 'Malformed recovery manifest changed current'
        Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Malformed recovery manifest removed journal'
    }
    Remove-Item -LiteralPath $candidateManifest -Force
    # A manifest-listed supporting file must be verified as well as the entry point.
    Journal 'committed'
    Set-Content -LiteralPath $current -Value $a
    Set-Content -LiteralPath $pending -Value $b
    $supportPath = Join-Path $root "releases\$b\support.txt"
    [IO.File]::WriteAllText($supportPath, 'original')
    $supportHash = (Get-FileHash -LiteralPath $supportPath -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText($candidateManifest, ('{"version":"' + $b + '","files":{"run_worker.py":"' + $originalHash + '","support.txt":"' + $supportHash + '"}}'))
    [IO.File]::WriteAllText($supportPath, 'tampered')
    $supportRejected = $false
    try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $supportRejected = $true }
    Assert $supportRejected 'Tampered supporting file must block recovery'
    Assert (((Get-Content $current -Raw).Trim()) -ceq $a) 'Tampered supporting file changed current'
    Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Tampered supporting file removed journal'
    Remove-Item -LiteralPath $supportPath -Force
    Remove-Item -LiteralPath $candidateManifest -Force
    # A valid entry point hash does not authorize an unlisted Python module.
    Journal 'committed'
    Set-Content -LiteralPath $current -Value $a
    Set-Content -LiteralPath $pending -Value $b
    $unlistedSource = Join-Path $root "releases\$b\unlisted_module.py"
    [IO.File]::WriteAllText($unlistedSource, '# not in manifest')
    [IO.File]::WriteAllText($candidateManifest, ('{"version":"' + $b + '","files":{"run_worker.py":"' + $originalHash + '"}}'))
    $unlistedRejected = $false
    try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $unlistedRejected = $true }
    Assert $unlistedRejected 'Unlisted Python module must block committed recovery'
    Assert (((Get-Content $current -Raw).Trim()) -ceq $a) 'Unlisted module changed current'
    Assert (((Get-Content $pending -Raw).Trim()) -ceq $b) 'Unlisted module changed pending'
    Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Unlisted module removed journal'
    Remove-Item -LiteralPath $unlistedSource -Force
    Remove-Item -LiteralPath $candidateManifest -Force
    # Prepared recovery must validate the previous release, not the candidate.
    Journal 'prepared'
    Set-Content -LiteralPath $current -Value $b
    Set-Content -LiteralPath $pending -Value $b
    $previousEntry = Join-Path $root "releases\$a\run_worker.py"
    $previousHash = (Get-FileHash -LiteralPath $previousEntry -Algorithm SHA256).Hash.ToLowerInvariant()
    $previousControl = Join-Path $root "releases\$a\grid\coordinator.py"
    $previousControlHash = (Get-FileHash -LiteralPath $previousControl -Algorithm SHA256).Hash.ToLowerInvariant()
    $previousManifest = Join-Path $root "releases\$a\release-manifest.json"
    [IO.File]::WriteAllText($previousManifest, ('{"version":"' + $a + '","files":{"run_worker.py":"' + $previousHash + '","grid/coordinator.py":"' + $previousControlHash + '"}}'))
    $previousOriginal = Get-Content -LiteralPath $previousEntry -Raw
    [IO.File]::WriteAllText($previousEntry, '# corrupted rollback target')
    $previousRejected = $false
    try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $previousRejected = $true }
    Assert $previousRejected 'Prepared recovery must reject tampered previous release'
    Assert (((Get-Content $current -Raw).Trim()) -ceq $b) 'Tampered rollback target changed current'
    Assert (((Get-Content $pending -Raw).Trim()) -ceq $b) 'Tampered rollback target changed pending'
    Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Tampered rollback target removed journal'
    [IO.File]::WriteAllText($previousEntry, $previousOriginal)
    Remove-Item -LiteralPath $previousManifest -Force

    # Committed recovery must not retain a corrupted rollback entry point.
    Journal 'committed'
    Set-Content -LiteralPath $current -Value $a
    Set-Content -LiteralPath $pending -Value $b
    [IO.File]::WriteAllText($previousManifest, ('{"version":"' + $a + '","files":{"run_worker.py":"' + $previousHash + '","grid/coordinator.py":"' + $previousControlHash + '"}}'))
    [IO.File]::WriteAllText($previousEntry, '# damaged previous release')
    $committedRollbackRejected = $false
    try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $committedRollbackRejected = $true }
    Assert $committedRollbackRejected 'Committed recovery must reject corrupted rollback entry point'
    Assert (((Get-Content $current -Raw).Trim()) -ceq $a) 'Corrupt rollback changed current'
    Assert (((Get-Content $pending -Raw).Trim()) -ceq $b) 'Corrupt rollback changed pending'
    Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Corrupt rollback removed journal'
    [IO.File]::WriteAllText($previousEntry, $previousOriginal)
    Remove-Item -LiteralPath $previousManifest -Force
    # Committed recovery must validate every manifest-listed rollback support file.
    Journal 'committed'
    Set-Content -LiteralPath $current -Value $a
    Set-Content -LiteralPath $pending -Value $b
    $rollbackSupport = Join-Path $root "releases\$a\rollback-support.txt"
    [IO.File]::WriteAllText($rollbackSupport, 'intact')
    $rollbackSupportHash = (Get-FileHash -LiteralPath $rollbackSupport -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText($previousManifest, ('{"version":"' + $a + '","files":{"run_worker.py":"' + $previousHash + '","grid/coordinator.py":"' + $previousControlHash + '","rollback-support.txt":"' + $rollbackSupportHash + '"}}'))
    [IO.File]::WriteAllText($rollbackSupport, 'corrupted')
    $rollbackSupportRejected = $false
    try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $rollbackSupportRejected = $true }
    Assert $rollbackSupportRejected 'Corrupted rollback support file must block committed recovery'
    Assert (((Get-Content $current -Raw).Trim()) -ceq $a) 'Corrupted rollback support changed current'
    Assert (((Get-Content $pending -Raw).Trim()) -ceq $b) 'Corrupted rollback support changed pending'
    Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Corrupted rollback support removed journal'
    Remove-Item -LiteralPath $rollbackSupport -Force
    Remove-Item -LiteralPath $previousManifest -Force
    # Committed recovery must reject Python sources omitted from rollback manifest.
    Journal 'committed'
    Set-Content -LiteralPath $current -Value $a
    Set-Content -LiteralPath $pending -Value $b
    $unlistedRollback = Join-Path $root "releases\$a\unlisted_rollback.py"
    [IO.File]::WriteAllText($unlistedRollback, '# unlisted rollback source')
    [IO.File]::WriteAllText($previousManifest, ('{"version":"' + $a + '","files":{"run_worker.py":"' + $previousHash + '","grid/coordinator.py":"' + $previousControlHash + '"}}'))
    $unlistedRollbackRejected = $false
    try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $unlistedRollbackRejected = $true }
    Assert $unlistedRollbackRejected 'Unlisted rollback Python source must block committed recovery'
    Assert (((Get-Content $current -Raw).Trim()) -ceq $a) 'Unlisted rollback source changed current'
    Assert (((Get-Content $pending -Raw).Trim()) -ceq $b) 'Unlisted rollback source changed pending'
    Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Unlisted rollback source removed journal'
    Remove-Item -LiteralPath $unlistedRollback -Force
    Remove-Item -LiteralPath $previousManifest -Force
    # A journal path occupied by a directory is corruption, not NO_JOURNAL.
    $journalMarker = Join-Path $root 'switch-journal.json'
    if (Test-Path -LiteralPath $journalMarker) { Remove-Item -LiteralPath $journalMarker -Force }
    New-Item -ItemType Directory -Path $journalMarker | Out-Null
    $journalDirectoryRejected = $false
    try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $journalDirectoryRejected = $true }
    Assert $journalDirectoryRejected 'Directory journal must fail closed'
    Assert (Test-Path -LiteralPath $journalMarker -PathType Container) 'Directory journal was modified'
    Remove-Item -LiteralPath $journalMarker -Recurse -Force
    # A directory in place of current.version must not be treated as a missing pointer.
    Journal 'prepared'
    if (Test-Path -LiteralPath $current) { Remove-Item -LiteralPath $current -Force }
    New-Item -ItemType Directory -Path $current | Out-Null
    Set-Content -LiteralPath $pending -Value $b
    $directoryPointerRejected = $false
    try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $directoryPointerRejected = $true }
    Assert $directoryPointerRejected 'Directory current.version must block recovery'
    Assert (Test-Path -LiteralPath $current -PathType Container) 'Recovery modified current.version directory'
    Assert (Test-Path -LiteralPath (Join-Path $root 'switch-journal.json')) 'Directory pointer recovery removed journal'
    Assert (((Get-Content $pending -Raw).Trim()) -ceq $b) 'Directory pointer recovery modified pending'
    Remove-Item -LiteralPath $current -Recurse -Force
    Set-Content -LiteralPath $current -Value $a
    # A pending.version directory must block both transaction phases without mutation.
    foreach ($pendingPhase in @('prepared','committed')) {
        Journal $pendingPhase
        Set-Content -LiteralPath $current -Value $a
        if (Test-Path -LiteralPath $pending) { Remove-Item -LiteralPath $pending -Force }
        New-Item -ItemType Directory -Path $pending | Out-Null
        $pendingDirectoryRejected = $false
        try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $pendingDirectoryRejected = $true }
        Assert $pendingDirectoryRejected 'Directory pending.version must block recovery'
        Assert (Test-Path -LiteralPath $pending -PathType Container) 'Recovery modified pending.version directory'
        Assert (((Get-Content $current -Raw).Trim()) -ceq $a) 'Directory pending.version changed current'
        Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Directory pending.version removed journal'
        Remove-Item -LiteralPath $pending -Recurse -Force
    }
    # A directory at previous.version must fail before changing any pointer.
    Journal 'committed'
    Set-Content -LiteralPath $current -Value $a
    Set-Content -LiteralPath $pending -Value $b
    $previousMarker = Join-Path $root 'previous.version'
    if (Test-Path -LiteralPath $previousMarker) { Remove-Item -LiteralPath $previousMarker -Force }
    New-Item -ItemType Directory -Path $previousMarker | Out-Null
    $previousDirectoryRejected = $false
    try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $previousDirectoryRejected = $true }
    Assert $previousDirectoryRejected 'Directory previous.version must block recovery'
    Assert (Test-Path -LiteralPath $previousMarker -PathType Container) 'Recovery modified previous.version directory'
    Assert (((Get-Content $current -Raw).Trim()) -ceq $a) 'Directory previous.version changed current'
    Assert (((Get-Content $pending -Raw).Trim()) -ceq $b) 'Directory previous.version changed pending'
    Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Directory previous.version removed journal'
    Remove-Item -LiteralPath $previousMarker -Recurse -Force
    # Recovery must reject corrupt current pointers without mutating the journal.
    foreach ($badCurrent in @( ('A' * 40), ('g' * 40), '../../bad' )) {
        Journal 'prepared'
        Set-Content -LiteralPath $current -Value $badCurrent
        Set-Content -LiteralPath $pending -Value $b
        $rejectedPointer = $false
        try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $rejectedPointer = $true }
        Assert $rejectedPointer 'Corrupt current pointer must block recovery'
        Assert (((Get-Content $current -Raw).Trim()) -eq $badCurrent) 'Corrupt pointer recovery changed current'
        Assert (((Get-Content $pending -Raw).Trim()) -eq $b) 'Corrupt pointer recovery changed pending'
        Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Corrupt pointer recovery deleted journal'
    }
    # Recovery must be repeatable when a prepared transaction is interrupted
    # after the rollback pointer was written but before journal removal.
    foreach ($pendingValue in @($a,$b)) {
        Journal 'prepared'
        Set-Content -LiteralPath $current -Value $a
        Set-Content -LiteralPath $pending -Value $pendingValue
        & $script -InstallRoot $root -Role WORKER -Apply | Out-Null
        Assert (((Get-Content $current -Raw).Trim()) -ceq $a) 'Repeat prepared recovery changed rollback target'
        Assert (-not (Test-Path $pending)) 'Repeat prepared recovery retained pending marker'
        Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Repeat prepared recovery retained journal'
    }
    # A committed transaction interrupted after writing the candidate pointer
    # must converge on candidate + pending, and remain safe to retry.
    foreach ($pendingValue in @($a,$b)) {
        Journal 'committed'
        Set-Content -LiteralPath $current -Value $b
        Set-Content -LiteralPath $pending -Value $pendingValue
        & $script -InstallRoot $root -Role WORKER -Apply | Out-Null
        Assert (((Get-Content $current -Raw).Trim()) -ceq $b) 'Repeat committed recovery lost candidate'
        Assert (((Get-Content $pending -Raw).Trim()) -ceq $b) 'Repeat committed recovery lost pending candidate'
        Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Repeat committed recovery retained journal'
    }
    # A crash can leave the active pointer absent while the journal survives.
    # The journal must still be sufficient to recover either transaction phase.
    foreach ($phaseCase in @('prepared','committed')) {
        Journal $phaseCase
        if (Test-Path -LiteralPath $current) { Remove-Item -LiteralPath $current -Force }
        if (Test-Path -LiteralPath $pending) { Remove-Item -LiteralPath $pending -Force }
        & $script -InstallRoot $root -Role WORKER -Apply | Out-Null
        $expectedCurrent = if ($phaseCase -eq 'prepared') { $a } else { $b }
        Assert (((Get-Content $current -Raw).Trim()) -ceq $expectedCurrent) 'Missing active pointer was not reconstructed'
        if ($phaseCase -eq 'prepared') {
            Assert (-not (Test-Path $pending)) 'Prepared recovery recreated pending marker'
        } else {
            Assert (((Get-Content $pending -Raw).Trim()) -ceq $b) 'Committed recovery did not reconstruct pending'
        }
        Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Missing-pointer recovery retained journal'
    }
    # A journal left by a committed switch must preserve its candidate on
    # repeated recovery, even when previous.version is stale or missing.
    foreach ($previousState in @('missing','stale')) {
        Journal 'committed'
        Set-Content -LiteralPath $current -Value $b
        Set-Content -LiteralPath $pending -Value $b
        $previousPath = Join-Path $root 'previous.version'
        if ($previousState -eq 'missing') {
            if (Test-Path -LiteralPath $previousPath) { Remove-Item -LiteralPath $previousPath -Force }
        } else {
            Set-Content -LiteralPath $previousPath -Value ('c' * 40)
        }
        & $script -InstallRoot $root -Role WORKER -Apply | Out-Null
        Assert (((Get-Content $previousPath -Raw).Trim()) -ceq $a) 'Committed recovery did not repair rollback pointer'
        Assert (((Get-Content $current -Raw).Trim()) -ceq $b) 'Committed recovery changed active candidate'
        Assert (((Get-Content $pending -Raw).Trim()) -ceq $b) 'Committed recovery changed pending candidate'
        Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Committed recovery retained journal'
    }
    # An absent pointer is recoverable, but an existing empty file indicates
    # corruption and must not be silently treated as a missing pointer.
    foreach ($phaseCase in @('prepared','committed')) {
        Journal $phaseCase
        Set-Content -LiteralPath $current -Value ''
        $emptyPointerRejected = $false
        try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $emptyPointerRejected = $true }
        Assert $emptyPointerRejected 'Empty current.version must fail closed'
        Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Empty pointer recovery erased journal'
        Assert (((Get-Content $current -Raw).Trim()) -ceq '') 'Empty pointer recovery changed current'
    }
    # Invalid JSON root types cannot represent a transaction journal.
    foreach ($invalidRoot in @('null', '[]', '42', '"prepared"', '{}')) {
        [IO.File]::WriteAllText((Join-Path $root 'switch-journal.json'), $invalidRoot)
        Set-Content -LiteralPath $current -Value $a
        $invalidRootRejected = $false
        try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $invalidRootRejected = $true }
        Assert $invalidRootRejected "Invalid journal root must fail closed: $invalidRoot"
        Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Invalid journal root was removed'
        Assert (((Get-Content $current -Raw).Trim()) -ceq $a) 'Invalid journal root changed current'
    }
    # JSON coercion must not turn malformed field types into valid metadata.
    foreach ($badTypedJournal in @(
        ('{"schema":"1","previous":"' + $a + '","candidate":"' + $b + '","phase":"prepared"}'),
        ('{"schema":true,"previous":"' + $a + '","candidate":"' + $b + '","phase":"prepared"}'),
        ('{"schema":1,"previous":null,"candidate":"' + $b + '","phase":"prepared"}'),
        ('{"schema":1,"previous":"' + $a + '","candidate":"' + $b + '","phase":["prepared"]}')
    )) {
        [IO.File]::WriteAllText((Join-Path $root 'switch-journal.json'), $badTypedJournal)
        Set-Content -LiteralPath $current -Value $a
        $badTypeRejected = $false
        try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $badTypeRejected = $true }
        Assert $badTypeRejected 'Wrong journal field type must fail closed'
        Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Wrong journal field type erased journal'
        Assert (((Get-Content $current -Raw).Trim()) -ceq $a) 'Wrong journal field type changed current'
    }
    # Missing rollback entry point must fail closed for both roles and phases.
    foreach ($roleCase in @(
        @{ Role='WORKER'; Entry='run_worker.py' },
        @{ Role='CONTROL'; Entry='grid\\coordinator.py' }
    )) {
        $rollbackEntry = Join-Path (Join-Path $root "releases\\$a") $roleCase.Entry
        $savedEntry = Get-Content -LiteralPath $rollbackEntry -Raw
        Remove-Item -LiteralPath $rollbackEntry -Force
        try {
            foreach ($phase in @('prepared','committed')) {
                Journal $phase
                Set-Content -LiteralPath $current -Value $b
                Set-Content -LiteralPath $pending -Value $b
                $blockedMissingRollback = $false
                try { & $script -InstallRoot $root -Role $roleCase.Role -Apply | Out-Null } catch { $blockedMissingRollback = $true }
                Assert $blockedMissingRollback "Missing $($roleCase.Role) rollback target must fail closed"
                Assert (((Get-Content $current -Raw).Trim()) -eq $b) 'Missing rollback changed current pointer'
                Assert (((Get-Content $pending -Raw).Trim()) -eq $b) 'Missing rollback changed pending pointer'
                Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Missing rollback deleted journal'
            }
        } finally {
            [IO.File]::WriteAllText($rollbackEntry, $savedEntry)
        }
    }
    # Once the missing rollback entry point is restored, retry must recover
    # the same journal without requiring any manual marker edits.
    Journal 'prepared'
    Set-Content -LiteralPath $current -Value $b
    Set-Content -LiteralPath $pending -Value $b
    $rollbackFile = Join-Path $root "releases\\$a\\run_worker.py"
    $rollbackContents = Get-Content -LiteralPath $rollbackFile -Raw
    Remove-Item -LiteralPath $rollbackFile -Force
    $retryInitiallyBlocked = $false
    try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $retryInitiallyBlocked = $true }
    Assert $retryInitiallyBlocked 'First recovery should reject missing rollback file'
    Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Failed recovery must retain journal for retry'
    [IO.File]::WriteAllText($rollbackFile, $rollbackContents)
    & $script -InstallRoot $root -Role WORKER -Apply | Out-Null
    Assert (((Get-Content $current -Raw).Trim()) -eq $a) 'Recovery retry did not restore previous version'
    Assert (-not (Test-Path $pending)) 'Recovery retry left pending marker'
    Assert (-not (Test-Path (Join-Path $root 'switch-journal.json'))) 'Recovery retry left journal'
    # Corrupt or truncated journals must never modify release pointers.
    foreach ($badJournal in @('', '{', 'null', '[]',
        '{"schema":1,"previous":"not-a-sha","candidate":"bbbb","phase":"prepared"}',
        ('{"schema":1,"previous":"' + ('A' * 40) + '","candidate":"' + $b + '","phase":"prepared"}'),
        ('{"schema":1,"previous":"' + $a + '","candidate":"' + ('B' * 40) + '","phase":"committed"}'),
        ('{"schema":1,"previous":"' + $a + '","candidate":"' + $b + '","phase":"unknown"}'),
        ('{"schema":1,"previous":"' + $a + '","candidate":"' + $b + '","phase":"PREPARED"}'),
        ('{"schema":1,"previous":"' + $a + '","candidate":"' + $b + '","phase":"COMMITTED"}'))) {
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
    # Successful atomic pointer replacements must not leak .bak files.
    Journal 'prepared'
    Set-Content -LiteralPath $current -Value $b
    Set-Content -LiteralPath $pending -Value $b
    & $script -InstallRoot $root -Role WORKER -Apply | Out-Null
    $backups = @(Get-ChildItem -LiteralPath $root -File -Filter '*.bak')
    Assert ($backups.Count -eq 0) 'Recovery leaked File.Replace backup files'
    Write-Output 'PASS: prepared, committed, plan-only and invalid-journal recovery'
} finally {
    if (Test-Path $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
