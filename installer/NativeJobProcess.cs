// C# 5 / .NET Framework compatible. Loaded only by explicit ephemeral execution.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Win32.SafeHandles;
namespace GridPortable {
 public sealed class OwnedJob : IDisposable {
  internal IntPtr Handle;
  public OwnedJob() {
   Handle=Native.CreateJobObject(IntPtr.Zero,null);
   if(Handle==IntPtr.Zero) throw Native.Error("JOB_CREATE");
   Native.JOBOBJECT_EXTENDED_LIMIT_INFORMATION info=new Native.JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
   info.BasicLimitInformation.LimitFlags=0x2000; // KILL_ON_JOB_CLOSE
   int size=Marshal.SizeOf(typeof(Native.JOBOBJECT_EXTENDED_LIMIT_INFORMATION));IntPtr p=Marshal.AllocHGlobal(size);
   try {Marshal.StructureToPtr(info,p,false);if(!Native.SetInformationJobObject(Handle,9,p,(uint)size))throw Native.Error("JOB_LIMIT");}
   catch {Dispose();throw;} finally {Marshal.FreeHGlobal(p);}
  }
  public void Dispose(){IntPtr h=Interlocked.Exchange(ref Handle,IntPtr.Zero);if(h!=IntPtr.Zero)Native.CloseHandle(h);}
 }
 [Serializable]
 public sealed class JobResult : IDisposable {
  public string Stdout;public string Stderr;public int ExitCode;[NonSerialized] public OwnedJob Job;
  public void Dispose(){if(Job!=null){Job.Dispose();Job=null;}}
 }
 public static class JobProcess {
  sealed class Drain {
   internal MemoryStream Data=new MemoryStream();internal volatile bool Overflow;internal Task Task;
   internal Drain(IntPtr handle){
    FileStream stream=new FileStream(new SafeFileHandle(handle,true),FileAccess.Read,4096,false);
    Task=System.Threading.Tasks.Task.Factory.StartNew(delegate {
     try {using(stream){byte[] b=new byte[4096];int n;while((n=stream.Read(b,0,b.Length))>0){if(Data.Length+n>65536){Overflow=true;break;}Data.Write(b,0,n);}}}
     catch {Overflow=true;}
    },CancellationToken.None,TaskCreationOptions.LongRunning,TaskScheduler.Default);
   }
  }
  public static JobResult Run(string executable,string arguments,string directory,IDictionary<string,string> environment,int seconds,bool retain) {
   return RunInJob(executable,arguments,directory,environment,seconds,retain,new OwnedJob());
  }
  // Caller may supply an owned Job; failure always closes it. A closed Job must
  // fail AssignProcessToJobObject while the new process is still suspended.
  public static JobResult RunInJob(string executable,string arguments,string directory,IDictionary<string,string> environment,int seconds,bool retain,OwnedJob job) {
   return RunCore(executable,arguments,directory,environment,seconds,retain,job,false);
  }
  public static JobResult RunDaemon(string executable,string arguments,string directory,IDictionary<string,string> environment,int seconds) {
   return RunCore(executable,arguments,directory,environment,seconds,true,new OwnedJob(),true);
  }
  static JobResult RunCore(string executable,string arguments,string directory,IDictionary<string,string> environment,int seconds,bool retain,OwnedJob job,bool daemonStdio) {
   if(seconds<1||seconds>180||job==null)throw new ArgumentException("JOB_ARGUMENT");
   IntPtr outRead=IntPtr.Zero,outWrite=IntPtr.Zero,errRead=IntPtr.Zero,errWrite=IntPtr.Zero,inRead=IntPtr.Zero,inWrite=IntPtr.Zero;
   IntPtr attributes=IntPtr.Zero,list=IntPtr.Zero,env=IntPtr.Zero;Native.PROCESS_INFORMATION pi=new Native.PROCESS_INFORMATION();
   Drain stdout=null,stderr=null;bool success=false,attributeReady=false;
   Stopwatch watch=Stopwatch.StartNew();
   try {
    Native.SECURITY_ATTRIBUTES sa=new Native.SECURITY_ATTRIBUTES();sa.nLength=Marshal.SizeOf(typeof(Native.SECURITY_ATTRIBUTES));sa.bInheritHandle=true;
    if(daemonStdio){
     // Fixed kernel NUL device only, never a caller-selected file. A daemon may
     // inherit these handles without retaining anonymous capture-pipe writers.
     inRead=Native.OpenNull(0x80000000,ref sa);outWrite=Native.OpenNull(0x40000000,ref sa);errWrite=Native.OpenNull(0x40000000,ref sa);
    }else{
     if(!Native.CreatePipe(out outRead,out outWrite,ref sa,0)||!Native.CreatePipe(out errRead,out errWrite,ref sa,0)||!Native.CreatePipe(out inRead,out inWrite,ref sa,0))throw Native.Error("PIPE_CREATE");
     if(!Native.SetHandleInformation(outRead,1,0)||!Native.SetHandleInformation(errRead,1,0)||!Native.SetHandleInformation(inWrite,1,0))throw Native.Error("PIPE_FLAGS");
     Native.Close(ref inWrite); // stdin is EOF; never inherit caller input.
    }
    IntPtr bytes=IntPtr.Zero;Native.InitializeProcThreadAttributeList(IntPtr.Zero,1,0,ref bytes);
    list=Marshal.AllocHGlobal(bytes);if(!Native.InitializeProcThreadAttributeList(list,1,0,ref bytes))throw Native.Error("ATTRIBUTE_INIT");attributeReady=true;
    attributes=Marshal.AllocHGlobal(IntPtr.Size*3);Marshal.WriteIntPtr(attributes,0,inRead);Marshal.WriteIntPtr(attributes,IntPtr.Size,outWrite);Marshal.WriteIntPtr(attributes,IntPtr.Size*2,errWrite);
    if(!Native.UpdateProcThreadAttribute(list,0,(IntPtr)0x20002,attributes,(IntPtr)(IntPtr.Size*3),IntPtr.Zero,IntPtr.Zero))throw Native.Error("ATTRIBUTE_HANDLES");
    Native.STARTUPINFOEX si=new Native.STARTUPINFOEX();si.StartupInfo.cb=Marshal.SizeOf(typeof(Native.STARTUPINFOEX));si.StartupInfo.dwFlags=0x100;si.StartupInfo.hStdInput=inRead;si.StartupInfo.hStdOutput=outWrite;si.StartupInfo.hStdError=errWrite;si.lpAttributeList=list;
    SortedDictionary<string,string> sorted=new SortedDictionary<string,string>(StringComparer.OrdinalIgnoreCase);
    foreach(KeyValuePair<string,string> pair in environment){if(pair.Key.IndexOfAny(new char[]{'=', '\0'})>=0||pair.Value.IndexOf('\0')>=0)throw new ArgumentException("ENVIRONMENT_INVALID");sorted.Add(pair.Key,pair.Value);}
    StringBuilder block=new StringBuilder();foreach(KeyValuePair<string,string> pair in sorted)block.Append(pair.Key).Append('=').Append(pair.Value).Append('\0');block.Append('\0');env=Marshal.StringToHGlobalUni(block.ToString());
    StringBuilder command=new StringBuilder("\""+executable+"\" "+arguments);
    if(!Native.CreateProcess(executable,command,IntPtr.Zero,IntPtr.Zero,true,0x00080000|0x00000400|0x00000004|0x08000000,env,directory,ref si,out pi))throw Native.Error("PROCESS_CREATE_SUSPENDED");
    // No application instruction has run. Never resume before ownership.
    if(!Native.AssignProcessToJobObject(job.Handle,pi.hProcess))throw Native.Error("JOB_ASSIGN");
    Native.Close(ref outWrite);Native.Close(ref errWrite);Native.Close(ref inRead);
    if(!daemonStdio){stdout=new Drain(outRead);outRead=IntPtr.Zero;stderr=new Drain(errRead);errRead=IntPtr.Zero;}
    if(Native.ResumeThread(pi.hThread)==0xffffffff)throw Native.Error("PROCESS_RESUME");Native.Close(ref pi.hThread);
    while(true){
     if(!daemonStdio&&(stdout.Overflow||stderr.Overflow))throw new InvalidOperationException("JOB_OUTPUT_LIMIT");
     bool exited=Native.WaitForSingleObject(pi.hProcess,0)==0;
     bool stdoutDone=daemonStdio||stdout.Task.IsCompleted,stderrDone=daemonStdio||stderr.Task.IsCompleted;
     if(exited&&stdoutDone&&stderrDone)break;
     if(watch.Elapsed.TotalSeconds>seconds){TimeoutException failure=new TimeoutException("JOB_DEADLINE");failure.Data["GridPortable.DeadlineState"]=new bool[]{exited,stdoutDone,stderrDone};throw failure;}Thread.Sleep(10);
    }
    uint code;if(!Native.GetExitCodeProcess(pi.hProcess,out code))throw Native.Error("PROCESS_EXIT_CODE");
    JobResult result=new JobResult();result.ExitCode=unchecked((int)code);result.Stdout=daemonStdio?String.Empty:Encoding.UTF8.GetString(stdout.Data.ToArray());result.Stderr=daemonStdio?String.Empty:Encoding.UTF8.GetString(stderr.Data.ToArray());
    if(code!=0){InvalidOperationException failure=new InvalidOperationException("JOB_PROCESS_FAILED");failure.Data["GridPortable.BoundedResult"]=result;throw failure;}
    if(retain)result.Job=job;else job.Dispose();success=true;return result;
   } finally {
    if(!success){
     // Includes Assign failure: terminate suspended root even if not in Job.
     if(pi.hProcess!=IntPtr.Zero)Native.TerminateProcess(pi.hProcess,1);
     job.Dispose();
    }
    Native.Close(ref outRead);Native.Close(ref outWrite);Native.Close(ref errRead);Native.Close(ref errWrite);Native.Close(ref inRead);Native.Close(ref inWrite);
    if(pi.hProcess!=IntPtr.Zero){Native.WaitForSingleObject(pi.hProcess,3000);Native.Close(ref pi.hProcess);}Native.Close(ref pi.hThread);
    // Closing the Job releases inherited pipe writers, including orphaned children.
    foreach(Drain drain in new Drain[]{stdout,stderr})if(drain!=null){if(drain.Task.Wait(3000))drain.Data.Dispose();}
    if(list!=IntPtr.Zero){if(attributeReady)Native.DeleteProcThreadAttributeList(list);Marshal.FreeHGlobal(list);}if(attributes!=IntPtr.Zero)Marshal.FreeHGlobal(attributes);if(env!=IntPtr.Zero)Marshal.FreeHGlobal(env);
   }
  }
 }
 internal static class Native {
  internal static IntPtr OpenNull(uint access,ref SECURITY_ATTRIBUTES attributes){
   IntPtr handle=CreateFile(@"\\.\NUL",access,3,ref attributes,3,0x80,IntPtr.Zero);
   if(handle==new IntPtr(-1))throw Error("NULL_STDIO_CREATE");return handle;
  }
  internal static Exception Error(string label){return new InvalidOperationException(label+":"+Marshal.GetLastWin32Error());}
  internal static void Close(ref IntPtr h){if(h!=IntPtr.Zero){CloseHandle(h);h=IntPtr.Zero;}}
  [StructLayout(LayoutKind.Sequential)] internal struct SECURITY_ATTRIBUTES{internal int nLength;internal IntPtr lpSecurityDescriptor;[MarshalAs(UnmanagedType.Bool)]internal bool bInheritHandle;}
  [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)]internal struct STARTUPINFO{internal int cb;internal string lpReserved,lpDesktop,lpTitle;internal int dwX,dwY,dwXSize,dwYSize,dwXCountChars,dwYCountChars,dwFillAttribute,dwFlags;internal short wShowWindow,cbReserved2;internal IntPtr lpReserved2,hStdInput,hStdOutput,hStdError;}
  [StructLayout(LayoutKind.Sequential)]internal struct STARTUPINFOEX{internal STARTUPINFO StartupInfo;internal IntPtr lpAttributeList;}
  [StructLayout(LayoutKind.Sequential)]internal struct PROCESS_INFORMATION{internal IntPtr hProcess,hThread;internal uint dwProcessId,dwThreadId;}
  [StructLayout(LayoutKind.Sequential)]internal struct JOBOBJECT_BASIC_LIMIT_INFORMATION{internal long PerProcessUserTimeLimit,PerJobUserTimeLimit;internal uint LimitFlags;internal UIntPtr MinimumWorkingSetSize,MaximumWorkingSetSize;internal uint ActiveProcessLimit;internal UIntPtr Affinity;internal uint PriorityClass,SchedulingClass;}
  [StructLayout(LayoutKind.Sequential)]internal struct IO_COUNTERS{internal ulong ReadOperationCount,WriteOperationCount,OtherOperationCount,ReadTransferCount,WriteTransferCount,OtherTransferCount;}
  [StructLayout(LayoutKind.Sequential)]internal struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION{internal JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;internal IO_COUNTERS IoInfo;internal UIntPtr ProcessMemoryLimit,JobMemoryLimit,PeakProcessMemoryUsed,PeakJobMemoryUsed;}
  [DllImport("kernel32.dll",SetLastError=true,CharSet=CharSet.Unicode)]internal static extern IntPtr CreateJobObject(IntPtr attributes,string name);
  [DllImport("kernel32.dll",SetLastError=true)]internal static extern bool SetInformationJobObject(IntPtr job,int type,IntPtr info,uint size);
  [DllImport("kernel32.dll",SetLastError=true)]internal static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
  [DllImport("kernel32.dll",EntryPoint="CreateFileW",SetLastError=true,CharSet=CharSet.Unicode)]internal static extern IntPtr CreateFile(string name,uint access,uint share,ref SECURITY_ATTRIBUTES attributes,uint creation,uint flags,IntPtr template);
  [DllImport("kernel32.dll",SetLastError=true)]internal static extern bool CreatePipe(out IntPtr read,out IntPtr write,ref SECURITY_ATTRIBUTES attributes,uint size);
  [DllImport("kernel32.dll",SetLastError=true)]internal static extern bool SetHandleInformation(IntPtr handle,uint mask,uint flags);
  [DllImport("kernel32.dll",SetLastError=true)]internal static extern bool InitializeProcThreadAttributeList(IntPtr list,int count,int flags,ref IntPtr size);
  [DllImport("kernel32.dll",SetLastError=true)]internal static extern bool UpdateProcThreadAttribute(IntPtr list,uint flags,IntPtr attribute,IntPtr value,IntPtr size,IntPtr previous,IntPtr returned);
  [DllImport("kernel32.dll")]internal static extern void DeleteProcThreadAttributeList(IntPtr list);
  [DllImport("kernel32.dll",EntryPoint="CreateProcessW",SetLastError=true,CharSet=CharSet.Unicode)]internal static extern bool CreateProcess(string application,StringBuilder command,IntPtr processAttributes,IntPtr threadAttributes,bool inherit,uint flags,IntPtr environment,string directory,ref STARTUPINFOEX startup,out PROCESS_INFORMATION process);
  [DllImport("kernel32.dll",SetLastError=true)]internal static extern uint ResumeThread(IntPtr thread);
  [DllImport("kernel32.dll",SetLastError=true)]internal static extern bool TerminateProcess(IntPtr process,uint code);
  [DllImport("kernel32.dll",SetLastError=true)]internal static extern bool GetExitCodeProcess(IntPtr process,out uint code);
  [DllImport("kernel32.dll")]internal static extern uint WaitForSingleObject(IntPtr handle,uint milliseconds);
  [DllImport("kernel32.dll")]internal static extern bool CloseHandle(IntPtr handle);
 }
}
