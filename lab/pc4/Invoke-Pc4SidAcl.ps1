#Requires -Version 5.1
[CmdletBinding()]
param([switch]$PlanOnly,[switch]$Execute,[switch]$Cleanup,[switch]$ApproveFixtureCreation,[switch]$ApproveFixtureCleanup,
 [string]$RunId,[string]$CollectorSid,[string]$StorageSid,[string]$AccountPlanReference,
 [string]$ExpectedPackageManifestSha256)
$ErrorActionPreference='Stop'
if($PlanOnly -and ($Execute -or $Cleanup)){throw 'MODES_EXCLUSIVE'}
# Default plan is constant metadata: no dot-sourcing, identity/provider query,
# native compilation, credentials, filesystem enumeration or process launch.
if(!$Execute -and !$Cleanup){
 [pscustomobject]@{mode='PlanOnly';status='BLOCKED';host='PC4';accounts='DISABLED_REQUIRES_SEPARATE_OWNER_PLAN';
  scope='NEW_GUID_FIXTURES_ONLY';execution_authorized=$false;readiness_passed=$false;airgap_verified=$false}
 return
}
if($Execute -and $Cleanup){throw 'MODES_EXCLUSIVE'}
# Immutable safety blocks; no approval switch overrides these.
if($Cleanup){throw 'CLEANUP_NOT_AUTHORIZED'}
if($Execute){throw 'EXECUTE_NOT_AUTHORIZED'}
if([Environment]::MachineName -cne 'PC4' -or ![Environment]::Is64BitProcess){throw 'PC4_LOCAL_ONLY'}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if(!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'BOOTSTRAP_ADMIN_REQUIRED_NOT_TEST_EVIDENCE'}
$bootstrapSid=$identity.User.Value
if($PSScriptRoot -cne 'C:\GridLab\Harness\PC4SidAcl'){throw 'REVIEWED_PACKAGE_LOCATION_REQUIRED'}
# Bootstrap code ACL checks must precede dot-sourcing any sibling component.
# The controller itself must already be verified under the separate staging plan.
foreach($path in @('C:\GridLab','C:\GridLab\Harness',$PSScriptRoot,(Join-Path $PSScriptRoot 'Common.ps1'),(Join-Path $PSScriptRoot 'package.sha256.json'))){
 $item=Get-Item -LiteralPath $path -Force -ErrorAction Stop
 if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'BOOTSTRAP_REPARSE_BLOCKED'}
 $a=Get-Acl -LiteralPath $path -ErrorAction Stop
 if($a.GetOwner([Security.Principal.SecurityIdentifier]).Value -cnotin @($bootstrapSid,'S-1-5-18','S-1-5-32-544')){throw 'BOOTSTRAP_OWNER_UNTRUSTED'}
 foreach($r in $a.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
  if($r.AccessControlType -ne 'Allow' -or ($r.IdentityReference.Value -cnotin @($bootstrapSid,'S-1-5-18','S-1-5-32-544') -and (([int64]$r.FileSystemRights -band 0x500D0156) -ne 0))){throw 'BOOTSTRAP_CODE_WRITABLE'}
 }
}
$bootstrapManifestPath=Join-Path $PSScriptRoot 'package.sha256.json'
if($ExpectedPackageManifestSha256 -cnotmatch '^[0-9a-f]{64}$' -or (Get-Item -LiteralPath $bootstrapManifestPath).Length -gt 16384 -or (Get-FileHash -LiteralPath $bootstrapManifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedPackageManifestSha256){throw 'BOOTSTRAP_PACKAGE_HASH_REQUIRED'}
$bootstrapManifest=[IO.File]::ReadAllText($bootstrapManifestPath,(New-Object Text.UTF8Encoding($false,$true)))|ConvertFrom-Json
if((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'Common.ps1') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $bootstrapManifest.files.'Common.ps1'){throw 'BOOTSTRAP_COMMON_HASH_MISMATCH'}
. (Join-Path $PSScriptRoot 'Common.ps1')
foreach($p in @('C:\GridLab','C:\GridLab\Secure','C:\GridLab\Harness',$PSScriptRoot,'C:\GridLab\Evidence')){Assert-Pc4TrustedAcl $p $bootstrapSid}
$packageFiles=@('Common.ps1','Actor.ps1','TokenFacts.cs','TokenFacts.dll','Invoke-Pc4SidAcl.ps1','Lifecycle.ps1')
foreach($name in @($packageFiles)+@('package.sha256.json')){Assert-Pc4TrustedAcl (Join-Path $PSScriptRoot $name) $bootstrapSid}
$packagePath=Join-Path $PSScriptRoot 'package.sha256.json'
if($ExpectedPackageManifestSha256 -cnotmatch '^[0-9a-f]{64}$' -or (Get-Pc4Hash $packagePath) -cne $ExpectedPackageManifestSha256){throw 'PINNED_PACKAGE_MANIFEST_REQUIRED'}
$package=Read-Pc4Text $packagePath 16384|ConvertFrom-Json
if(@($package.PSObject.Properties).Count -ne 3 -or $package.source_sha -cnotmatch '^[0-9a-f]{40}$' -or $package.kind -cne 'PC4_OFFLINE_BUILT_PACKAGE' -or @($package.files.PSObject.Properties).Count -ne $packageFiles.Count){throw 'PACKAGE_PROFILE_BLOCKED'}
foreach($name in $packageFiles){if((Get-Pc4Hash (Join-Path $PSScriptRoot $name)) -cne $package.files.$name){throw 'PACKAGE_HASH_MISMATCH'}}
. (Join-Path $PSScriptRoot 'Lifecycle.ps1')
Assert-Pc4EvidenceAcl 'C:\GridLab\Evidence' $bootstrapSid
Assert-Pc4Guid $RunId
$evidence=(Get-Pc4Paths $RunId 'Collector').Evidence
if(!$ApproveFixtureCreation -or $AccountPlanReference -cnotmatch '^[A-Z0-9][A-Z0-9_-]{3,63}$'){throw 'SEPARATE_ACCOUNT_PLAN_AND_FIXTURE_APPROVAL_REQUIRED'}
Assert-Pc4Sid $CollectorSid '1003';Assert-Pc4Sid $StorageSid '1004'
$sids=@{Collector=$CollectorSid;Storage=$StorageSid};$credentials=@{}
foreach($role in @('Collector','Storage')){
 $u=Get-LocalUser -Name ('GridLab'+$role) -ErrorAction Stop
 if($u.SID.Value -cne $sids[$role] -or $u.Enabled -ne $true){throw 'ACCOUNT_IDENTITY_OR_ENABLED_STATE_BLOCKED'}
 Assert-Pc4ParentAcl (Get-Pc4Paths $RunId $role).Parent $sids[$role]
 Assert-Pc4FreshScope (Test-Pc4Absent (Get-Pc4Paths $RunId $role).Root) (Test-Pc4Absent $evidence) $true
}
if(!(Test-Pc4Absent $evidence)){throw 'RERUN_REFUSES_EXISTING_EVIDENCE'}
# Disabled accounts must be handled by a distinct owner-reviewed plan; this
# package NEVER enables users, changes groups, rights, ACLs or execution policy.
foreach($role in @('Collector','Storage')){
 $c=Get-Credential -UserName ('PC4\GridLab'+$role) -Message 'Local lab credential; never enter it into command-line arguments'
 if($null -eq $c -or $c.UserName -cne ('PC4\GridLab'+$role)){throw 'CREDENTIAL_SCOPE_BLOCKED'}
 $credentials[$role]=$c
}
Add-Type -Path (Join-Path $PSScriptRoot 'TokenFacts.dll')
$manifest=[ordered]@{schema=1;kind='PC4_OWNED_FIXTURE_MANIFEST';run_id=$RunId;bootstrap_sid=$bootstrapSid;account_plan_reference=$AccountPlanReference;
 source_sha=$package.source_sha;package_manifest_sha256=$ExpectedPackageManifestSha256;
 package_hashes=@{};expected_sids=$sids;complete=$false;airgap_verified=$false;execution_authorized=$false;readiness_passed=$false}
foreach($name in @($packageFiles)+@('package.sha256.json')){$manifest.package_hashes[$name]=Get-Pc4Hash (Join-Path $PSScriptRoot $name)}
$processes=@{};$launchIntents=@{};$success=$false;$pins=New-Object Collections.Generic.List[object]
try {
 foreach($path in @('C:\GridLab','C:\GridLab\Secure','C:\GridLab\Secure\Collector','C:\GridLab\Secure\Storage','C:\GridLab\Evidence')){$pins.Add([GridPc4.TokenFacts]::PinDirectory($path))}
 $null=New-Item -ItemType Directory -Path $evidence -ErrorAction Stop
 Assert-Pc4EvidenceAcl $evidence $bootstrapSid
 Write-Pc4NewText (Join-Path $evidence 'manifest.json') ($manifest|ConvertTo-Json -Depth 8 -Compress)
 $aclBefore=[ordered]@{}
 foreach($role in @('Collector','Storage')){$a=Get-Acl -LiteralPath (Get-Pc4Paths $RunId $role).Parent;$aclBefore[$role]=@{owner=$a.GetOwner([Security.Principal.SecurityIdentifier]).Value;sddl=$a.Sddl}}
 Write-Pc4NewText (Join-Path $evidence 'acl-before.json') ($aclBefore|ConvertTo-Json -Depth 5 -Compress)
 foreach($role in @('Collector','Storage')){
  $root=(Get-Pc4Paths $RunId $role).Root
  $null=New-Item -ItemType Directory -Path $root -ErrorAction Stop
  Assert-Pc4Plain $root
  $pins.Add([GridPc4.TokenFacts]::PinDirectory($root))
  Write-Pc4NewText (Join-Path $root 'fixture.json') (@{kind='PC4_DISPOSABLE_FIXTURE';run_id=$RunId;role=$role}|ConvertTo-Json -Compress)
  Write-Pc4NewText (Join-Path $root 'canary.txt') ($RunId+'|'+$role+'|CANARY')
 }
 foreach($role in @('Collector','Storage')){
  $start=New-Object Diagnostics.ProcessStartInfo
  $start.FileName=Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::System)) 'WindowsPowerShell\v1.0\powershell.exe'
  $start.Arguments='-NoLogo -NoProfile -NonInteractive -File "'+(Join-Path $PSScriptRoot 'Actor.ps1')+'" -RunId '+$RunId+' -Role '+$role+' -ExpectedSid '+$sids[$role]+' -TokenAssemblySha256 '+$package.files.'TokenFacts.dll'
  $start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.LoadUserProfile=$false
  $start.WorkingDirectory=(Get-Pc4Paths $RunId $role).Root
  $start.UserName='GridLab'+$role;$start.Domain='PC4';$start.Password=$credentials[$role].Password
  Write-Pc4NewText (Join-Path $evidence ($role+'-launch-intent.json')) (@{run_id=$RunId;role=$role;state='LAUNCH_INTENT_ONLY'}|ConvertTo-Json -Compress)
  $launchIntents[$role]=$true
  $processes[$role]=[Diagnostics.Process]::Start($start)
  if($null -eq $processes[$role]){throw 'ACTOR_START_UNKNOWN'}
  $null=$processes[$role].Handle # retain OS identity before publishing PID
  $actorStarted=$processes[$role].StartTime.ToUniversalTime().ToString('O')
  Write-Pc4NewText (Join-Path $evidence ($role+'-process.json')) (@{run_id=$RunId;role=$role;state='ACTOR_STARTED';pid=$processes[$role].Id;start_utc=$processes[$role].StartTime.ToUniversalTime().ToString('O')}|ConvertTo-Json -Compress)
 }
 foreach($role in @('Collector','Storage')){
  $root=(Get-Pc4Paths $RunId $role).Root;$ready=Join-Path $root 'ready.json';$deadline=[DateTime]::UtcNow.AddSeconds(30)
  while(Test-Pc4Absent $ready){if($processes[$role].HasExited -or [DateTime]::UtcNow -gt $deadline){throw 'ACTOR_START_FAILED'};Start-Sleep -Milliseconds 100}
  $r=Read-Pc4Text $ready 16384|ConvertFrom-Json
  if($processes[$role].HasExited -or $r.run_id -cne $RunId -or $r.role -cne $role -or $r.start_utc -cne $processes[$role].StartTime.ToUniversalTime().ToString('O') -or $r.pid -ne $processes[$role].Id -or !(Test-Pc4Facts $r.facts $sids[$role])){throw 'CHILD_HANDSHAKE_BLOCKED'}
  $observed=[GridPc4.TokenFacts]::ReadProcessHandle($processes[$role].Handle,$false)
  if(!(Test-Pc4Facts $observed $sids[$role])){throw 'PARENT_OBSERVED_TOKEN_BLOCKED'}
  Write-Pc4NewText (Join-Path $evidence ($role+'-parent-token.json')) (@{pid=$processes[$role].Id;facts=$observed}|ConvertTo-Json -Depth 8 -Compress)
 }
 foreach($role in @('Collector','Storage')){Write-Pc4NewText (Join-Path (Get-Pc4Paths $RunId $role).Root 'go.flag') 'GO'}
 $all=''
 foreach($role in @('Collector','Storage')){
  if(!$processes[$role].WaitForExit(30000) -or $processes[$role].ExitCode -ne 0){throw 'ACTOR_FAILED_OR_TIMEOUT'}
  $root=(Get-Pc4Paths $RunId $role).Root
  Assert-Pc4ParentAcl (Get-Pc4Paths $RunId $role).Parent $sids[$role];Assert-Pc4Plain $root
  if((Read-Pc4Text (Join-Path $root 'canary.txt') 4096) -cne ($RunId+'|'+$role+'|CANARY')){throw 'FOREIGN_CANARY_CHANGED'}
  $text=Read-Pc4Text (Join-Path $root 'actor.jsonl') 65536
  Write-Pc4NewText (Join-Path $evidence ($role+'-actor.jsonl')) $text;$all+=$text
 }
 Write-Pc4NewText (Join-Path $evidence 'results.jsonl') $all
 $aclAfter=[ordered]@{}
 foreach($role in @('Collector','Storage')){
  $a=Get-Acl -LiteralPath (Get-Pc4Paths $RunId $role).Parent;$aclAfter[$role]=@{owner=$a.GetOwner([Security.Principal.SecurityIdentifier]).Value;sddl=$a.Sddl}
  if($aclAfter[$role].sddl -cne $aclBefore[$role].sddl -or $aclAfter[$role].owner -cne $aclBefore[$role].owner){throw 'PARENT_ACL_CHANGED'}
 }
 Write-Pc4NewText (Join-Path $evidence 'acl-after.json') ($aclAfter|ConvertTo-Json -Depth 5 -Compress)
 # Validate native records independently before calling the reported suite pass.
 $records=@($all.TrimEnd("`n").Split("`n")|ForEach-Object {$_|ConvertFrom-Json})
 if($records.Count -ne 10){throw 'EVIDENCE_COUNT_INVALID'}
 $suite=New-Object Xml.XmlDocument;$s=$suite.CreateElement('testsuite');$null=$suite.AppendChild($s)
 $s.SetAttribute('name','PC4_LOCAL_REPORTED_NOT_INDEPENDENTLY_ATTESTED');$s.SetAttribute('tests','10');$s.SetAttribute('failures','0');$s.SetAttribute('errors','0');$s.SetAttribute('skipped','0')
 $idx=0
 foreach($role in @('Collector','Storage')){foreach($case in @('token','own_write','own_read','foreign_read_denied','foreign_write_denied')){
  $r=$records[$idx];$idx++
  if($r.run_id -cne $RunId -or $r.role -cne $role -or $r.case -cne $case -or $r.pid -ne $processes[$role].Id -or $r.outcome -cne 'PASS'){throw 'EVIDENCE_BINDING_INVALID'}
  if($case -ceq 'token' -and !(Test-Pc4Facts $r.facts $sids[$role])){throw 'EVIDENCE_TOKEN_INVALID'}
  $expectedCode=if($case.StartsWith('foreign_')){'ACCESS_DENIED_5'}else{'OK'}
  if($r.code -cne $expectedCode){throw 'EVIDENCE_ERROR_CODE_INVALID'}
  $c=$suite.CreateElement('testcase');$c.SetAttribute('classname',('PC4.'+$role));$c.SetAttribute('name',$case);$null=$s.AppendChild($c)
 }}
 Write-Pc4NewText (Join-Path $evidence 'junit.xml') $suite.OuterXml
 $success=$true
} catch {
 # Preserve partial evidence. No exception details/credentials are logged.
 if(!(Test-Pc4Absent $evidence)){
  $failure=Join-Path $evidence 'failure.txt';if(Test-Pc4Absent $failure){Write-Pc4NewText $failure 'PC4_RUN_BLOCKED_OR_PARTIAL'}
  if(Test-Pc4Absent (Join-Path $evidence 'junit.xml')){Write-Pc4NewText (Join-Path $evidence 'junit.xml') '<testsuite name="PC4_BLOCKED_PARTIAL" tests="1" failures="1" errors="0" skipped="0"><testcase name="incomplete_run"><failure message="PC4_RUN_BLOCKED_OR_PARTIAL" /></testcase></testsuite>'}
  if(Test-Pc4Absent (Join-Path $evidence 'failure.jsonl')){Write-Pc4NewText (Join-Path $evidence 'failure.jsonl') ((@{run_id=$RunId;status='BLOCKED_PARTIAL';physical_attestation=$false}|ConvertTo-Json -Compress)+"`n")}
  $partial=Join-Path $evidence 'partial-sha256.json'
  if(Test-Pc4Absent $partial){$hashes=[ordered]@{};foreach($f in @(Get-ChildItem -LiteralPath $evidence -File)){$hashes[$f.Name]=Get-Pc4Hash $f.FullName};Write-Pc4NewText $partial ($hashes|ConvertTo-Json -Compress)}
 }
 throw 'PC4_RUN_BLOCKED_OR_PARTIAL'
} finally {
 $shutdown=[ordered]@{};$shutdownBlocked=$false
 foreach($role in @('Collector','Storage')){
  if($processes.ContainsKey($role)){
   $stop=Join-Path (Get-Pc4Paths $RunId $role).Root 'stop.flag'
   $r=Stop-Pc4Actor $processes[$role] {if(Test-Pc4Absent $stop){Write-Pc4NewText $stop 'STOP'}}
   $shutdown[$role]=$r
   if($r.status -cne 'EXIT_CONFIRMED'){$shutdownBlocked=$true}
   else {$processes[$role].Dispose()}
   if($r.exit_code -ne 0 -or $r.signal_failed){$shutdownBlocked=$true}
  } elseif($launchIntents.ContainsKey($role)) {
   $shutdown[$role]=@{status='BLOCKED_LAUNCH_OUTCOME_UNKNOWN';exit_code=$null};$shutdownBlocked=$true
  } else {$shutdown[$role]=@{status='NOT_LAUNCHED';exit_code=$null}}
 }
 $credentials.Clear()
 foreach($pin in $pins){$pin.Dispose()}
 if(!(Test-Pc4Absent $evidence)){Write-Pc4NewText (Join-Path $evidence 'shutdown.json') ($shutdown|ConvertTo-Json -Depth 5 -Compress)}
 if($shutdownBlocked){throw 'ACTOR_SHUTDOWN_UNCONFIRMED'}
}

if($success){
 Write-Pc4NewText (Join-Path $evidence 'completed.json') (@{run_id=$RunId;reported_cases=10;physical_attestation=$false;airgap_verified=$false}|ConvertTo-Json -Compress)
 $hashes=[ordered]@{};foreach($f in @(Get-ChildItem -LiteralPath $evidence -File)){$hashes[$f.Name]=Get-Pc4Hash $f.FullName}
 Write-Pc4NewText (Join-Path $evidence 'sha256.json') ($hashes|ConvertTo-Json -Compress)
 [pscustomobject]@{status='TEN_LOCAL_CASES_REPORTED_NOT_ATTESTED';run_id=$RunId;physical_attestation=$false;readiness_passed=$false}
}
