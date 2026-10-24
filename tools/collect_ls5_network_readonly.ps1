#Requires -Version 5.1
<#
.SYNOPSIS
  Operator-run, read-only LS5 network inventory. Not authorized for execution by this PR.
.DESCRIPTION
  No sockets, SSH, Tailscale CLI, process launches, writes, service or firewall changes.
  Produces console-only JSON. Operator must independently authorize use and redact before sharing.
#>
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Get-ReadOnlyNetworkInventory {
    $ports = @(22, 8765, 55432)
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
        Where-Object { $ports -contains [int]$_.LocalPort } |
        Select-Object LocalAddress,LocalPort,OwningProcess,State)
    $adapters = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
        Select-Object InterfaceAlias,IPAddress,PrefixLength,AddressState)
    $firewall = @(Get-NetFirewallRule -Enabled True -Direction Inbound -ErrorAction Stop |
        ForEach-Object {
            $rule = $_
            $addresses = @($rule | Get-NetFirewallAddressFilter -ErrorAction Stop | Select-Object -ExpandProperty RemoteAddress)
            $ports = @($rule | Get-NetFirewallPortFilter -ErrorAction Stop |
                Select-Object Protocol,LocalPort,RemotePort)
            [pscustomobject]@{
                DisplayName = $rule.DisplayName
                Name = $rule.Name
                Action = [string]$rule.Action
                Profile = [string]$rule.Profile
                RemoteAddress = $addresses
                PortFilters = $ports
            }
        })
    [pscustomobject]@{
        schema = 'grid-network-readonly-observation-1'
        observed_utc = [DateTime]::UtcNow.ToString('o')
        node_claim = $env:COMPUTERNAME
        status = 'UNVERIFIED_OBSERVATION'
        physical_ready = $false
        execution_authorized = $false
        listeners = $listeners
        ipv4 = $adapters
        enabled_inbound_firewall_rules = $firewall
        missing_evidence = @('Tailscale ACL','SSH principal identity','TLS certificate','API auth route review','effective firewall profiles','negative reachability tests')
    }
}
Get-ReadOnlyNetworkInventory | ConvertTo-Json -Depth 9
