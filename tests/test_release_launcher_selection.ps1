$ErrorActionPreference = 'Stop'
$root = Join-Path ([IO.Path]::GetTempPath()) ("grid-launcher-test-" + [guid]::NewGuid().ToString('N'))
$originalLocation = (Get-Location).Path
$oldProgramData = $env:ProgramData
$oldCapture = $env:GRID_TEST_CAPTURE
$a = 'a' * 40
$b = 'b' * 40
function Assert([bool]$Condition,[string]$Message) { if (-not $Condition) { throw $Message } }
try {
    $env:ProgramData = Join-Path $root 'data'
    New-Item -ItemType Directory -Force -Path $env:ProgramData | Out-Null
    $stub = Join-Path $root 'fake-python.ps1'
    Set-Content -LiteralPath $stub -Value '[IO.File]::WriteAllText($env:GRID_TEST_CAPTURE, ($args -join " "))'
    foreach ($role in @('WORKER','CONTROL')) {
        $install = Join-Path $root $role
        $entry = if ($role -eq 'WORKER') { 'run_worker.py' } else { 'grid\coordinator.py' }
        foreach ($v in @($a,$b)) {
            $dest = Join-Path (Join-Path $install 'releases') $v
            New-Item -ItemType Directory -Force -Path (Split-Path (Join-Path $dest $entry) -Parent) | Out-Null
            Set-Content -LiteralPath (Join-Path $dest $entry) -Value '# stub'
        }
        $launcherName = if ($role -eq 'WORKER') { 'launcher.ps1' } else { 'coordinator-launcher.ps1' }
        $launcher = Join-Path (Join-Path $PSScriptRoot '..\installer') $launcherName
        $env:GRID_TEST_CAPTURE = Join-Path $root ($role + '.txt')
        foreach ($case in @(
            @{ Current=$a; Previous=$b; Expected=$a },
            @{ Current='../../bad'; Previous=$b; Expected=$b },
            @{ Current=$b; Previous=$a; Expected=$b },
            @{ Current=('c' * 40); Previous=$a; Expected=$a }
        )) {
            Set-Content -LiteralPath (Join-Path $install 'current.version') -Value $case.Current
            Set-Content -LiteralPath (Join-Path $install 'previous.version') -Value $case.Previous
            if (Test-Path $env:GRID_TEST_CAPTURE) { Remove-Item $env:GRID_TEST_CAPTURE -Force }
            & $launcher -Python $stub -InstallRoot $install
            Assert (Test-Path $env:GRID_TEST_CAPTURE) "$role launcher did not call stub"
            $invocation = Get-Content -LiteralPath $env:GRID_TEST_CAPTURE -Raw
            Assert ($invocation.Contains("--version " + $case.Expected)) "$role selected wrong release for $($case.Current)"
        }
        # Neither release exists and bootstrap is absent: startup must fail closed.
        Set-Content -LiteralPath (Join-Path $install 'current.version') -Value ('c' * 40)
        Set-Content -LiteralPath (Join-Path $install 'previous.version') -Value ('d' * 40)
        if (Test-Path $env:GRID_TEST_CAPTURE) { Remove-Item $env:GRID_TEST_CAPTURE -Force }
        $startupFailed = $false
        try { & $launcher -Python $stub -InstallRoot $install | Out-Null } catch { $startupFailed = $true }
        Assert $startupFailed "$role launched without a valid release or bootstrap"
        Assert (-not (Test-Path $env:GRID_TEST_CAPTURE)) "$role invoked Python without a runnable release"
    }
    Write-Output 'PASS: WORKER and CONTROL launcher version selection'
} finally {
    Set-Location -LiteralPath $originalLocation
    $env:ProgramData = $oldProgramData
    $env:GRID_TEST_CAPTURE = $oldCapture
    if (Test-Path $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
