#Requires -Version 5.1
# Standalone minimal invocation: no Grid CLI/config/network/DB; hosted fixture only.
param([string]$Root,[string]$Head,[string]$Sid,[string]$ImageSha,[string]$PackageSha,[string]$Evidence)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if([Environment]::GetEnvironmentVariable('GITHUB_ACTIONS','Process') -cne 'true' -or [Environment]::GetEnvironmentVariable('RUNNER_ENVIRONMENT','Process') -cne 'github-hosted' -or [Environment]::GetEnvironmentVariable('GITHUB_JOB','Process') -cne 's0-windows' -or [Environment]::GetEnvironmentVariable('GITHUB_REPOSITORY','Process') -cne 'YehorBabenko88/bybit-cluster-grid' -or [Environment]::GetEnvironmentVariable('EXACT_HEAD_SHA','Process') -cne $Head -or [Environment]::MachineName -in @('LS5','PC4')){throw 'PROBE_HOSTED_ONLY'}
if($Head -cnotmatch '^[0-9a-f]{40}$' -or $PackageSha -cnotmatch '^[0-9a-f]{64}$' -or $ImageSha -cnotmatch '^[0-9a-f]{64}$'){throw 'PROBE_PINS'}
$evidenceParent=[IO.Directory]::GetParent($Evidence)
if(!$evidenceParent -or $evidenceParent.Name -cne 'temp' -or $evidenceParent.Parent.Name -cnotmatch '^s0-maintenance-[0-9a-f-]{36}$'){throw 'PROBE_FIXTURE_ONLY'}
$log=[IO.File]::Open($Evidence,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
function Trace([string]$Stage){$raw=[Text.Encoding]::ASCII.GetBytes('{"scope":"HOSTED_DIAGNOSTIC_NOT_ACCEPTANCE","stage":"'+$Stage+'"}'+"`n");$log.Write($raw,0,$raw.Length);$log.Flush($true)}
try{
 Trace 'SHELL_ENTER'
 Add-Type -AssemblyName System.IO.Compression
 $zipBytes=[IO.File]::ReadAllBytes((Join-Path $Root 'source.zip'))
 $hash=[Security.Cryptography.SHA256]::Create()
 try{$actual=([BitConverter]::ToString($hash.ComputeHash($zipBytes))).Replace('-','').ToLowerInvariant()}finally{$hash.Dispose()}
 if($actual -cne $PackageSha){throw 'PROBE_ZIP_HASH'}
 Trace 'SOURCE_ZIP_PINNED'
 $memory=New-Object IO.MemoryStream(,$zipBytes);$archive=New-Object IO.Compression.ZipArchive($memory,[IO.Compression.ZipArchiveMode]::Read,$true)
 try{
  $entries=@($archive.Entries|Where-Object FullName -CEQ 'native/S0Launcher.dll')
  if($entries.Count -ne 1 -or $entries[0].Length -gt 4194304){throw 'PROBE_HELPER_BOUND'}
  $input=$entries[0].Open();$copy=New-Object IO.MemoryStream
  try{$input.CopyTo($copy);$helper=$copy.ToArray()}finally{$input.Dispose();$copy.Dispose()}
 }finally{$archive.Dispose();$memory.Dispose()}
 [void][Reflection.Assembly]::Load($helper)
 Trace 'NATIVE_ASSEMBLY_LOADED'
 $envBlock=@{}
 foreach($key in @('SystemRoot','WINDIR','USERPROFILE','LOCALAPPDATA','USERNAME','COMPUTERNAME')){$envBlock[$key]=[Environment]::GetEnvironmentVariable($key,'Process')}
 $envBlock['TEMP']=[IO.Directory]::GetParent($Evidence).FullName;$envBlock['TMP']=$envBlock['TEMP'];$envBlock['PATH']=[Environment]::SystemDirectory
 Trace 'NATIVE_HANDOFF_BEGIN'
 # Same native launcher and package custody, only Python body reduced to immediate exit.
 $result=[GridS0.ProcessHost]::RunAtUserProfileV1($Root,'-I -S -B -c "raise SystemExit(0)"',$envBlock,$Sid,$ImageSha,$Head,5,$PackageSha)
 Trace 'NATIVE_HANDOFF_RETURN'
 $facts=[ordered]@{scope='HOSTED_DIAGNOSTIC_NOT_ACCEPTANCE';stage='OWN_NATIVE_CHILD_IDENTITY';pid=$result.Pid;creation_filetime=$result.CreationFileTime;exit_code=$result.ExitCode;timed_out=$result.TimedOut;job_member=$result.JobMember}
 $factsBytes=[Text.Encoding]::ASCII.GetBytes(($facts|ConvertTo-Json -Compress)+"`n");$log.Write($factsBytes,0,$factsBytes.Length);$log.Flush($true)
 if($result.TimedOut -or $result.ExitCode -ne 0 -or !$result.JobMember -or $result.ObservedElevated -or $result.ObservedAdminEnabled){throw 'PROBE_CHILD_FAILED'}
 Trace 'CHILD_EXIT_VERIFIED'
}catch{
 Trace 'PROBE_BLOCKED';throw 'PROBE_BLOCKED'
}finally{$log.Dispose()}
