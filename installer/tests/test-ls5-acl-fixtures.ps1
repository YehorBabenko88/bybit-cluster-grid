#Requires -Version 5.1
# Structural ACL tests ONLY in a fresh hosted-CI GUID fixture. No user creation,
# task/service operations, production paths, physical token proof or cleanup.
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
 $env:RUNNER_OS -cne 'Windows' -or $env:GITHUB_REPOSITORY -cne 'YehorBabenko88/bybit-cluster-grid' -or
 $env:GITHUB_JOB -cne 'windows-acl-fixtures' -or $env:GITHUB_RUN_ID -cnotmatch '^[1-9][0-9]*$' -or
 $env:EXACT_HEAD_SHA -cnotmatch '^[0-9a-f]{40}$') {throw 'HOSTED_GUID_FIXTURE_ONLY_BEFORE_MUTATION'}
$temp=[IO.Path]::GetFullPath($env:RUNNER_TEMP)
if((Get-Item -LiteralPath $temp -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'TEMP_REPARSE_BLOCKED'}
$script:root=Join-Path $temp ('grid-ls5-acl-'+[guid]::NewGuid().ToString('D'))
if(![IO.Path]::GetFullPath($script:root).StartsWith($temp.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'FIXTURE_SCOPE_BLOCKED'}
$null=New-Item -ItemType Directory -Path $script:root -ErrorAction Stop
$custodian=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value # CI fixture custodian only
$script:events=New-Object Collections.Generic.List[object]
function Check([string]$Case,[bool]$Pass){
 $script:events.Add([ordered]@{case=$Case;outcome=$(if($Pass){'PASS'}else{'FAIL'});
  head=$env:EXACT_HEAD_SHA;run_id=$env:GITHUB_RUN_ID;attempt=$env:GITHUB_RUN_ATTEMPT;
  scope='HOSTED_GUID_ACL_LAYOUT_ONLY';host_verified=$false;physical_attestation=$false;
  execute_authorized=$false;cleanup_authorized=$false})
 if(!$Pass){throw 'FIXTURE_ASSERT_FAILED'}
}
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class GridAclFixtureInfo {
 [StructLayout(LayoutKind.Sequential)] struct Info {public uint A,C1,C2,A1,A2,W1,W2,V,S1,S2,L,I1,I2;}
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetFileInformationByHandle(SafeFileHandle h,out Info i);
 public static uint Links(string path) {
  using(var f=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.ReadWrite)) {
   Info i;if(!GetFileInformationByHandle(f.SafeFileHandle,out i))throw new InvalidOperationException("FIXTURE_INFO_FAILED");return i.L;
  }
 }
}
'@
function Assert-Scope([string]$Path){
 $full=[IO.Path]::GetFullPath($Path)
 if($full -cne $script:root -and !$full.StartsWith($script:root+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'OUTSIDE_FIXTURE'}
 $cursor=$full
 while($cursor.StartsWith($script:root,[StringComparison]::OrdinalIgnoreCase)){
  $i=Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
  if($i.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'REPARSE_BLOCKED'}
  if($cursor -ceq $script:root){break};$cursor=Split-Path $cursor -Parent
 }
 $item=Get-Item -LiteralPath $full -Force
 if(!$item.PSIsContainer -and [GridAclFixtureInfo]::Links($full) -ne 1){throw 'HARDLINK_BLOCKED'}
}
function Has-Users([string]$Path,[int64]$Mask){
 $a=Get-Acl -LiteralPath $Path
 return @($a.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])|Where-Object {
  $_.IdentityReference.Value -ceq 'S-1-5-32-545' -and $_.AccessControlType -eq 'Allow' -and
  (([int64]$_.FileSystemRights -band $Mask) -ne 0)}).Count -gt 0
}
function Policy([string]$Path,[switch]$BeforeSetFault){
 Assert-Scope $Path
 $i=Get-Item -LiteralPath $Path;$a=Get-Acl -LiteralPath $Path
 $a.SetAccessRuleProtection($true,$false)
 foreach($r in @($a.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))){$null=$a.RemoveAccessRuleSpecific($r)}
 $flags=if($i.PSIsContainer){[Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'}else{[Security.AccessControl.InheritanceFlags]::None}
 foreach($sid in @('S-1-5-18','S-1-5-32-544',$custodian)|Select-Object -Unique){
  $id=New-Object Security.Principal.SecurityIdentifier($sid)
  $rule=New-Object Security.AccessControl.FileSystemAccessRule($id,'FullControl',$flags,'None','Allow');$a.AddAccessRule($rule)
 }
 if($BeforeSetFault){throw 'INJECTED_BEFORE_SET'}
 Set-Acl -LiteralPath $Path -AclObject $a -ErrorAction Stop
}
function Reject([string]$Case,[scriptblock]$Action){$failed=$false;try{& $Action|Out-Null}catch{$failed=$true};Check $Case $failed}
try {
 Policy $script:root
 $a=Get-Acl -LiteralPath $script:root
 $users=New-Object Security.Principal.SecurityIdentifier('S-1-5-32-545')
 $a.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($users,'ReadAndExecute','ContainerInherit,ObjectInherit','None','Allow')))
 $a.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($users,'Write','ContainerInherit','None','Allow')))
 Set-Acl -LiteralPath $script:root -AclObject $a
 $dir=Join-Path $script:root 'runtime';$null=New-Item -ItemType Directory -Path $dir
 $file=Join-Path $dir 'synthetic.py';[IO.File]::WriteAllText($file,'SYNTHETIC_ONLY')
 $envFile=Join-Path $script:root 'synthetic.env';[IO.File]::WriteAllText($envFile,'NO_REAL_SECRETS')
 Check 'inherited-directory-write' (Has-Users $dir 2)
 Check 'leaf-rx-does-not-prove-parent-safe' (!(Has-Users $file 2) -and (Has-Users $file 0x20))
 Check 'env-readable-before' (Has-Users $envFile 1)
 $before=(Get-Acl -LiteralPath $envFile).Sddl
 Reject 'partial-before-set-fault' {Policy $envFile -BeforeSetFault}
 Check 'failure-preserves-original' ((Get-Acl -LiteralPath $envFile).Sddl -ceq $before)
 Policy $envFile
 Check 'secret-users-removed' (!(Has-Users $envFile 0x1F01FF))
 $restore=Get-Acl -LiteralPath $envFile;$restore.SetSecurityDescriptorSddlForm($before)
 Assert-Scope $envFile;Set-Acl -LiteralPath $envFile -AclObject $restore
 Check 'fixture-only-sddl-rollback' ((Get-Acl -LiteralPath $envFile).Sddl -ceq $before)
 foreach($path in @($script:root,$dir,$file,$envFile)){Policy $path}
 Check 'all-users-removed' (!(Has-Users $dir 0x1F01FF) -and !(Has-Users $file 0x1F01FF) -and !(Has-Users $envFile 0x1F01FF))
 $after=(Get-Acl -LiteralPath $dir).Sddl;Policy $dir
 Check 'idempotent-repeat' ((Get-Acl -LiteralPath $dir).Sddl -ceq $after)
 $new=Join-Path $dir 'new-release.py';[IO.File]::WriteAllText($new,'NEW_SYNTHETIC_RELEASE')
 Check 'new-release-inherits-no-users-write' (!(Has-Users $new 0x1F01FF))
 $target=Join-Path $script:root 'target';$null=New-Item -ItemType Directory -Path $target
 $junction=Join-Path $script:root 'junction';$null=New-Item -ItemType Junction -Path $junction -Value $target
 Reject 'junction-blocked' {Policy $junction}
 $symlink=Join-Path $script:root 'symlink';$null=New-Item -ItemType SymbolicLink -Path $symlink -Value $file
 Reject 'symlink-blocked' {Policy $symlink}
 $hardlink=Join-Path $script:root 'hardlink';$null=New-Item -ItemType HardLink -Path $hardlink -Value $file
 Check 'hardlink-count-observed' ([GridAclFixtureInfo]::Links($file) -eq 2)
 Reject 'hardlink-blocked' {Policy $hardlink}
 Reject 'system-root-outside-fixture-blocked' {Policy 'C:\ProgramData'}
 Check 'evidence-not-physical' $true
} finally {
 $lines=@($script:events|ForEach-Object {$_|ConvertTo-Json -Compress}) -join "`n"
 [IO.File]::WriteAllText((Join-Path $env:GITHUB_WORKSPACE 'ls5-acl-windows.jsonl'),$lines+"`n",(New-Object Text.UTF8Encoding($false)))
 # Intentionally retain fixtures; never recurse/delete or infer resource ownership.
}
Write-Output ('WINDOWS_GUID_ACL_CASES='+$script:events.Count+'; STRUCTURAL_ONLY; PHYSICAL_NOT_RUN')
