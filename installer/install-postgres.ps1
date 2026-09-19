param(
 [Parameter(Mandatory=$true)][string]$Installer,
 [Parameter(Mandatory=$true)][string]$DataRoot,
 [Parameter(Mandatory=$true)][string]$SuperPassword
)
$ErrorActionPreference="Stop"
if(!(Test-Path $Installer)){throw "Approved PostgreSQL installer missing"}
$PgRoot=Join-Path $DataRoot "postgres"
$PgData=Join-Path $PgRoot "data"
New-Item -ItemType Directory -Force -Path $PgRoot | Out-Null

# EnterpriseDB Windows installer unattended arguments. Keep this Grid-owned instance isolated.
$args=@(
 "--mode","unattended",
 "--unattendedmodeui","none",
 "--prefix",$PgRoot,
 "--datadir",$PgData,
 "--serverport","55432",
 "--superpassword",$SuperPassword
)
$p=Start-Process -FilePath $Installer -ArgumentList $args -Wait -PassThru
if($p.ExitCode -ne 0){throw "PostgreSQL installer failed: $($p.ExitCode)"}
