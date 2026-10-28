# Pure production-branch regression: no native calls, processes or host changes.
$ErrorActionPreference = 'Stop'
$path = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../physical-smoke-s0.ps1'))
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'S0_TIMEOUT_TEST_SYNTAX' }
$expected = @(
    'if ($result.TimedOut) { throw ''S0_NATIVE_TIMEOUT_OWN_JOB_CLOSED'' }',
    'if ($result.ExitCode -ne 0) { throw ''S0_COMMAND_FAILED'' }'
)
$branches = @($ast.FindAll({ param($node) $node -is [Management.Automation.Language.IfStatementAst] }, $true))
foreach ($text in $expected) {
    if (@($branches | Where-Object { $_.Extent.Text -ceq $text }).Count -ne 1) { throw 'S0_TIMEOUT_TEST_BRANCH_MISSING' }
}
# Only these two exact, reviewed throw-only branches are evaluated.
$snippet = [scriptblock]::Create('param($result)' + "`n" + ($expected -join "`n"))
$cases = @(
    @{TimedOut=$true; Code=[uint32]0; Error='S0_NATIVE_TIMEOUT_OWN_JOB_CLOSED'},
    @{TimedOut=$true; Code=[uint32]7; Error='S0_NATIVE_TIMEOUT_OWN_JOB_CLOSED'},
    @{TimedOut=$false; Code=[uint32]0; Error=$null},
    @{TimedOut=$false; Code=[uint32]7; Error='S0_COMMAND_FAILED'},
    @{TimedOut=$false; Code=[uint32]4294967295; Error='S0_COMMAND_FAILED'}
)
foreach ($case in $cases) {
    $observed = $null
    try { & $snippet ([pscustomobject]@{TimedOut=$case.TimedOut; ExitCode=$case.Code}) }
    catch { $observed = $_.Exception.Message }
    if ($observed -cne $case.Error) { throw 'S0_TIMEOUT_TEST_FALSE_SUCCESS' }
}
[ordered]@{scope='PURE_TIMEOUT_BRANCH_TEST_NOT_PHYSICAL'; status='TEST_PASS'; cases=$cases.Count; s0_execute=$false; g1_execute=$false} | ConvertTo-Json
