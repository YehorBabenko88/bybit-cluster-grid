param([switch]$Remove)
$ErrorActionPreference="Stop"
$name="BybitClusterGrid Coordinator Management"
if($Remove){
  Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
  exit 0
}
Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -RemoteAddress 100.64.0.0/10,fd7a:115c:a1e0::/48 -Profile Any | Out-Null
