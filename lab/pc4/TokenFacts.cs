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
  static IntPtr Info(IntPtr t,int cls) {
   int n; bool first=GetTokenInformation(t,cls,IntPtr.Zero,0,out n);
   if(first || Marshal.GetLastWin32Error()!=122 || n<4 || n>65536) throw new InvalidOperationException("TOKEN_BUFFER_INVALID");
   IntPtr b=Marshal.AllocHGlobal(n);
   try { int used; Need(GetTokenInformation(t,cls,b,n,out used)); if(used>n) throw new InvalidOperationException("TOKEN_SIZE_INVALID"); return b; }
   catch { Marshal.FreeHGlobal(b); throw; }
  }
  static string Sid(IntPtr p) { return new SecurityIdentifier(p).Value; }
  public static Facts Read(int pid,bool currentThread) {
   IntPtr process=OpenProcess(0x1000,false,pid); if(process==IntPtr.Zero) throw new Win32Exception();
   IntPtr token=IntPtr.Zero;
   try {
    Need(OpenProcessToken(process,8,out token)); Facts f=new Facts(); IntPtr b;
    b=Info(token,1);try{f.sid=Sid(Marshal.ReadIntPtr(b));}finally{Marshal.FreeHGlobal(b);}
    b=Info(token,2);try{
     int count=Marshal.ReadInt32(b); if(count<0 || count>512)throw new InvalidOperationException("GROUP_COUNT_INVALID");
     int offset=IntPtr.Size==8?8:4; int stride=Marshal.SizeOf(typeof(SidAttr));
     for(int i=0;i<count;i++) { SidAttr g=(SidAttr)Marshal.PtrToStructure(IntPtr.Add(b,offset+i*stride),typeof(SidAttr)); if(Sid(g.Sid)=="S-1-5-32-544") f.admin_group=true; }
    }finally{Marshal.FreeHGlobal(b);}
    b=Info(token,20);try{f.elevated=Marshal.ReadInt32(b)!=0;}finally{Marshal.FreeHGlobal(b);}
    b=Info(token,25);try{string s=Sid(Marshal.ReadIntPtr(b));f.integrity_rid=int.Parse(s.Substring(s.LastIndexOf('-')+1));}finally{Marshal.FreeHGlobal(b);}
    b=Info(token,3);try{
     int count=Marshal.ReadInt32(b);if(count<1 || count>128)throw new InvalidOperationException("PRIV_COUNT_INVALID");
     List<Privilege> list=new List<Privilege>();int stride=Marshal.SizeOf(typeof(LuidAttr));
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
   }finally{if(token!=IntPtr.Zero)CloseHandle(token);CloseHandle(process);}
  }
 }
}
