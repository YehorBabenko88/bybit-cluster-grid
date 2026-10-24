#Requires -Version 5.1
<#
Offline-reviewed operator-only LOCAL read-only inventory. Never run without separate approval.
No outbound network, writes, service changes, or secret collection. JSON stdout only.
#>
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ports = @(22,8765,55432)
$maxRules = 2000
$result = [ordered]@{
 schema = 'grid-network-readonly-observation-2'
 status = 'BLOCKED'
 host_verified = $false
 execution_authorized = $false
 physical_tests = '0/10 NOT_RUN'
 observed_utc = [DateTime]::UtcNow.ToString('o')
 listeners = @()
 listener_count = 0
 firewall_rule_count = 0
 relevant_firewall_rules = @()
 relevant_rule_count = 0
 errors = @()
 evidence_limits = @('NO_TAILSCALE_POLICY','NO_SSH_IDENTITY','NO_TLS_AUTH_PROOF','NO_REMOTE_REACHABILITY','NO_EFFECTIVE_FIREWALL_PROOF')
}
try {
 $all = @(Get-NetTCPConnection -State Listen -ErrorAction Stop)
 $result.listeners = @($all | Where-Object { $ports -contains [int]$_.LocalPort } |
    ForEach-Object { [ordered]@{address=[string]$_.LocalAddress;port=[int]$_.LocalPort;pid=[int]$_.OwningProcess} })
 $result.listener_count = @($result.listeners).Count
 $rules = @(Get-NetFirewallRule -Enabled True -Direction Inbound -ErrorAction Stop)
 $result.firewall_rule_count = $rules.Count
 if ($rules.Count -gt $maxRules) { throw 'FIREWALL_INVENTORY_LIMIT' }
 foreach ($rule in $rules) {
   $pf = @($rule | Get-NetFirewallPortFilter -ErrorAction Stop)
   $af = @($rule | Get-NetFirewallAddressFilter -ErrorAction Stop)
   if ($pf.Count -ne 1 -or $af.Count -ne 1) { throw 'FIREWALL_FILTER_INCOMPLETE' }
   $protocol = [string]$pf[0].Protocol
   $localPort = [string]$pf[0].LocalPort
   $portMatches = $localPort -eq 'Any'
   foreach ($part in ($localPort -split ',')) {
     $item = $part.Trim()
     if ($item -in @('22','8765','55432')) { $portMatches = $true; continue }
     if ($item -match '^(\\d+)\\s*-\\s*(\\d+)
   $relevant = ($protocol -in @('TCP','6','Any')) -and $portMatches
   if ($relevant) {
      $result.relevant_firewall_rules += [ordered]@{
        action=[string]$rule.Action
        profile=[string]$rule.Profile
        protocol=$protocol
        local_port=$localPort
        remote_address=@($af[0].RemoteAddress)
      }
      if ($result.relevant_firewall_rules.Count -gt $maxRules) { throw 'RELEVANT_RULE_LIMIT' }
   }
 }
 $result.relevant_rule_count = $result.relevant_firewall_rules.Count
 $result.status = 'UNVERIFIED_READ_ONLY_OBSERVATION'
} catch {
 $result.status = 'BLOCKED'
 $result.errors = @('INVENTORY_INCOMPLETE_OR_ERROR')
 $result.listeners = @()
 $result.relevant_firewall_rules = @()
 $result.listener_count = 0
 $result.relevant_rule_count = 0
}
$result | ConvertTo-Json -Depth 8 -Compress
) {
       $low = [int]$Matches[1]; $high = [int]$Matches[2]
       if ($low -gt $high) { throw 'FIREWALL_PORT_RANGE_INVALID' }
       foreach ($target in $ports) {
         if ($low -le $target -and $target -le $high) { $portMatches = $true }
       }
     } elseif ($item -notmatch '^\\d+
   $relevant = ($protocol -in @('TCP','6','Any')) -and $portMatches
   if ($relevant) {
      $result.relevant_firewall_rules += [ordered]@{
        action=[string]$rule.Action
        profile=[string]$rule.Profile
        protocol=$protocol
        local_port=$localPort
        remote_address=@($af[0].RemoteAddress)
      }
      if ($result.relevant_firewall_rules.Count -gt $maxRules) { throw 'RELEVANT_RULE_LIMIT' }
   }
 }
 $result.relevant_rule_count = $result.relevant_firewall_rules.Count
 $result.status = 'UNVERIFIED_READ_ONLY_OBSERVATION'
} catch {
 $result.status = 'BLOCKED'
 $result.errors = @('INVENTORY_INCOMPLETE_OR_ERROR')
 $result.listeners = @()
 $result.relevant_firewall_rules = @()
 $result.listener_count = 0
 $result.relevant_rule_count = 0
}
$result | ConvertTo-Json -Depth 8 -Compress
 -and $item -ne 'Any') {
       # Unrecognized service/range expressions may cover a target port.
       # Refuse a misleading incomplete inventory rather than silently omit.
       throw 'FIREWALL_PORT_EXPRESSION_UNSUPPORTED'
     }
   }
   $relevant = ($protocol -in @('TCP','6','Any')) -and $portMatches
   if ($relevant) {
      $result.relevant_firewall_rules += [ordered]@{
        action=[string]$rule.Action
        profile=[string]$rule.Profile
        protocol=$protocol
        local_port=$localPort
        remote_address=@($af[0].RemoteAddress)
      }
      if ($result.relevant_firewall_rules.Count -gt $maxRules) { throw 'RELEVANT_RULE_LIMIT' }
   }
 }
 $result.relevant_rule_count = $result.relevant_firewall_rules.Count
 $result.status = 'UNVERIFIED_READ_ONLY_OBSERVATION'
} catch {
 $result.status = 'BLOCKED'
 $result.errors = @('INVENTORY_INCOMPLETE_OR_ERROR')
 $result.listeners = @()
 $result.relevant_firewall_rules = @()
 $result.listener_count = 0
 $result.relevant_rule_count = 0
}
$result | ConvertTo-Json -Depth 8 -Compress
