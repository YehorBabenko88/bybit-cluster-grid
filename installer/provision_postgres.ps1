param(
 [Parameter(Mandatory=$true)][string]$DiscoveryPath,
 [Parameter(Mandatory=$true)][string]$DataRoot
)
$ErrorActionPreference="Stop"
$d=Get-Content $DiscoveryPath -Raw | ConvertFrom-Json
$EnvFile=Join-Path $DataRoot ".env"

# Safe rule: detect existing PostgreSQL, but never change its version, service, cluster,
# authentication or unrelated databases automatically.
$psql=(Get-Command psql.exe -ErrorAction SilentlyContinue).Source
if(!$psql){
    foreach($p in $d.postgres){
        if($p.bin -and (Test-Path (Join-Path $p.bin "psql.exe"))){$psql=Join-Path $p.bin "psql.exe";break}
    }
}
if(!$psql){
    $BundledInstaller=Join-Path $PSScriptRoot "postgres-installer.exe"
    if(Test-Path $BundledInstaller){
        throw "Bundled PostgreSQL unattended installation requires explicit packaged credentials/config and is not enabled yet."
    }
    throw "PostgreSQL not found. Provide the approved PostgreSQL installer in the deployment bundle."
}

# Do not guess administrator passwords. If GRID_POSTGRES_DSN was pre-enrolled, use it.
$existing=[Environment]::GetEnvironmentVariable("GRID_POSTGRES_DSN","Machine")
if($existing){
    Add-Content -Encoding UTF8 $EnvFile "POSTGRES_DSN=$existing"
    exit 0
}
throw "PostgreSQL detected, but Grid DB credentials are not provisioned. Enrollment must provide a Grid-owned DSN."
