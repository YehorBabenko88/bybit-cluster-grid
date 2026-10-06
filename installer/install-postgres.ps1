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

# Bound disk growth for the Grid-owned instance only. External PostgreSQL is
# deliberately never modified by this installer.
$Conf=Join-Path $PgData "postgresql.conf"
if(!(Test-Path $Conf)){throw "Grid PostgreSQL configuration not found after install"}
Add-Content -Encoding ascii $Conf @"

# BybitClusterGrid managed durability / disk bounds
max_wal_size = '2GB'
min_wal_size = '256MB'
checkpoint_timeout = '10min'
checkpoint_completion_target = 0.9
logging_collector = on
log_destination = 'stderr'
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d.log'
log_rotation_age = 1d
log_rotation_size = 100MB
log_truncate_on_rotation = on
"@
Restart-Service -Name $ServiceName -Force
$svc=Get-Service -Name $ServiceName
$svc.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Running,[TimeSpan]::FromSeconds(60))

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
Remove-Item $Installing -Force -ErrorAction SilentlyContinue
