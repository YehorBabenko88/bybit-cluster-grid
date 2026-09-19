param(
 [Parameter(Mandatory=$true)][string]$DiscoveryPath,
 [Parameter(Mandatory=$true)][string]$DataRoot
)
$ErrorActionPreference="Stop"
$d=Get-Content $DiscoveryPath -Raw | ConvertFrom-Json
$EnvFile=Join-Path $DataRoot ".env"

# A pre-provisioned Grid DSN always wins.
$existing=[Environment]::GetEnvironmentVariable("GRID_POSTGRES_DSN","Machine")
if($existing){
    Add-Content -Encoding UTF8 $EnvFile "POSTGRES_DSN=$existing"
    exit 0
}

$psql=(Get-Command psql.exe -ErrorAction SilentlyContinue).Source
if(!$psql){
    foreach($p in $d.postgres){
        if($p.bin -and (Test-Path (Join-Path $p.bin "psql.exe"))){$psql=Join-Path $p.bin "psql.exe";break}
    }
}

if($psql){
    # We intentionally do not guess or alter credentials of an unrelated server.
    throw "PostgreSQL exists but no Grid-owned DSN is provisioned. Refusing to modify the existing server automatically."
}

$Installer=Join-Path $PSScriptRoot "postgres-installer.exe"
if(!(Test-Path $Installer)){
    throw "PostgreSQL is absent and approved postgres-installer.exe is not included in the deployment bundle."
}

# Generate credentials only for the isolated Grid-owned PostgreSQL instance.
$bytes=New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$Super=[Convert]::ToBase64String($bytes).Replace("/","_").Replace("+","-").TrimEnd("=")
& (Join-Path $PSScriptRoot "install-postgres.ps1") -Installer $Installer -DataRoot $DataRoot -SuperPassword $Super

$PsqlLocal=Join-Path $DataRoot "postgres\bin\psql.exe"
if(!(Test-Path $PsqlLocal)){throw "Grid PostgreSQL installed but psql.exe not found"}
$env:PGPASSWORD=$Super
$DbPassBytes=New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($DbPassBytes)
$DbPass=[Convert]::ToBase64String($DbPassBytes).Replace("/","_").Replace("+","-").TrimEnd("=")

& $PsqlLocal -h 127.0.0.1 -p 55432 -U postgres -d postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE cluster_grid LOGIN PASSWORD '$DbPass';"
if($LASTEXITCODE -ne 0){throw "Failed creating Grid PostgreSQL role"}
& $PsqlLocal -h 127.0.0.1 -p 55432 -U postgres -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE bybit_cluster_grid OWNER cluster_grid;"
if($LASTEXITCODE -ne 0){throw "Failed creating Grid PostgreSQL database"}
Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
Add-Content -Encoding UTF8 $EnvFile "POSTGRES_DSN=postgresql://cluster_grid:$DbPass@127.0.0.1:55432/bybit_cluster_grid"
