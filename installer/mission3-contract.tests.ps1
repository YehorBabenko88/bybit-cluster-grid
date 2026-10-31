[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$UnifiedRoot)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted') {throw 'Actual disposable Windows CI required'}
# Actual parser and CMS tests, no mock Windows success, no installed services.
foreach($file in @('mission3-install.ps1','mission3-service.ps1','mission3-verify-release.ps1')) {
 $tokens=$null;$errors=$null
 [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $file),[ref]$tokens,[ref]$errors) | Out-Null
 if ($errors.Count -ne 0) {throw 'PowerShell contract syntax rejected'}
}
& (Join-Path $UnifiedRoot 'tests/windows/Test-SecurityPackage.ps1')
# Pure PowerShell script status: no native exit code is produced. Under
# StrictMode, reading an unset LASTEXITCODE is itself a terminating failure.
if (-not $?) {throw 'Existing real CMS negative/positive tests failed'}
# Guard must deny a physical/external service root before any NSSM call.
$serviceText=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'mission3-service.ps1'))
foreach($required in @('Prepare','RUNNER_TEMP','github-hosted','LocalService','SERVICE_DEMAND_START','admin_stopped')) {
 if (!$serviceText.Contains($required)) {throw 'Required deployment safety contract missing'}
}
Write-Output "PASS MISSION3_SOURCE_CMS_CONTRACT ($($PSVersionTable.PSVersion)); service_execution=NOT_RUN; physical=NOT_AUTHORIZED"
