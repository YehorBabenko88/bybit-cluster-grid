// C#5/.NET Framework 4.8. Explicit alternative; never a LocalAppData fallback.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace GridS0 {
 public static partial class Bootstrap {
  internal enum ParentKind { LocalAppData, UserProfileV1 }
  [DllImport("shell32.dll",CharSet=CharSet.Unicode,ExactSpelling=true)] static extern int SHGetKnownFolderPath(ref Guid folder,uint flags,IntPtr token,out IntPtr path);
  [DllImport("userenv.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool GetUserProfileDirectoryW(IntPtr token,StringBuilder path,ref uint count);
  [DllImport("kernel32.dll")] static extern IntPtr GetCurrentThread();
  [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool CloseHandle(IntPtr handle);
  [DllImport("kernel32.dll",ExactSpelling=true)] static extern int GetCurrentPackageFullName(ref uint count,IntPtr name);
  [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenThreadToken(IntPtr thread,uint access,bool self,out IntPtr token);
  [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenProcessToken(IntPtr process,uint access,out IntPtr token);
  [DllImport("advapi32.dll",SetLastError=true)] static extern bool GetTokenInformation(IntPtr token,int kind,out uint data,int length,out int count);
  static void ProfileContext(IntPtr token) {
   IntPtr thread; bool found=OpenThreadToken(GetCurrentThread(),8,true,out thread); int error=Marshal.GetLastWin32Error();
   if(found) { if(thread!=IntPtr.Zero) CloseHandle(thread); Need(false); }
   Need(error==1008); uint app; int actual; Need(GetTokenInformation(token,29,out app,4,out actual) && actual==4 && app==0);
   uint size=0; Need(GetCurrentPackageFullName(ref size,IntPtr.Zero)==15700 && size==0);
  }
  internal static string ReadUserProfile(string sid) {
   TokenObservation before=TokenObserver.RequireStandard(sid); IntPtr token=IntPtr.Zero, raw=IntPtr.Zero;
   try {
    Need(OpenProcessToken(GetCurrentProcess(),8,out token)); ProfileContext(token);
    Guid folder=new Guid("5e6c858f-0e22-4760-9afe-ea3317b67173"); Need(SHGetKnownFolderPath(ref folder,0x4000,IntPtr.Zero,out raw)==0 && raw!=IntPtr.Zero);
    int chars=0; while(chars<=240 && Marshal.ReadInt16(raw,chars*2)!=0) chars++; Need(chars>3 && chars<=240);
    string resolved=Marshal.PtrToStringUni(raw,chars);
    uint count=0; bool first=GetUserProfileDirectoryW(token,null,ref count); int error=Marshal.GetLastWin32Error();
    Need(!first && error==122 && count>4 && count<=241); uint bound=count; var query=new StringBuilder((int)count);
    Need(GetUserProfileDirectoryW(token,query,ref count) && count>0 && count<=bound && query.Length>3 && query.Length<bound);
    Need(ProfilePathsValid(resolved,query.ToString(),Path.GetPathRoot(Environment.GetFolderPath(Environment.SpecialFolder.Windows))));
    ProfileContext(token); TokenObservation after=TokenObserver.RequireStandard(sid);
    Need(before.Pid==after.Pid && before.CreationFileTime==after.CreationFileTime && before.Sid==after.Sid);
    return resolved;
   } finally { if(raw!=IntPtr.Zero) Marshal.FreeCoTaskMem(raw); if(token!=IntPtr.Zero) Need(CloseHandle(token)); }
  }
  internal static bool ProfilePathsValid(string a,string b,string volume) {
   if(a==null || b==null || volume==null || a.Length<=3 || a.Length>240 || !String.Equals(a,b,StringComparison.OrdinalIgnoreCase) ||
      volume.Length!=3 || volume[1]!=':' || volume[2]!='\\' || !a.StartsWith(volume,StringComparison.OrdinalIgnoreCase) || a.IndexOf('/')>=0) return false;
   try { if(a!=Path.GetFullPath(a) || a.EndsWith("\\",StringComparison.Ordinal)) return false; } catch { return false; }
   foreach(string part in a.Substring(3).Split('\\')) {
    if(part.Length==0 || part.TrimEnd(' ','.')!=part || part=="." || part=="..") return false;
    foreach(char c in part) if(c<32 || ":<>\"|?*%~".IndexOf(c)>=0 || Char.IsSurrogate(c)) return false;
    if(Match(part.Split('.')[0].ToUpperInvariant(),"CON|PRN|AUX|NUL|CONIN\\$|CONOUT\\$|COM[0-9\u00b9\u00b2\u00b3]|LPT[0-9\u00b9\u00b2\u00b3]")) return false;
   }
   return true;
  }
  static string ParentPath(string sid,ParentKind kind) {
   Need(kind==ParentKind.LocalAppData || kind==ParentKind.UserProfileV1);
   return kind==ParentKind.UserProfileV1?ReadUserProfile(sid):Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData,Environment.SpecialFolderOption.DoNotVerify).TrimEnd('\\');
  }
  public sealed class UserProfileLease:IDisposable {
   readonly string sid; Pins pins; readonly string path;
   internal UserProfileLease(string s) { sid=s; path=ReadUserProfile(s); pins=new Pins(path,s,true); }
   public string ParentPath { get { Check(); return path; } }
   public string ParentIdentity { get { Check(); return pins.ParentId; } }
   public void Check() { Need(pins!=null && String.Equals(ReadUserProfile(sid),path,StringComparison.OrdinalIgnoreCase)); pins.Check(); }
   public void Dispose() { if(pins!=null) { pins.Dispose(); pins=null; } }
  }
  public static UserProfileLease HoldUserProfileV1(string sid) { return new UserProfileLease(sid); }
  static string SecurityStamp(SafeFileHandle handle,string profileSid=null) {
   IntPtr owner,dacl,raw; Need(GetSecurityInfo(handle,1,7,out owner,IntPtr.Zero,out dacl,IntPtr.Zero,out raw)==0);
   try {
    uint length=GetSecurityDescriptorLength(raw); Need(length>=20 && length<=65536 && owner!=IntPtr.Zero && dacl!=IntPtr.Zero);
    byte[] bytes=new byte[length]; Marshal.Copy(raw,bytes,0,(int)length);
    var descriptor=new RawSecurityDescriptor(bytes,0);
    if(profileSid!=null) foreach(GenericAce entry in descriptor.DiscretionaryAcl) {
     var ace=entry as CommonAce;Need(ace!=null && !ace.IsCallback);
     string trustee=ace.SecurityIdentifier.Value;
     if(ace.AceQualifier==AceQualifier.AccessAllowed && (ace.AceFlags&AceFlags.InheritOnly)==0 && trustee!=profileSid && trustee!=SystemSid && trustee!=AdminSid) Need(((uint)ace.AccessMask&(0x10u|0x100u))==0);
    }
    return Hash(Encoding.Unicode.GetBytes(descriptor.GetSddlForm(AccessControlSections.Owner|AccessControlSections.Group|AccessControlSections.Access)));
   } finally { if(raw!=IntPtr.Zero) LocalFree(raw); }
  }
  public sealed class UserProfileSourceLease:IDisposable {
   readonly string sid,root; Pins ancestry; readonly List<SafeFileHandle> files=new List<SafeFileHandle>();
   readonly List<string> paths=new List<string>(),ids=new List<string>(),stamps=new List<string>();
   internal UserProfileSourceLease(string path,string s,string packageSha,string head) {
    root=path;sid=s;
    try {
     ancestry=new Pins(root,sid); Inspect(ancestry.Parent,root,true,true,sid);
     var pending=new Queue<string>(); pending.Enqueue(root); int count=0; var payloads=new Dictionary<string,byte[]>(StringComparer.Ordinal);
     while(pending.Count>0) foreach(string member in Directory.GetFileSystemEntries(pending.Dequeue())) {
      Need(++count<=20000); FileAttributes attributes=File.GetAttributes(member); Need((attributes&FileAttributes.ReparsePoint)==0);
      bool directory=(attributes&FileAttributes.Directory)!=0; SafeFileHandle handle=directory?Open(member,true,false):TransferReadHandle(member);
      files.Add(handle);paths.Add(member);ids.Add(Inspect(handle,member,directory,true,sid));stamps.Add(SecurityStamp(handle));
      if(directory) pending.Enqueue(member);
      else {
       string relative=member.Substring(root.Length+1).Replace('\\','/');
       using(var borrowed=new SafeFileHandle(handle.DangerousGetHandle(),false)) using(var stream=new FileStream(borrowed,FileAccess.Read,8192,false)) payloads.Add(relative,TransferRead(stream,relative=="source.zip"?(int)MaxZip:(int)MaxFile));
      }
     }
     Need(payloads.ContainsKey("source.zip")); Package expected=Validate(payloads["source.zip"],packageSha,head);
     Need(payloads.Count==expected.Files.Count+1);
     foreach(var item in expected.Files) Need(payloads.ContainsKey(item.Key) && Hash(payloads[item.Key])==Hash(item.Value));
     Check();
    } catch { Dispose(); throw; }
   }
   public void Check() {
    Need(ancestry!=null); ancestry.Check(); Inspect(ancestry.Parent,root,true,true,sid);
    for(int i=0;i<files.Count;i++) {
     Info info; Need(GetFileInformationByHandle(files[i],out info)); bool directory=(info.Attributes&16)!=0;
     Need(Inspect(files[i],paths[i],directory,true,sid)==ids[i] && SecurityStamp(files[i])==stamps[i]);
    }
   }
   public void Dispose() { foreach(var file in files) file.Dispose(); files.Clear(); if(ancestry!=null) { ancestry.Dispose(); ancestry=null; } }
  }
  internal static UserProfileSourceLease HoldUserProfileSourceV1(string root,string sid,string packageSha,string head) { return new UserProfileSourceLease(root,sid,packageSha,head); }
  [StructLayout(LayoutKind.Sequential)] struct UnicodeName { internal ushort Length,MaximumLength; internal IntPtr Buffer; }
  [StructLayout(LayoutKind.Sequential)] struct ObjectAttributes { internal uint Length; internal IntPtr RootDirectory,ObjectName; internal uint Attributes; internal IntPtr SecurityDescriptor,SecurityQos; }
  [DllImport("ntdll.dll")] static extern int NtCreateFile(out SafeFileHandle file,uint access,ref ObjectAttributes attributes,out IoStatus io,IntPtr allocation,uint fileAttributes,uint share,uint disposition,uint options,IntPtr ea,uint eaLength);
  static SafeFileHandle CreateProfileTransaction(SafeFileHandle parent,string leaf,Security security) {
   Need(parent!=null && !parent.IsInvalid && Match(leaf,"\\.GridS0Transaction-[0-9a-f-]{36}"));
   IntPtr name=Marshal.StringToHGlobalUni(leaf), descriptor=IntPtr.Zero; bool retained=false;
   try {
    parent.DangerousAddRef(ref retained);
    var unicode=new UnicodeName { Length=(ushort)(leaf.Length*2),MaximumLength=(ushort)((leaf.Length+1)*2),Buffer=name };
    descriptor=Marshal.AllocHGlobal(Marshal.SizeOf(typeof(UnicodeName))); Marshal.StructureToPtr(unicode,descriptor,false);
    var attributes=new ObjectAttributes { Length=(uint)Marshal.SizeOf(typeof(ObjectAttributes)),RootDirectory=parent.DangerousGetHandle(),ObjectName=descriptor,Attributes=0x40,SecurityDescriptor=security.Attributes.Descriptor };
    SafeFileHandle handle; IoStatus io; int result=NtCreateFile(out handle,0x80000000|0x10000|0x100000,ref attributes,out io,IntPtr.Zero,0x12,3,2,0x200021,IntPtr.Zero,0);
    if(result!=0 || handle==null || handle.IsInvalid || io.Information.ToUInt64()!=2) {
     if(handle!=null) handle.Dispose();
     throw new InvalidOperationException(result!=0?"S0_PROFILE_CREATE_NT_"+result.ToString("X8"):"S0_PROFILE_CREATE_RESULT_BLOCKED");
    }
    return handle;
   } finally { if(descriptor!=IntPtr.Zero) Marshal.FreeHGlobal(descriptor); Marshal.FreeHGlobal(name); if(retained) parent.DangerousRelease(); }
  }
  public static BootstrapReceipt PlanInputAtUserProfileV1(byte[] canonicalPlan,string expectedSha,string expectedHead,string expectedRunId,string targetRoot,string expectedSid) { return Input(canonicalPlan,expectedSha,expectedHead,expectedRunId,targetRoot,expectedSid,false,ParentKind.UserProfileV1); }
  public static BootstrapReceipt StagePlanInputAtUserProfileV1(byte[] canonicalPlan,string expectedSha,string expectedHead,string expectedRunId,string targetRoot,string expectedSid,bool approved) { Need(approved); return Input(canonicalPlan,expectedSha,expectedHead,expectedRunId,targetRoot,expectedSid,true,ParentKind.UserProfileV1); }
  public static BootstrapReceipt PlanRoleImportAtUserProfileV1(byte[] sixFileZip,string expectedSha,string expectedHead,string expectedRunId,string expectedPackageSha,string targetRoot,string expectedSid) { return ImportRole(sixFileZip,expectedSha,expectedHead,expectedRunId,expectedPackageSha,targetRoot,expectedSid,false,ParentKind.UserProfileV1); }
  public static BootstrapReceipt StageRoleImportAtUserProfileV1(byte[] sixFileZip,string expectedSha,string expectedHead,string expectedRunId,string expectedPackageSha,string targetRoot,string expectedSid,bool approved) { Need(approved); return ImportRole(sixFileZip,expectedSha,expectedHead,expectedRunId,expectedPackageSha,targetRoot,expectedSid,true,ParentKind.UserProfileV1); }
  public static TransferSlotReceipt PlanTransferSlotAtUserProfileV1(string head,string run,string payloadSha,long size,string targetRoot,string sid) { return TransferSlot(head,run,payloadSha,size,targetRoot,sid,false,ParentKind.UserProfileV1); }
  public static TransferSlotReceipt StageTransferSlotAtUserProfileV1(string head,string run,string payloadSha,long size,string targetRoot,string sid,bool approved) { Need(approved); return TransferSlot(head,run,payloadSha,size,targetRoot,sid,true,ParentKind.UserProfileV1); }
  public static TransferExportReceipt PlanTransferExportAtUserProfileV1(string sourcePC4RoleRoot,string head,string run,string packageSha,string targetRoot,string sid) { return TransferExport(sourcePC4RoleRoot,head,run,packageSha,targetRoot,sid,false,ParentKind.UserProfileV1); }
  public static TransferExportReceipt StageTransferExportAtUserProfileV1(string sourcePC4RoleRoot,string head,string run,string packageSha,string targetRoot,string sid,bool approved) { Need(approved); return TransferExport(sourcePC4RoleRoot,head,run,packageSha,targetRoot,sid,true,ParentKind.UserProfileV1); }
  public static TransferProbeReceipt PlanTransferProbeAtUserProfileV1(string head,string run,string hostIP,string ed25519Base64Blob,string fullSHA256Fingerprint,string targetNewInputUUID,string sid) { return TransferProbe(head,run,hostIP,ed25519Base64Blob,fullSHA256Fingerprint,targetNewInputUUID,sid,false,ParentKind.UserProfileV1); }
  public static TransferProbeReceipt StageTransferProbeAtUserProfileV1(string head,string run,string hostIP,string ed25519Base64Blob,string fullSHA256Fingerprint,string targetNewInputUUID,string sid,bool approved) { Need(approved); return TransferProbe(head,run,hostIP,ed25519Base64Blob,fullSHA256Fingerprint,targetNewInputUUID,sid,true,ParentKind.UserProfileV1); }
  public static TransferKnownHostsReceipt PlanTransferKnownHostsAtUserProfileV1(string exportRoot,string rootId,string payloadSHA,string head,string run,string hostIP,string ed25519Base64Blob,string fullSHA256Fingerprint,string sid) { return TransferKnownHosts(exportRoot,rootId,payloadSHA,head,run,hostIP,ed25519Base64Blob,fullSHA256Fingerprint,sid,false,ParentKind.UserProfileV1); }
  public static TransferKnownHostsReceipt StageTransferKnownHostsAtUserProfileV1(string exportRoot,string rootId,string payloadSHA,string head,string run,string hostIP,string ed25519Base64Blob,string fullSHA256Fingerprint,string sid,bool approved) { Need(approved); return TransferKnownHosts(exportRoot,rootId,payloadSHA,head,run,hostIP,ed25519Base64Blob,fullSHA256Fingerprint,sid,true,ParentKind.UserProfileV1); }
  public static BootstrapReceipt PlanPackageAtUserProfileV1(byte[] zip,string sha,string head,string target,string sid) { return RunPackage(zip,sha,head,target,sid,false,ParentKind.UserProfileV1); }
  public static TransferSlotLease OpenTransferSlotAtUserProfileV1(string root,string rootId,string fileId,string head,string run,string sha,long size,string sid,bool approved) { return OpenTransferSlotCore(root,rootId,fileId,head,run,sha,size,sid,approved,ParentKind.UserProfileV1); }
  public static BootstrapReceipt PlanTransferImportAtUserProfileV1(TransferSlotLease lease,string head,string run,string packageSha,string target,string sid) {
   Need(lease!=null && lease.BoundKind==ParentKind.UserProfileV1 && lease.BoundHead==head && lease.BoundRun==run && lease.BoundSid==sid);
   return ImportRole(lease.CaptureVerified(),lease.BoundSha,head,run,packageSha,target,sid,false,ParentKind.UserProfileV1);
  }
  public static BootstrapReceipt StageTransferImportAtUserProfileV1(TransferSlotLease lease,string head,string run,string packageSha,string target,string sid,bool approved) {
   Need(approved && lease!=null && lease.BoundKind==ParentKind.UserProfileV1 && lease.BoundHead==head && lease.BoundRun==run && lease.BoundSid==sid);
   return ImportRole(lease.CaptureForImport(),lease.BoundSha,head,run,packageSha,target,sid,true,ParentKind.UserProfileV1);
  }
  public static TransferSenderLease OpenTransferSenderAtUserProfileV1(string root,string rootId,string sha,string knownSha,string sid) {
   SenderRoot(root,rootId,sha,sid,ParentKind.UserProfileV1); Need(Match(knownSha,"[0-9a-f]{64}")); return new TransferSenderLease(root,rootId,sha,knownSha,sid,ParentKind.UserProfileV1);
  }
  public static BootstrapReceipt PlanPackageDiagnosticAtUserProfileV1(byte[] zip,string sha,string head,string target,string sid) {
   Need(!tracePlan); tracePlan=true; try { TracePlan("ENTER"); return RunPackage(zip,sha,head,target,sid,false,ParentKind.UserProfileV1); } finally { tracePlan=false; }
  }
  public static BootstrapReceipt StagePackageAtUserProfileV1(byte[] zip,string sha,string head,string target,string sid,bool approved) { Need(approved); return RunPackage(zip,sha,head,target,sid,true,ParentKind.UserProfileV1); }
 }
 public static partial class ProcessHost {
  [ThreadStatic] static bool traceRuntime;
  static void TraceRuntime(string stage) { if(traceRuntime) { Console.Out.WriteLine("S0_NATIVE_"+stage); Console.Out.Flush(); } }
  // Only post-failure hosted diagnostics; no change to the mandatory cold-first entry.
  public static Result RunDiagnosticAtUserProfileV1(string root,string arguments,IDictionary environment,string sid,string sha,string head,int seconds,string packageSha) {
   if(traceRuntime || Environment.GetEnvironmentVariable("GITHUB_ACTIONS")!="true" || Environment.GetEnvironmentVariable("RUNNER_ENVIRONMENT")!="github-hosted" || Environment.GetEnvironmentVariable("GITHUB_JOB")!="s0-windows" || Environment.GetEnvironmentVariable("GITHUB_REPOSITORY")!="YehorBabenko88/bybit-cluster-grid" || Environment.GetEnvironmentVariable("EXACT_HEAD_SHA")!=head || String.Equals(Environment.MachineName,"LS5",StringComparison.OrdinalIgnoreCase) || String.Equals(Environment.MachineName,"PC4",StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("S0_HOSTED_DIAGNOSTIC_ONLY");
   traceRuntime=true;try { return RunAtUserProfileV1(root,arguments,environment,sid,sha,head,seconds,packageSha); } finally { traceRuntime=false; }
  }
  public static Result RunAtUserProfileV1(string root,string arguments,IDictionary environment,string sid,string sha,string head,int seconds,string packageSha) {
   TraceRuntime("PROFILE_ENTER");
   using(var parent=Bootstrap.HoldUserProfileV1(sid)) {
    TraceRuntime("PROFILE_HELD");
    if(root==null || !String.Equals(Path.GetDirectoryName(Path.GetFullPath(root)),parent.ParentPath,StringComparison.OrdinalIgnoreCase) || !System.Text.RegularExpressions.Regex.IsMatch(Path.GetFileName(root),"\\AGridS0Package-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\\z")) throw new InvalidOperationException("S0_USER_PROFILE_PACKAGE_NAMESPACE");
    TraceRuntime("SOURCE_HOLD");
    using(var source=Bootstrap.HoldUserProfileSourceV1(root,sid,packageSha,head)) {
     TraceRuntime("SOURCE_HELD");parent.Check();TraceRuntime("PARENT_RECHECKED");
     Result result=Run(root,arguments,environment,sid,sha,head,seconds);
     TraceRuntime("PROCESS_RETURN");source.Check();TraceRuntime("SOURCE_RECHECKED");parent.Check();return result;
    }
   }
  }
 }
}
