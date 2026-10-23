#Requires -Version 5.1
[CmdletBinding()]
param([switch]$Apply,[switch]$Rollback)
$ErrorActionPreference='Stop'
if($Apply -and $Rollback){throw 'MODES_EXCLUSIVE'}
if($Apply){throw 'EXECUTE_NOT_AUTHORIZED: native custody executor is not proven'}
if($Rollback){throw 'ROLLBACK_NOT_AUTHORIZED: original ACL may reintroduce P0 exposure'}
[pscustomobject]@{mode='PlanOnly';status='BLOCKED';host_verified=$false;execute_authorized=$false;
 cleanup_authorized=$false;deployment_authorized=$false;physical_pc4='0/10 NOT_RUN';
 next_step='Use pure snapshot model from independently protected checkout; no host observations'}
