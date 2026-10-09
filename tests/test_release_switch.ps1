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
        [IO.File]::WriteAllText((Join-Path $dir 'release-manifest.json'), ('{"version":"' + $version + '","files":{}}'))
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
    Set-Content -LiteralPath $manifestPath -Value ('{"version":"' + $a + '","files":{}}')
    $invalid = $false
    try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null }
    catch { $invalid = $true }
    Assert $invalid 'Mismatched manifest must fail'
    Assert (((Get-Content (Join-Path $root 'current.version') -Raw).Trim()) -eq $a) 'Failed plan changed current'
    Set-Content -LiteralPath $manifestPath -Value ('{"version":"' + $b + '","files":{}}')
    Set-Content -LiteralPath (Join-Path $root 'failed.version') -Value $b
    $blocked = $false
    try { & $script -Version $b -InstallRoot $root -Role WORKER | Out-Null }
    catch { $blocked = $true }
    Assert $blocked 'Previously failed release must be blocked'
        Write-Output 'PASS: release switch plan, missing release, manifest mismatch, failed-release quarantine'
} finally {
    if (Test-Path $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
