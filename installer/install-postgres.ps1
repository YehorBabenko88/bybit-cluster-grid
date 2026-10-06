param(
 [Parameter(Mandatory=$true)][string]$Installer,
 [Parameter(Mandatory=$true)][string]$DataRoot,
 [Parameter(Mandatory=$true)][string]$SuperPassword
)
$ErrorActionPreference="Stop"
if(!(Test-Path $Installer)){throw "Approved PostgreSQL installer missing"}
$PgRoot=Join-Path $DataRoot "postgres"
$PgData=Join-Path $PgRoot "data"
$ServiceName="BybitClusterGridPostgres"
$Port=55432
$InstanceId=[guid]::NewGuid().ToString()
New-Item -ItemType Directory -Force -Path $PgRoot | Out-Null
$Installing=Join-Path $DataRoot "postgres-installing.json"
[ordered]@{
  schema=1; service_name=$ServiceName; port=$Port; root=$PgRoot; data=$PgData
  started_at=(Get-Date).ToUniversalTime().ToString("o")
} | ConvertTo-Json | Set-Content -Encoding UTF8 $Installing

$args=@(
 "--mode","unattended",
 "--unattendedmodeui","none",
 "--prefix",$PgRoot,
 "--datadir",$PgData,
 "--serverport","$Port",
 "--servicename",$ServiceName,
 "--superpassword",$SuperPassword
)
$p=Start-Process -FilePath $Installer -ArgumentList $args -Wait -PassThru
if($p.ExitCode -ne 0){throw "PostgreSQL installer failed: $($p.ExitCode)"}

$manifest=[ordered]@{
  schema=1
  owned_by_grid=$true
  instance_id=$InstanceId
  service_name=$ServiceName
  port=$Port
  root=$PgRoot
  data=$PgData
  created_at=(Get-Date).ToUniversalTime().ToString("o")
}
$manifest | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $DataRoot "postgres-owned.json")
# Keep postgres-installing.json until role/database credentials and POSTGRES_DSN
# are committed by provision_postgres.ps1.
