param(
 [Parameter(Mandatory=$true)][string]$InstallRoot,
 [Parameter(Mandatory=$true)][ValidateSet("ConfirmRunning","AfterExit")][string]$Phase,
 [Parameter(Mandatory=$true)][string]$Version,
 [int]$ProcessId=0,
 [int]$RuntimeSeconds=0,
 [int]$ExitCode=0
)
$ErrorActionPreference="Stop"
$Pending=Join-Path $InstallRoot "pending.version"
$CrashFile=Join-Path $InstallRoot "pending-crashes.txt"

function PendingMatches {
  if(!(Test-Path $Pending)){return $false}
  $pv=(Get-Content $Pending -Raw).Trim()
  return [bool]($pv -and $pv -eq $Version)
}
function Write-AtomicText([string]$Path,[string]$Value){
  $tmp=$Path+".tmp"
  $fs=[IO.File]::Open($tmp,[IO.FileMode]::Create,[IO.FileAccess]::Write,[IO.FileShare]::None)
  try{
    $bytes=[Text.Encoding]::UTF8.GetBytes($Value)
    $fs.Write($bytes,0,$bytes.Length)
    $fs.Flush($true)
  }finally{$fs.Dispose()}
  Move-Item $tmp $Path -Force
}
if(!(PendingMatches)){exit 0}

if($Phase -eq "ConfirmRunning"){
  if($ProcessId -le 0){exit 0}
  Start-Sleep -Seconds 60
  if(!(PendingMatches)){exit 0}
  $p=Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if($p){
    # The exact process launched for this pending release survived the
    # stabilization window. Publish health by clearing pending state.
    Remove-Item $Pending,$CrashFile -Force -ErrorAction SilentlyContinue
  }
  exit 0
}

# AfterExit: only exits inside the stabilization window count toward rollback.
# A process that had already survived 60s should normally have been confirmed
# by ConfirmRunning; tolerate timer scheduling delay without calling it a crash.
if($RuntimeSeconds -ge 60){exit 0}
$count=0
if(Test-Path $CrashFile){[void][int]::TryParse((Get-Content $CrashFile -Raw).Trim(),[ref]$count)}
$count++
Write-AtomicText $CrashFile ([string]$count)
if($count -lt 3){exit 0}

$Previous=Join-Path $InstallRoot "previous.version"
if(!(Test-Path $Previous)){exit 0}
$prev=(Get-Content $Previous -Raw).Trim()
if(!$prev -or $prev -eq $Version){exit 0}
$candidate=Join-Path (Join-Path $InstallRoot "releases") $prev
if(!(Test-Path $candidate)){exit 0}
$current=Join-Path $InstallRoot "current.version"
Write-AtomicText $current $prev
Remove-Item $Pending,$CrashFile -Force -ErrorAction SilentlyContinue
exit 75
