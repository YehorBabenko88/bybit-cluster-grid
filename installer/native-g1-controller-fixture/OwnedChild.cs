using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;
using Microsoft.Win32.SafeHandles;
internal sealed class OwnedChild:IDisposable {
 [StructLayout(LayoutKind.Sequential)]struct SI{public uint cb;public IntPtr reserved,desktop,title;public uint x,y,xs,ys,xc,yc,fill,flags;public ushort show,reserved2;public IntPtr reserved3,input,output,error;}
 [StructLayout(LayoutKind.Sequential)]struct SX{public SI si;public IntPtr list;}
 [StructLayout(LayoutKind.Sequential)]struct PI{public IntPtr process,thread;public uint pid,tid;}
 [StructLayout(LayoutKind.Sequential)]struct Label{public IntPtr sid;public uint attributes;}
 [StructLayout(LayoutKind.Sequential)]struct Caps{public IntPtr sid,capabilities;public uint count,reserved;}
 [StructLayout(LayoutKind.Sequential)]struct Basic{public long processTime,jobTime;public uint flags;public UIntPtr min,max;public uint active;public UIntPtr affinity;public uint priority,scheduling;}
 [StructLayout(LayoutKind.Sequential)]struct IO{public ulong r,w,o,rb,wb,ob;}
 [StructLayout(LayoutKind.Sequential)]struct Limits{public Basic basic;public IO io;public UIntPtr processMemory,jobMemory,peakProcess,peakJob;}
 [DllImport("kernel32.dll",SetLastError=true)]static extern IntPtr CreateJobObjectW(IntPtr sa,IntPtr name);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool SetInformationJobObject(IntPtr j,int c,ref Limits l,int size);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool QueryInformationJobObject(IntPtr j,int c,out Limits l,int size,out int returned);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool IsProcessInJob(IntPtr p,IntPtr j,out bool yes);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool InitializeProcThreadAttributeList(IntPtr p,int count,int flags,ref UIntPtr size);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool UpdateProcThreadAttribute(IntPtr p,uint flags,UIntPtr attribute,IntPtr value,UIntPtr size,IntPtr previous,IntPtr returned);
 [DllImport("kernel32.dll")]static extern void DeleteProcThreadAttributeList(IntPtr p);
 [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern bool CreateProcessAsUserW(SafeAccessTokenHandle token,string app,StringBuilder args,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr env,string cwd,ref SX si,out PI pi);
 [DllImport("advapi32.dll",SetLastError=true)]static extern bool CreateRestrictedToken(SafeAccessTokenHandle existing,uint flags,uint disabled,IntPtr sids,uint removed,IntPtr privileges,uint restrictedCount,IntPtr restrictedSids,out SafeAccessTokenHandle token);
 [DllImport("userenv.dll",CharSet=CharSet.Unicode)]static extern int CreateAppContainerProfile(string name,string display,string description,IntPtr caps,uint count,out IntPtr sid);
 [DllImport("advapi32.dll")]static extern IntPtr FreeSid(IntPtr sid);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool GetHandleInformation(IntPtr handle,out uint flags);
 [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr h);
 [DllImport("kernel32.dll",SetLastError=true)]static extern uint ResumeThread(IntPtr h);
 [DllImport("kernel32.dll")]static extern uint WaitForSingleObject(IntPtr h,uint ms);
 [DllImport("kernel32.dll")]static extern uint GetProcessId(IntPtr process);
 [DllImport("kernel32.dll")]static extern bool GetExitCodeProcess(IntPtr h,out uint code);
 [DllImport("kernel32.dll")]static extern bool TerminateProcess(IntPtr h,uint code);
 [DllImport("kernel32.dll")]static extern bool GetProcessTimes(IntPtr h,out long created,out long exit,out long kernel,out long user);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern bool QueryFullProcessImageNameW(IntPtr p,uint flags,StringBuilder path,ref uint size);
 [DllImport("advapi32.dll",SetLastError=true)]static extern bool OpenProcessToken(IntPtr p,uint access,out SafeAccessTokenHandle token);
 [DllImport("advapi32.dll",SetLastError=true)]static extern bool GetTokenInformation(SafeAccessTokenHandle t,int c,IntPtr b,int size,out int needed);
 [DllImport("advapi32.dll",SetLastError=true)]static extern bool SetTokenInformation(SafeAccessTokenHandle t,int kind,IntPtr info,int size);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool SetFileInformationByHandle(SafeFileHandle h,int c,ref int value,int size);
 readonly List<LoaderFact> loaderEvents=new();internal IReadOnlyList<LoaderFact> LoaderEvents=>loaderEvents;
 IOwnedExecutable? ownedImage;OwnedDesktop? ownedDesktop;IntPtr job,process,thread;long creation;bool imagePreverified;string imagePath="";internal bool Exited=>process!=IntPtr.Zero&&WaitForSingleObject(process,0)==0;
 internal uint ProcessId{get{ControllerPolicy.Need(process!=IntPtr.Zero,"PROCESS_HANDLE_MISSING");uint id=GetProcessId(process);ControllerPolicy.Need(id>0,"PROCESS_ID_UNKNOWN");return id;}}
 internal OwnedChild(byte[] payload,string expectedHash,string expectedUser):this(expectedUser,(package,moniker)=>new OwnedImage(package,moniker,expectedUser,payload,expectedHash)){}
 internal OwnedChild(string expectedUser,Func<string,string,IOwnedExecutable> factory){IntPtr sid=IntPtr.Zero,list=IntPtr.Zero,cap=IntPtr.Zero,environment=IntPtr.Zero,desktopName=IntPtr.Zero,jobList=IntPtr.Zero,outputList=IntPtr.Zero;bool initialized=false;try{
  string moniker="g1-fixture-"+Guid.NewGuid().ToString("D");ControllerPolicy.Need(CreateAppContainerProfile(moniker,"CI test fixture","Disposable runner only",IntPtr.Zero,0,out sid)==0,"PROFILE");string expectedSid=new SecurityIdentifier(sid).Value;ownedImage=factory(expectedSid,moniker);imagePath=ownedImage.Path;
  job=CreateJobObjectW(IntPtr.Zero,IntPtr.Zero);ControllerPolicy.Need(job!=IntPtr.Zero);var limits=new Limits{basic=new Basic{flags=0x2008,active=1}};ControllerPolicy.Need(SetInformationJobObject(job,9,ref limits,Marshal.SizeOf<Limits>()),"JOB_LIMITS");ControllerPolicy.Need(QueryInformationJobObject(job,9,out var actual,Marshal.SizeOf<Limits>(),out int returned)&&returned==Marshal.SizeOf<Limits>()&&actual.basic.flags==0x2008&&actual.basic.active==1,"JOB_READBACK");
  bool redirected=ownedImage.OutputHandle!=null;int attributeCount=redirected?3:2;
  UIntPtr size=UIntPtr.Zero;InitializeProcThreadAttributeList(IntPtr.Zero,attributeCount,0,ref size);ControllerPolicy.Need(size.ToUInt64()>0&&size.ToUInt64()<65536);list=Marshal.AllocHGlobal(checked((int)size.ToUInt64()));ControllerPolicy.Need(InitializeProcThreadAttributeList(list,attributeCount,0,ref size));initialized=true;cap=Marshal.AllocHGlobal(Marshal.SizeOf<Caps>());Marshal.StructureToPtr(new Caps{sid=sid},cap,false);ControllerPolicy.Need(UpdateProcThreadAttribute(list,0,(UIntPtr)0x20009,cap,(UIntPtr)Marshal.SizeOf<Caps>(),IntPtr.Zero,IntPtr.Zero));
  jobList=Marshal.AllocHGlobal(IntPtr.Size);Marshal.WriteIntPtr(jobList,job);if(!UpdateProcThreadAttribute(list,0,(UIntPtr)0x2000D,jobList,(UIntPtr)IntPtr.Size,IntPtr.Zero,IntPtr.Zero))throw new Blocked("ATOMIC_JOB_LIST_WIN32_"+Marshal.GetLastWin32Error());
  IntPtr output=IntPtr.Zero;
  if(redirected){var h=ownedImage.OutputHandle!;ControllerPolicy.Need(!h.IsClosed&&!h.IsInvalid,"OWNED_OUTPUT_HANDLE");output=h.DangerousGetHandle();ControllerPolicy.Need(GetHandleInformation(output,out uint flags)&&(flags&1)==1,"OUTPUT_NOT_INHERITABLE");outputList=Marshal.AllocHGlobal(IntPtr.Size);Marshal.WriteIntPtr(outputList,output);ControllerPolicy.Need(UpdateProcThreadAttribute(list,0,(UIntPtr)0x20002,outputList,(UIntPtr)IntPtr.Size,IntPtr.Zero,IntPtr.Zero),"EXACT_OUTPUT_HANDLE_LIST");}
  environment=Marshal.StringToHGlobalUni(ownedImage.EnvironmentBlock);
  ControllerPolicy.Need(OpenProcessToken(new IntPtr(-1),0x8B,out var original),"PARENT_PRIMARY_TOKEN");using var originalToken=original;
  if(!CreateRestrictedToken(originalToken,5,0,IntPtr.Zero,0,IntPtr.Zero,0,IntPtr.Zero,out var restricted))throw new Blocked("RESTRICTED_TOKEN_WIN32_"+Marshal.GetLastWin32Error());using var restrictedToken=restricted;LowerOwnedToken(restrictedToken);ControllerPolicy.ChildToken(Native.TokenFacts(restrictedToken),expectedUser);
  ownedDesktop=new OwnedDesktop(expectedUser,expectedSid);desktopName=Marshal.StringToHGlobalUni(ownedDesktop.Name);
  var sx=new SX{si=new SI{cb=(uint)Marshal.SizeOf<SX>(),desktop=desktopName,flags=redirected?0x100u:0u,output=output,error=output,input=IntPtr.Zero},list=list};if(!CreateProcessAsUserW(restrictedToken,imagePath,new StringBuilder(ownedImage.CommandLine),IntPtr.Zero,IntPtr.Zero,redirected,0x08080404|(ownedImage.TraceLoader?2u:0u),environment,ownedImage.WorkingDirectory,ref sx,out var pi))throw new Blocked("CREATE_SUSPENDED_WIN32_"+Marshal.GetLastWin32Error());process=pi.process;thread=pi.thread;
  ControllerPolicy.Need(IsProcessInJob(process,job,out bool inside)&&inside,"JOB_ASSIGN");ControllerPolicy.Need(GetProcessTimes(process,out creation,out _,out _,out _)&&creation>0,"PROCESS_TIME");Guard();ControllerPolicy.Need(OpenProcessToken(process,8,out var token));using(token){ControllerPolicy.ChildToken(Native.TokenFacts(token),expectedUser);Token(token,29,(p,n)=>ControllerPolicy.Need(n==4&&Marshal.ReadInt32(p)==1,"APP_TOKEN"));Token(token,30,(p,n)=>ControllerPolicy.Need(n>=4&&Marshal.ReadInt32(p)==0,"CAPABILITIES"));Token(token,31,(p,n)=>{ControllerPolicy.Need(n>=IntPtr.Size+8);var s=Marshal.ReadIntPtr(p);long offset=s.ToInt64()-p.ToInt64();Policy.SidBounds(offset,n,IntPtr.Size,0);int sub=Marshal.ReadByte(s,1);Policy.SidBounds(offset,n,IntPtr.Size,sub);ControllerPolicy.Need(new SecurityIdentifier(s).Value==expectedSid,"APP_SID");});}
 }catch{Dispose();throw;}finally{if(initialized)DeleteProcThreadAttributeList(list);if(list!=IntPtr.Zero)Marshal.FreeHGlobal(list);if(cap!=IntPtr.Zero)Marshal.FreeHGlobal(cap);if(sid!=IntPtr.Zero)FreeSid(sid);if(environment!=IntPtr.Zero)Marshal.FreeHGlobal(environment);if(desktopName!=IntPtr.Zero)Marshal.FreeHGlobal(desktopName);if(jobList!=IntPtr.Zero)Marshal.FreeHGlobal(jobList);if(outputList!=IntPtr.Zero)Marshal.FreeHGlobal(outputList);}}
 // Changes only the fresh restricted token handle, never an account, ACL or caller token.
 static void LowerOwnedToken(SafeAccessTokenHandle token){
  var sid=new SecurityIdentifier("S-1-16-4096");var bytes=new byte[sid.BinaryLength];sid.GetBinaryForm(bytes,0);int prefix=Marshal.SizeOf<Label>();int size=checked(prefix+bytes.Length);var buffer=Marshal.AllocHGlobal(size);
  try{var pointer=IntPtr.Add(buffer,prefix);Marshal.Copy(bytes,0,pointer,bytes.Length);Marshal.StructureToPtr(new Label{sid=pointer,attributes=0x20},buffer,false);if(!SetTokenInformation(token,25,buffer,size))throw new Blocked("LOWER_OWNED_TOKEN_WIN32_"+Marshal.GetLastWin32Error());}finally{Marshal.FreeHGlobal(buffer);}
 }
 static void Token(SafeAccessTokenHandle t,int c,Action<IntPtr,int> check){bool ok=GetTokenInformation(t,c,IntPtr.Zero,0,out int n);ControllerPolicy.Need(!ok&&Marshal.GetLastWin32Error()==122&&n>0&&n<=65536,"TOKEN_SIZE");var p=Marshal.AllocHGlobal(n);try{ControllerPolicy.Need(GetTokenInformation(t,c,p,n,out int used)&&used==n);check(p,n);}finally{Marshal.FreeHGlobal(p);}}
 internal void Guard(){ControllerPolicy.Need(ownedDesktop!=null,"OWNED_DESKTOP_REQUIRED");ownedDesktop!.Guard();ControllerPolicy.Need(GetProcessTimes(process,out long c,out _,out _,out _)&&c==creation,"PROCESS_IDENTITY");uint n=32768;var text=new StringBuilder((int)n);bool queried=QueryFullProcessImageNameW(process,0,text,ref n);ControllerPolicy.ImageObservation(queried,string.Equals(text.ToString(),imagePath,StringComparison.OrdinalIgnoreCase),Exited,imagePreverified);ControllerPolicy.Need(ownedImage!=null,"OWNED_IMAGE_REQUIRED");ownedImage!.Guard();if(queried)imagePreverified=true;}
 internal void Resume(){Guard();ControllerPolicy.Need(ResumeThread(thread)==1,"RESUME");}
 internal void Wait()=>Wait(10000);
 internal void Wait(uint timeout){ControllerPolicy.Need(timeout>0&&timeout<=120000,"WAIT_BOUND");if(ownedImage?.TraceLoader==true)LoaderTrace.Pump(process,ProcessId,timeout,loaderEvents,ownedImage.ValidateModule);uint wait=WaitForSingleObject(process,timeout);bool queried=GetExitCodeProcess(process,out uint code);ControllerPolicy.Need(wait==0&&queried&&code==0,"COOPERATIVE_EXIT_WAIT_"+wait+"_QUERIED_"+queried+"_CODE_"+code.ToString("X8"));Guard();}
 internal void Stop(){Guard();ControllerPolicy.Need(TerminateProcess(process,99)&&WaitForSingleObject(process,10000)==0,"FORCED_STOP");Guard();}
 internal void CloseJobStop(){Guard();ControllerPolicy.Need(job!=IntPtr.Zero&&WaitForSingleObject(process,0)==258,"JOB_CLOSE_PRECONDITION");ControllerPolicy.Need(CloseHandle(job),"JOB_CLOSE");job=IntPtr.Zero;ControllerPolicy.Need(WaitForSingleObject(process,10000)==0,"JOB_CLOSE_DID_NOT_STOP_CHILD");Guard();}
 internal static void Cleanup(OwnedFixture f,OwnedChild? child,Guardian guardian,bool failTerminalFlush=false){if(child==null||!child.Exited)throw new Blocked("CLEANUP_LIVE_OR_UNKNOWN");guardian.RequireFixture(f);guardian.RequireChild(child);child.Guard();guardian.Append("CLEANUP_INTENT");int yes=1;ControllerPolicy.Need(SetFileInformationByHandle(f.Target,4,ref yes,4),"MARKER_DISPOSITION");guardian.CompleteMarkerDisposition(failTerminalFlush);}
 public void Dispose(){if(job!=IntPtr.Zero){CloseHandle(job);job=IntPtr.Zero;}if(process!=IntPtr.Zero){if(WaitForSingleObject(process,0)!=0)TerminateProcess(process,98);WaitForSingleObject(process,10000);CloseHandle(process);process=IntPtr.Zero;}if(thread!=IntPtr.Zero){CloseHandle(thread);thread=IntPtr.Zero;}ownedDesktop?.Dispose();ownedDesktop=null;ownedImage?.Dispose();ownedImage=null;}
}


