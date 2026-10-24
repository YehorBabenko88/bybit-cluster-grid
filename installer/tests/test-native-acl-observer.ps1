#Requires -Version 5.1
# Hosted GUID fixture only; observer remains read-only, all ACL writes are fixture setup.
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
 $env:RUNNER_OS -cne 'Windows' -or $env:GITHUB_REPOSITORY -cne 'YehorBabenko88/bybit-cluster-grid' -or
 $env:GITHUB_JOB -cne 'observer-fixture' -or $env:EXACT_HEAD_SHA -cnotmatch '^[0-9a-f]{40}$'){
 throw 'HOSTED_NATIVE_GUID_FIXTURE_ONLY'
}
$temp=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')
if((Get-Item -LiteralPath $temp -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'TEMP_REPARSE'}
$script:root=Join-Path $temp ('native-observer-'+[guid]::NewGuid().ToString('D'))
$null=New-Item -ItemType Directory -Path $script:root -ErrorAction Stop
$script:exe=Join-Path $env:GITHUB_WORKSPACE 'installer/native-acl-observer/bin/Release/net8.0-windows/NativeAclObserver.exe'
$script:events=New-Object Collections.Generic.List[object]
$script:sessions=New-Object Collections.Generic.List[object]
$current=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value # CI custodian, NOT non-admin proof
function Check([string]$Case,[bool]$Ok,$Details=$null){
 $script:events.Add([ordered]@{case=$Case;outcome=$(if($Ok){'PASS'}else{'FAIL'});head=$env:EXACT_HEAD_SHA;
  run_id=$env:GITHUB_RUN_ID;attempt=$env:GITHUB_RUN_ATTEMPT;kind='HOSTED_GUID_OBSERVER_TEST';
  host_verified=$false;physical_attestation=$false;apply_authorized=$false;execute_authorized=$false;cleanup_authorized=$false;payload=$script:lastObservation;details=$Details})
 if(!$Ok){throw ('CASE_FAILED:'+ $Case)}
}
function Observe([string]$Path){
 $args=@();if($Path){$args+=,$Path}
 $result=@(& $script:exe @args);$code=$LASTEXITCODE
 if($result.Count -ne 1){throw 'OBSERVER_JSON_REQUIRED'}
 $script:lastObservation=[pscustomobject]@{code=$code;value=($result[0]|ConvertFrom-Json)}
 return $script:lastObservation
}
function FixtureFile([string]$Name){
 $p=Join-Path $script:root $Name;[IO.File]::WriteAllText($p,'SYNTHETIC_ONLY');return $p
}
function Acl([string]$Path,[string]$Sddl){
 $full=[IO.Path]::GetFullPath($Path)
 if(!$full.StartsWith($script:root+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'OUTSIDE_GUID'}
 if((Get-Item -LiteralPath $full -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'SETUP_REPARSE'}
 $a=Get-Acl -LiteralPath $full;$a.SetSecurityDescriptorSddlForm($Sddl)
 Set-Acl -LiteralPath $full -AclObject $a -ErrorAction Stop
}
function Session([string]$Path){
 $si=New-Object Diagnostics.ProcessStartInfo
 $si.FileName=$script:exe;$si.Arguments='--session "'+$Path+'"';$si.UseShellExecute=$false
 $si.RedirectStandardInput=$true;$si.RedirectStandardOutput=$true;$si.RedirectStandardError=$true;$si.CreateNoWindow=$true
 $p=New-Object Diagnostics.Process;$p.StartInfo=$si
 if(!$p.Start()){throw 'OBSERVER_SESSION_START'};$script:sessions.Add($p)
 $null=$p.StandardError.ReadToEndAsync()
 $read=$p.StandardOutput.ReadLineAsync();if(!$read.Wait(15000)){throw 'SESSION_INITIAL_TIMEOUT'}
 $value=$read.Result|ConvertFrom-Json
 if($value.observation -cne 'HELD' -or $value.status -cne 'BLOCKED'){throw ('SESSION_NOT_HELD:'+ $value.reason)}
 return $p
}
function Recheck($Process){
 $stdout=$Process.StandardOutput.ReadToEndAsync()
 $Process.StandardInput.WriteLine('recheck');$Process.StandardInput.Flush()
 if(!$Process.WaitForExit(15000)){throw 'OBSERVER_SHUTDOWN_TIMEOUT'}
 if(!$stdout.Wait(15000)){throw 'OBSERVER_OUTPUT_TIMEOUT'}
 $s=$stdout.Result;$script:lastObservation=[pscustomobject]@{code=$Process.ExitCode;value=($s|ConvertFrom-Json)};return $script:lastObservation
}
try {
 $file=FixtureFile 'ordinary.txt';$r=Observe $file
 Check 'ordinary-read-only-observation' ($r.code -eq 0 -and $r.value.observation -ceq 'OBSERVED')
 Check 'authority-always-blocked' ($r.value.status -ceq 'BLOCKED' -and $r.value.host_verified -eq $false -and $r.value.apply_authorized -eq $false)
 $chain=@($r.value.chain)
 Check 'ancestor-file-identities' ($chain.Count -gt 3 -and @($chain|Where-Object {$_.identity.fileId -cnotmatch '^[0-9A-F]{32}$'}).Count -eq 0)
 Check 'owner-group-dacl-sids' (@($chain|Where-Object {$_.owner -notmatch '^S-1-' -or $_.group -notmatch '^S-1-' -or !$_.descriptorSha256 -or $null -eq $_.aces}).Count -eq 0)
 Check 'captured-token-context' ($r.value.token.user -ceq $current -and $r.value.token.groups.Count -gt 0)
 Check 'unknown-full-effective-rights-blocked' ($r.value.effectiveRightsStatus -ceq 'BLOCKED_MIC_ALL_PRINCIPALS_AND_PRIVILEGES_NOT_PROVEN')
 $bad=Observe '';Check 'missing-argument-refused' ($bad.code -eq 2 -and $bad.value.reason -ceq 'ARGUMENT_OR_PLATFORM')
 $bad=Observe 'relative';Check 'relative-path-refused' ($bad.code -eq 2 -and $bad.value.reason -ceq 'PATH_FORM')
 $bad=Observe (Join-Path $script:root 'missing');Check 'missing-object-api-failure' ($bad.code -eq 2 -and $bad.value.reason -ceq 'NT_OPEN_FAILED')
 $target=Join-Path $script:root 'target';$null=New-Item -ItemType Directory -Path $target
 $targetFile=Join-Path $target 'child';[IO.File]::WriteAllText($targetFile,'SYNTHETIC_ONLY')
 $j=Join-Path $script:root 'junction';$null=New-Item -ItemType Junction -Path $j -Value $target
 $bad=Observe $j;Check 'junction-refused' ($bad.code -eq 2 -and $bad.value.reason -cin @('REPARSE','NT_OPEN_FAILED'))
 $bad=Observe (Join-Path $j 'child');Check 'ancestor-junction-refused' ($bad.code -eq 2 -and $bad.value.reason -cin @('REPARSE','NT_OPEN_FAILED'))
 $l=Join-Path $script:root 'symlink';$null=New-Item -ItemType SymbolicLink -Path $l -Value $file
 $bad=Observe $l;Check 'symlink-refused' ($bad.code -eq 2 -and $bad.value.reason -cin @('REPARSE','NT_OPEN_FAILED'))
 $h=Join-Path $script:root 'hardlink';$null=New-Item -ItemType HardLink -Path $h -Value $file
 $bad=Observe $h;Check 'hardlink-refused' ($bad.code -eq 2 -and $bad.value.reason -ceq 'HARDLINK')
 $heldFile=FixtureFile 'held.txt';$p=Session $heldFile
 $err=0;try{[IO.File]::Move($heldFile,$heldFile+'.moved')}catch [IO.IOException]{$err=$_.Exception.HResult -band 0xffff}
 $end=Recheck $p;Check 'held-leaf-rename-denied' ($err -eq 32 -and $end.code -eq 0) @{rename_win32=$err}
 $dir=Join-Path $script:root 'held-parent';$null=New-Item -ItemType Directory -Path $dir
 $child=Join-Path $dir 'child';[IO.File]::WriteAllText($child,'SYNTHETIC_ONLY');$p=Session $child
 $err=0;try{[IO.Directory]::Move($dir,$dir+'.moved')}catch [IO.IOException]{$err=$_.Exception.HResult -band 0xffff}
 $end=Recheck $p;Check 'held-parent-rename-denied' ($err -eq 32 -and $end.code -eq 0) @{rename_win32=$err}
 $drift=FixtureFile 'drift';$p=Session $drift
 Acl $drift ('D:P(A;;FA;;;SY)(A;;FA;;;'+$current+')(A;;RC;;;WD)')
 $end=Recheck $p;Check 'descriptor-toctou-refused' ($end.code -eq 2 -and $end.value.reason -ceq 'OBSERVATION_CHANGED')
 $denied=FixtureFile 'group-deny'
 Acl $denied ('D:P(D;;0x2;;;WD)(A;;FA;;;SY)(A;;0x1200a9;;;'+$current+')(A;;0x2;;;WD)')
 $v=Observe $denied;Check 'group-deny-precedes-allow' ($v.code -eq 0 -and $v.value.chain[-1].effectiveRights.WRITE_DATA -ceq 'DACL_DENY')
 $allow=FixtureFile 'group-owner-write'
 Acl $allow ('D:P(A;;FA;;;SY)(A;;0x1200a9;;;'+$current+')(A;;0x80000;;;WD)')
 $v=Observe $allow;Check 'group-write-owner-detected' ($v.code -eq 0 -and $v.value.chain[-1].effectiveRights.WRITE_OWNER -ceq 'DACL_ALLOW')
 $v=Observe $allow;Check 'owner-write-dac-detected' ($v.code -eq 0 -and $v.value.chain[-1].effectiveRights.WRITE_DAC -ceq 'DACL_ALLOW')
 $parent=Join-Path $script:root 'delete-child';$null=New-Item -ItemType Directory -Path $parent
 $f=Join-Path $parent 'child';[IO.File]::WriteAllText($f,'SYNTHETIC_ONLY')
 Acl $f ('D:P(A;;FA;;;SY)(A;;0x1200a9;;;'+$current+')')
 Acl $parent ('D:P(A;;FA;;;SY)(A;;0x1200a9;;;'+$current+')(A;;0x40;;;WD)')
 $v=Observe $f;Check 'parent-delete-child-detected' ($v.code -eq 0 -and $v.value.chain[-2].effectiveRights.DELETE_CHILD -ceq 'DACL_ALLOW')
 $noRead=FixtureFile 'no-read-control'
 Acl $noRead ('D:P(D;;0x20000;;;OW)(A;;FA;;;SY)(A;;0x120089;;;'+$current+')')
 $v=Observe $noRead;Check 'read-control-denied-blocked' ($v.code -eq 2 -and $v.value.reason -ceq 'NT_OPEN_FAILED')
 foreach($fault in @('TOKEN_OPEN','TOKEN_QUERY','IDENTITY','DESCRIPTOR','ACCESS_CHECK','PRIVILEGE')){
  $result=@(& $script:exe --test-fault $fault $heldFile);$code=$LASTEXITCODE
  $script:lastObservation=[pscustomobject]@{code=$code;value=($result[0]|ConvertFrom-Json)}
  Check ('injected-'+$fault) ($code -eq 2 -and $script:lastObservation.value.reason -ceq ('INJECTED_'+$fault) -and $script:lastObservation.value.fault_injection -eq $true)
 }
 $null=Observe $heldFile;Check 'no-physical-attestation' $true
} finally {
 $releaseFailed=$false
 foreach($p in $script:sessions){
  if(!$p.HasExited){$p.StandardInput.Close();if(!$p.WaitForExit(25000)){$releaseFailed=$true}}
  if($p.HasExited){$p.Dispose()}
 }
 $lines=@($script:events|ForEach-Object {$_|ConvertTo-Json -Compress -Depth 32}) -join "`n"
 [IO.File]::WriteAllText((Join-Path $env:GITHUB_WORKSPACE 'native-observer.jsonl'),$lines+"`n",(New-Object Text.UTF8Encoding($false)))
 if($releaseFailed){throw 'SESSION_NOT_RELEASED'}
 # Retain every fixture. No cleanup, account changes or production claims.
}
$global:LASTEXITCODE=0
Write-Output ('NATIVE_GUID_CASES='+$script:events.Count+'; PHYSICAL_NOT_RUN; NO_AUTHORITY')
