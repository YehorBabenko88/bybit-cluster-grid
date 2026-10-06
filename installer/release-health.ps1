param(
 [Parameter(Mandatory=$true)][string]$InstallRoot,
 [Parameter(Mandatory=$true)][ValidateSet("AfterExit")][string]$Phase,
 [Parameter(Mandatory=$true)][string]$Version,
 [int]$RuntimeSeconds=0,
 [int]$ExitCode=0
)
$ErrorActionPreference="Stop"
$Pending=Join-Path $InstallRoot "pending.version"
$CrashFile=Join-Path $InstallRoot "pending-crashes.txt"
if(!(Test-Path $Pending)){exit 0}
$pv=(Get-Content $Pending -Raw).Trim()
if(!$pv -or $pv -ne $Version){exit 0}
if($RuntimeSeconds -ge 60){
  Remove-Item $Pending,$CrashFile -Force -ErrorAction SilentlyContinue
  exit 0
}
$count=0
if(Test-Path $CrashFile){[void][int]::TryParse((Get-Content $CrashFile -Raw).Trim(),[ref]$count)}
$count++
$tmp=$CrashFile+".tmp"
[System.IO.File]::WriteAllText($tmp,[string]$count,[System.Text.Encoding]::ASCII)
Move-Item $tmp $CrashFile -Force
if($count -lt 3){exit 0}
$Previous=Join-Path $InstallRoot "previous.version"
if(!(Test-Path $Previous)){exit 0}
$prev=(Get-Content $Previous -Raw).Trim()
if(!$prev -or $prev -eq $Version){exit 0}
$candidate=Join-Path (Join-Path $InstallRoot "releases") $prev
if(!(Test-Path $candidate)){exit 0}
$current=Join-Path $InstallRoot "current.version"
$tmpCurrent=$current+".tmp"
[System.IO.File]::WriteAllText($tmpCurrent,$prev,[System.Text.Encoding]::UTF8)
Move-Item $tmpCurrent $current -Force
Remove-Item $Pending,$CrashFile -Force -ErrorAction SilentlyContinue
exit 75
