#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$script:Pc4Utf8=New-Object Text.UTF8Encoding($false,$true)
function Assert-Pc4Guid([string]$RunId){
 if($RunId -cnotmatch '^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'){throw 'RUN_ID_INVALID'}
}
function Assert-Pc4Sid([string]$Sid,[string]$Rid){
 if($Sid -cnotmatch ('^S-1-5-21-[0-9]+-[0-9]+-[0-9]+-'+$Rid+'$')){throw 'FULL_SID_REQUIRED'}
 $parsed=New-Object Security.Principal.SecurityIdentifier($Sid)
 if($parsed.Value -cne $Sid){throw 'SID_NONCANONICAL'}
}
function Get-Pc4Paths([string]$RunId,[string]$Role){
 Assert-Pc4Guid $RunId
 if($Role -cnotin @('Collector','Storage')){throw 'ROLE_INVALID'}
 [pscustomobject]@{Parent=('C:\GridLab\Secure\'+$Role);Root=('C:\GridLab\Secure\'+$Role+'\sid-acl-'+$RunId);Evidence=('C:\GridLab\Evidence\sid-acl-'+$RunId)}
}
function Assert-Pc4Plain([string]$Path){
 $cursor=$Path
 while($cursor){
  $i=Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
  if($i.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'REPARSE_BLOCKED'}
  $p=[IO.Directory]::GetParent($cursor);if($null -eq $p){break};$cursor=$p.FullName
 }
}
function Test-Pc4Absent([string]$Path){
 try{$null=Get-Item -LiteralPath $Path -Force -ErrorAction Stop;return $false}
 catch [Management.Automation.ItemNotFoundException]{return $true}
}
function Get-Pc4Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()}
function Read-Pc4Text([string]$Path,[int]$Limit){
 Assert-Pc4Plain $Path
 if($Limit -lt 1 -or $Limit -gt 131072){throw 'READ_LIMIT_INVALID'}
 $s=New-Object IO.FileStream($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
 try {
  $buf=New-Object byte[] ($Limit+1);$used=0
  while($used -lt $buf.Length){$n=$s.Read($buf,$used,($buf.Length-$used));if($n -eq 0){break};$used+=$n}
  if($used -gt $Limit){throw 'EVIDENCE_TOO_LARGE'}
  return $script:Pc4Utf8.GetString($buf,0,$used)
 } finally {$s.Dispose()}
}
function Write-Pc4NewText([string]$Path,[string]$Text){
 $bytes=$script:Pc4Utf8.GetBytes($Text)
 $s=New-Object IO.FileStream($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
 try{$s.Write($bytes,0,$bytes.Length);$s.Flush($true)}finally{$s.Dispose()}
}
function Add-Pc4Text([string]$Path,[string]$Text){
 $bytes=$script:Pc4Utf8.GetBytes($Text)
 # Open, not Append/Create: a missing per-run stream must not be recreated.
 $s=New-Object IO.FileStream($Path,[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::None)
 try{$null=$s.Seek(0,[IO.SeekOrigin]::End);$s.Write($bytes,0,$bytes.Length);$s.Flush($true)}finally{$s.Dispose()}
}
function Test-Pc4Facts($Facts,[string]$ExpectedSid){
 if($null -eq $Facts){return $false}
 foreach($k in @('admin_group','elevated','impersonating')){if($Facts.$k -isnot [bool]){return $false}}
 if(($Facts.integrity_rid -isnot [int] -and $Facts.integrity_rid -isnot [long]) -or $Facts.sid -isnot [string]){return $false}
 if($Facts.sid -cne $ExpectedSid -or $Facts.admin_group -ne $false -or $Facts.elevated -ne $false -or $Facts.impersonating -ne $false -or $Facts.integrity_rid -le 0 -or $Facts.integrity_rid -gt 8192){return $false}
 $seen=@();foreach($p in $Facts.privileges){
  if($p.enabled -isnot [bool]){return $false}
  if($p.name -cnotin @('SeChangeNotifyPrivilege','SeShutdownPrivilege','SeUndockPrivilege','SeIncreaseWorkingSetPrivilege','SeTimeZonePrivilege') -or $p.name -cin $seen){return $false}
  if($p.enabled -and $p.name -cne 'SeChangeNotifyPrivilege'){return $false};$seen+=,$p.name
 }
 return ($seen.Count -gt 0)
}
function Assert-Pc4ParentAcl([string]$Path,[string]$OwnerSid){
 Assert-Pc4Plain $Path;$acl=Get-Acl -LiteralPath $Path -ErrorAction Stop
 if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cnotin @($OwnerSid,'S-1-5-18','S-1-5-32-544')){throw 'PARENT_OWNER_UNKNOWN'}
 if(!$acl.AreAccessRulesProtected){throw 'PARENT_ACL_NOT_PROTECTED'}
 $rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
 if($rules.Count -ne 3){throw 'PARENT_ACL_UNKNOWN'}
 $seen=@();foreach($r in $rules){
  $sid=$r.IdentityReference.Value;$mask=([int64]$r.FileSystemRights -band (-bnot [int64]0x100000))
  $expected=if($sid -ceq $OwnerSid){[int64][Security.AccessControl.FileSystemRights]::Modify -band (-bnot [int64]0x100000)}else{[int64][Security.AccessControl.FileSystemRights]::FullControl -band (-bnot [int64]0x100000)}
  if($sid -cnotin @($OwnerSid,'S-1-5-18','S-1-5-32-544') -or $sid -cin $seen -or $mask -ne $expected -or $r.AccessControlType -ne 'Allow' -or $r.InheritanceFlags -ne 'ContainerInherit, ObjectInherit' -or $r.PropagationFlags -ne 'None'){throw 'PARENT_ACL_UNSAFE'}
  $seen+=,$sid
 }
}
function Assert-Pc4TrustedAcl([string]$Path,[string]$BootstrapSid){
 Assert-Pc4Plain $Path;$a=Get-Acl -LiteralPath $Path -ErrorAction Stop
 $owner=$a.GetOwner([Security.Principal.SecurityIdentifier]).Value
 if($owner -cnotin @($BootstrapSid,'S-1-5-18','S-1-5-32-544')){throw 'CONTROL_OWNER_UNTRUSTED'}
 foreach($r in $a.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
  if($r.AccessControlType -ne 'Allow'){throw 'CONTROL_ACL_UNKNOWN'}
  if($r.IdentityReference.Value -cnotin @($BootstrapSid,'S-1-5-18','S-1-5-32-544') -and (([int64]$r.FileSystemRights -band 0x500D0156) -ne 0)){throw 'CONTROL_WRITABLE'}
 }
}
function Assert-Pc4EvidenceAcl([string]$Path,[string]$BootstrapSid){
 Assert-Pc4TrustedAcl $Path $BootstrapSid
 $a=Get-Acl -LiteralPath $Path -ErrorAction Stop
 foreach($r in $a.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
  if($r.IdentityReference.Value -cnotin @($BootstrapSid,'S-1-5-18','S-1-5-32-544')){throw 'EVIDENCE_NOT_PRIVATE'}
 }
}
function Assert-Pc4FreshScope($FixtureAbsent,$EvidenceAbsent,$InventoryKnown){
 if($FixtureAbsent -isnot [bool] -or $EvidenceAbsent -isnot [bool] -or $InventoryKnown -isnot [bool] -or !$FixtureAbsent -or !$EvidenceAbsent -or !$InventoryKnown){throw 'FRESH_SCOPE_BLOCKED'}
}
function Assert-Pc4RecordedHash($Index,[string]$Name,[string]$Actual){
 if($Name -cnotmatch '^(manifest\.json|(Collector|Storage)-(launch-intent|process)\.json)$' -or $Actual -cnotmatch '^[0-9a-f]{64}$'){throw 'RECORDED_HASH_SCOPE_INVALID'}
 if($null -eq $Index -or $null -eq $Index.PSObject.Properties[$Name]){throw 'RECORDED_HASH_MISSING'}
 $expected=$Index.PSObject.Properties[$Name].Value
 if($expected -isnot [string] -or $expected -cnotmatch '^[0-9a-f]{64}$' -or $expected -cne $Actual){throw 'RECORDED_HASH_MISMATCH'}
}
function Get-Pc4CleanupNames([string]$RunId,[string]$Role,$Marker,$Entries,$ProcessAbsent){
 Assert-Pc4Guid $RunId;$null=Get-Pc4Paths $RunId $Role
 if($ProcessAbsent -isnot [bool] -or !$ProcessAbsent){throw 'CLEANUP_PROCESS_UNKNOWN'}
 if($null -eq $Marker -or $Marker.run_id -cne $RunId -or $Marker.role -cne $Role -or $Marker.kind -cne 'PC4_DISPOSABLE_FIXTURE'){throw 'CLEANUP_MARKER_MISMATCH'}
 $names=@();foreach($f in $Entries){
  if($f.PSIsContainer -ne $false -or ($f.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $f.Name -cnotin @('fixture.json','canary.txt','own.txt','ready.json','go.flag','stop.flag','actor.jsonl') -or $f.Name -cin $names){throw 'CLEANUP_UNKNOWN_ENTRY'}
  $names+=,$f.Name
 }
 if('fixture.json' -cnotin $names){throw 'CLEANUP_MARKER_MISSING'}
 @($names|Where-Object {$_ -cne 'fixture.json'})
}
