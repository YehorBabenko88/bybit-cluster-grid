# Actual local junction and command-observer regression. Cloud hosted Windows only.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or !$env:RUNNER_TEMP) {throw 'Disposable hosted Windows required'}
if ($env:COMPUTERNAME -match '^(?i:LS5|PC4|ADMINIT)$') {throw 'Physical office execution prohibited'}
$testRoot=Join-Path $env:RUNNER_TEMP ('mission3-path-security-'+[guid]::NewGuid().ToString('N'))
$target=Join-Path $testRoot 'local-target'
$junction=Join-Path $testRoot 'local-junction'
$missing=Join-Path $testRoot 'missing-parent'
function Test-Mission3PathHelper([string]$ScriptFile,[string]$Junction,[string]$Missing,[string]$Allowed) {
 $tokens=$null;$errors=$null
 $ast=[Management.Automation.Language.Parser]::ParseFile($ScriptFile,[ref]$tokens,[ref]$errors)
 if ($errors.Count -ne 0) {throw 'Installer parse rejected'}
 $definitions=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq 'Assert-Mission3LocalPath'},$true))
 if ($definitions.Count -ne 1) {throw 'One actual source path helper required'}
 $script:Mission3PathProbes=New-Object 'System.Collections.Generic.List[string]'
 $script:Mission3ForbiddenPrefix=''
 function Get-Item {
  [CmdletBinding()]param([Parameter(Mandatory=$true)][string]$LiteralPath,[switch]$Force)
  $script:Mission3PathProbes.Add($LiteralPath)
  if ($script:Mission3ForbiddenPrefix -and $LiteralPath.StartsWith($script:Mission3ForbiddenPrefix,[StringComparison]::OrdinalIgnoreCase)) {throw 'FORBIDDEN_DESCENDANT_PROBE'}
  Microsoft.PowerShell.Management\Get-Item @PSBoundParameters
 }
 function Test-Path {
  [CmdletBinding()]param([Parameter(Mandatory=$true)][string]$LiteralPath)
  $script:Mission3PathProbes.Add($LiteralPath)
  if ($script:Mission3ForbiddenPrefix -and $LiteralPath.StartsWith($script:Mission3ForbiddenPrefix,[StringComparison]::OrdinalIgnoreCase)) {throw 'FORBIDDEN_DESCENDANT_PROBE'}
  Microsoft.PowerShell.Management\Test-Path @PSBoundParameters
 }
 # Extract only the real function definition. Never execute installer top-level
 # actions, signatures, Python, NSSM, services or enrollment in this test.
 . ([ScriptBlock]::Create($definitions[0].Extent.Text))
 Assert-Mission3LocalPath $Allowed
 $script:Mission3PathProbes.Clear()
 $script:Mission3ForbiddenPrefix=$Junction.TrimEnd('\')+'\'
 $rejected=$false
 try {Assert-Mission3LocalPath (Join-Path $Junction 'existing-marker.txt')} catch {
  if ($_.Exception.Message -eq 'FORBIDDEN_DESCENDANT_PROBE') {throw 'Guard probed a junction descendant before its ancestor'}
  $rejected=$true
 }
 if (!$rejected -or !$script:Mission3PathProbes.Contains($Junction)) {throw 'Actual local junction must be inspected and refused'}
 foreach($probe in $script:Mission3PathProbes) {
  if ($probe.StartsWith($script:Mission3ForbiddenPrefix,[StringComparison]::OrdinalIgnoreCase)) {throw 'Descendant metadata was accessed'}
 }
 # Missing ancestors are allowed for a future installation, but their children
 # must never be probed. Unknown errors must still block, not look like absence.
 $script:Mission3PathProbes.Clear()
 $script:Mission3ForbiddenPrefix=$Missing.TrimEnd('\')+'\'
 Assert-Mission3LocalPath (Join-Path $Missing 'uncreated-child\file.txt')
 if (!$script:Mission3PathProbes.Contains($Missing)) {throw 'Missing ancestor was not observed'}
 $script:Mission3PathProbes.Clear()
 $rejected=$false
 try {Assert-Mission3LocalPath '\\not-a-real-server\never-contacted\file.txt'} catch {$rejected=$true}
 if (!$rejected -or $script:Mission3PathProbes.Count -ne 0) {throw 'UNC must be refused before filesystem probes'}
 $script:Mission3PathProbes.Clear()
 $script:Mission3ForbiddenPrefix=''
}
try {
 New-Item -ItemType Directory -Path $testRoot | Out-Null
 New-Item -ItemType Directory -Path $target | Out-Null
 [IO.File]::WriteAllText((Join-Path $target 'existing-marker.txt'),'harmless local marker')
 New-Item -ItemType Junction -Path $junction -Target $target | Out-Null
 foreach($file in @('mission3-install.ps1','mission3-service.ps1')) {
  Test-Mission3PathHelper (Join-Path $PSScriptRoot $file) $junction $missing (Join-Path $target 'existing-marker.txt')
 }
 if (![IO.File]::Exists((Join-Path $target 'existing-marker.txt'))) {throw 'Local target changed unexpectedly'}
 Write-Output "PASS MISSION3_ANCESTOR_FIRST_LOCAL_PATH ($($PSVersionTable.PSVersion)); services=NOT_RUN; physical=NOT_AUTHORIZED"
} finally {
 # Remove only our own harmless junction, then our own freshly created test root.
 # Directory.Delete without recursion removes the junction itself, not its target.
 if ([IO.Directory]::Exists($junction)) {[IO.Directory]::Delete($junction)}
 if ([IO.Directory]::Exists($testRoot)) {Remove-Item -LiteralPath $testRoot -Recurse -Force}
}
