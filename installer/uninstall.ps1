#Requires -RunAsAdministrator
param([switch]$PurgeData)
$ErrorActionPreference="Stop"
$TaskName="BybitClusterGridAgent"
$InstallRoot="$env:ProgramFiles\BybitClusterGrid"
$DataRoot="$env:ProgramData\BybitClusterGrid"
$Manifest=Join-Path $DataRoot "postgres-owned.json"

Stop-ScheduledTask $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask $TaskName -Confirm:$false -ErrorAction SilentlyContinue

if($PurgeData -and (Test-Path $Manifest)){
    try {
        $m=Get-Content $Manifest -Raw | ConvertFrom-Json
        $safeRoot=[IO.Path]::GetFullPath($DataRoot).TrimEnd('\')+'\'
        $pgRoot=[IO.Path]::GetFullPath([string]$m.root)
        $pgData=[IO.Path]::GetFullPath([string]$m.data)
        $valid=($m.owned_by_grid -eq $true) -and
               ([string]$m.service_name -eq "BybitClusterGridPostgres") -and
               ([int]$m.port -eq 55432) -and
               $pgRoot.StartsWith($safeRoot,[StringComparison]::OrdinalIgnoreCase) -and
               $pgData.StartsWith($safeRoot,[StringComparison]::OrdinalIgnoreCase)
        if(!$valid){throw "Grid PostgreSQL ownership manifest failed safety validation"}

        $svc=Get-Service -Name $m.service_name -ErrorAction SilentlyContinue
        if($svc){
            Stop-Service -Name $m.service_name -Force -ErrorAction SilentlyContinue
            & sc.exe delete $m.service_name | Out-Null
        }
    } catch {
        Write-Error "Refusing PostgreSQL purge: $($_.Exception.Message)"
        exit 20
    }
}

Remove-Item -Recurse -Force $InstallRoot -ErrorAction SilentlyContinue

if($PurgeData){
    # Re-validate that the target is exactly our fixed ProgramData child before recursive removal.
    $expected=[IO.Path]::GetFullPath((Join-Path $env:ProgramData "BybitClusterGrid")).TrimEnd('\')
    $actual=[IO.Path]::GetFullPath($DataRoot).TrimEnd('\')
    if($actual -ne $expected){throw "Unsafe Grid data root"}
    Remove-Item -Recurse -Force $DataRoot -ErrorAction SilentlyContinue
    Write-Host "Grid agent and Grid-owned data removed."
} else {
    Write-Host "Grid agent removed; Grid data preserved."
}
