param(
 [Parameter(Mandatory=$true)][string]$DataRoot,
 [switch]$Apply,
 [switch]$Restart
)
$ErrorActionPreference="Stop"
$Manifest=Join-Path $DataRoot "postgres-owned.json"
if($Restart -and !$Apply){throw 'Restart requires explicit Apply'}
if(!(Test-Path -LiteralPath $Manifest -PathType Leaf)){throw 'Grid PostgreSQL ownership manifest missing'}
$m=Get-Content $Manifest -Raw | ConvertFrom-Json
$expectedRoot=[IO.Path]::GetFullPath((Join-Path $DataRoot 'postgres')).TrimEnd('\')
$expectedData=Join-Path $expectedRoot 'data'
$root=[IO.Path]::GetFullPath([string]$m.root)
if($m.owned_by_grid -isnot [bool] -or !$m.owned_by_grid -or [string]$m.service_name -ne "BybitClusterGridPostgres" -or
   [int]$m.port -ne 55432 -or $root.TrimEnd('\') -ine $expectedRoot -or
   [IO.Path]::GetFullPath([string]$m.data).TrimEnd('\') -ine $expectedData){
    throw "Refusing PostgreSQL config update: invalid ownership manifest"
}
$conf=Join-Path ([string]$m.data) "postgresql.conf"
if(!(Test-Path -LiteralPath $conf -PathType Leaf)){throw "Grid PostgreSQL configuration missing"}
foreach($path in @($conf,$Manifest)){
 $cursor=[IO.Path]::GetFullPath($path)
 while($cursor){
  if((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Grid PostgreSQL path traverses a reparse point'}
  $parent=[IO.Directory]::GetParent($cursor)
  if($null -eq $parent){break};$cursor=$parent.FullName
 }
}
if($Restart){
 $service=Get-CimInstance Win32_Service -Filter "Name='BybitClusterGridPostgres'" -ErrorAction Stop
 $image='^\s*"?'+[regex]::Escape((Join-Path $expectedRoot 'bin\'))+'(pg_ctl|postgres)\.exe"?(?=\s|$)'
 $dataArg='(?:^|\s)-D\s+(?:"'+[regex]::Escape($expectedData)+'"|'+[regex]::Escape($expectedData)+'(?=\s|$))'
 if(!$service -or $service.PathName -notmatch $image -or $service.PathName -notmatch $dataArg){
  throw 'Grid PostgreSQL service ownership could not be verified; restart refused'
 }
}
$mutex=[Threading.Mutex]::new($false,'Global\BybitClusterGridPostgresConfig')
$held=$false
try {
 try {$held=$mutex.WaitOne(0)} catch [Threading.AbandonedMutexException] {$held=$true}
 if(!$held){throw 'Another Grid PostgreSQL config operation is running'}
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
$original=Get-Content -LiteralPath $conf -Raw
$text=$original
$pattern='(?s)'+[regex]::Escape($begin)+'.*?'+[regex]::Escape($end)
if($text -match $pattern){$text=[regex]::Replace($text,$pattern,[System.Text.RegularExpressions.MatchEvaluator]{param($x)$block})}
else{$text=$text.TrimEnd()+"`r`n`r`n"+$block+"`r`n"}
if($text -ceq $original){Write-Output 'POSTGRES_CONFIG_ALREADY_CURRENT';return}
if(!$Apply){Write-Output 'POSTGRES_CONFIG_PLAN_ONLY; restart=false';return}
$tmp=$conf+'.'+[guid]::NewGuid().ToString('N')+'.tmp'
$backup=$conf+'.grid-backup-'+[guid]::NewGuid().ToString('N')
$bytes=[Text.UTF8Encoding]::new($false).GetBytes($text)
$stream=[IO.File]::Open($tmp,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try {$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)} finally {$stream.Dispose()}
[IO.File]::Replace($tmp,$conf,$backup,$true)
Write-Output 'POSTGRES_CONFIG_APPLIED; previous configuration preserved'
if($Restart){
 Restart-Service -Name ([string]$m.service_name) -Force
 $svc=Get-Service -Name ([string]$m.service_name)
 $svc.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Running,[TimeSpan]::FromSeconds(60))
}
} finally {if($held){$mutex.ReleaseMutex()};$mutex.Dispose()}
