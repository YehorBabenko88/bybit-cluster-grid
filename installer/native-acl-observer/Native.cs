#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.IO;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Win32.SafeHandles;
[assembly:DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
internal static class Native
{
 internal static string? Fault;
 static void Inject(string name){if(Fault==name)throw new Blocked("INJECTED_"+name);}
 const uint Read=Policy.ShareReadAccess,Share=3,OBJ_DONT_REPARSE=0x1000;
 [StructLayout(LayoutKind.Sequential)]struct UnicodeName{public ushort Length,MaximumLength;public IntPtr Buffer;}
 [StructLayout(LayoutKind.Sequential)]struct ObjectAttributes{public int Length;public IntPtr RootDirectory,ObjectName;public uint Attributes;public IntPtr SecurityDescriptor,SecurityQualityOfService;}
 [StructLayout(LayoutKind.Sequential)]struct IoStatus{public IntPtr Status,Information;}
 [StructLayout(LayoutKind.Sequential)]struct FileInfo{
  public uint Attributes;public System.Runtime.InteropServices.ComTypes.FILETIME C,A,W;
  public uint Volume,SizeHigh,SizeLow,Links,IndexHigh,IndexLow;
 }
 [StructLayout(LayoutKind.Sequential)]struct FileId{public ulong Volume,Low,High;}
 [StructLayout(LayoutKind.Sequential)]struct Mapping{public uint Read,Write,Execute,All;}
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true,EntryPoint="CreateFileW")]
 static extern SafeFileHandle CreateFile(string p,uint a,uint s,IntPtr sa,uint d,uint f,IntPtr t);
 [DllImport("ntdll.dll")]static extern int NtCreateFile(out SafeFileHandle h,uint access,ref ObjectAttributes a,out IoStatus io,IntPtr size,uint attr,uint share,uint disposition,uint options,IntPtr ea,uint eaSize);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool GetFileInformationByHandle(SafeFileHandle h,out FileInfo info);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool GetFileInformationByHandleEx(SafeFileHandle h,int c,out FileId id,uint size);
 [DllImport("kernel32.dll")]static extern uint GetFileType(SafeFileHandle h);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true,ExactSpelling=true)]static extern bool GetVolumeInformationByHandleW(SafeFileHandle h,StringBuilder name,uint n,out uint serial,out uint max,out uint flags,StringBuilder fs,uint fsSize);
 [DllImport("advapi32.dll")]static extern uint GetSecurityInfo(SafeFileHandle h,int type,uint requested,out IntPtr owner,out IntPtr group,out IntPtr dacl,out IntPtr sacl,out IntPtr descriptor);
 [DllImport("advapi32.dll")]static extern uint GetSecurityDescriptorLength(IntPtr p);
 [DllImport("advapi32.dll")]static extern bool IsValidSecurityDescriptor(IntPtr p);
 [DllImport("kernel32.dll")]static extern IntPtr LocalFree(IntPtr p);
 [DllImport("kernel32.dll")]static extern IntPtr GetCurrentProcess();
 [DllImport("kernel32.dll")]static extern IntPtr GetCurrentThread();
 [DllImport("advapi32.dll",SetLastError=true)]static extern bool OpenThreadToken(IntPtr thread,uint access,bool asSelf,out SafeAccessTokenHandle token);
 [DllImport("advapi32.dll",SetLastError=true)]static extern bool OpenProcessToken(IntPtr process,uint access,out SafeAccessTokenHandle token);
 [DllImport("advapi32.dll",SetLastError=true)]static extern bool DuplicateTokenEx(SafeAccessTokenHandle t,uint access,IntPtr sa,int level,int type,out SafeAccessTokenHandle copy);
 [DllImport("advapi32.dll",SetLastError=true)]static extern bool GetTokenInformation(SafeAccessTokenHandle t,int info,IntPtr buffer,int size,out int required);
 [DllImport("advapi32.dll",SetLastError=true)]static extern bool AccessCheck(IntPtr sd,SafeAccessTokenHandle t,uint desired,ref Mapping mapping,IntPtr privileges,ref uint length,out uint granted,out bool allowed);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true,ExactSpelling=true)]static extern uint QueryDosDeviceW(string name,StringBuilder target,uint size);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true,ExactSpelling=true)]static extern uint GetFinalPathNameByHandleW(SafeFileHandle h,StringBuilder name,uint size,uint flags);
 public static SafeFileHandle OpenRoot(string root){
  var mapping=new StringBuilder(32768);
  if(QueryDosDeviceW(root[..2],mapping,32768)==0)throw new Blocked("ROOT_MAPPING_UNPROVEN");
  var h=CreateFile("\\\\?\\"+root,Read|0x20,Share,IntPtr.Zero,3,0x02200000,IntPtr.Zero);
  try{
   if(h.IsInvalid)throw new Blocked("ROOT_OPEN_FAILED",Marshal.GetLastWin32Error());
   var final=new StringBuilder(32768);uint length=GetFinalPathNameByHandleW(h,final,32768,2);
   if(length==0 || length>=32768)throw new Blocked("ROOT_MAPPING_UNPROVEN");
   Policy.RootMapping(mapping.ToString(),final.ToString());return h;
  }catch{h.Dispose();throw;}
 }
 public static SafeFileHandle OpenChild(SafeFileHandle parent,string name,bool directory){
  IntPtr text=IntPtr.Zero,u=IntPtr.Zero;
  try{
   text=Marshal.StringToHGlobalUni(name);var n=new UnicodeName{Length=checked((ushort)(name.Length*2)),MaximumLength=checked((ushort)((name.Length+1)*2)),Buffer=text};
   u=Marshal.AllocHGlobal(Marshal.SizeOf<UnicodeName>());Marshal.StructureToPtr(n,u,false);
   // parent is retained by caller; one component only; do not follow reparses.
   var a=new ObjectAttributes{Length=Marshal.SizeOf<ObjectAttributes>(),RootDirectory=parent.DangerousGetHandle(),ObjectName=u,Attributes=0x40|OBJ_DONT_REPARSE};
   int status=NtCreateFile(out var child,Read|(directory?0x20u:0u),ref a,out _,IntPtr.Zero,0,Share,1,0x00200020|(directory?1u:0u),IntPtr.Zero,0);
   GC.KeepAlive(parent);
   if(status!=0 || child.IsInvalid){child.Dispose();throw new Blocked("NT_OPEN_FAILED",status);}return child;
  }finally{if(u!=IntPtr.Zero)Marshal.FreeHGlobal(u);if(text!=IntPtr.Zero)Marshal.FreeHGlobal(text);}
 }
 public static Identity Id(SafeFileHandle h){
  Inject("IDENTITY");
  if(GetFileType(h)!=1 || !GetFileInformationByHandle(h,out var f) || !GetFileInformationByHandleEx(h,18,out var id,24))throw new Blocked("IDENTITY_API_FAILED");
  var fs=new StringBuilder(32);if(!GetVolumeInformationByHandleW(h,new StringBuilder(256),256,out _,out _,out _,fs,32) || fs.ToString()!="NTFS")throw new Blocked("FILESYSTEM_UNSUPPORTED");
  return new Identity(id.Volume,id.High.ToString("X16")+id.Low.ToString("X16"),f.Links,f.Attributes);
 }
 public static SafeAccessTokenHandle CaptureToken(){
  Inject("TOKEN_OPEN");
  SafeAccessTokenHandle original;
  if(!OpenThreadToken(GetCurrentThread(),10,true,out original)){
   int error=Marshal.GetLastWin32Error();original.Dispose();
   if(error!=1008 || !OpenProcessToken(GetCurrentProcess(),10,out original))throw new Blocked("TOKEN_OPEN_FAILED");
  }
  using(original){if(!DuplicateTokenEx(original,8,IntPtr.Zero,2,2,out var copy)){copy.Dispose();throw new Blocked("TOKEN_DUPLICATION_FAILED");}return copy;}
 }
 static byte[] TokenBytes(SafeAccessTokenHandle t,int type){
  Inject("TOKEN_QUERY");
  bool probe=GetTokenInformation(t,type,IntPtr.Zero,0,out int size);
  int probeError=Marshal.GetLastWin32Error();
  if(type!=20)throw new Blocked("TOKEN_SCALAR_CLASS");
  Policy.ScalarProbe(probe,probeError,size);
  IntPtr p=Marshal.AllocHGlobal(size);
  try{if(!GetTokenInformation(t,type,p,size,out int used) || used!=size)throw new Blocked("TOKEN_QUERY_FAILED");
   var b=new byte[size];Marshal.Copy(p,b,0,size);return b;
  }finally{Marshal.FreeHGlobal(p);}
 }
 // SID pointers from native TOKEN_GROUPS are validated inside their live buffer.
 static List<GroupFact> Groups(SafeAccessTokenHandle t){
  GetTokenInformation(t,2,IntPtr.Zero,0,out int size);
  if(Marshal.GetLastWin32Error()!=122 || size<4 || size>1048576)throw new Blocked("TOKEN_GROUP_SIZE");
  IntPtr p=Marshal.AllocHGlobal(size);
  try{
   if(!GetTokenInformation(t,2,p,size,out int used) || used!=size)throw new Blocked("TOKEN_GROUP_QUERY");
   int count=Marshal.ReadInt32(p);int offset=IntPtr.Size==8?8:4;int stride=IntPtr.Size==8?16:8;
   Policy.GroupLayout(count,size,IntPtr.Size);
   var groups=new List<GroupFact>();
   for(int i=0;i<count;i++){
    var item=IntPtr.Add(p,offset+i*stride);var sid=Marshal.ReadIntPtr(item);long delta=sid.ToInt64()-p.ToInt64();
    Policy.SidBounds(delta,size,offset+count*stride,0);
    int sub=Marshal.ReadByte(sid,1);Policy.SidBounds(delta,size,offset+count*stride,sub);int length=8+4*sub;
    var bytes=new byte[length];Marshal.Copy(sid,bytes,0,length);var value=new SecurityIdentifier(bytes,0).Value;
    uint flags=unchecked((uint)Marshal.ReadInt32(item,IntPtr.Size));Policy.GroupFlags(flags);groups.Add(new GroupFact(value,flags));
   }return groups;
  }finally{Marshal.FreeHGlobal(p);}
 }
 public static TokenFact TokenFacts(SafeAccessTokenHandle t){
  using var identity=new WindowsIdentity(t.DangerousGetHandle());var user=identity.User?.Value??throw new Blocked("TOKEN_USER_UNKNOWN");
  bool elevated=Policy.ScalarElevation(BitConverter.ToUInt32(TokenBytes(t,20),0));
  // WindowsIdentity provides native validated user/group SIDs. Integrity pointer
  // need not be dereferenced: token SID list includes the integrity label.
  var groups=Groups(t);uint level;
  GetTokenInformation(t,25,IntPtr.Zero,0,out int size);
  if(Marshal.GetLastWin32Error()!=122 || size<16 || size>1048576)throw new Blocked("TOKEN_LABEL_SIZE");
  var buffer=Marshal.AllocHGlobal(size);
  try{
   if(!GetTokenInformation(t,25,buffer,size,out int used) || used!=size)throw new Blocked("TOKEN_LABEL_QUERY");
   var ptr=Marshal.ReadIntPtr(buffer);long delta=ptr.ToInt64()-buffer.ToInt64();Policy.SidBounds(delta,size,IntPtr.Size+4,0);
   int sub=Marshal.ReadByte(ptr,1);Policy.SidBounds(delta,size,IntPtr.Size+4,sub);
   var label=new byte[8+4*sub];Marshal.Copy(ptr,label,0,label.Length);var sid=new SecurityIdentifier(label,0).Value;
   if(!sid.StartsWith("S-1-16-",StringComparison.Ordinal) || !uint.TryParse(sid[7..],out level))throw new Blocked("TOKEN_INTEGRITY_UNKNOWN");
  }finally{Marshal.FreeHGlobal(buffer);}
  var hash=Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(new{user,elevated,level,groups})));
  return new TokenFact(user,elevated,level,groups,hash);
 }
 public static Observation Observe(SafeFileHandle h,SafeAccessTokenHandle token,int depth){
  var id=Id(h);Policy.Object(id,false);
  Inject("DESCRIPTOR");
  uint error=GetSecurityInfo(h,1,7,out _,out _,out _,out _,out IntPtr sd);
  if(error!=0){if(sd!=IntPtr.Zero)LocalFree(sd);throw new Blocked("SECURITY_INFO_FAILED",unchecked((int)error));}
  try{
   if(sd==IntPtr.Zero)throw new Blocked("DESCRIPTOR_MISSING");
   uint size=GetSecurityDescriptorLength(sd);
   if(!IsValidSecurityDescriptor(sd) || size<20 || size>1048576)throw new Blocked("DESCRIPTOR_INVALID");
   var bytes=new byte[size];Marshal.Copy(sd,bytes,0,checked((int)size));var d=new RawSecurityDescriptor(bytes,0);
   if(d.Owner==null || d.Group==null || d.DiscretionaryAcl==null)throw new Blocked("DESCRIPTOR_INCOMPLETE");
   var aces=new List<AceFact>();
   foreach(GenericAce a in d.DiscretionaryAcl){
    if(a is not CommonAce c || c.IsCallback || c.AceQualifier is not(AceQualifier.AccessAllowed or AceQualifier.AccessDenied))throw new Blocked("ACE_UNSUPPORTED");
    if(((int)c.AceFlags&~31)!=0)throw new Blocked("ACE_FLAGS_UNSUPPORTED");
    aces.Add(new AceFact(c.SecurityIdentifier.Value,c.AccessMask,(int)c.AceFlags,c.AceQualifier.ToString()));
   }
   var rights=new Dictionary<string,string>();
   foreach(var pair in new Dictionary<string,uint>{{"DELETE",0x10000},{"WRITE_DAC",0x40000},{"WRITE_OWNER",0x80000},{"WRITE_DATA",2},{"APPEND_DATA",4},{"DELETE_CHILD",0x40}}){
    if(pair.Key=="DELETE_CHILD" && (id.Attributes&0x10)==0)continue;
    uint length=1024;IntPtr privileges=Marshal.AllocHGlobal((int)length);
    try{var mapping=new Mapping{Read=0x120089,Write=0x120116,Execute=0x1200A0,All=0x1F01FF};
     Inject("ACCESS_CHECK");Inject("PRIVILEGE");
     if(!AccessCheck(sd,token,pair.Value,ref mapping,privileges,ref length,out uint granted,out bool allowed))throw new Blocked("ACCESS_CHECK_FAILED",Marshal.GetLastWin32Error());
     if(length>1024 || (allowed && (granted&pair.Value)!=pair.Value))throw new Blocked("ACCESS_CHECK_STRUCTURE");
     int usedPrivileges=Marshal.ReadInt32(privileges);
     if(usedPrivileges<0 || usedPrivileges>80)throw new Blocked("PRIVILEGE_SET_INVALID");
     rights[pair.Key]=usedPrivileges!=0?"BLOCKED_PRIVILEGED_ACCESS":(allowed?"DACL_ALLOW":"DACL_DENY");
    }finally{Marshal.FreeHGlobal(privileges);}
   }
   return new Observation(depth,id,d.Owner.Value,d.Group.Value,Convert.ToHexString(SHA256.HashData(bytes)),
    (d.ControlFlags&ControlFlags.DiscretionaryAclProtected)!=0,aces,rights);
  }finally{LocalFree(sd);}
 }
}
