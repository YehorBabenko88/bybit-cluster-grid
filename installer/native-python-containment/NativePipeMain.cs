using System.Buffers.Binary;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Win32.SafeHandles;

// Explicit one-way FIXED_PING fixture; no broker verbs, network or Grid adapter.
internal static class NativePipeMain {
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern SafeFileHandle CreateFileW(string path,uint access,uint share,IntPtr attributes,uint disposition,uint flags,IntPtr template);
 static string Env(string key)=>Environment.GetEnvironmentVariable(key)??"";
 static string Hash(byte[] bytes)=>Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
 static void Copy(string folder,string name,byte[] raw){using var f=new FileStream(System.IO.Path.Combine(Env("GITHUB_WORKSPACE"),folder,name),FileMode.CreateNew,FileAccess.Write,FileShare.Read);f.Write(raw);f.Flush(true);}
 internal static int Run(bool debugged){
  string folder=debugged?"pipe-debugged-evidence":"pipe-undebugged-evidence";string? error=null,inputHash=null,resultHash=null,frameHash=null;object? identity=null,parent=null,configuration=null,ownership=null;JsonElement? result=null;bool readerJoined=false,retained=false;int? exitCode=null;IReadOnlyList<LoaderFact> loader=Array.Empty<LoaderFact>();
  try{
   var measured=TransportMain.ReadInput("pipe-input","PIPE_INPUT_SHA256");var input=measured.Input;inputHash=measured.ManifestHash;ControllerPolicy.Need(PipeExecutable.ModelTests(),"PIPE_LENGTH_MODELS");
   using var original=Native.CaptureToken();var facts=Native.TokenFacts(original);using var current=Process.GetCurrentProcess();parent=new{pid=Environment.ProcessId,creation_time=current.StartTime.ToFileTimeUtc(),token=facts};
   using var canaryRoot=new OwnedFixture(input.Head,input.Run,input.Attempt,facts.User);string canaryPath=System.IO.Path.Combine(canaryRoot.Path,"outside.fixture");Identity canaryId;string canaryDescriptor;
   using(var made=FixtureNative.Create(canaryRoot.Root,"outside.fixture",false,new RawSecurityDescriptor("D:P(A;;FA;;;SY)(A;;FA;;;"+facts.User+")"))){FixtureNative.AppendFlush(made,System.Text.Encoding.ASCII.GetBytes("synthetic nonsecret fixture"));canaryId=Native.Id(made);canaryDescriptor=FixtureNative.Descriptor(made);}
   using var canary=CreateFileW(canaryPath,0x80020000,7,IntPtr.Zero,3,0x200000,IntPtr.Zero);ControllerPolicy.Need(!canary.IsInvalid&&Native.Id(canary)==canaryId&&FixtureNative.Descriptor(canary)==canaryDescriptor,"PIPE_CANARY_PIN");string canaryHash=Hash(FixtureNative.Read(canary));
   string nonce=Guid.NewGuid().ToString("N");object config=new{schema=1,head=input.Head,run_id=input.Run,attempt=input.Attempt,nonce,parent_pid=Environment.ProcessId,canary=canaryPath};configuration=config;PythonBundle? bundle=null;PipeExecutable? pipe=null;string package="";
   using var child=new OwnedChild(facts.User,(sid,moniker)=>{package=sid;bundle=new PythonBundle(sid,moniker,facts.User,input,measured.ManifestHash,config,debugged,"pipe-input");return pipe=new PipeExecutable(bundle,facts.User,sid);});
   var activePipe=pipe??throw new Blocked("PIPE_WRAPPER_MISSING");var activeBundle=bundle??throw new Blocked("PIPE_BUNDLE_MISSING");identity=child.SecuritySnapshot(facts.User,package);activePipe.DropParentWriter();ownership=activePipe.OwnershipFacts();using var cancellation=new CancellationTokenSource();Task<byte[]>? reading=null;byte[]? frame=null;
   try{
    child.Resume();reading=Task.Run(()=>activePipe.ReadBounded(cancellation.Token,TimeSpan.FromSeconds(30)));
    try{child.Wait(90000);exitCode=0;}catch(Exception e){error=e is Blocked b?b.Code:e.GetType().Name;}
    try{frame=reading.WaitAsync(TimeSpan.FromSeconds(5)).GetAwaiter().GetResult();readerJoined=true;}catch(Exception e){error??="PIPE_FRAME_"+(e is Blocked b?b.Code:e.GetType().Name);}
   }finally{
    cancellation.Cancel();if(reading!=null&&!reading.IsCompleted){try{reading.WaitAsync(TimeSpan.FromSeconds(3)).GetAwaiter().GetResult();readerJoined=true;}catch{error??="PIPE_READER_JOIN_UNKNOWN";}}else if(reading!=null)readerJoined=true;
    retained=reading!=null&&!reading.IsCompleted;
   }
   loader=child.LoaderEvents;
   if(child.Exited){
    try{byte[] raw=activeBundle.Result();resultHash=Hash(raw);result=JsonDocument.Parse(raw).RootElement.Clone();ControllerPolicy.Need(result.Value.GetProperty("pid").GetInt32()==child.ProcessId,"PIPE_RESULT_PID");Copy(folder,"child.json",raw);}catch(Exception e){error??="PIPE_RESULT_"+(e is Blocked b?b.Code:e.GetType().Name);}
    try{Copy(folder,"diagnostics.txt",activeBundle.Diagnostics());}catch(Exception e){error??="PIPE_DIAGNOSTICS_"+e.GetType().Name;}
   }else error??="PIPE_CHILD_STILL_RUNNING";
   if(frame!=null){
    byte[] body=JsonSerializer.SerializeToUtf8Bytes(new{attempt=input.Attempt,head=input.Head,nonce,pid=child.ProcessId,run_id=input.Run,schema=1,verb="ping"});byte[] expected=new byte[body.Length+4];BinaryPrimitives.WriteUInt32LittleEndian(expected,(uint)body.Length);body.CopyTo(expected,4);
    ControllerPolicy.Need(frame.AsSpan().SequenceEqual(expected),"FIXED_PING_CONTEXT");frameHash=Hash(frame);Copy(folder,"frame.bin",frame);
   }else error??="PIPE_FRAME_UNAVAILABLE";
   canaryRoot.Guard(canaryRoot.Old);ControllerPolicy.Need(Native.Id(canary)==canaryId&&FixtureNative.Descriptor(canary)==canaryDescriptor&&Hash(FixtureNative.Read(canary))==canaryHash,"PIPE_CANARY_CHANGED");
  }catch(Exception e){error??=e is Blocked b?b.Code:"PIPE_PARENT_"+e.GetType().Name;}
  Console.WriteLine(JsonSerializer.Serialize(new{schema=1,head=Env("EXACT_HEAD_SHA"),run_id=Env("GITHUB_RUN_ID"),attempt=Env("GITHUB_RUN_ATTEMPT"),profile="ONE_WAY_FIXED_PING_PROTOTYPE_ONLY",debugged,status="BLOCKED",reason=error??"OWNER_AUTHORIZATION_AND_FULL_TRANSPORT_UNPROVEN",prototype_result=error==null?"FIXED_PING_OBSERVED":"INCOMPLETE",parent,config=configuration,child_identity=identity,pipe_ownership=ownership,input_manifest_sha256=inputHash,result_sha256=resultHash,frame_sha256=frameHash,reader_joined=readerJoined,retained_on_unknown=retained,child_exit_code=exitCode,loader_events=loader,child=result,host_verified=false,execute_authorized=false,cleanup_authorized=false,physical="0/10 NOT_RUN",whole_system="PARTIAL",fixture_teardown="HELD_HANDLES_CLOSED_OR_RETAINED_DISPOSABLE_VM_TEARDOWN_REQUIRED"}));return 1;
 }
}
