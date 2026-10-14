param([string]$ScriptPath=(Join-Path $PSScriptRoot '..\configure-postgres.ps1'))
$ErrorActionPreference='Stop'
$root=Join-Path ([IO.Path]::GetTempPath()) ('grid-pg-config-'+[guid]::NewGuid().ToString('N'))
$owned=Join-Path $root 'owned'
$pg=Join-Path $owned 'postgres'
$data=Join-Path $pg 'data'
$foreign=Join-Path $root 'foreign'
[void][IO.Directory]::CreateDirectory($data)
[void][IO.Directory]::CreateDirectory($foreign)
$foreignConf=Join-Path $foreign 'postgresql.conf'
$conf=Join-Path $data 'postgresql.conf'
[IO.File]::WriteAllText($foreignConf,'FOREIGN_UNCHANGED')
[IO.File]::WriteAllText($conf,'port=55432')
$global:GridConfigRestarts=0
function Restart-Service { param($Name,[switch]$Force) $global:GridConfigRestarts++ }
function Get-Service { param($Name) [pscustomobject]@{WaitForStatus={}} }
function Write-Manifest($dataPath){
 @{schema=1;owned_by_grid=$true;service_name='BybitClusterGridPostgres';port=55432;root=$pg;data=$dataPath} |
 ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $owned 'postgres-owned.json')
}
Write-Manifest $foreign
$rejected=$false
try { & $ScriptPath -DataRoot $owned } catch { $rejected=$true }
if(!$rejected -or [IO.File]::ReadAllText($foreignConf) -ne 'FOREIGN_UNCHANGED') {throw 'Foreign PostgreSQL path was not rejected before mutation'}
Write-Manifest $data
$before=[IO.File]::ReadAllText($conf)
& $ScriptPath -DataRoot $owned
if([IO.File]::ReadAllText($conf) -ne $before -or $global:GridConfigRestarts -ne 0){throw 'Default config check mutated state'}
& $ScriptPath -DataRoot $owned -Apply
$after=[IO.File]::ReadAllText($conf)
if($after -eq $before -or $global:GridConfigRestarts -ne 0){throw 'Explicit apply did not preserve restart gate'}
$stamp=(Get-Item -LiteralPath $conf).LastWriteTimeUtc.Ticks
& $ScriptPath -DataRoot $owned -Apply
if((Get-Item -LiteralPath $conf).LastWriteTimeUtc.Ticks -ne $stamp){throw 'Idempotent config apply rewrote file'}
function Get-CimInstance {[CmdletBinding()]param($ClassName,$Filter) [pscustomobject]@{PathName='C:\foreign\pg_ctl.exe -D C:\foreign'}}
$rejected=$false
try {& $ScriptPath -DataRoot $owned -Apply -Restart} catch {$rejected=$true}
if(!$rejected -or $global:GridConfigRestarts -ne 0){throw 'Foreign service image was not rejected'}
$jOwned=Join-Path $root 'junction-owned'
$jPg=Join-Path $jOwned 'postgres'
[void][IO.Directory]::CreateDirectory($jPg)
New-Item -ItemType Junction -Path (Join-Path $jPg 'data') -Target $foreign | Out-Null
@{schema=1;owned_by_grid=$true;service_name='BybitClusterGridPostgres';port=55432;root=$jPg;data=(Join-Path $jPg 'data')} |
 ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $jOwned 'postgres-owned.json')
$rejected=$false
try {& $ScriptPath -DataRoot $jOwned -Apply} catch {$rejected=$true}
if(!$rejected -or [IO.File]::ReadAllText($foreignConf) -ne 'FOREIGN_UNCHANGED'){throw 'Junction path was not rejected before mutation'}
Write-Output 'Safe PostgreSQL configuration fixture passed; no real services queried'
