[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$ReleaseManifestSha256,
 [Parameter(Mandatory=$true)][string]$OutputPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
# Mission4 preparation ONLY. No host lookup, connection, inventory collection,
# service/registry calls, installation, update, or remote command is performed.
if ($ReleaseManifestSha256 -cnotmatch '^[0-9a-f]{64}$') {throw 'Exact reviewed release manifest SHA256 required'}
if (Test-Path -LiteralPath $OutputPath) {throw 'New preparation document required'}
$plan=[ordered]@{
 schema='unified.adminit.acceptance-plan.v1'
 mode='PREPARE_ONLY'
 target_host='ADMINIT'
 release_manifest_sha256=$ReleaseManifestSha256
 owner_grant=$null
 execution_authorized=$false
 physical_acceptance='NOT_RUN'
 execution_scope='historical_training_oos_public_paper_only'
 trading_authorized=$false
 inventory_required=@('exact_host_identity','existing_services_readonly','os_and_powershell_versions','trusted_python_node_git','postgresql_data_ownership','independent_publisher_pin','protected_paths_acl','free_disk','backup_restore_proof','network_policy','functional_six_module_health')
 prerequisites=@('cloud_source_tests_complete','native_windows_evidence','signed_immutable_release','owner_exact_host_release_scope_grant_after_cloud_completion')
}
$json=$plan | ConvertTo-Json -Depth 6
$stream=[IO.File]::Open($OutputPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try {
 $bytes=(New-Object Text.UTF8Encoding($false)).GetBytes($json)
 $stream.Write($bytes,0,$bytes.Length)
} finally {$stream.Dispose()}
Write-Output 'PREPARED_ACCEPTANCE_PLAN_ONLY; ADMINIT_CONNECTIONS=NONE; physical=NOT_AUTHORIZED'
