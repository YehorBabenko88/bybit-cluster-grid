#Requires -Version 5.1
[CmdletBinding()]
param(
 [ValidateSet('PlanOnly')][string]$Mode='PlanOnly',
 [Parameter(Mandatory=$true)][string]$EvidencePath,
 [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ReviewedVersion,
 [Parameter(Mandatory=$true)][string]$Python,
 [ValidateSet('json','markdown')][string]$Format='json'
)
$ErrorActionPreference='Stop'
# Trusted local planner only. No target-release code, remote processes or Apply mode.
& $Python -B (Join-Path $PSScriptRoot 'physical_deployment_harness.py') --evidence $EvidencePath --commit $ReviewedVersion --format $Format
if($LASTEXITCODE -ne 0){throw 'PHYSICAL_PLAN_BLOCKED'}
