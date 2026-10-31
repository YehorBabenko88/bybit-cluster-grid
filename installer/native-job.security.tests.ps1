# Actual harmless Windows child processes. No SDK qualification or services.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$NativeJobSha256)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or $env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or !$env:RUNNER_TEMP -or [Environment]::MachineName.Split('.')[0] -in @('ADMINIT','LS5','PC4')){throw 'HOSTED_WINDOWS_TEST_ONLY'}
Import-Module (Join-Path $PSScriptRoot 'PortableRuntime.psm1') -Force
Assert-PortableLocalPath $env:RUNNER_TEMP -MustExist
$fixtureRoot=Join-Path $env:RUNNER_TEMP ('native-job-tests-'+[Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($fixtureRoot) | Out-Null
$lease=$null;$phase='INITIALIZE'
try {
 Initialize-PortableJob (Join-Path $PSScriptRoot 'NativeJobProcess.cs') $NativeJobSha256
 # This is a real minimal executable compiled only in the hosted test namespace.
 # The orphan case explicitly inherits actual stdout/stderr. The retained
 # case deliberately has no inherited handles, no STARTF_USESTDHANDLES and
 # DETACHED_PROCESS; Job membership is independent of handle inheritance.
 $phase='COMPILE_FIXTURE'
 $source=@'
using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Runtime.InteropServices;
class HeartbeatFixture {
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)]struct SI {public int cb;public string reserved,desktop,title;public int x,y,xs,ys,xc,yc,fill,flags;public short show,cb2;public IntPtr reserved2,input,output,error;}
 [StructLayout(LayoutKind.Sequential)]struct PI {public IntPtr process,thread;public uint pid,tid;}
 [DllImport("kernel32.dll")]static extern IntPtr GetStdHandle(int which);
 [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr handle);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern bool CreateProcess(string app,StringBuilder cmd,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr env,string cwd,ref SI startup,out PI process);
 static int Main(string[] args) {
  if(args[0]=="marker"){File.WriteAllText(args[1],"RESUMED");return 0;}
  if(args[0]=="child"||args[0]=="closed-child"){
   if(args[0]=="closed-child"){CloseHandle(GetStdHandle(-11));CloseHandle(GetStdHandle(-12));}
   for(int i=0;i<600;i++){File.AppendAllText(args[1],"x");Thread.Sleep(25);}return 0;
  }
  SI si=new SI();si.cb=Marshal.SizeOf(typeof(SI));PI pi;
  bool nonzero=args[0]=="nonzero";bool retained=args[0]=="retained"||nonzero;
  if(!retained){si.flags=0x100;si.input=GetStdHandle(-10);si.output=GetStdHandle(-11);si.error=GetStdHandle(-12);}
  string exe=System.Reflection.Assembly.GetExecutingAssembly().Location;
  string child=retained?"closed-child":"child";
  if(!CreateProcess(exe,new StringBuilder("\""+exe+"\" "+child+" \""+args[1]+"\""),IntPtr.Zero,IntPtr.Zero,!retained,retained?8u:0u,IntPtr.Zero,Environment.CurrentDirectory,ref si,out pi))return 7;
  CloseHandle(pi.thread);CloseHandle(pi.process);
  if(nonzero){for(int i=0;i<100&&!File.Exists(args[1]);i++)Thread.Sleep(20);if(!File.Exists(args[1]))return 9;Console.WriteLine("BOUNDED_FAILURE_FIXTURE");Console.Error.WriteLine("BOUNDED_FAILURE_STDERR");return 7;}
  return 0;
 }
}
'@
 $exe=Join-Path $fixtureRoot 'heartbeat.exe'
 # Use the Windows .NET Framework compiler so the fixture is a directly
 # executable CLR program under both PS5 and PS7 (no CoreCLR apphost assumption).
 $compiler=Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::Windows)) 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
 Assert-PortableLocalPath $compiler -MustExist
 $sourceFile=Join-Path $fixtureRoot 'heartbeat.cs';[IO.File]::WriteAllText($sourceFile,$source)
 $compilerOutput= & $compiler /nologo /target:exe ('/out:'+$exe) $sourceFile 2>&1
 if($LASTEXITCODE -ne 0 -or ![IO.File]::Exists($exe)){throw 'HARMLESS_FIXTURE_COMPILE_FAILED'}
 $environment=[Collections.Generic.Dictionary[string,string]]::new([StringComparer]::OrdinalIgnoreCase)
 $environment.Add('SystemRoot',[Environment]::GetFolderPath([Environment+SpecialFolder]::Windows))
 $environment.Add('TEMP',$fixtureRoot);$environment.Add('TMP',$fixtureRoot)
 $phase='ORPHAN_DEADLINE'
 $heartbeat=Join-Path $fixtureRoot 'orphan-heartbeat'
 $deadlineDenied=$false
 try{$unexpected=[GridPortable.JobProcess]::Run($exe,('parent "'+$heartbeat+'"'),$fixtureRoot,$environment,2,$false);$unexpected.Dispose()}catch{if($_.Exception.ToString() -notmatch 'JOB_DEADLINE'){throw};$deadlineDenied=$true}
 if(!$deadlineDenied -or ![IO.File]::Exists($heartbeat)){throw 'REAL_CHILD_DEADLINE_NOT_EXERCISED'}
 $before=([IO.FileInfo]$heartbeat).Length;Start-Sleep -Milliseconds 700
 if(([IO.FileInfo]$heartbeat).Length -ne $before){throw 'ORPHAN_SURVIVED_JOB_CLOSE'}
 # A successful root with a detached child and NO inherited handles may retain its Job
 # for PG-style lifetime; disposal must still own and kill that living child.
 $phase='RETAINED_LIFETIME'
 $retained=Join-Path $fixtureRoot 'retained-heartbeat'
 $lease=[GridPortable.JobProcess]::Run($exe,('retained "'+$retained+'"'),$fixtureRoot,$environment,5,$true)
 Start-Sleep -Milliseconds 300
 if(![IO.File]::Exists($retained)){throw 'RETAINED_CHILD_NOT_STARTED'}
 $before=([IO.FileInfo]$retained).Length;Start-Sleep -Milliseconds 300
 if(([IO.FileInfo]$retained).Length -le $before){throw 'RETAINED_JOB_CLOSED_EARLY'}
 $lease.Dispose();$lease=$null;Start-Sleep -Milliseconds 300
 $before=([IO.FileInfo]$retained).Length;Start-Sleep -Milliseconds 500
 if(([IO.FileInfo]$retained).Length -ne $before){throw 'RETAINED_CHILD_SURVIVED_CLOSE'}
 # Actual AssignProcessToJobObject failure, not a callback or mocked result.
 # The new root exists suspended; a disposed Job's invalid handle cannot own it.
 $phase='ASSIGNMENT_DENY'
 $marker=Join-Path $fixtureRoot 'must-never-resume'
 $closed=[GridPortable.OwnedJob]::new();$closed.Dispose();$assignmentDenied=$false
 try{$unexpected=[GridPortable.JobProcess]::RunInJob($exe,('marker "'+$marker+'"'),$fixtureRoot,$environment,5,$false,$closed);$unexpected.Dispose()}catch{if($_.Exception.ToString() -notmatch 'JOB_ASSIGN'){throw};$assignmentDenied=$true}
 Start-Sleep -Milliseconds 300
 if(!$assignmentDenied -or [IO.File]::Exists($marker)){throw 'UNOWNED_PROCESS_RESUMED'}
 $phase='NONZERO_PRIVATE_RESULT'
 $failedHeartbeat=Join-Path $fixtureRoot 'nonzero-heartbeat';$privateResult=$null
 try{$unexpected=[GridPortable.JobProcess]::Run($exe,('nonzero "'+$failedHeartbeat+'"'),$fixtureRoot,$environment,5,$false);$unexpected.Dispose()}catch{
  $errorNode=$_.Exception
  for($depth=0;$null -ne $errorNode -and $depth -lt 8;$depth++){
   if($errorNode.Data.Contains('GridPortable.BoundedResult')){$privateResult=$errorNode.Data['GridPortable.BoundedResult'];break}
   $errorNode=$errorNode.InnerException
  }
  if($null -eq $privateResult){throw}
 }
 if($privateResult -isnot [GridPortable.JobResult] -or $privateResult.ExitCode -ne 7 -or $privateResult.Stdout.Trim() -cne 'BOUNDED_FAILURE_FIXTURE' -or $privateResult.Stderr.Trim() -cne 'BOUNDED_FAILURE_STDERR' -or $null -ne $privateResult.Job -or ![IO.File]::Exists($failedHeartbeat)){throw 'NONZERO_PRIVATE_RESULT_INVALID'}
 Start-Sleep -Milliseconds 300;$before=([IO.FileInfo]$failedHeartbeat).Length;Start-Sleep -Milliseconds 500
 if(([IO.FileInfo]$failedHeartbeat).Length -ne $before){throw 'NONZERO_CHILD_SURVIVED_CLOSE'}
 [pscustomobject]@{schema='grid.native-job-tests.v1';scope='HARMLESS_PROCESS_CONTAINMENT_ONLY';passed=4;sdk_qualification='NOT_RUN';physical='NOT_RUN'} | ConvertTo-Json -Compress
}catch{
 $classification='UNKNOWN'
 $detail=$_.Exception.ToString()
 foreach($code in @('JOB_DEADLINE','JOB_OUTPUT_LIMIT','JOB_ASSIGN','PROCESS_CREATE_SUSPENDED','PROCESS_RESUME','JOB_CREATE','JOB_LIMIT','ATTRIBUTE_INIT','ATTRIBUTE_HANDLES','PIPE_CREATE','PIPE_FLAGS','JOB_PROCESS_FAILED','HARMLESS_FIXTURE_COMPILE_FAILED','REAL_CHILD_DEADLINE_NOT_EXERCISED','ORPHAN_SURVIVED_JOB_CLOSE','RETAINED_CHILD_NOT_STARTED','RETAINED_JOB_CLOSED_EARLY','RETAINED_CHILD_SURVIVED_CLOSE','UNOWNED_PROCESS_RESUMED','NONZERO_PRIVATE_RESULT_INVALID','NONZERO_CHILD_SURVIVED_CLOSE')){if($detail.Contains($code)){$classification=$code;break}}
 Write-Output "::error title=Native Job subcase::phase=$phase code=$classification line=$([int]$_.InvocationInfo.ScriptLineNumber)"
 throw
}finally{
 if($null -ne $lease){$lease.Dispose()}
 if([IO.Directory]::Exists($fixtureRoot)){Assert-PortableLocalPath $fixtureRoot -MustExist;Remove-Item -LiteralPath $fixtureRoot -Recurse -Force}
}
