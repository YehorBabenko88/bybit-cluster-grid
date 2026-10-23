#Requires -Version 5.1
# Legacy resilience/blanket-rights utility is retired. No service or ACL effects.
param([string]$ServiceName="BybitClusterGrid",[string]$GridRoot="C:\ProgramData\BybitClusterGrid",[switch]$Apply)
$ErrorActionPreference='Stop'
if($Apply){throw 'LS5_ACL_EXECUTE_NOT_AUTHORIZED: use reviewed per-object remediation plan'}
Write-Output 'PLAN_ONLY; BLOCKED; service/ACL operations retired; Execute NOT_AUTHORIZED'
