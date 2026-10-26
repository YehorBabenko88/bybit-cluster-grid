[CmdletBinding()]
param([switch]$CollectMemory,[switch]$G0Approved,[byte[]]$AssemblyBytes,[string]$AssemblySha256='',[string]$Head='',[string]$RunId='',[string]$CollectorSid='',[string]$StorageSid='')
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
function Get-G0IdentityBinding {
 param([scriptblock]$Query,[string]$CollectorSid,[string]$StorageSid)
 $WarningPreference='Stop'
 $answer=@{complete=$false;identities=@();code='IDENTITY_FAILED'}
 try{
  $pins=[ordered]@{GridLabCollector=$CollectorSid;GridLabStorage=$StorageSid}
  if($CollectorSid -ceq $StorageSid -or ($CollectorSid -replace '-[^-]+$','') -cne ($StorageSid -replace '-[^-]+$','')){throw 'SID_PIN'}
  foreach($name in $pins.Keys){$sid=$pins[$name];$rid=if($name -ceq 'GridLabCollector'){'1003'}else{'1004'}
   if($sid -cnotmatch ('^S-1-5-21-(?:[1-9][0-9]{0,9}-){3}'+$rid+'$') -or ([Security.Principal.SecurityIdentifier]::new($sid)).Value -cne $sid){throw 'SID_PIN'}
  }
  foreach($name in $pins.Keys){$rows=@(& $Query $name);if($rows.Count -ne 1 -or $rows[0].Name -cne $name -or $rows[0].SID.Value -cne $pins[$name]){$answer.code='SID_MISMATCH';throw 'SID_PIN'};$answer.identities+=@{name=$name;sid=$pins[$name]}}
  $answer.complete=$true;$answer.code='IDENTITY_BOUND'
 }catch{$answer.identities=@()}
 return $answer
}
$rights=@('SeInteractiveLogonRight','SeRemoteInteractiveLogonRight','SeNetworkLogonRight','SeBatchLogonRight','SeServiceLogonRight','SeDenyInteractiveLogonRight','SeDenyRemoteInteractiveLogonRight','SeDenyNetworkLogonRight','SeDenyBatchLogonRight','SeDenyServiceLogonRight')
$report=[ordered]@{schema='grid-g0-lsa-1';head=$Head;run_id=$RunId;host='PC4';mode='PlanOnly';collection='BLOCKED';subjects=@();effective_rights='UNKNOWN';group_completeness='UNKNOWN';execution_authorized=$false;cleanup_authorized=$false;host_verified=$false;actor_tokens_created=$false;physical_tests='0/10 NOT_RUN'}
if(-not $CollectMemory){$report|ConvertTo-Json -Depth 10 -Compress;return}
$report.mode='MemoryReadOnly'
$report.host=[Environment]::MachineName.ToUpperInvariant()
foreach($name in @('GridLabCollector','GridLabStorage')){$map=[ordered]@{};foreach($right in $rights){$map[$right]='UNKNOWN'};$pin=if($name -ceq 'GridLabCollector'){$CollectorSid}else{$StorageSid};$report.subjects+=@{name=$name;expected_sid=$pin;observed_sid=$null;state='UNKNOWN';code='IDENTITY_FAILED';ntstatus=0;win32=0;cleanup_failed=$false;rights=@();logon_rights=$map}}
$phase='INVALID_G0_SCOPE'
try{
 if(-not $G0Approved -or [Environment]::MachineName -ine 'PC4' -or -not [Environment]::Is64BitProcess -or $env:OS -ne 'Windows_NT' -or $Head -cnotmatch '^[a-f0-9]{40}$' -or $RunId -cnotmatch '^[a-f0-9]{32}$' -or $AssemblySha256 -cnotmatch '^[a-f0-9]{64}$' -or $null -eq $AssemblyBytes -or $AssemblyBytes.Length -eq 0 -or $AssemblyBytes.Length -gt 1048576){throw 'INVALID_G0_SCOPE'}
 $phase='ASSEMBLY_DIGEST_MISMATCH'
 $sha=[Security.Cryptography.SHA256]::Create();try{$actual=([BitConverter]::ToString($sha.ComputeHash($AssemblyBytes))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
 if($actual -cne $AssemblySha256){throw 'ASSEMBLY_DIGEST'}
 # Explicit OS module path, never PATH/PSModulePath discovery or a compatibility subprocess.
 $phase='IDENTITY_FAILED'
 Import-Module 'C:\Windows\System32\WindowsPowerShell\v1.0\Modules\Microsoft.PowerShell.LocalAccounts\Microsoft.PowerShell.LocalAccounts.psd1' -ErrorAction Stop -WarningAction Stop
 $binding=Get-G0IdentityBinding -CollectorSid $CollectorSid -StorageSid $StorageSid -Query {param($n) Microsoft.PowerShell.LocalAccounts\Get-LocalUser -Name $n -ErrorAction Stop -WarningAction Stop}
 if(-not $binding.complete){foreach($s in $report.subjects){$s.code=$binding.code};throw 'IDENTITY_BLOCKED'}
 # Hash validation and BOTH identity pins precede assembly loading and every LSA call.
 $phase='ASSEMBLY_LOAD_FAILED'
 $assembly=[Reflection.Assembly]::Load($AssemblyBytes)
 $api=[Activator]::CreateInstance($assembly.GetType('GridLab.LsaReadOnly.NativeApi',$true))
 $read=$assembly.GetType('GridLab.LsaReadOnly.SidBoundReader',$true).GetMethod('Read')
 $phase='LSA_INVOCATION_FAILED'
 foreach($s in $report.subjects){
  $s.observed_sid=$s.expected_sid;$r=$read.Invoke($null,@($api,$s.expected_sid,$s.observed_sid));$s.state=$r.State;$s.code=$r.Code;$s.ntstatus=[uint32]$r.Status;$s.win32=[uint32]$r.Win32Error;$s.cleanup_failed=[bool]$r.CleanupFailed;$s.rights=@($r.Rights)
  $valid=($r.State -ceq 'DIRECT_ONLY' -and -not $r.CleanupFailed -and (($r.Code -ceq 'ENUMERATED' -and $r.Status -eq 0 -and $r.Win32Error -eq 0) -or ($r.Code -ceq 'NO_DIRECT_ASSIGNMENTS' -and $r.Status -eq 3221225524 -and $r.Win32Error -eq 2 -and @($r.Rights).Count -eq 0)))
  foreach($right in @($r.Rights)){if($right.EndsWith('Right') -and $right -cnotin $rights){$valid=$false;$s.code='UNSUPPORTED_RIGHT'}}
  if($valid){foreach($right in $rights){$s.logon_rights[$right]=if($right -cin @($r.Rights)){'ASSIGNED_DIRECT'}else{'NOT_DIRECTLY_ASSIGNED'}}}
  else{$s.state='UNKNOWN';$s.rights=@();if($s.code -cin @('ENUMERATED','NO_DIRECT_ASSIGNMENTS')){$s.code='API_OR_DATA_ERROR'}}
 }
 if(@($report.subjects|Where-Object {$_.state -cne 'DIRECT_ONLY'}).Count -eq 0){$report.collection='DIRECT_POLICY_OBSERVED'}
}catch{foreach($s in $report.subjects){if($s.state -ceq 'UNKNOWN' -and $s.code -ceq 'IDENTITY_FAILED'){$s.code=$phase}}}
$report|ConvertTo-Json -Depth 10 -Compress
if($report.collection -ne 'DIRECT_POLICY_OBSERVED'){exit 1}
