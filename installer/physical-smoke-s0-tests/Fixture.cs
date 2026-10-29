// C# 5 / .NET Framework. Genuine hosted Windows fixture only; never physical acceptance.
using System;
using System.Collections;
using System.IO;
using System.IO.Pipes;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using GridS0;

public static class Fixture
{
    static string stage="FIXTURE_ENTRY";
    static uint? childExit=null;
    [StructLayout(LayoutKind.Sequential)] struct SI {
        public uint cb; public IntPtr reserved, desktop, title;
        public uint x,y,xs,ys,xc,yc,fill,flags; public ushort show,reservedSize;
        public IntPtr reservedBytes,input,output,error;
    }
    [StructLayout(LayoutKind.Sequential)] struct SX { public SI si; public IntPtr attributes; }
    [StructLayout(LayoutKind.Sequential)] struct PI { public IntPtr process,thread; public uint pid,tid; }
    [StructLayout(LayoutKind.Sequential)] struct Basic {
        public long processTime,jobTime; public uint flags; public UIntPtr min,max;
        public uint active; public UIntPtr affinity; public uint priority,scheduling;
    }
    [StructLayout(LayoutKind.Sequential)] struct IO { public ulong ro,wo,oo,rb,wb,ob; }
    [StructLayout(LayoutKind.Sequential)] struct Limits { public Basic basic; public IO io; public UIntPtr pm,jm,pp,pj; }
    [StructLayout(LayoutKind.Sequential)] struct Label { public IntPtr sid; public uint attributes; }
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool CreateRestrictedToken(IntPtr token,uint flags,uint disabled,IntPtr sids,uint removed,IntPtr privileges,uint restricted,IntPtr restrictedSids,out IntPtr result);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool SetTokenInformation(IntPtr token,int kind,IntPtr buffer,int size);
    [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcessAsUserW(IntPtr token,string app,StringBuilder command,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr environment,string cwd,ref SX startup,out PI process);
    [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr CreateJobObjectW(IntPtr attributes,IntPtr name);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job,int kind,ref Limits limits,int size);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool QueryInformationJobObject(IntPtr job,int kind,out Limits limits,int size,out int returned);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool InitializeProcThreadAttributeList(IntPtr list,int count,int flags,ref UIntPtr size);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool UpdateProcThreadAttribute(IntPtr list,uint flags,UIntPtr attribute,IntPtr value,UIntPtr size,IntPtr previous,IntPtr returned);
    [DllImport("kernel32.dll")] static extern void DeleteProcThreadAttributeList(IntPtr list);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool IsProcessInJob(IntPtr process,IntPtr job,out bool member);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetProcessTimes(IntPtr process,out long created,out long exited,out long kernel,out long user);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint GetProcessId(IntPtr process);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint ResumeThread(IntPtr thread);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint WaitForSingleObject(IntPtr handle,uint milliseconds);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetExitCodeProcess(IntPtr process,out uint code);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetHandleInformation(IntPtr handle,out uint flags);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool PeekNamedPipe(IntPtr handle,IntPtr buffer,uint length,IntPtr read,out uint available,IntPtr left);

    static void Need(bool value,string code) { if(!value) throw new InvalidOperationException(code); }
    static void Hosted() {
        Need(Environment.OSVersion.Platform==PlatformID.Win32NT && Environment.Is64BitProcess,"FIXTURE_WINDOWS_X64");
        Need(Environment.GetEnvironmentVariable("GITHUB_ACTIONS")=="true" && Environment.GetEnvironmentVariable("RUNNER_ENVIRONMENT")=="github-hosted" && Environment.GetEnvironmentVariable("GITHUB_REPOSITORY")=="YehorBabenko88/bybit-cluster-grid" && Environment.GetEnvironmentVariable("GITHUB_JOB")=="s0-windows","FIXTURE_HOSTED_GATE");
        Need(!String.Equals(Environment.MachineName,"LS5",StringComparison.OrdinalIgnoreCase) && !String.Equals(Environment.MachineName,"PC4",StringComparison.OrdinalIgnoreCase),"FIXTURE_PHYSICAL_HOST_BLOCKED");
    }
    static string Quote(string value) {
        Need(value!=null && value.IndexOf('"')<0 && value.IndexOf('\0')<0 && value.IndexOf('\r')<0 && value.IndexOf('\n')<0 && !value.EndsWith("\\",StringComparison.Ordinal),"FIXTURE_ARGUMENT");
        return "\""+value+"\"";
    }
    static void LowerFreshToken(IntPtr token) {
        SecurityIdentifier sid=new SecurityIdentifier("S-1-16-8192"); byte[] bytes=new byte[sid.BinaryLength]; sid.GetBinaryForm(bytes,0);
        int prefix=Marshal.SizeOf(typeof(Label)); IntPtr buffer=Marshal.AllocHGlobal(prefix+bytes.Length);
        try { IntPtr pointer=IntPtr.Add(buffer,prefix); Marshal.Copy(bytes,0,pointer,bytes.Length); Marshal.StructureToPtr(new Label{sid=pointer,attributes=0x20},buffer,false); Need(SetTokenInformation(token,25,buffer,prefix+bytes.Length),"FIXTURE_FRESH_TOKEN_MEDIUM"); }
        finally { Marshal.FreeHGlobal(buffer); }
    }
    static int Parent(string root,string sha,string head,string output) {
        IntPtr token=IntPtr.Zero,job=IntPtr.Zero,list=IntPtr.Zero,jobList=IntPtr.Zero,handleList=IntPtr.Zero; PI process=new PI(); bool initialized=false;
        AnonymousPipeServerStream pipe=null,stdinPipe=null;
        try {
            stage="FIXTURE_CREATE_TOKEN";
            using(WindowsIdentity identity=WindowsIdentity.GetCurrent()) Need(CreateRestrictedToken(identity.Token,5,0,IntPtr.Zero,0,IntPtr.Zero,0,IntPtr.Zero,out token),"FIXTURE_RESTRICTED_SELF_TOKEN");
            stage="FIXTURE_LOWER_TOKEN";
            LowerFreshToken(token);
            stage="FIXTURE_CREATE_JOB";
            job=CreateJobObjectW(IntPtr.Zero,IntPtr.Zero); Need(job!=IntPtr.Zero,"FIXTURE_OWN_JOB");
            // Four leaves room for the attempted grandchild: only the inner job may deny it.
            Limits limits=new Limits(); limits.basic.flags=0x2008; limits.basic.active=4; int size=Marshal.SizeOf(typeof(Limits));
            Need(SetInformationJobObject(job,9,ref limits,size),"FIXTURE_JOB_LIMITS");
            Limits actual; int returned; Need(QueryInformationJobObject(job,9,out actual,size,out returned) && returned==size && actual.basic.flags==0x2008 && actual.basic.active==4,"FIXTURE_JOB_READBACK");
            stage="FIXTURE_CREATE_OWN_PIPE";
            // A 16 KiB buffer exceeds the complete bounded 8 KiB JSON message.
            // Only this fixture's output writer and input reader are inherited.
            pipe=new AnonymousPipeServerStream(PipeDirection.In,HandleInheritability.Inheritable,16384);
            IntPtr writer=pipe.ClientSafePipeHandle.DangerousGetHandle(); uint writerFlags;
            Need(GetHandleInformation(writer,out writerFlags) && (writerFlags&1)==1,"FIXTURE_PIPE_WRITER_INHERITABLE");
            stdinPipe=new AnonymousPipeServerStream(PipeDirection.Out,HandleInheritability.Inheritable,4096);
            IntPtr reader=stdinPipe.ClientSafePipeHandle.DangerousGetHandle(); uint readerFlags;
            Need(GetHandleInformation(reader,out readerFlags) && (readerFlags&1)==1,"FIXTURE_PIPE_READER_INHERITABLE");
            UIntPtr bytes=UIntPtr.Zero; Need(!InitializeProcThreadAttributeList(IntPtr.Zero,2,0,ref bytes) && Marshal.GetLastWin32Error()==122 && bytes.ToUInt64()>0 && bytes.ToUInt64()<=65536,"FIXTURE_ATTRIBUTE_SIZE");
            list=Marshal.AllocHGlobal((int)bytes.ToUInt64()); Need(InitializeProcThreadAttributeList(list,2,0,ref bytes),"FIXTURE_ATTRIBUTE_INIT"); initialized=true;
            jobList=Marshal.AllocHGlobal(IntPtr.Size); Marshal.WriteIntPtr(jobList,job);
            Need(UpdateProcThreadAttribute(list,0,(UIntPtr)0x2000D,jobList,(UIntPtr)IntPtr.Size,IntPtr.Zero,IntPtr.Zero),"FIXTURE_ATOMIC_JOB");
            handleList=Marshal.AllocHGlobal(IntPtr.Size*2); Marshal.WriteIntPtr(handleList,writer); Marshal.WriteIntPtr(handleList,IntPtr.Size,reader);
            Need(UpdateProcThreadAttribute(list,0,(UIntPtr)0x20002,handleList,(UIntPtr)(IntPtr.Size*2),IntPtr.Zero,IntPtr.Zero),"FIXTURE_EXACT_PIPE_HANDLE_LIST");
            string self=Assembly.GetExecutingAssembly().Location; SX startup=new SX(); startup.si.cb=(uint)Marshal.SizeOf(typeof(SX)); startup.attributes=list;
            startup.si.flags=0x100; startup.si.input=reader; startup.si.output=writer; startup.si.error=writer;
            StringBuilder command=new StringBuilder(Quote(self)+" --child "+Quote(root)+" "+Quote(sha)+" "+Quote(head)+" "+Quote(output));
            stage="FIXTURE_CREATE_RESTRICTED_CHILD";
            Need(CreateProcessAsUserW(token,self,command,IntPtr.Zero,IntPtr.Zero,true,0x80004,IntPtr.Zero,Path.GetDirectoryName(self),ref startup,out process),"FIXTURE_CREATE_RESTRICTED_SELF");
            pipe.DisposeLocalCopyOfClientHandle();
            // No input is used. Closing our writer gives the child's valid input EOF.
            stdinPipe.DisposeLocalCopyOfClientHandle(); stdinPipe.Dispose(); stdinPipe=null;
            bool member; long created,exited,kernel,user;
            Need(GetProcessId(process.process)==process.pid && process.pid>0 && GetProcessTimes(process.process,out created,out exited,out kernel,out user) && created>0 && IsProcessInJob(process.process,job,out member) && member,"FIXTURE_OWN_CHILD_IDENTITY");
            stage="FIXTURE_RESUME_CHILD";
            Need(ResumeThread(process.thread)==1,"FIXTURE_RESUME");
            uint wait=WaitForSingleObject(process.process,90000);
            if(wait!=0) { CloseHandle(job); job=IntPtr.Zero; Need(WaitForSingleObject(process.process,5000)==0,"FIXTURE_OWN_CHILD_STOP"); throw new InvalidOperationException("FIXTURE_90_SECOND_BOUND"); }
            uint code; Need(GetExitCodeProcess(process.process,out code),"FIXTURE_EXIT_QUERY");
            childExit=code;stage="FIXTURE_READ_CHILD_OUTPUT";
            {
                byte[] raw=new byte[8193]; int count=0;
                // Peek before each read: an unexpected surviving writer must
                // block the fixture, never leave an unbounded blocking read.
                while(true) {
                    uint available;
                    bool peek=PeekNamedPipe(pipe.SafePipeHandle.DangerousGetHandle(),IntPtr.Zero,0,IntPtr.Zero,out available,IntPtr.Zero);
                    int error=Marshal.GetLastWin32Error();
                    if(!peek) { Need(error==109,"FIXTURE_PIPE_PEEK"); break; }
                    Need(available>0,"FIXTURE_PIPE_SURVIVING_WRITER");
                    Need(count<8193,"FIXTURE_OUTPUT_BOUND");
                    int requested=(int)Math.Min((uint)(8193-count),available);
                    int read=pipe.Read(raw,count,requested); Need(read>0,"FIXTURE_OUTPUT_READ"); count+=read;
                    Need(count<=8192,"FIXTURE_OUTPUT_BOUND");
                }
                Need(count>0,"FIXTURE_OUTPUT_EMPTY");
                string json=new UTF8Encoding(false,true).GetString(raw,0,count);
                Need(json.StartsWith("{\"scope\":\"HOSTED_FIXTURE_NOT_PHYSICAL\",",StringComparison.Ordinal) && json.EndsWith("}",StringComparison.Ordinal) && json.IndexOf('\n')<0 && json.IndexOf('\r')<0 && json.IndexOf('\0')<0,"FIXTURE_OUTPUT_FORMAT");
                string fact="\\{\"pid\":[1-9][0-9]{0,9},\"creation_filetime\":[1-9][0-9]{0,18},\"exit_code\":[0-9]{1,10},\"timed_out\":(?:true|false),\"budget_seconds\":[1-5],\"observed_user_sid\":\"S-1-[0-9]+(?:-[0-9]+)+\",\"observed_elevated\":false,\"observed_integrity\":\"S-1-16-8192\",\"observed_admin_enabled\":false,\"job_member\":true,\"job_flags\":8200,\"active_limit\":1\\}";
                string success="\\A\\{\"scope\":\"HOSTED_FIXTURE_NOT_PHYSICAL\",\"fixture\":true,\"head\":\""+Regex.Escape(head)+"\",\"token_probe_cases\":14,\"normal\":"+fact+",\"deadline\":"+fact+",\"descendant_denied\":"+fact+",\"wrong_hash_rejected\":true,\"wrong_sid_rejected\":true\\}\\z";
                string failure="\\A\\{\"scope\":\"HOSTED_FIXTURE_NOT_PHYSICAL\",\"status\":\"BLOCKED\",\"error\":\"(?:FIXTURE|S0)_[A-Z0-9_]{1,80}\",\"stage\":\"FIXTURE_[A-Z0-9_]{1,80}\",\"exception_type\":\"[A-Za-z0-9_.+]{1,160}\",\"hresult\":-?[0-9]{1,10},\"last_win32_diagnostic\":[0-9]{1,10},\"child_exit_code\":(?:null|[0-9]{1,10})\\}\\z";
                Need(Regex.IsMatch(json,code==0?success:failure),"FIXTURE_OUTPUT_SCHEMA");
                Console.WriteLine(json);
            }
            return code==0?0:1;
        } finally {
            // Closing only this unnamed owned job stops only this fixture's descendants.
            if(job!=IntPtr.Zero) CloseHandle(job);
            if(process.process!=IntPtr.Zero) { WaitForSingleObject(process.process,5000); CloseHandle(process.process); }
            if(process.thread!=IntPtr.Zero) CloseHandle(process.thread);
            if(pipe!=null) pipe.Dispose();
            if(stdinPipe!=null) stdinPipe.Dispose();
            if(initialized) DeleteProcThreadAttributeList(list);
            if(list!=IntPtr.Zero) Marshal.FreeHGlobal(list); if(jobList!=IntPtr.Zero) Marshal.FreeHGlobal(jobList); if(handleList!=IntPtr.Zero) Marshal.FreeHGlobal(handleList); if(token!=IntPtr.Zero) CloseHandle(token);
        }
    }
    static string Fact(Result result,int budget) {
        Need(result.Pid>0 && result.CreationFileTime>0,"FIXTURE_RESULT_IDENTITY");
        Need(result.ObservedUserSid!=null && Regex.IsMatch(result.ObservedUserSid,"\\AS-1-[0-9]+(?:-[0-9]+)+\\z"),"FIXTURE_RESULT_USER_SID");
        Need(!result.ObservedElevated && !result.ObservedAdminEnabled && result.ObservedIntegrity=="S-1-16-8192","FIXTURE_RESULT_TOKEN");
        Need(result.JobMember && result.JobFlags==0x2008 && result.ActiveLimit==1,"FIXTURE_RESULT_JOB");
        return "{\"pid\":"+result.Pid+",\"creation_filetime\":"+result.CreationFileTime+",\"exit_code\":"+result.ExitCode+",\"timed_out\":"+(result.TimedOut?"true":"false")+",\"budget_seconds\":"+budget+",\"observed_user_sid\":\""+result.ObservedUserSid+"\",\"observed_elevated\":"+(result.ObservedElevated?"true":"false")+",\"observed_integrity\":\""+result.ObservedIntegrity+"\",\"observed_admin_enabled\":"+(result.ObservedAdminEnabled?"true":"false")+",\"job_member\":"+(result.JobMember?"true":"false")+",\"job_flags\":"+result.JobFlags+",\"active_limit\":"+result.ActiveLimit+"}";
    }
    static void WriteOutput(string json) {
        byte[] bytes=new UTF8Encoding(false,true).GetBytes(json); Need(bytes.Length<=8192,"FIXTURE_OUTPUT_BOUND");
        Console.Write(json); Console.Out.Flush();
    }
    static int Child(string root,string sha,string head,string output) {
        stage="FIXTURE_CHILD_ENVIRONMENT";
        string sid; using(WindowsIdentity identity=WindowsIdentity.GetCurrent()) sid=identity.User.Value;
        Hashtable env=new Hashtable();
        foreach(string key in new string[]{"SystemRoot","WINDIR","USERPROFILE","LOCALAPPDATA","USERNAME","COMPUTERNAME"}) {
            string value=Environment.GetEnvironmentVariable(key); Need(!String.IsNullOrEmpty(value),"FIXTURE_ENVIRONMENT"); env[key]=value;
        }
        string temporary=Environment.GetEnvironmentVariable("RUNNER_TEMP"); Need(!String.IsNullOrEmpty(temporary),"FIXTURE_ENVIRONMENT");
        env["TEMP"]=temporary; env["TMP"]=temporary; env["PATH"]=Path.Combine((string)env["SystemRoot"],"System32");
        stage="FIXTURE_BOOTSTRAP";
        try { BootstrapTests.Hosted(root,sha,head); } catch { stage=BootstrapTests.Phase=="FIXTURE_INPUTS"?InputTests.Phase:BootstrapTests.Phase=="FIXTURE_TRANSFERS"?TransferTests.Phase:BootstrapTests.Phase=="FIXTURE_EXPORTS"?TransferExportTests.Phase:BootstrapTests.Phase=="FIXTURE_TRANSPORT"?TransferTransportTests.Phase:BootstrapTests.Phase; throw; }
        stage="FIXTURE_TOKEN_PROBE_POLICY";
        bool[] probeCases={
            ProcessHost.TokenProbeValid(20,false,122,4),ProcessHost.TokenProbeValid(20,false,24,4),
            ProcessHost.TokenProbeValid(1,false,122,16),ProcessHost.TokenProbeValid(2,false,122,64),ProcessHost.TokenProbeValid(25,false,122,28),
            !ProcessHost.TokenProbeValid(20,false,24,8),!ProcessHost.TokenProbeValid(20,false,24,0),!ProcessHost.TokenProbeValid(20,false,24,-1),
            !ProcessHost.TokenProbeValid(20,false,5,4),!ProcessHost.TokenProbeValid(20,false,6,4),!ProcessHost.TokenProbeValid(20,true,122,4),
            !ProcessHost.TokenProbeValid(3,false,122,16),!ProcessHost.TokenProbeValid(1,false,24,4),!ProcessHost.TokenProbeValid(1,false,122,65537)};
        Need(probeCases.Length==14,"FIXTURE_TOKEN_PROBE_COUNT");
        foreach(bool passed in probeCases) Need(passed,"FIXTURE_TOKEN_PROBE_POLICY");
        stage="FIXTURE_NORMAL_CHILD";
        Result normal=ProcessHost.Run(root,"-I -S -B -c \"raise SystemExit(0)\"",env,sid,sha,head,5);
        Need(!normal.TimedOut && normal.ExitCode==0,"FIXTURE_NORMAL_EXIT");
        stage="FIXTURE_TIMEOUT_CHILD";
        Result timeout=ProcessHost.Run(root,"-I -S -B -c \"import time; time.sleep(10)\"",env,sid,sha,head,1);
        Need(timeout.TimedOut,"FIXTURE_DEADLINE");
        // Python exec receives escaped newlines; ProcessHost forbids actual newline arguments.
        string spawnArg="-I -S -B -c \"exec('import subprocess,sys\\ntry:\\n subprocess.run([sys.executable,chr(45)+chr(99),chr(112)+chr(97)+chr(115)+chr(115)],check=True)\\nexcept OSError:\\n sys.exit(0)\\nsys.exit(99)')\"";
        stage="FIXTURE_DESCENDANT_CHILD";
        Result denied=ProcessHost.Run(root,spawnArg,env,sid,sha,head,5);
        Need(!denied.TimedOut && denied.ExitCode==0,"FIXTURE_DESCENDANT_DENIED");
        bool wrongHash=false,wrongSid=false;
        try { ProcessHost.Run(root,"-I -S -B -c \"raise SystemExit(99)\"",env,sid,new string(sha[0]=='0'?'1':'0',64),head,5); }
        catch(InvalidOperationException error) { Need(error.Message=="S0_IMAGE_HASH","FIXTURE_HASH_FAILURE_CODE"); wrongHash=true; }
        try { ProcessHost.Run(root,"-I -S -B -c \"raise SystemExit(99)\"",env,"S-1-5-18",sha,head,5); }
        catch(InvalidOperationException error) { Need(error.Message=="S0_OPERATOR_SID","FIXTURE_SID_FAILURE_CODE"); wrongSid=true; }
        Need(wrongHash && wrongSid,"FIXTURE_NEGATIVE_GUARDS");
        WriteOutput("{\"scope\":\"HOSTED_FIXTURE_NOT_PHYSICAL\",\"fixture\":true,\"head\":\""+head+"\",\"token_probe_cases\":14,\"normal\":"+Fact(normal,5)+",\"deadline\":"+Fact(timeout,1)+",\"descendant_denied\":"+Fact(denied,5)+",\"wrong_hash_rejected\":true,\"wrong_sid_rejected\":true}");
        return 0;
    }
    public static int Main(string[] args) {
        try {
            stage="FIXTURE_ARGUMENTS";
            Hosted(); Need(args.Length==5 && (args[0]=="--parent" || args[0]=="--child"),"FIXTURE_ARGUMENTS");
            Need(Regex.IsMatch(args[2],"\\A[0-9a-fA-F]{64}\\z") && Regex.IsMatch(args[3],"\\A[0-9a-fA-F]{40}\\z"),"FIXTURE_PINS");
            Need(args[3]==Environment.GetEnvironmentVariable("EXACT_HEAD_SHA"),"FIXTURE_CI_HEAD");
            Need(Path.IsPathRooted(args[1]) && !args[1].StartsWith(@"\\",StringComparison.Ordinal),"FIXTURE_PACKAGE_ROOT");
            string output=Path.GetFullPath(args[4]); string prefix=Path.GetFullPath(args[1]).TrimEnd('\\')+"\\";
            Need(output.StartsWith(prefix,StringComparison.OrdinalIgnoreCase) && !File.Exists(output) && !Directory.Exists(output),"FIXTURE_FRESH_OUTPUT");
            return args[0]=="--parent"?Parent(args[1],args[2],args[3],output):Child(args[1],args[2],args[3],output);
        } catch(Exception error) {
            string code=error is InvalidOperationException && Regex.IsMatch(error.Message,"\\A(?:FIXTURE|S0)_[A-Z0-9_]{1,80}\\z")?error.Message:"FIXTURE_CHECK_FAILED";
            string type=error.GetType().FullName;
            if(type==null || !Regex.IsMatch(type,"\\A[A-Za-z0-9_.+]{1,160}\\z"))type="Unknown";
            // Numeric diagnostics only, never exception messages/paths/arguments.
            // Last Win32 value is diagnostic context, not an attributed cause.
            string json="{\"scope\":\"HOSTED_FIXTURE_NOT_PHYSICAL\",\"status\":\"BLOCKED\",\"error\":\""+code+"\",\"stage\":\""+stage+"\",\"exception_type\":\""+type+"\",\"hresult\":"+error.HResult+",\"last_win32_diagnostic\":"+unchecked((uint)Marshal.GetLastWin32Error())+",\"child_exit_code\":"+(childExit.HasValue?childExit.Value.ToString():"null")+"}";
            // Includes early Hosted/argument failures: no ACL-dependent file handoff.
            WriteOutput(json);
            return 1;
        }
    }
}
