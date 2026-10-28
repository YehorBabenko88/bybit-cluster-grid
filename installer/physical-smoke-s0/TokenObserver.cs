// C# 5 / .NET Framework 4.8; compile and execute only in genuine hosted CI.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
namespace GridS0
{
    public sealed class TokenGroupFact { public string Sid; public uint Attributes; }
    public sealed class TokenPrivilegeFact { public string Name; public uint Attributes; }
    public sealed class TokenObservation
    {
        public string Sid; public uint Pid; public long CreationFileTime; public bool Elevated;
        public string Integrity; public TokenGroupFact[] Groups; public TokenPrivilegeFact[] Privileges;
        public string[] EnabledPrivileges; public bool Standard;
    }
    public static class TokenObserver
    {
        [StructLayout(LayoutKind.Sequential)] struct Luid { public uint Low; public int High; }
        [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
        [DllImport("kernel32.dll")] static extern uint GetCurrentProcessId();
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetProcessTimes(IntPtr p,out long c,out long e,out long k,out long u);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool CloseHandle(IntPtr h);
        [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenProcessToken(IntPtr p,uint access,out IntPtr t);
        [DllImport("advapi32.dll",SetLastError=true)] static extern bool GetTokenInformation(IntPtr t,int kind,IntPtr b,int n,out int needed);
        [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool LookupPrivilegeNameW(string system,ref Luid luid,StringBuilder name,ref uint length);
        static void Need(bool x) { if(!x) throw new InvalidOperationException("S0_TOKEN_BLOCKED"); }
        public static bool ProbeValid(int kind,bool success,int error,int size)
        {
            if(success) return false;
            if(kind==20) return size==4 && (error==122 || error==24);
            return (kind==1 || kind==2 || kind==3 || kind==25) && error==122 && size>0 && size<=65536;
        }
        static byte[] ReadToken(IntPtr t,int kind,out ulong address)
        {
            int n; bool ok=GetTokenInformation(t,kind,IntPtr.Zero,0,out n);
            int error=Marshal.GetLastWin32Error(); Need(ProbeValid(kind,ok,error,n));
            IntPtr p=Marshal.AllocHGlobal(n);
            try { int actual; Need(GetTokenInformation(t,kind,p,n,out actual) && actual==n);
                byte[] b=new byte[n]; Marshal.Copy(p,b,0,n); address=unchecked((ulong)p.ToInt64()); return b;
            } finally { Marshal.FreeHGlobal(p); }
        }
        static void Buffer(byte[] b) { Need(b!=null && b.Length>0 && b.Length<=65536); }
        static uint U32(byte[] b,int n) { Need(n>=0 && n<=b.Length-4); return BitConverter.ToUInt32(b,n); }
        static ulong Pointer(byte[] b,int n,int width)
        { Need(width==4 || width==8); Need(n>=0 && n<=b.Length-width); return width==8?BitConverter.ToUInt64(b,n):U32(b,n); }
        static string Sid(byte[] b,ulong address,ulong pointer,int minimum)
        {
            Need(pointer>=address); ulong delta=pointer-address;
            Need(delta<=(ulong)b.Length && delta>=(ulong)minimum && delta%4==0 && delta+8<=(ulong)b.Length);
            int at=(int)delta, count=b[at+1]; Need(b[at]==1 && count<=15 && delta+8+(ulong)count*4<=(ulong)b.Length);
            ulong authority=0; for(int i=2;i<8;i++) authority=(authority<<8)|b[at+i];
            StringBuilder s=new StringBuilder("S-1-"); s.Append(authority.ToString(System.Globalization.CultureInfo.InvariantCulture));
            for(int i=0;i<count;i++) s.Append('-').Append(U32(b,at+8+i*4).ToString(System.Globalization.CultureInfo.InvariantCulture));
            return s.ToString();
        }
        public static void ValidateGroupAttributes(uint a)
        {
            Need((a & ~0xE000007Fu)==0);
            Need((a&0xC0000000u)==0 || (a&0xC0000000u)==0xC0000000u);
            Need((a&16)==0 || (a&14)==0);
            Need((a&64)==0 || (a&32)!=0);
            Need((a&32)==0 || (a&~0x61u)==0);
        }
        public static TokenGroupFact[] DecodeGroups(byte[] b,ulong address,int width)
        {
            Buffer(b); Need(width==4 || width==8); int first=width==8?8:4, stride=width==8?16:8;
            uint count=U32(b,0); Need(count<=4096 && first+(long)count*stride<=b.Length);
            int minimum=first+(int)count*stride; TokenGroupFact[] result=new TokenGroupFact[(int)count];
            HashSet<string> seen=new HashSet<string>(StringComparer.Ordinal);
            for(int i=0;i<result.Length;i++) { int at=first+i*stride; uint a=U32(b,at+width); ValidateGroupAttributes(a);
                string sid=Sid(b,address,Pointer(b,at,width),minimum); Need(seen.Add(sid)); result[i]=new TokenGroupFact { Sid=sid,Attributes=a }; }
            return result;
        }
        public static TokenPrivilegeFact[] DecodePrivileges(byte[] b,Func<uint,int,string> resolve)
        {
            Buffer(b); Need(resolve!=null); uint count=U32(b,0); Need(count<=4096 && 4+(long)count*12==b.Length);
            TokenPrivilegeFact[] result=new TokenPrivilegeFact[(int)count]; HashSet<string> seen=new HashSet<string>(StringComparer.Ordinal);
            for(int i=0;i<result.Length;i++) { int at=4+i*12; uint a=U32(b,at+8); Need((a&~0x80000003u)==0);
                string name=resolve(U32(b,at),unchecked((int)U32(b,at+4)));
                Need(name!=null && name.Length>0 && name.Length<=256 && name.StartsWith("Se",StringComparison.Ordinal) && name.EndsWith("Privilege",StringComparison.Ordinal) && seen.Add(name));
                for(int j=0;j<name.Length;j++) Need((name[j]>='A' && name[j]<='Z') || (name[j]>='a' && name[j]<='z'));
                result[i]=new TokenPrivilegeFact { Name=name, Attributes=a }; }
            return result;
        }
        static string PrivilegeName(uint low,int high)
        {
            Luid id=new Luid { Low=low,High=high }; uint length=257; StringBuilder name=new StringBuilder(257);
            Need(LookupPrivilegeNameW(null,ref id,name,ref length) && length>0 && length<=256 && name.Length==length); return name.ToString();
        }
        public static bool IsStandard(TokenObservation o)
        {
            if(o==null || String.IsNullOrEmpty(o.Sid) || o.Pid==0 || o.CreationFileTime<=0 || o.Elevated || o.Integrity!="S-1-16-8192" || o.Groups==null || o.Privileges==null || o.Groups.Length>4096 || o.Privileges.Length>4096) return false;
            HashSet<string> groups=new HashSet<string>(StringComparer.Ordinal), privileges=new HashSet<string>(StringComparer.Ordinal);
            foreach(TokenGroupFact g in o.Groups) { if(g==null || String.IsNullOrEmpty(g.Sid) || !groups.Add(g.Sid)) return false;
                try { ValidateGroupAttributes(g.Attributes); } catch(InvalidOperationException) { return false; }
                if(g.Sid=="S-1-5-32-544" && (g.Attributes&4)!=0) return false; }
            foreach(TokenPrivilegeFact p in o.Privileges) if(p==null || String.IsNullOrEmpty(p.Name) || !privileges.Add(p.Name) || (p.Attributes&~0x80000003u)!=0 || ((p.Attributes&2)!=0 && p.Name!="SeChangeNotifyPrivilege")) return false;
            return true;
        }
        static TokenObservation ReadCore()
        {
            Need(Environment.OSVersion.Platform==PlatformID.Win32NT); IntPtr token;
            Need(OpenProcessToken(GetCurrentProcess(),8,out token) && token!=IntPtr.Zero);
            try {
                TokenObservation o=new TokenObservation(); ulong address; byte[] b; int width=IntPtr.Size, stride=width==8?16:8;
                b=ReadToken(token,1,out address); Need(b.Length>=stride && U32(b,width)==0); o.Sid=Sid(b,address,Pointer(b,0,width),stride);
                b=ReadToken(token,20,out address); Need(b.Length==4 && U32(b,0)<=1); o.Elevated=U32(b,0)==1;
                b=ReadToken(token,25,out address); Need(b.Length>=stride && U32(b,width)==0x60); o.Integrity=Sid(b,address,Pointer(b,0,width),stride);
                b=ReadToken(token,2,out address); o.Groups=DecodeGroups(b,address,width);
                b=ReadToken(token,3,out address); o.Privileges=DecodePrivileges(b,PrivilegeName);
                List<string> enabled=new List<string>(); foreach(TokenPrivilegeFact p in o.Privileges) if((p.Attributes&2)!=0) enabled.Add(p.Name); o.EnabledPrivileges=enabled.ToArray();
                long created,exited,kernel,user; Need(GetProcessTimes(GetCurrentProcess(),out created,out exited,out kernel,out user));
                o.Pid=GetCurrentProcessId(); o.CreationFileTime=created; Need(o.Pid!=0 && created>0); o.Standard=IsStandard(o); return o;
            } finally { Need(CloseHandle(token)); }
        }
        public static TokenObservation Read()
        {
            try { return ReadCore(); }
            catch(Exception) { throw new InvalidOperationException("S0_TOKEN_BLOCKED"); }
        }
        public static TokenObservation RequireStandard(string expectedSid)
        {
            Need(!String.IsNullOrEmpty(expectedSid)); TokenObservation o=Read();
            Need(o.Standard && String.Equals(o.Sid,expectedSid,StringComparison.Ordinal)); return o;
        }
    }
}
