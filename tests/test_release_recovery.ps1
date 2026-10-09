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
    Journal 'invalid'
    $blocked = $false
    try { & $script -InstallRoot $root -Role WORKER -Apply | Out-Null } catch { $blocked = $true }
    Assert $blocked 'Invalid journal must fail closed'
    Assert (Test-Path (Join-Path $root 'switch-journal.json')) 'Invalid journal was deleted'
    Write-Output 'PASS: prepared, committed, plan-only and invalid-journal recovery'
} finally {
    if (Test-Path $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
