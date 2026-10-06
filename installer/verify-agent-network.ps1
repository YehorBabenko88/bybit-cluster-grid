#Requires -RunAsAdministrator
param([Parameter(Mandatory=$true)][string]$CoordinatorUrl)
$ErrorActionPreference="Stop"
try{$uri=[Uri]$CoordinatorUrl}catch{throw "Invalid CoordinatorUrl: $CoordinatorUrl"}
if($uri.Scheme -notin @("http","https")){throw "CoordinatorUrl must use http or https"}
$hostName=$uri.Host
$port=if($uri.IsDefaultPort){if($uri.Scheme -eq "https"){443}else{80}}else{$uri.Port}
$ts=Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
if(!(Test-Path $ts)){throw "Tailscale client is missing"}
$status=& $ts status --json 2>$null
if($LASTEXITCODE -ne 0 -or !$status){throw "Tailscale status unavailable"}
try{$state=[string](($status|ConvertFrom-Json).BackendState)}catch{$state=""}
if($state -ne "Running"){throw "Tailscale is not Running"}
$eset=@(Get-Service -ErrorAction SilentlyContinue | Where-Object {$_.Name -match '^(ekrn|epfw|eraagent)' -or $_.DisplayName -match 'ESET'} | Select-Object -ExpandProperty Name)
if($eset.Count -gt 0){Write-Host ("ESET detected: "+($eset -join ", "))}
$tcp=Test-NetConnection $hostName -Port $port -WarningAction SilentlyContinue
if(!$tcp.TcpTestSucceeded){
    $hint="Grid cannot reach CONTROL at "+$hostName+":"+$port+"."
    if($eset.Count -gt 0){$hint+=" ESET is active; verify its firewall policy permits this outbound TCP path. Do not disable ESET."}
    $hint+=" Also verify the tailnet tag policy allows grid nodes to reach Grid CONTROL on this port."
    throw $hint
}
try{
    $health=Invoke-RestMethod -Uri ($CoordinatorUrl.TrimEnd('/')+"/health") -TimeoutSec 10
    if($health.ok -ne $true){throw "health returned ok=false"}
}catch{throw "TCP to CONTROL works, but Grid /health failed: $($_.Exception.Message)"}
Write-Host "Grid network preflight OK: Tailscale running, CONTROL TCP reachable, /health healthy."
