# Separate diagnostic, not part of the pinned physical SID/ACL package.
[CmdletBinding()]
param([switch]$CollectLocal)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$report = [ordered]@{
    schema = 'grid-lsa-readonly-1'; mode = 'PlanOnly'; readiness = 'BLOCKED'
    effective_rights = 'UNKNOWN'; execution_authorized = $false
    physical_tests = '0/10 NOT_RUN'; records = @(); errors = @()
    group_completeness = 'UNKNOWN'; actor_token_observed = $false
}
if (-not $CollectLocal) { $report | ConvertTo-Json -Depth 8; return }
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
    $PSVersionTable.PSVersion.Major -ne 5) { throw 'REQUIRES_WINDOWS_POWERSHELL_5_X64' }
# Compilation may write compiler temporaries; this is policy-read-only, NOT zero-write.
# Run only from a reviewed, locally protected source directory after owner approval.
Add-Type -Path (Join-Path $PSScriptRoot 'LsaRights.cs')
. (Join-Path $PSScriptRoot 'Inventory.ps1')
$report.mode = 'CollectLocalReadOnly'
$api = New-Object GridLab.LsaReadOnly.NativeApi
$denyRights = @('SeDenyBatchLogonRight','SeDenyInteractiveLogonRight',
    'SeDenyServiceLogonRight','SeDenyNetworkLogonRight','SeDenyRemoteInteractiveLogonRight')
$allowRights = @('SeBatchLogonRight','SeInteractiveLogonRight','SeServiceLogonRight',
    'SeNetworkLogonRight','SeRemoteInteractiveLogonRight')
$inventory = Get-LsaCandidateInventory -Users {
    @('GridLabCollector','GridLabStorage') | ForEach-Object { Get-LocalUser -Name $_ -ErrorAction Stop }
} -Groups { Get-LocalGroup -ErrorAction Stop } -Members {
    param($group)
    Get-LocalGroupMember -SID $group.SID -ErrorAction Stop
}
$candidates=$inventory.candidates
$report.errors=@($inventory.errors)
# Conditional SIDs are queried as candidates, never asserted to exist in a future token.
$known = [ordered]@{
    'S-1-1-0'='Everyone'; 'S-1-5-11'='AuthenticatedUsers'; 'S-1-5-113'='LocalAccount'
    'S-1-5-114'='LocalAccountAdmin'; 'S-1-5-32-545'='Users'; 'S-1-5-32-544'='Administrators'
    'S-1-5-2'='Network'; 'S-1-5-3'='Batch'; 'S-1-5-4'='Interactive'; 'S-1-5-6'='Service'
    'S-1-5-14'='RemoteInteractive'; 'S-1-5-15'='ThisOrganization'
    'S-1-2-0'='Local'; 'S-1-2-1'='ConsoleLogon'
}
foreach ($sid in $known.Keys) {
    if (-not $candidates.Contains($sid)) { $candidates[$sid]=@{alias=$known[$sid]; relation='CONDITIONAL_CANDIDATE'} }
}
foreach ($sid in $candidates.Keys) {
    $r = [GridLab.LsaReadOnly.Reader]::Read($api,$sid)
    $report.records += [ordered]@{
        principal=$candidates[$sid].alias; relation=$candidates[$sid].relation
        state=$r.State; code=$r.Code; ntstatus=('0x{0:X8}' -f $r.Status); win32=$r.Win32Error
        cleanup_failed=$r.CleanupFailed
        direct_allow=@($r.Rights | Where-Object { $_ -cin $allowRights })
        direct_deny=@($r.Rights | Where-Object { $_ -cin $denyRights })
    }
}
# No full SID, SDDL, exception text, password, or token is emitted.
$report | ConvertTo-Json -Depth 8
