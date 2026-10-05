param(
 [Parameter(Mandatory=$true)][string]$DataRoot,
 [int]$TimeoutSeconds=120
)
$ErrorActionPreference="Stop"
$Manifest=Join-Path $DataRoot "postgres-owned.json"
if(!(Test-Path $Manifest)){exit 0}
$m=Get-Content $Manifest -Raw | ConvertFrom-Json
if($m.owned_by_grid -ne $true -or [string]$m.service_name -ne "BybitClusterGridPostgres"){
    throw "Invalid Grid PostgreSQL ownership manifest during cold boot"
}
$svc=Get-Service -Name ([string]$m.service_name) -ErrorAction SilentlyContinue
if(!$svc){throw "Grid-owned PostgreSQL service is missing"}
if($svc.Status -ne "Running"){Start-Service -Name $svc.Name}
$deadline=(Get-Date).AddSeconds([Math]::Max(10,$TimeoutSeconds))
do {
    $svc.Refresh()
    if($svc.Status -eq "Running"){
        Write-Host "Grid-owned PostgreSQL service is running."
        exit 0
    }
    Start-Sleep -Seconds 2
} while((Get-Date) -lt $deadline)
throw "Grid-owned PostgreSQL did not reach Running state before cold-boot timeout"
