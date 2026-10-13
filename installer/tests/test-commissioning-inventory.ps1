param([ValidateSet('all','markers','race')][string]$Scenario='all',[string]$CollectorPath='')
$ErrorActionPreference='Stop'
$root=Join-Path ([IO.Path]::GetTempPath()) ('grid-inventory-test-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($root)
$collector=Join-Path $PSScriptRoot '..\collect-commissioning-inventory.ps1'
if($CollectorPath){$collector=$CollectorPath}
# Synthetic providers only: no live Windows process/task/service inventory.
function Get-CimInstance { [CmdletBinding()]param([string]$ClassName) @() }
function Get-ScheduledTask { [CmdletBinding()]param() @() }
function Get-PSDrive { [CmdletBinding()]param([string]$Name,[string]$PSProvider) @{Free=123;Used=456} }
if($Scenario -in @('all','markers')){
    [IO.File]::WriteAllText((Join-Path $root 'current.version'),('a'*40))
    [IO.File]::WriteAllText((Join-Path $root 'previous.version'),('b'*40))
    $report=(& $collector -GridRoot $root | Out-String | ConvertFrom-Json)
    if($report.grid_current_sha -cne ('a'*40) -or $report.grid_previous_sha -cne ('b'*40)){
        throw 'Installed .version release markers were not read correctly'
    }
}
if($Scenario -in @('all','race')){
    $global:GridAuditInventoryRaceTarget=Join-Path $root 'race.json'
    $global:GridAuditInventoryRaceInjected=$false
    function Test-Path {
        [CmdletBinding()]param([string]$LiteralPath,[string]$PathType)
        if($LiteralPath -eq $global:GridAuditInventoryRaceTarget -and -not $global:GridAuditInventoryRaceInjected){
            $global:GridAuditInventoryRaceInjected=$true
            [IO.File]::WriteAllText($global:GridAuditInventoryRaceTarget,'sentinel-owned-by-other-writer')
            return $false
        }
        Microsoft.PowerShell.Management\Test-Path @PSBoundParameters
    }
    $refused=$false
    try { & $collector -GridRoot $root -OutputPath $global:GridAuditInventoryRaceTarget | Out-Null }
    catch { $refused=$true }
    if(-not $global:GridAuditInventoryRaceInjected){throw 'Race injection did not execute'}
    if(-not $refused){throw 'Concurrent inventory output was not refused'}
    if([IO.File]::ReadAllText($global:GridAuditInventoryRaceTarget) -cne 'sentinel-owned-by-other-writer'){
        throw 'Concurrent inventory output was overwritten'
    }
}
Write-Output ('Synthetic commissioning inventory '+$Scenario+' passed')
