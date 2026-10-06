param(
 [Parameter(Mandatory=$true)][string]$DiscoveryPath,
 [Parameter(Mandatory=$true)][string]$DataRoot
)
$ErrorActionPreference="Stop"
$d=Get-Content $DiscoveryPath -Raw | ConvertFrom-Json
$EnvFile=Join-Path $DataRoot ".env"
$Manifest=Join-Path $DataRoot "postgres-owned.json"

function Get-EnvValue([string]$Path,[string]$Name){
    if(!(Test-Path $Path)){return $null}
    $line=Get-Content $Path | Where-Object {$_ -match ("^"+[regex]::Escape($Name)+"=")} | Select-Object -Last 1
    if(!$line){return $null}
    return $line.Substring($Name.Length+1)
}
function Add-EnvOnce([string]$Name,[string]$Value){
    $existing=Get-EnvValue $EnvFile $Name
    if($existing){return}
    Add-Content -Encoding UTF8 $EnvFile "$Name=$Value"
}

# First priority: an instance previously created by this Grid installation.
if(Test-Path $Manifest){
    $m=Get-Content $Manifest -Raw | ConvertFrom-Json
    $safe=[IO.Path]::GetFullPath($DataRoot).TrimEnd('\')+'\'
    $root=[IO.Path]::GetFullPath([string]$m.root)
    $valid=($m.owned_by_grid -eq $true) -and
           ([string]$m.service_name -eq "BybitClusterGridPostgres") -and
           ([int]$m.port -eq 55432) -and
           $root.StartsWith($safe,[StringComparison]::OrdinalIgnoreCase)
    if(!$valid){throw "Existing Grid PostgreSQL ownership manifest is invalid; refusing repair"}
    $dsn=Get-EnvValue $EnvFile "POSTGRES_DSN"
    if(!$dsn){throw "Grid PostgreSQL exists but its DSN is missing; refusing to rotate credentials automatically"}
    $svc=Get-Service -Name $m.service_name -ErrorAction SilentlyContinue
    if($svc -and $svc.Status -ne "Running"){Start-Service -Name $m.service_name}
    Write-Host "Reusing Grid-owned PostgreSQL instance."
    exit 0
}

# Recover a power loss after the Grid PostgreSQL installer created its
# dedicated service/data tree but before postgres-owned.json was published.
# Adoption is intentionally strict so unrelated PostgreSQL is never claimed.
$PartialRoot=Join-Path $DataRoot "postgres"
$PartialData=Join-Path $PartialRoot "data"
$PartialPsql=Join-Path $PartialRoot "bin\psql.exe"
$PartialConf=Join-Path $PartialData "postgresql.conf"
$PartialSvc=Get-Service -Name "BybitClusterGridPostgres" -ErrorAction SilentlyContinue
if(!(Test-Path $Manifest) -and $PartialSvc -and (Test-Path $PartialPsql) -and (Test-Path $PartialConf)){
    $confText=Get-Content $PartialConf -Raw
    if($confText -match '(?m)^\s*port\s*=\s*55432\s*(?:#.*)?
if($existing){
    Add-EnvOnce "POSTGRES_DSN" $existing
    Write-Host "Using pre-provisioned GRID_POSTGRES_DSN."
    exit 0
}

$psql=(Get-Command psql.exe -ErrorAction SilentlyContinue).Source
if(!$psql){
    foreach($p in $d.postgres){
        if($p.bin -and (Test-Path (Join-Path $p.bin "psql.exe"))){$psql=Join-Path $p.bin "psql.exe";break}
    }
}
if($psql){
    throw "Unrelated PostgreSQL exists but no Grid DSN is provisioned. Refusing to modify it automatically."
}

$Installer=Join-Path $PSScriptRoot "postgres-installer.exe"
if(!(Test-Path $Installer)){
    throw "PostgreSQL is absent and approved postgres-installer.exe is not included in the deployment bundle."
}

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
Add-EnvOnce "POSTGRES_DSN" "postgresql://cluster_grid:$DbPass@127.0.0.1:55432/bybit_cluster_grid"
){
        $dsn=Get-EnvValue $EnvFile "POSTGRES_DSN"
        if(!$dsn){
            throw "Interrupted Grid PostgreSQL install detected before database credentials were committed; safe automatic credential recovery is unavailable."
        }
        $manifest=[ordered]@{
          schema=1; owned_by_grid=$true; instance_id=[guid]::NewGuid().ToString()
          service_name="BybitClusterGridPostgres"; port=55432
          root=$PartialRoot; data=$PartialData
          recovered_at=(Get-Date).ToUniversalTime().ToString("o")
        }
        $manifest | ConvertTo-Json | Set-Content -Encoding UTF8 $Manifest
        if($PartialSvc.Status -ne "Running"){Start-Service $PartialSvc.Name}
        Write-Host "Recovered interrupted Grid-owned PostgreSQL ownership manifest."
        exit 0
    }
}

# A deliberately pre-provisioned Grid DSN also wins and is never modified.
$existing=[Environment]::GetEnvironmentVariable("GRID_POSTGRES_DSN","Machine")
if($existing){
    Add-EnvOnce "POSTGRES_DSN" $existing
    Write-Host "Using pre-provisioned GRID_POSTGRES_DSN."
    exit 0
}

$psql=(Get-Command psql.exe -ErrorAction SilentlyContinue).Source
if(!$psql){
    foreach($p in $d.postgres){
        if($p.bin -and (Test-Path (Join-Path $p.bin "psql.exe"))){$psql=Join-Path $p.bin "psql.exe";break}
    }
}
if($psql){
    throw "Unrelated PostgreSQL exists but no Grid DSN is provisioned. Refusing to modify it automatically."
}

$Installer=Join-Path $PSScriptRoot "postgres-installer.exe"
if(!(Test-Path $Installer)){
    throw "PostgreSQL is absent and approved postgres-installer.exe is not included in the deployment bundle."
}

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
Add-EnvOnce "POSTGRES_DSN" "postgresql://cluster_grid:$DbPass@127.0.0.1:55432/bybit_cluster_grid"
