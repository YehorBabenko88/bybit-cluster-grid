// Collector only. Compilation does not collect anything. No token creation,
// privilege adjustment, account changes or credential handling.
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace GridPc4 {
 public sealed class Privilege { public string name; public bool enabled; }
 public sealed class Facts {
  public string sid; public bool admin_group; public bool elevated;
  public int integrity_rid; public bool impersonating; public Privilege[] privileges;
 }
 public static class TokenFacts {
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern SafeFileHandle CreateFile(string p,uint access,uint share,IntPtr sec,uint create,uint flags,IntPtr template);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetFileInformationByHandle(SafeFileHandle h,out FileInfo i);
  [StructLayout(LayoutKind.Sequential)] struct FileInfo {
   public uint Attr,CTLow,CTHigh,ATLow,ATHigh,WTLow,WTHigh,Volume,SizeHigh,SizeLow,Links,IndexHigh,IndexLow;
  }
  public static SafeFileHandle PinDirectory(string path) {
   SafeFileHandle h=CreateFile(path,0x80,3,IntPtr.Zero,3,0x02200000,IntPtr.Zero);
   if(h.IsInvalid){h.Dispose();throw new Win32Exception();}
   try{FileInfo i;Need(GetFileInformationByHandle(h,out i));if((i.Attr&0x400)!=0 || (i.Attr&0x10)==0)throw new InvalidOperationException("DIRECTORY_REDIRECTED");return h;}
   catch{h.Dispose();throw;}
  }
  [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr OpenProcess(uint a,bool inherit,int pid);
  [DllImport("kernel32.dll")] static extern IntPtr GetCurrentThread();
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool CloseHandle(IntPtr h);
  [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenProcessToken(IntPtr p,uint access,out IntPtr t);
  [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenThreadToken(IntPtr p,uint access,bool self,out IntPtr t);
  [DllImport("advapi32.dll",SetLastError=true)] static extern bool GetTokenInformation(IntPtr t,int cls,IntPtr buf,int n,out int len);
  [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool LookupPrivilegeName(string sys,ref Luid id,StringBuilder name,ref int size);
  [StructLayout(LayoutKind.Sequential)] struct Luid { public uint Low; public int High; }
  [StructLayout(LayoutKind.Sequential)] struct LuidAttr { public Luid Id; public uint Attr; }
  [StructLayout(LayoutKind.Sequential)] struct SidAttr { public IntPtr Sid; public uint Attr; }
  static void Need(bool ok) { if(!ok) throw new Win32Exception(Marshal.GetLastWin32Error()); }
  static IntPtr Info(IntPtr t,int cls,out int length) {
   length=0;
   int n; bool first=GetTokenInformation(t,cls,IntPtr.Zero,0,out n);
   if(first || Marshal.GetLastWin32Error()!=122 || n<4 || n>65536) throw new InvalidOperationException("TOKEN_BUFFER_INVALID");
   IntPtr b=Marshal.AllocHGlobal(n);
   try { int used; Need(GetTokenInformation(t,cls,b,n,out used)); if(used<4 || used>n) throw new InvalidOperationException("TOKEN_SIZE_INVALID"); length=used; return b; }
   catch { Marshal.FreeHGlobal(b); throw; }
  }
  static void Range(IntPtr b,int length,int offset,int size) {
   if(b==IntPtr.Zero || length<4 || length>65536 || offset<0 || size<0 || offset>length-size)
    throw new InvalidOperationException("TOKEN_RANGE_INVALID");
  }
  static string Sid(IntPtr b,int length,IntPtr p) {
   long delta=checked(p.ToInt64()-b.ToInt64());
   if(delta<0 || delta>Int32.MaxValue)throw new InvalidOperationException("SID_POINTER_INVALID");
   Range(b,length,(int)delta,8);
   int count=Marshal.ReadByte(p,1);
   if(Marshal.ReadByte(p)!=1 || count>15)throw new InvalidOperationException("SID_HEADER_INVALID");
   Range(b,length,(int)delta,checked(8+4*count));
   return new SecurityIdentifier(p).Value;
  }
  // Pure parser: caller supplies an owned buffer. Never reads a host token.
  public static bool ParseGroupBuffer(IntPtr b,int length) {
   bool present;return ParseGroups(b,length,out present);
  }
  public static bool HasAdministratorGroup(IntPtr b,int length) {
   bool present;ParseGroups(b,length,out present);return present;
  }
  static bool ParseGroups(IntPtr b,int length,out bool present) {
   present=false;
   Range(b,length,0,4);int count=Marshal.ReadInt32(b);
   if(count<0 || count>512)throw new InvalidOperationException("GROUP_COUNT_INVALID");
   int offset=IntPtr.Size==8?8:4;int stride=Marshal.SizeOf(typeof(SidAttr));
   if(count>0)Range(b,length,offset,checked(count*stride));
   bool admin=false;
   for(int i=0;i<count;i++) {
    SidAttr g=(SidAttr)Marshal.PtrToStructure(IntPtr.Add(b,offset+i*stride),typeof(SidAttr));
    if((g.Attr & ~0xE000007Fu)!=0)throw new InvalidOperationException("GROUP_ATTRIBUTES_INVALID");
    if((g.Attr & 0x00000014u)==0x00000014u)throw new InvalidOperationException("GROUP_ATTRIBUTES_CONFLICT");
    string sid=Sid(b,length,g.Sid);
    if(sid=="S-1-5-32-544")present=true;
    if(sid=="S-1-5-32-544" && (g.Attr & 0x00000004u)!=0 && (g.Attr & 0x00000010u)==0)admin=true;
   }
   return admin;
  }
  public static Facts Read(int pid,bool currentThread) {
   IntPtr process=OpenProcess(0x1000,false,pid); if(process==IntPtr.Zero) throw new Win32Exception();
   try{return ReadProcessHandle(process,currentThread);}finally{CloseHandle(process);}
  }
  public static Facts ReadProcessHandle(IntPtr process,bool currentThread) {
   if(process==IntPtr.Zero || process==new IntPtr(-1))throw new InvalidOperationException("PROCESS_HANDLE_INVALID");
   IntPtr token=IntPtr.Zero;
   try {
    Need(OpenProcessToken(process,8,out token)); Facts f=new Facts(); IntPtr b;int length;
    b=Info(token,1,out length);try{Range(b,length,0,Marshal.SizeOf(typeof(SidAttr)));f.sid=Sid(b,length,Marshal.ReadIntPtr(b));}finally{Marshal.FreeHGlobal(b);}
    b=Info(token,2,out length);try{
     bool present;f.admin_group=ParseGroups(b,length,out present);
     // Effective membership is not account provenance: filtered/restricted admin
     // tokens must never become evidence for ordinary-user isolation.
     if(present)throw new InvalidOperationException("ADMIN_MEMBERSHIP_FORBIDDEN");
    }finally{Marshal.FreeHGlobal(b);}
    b=Info(token,20,out length);try{Range(b,length,0,4);int elevation=Marshal.ReadInt32(b);if(elevation!=0 && elevation!=1)throw new InvalidOperationException("ELEVATION_INVALID");f.elevated=elevation==1;}finally{Marshal.FreeHGlobal(b);}
    b=Info(token,25,out length);try{Range(b,length,0,Marshal.SizeOf(typeof(SidAttr)));string s=Sid(b,length,Marshal.ReadIntPtr(b));if(!s.StartsWith("S-1-16-",StringComparison.Ordinal) || s.Split('-').Length!=4)throw new InvalidOperationException("INTEGRITY_SID_INVALID");f.integrity_rid=int.Parse(s.Substring(s.LastIndexOf('-')+1));}finally{Marshal.FreeHGlobal(b);}
    b=Info(token,3,out length);try{
     int count=Marshal.ReadInt32(b);if(count<1 || count>128)throw new InvalidOperationException("PRIV_COUNT_INVALID");
     List<Privilege> list=new List<Privilege>();int stride=Marshal.SizeOf(typeof(LuidAttr));Range(b,length,4,checked(count*stride));
     for(int i=0;i<count;i++) {
      LuidAttr p=(LuidAttr)Marshal.PtrToStructure(IntPtr.Add(b,4+i*stride),typeof(LuidAttr));
      int size=256;StringBuilder name=new StringBuilder(size);Need(LookupPrivilegeName(null,ref p.Id,name,ref size));
      list.Add(new Privilege{name=name.ToString(),enabled=(p.Attr&2)!=0});
     }f.privileges=list.ToArray();
    }finally{Marshal.FreeHGlobal(b);}
    if(currentThread) {
     IntPtr thread;bool ok=OpenThreadToken(GetCurrentThread(),8,true,out thread);
     if(ok){f.impersonating=true;CloseHandle(thread);}else if(Marshal.GetLastWin32Error()!=1008)throw new Win32Exception();
    }
    return f;
   }finally{if(token!=IntPtr.Zero)CloseHandle(token);}
  }
 }
}
