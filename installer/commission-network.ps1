#Requires -Version 5.1
param(
  [int]$ExpectedOnlinePeers=2,
  [int[]]$TcpPorts=@(),
  [string]$OutFile=""
)
$ErrorActionPreference="Stop"

$ts=Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
if(!(Test-Path $ts)){ throw "Tailscale CLI not found: $ts" }

$raw=& $ts status --json
if($LASTEXITCODE -ne 0 -or !$raw){ throw "tailscale status --json failed" }
$status=$raw | ConvertFrom-Json
if([string]$status.BackendState -ne "Running"){ throw "Tailscale backend is not Running" }

$selfName=[string]$status.Self.HostName
$selfDns=[string]$status.Self.DNSName
$selfIps=@($status.Self.TailscaleIPs)
$rows=@()

$peers=@()
if($status.Peer){
  $peers=@($status.Peer.PSObject.Properties | ForEach-Object {$_.Value})
}
foreach($p in $peers){
  $online=[bool]$p.Online
  $name=if($p.HostName){[string]$p.HostName}else{[string]$p.DNSName}
  $dns=[string]$p.DNSName
  $ips=@($p.TailscaleIPs)
  $target=if($dns){$dns.TrimEnd('.')}elseif($ips.Count){[string]$ips[0]}else{$name}
  $pingOk=$false; $pingDetail=""
  if($online -and $target){
    try{
      $pingOut=& $ts ping --c 3 --timeout 5s $target 2>&1
      $pingOk=($LASTEXITCODE -eq 0)
      $pingDetail=($pingOut -join " ")
    }catch{$pingDetail=$_.Exception.Message}
  }
  $tcp=@{}
  foreach($port in $TcpPorts){
    try{
      $t=Test-NetConnection -ComputerName $target -Port $port -WarningAction SilentlyContinue
      $tcp[[string]$port]=[bool]$t.TcpTestSucceeded
    }catch{$tcp[[string]$port]=$false}
  }
  $rows += [pscustomobject]@{
    Name=$name
    DNSName=$dns
    IPs=($ips -join ",")
    Online=$online
    TailscalePing=$pingOk
    Tcp=$tcp
    PingDetail=$pingDetail
  }
}

$onlinePeers=@($rows | Where-Object {$_.Online -and $_.TailscalePing})
$ok=([string]$status.BackendState -eq "Running" -and $onlinePeers.Count -ge $ExpectedOnlinePeers)
$result=[ordered]@{
  CheckedAt=(Get-Date).ToString("o")
  ComputerName=$env:COMPUTERNAME
  User=$env:USERNAME
  BackendState=[string]$status.BackendState
  SelfHostName=$selfName
  SelfDNSName=$selfDns
  SelfIPs=$selfIps
  ExpectedOnlinePeers=$ExpectedOnlinePeers
  ReachablePeerCount=$onlinePeers.Count
  Pass=$ok
  Peers=$rows
}
$json=$result | ConvertTo-Json -Depth 8
$json
if($OutFile){
  $dir=Split-Path -Parent $OutFile
  if($dir){New-Item -ItemType Directory -Path $dir -Force | Out-Null}
  $json | Set-Content -Path $OutFile -Encoding UTF8
}
if(!$ok){ exit 2 }
exit 0
