using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;
using Microsoft.Win32.SafeHandles;
internal sealed class OwnedChild:IDisposable {
 [StructLayout(LayoutKind.Sequential)]struct SI{public uint cb;public IntPtr reserved,desktop,title;public uint x,y,xs,ys,xc,yc,fill,flags;public ushort show,reserved2;public IntPtr reserved3,input,output,error;}
 [StructLayout(LayoutKind.Sequential)]struct SX{public SI si;public IntPtr list;}
 [StructLayout(LayoutKind.Sequential)]struct PI{public IntPtr process,thread;public uint pid,tid;}
 [StructLayout(LayoutKind.Sequential)]struct Caps{public IntPtr sid,capabilities;public uint count,reserved;}
 [StructLayout(LayoutKind.Sequential)]struct Basic{public long processTime,jobTime;public uint flags;public UIntPtr min,max;public uint active;public UIntPtr affinity;public uint priority,scheduling;}
 [StructLayout(LayoutKind.Sequential)]struct IO{public ulong r,w,o,rb,wb,ob;}
 [StructLayout(LayoutKind.Sequential)]struct Limits{public Basic basic;public IO io;public UIntPtr processMemory,jobMemory,peakProcess,peakJob;}
 [DllImport("kernel32.dll",SetLastError=true)]static extern IntPtr CreateJobObjectW(IntPtr sa,IntPtr name);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool SetInformationJobObject(IntPtr j,int c,ref Limits l,int size);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool QueryInformationJobObject(IntPtr j,int c,out Limits l,int size,out int returned);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool AssignProcessToJobObject(IntPtr j,IntPtr p);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool IsProcessInJob(IntPtr p,IntPtr j,out bool yes);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool InitializeProcThreadAttributeList(IntPtr p,int count,int flags,ref UIntPtr size);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool UpdateProcThreadAttribute(IntPtr p,uint flags,UIntPtr attribute,IntPtr value,UIntPtr size,IntPtr previous,IntPtr returned);
 [DllImport("kernel32.dll")]static extern void DeleteProcThreadAttributeList(IntPtr p);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern bool CreateProcessW(string app,StringBuilder args,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr env,string cwd,ref SX si,out PI pi);
 [DllImport("userenv.dll",CharSet=CharSet.Unicode)]static extern int CreateAppContainerProfile(string name,string display,string description,IntPtr caps,uint count,out IntPtr sid);
 [DllImport("advapi32.dll")]static extern IntPtr FreeSid(IntPtr sid);
 [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr h);
 [DllImport("kernel32.dll",SetLastError=true)]static extern uint ResumeThread(IntPtr h);
 [DllImport("kernel32.dll")]static extern uint WaitForSingleObject(IntPtr h,uint ms);
 [DllImport("kernel32.dll")]static extern bool GetExitCodeProcess(IntPtr h,out uint code);
 [DllImport("kernel32.dll")]static extern bool TerminateProcess(IntPtr h,uint code);
 [DllImport("kernel32.dll")]static extern bool GetProcessTimes(IntPtr h,out long created,out long exit,out long kernel,out long user);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern bool QueryFullProcessImageNameW(IntPtr p,uint flags,StringBuilder path,ref uint size);
 [DllImport("advapi32.dll",SetLastError=true)]static extern bool OpenProcessToken(IntPtr p,uint access,out SafeAccessTokenHandle token);
 [DllImport("advapi32.dll",SetLastError=true)]static extern bool GetTokenInformation(SafeAccessTokenHandle t,int c,IntPtr b,int size,out int needed);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool SetFileInformationByHandle(SafeFileHandle h,int c,ref int value,int size);
 IntPtr job,process,thread;long creation;readonly SafeFileHandle image;readonly string imagePath;internal bool Exited=>process!=IntPtr.Zero&&WaitForSingleObject(process,0)==0;
 internal OwnedChild(SafeFileHandle pin,string path){image=pin;imagePath=path;IntPtr sid=IntPtr.Zero,list=IntPtr.Zero,cap=IntPtr.Zero,environment=IntPtr.Zero;bool initialized=false;try{
  ControllerPolicy.Need(CreateAppContainerProfile("g1-fixture-"+Guid.NewGuid().ToString("D"),"CI test fixture","Disposable runner only",IntPtr.Zero,0,out sid)==0,"PROFILE");string expectedSid=new SecurityIdentifier(sid).Value;
  job=CreateJobObjectW(IntPtr.Zero,IntPtr.Zero);ControllerPolicy.Need(job!=IntPtr.Zero);var limits=new Limits{basic=new Basic{flags=0x2008,active=1}};ControllerPolicy.Need(SetInformationJobObject(job,9,ref limits,Marshal.SizeOf<Limits>()),"JOB_LIMITS");ControllerPolicy.Need(QueryInformationJobObject(job,9,out var actual,Marshal.SizeOf<Limits>(),out int returned)&&returned==Marshal.SizeOf<Limits>()&&actual.basic.flags==0x2008&&actual.basic.active==1,"JOB_READBACK");
  UIntPtr size=UIntPtr.Zero;InitializeProcThreadAttributeList(IntPtr.Zero,1,0,ref size);ControllerPolicy.Need(size.ToUInt64()>0&&size.ToUInt64()<65536);list=Marshal.AllocHGlobal(checked((int)size.ToUInt64()));ControllerPolicy.Need(InitializeProcThreadAttributeList(list,1,0,ref size));initialized=true;cap=Marshal.AllocHGlobal(Marshal.SizeOf<Caps>());Marshal.StructureToPtr(new Caps{sid=sid},cap,false);ControllerPolicy.Need(UpdateProcThreadAttribute(list,0,(UIntPtr)0x20009,cap,(UIntPtr)Marshal.SizeOf<Caps>(),IntPtr.Zero,IntPtr.Zero));
  string windows=Environment.GetFolderPath(Environment.SpecialFolder.Windows);ControllerPolicy.Need(Path.IsPathFullyQualified(windows));environment=Marshal.StringToHGlobalUni("SystemRoot="+windows+"\0WINDIR="+windows+"\0\0");
  var sx=new SX{si=new SI{cb=(uint)Marshal.SizeOf<SX>()},list=list};ControllerPolicy.Need(CreateProcessW(path,new StringBuilder("\""+path+"\" /d /c exit 0"),IntPtr.Zero,IntPtr.Zero,false,0x80404,environment,Path.GetDirectoryName(path)!,ref sx,out var pi),"CREATE_SUSPENDED");process=pi.process;thread=pi.thread;
  ControllerPolicy.Need(AssignProcessToJobObject(job,process)&&IsProcessInJob(process,job,out bool inside)&&inside,"JOB_ASSIGN");ControllerPolicy.Need(GetProcessTimes(process,out creation,out _,out _,out _)&&creation>0,"PROCESS_TIME");Guard();ControllerPolicy.Need(OpenProcessToken(process,8,out var token));using(token){ControllerPolicy.Need(!Native.TokenFacts(token).Elevated,"ELEVATED");Token(token,29,(p,n)=>ControllerPolicy.Need(n==4&&Marshal.ReadInt32(p)==1,"APP_TOKEN"));Token(token,30,(p,n)=>ControllerPolicy.Need(n>=4&&Marshal.ReadInt32(p)==0,"CAPABILITIES"));Token(token,31,(p,n)=>{ControllerPolicy.Need(n>=IntPtr.Size+8);var s=Marshal.ReadIntPtr(p);long offset=s.ToInt64()-p.ToInt64();Policy.SidBounds(offset,n,IntPtr.Size,0);int sub=Marshal.ReadByte(s,1);Policy.SidBounds(offset,n,IntPtr.Size,sub);ControllerPolicy.Need(new SecurityIdentifier(s).Value==expectedSid,"APP_SID");});}
 }catch{Dispose();throw;}finally{if(initialized)DeleteProcThreadAttributeList(list);if(list!=IntPtr.Zero)Marshal.FreeHGlobal(list);if(cap!=IntPtr.Zero)Marshal.FreeHGlobal(cap);if(sid!=IntPtr.Zero)FreeSid(sid);if(environment!=IntPtr.Zero)Marshal.FreeHGlobal(environment);}}
 static void Token(SafeAccessTokenHandle t,int c,Action<IntPtr,int> check){bool ok=GetTokenInformation(t,c,IntPtr.Zero,0,out int n);ControllerPolicy.Need(!ok&&Marshal.GetLastWin32Error()==122&&n>0&&n<=65536,"TOKEN_SIZE");var p=Marshal.AllocHGlobal(n);try{ControllerPolicy.Need(GetTokenInformation(t,c,p,n,out int used)&&used==n);check(p,n);}finally{Marshal.FreeHGlobal(p);}}
 internal void Guard(){ControllerPolicy.Need(GetProcessTimes(process,out long c,out _,out _,out _)&&c==creation,"PROCESS_IDENTITY");uint n=32768;var text=new StringBuilder((int)n);ControllerPolicy.Need(QueryFullProcessImageNameW(process,0,text,ref n)&&string.Equals(text.ToString(),imagePath,StringComparison.OrdinalIgnoreCase),"IMAGE_IDENTITY");ControllerPolicy.Need(!image.IsClosed&&!image.IsInvalid);}
 internal void Resume(){Guard();ControllerPolicy.Need(ResumeThread(thread)==1,"RESUME");}
 internal void Wait(){ControllerPolicy.Need(WaitForSingleObject(process,10000)==0&&GetExitCodeProcess(process,out uint code)&&code==0,"COOPERATIVE_EXIT");Guard();}
 internal void Stop(){Guard();ControllerPolicy.Need(TerminateProcess(process,99)&&WaitForSingleObject(process,10000)==0,"FORCED_STOP");Guard();}
 internal static void Cleanup(OwnedFixture f,OwnedChild? child,Guardian guardian){if(child==null||!child.Exited)throw new Blocked("CLEANUP_LIVE_OR_UNKNOWN");child.Guard();guardian.Guard();guardian.Append("CLEANUP_INTENT");int yes=1;ControllerPolicy.Need(SetFileInformationByHandle(f.Target,4,ref yes,4),"MARKER_DISPOSITION");guardian.Append("CLEANED");}
 public void Dispose(){if(job!=IntPtr.Zero){CloseHandle(job);job=IntPtr.Zero;}if(process!=IntPtr.Zero){if(WaitForSingleObject(process,0)!=0)TerminateProcess(process,98);WaitForSingleObject(process,10000);CloseHandle(process);process=IntPtr.Zero;}if(thread!=IntPtr.Zero){CloseHandle(thread);thread=IntPtr.Zero;}}
}


