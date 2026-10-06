param(
 [Parameter(Mandatory=$true)][string]$DataRoot
)
$ErrorActionPreference="Stop"
$Manifest=Join-Path $DataRoot "postgres-owned.json"
if(!(Test-Path $Manifest)){exit 0}
$m=Get-Content $Manifest -Raw | ConvertFrom-Json
$safe=[IO.Path]::GetFullPath($DataRoot).TrimEnd('\')+'\'
$root=[IO.Path]::GetFullPath([string]$m.root)
if($m.owned_by_grid -ne $true -or [string]$m.service_name -ne "BybitClusterGridPostgres" -or
   [int]$m.port -ne 55432 -or !$root.StartsWith($safe,[StringComparison]::OrdinalIgnoreCase)){
    throw "Refusing PostgreSQL config update: invalid ownership manifest"
}
$conf=Join-Path ([string]$m.data) "postgresql.conf"
if(!(Test-Path $conf)){throw "Grid PostgreSQL configuration missing"}
$begin="# BEGIN BybitClusterGrid managed"
$end="# END BybitClusterGrid managed"
$block=@"
$begin
max_wal_size = '2GB'
min_wal_size = '256MB'
checkpoint_timeout = '10min'
checkpoint_completion_target = 0.9
logging_collector = on
log_destination = 'stderr'
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M.log'
log_rotation_age = 1d
log_rotation_size = 100MB
log_truncate_on_rotation = off
$end
"@
$text=Get-Content $conf -Raw
$pattern='(?s)'+[regex]::Escape($begin)+'.*?'+[regex]::Escape($end)
if($text -match $pattern){$text=[regex]::Replace($text,$pattern,[System.Text.RegularExpressions.MatchEvaluator]{param($x)$block})}
else{$text=$text.TrimEnd()+"`r`n`r`n"+$block+"`r`n"}
$tmp=$conf+".grid.tmp"
[IO.File]::WriteAllText($tmp,$text,[Text.Encoding]::UTF8)
Move-Item $tmp $conf -Force
Restart-Service -Name ([string]$m.service_name) -Force
$svc=Get-Service -Name ([string]$m.service_name)
$svc.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Running,[TimeSpan]::FromSeconds(60))
