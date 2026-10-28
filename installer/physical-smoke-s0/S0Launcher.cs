using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;

namespace GridS0
{
    public sealed class Result
    {
        public uint Pid { get; internal set; }
        public long CreationFileTime { get; internal set; }
        public uint ExitCode { get; internal set; }
        public bool TimedOut { get; internal set; }
        public string Scope { get; internal set; }
        public string ObservedUserSid { get; internal set; }
        public bool ObservedElevated { get; internal set; }
        public string ObservedIntegrity { get; internal set; }
        public bool ObservedAdminEnabled { get; internal set; }
        public bool JobMember { get; internal set; }
        public uint JobFlags { get; internal set; }
        public uint ActiveLimit { get; internal set; }
    }

    // S0 is a normal standard-token process with a one-process job lifetime.
    // This is explicitly NOT a G1 sandbox or an OS network restriction.
    public static class ProcessHost
    {
        [StructLayout(LayoutKind.Sequential)] struct StartupInfo
        {
            public uint cb; public IntPtr reserved, desktop, title;
            public uint x, y, xSize, ySize, xChars, yChars, fill, flags;
            public ushort show, reservedSize; public IntPtr reservedBytes, input, output, error;
        }
        [StructLayout(LayoutKind.Sequential)] struct StartupInfoEx { public StartupInfo startup; public IntPtr attributes; }
        [StructLayout(LayoutKind.Sequential)] struct ProcessInformation { public IntPtr hProcess, hThread; public uint processId, threadId; }
        [StructLayout(LayoutKind.Sequential)] struct BasicLimits
        {
            public long processTime, jobTime; public uint flags;
            public UIntPtr minimumWorkingSet, maximumWorkingSet;
            public uint activeProcessLimit; public UIntPtr affinity; public uint priorityClass, schedulingClass;
        }
        [StructLayout(LayoutKind.Sequential)] struct IoCounters { public ulong readOperations, writeOperations, otherOperations, readBytes, writeBytes, otherBytes; }
        [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits
        {
            public BasicLimits basic; public IoCounters io;
            public UIntPtr processMemoryLimit, jobMemoryLimit, peakProcessMemoryUsed, peakJobMemoryUsed;
        }
        [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct OsVersion
        {
            public uint size, major, minor, build, platform;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst=128)] public string servicePack;
            public ushort servicePackMajor, servicePackMinor, suiteMask; public byte productType, reserved;
        }

        [DllImport("ntdll.dll", CharSet=CharSet.Unicode)] static extern int RtlGetVersion(ref OsVersion version);
        [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr CreateJobObjectW(IntPtr attributes, IntPtr name);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job, int kind, ref ExtendedLimits limits, int length);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool QueryInformationJobObject(IntPtr job, int kind, out ExtendedLimits limits, int length, out int returned);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetHandleInformation(IntPtr handle, out uint flags);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool InitializeProcThreadAttributeList(IntPtr list, int count, int flags, ref UIntPtr size);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool UpdateProcThreadAttribute(IntPtr list, uint flags, UIntPtr attribute, IntPtr value, UIntPtr size, IntPtr previousValue, IntPtr returnedSize);
        [DllImport("kernel32.dll")] static extern void DeleteProcThreadAttributeList(IntPtr list);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool CreateProcessW(string application, StringBuilder commandLine, IntPtr processAttributes, IntPtr threadAttributes, bool bInheritHandles, uint flags, IntPtr environment, string directory, ref StartupInfoEx startup, out ProcessInformation process);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool IsProcessInJob(IntPtr process, IntPtr job, out bool member);
        [DllImport("kernel32.dll", SetLastError=true)] static extern uint GetProcessId(IntPtr process);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetProcessTimes(IntPtr process, out long created, out long exited, out long kernel, out long user);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool QueryFullProcessImageNameW(IntPtr process, uint flags, StringBuilder image, ref uint size);
        [DllImport("kernel32.dll", SetLastError=true)] static extern uint ResumeThread(IntPtr thread);
        [DllImport("kernel32.dll", SetLastError=true)] static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetExitCodeProcess(IntPtr process, out uint exitCode);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool CloseHandle(IntPtr handle);
        [DllImport("advapi32.dll", SetLastError=true)] static extern bool GetTokenInformation(IntPtr token, int kind, IntPtr data, int length, out int required);
        [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
        [DllImport("advapi32.dll", SetLastError=true)] static extern bool OpenProcessToken(IntPtr process, uint access, out IntPtr token);

        static void Need(bool condition, string code) { if (!condition) throw new InvalidOperationException(code); }

        public static bool TokenProbeValid(int kind, bool success, int error, int size)
        {
            // Same scalar contract as native-acl-observer Policy.ScalarProbe.
            // ERROR_BAD_LENGTH is valid only for the four-byte TokenElevation.
            if(success) return false;
            if(kind==20) return size==4 && (error==122 || error==24);
            return (kind==1 || kind==2 || kind==25) && error==122 && size>0 && size<=65536;
        }

        static void Token(IntPtr token, int kind, Action<IntPtr, int> validate)
        {
            int required;
            bool initial=GetTokenInformation(token, kind, IntPtr.Zero, 0, out required);
            int probeError=Marshal.GetLastWin32Error();
            Need(TokenProbeValid(kind,initial,probeError,required), "S0_TOKEN_SIZE");
            IntPtr buffer=Marshal.AllocHGlobal(required);
            try
            {
                int actual;
                Need(GetTokenInformation(token, kind, buffer, required, out actual) && actual==required, "S0_TOKEN_READ");
                validate(buffer, required);
            }
            finally { Marshal.FreeHGlobal(buffer); }
        }

        sealed class TokenFacts
        {
            internal string userSid, integrity;
            internal bool elevated, adminEnabled;
        }

        static string BoundedSid(IntPtr buffer, int length, IntPtr sid, int minimumOffset)
        {
            long offset=sid.ToInt64()-buffer.ToInt64();
            Need(offset>=minimumOffset && offset%4==0 && offset<=length-8, "S0_TOKEN_SID_BOUNDS");
            int count=Marshal.ReadByte(sid,1);
            Need(Marshal.ReadByte(sid)==1 && count<=15 && offset+8+count*4<=length, "S0_TOKEN_SID_LAYOUT");
            return new SecurityIdentifier(sid).Value;
        }

        // The only process arguments are the current-process pseudo handle and
        // the held handle returned by our own suspended CreateProcessW call.
        static TokenFacts ValidateOwnedProcessToken(IntPtr ownedProcess, string operatorSid)
        {
            IntPtr token;
            Need(OpenProcessToken(ownedProcess,8,out token) && token!=IntPtr.Zero, "S0_PRIMARY_TOKEN_OPEN");
            try
            {
                TokenFacts facts=new TokenFacts();
                int sidAndAttributesSize=IntPtr.Size==8 ? 16 : 8;
                Token(token,1,delegate(IntPtr buffer,int length)
                {
                    Need(length>=sidAndAttributesSize, "S0_USER_LAYOUT");
                    facts.userSid=BoundedSid(buffer,length,Marshal.ReadIntPtr(buffer),sidAndAttributesSize);
                    Need(String.Equals(facts.userSid,operatorSid,StringComparison.Ordinal), "S0_OPERATOR_SID");
                });
                Token(token,20,delegate(IntPtr buffer,int length)
                {
                    Need(length==4, "S0_ELEVATION_LAYOUT");
                    int elevation=Marshal.ReadInt32(buffer);
                    Need(elevation==0 || elevation==1, "S0_ELEVATION_VALUE");
                    facts.elevated=elevation==1;
                    Need(!facts.elevated, "S0_ELEVATED_TOKEN");
                });
                Token(token,25,delegate(IntPtr buffer,int length)
                {
                    Need(length>=sidAndAttributesSize, "S0_INTEGRITY_LAYOUT");
                    facts.integrity=BoundedSid(buffer,length,Marshal.ReadIntPtr(buffer),sidAndAttributesSize);
                    Need(facts.integrity=="S-1-16-8192", "S0_INTEGRITY_LEVEL");
                });
                Token(token,2,delegate(IntPtr buffer,int length)
                {
                    Need(length>=4, "S0_GROUPS_LAYOUT");
                    int count=Marshal.ReadInt32(buffer);
                    int first=IntPtr.Size==8 ? 8 : 4;
                    Need(count>=0 && count<=4096 && first+(long)count*sidAndAttributesSize<=length, "S0_GROUPS_COUNT");
                    int sidMinimum=first+count*sidAndAttributesSize;
                    for (int index=0; index<count; index++)
                    {
                        IntPtr group=IntPtr.Add(buffer,first+index*sidAndAttributesSize);
                        string sid=BoundedSid(buffer,length,Marshal.ReadIntPtr(group),sidMinimum);
                        uint attributes=unchecked((uint)Marshal.ReadInt32(group,IntPtr.Size));
                        if (sid=="S-1-5-32-544" && (attributes&4)!=0 && (attributes&16)==0) facts.adminEnabled=true;
                    }
                    Need(!facts.adminEnabled, "S0_ADMIN_TOKEN");
                });
                return facts;
            }
            finally { Need(CloseHandle(token), "S0_TOKEN_CLOSE"); }
        }

        static string ClosedEnvironment(IDictionary environment)
        {
            Need(environment!=null && environment.Count==9, "S0_ENVIRONMENT_COUNT");
            HashSet<string> allowed=new HashSet<string>(new string[]{"SystemRoot","WINDIR","USERPROFILE","LOCALAPPDATA","USERNAME","COMPUTERNAME","TEMP","TMP","PATH"},StringComparer.OrdinalIgnoreCase);
            SortedDictionary<string,string> values=new SortedDictionary<string,string>(StringComparer.OrdinalIgnoreCase);
            foreach (DictionaryEntry entry in environment)
            {
                string key=entry.Key as string; string value=entry.Value as string;
                Need(key!=null && Regex.IsMatch(key, @"\A[A-Za-z_][A-Za-z0-9_]{0,127}\z") && value!=null && value.Length<=8192 && value.IndexOf('\0')<0, "S0_ENVIRONMENT_ENTRY");
                Need(allowed.Contains(key) && !values.ContainsKey(key) && value.Length>0, "S0_ENVIRONMENT_DUPLICATE_OR_UNREVIEWED");
                values.Add(key,value);
            }
            StringBuilder result=new StringBuilder();
            foreach (KeyValuePair<string,string> entry in values) result.Append(entry.Key).Append('=').Append(entry.Value).Append('\0');
            result.Append('\0');
            Need(result.Length<=32767, "S0_ENVIRONMENT_SIZE");
            return result.ToString();
        }

        static void CloseOwnedJob(ref IntPtr job)
        {
            if (job==IntPtr.Zero) return;
            IntPtr owned=job;
            Need(CloseHandle(owned), "S0_JOB_CLOSE_BLOCKED");
            job=IntPtr.Zero;
        }

        public static Result Run(string packageRoot, string arguments, IDictionary environment, string operatorSid, string expectedExeSha, string head, int seconds)
        {
            IntPtr job=IntPtr.Zero, attributes=IntPtr.Zero, jobList=IntPtr.Zero, environmentBlock=IntPtr.Zero;
            ProcessInformation process=new ProcessInformation(); bool initialized=false;
            FileStream source=null;
            try
            {
                Need(Environment.OSVersion.Platform==PlatformID.Win32NT && Environment.Is64BitProcess, "S0_WINDOWS_X64_REQUIRED");
                OsVersion version=new OsVersion(); version.size=(uint)Marshal.SizeOf(typeof(OsVersion));
                Need(RtlGetVersion(ref version)==0 && version.major>=10 && version.build>=14393, "S0_WINDOWS_VERSION");
                Need(!(seconds < 1 || seconds > 300), "S0_TIME_BUDGET");
                Need(head!=null && Regex.IsMatch(head, @"\A[0-9a-fA-F]{40}\z"), "S0_HEAD");
                Need(expectedExeSha!=null && Regex.IsMatch(expectedExeSha, @"\A[0-9a-fA-F]{64}\z"), "S0_IMAGE_HASH_FORMAT");
                Need(arguments!=null && arguments.Length<=8192 && arguments.IndexOf('\0')<0 && arguments.IndexOf('\r')<0 && arguments.IndexOf('\n')<0, "S0_ARGUMENTS");
                ValidateOwnedProcessToken(GetCurrentProcess(),operatorSid);
                Need(packageRoot!=null && Path.IsPathRooted(packageRoot) && !packageRoot.StartsWith(@"\\", StringComparison.Ordinal), "S0_PACKAGE_ROOT");
                string root=Path.GetFullPath(packageRoot);
                Need(root.Length>=3 && root[1]==':' && root[2]=='\\' && root.IndexOf('"')<0, "S0_PACKAGE_ROOT_FORMAT");
                string executable=Path.Combine(root, "runtime", "python.exe");
                Need((File.GetAttributes(executable)&FileAttributes.ReparsePoint)==0, "S0_IMAGE_REPARSE");
                source=new FileStream(executable, FileMode.Open, FileAccess.Read, FileShare.Read);
                using (SHA256 hash=SHA256.Create())
                {
                    string observed=BitConverter.ToString(hash.ComputeHash(source)).Replace("-", "");
                    Need(String.Equals(observed, expectedExeSha, StringComparison.OrdinalIgnoreCase), "S0_IMAGE_HASH");
                }
                string closedEnvironment=ClosedEnvironment(environment);
                job=CreateJobObjectW(IntPtr.Zero, IntPtr.Zero);
                Need(job!=IntPtr.Zero, "S0_JOB_CREATE");
                uint handleFlags;
                Need(GetHandleInformation(job,out handleFlags) && (handleFlags&1)==0, "S0_JOB_INHERITANCE");
                ExtendedLimits limits=new ExtendedLimits(); limits.basic.flags=0x2008; limits.basic.activeProcessLimit=1;
                int limitSize=Marshal.SizeOf(typeof(ExtendedLimits));
                Need(SetInformationJobObject(job,9,ref limits,limitSize), "S0_JOB_LIMIT_SET");
                ExtendedLimits observedLimits; int returned;
                Need(QueryInformationJobObject(job,9,out observedLimits,limitSize,out returned) && returned==limitSize && observedLimits.basic.flags==0x2008 && observedLimits.basic.activeProcessLimit==1, "S0_JOB_LIMIT_READBACK");
                UIntPtr attributeSize=UIntPtr.Zero;
                bool sizing=InitializeProcThreadAttributeList(IntPtr.Zero,1,0,ref attributeSize);
                Need(!sizing && Marshal.GetLastWin32Error()==122 && attributeSize.ToUInt64()>0 && attributeSize.ToUInt64()<=65536, "S0_ATTRIBUTE_SIZE");
                attributes=Marshal.AllocHGlobal(checked((int)attributeSize.ToUInt64()));
                Need(InitializeProcThreadAttributeList(attributes,1,0,ref attributeSize), "S0_ATTRIBUTE_INIT"); initialized=true;
                jobList=Marshal.AllocHGlobal(IntPtr.Size); Marshal.WriteIntPtr(jobList,job);
                Need(UpdateProcThreadAttribute(attributes,0,(UIntPtr)0x2000D,jobList,(UIntPtr)IntPtr.Size,IntPtr.Zero,IntPtr.Zero), "S0_ATOMIC_JOB_ATTRIBUTE");
                environmentBlock=Marshal.StringToHGlobalUni(closedEnvironment);
                StartupInfoEx startup=new StartupInfoEx(); startup.startup.cb=(uint)Marshal.SizeOf(typeof(StartupInfoEx)); startup.attributes=attributes;
                StringBuilder command=new StringBuilder("\""+executable+"\" "+arguments);
                Need(CreateProcessW(executable,command,IntPtr.Zero,IntPtr.Zero,false,0x80404,environmentBlock,root,ref startup,out process), "S0_CREATE_SUSPENDED");
                bool member;
                Need(IsProcessInJob(process.hProcess,job,out member) && member, "S0_JOB_MEMBERSHIP");
                uint pid=GetProcessId(process.hProcess);
                Need(pid!=0 && pid==process.processId, "S0_PROCESS_IDENTITY");
                long created, exited, kernel, user;
                Need(GetProcessTimes(process.hProcess,out created,out exited,out kernel,out user) && created>0, "S0_PROCESS_TIME");
                uint imageLength=32768; StringBuilder image=new StringBuilder((int)imageLength);
                Need(QueryFullProcessImageNameW(process.hProcess,0,image,ref imageLength) && String.Equals(image.ToString(),executable,StringComparison.OrdinalIgnoreCase), "S0_PROCESS_IMAGE");
                TokenFacts childToken=ValidateOwnedProcessToken(process.hProcess,operatorSid);
                Need(ResumeThread(process.hThread)==1, "S0_RESUME");
                uint wait=WaitForSingleObject(process.hProcess,checked((uint)seconds*1000));
                bool timedOut=wait==258;
                Need(wait==0 || timedOut, "S0_WAIT_BLOCKED");
                if (timedOut)
                {
                    CloseOwnedJob(ref job);
                    Need(WaitForSingleObject(process.hProcess, 5000)==0, "S0_TIMEOUT_EXIT_BLOCKED");
                }
                uint exitCode;
                Need(GetExitCodeProcess(process.hProcess,out exitCode), "S0_EXIT_CODE");
                return new Result { Pid=pid, CreationFileTime=created, ExitCode=exitCode, TimedOut=timedOut, Scope="S0_STANDARD_TOKEN_JOB_LIMITED_NOT_G1", ObservedUserSid=childToken.userSid, ObservedElevated=childToken.elevated, ObservedIntegrity=childToken.integrity, ObservedAdminEnabled=childToken.adminEnabled, JobMember=member, JobFlags=observedLimits.basic.flags, ActiveLimit=observedLimits.basic.activeProcessLimit };
            }
            catch (InvalidOperationException error)
            {
                // Preserve only our fixed codes, never Win32 messages or values.
                if (Regex.IsMatch(error.Message, @"\AS0_[A-Z0-9_]{1,80}\z")) throw;
                throw new InvalidOperationException("S0_HOST_BLOCKED");
            }
            catch (Exception) { throw new InvalidOperationException("S0_HOST_BLOCKED"); }
            finally
            {
                // Only this freshly created unnamed job can end this host's own child.
                // Keep source custody until the child has exited or bounded cleanup fails.
                try
                {
                    CloseOwnedJob(ref job);
                    if (process.hProcess!=IntPtr.Zero) Need(WaitForSingleObject(process.hProcess, 5000)==0, "S0_FINAL_EXIT_BLOCKED");
                }
                finally
                {
                    if (process.hThread!=IntPtr.Zero) CloseHandle(process.hThread);
                    if (process.hProcess!=IntPtr.Zero) CloseHandle(process.hProcess);
                    if (initialized) DeleteProcThreadAttributeList(attributes);
                    if (attributes!=IntPtr.Zero) Marshal.FreeHGlobal(attributes);
                    if (jobList!=IntPtr.Zero) Marshal.FreeHGlobal(jobList);
                    if (environmentBlock!=IntPtr.Zero) Marshal.FreeHGlobal(environmentBlock);
                    if (source!=null) source.Dispose();
                }
            }
        }
    }
}
