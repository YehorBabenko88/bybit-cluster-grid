# Actual vendor archives only. Missing input is an error, never a skipped test.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RequestFile)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
# Request pins must come from the externally reviewed release/CI configuration.
# The stage enforces hosted Windows, explicit authorization and RUNNER_TEMP.
if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or $env:RUNNER_OS -cne 'Windows'){throw 'HOSTED_WINDOWS_TEST_ONLY'}
Import-Module (Join-Path $PSScriptRoot 'PortableRuntime.psm1') -Force
Assert-PortableLocalPath $RequestFile -MustExist
if(([IO.FileInfo]$RequestFile).Length -gt 16384){throw 'STAGE_REQUEST_SIZE'}
$request=[IO.File]::ReadAllText($RequestFile) | ConvertFrom-Json
$arguments=@{}
$keys=@('ArtifactRoot','StageRoot','UnifiedRoot','UnifiedSourceHead','UnifiedSourceTree','CatalogSha256','PreflightSha256','SourceGuardSha256','LibrarySha256','NativeJobSha256')
if(@($request.PSObject.Properties).Count -ne $keys.Count){throw 'EXACT_STAGE_REQUEST_REQUIRED'}
foreach($key in $keys){if($null -eq $request.PSObject.Properties[$key] -or $request.$key -isnot [string]){throw 'EXACT_STAGE_REQUEST_REQUIRED'};$arguments[$key]=$request.$key}
$stage=Join-Path $PSScriptRoot 'Stage-PortableWindowsRuntime.ps1'
if([IO.Directory]::Exists($arguments.StageRoot) -or [IO.File]::Exists($arguments.StageRoot)){throw 'FRESH_STAGE_REQUIRED'}
$prepared= & $stage @arguments -Mode Prepare | ConvertFrom-Json
if($prepared.result -cne 'PREPARED_INPUTS_ONLY' -or $prepared.native_execution -cne 'NOT_RUN' -or $prepared.installation_closure -ne $false -or [IO.Directory]::Exists($arguments.StageRoot)){throw 'PREPARE_EFFECT_OR_CONTRACT_FAILURE'}
$smoke= & $stage @arguments -Mode EphemeralCI -AuthorizeEphemeralWindowsCI | ConvertFrom-Json
if($smoke.result -cne 'PASS_COMPONENT_SDK_SMOKE_ONLY' -or $smoke.installation_closure -ne $false -or $smoke.physical_deployment_allowed -ne $false -or $smoke.global_status -cne 'NO_GO' -or $smoke.services -cne 'NOT_INSTALLED' -or $smoke.physical -cne 'NOT_RUN' -or !$smoke.postgresql.stopped){throw 'COMPONENT_SMOKE_CONTRACT_FAILURE'}
$smoke | ConvertTo-Json -Depth 14 -Compress
