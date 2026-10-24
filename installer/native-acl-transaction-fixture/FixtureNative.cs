#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Text;
using Microsoft.Win32.SafeHandles;
// Not linked into the observer. No caller-supplied target path, ACL or journal is accepted.
internal sealed class OwnedFixture:IDisposable
{
 readonly List<SafeFileHandle> parents=new();
 public SafeFileHandle Root{get;} public SafeFileHandle Target{get;private set;} public SafeFileHandle Journal{get;private set;}
 public string Path{get;} public string Old{get;} public string New{get;} public TxBinding Binding{get;}
 public Identity JournalId{get;}
 readonly List<(SafeFileHandle Handle,Identity Id,string Sd)> custody=new();
 readonly string journalDescriptor;
 public OwnedFixture(string head,string run,string attempt,string sid){
  try{
   string temp=System.IO.Path.GetFullPath(Environment.GetEnvironmentVariable("RUNNER_TEMP")??throw new Blocked("FIXTURE_TEMP_MISSING")).TrimEnd('\\');
   var parts=Policy.Components(temp);
   for(int n=0;n<parts.Length;n++){
    var h=n==0?Native.OpenRoot(parts[n]):Native.OpenChild(parents[^1],parts[n],true);parents.Add(h);Policy.Object(Native.Id(h),true);
    if(Native.Id(h).Volume!=Native.Id(parents[0]).Volume)throw new Blocked("FIXTURE_VOLUME");
   }
   string name="native-acl-tx-"+Guid.NewGuid().ToString("D");Path=System.IO.Path.Combine(temp,name);
   var descriptor=new RawSecurityDescriptor("D:P(A;;FA;;;SY)(A;;FA;;;"+sid+")");
   Root=FixtureNative.Create(parents[^1],name,true,descriptor);parents.Add(Root);
   Target=FixtureNative.Create(Root,"target.fixture",false,descriptor);parents.Add(Target);
   Journal=FixtureNative.Create(Root,"journal.jsonl",false,descriptor);parents.Add(Journal);
   JournalId=Native.Id(Journal);journalDescriptor=FixtureNative.Descriptor(Journal);
   // NtCreateFile may clear AUTO_INHERITED even if requested in the input SD.
   // Canonicalize ONLY this just-created private target before the journal binding.
   // Require precisely the same owner/group/ACEs and the API's known control-bit result.
   var targetId=Native.Id(Target);var initial=FixtureNative.Descriptor(Target);
   var canonical=new RawSecurityDescriptor(Convert.FromBase64String(initial),0);
   canonical.SetFlags(canonical.ControlFlags|ControlFlags.DiscretionaryAclAutoInherited);
   FixtureNative.SetDacl(Target,initial);Old=FixtureNative.Descriptor(Target);
   if(Native.Id(Target)!=targetId || Old!=FixtureNative.Encode(canonical))throw new Blocked("FIXTURE_INITIAL_CANONICALIZATION");
   foreach(var h in parents.Where(h=>h!=Target))custody.Add((h,Native.Id(h),FixtureNative.Descriptor(h)));
   var next=new RawSecurityDescriptor(Convert.FromBase64String(Old),0);
   next.DiscretionaryAcl=new RawSecurityDescriptor("D:P(A;;FA;;;SY)(A;;0x160089;;;"+sid+")").DiscretionaryAcl;
   New=FixtureNative.Encode(next);Binding=new TxBinding(1,head,run,attempt,Guid.NewGuid().ToString("D"),Native.Id(Root),Native.Id(Target),Old,New);
   if(!FixtureNative.ProtectedFor(FixtureNative.Descriptor(Root),sid) || !FixtureNative.ProtectedFor(Old,sid) || !FixtureNative.ProtectedFor(FixtureNative.Descriptor(Journal),sid))throw new Blocked("FIXTURE_INITIAL_CUSTODY");
  }catch{Dispose();throw;}
 }
 public void Guard(string expected)=>GuardCore(expected,Binding.Target);
 public void GuardMarkerDeletePending()=>GuardCore(Old,FixtureNative.PendingMarker(Target,Binding.Target));
 void GuardCore(string expected,Identity expectedTarget){
  var root=Native.Id(Root);var target=Native.Id(Target);var journal=Native.Id(Journal);var actual=FixtureNative.Descriptor(Target);
  if(root!=Binding.Root || target!=expectedTarget || journal!=JournalId || actual!=expected){
   var failure=new Blocked("FIXTURE_CUSTODY_CHANGED");
   failure.Data["fixture_diagnostic"]=new{root_matches=root==Binding.Root,target_matches=target==Binding.Target,journal_matches=journal==JournalId,
    descriptor_matches=actual==expected,actual_fixture_descriptor=actual,expected_fixture_descriptor=expected};throw failure;
  }
  foreach(var c in custody)if(Native.Id(c.Handle)!=c.Id || FixtureNative.Descriptor(c.Handle)!=c.Sd)throw new Blocked("FIXTURE_ANCESTOR_OR_JOURNAL_DRIFT");
 }
 public void ReopenChildren(){
  // Simulated barrier restart only: harness keeps the root/ancestor handles. Not OS crash evidence.
  custody.RemoveAll(c=>c.Handle==Journal);Target.Dispose();Journal.Dispose();
  Target=FixtureNative.OpenExisting(Root,"target.fixture",0x160089);parents.Add(Target);
  Journal=FixtureNative.OpenExisting(Root,"journal.jsonl",0x1f01ff);parents.Add(Journal);
  if(Native.Id(Target)!=Binding.Target || Native.Id(Journal)!=JournalId || FixtureNative.Descriptor(Journal)!=journalDescriptor)throw new Blocked("FIXTURE_REOPEN_IDENTITY");
  custody.Add((Journal,JournalId,journalDescriptor));
 }
 public void Change(string expected,string next){Guard(expected);FixtureNative.SetDacl(Target,next);Guard(next);}
 public void Dispose(){for(int n=parents.Count-1;n>=0;n--)parents[n].Dispose();parents.Clear();}
}
internal static class FixtureNative
{
 [StructLayout(LayoutKind.Sequential)]struct StandardInfo{public long AllocationSize,EndOfFile;public uint Links;public byte DeletePending,Directory;}
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool GetFileInformationByHandleEx(SafeFileHandle h,int kind,out StandardInfo info,uint size);
 public static void ValidatePendingMarker(Identity before,Identity after,uint links,bool pending,bool directory){
  // Only the diagnosed one-link -> zero-accessible-links terminal state is admitted.
  Policy.Object(before,false);
  if(before.Links!=1 || after!=(before with{Links=0}) || links!=0 || !pending || directory)throw new Blocked("FIXTURE_MARKER_PENDING_IDENTITY_OR_STATE");
 }
 public static Identity PendingMarker(SafeFileHandle handle,Identity before){
  Need(GetFileInformationByHandleEx(handle,1,out var info,(uint)Marshal.SizeOf<StandardInfo>()),"MARKER_STANDARD_INFO");
  var after=Native.Id(handle);ValidatePendingMarker(before,after,info.Links,info.DeletePending==1,info.Directory!=0);return after;
 }

 [StructLayout(LayoutKind.Sequential)]struct U{public ushort Length,MaximumLength;public IntPtr Buffer;}
 [StructLayout(LayoutKind.Sequential)]struct A{public int Length;public IntPtr RootDirectory,ObjectName;public uint Attributes;public IntPtr SecurityDescriptor,SecurityQualityOfService;}
 [StructLayout(LayoutKind.Sequential)]struct I{public IntPtr Status,Information;}
 [DllImport("ntdll.dll")]static extern int NtCreateFile(out SafeFileHandle h,uint access,ref A a,out I io,IntPtr size,uint attr,uint share,uint disposition,uint options,IntPtr ea,uint eaSize);
 [DllImport("advapi32.dll")]static extern uint GetSecurityInfo(SafeFileHandle h,int type,uint request,out IntPtr owner,out IntPtr group,out IntPtr dacl,out IntPtr sacl,out IntPtr sd);
 [DllImport("advapi32.dll")]static extern uint SetSecurityInfo(SafeFileHandle h,int type,uint request,IntPtr owner,IntPtr group,IntPtr dacl,IntPtr sacl);
 [DllImport("advapi32.dll")]static extern uint GetSecurityDescriptorLength(IntPtr sd);
 [DllImport("kernel32.dll")]static extern IntPtr LocalFree(IntPtr p);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool WriteFile(SafeFileHandle h,byte[] bytes,uint count,out uint wrote,IntPtr overlap);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool ReadFile(SafeFileHandle h,byte[] bytes,uint count,out uint read,IntPtr overlap);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool SetFilePointerEx(SafeFileHandle h,long offset,out long current,uint mode);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool GetFileSizeEx(SafeFileHandle h,out long size);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool FlushFileBuffers(SafeFileHandle h);
 static void Need(bool ok,string code){if(!ok)throw new Blocked("FIXTURE_"+code,Marshal.GetLastWin32Error());}
 public static string Encode(RawSecurityDescriptor sd){var b=new byte[sd.BinaryLength];sd.GetBinaryForm(b,0);return Convert.ToBase64String(b);}
 public static bool ProtectedFor(string sd,string sid){
  var d=new RawSecurityDescriptor(Convert.FromBase64String(sd),0);
  return d.DiscretionaryAcl!=null && d.DiscretionaryAcl.Count==2 && (d.ControlFlags&ControlFlags.DiscretionaryAclProtected)!=0 &&
   d.DiscretionaryAcl.Cast<GenericAce>().All(a=>a is CommonAce c && !c.IsCallback && c.AceFlags==AceFlags.None && c.AceQualifier==AceQualifier.AccessAllowed && c.AccessMask==0x1f01ff && (c.SecurityIdentifier.Value==sid || c.SecurityIdentifier.Value=="S-1-5-18"));
 }
 public static SafeFileHandle Create(SafeFileHandle parent,string component,bool directory,RawSecurityDescriptor sd)=>Open(parent,component,directory,sd,2,0x1f01ff);
 public static SafeFileHandle OpenExisting(SafeFileHandle parent,string component,uint access)=>Open(parent,component,false,null,1,access);
 public static SafeFileHandle ProbeData(SafeFileHandle parent,string component,bool write)=>Open(parent,component,false,null,1,write?0x100002u:0x100001u,7);
 static SafeFileHandle Open(SafeFileHandle parent,string component,bool directory,RawSecurityDescriptor? sd,uint disposition,uint access,uint share=0){
  if(component.Contains('\\') || component.Contains('/') || component.Contains(':') || component is "" or "." or "..")throw new Blocked("FIXTURE_COMPONENT");
  IntPtr text=IntPtr.Zero,unicode=IntPtr.Zero,security=IntPtr.Zero;
  try{
   text=Marshal.StringToHGlobalUni(component);var u=new U{Length=checked((ushort)(component.Length*2)),MaximumLength=checked((ushort)((component.Length+1)*2)),Buffer=text};
   unicode=Marshal.AllocHGlobal(Marshal.SizeOf<U>());Marshal.StructureToPtr(u,unicode,false);
   if(sd!=null){var raw=Convert.FromBase64String(Encode(sd));security=Marshal.AllocHGlobal(raw.Length);Marshal.Copy(raw,0,security,raw.Length);}
   var a=new A{Length=Marshal.SizeOf<A>(),RootDirectory=parent.DangerousGetHandle(),ObjectName=unicode,Attributes=0x1040,SecurityDescriptor=security};
   // FILE_CREATE: never adopt/overwrite an existing object. No share read/write/delete.
   // Begin with ARCHIVE already set: appending the journal must not create an attribute-only identity mismatch.
   int status=NtCreateFile(out var h,access,ref a,out _,IntPtr.Zero,directory?0x10u:0x20u,share,disposition,0x200020u|(directory?1u:0x40u),IntPtr.Zero,0);GC.KeepAlive(parent);
   if(status!=0 || h.IsInvalid){h.Dispose();throw new Blocked("FIXTURE_CREATE_REFUSED",status);}
   try{Policy.Object(Native.Id(h),directory);return h;}catch{h.Dispose();throw;}
  }finally{if(text!=IntPtr.Zero)Marshal.FreeHGlobal(text);if(unicode!=IntPtr.Zero)Marshal.FreeHGlobal(unicode);if(security!=IntPtr.Zero)Marshal.FreeHGlobal(security);}
 }
 public static string Descriptor(SafeFileHandle h){
  uint error=GetSecurityInfo(h,1,7,out _,out _,out _,out _,out var p);
  try{if(error!=0 || p==IntPtr.Zero)throw new Blocked("FIXTURE_SECURITY_INFO",unchecked((int)error));
   uint size=GetSecurityDescriptorLength(p);Need(size>=20 && size<=131072,"DESCRIPTOR_SIZE");
   var bytes=new byte[size];Marshal.Copy(p,bytes,0,checked((int)size));return Encode(new RawSecurityDescriptor(bytes,0));
  }finally{if(p!=IntPtr.Zero)LocalFree(p);}
 }
 // Called only with an owned newly-created leaf file. Never directories: no propagation.
 internal static void SetDacl(SafeFileHandle h,string value){
  Policy.Object(Native.Id(h),false);if((Native.Id(h).Attributes&0x10)!=0)throw new Blocked("FIXTURE_LEAF_ONLY");
  var d=new RawSecurityDescriptor(Convert.FromBase64String(value),0);
  if(d.DiscretionaryAcl==null || (d.ControlFlags&ControlFlags.DiscretionaryAclProtected)==0 || d.DiscretionaryAcl.Count==0)throw new Blocked("FIXTURE_DACL_INCOMPLETE");
  var raw=new byte[d.DiscretionaryAcl.BinaryLength];d.DiscretionaryAcl.GetBinaryForm(raw,0);IntPtr p=Marshal.AllocHGlobal(raw.Length);
  try{Marshal.Copy(raw,0,p,raw.Length);uint e=SetSecurityInfo(h,1,0x80000004,IntPtr.Zero,IntPtr.Zero,p,IntPtr.Zero);if(e!=0)throw new Blocked("FIXTURE_SET_DACL",unchecked((int)e));}
  finally{Marshal.FreeHGlobal(p);}
 }
 public static byte[] Read(SafeFileHandle h){
  Need(GetFileSizeEx(h,out long length) && length>=0 && length<=262144,"JOURNAL_SIZE");Need(SetFilePointerEx(h,0,out _,0),"JOURNAL_SEEK");
  var bytes=new byte[checked((int)length)];Need(ReadFile(h,bytes,(uint)bytes.Length,out uint got,IntPtr.Zero) && got==bytes.Length,"JOURNAL_READ");return bytes;
 }
 public static void AppendFlush(SafeFileHandle h,byte[] line,bool injectFlush=false){
  Need(line.Length>0 && line.Length<262144,"JOURNAL_WRITE_SIZE");Need(SetFilePointerEx(h,0,out _,2),"JOURNAL_SEEK");
  Need(WriteFile(h,line,(uint)line.Length,out uint wrote,IntPtr.Zero) && wrote==line.Length,"JOURNAL_WRITE");
  if(injectFlush)throw new Blocked("INJECTED_FIXTURE_FLUSH_FAILURE");
  Need(FlushFileBuffers(h),"JOURNAL_FLUSH");
 }
}
