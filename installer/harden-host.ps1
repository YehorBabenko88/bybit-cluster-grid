#Requires -RunAsAdministrator
param([string]$SshRemoteAddress="100.64.0.0/10")
$ErrorActionPreference="Stop"

# Critical connectivity services recover after crashes/stops. This does not
# conceal them from administrators and does not prevent normal maintenance.
foreach($name in @("Tailscale","sshd")){
  $svc=Get-Service -Name $name -ErrorAction SilentlyContinue
  if(!$svc){ Write-Warning "$name service is not installed"; continue }
  Set-Service -Name $name -StartupType Automatic
  sc.exe failure $name reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
  sc.exe failureflag $name 1 | Out-Null
  if($svc.Status -ne "Running"){ Start-Service $name }
}

# SSH stays key-only. Validate before restart so a malformed config cannot
# silently lock out remote commissioning.
$cfg="C:\ProgramData\ssh\sshd_config"
if(Test-Path $cfg){
  $text=Get-Content $cfg -Raw
  foreach($pair in @(@("PasswordAuthentication","no"),@("PubkeyAuthentication","yes"))){
    $k=$pair[0]; $v=$pair[1]; $line="$k $v"
    if($text -match "(?m)^\s*#?\s*$k\s+.*$"){$text=[regex]::Replace($text,"(?m)^\s*#?\s*$k\s+.*$",$line)}
    else{$text+="`r`n$line"}
  }
  $tmp="$cfg.grid-new"; [IO.File]::WriteAllText($tmp,$text,[Text.Encoding]::ASCII)
  & sshd.exe -t -f $tmp
  if($LASTEXITCODE -ne 0){Remove-Item $tmp -Force;throw "Candidate sshd_config validation failed"}
  Move-Item $tmp $cfg -Force
  Restart-Service sshd
}

Get-NetFirewallRule -DisplayName "Bybit Cluster Grid SSH via Tailscale" -EA SilentlyContinue|Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "Bybit Cluster Grid SSH via Tailscale" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 22 -RemoteAddress $SshRemoteAddress -Profile Any|Out-Null
Write-Host "Grid host security baseline applied."
