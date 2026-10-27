using System.Buffers.Binary;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using Microsoft.Win32.SafeHandles;

// Hosted caller must gate before construction. This object owns only its fresh
// anonymous pipe and delegated bundle; it never opens a named pipe or endpoint.
internal sealed class PipeExecutable:IOwnedExecutable {
 const int MaxPayload=512,MaxFrame=MaxPayload+4;
 const int PackageWrite=0x120116;
 [StructLayout(LayoutKind.Sequential)]struct SecurityAttributes{public uint length;public IntPtr descriptor;[MarshalAs(UnmanagedType.Bool)]public bool inherit;}
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool CreatePipe(out IntPtr read,out IntPtr write,ref SecurityAttributes attributes,uint size);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool SetHandleInformation(SafeFileHandle handle,uint mask,uint flags);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool GetHandleInformation(SafeFileHandle handle,out uint flags);
 [DllImport("kernel32.dll",SetLastError=true)]static extern uint GetFileType(SafeFileHandle handle);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool PeekNamedPipe(SafeFileHandle handle,IntPtr buffer,uint size,IntPtr read,out uint available,IntPtr left);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool ReadFile(SafeFileHandle handle,[Out]byte[] bytes,uint size,out uint read,IntPtr overlapped);
 readonly PythonBundle bundle;
 readonly object gate=new();
 readonly string user,package;
 SafeFileHandle? reader,writer;
 string descriptor="",creationDescriptor="";
 bool dropped,disposed;
 volatile bool readStarted,readFinished,retainedOnUnknown;
 public string Path=>bundle.Path;
 public string CommandLine=>bundle.CommandLine;
 public string WorkingDirectory=>bundle.WorkingDirectory;
 public string EnvironmentBlock=>bundle.EnvironmentBlock;
 public bool TraceLoader=>bundle.TraceLoader;
 public SafeFileHandle? OutputHandle=>writer;
 static void Need(bool condition,string code){if(!condition)throw new Blocked(code);}
 static Blocked Error(string operation)=>new("PIPE_"+operation+"_WIN32_"+Marshal.GetLastWin32Error());
 internal PipeExecutable(PythonBundle bundle,string userSID,string packageSID){
  this.bundle=bundle;user=new SecurityIdentifier(userSID).Value;package=new SecurityIdentifier(packageSID).Value;
  Need(user!=package&&user!="S-1-5-18"&&package.StartsWith("S-1-15-2-",StringComparison.Ordinal),"PIPE_SID_BINDING");
  IntPtr security=IntPtr.Zero;
  try{
   var sd=new RawSecurityDescriptor("D:P(A;;FA;;;SY)(A;;FA;;;"+user+")(A;;0x120116;;;"+package+")S:(ML;;NW;;;LW)");
   var bytes=new byte[sd.BinaryLength];sd.GetBinaryForm(bytes,0);creationDescriptor=Convert.ToBase64String(bytes);
   security=Marshal.AllocHGlobal(bytes.Length);Marshal.Copy(bytes,0,security,bytes.Length);
   var attributes=new SecurityAttributes{length=(uint)Marshal.SizeOf<SecurityAttributes>(),descriptor=security,inherit=true};
   // On failed CreatePipe its outputs are indeterminate; do not adopt them.
   if(!CreatePipe(out var read,out var write,ref attributes,4096))throw Error("CREATE");
   reader=new SafeFileHandle(read,true);writer=new SafeFileHandle(write,true);
   if(!SetHandleInformation(reader,1,0))throw Error("READ_INHERIT_CLEAR");
   if(!SetHandleInformation(writer,1,1))throw Error("WRITE_INHERIT_SET");
   descriptor=FixtureNative.Descriptor(reader);ValidateDescriptor(descriptor);Guard();
  }catch{Dispose();throw;}finally{if(security!=IntPtr.Zero)Marshal.FreeHGlobal(security);}
 }
 void ValidateDescriptor(string encoded){
  var sd=new RawSecurityDescriptor(Convert.FromBase64String(encoded),0);
  var expected=new Dictionary<string,int>{{"S-1-5-18",0x1f01ff},{user,0x1f01ff},{package,PackageWrite}};
  Need((sd.ControlFlags&ControlFlags.DiscretionaryAclProtected)!=0&&sd.DiscretionaryAcl!=null&&sd.DiscretionaryAcl.Count==3,"PIPE_DACL_SHAPE");
  var seen=new HashSet<string>();
  foreach(GenericAce ace in sd.DiscretionaryAcl!){
   Need(ace is CommonAce,"PIPE_DACL_ACE_TYPE");var common=(CommonAce)ace;
   Need(!common.IsCallback&&common.AceFlags==AceFlags.None&&common.AceQualifier==AceQualifier.AccessAllowed&&expected.TryGetValue(common.SecurityIdentifier.Value,out int mask)&&common.AccessMask==mask&&seen.Add(common.SecurityIdentifier.Value),"PIPE_DACL_GRANT");
  }
 }
 void GuardCore(){
  Need(!disposed&&reader!=null&&!reader.IsClosed&&!reader.IsInvalid,"PIPE_READ_CUSTODY");
  Need(GetFileType(reader!)==3,"PIPE_READ_TYPE");
  Need(GetHandleInformation(reader!,out uint readFlags)&&(readFlags&1)==0,"PIPE_READ_INHERITANCE");
  string current=FixtureNative.Descriptor(reader!);ValidateDescriptor(current);Need(current==descriptor,"PIPE_DACL_DRIFT");
  if(dropped)Need(writer!=null&&writer.IsClosed,"PIPE_PARENT_WRITER_NOT_CLOSED");
  else{
   Need(writer!=null&&!writer.IsClosed&&!writer.IsInvalid,"PIPE_WRITE_CUSTODY");
   Need(GetFileType(writer!)==3,"PIPE_WRITE_TYPE");
   Need(GetHandleInformation(writer!,out uint writeFlags)&&(writeFlags&1)==1,"PIPE_WRITE_INHERITANCE");
  }
 }
 public void Guard(){
  if(readStarted){
   // Never queue behind a possibly stalled synchronous pipe call. Reader alone
   // owns native read-handle operations until it has joined.
   bundle.Guard();Need(!disposed&&dropped&&reader!=null&&!reader.IsClosed&&!reader.IsInvalid&&writer!=null&&writer.IsClosed,"PIPE_ACTIVE_READ_CUSTODY");return;
  }
  lock(gate){bundle.Guard();GuardCore();}
 }
 public void ValidateModule(SafeFileHandle handle,string path)=>bundle.ValidateModule(handle,path);
 // Required order: successful suspended child creation, this call, then Resume.
 internal void DropParentWriter(){lock(gate){GuardCore();Need(!dropped,"PIPE_WRITER_DROP_REPLAY");writer!.Dispose();dropped=true;GuardCore();}}
 internal object OwnershipFacts(){
  // Snapshot before starting the reader; never wait behind native read I/O.
  Need(!readStarted,"PIPE_FACTS_AFTER_READER_REFUSED");
  lock(gate){Need(!readStarted,"PIPE_FACTS_AFTER_READER_REFUSED");GuardCore();return new{schema=1,descriptor_base64=descriptor,creation_descriptor_base64=creationDescriptor,dacl_ace_count=3,package_dacl_grant_mask=PackageWrite,granted_access="NOT_INDEPENDENTLY_QUERIED",read_handle_inheritable=false,write_handle_inheritable_before_drop=true,parent_writer_closed=dropped,label="LABEL_UNVERIFIED",retained_on_unknown=retainedOnUnknown,assurance="OBSERVED_NOT_ATTESTED",host_verified=false,execute_authorized=false,cleanup_authorized=false};}
 }
 internal bool RetainedOnUnknown=>retainedOnUnknown;
 internal static bool ValidFrameLength(uint length)=>length is >0 and <=MaxPayload;
 internal static bool ModelTests()=>ValidFrameLength(1)&&ValidFrameLength(512)&&!ValidFrameLength(0)&&!ValidFrameLength(513)&&!ValidFrameLength(uint.MaxValue);
 internal byte[] ReadBounded(CancellationToken cancellation,TimeSpan timeout){
  Need(timeout>TimeSpan.Zero&&timeout<=TimeSpan.FromSeconds(30),"PIPE_READ_DEADLINE_BOUND");
  lock(gate){GuardCore();Need(dropped&&!readStarted,"PIPE_READ_LIFECYCLE");readStarted=true;}
  try{
   var clock=Stopwatch.StartNew();var frame=new List<byte>(MaxFrame);uint? payloadLength=null;
   while(true){
    Need(!cancellation.IsCancellationRequested,"PIPE_READ_CANCELLED");Need(clock.Elapsed<timeout,"PIPE_READ_TIMEOUT");
    // Sole reader and serialized access on this handle avoid competing reads.
    // CreatePipe handles are synchronous: this is a cooperative polling bound,
    // not an OS guarantee that PeekNamedPipe cannot stall. Outer hosted process
    // supervisor must enforce its own deadline (per Microsoft Peek docs).
    if(!PeekNamedPipe(reader!,IntPtr.Zero,0,IntPtr.Zero,out uint available,IntPtr.Zero)){
     int error=Marshal.GetLastWin32Error();
     if(error!=109)throw new Blocked("PIPE_PEEK_WIN32_"+error);
     Need(payloadLength.HasValue&&frame.Count==4+(int)payloadLength.Value,"PIPE_EOF_FRAME_UNKNOWN");
     return frame.ToArray();
    }
    Need(available<=MaxFrame-frame.Count,"PIPE_FRAME_OVERSIZE");
    if(available==0){if(cancellation.WaitHandle.WaitOne(10))throw new Blocked("PIPE_READ_CANCELLED");continue;}
    var bytes=new byte[(int)available];
    if(!ReadFile(reader!,bytes,available,out uint read,IntPtr.Zero))throw Error("READ");
    Need(read>0&&read<=available,"PIPE_READ_COUNT_UNKNOWN");
    for(int i=0;i<(int)read;i++)frame.Add(bytes[i]);
    if(!payloadLength.HasValue&&frame.Count>=4){payloadLength=BinaryPrimitives.ReadUInt32LittleEndian(frame.ToArray().AsSpan(0,4));Need(ValidFrameLength(payloadLength.Value),"PIPE_PAYLOAD_LENGTH_BOUND");}
    if(payloadLength.HasValue)Need(frame.Count<=4+(int)payloadLength.Value,"PIPE_TRAILING_BYTES");
   }
  }finally{readFinished=true;}
 }
 public void Dispose(){
  // No blocking lock and no closing/reusing handles underneath an unknown
  // synchronous reader. Retain until a subsequent joined disposal or VM exit.
  if(readStarted&&!readFinished){retainedOnUnknown=true;return;}
  lock(gate){if(disposed)return;if(readStarted&&!readFinished){retainedOnUnknown=true;return;}disposed=true;writer?.Dispose();reader?.Dispose();bundle.Dispose();}
 }
}
