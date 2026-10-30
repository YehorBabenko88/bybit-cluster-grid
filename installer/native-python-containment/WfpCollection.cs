using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

// Diagnostic preparation ONLY for an exclusively owned disposable GitHub VM.
// COLLECT_NET_EVENTS is GLOBAL, not session/handle-owned. These files are not a
// durable anti-rollback service, physical cleanup authority, or reboot recovery.
// No filter, exemption, ACL, service, account, or network capability is changed.
// API contracts: learn.microsoft.com/windows/win32/api/fwpmu/
// nf-fwpmu-fwpmenginegetoption0 and nf-fwpmu-fwpmenginesetoption0.
internal static class WfpCollection {
 const int CollectNetEvents=0;
 const uint FwpUint32=3;
 const string Repo="YehorBabenko88/bybit-cluster-grid";
 [StructLayout(LayoutKind.Explicit,Size=16)]
 internal struct Value { [FieldOffset(0)]internal uint Type; [FieldOffset(8)]internal uint Data; }
 internal record Context(string Head,string Run,string Attempt,string Machine,string Workspace);
 internal record Prepared(int Schema,string Phase,Context Context,int Option,uint Original);
 internal record Enabled(int Schema,string Phase,Context Context,string PreparedSha256,uint Observed);
 [DllImport("fwpuclnt.dll",CharSet=CharSet.Unicode,ExactSpelling=true)]
 static extern uint FwpmEngineOpen0(string? serverName,uint authnService,IntPtr authIdentity,IntPtr session,out IntPtr engine);
 [DllImport("fwpuclnt.dll",ExactSpelling=true)]static extern uint FwpmEngineGetOption0(IntPtr engine,int option,out IntPtr value);
 [DllImport("fwpuclnt.dll",ExactSpelling=true)]static extern uint FwpmEngineSetOption0(IntPtr engine,int option,ref Value value);
 [DllImport("fwpuclnt.dll",ExactSpelling=true)]static extern uint FwpmEngineClose0(IntPtr engine);
 [DllImport("fwpuclnt.dll",ExactSpelling=true)]static extern void FwpmFreeMemory0(ref IntPtr memory);

 static string Env(string name)=>Environment.GetEnvironmentVariable(name)??"";
 static void Need(bool valid,string code){if(!valid)throw new InvalidOperationException(code);}
 static byte[] Canon<T>(T value)=>JsonSerializer.SerializeToUtf8Bytes(value);
 static string Hash(byte[] value)=>Convert.ToHexString(SHA256.HashData(value)).ToLowerInvariant();
 static T Parse<T>(byte[] raw){
  Need(raw.Length is >0 and <=16384,"WFP_RECORD_SIZE");
  try{var value=JsonSerializer.Deserialize<T>(raw,new JsonSerializerOptions{MaxDepth=8});Need(value!=null&&Canon(value).AsSpan().SequenceEqual(raw),"WFP_RECORD_NONCANONICAL");return value!;}
  catch(JsonException){throw new InvalidOperationException("WFP_RECORD_INVALID");}
 }
 static byte[] Read(FileStream file){
  Need(file.Length is >0 and <=16384,"WFP_RECORD_SIZE");var raw=new byte[(int)file.Length];file.ReadExactly(raw);return raw;
 }
 static FileStream Create(string path,byte[] bytes){
  var file=new FileStream(path,FileMode.CreateNew,FileAccess.ReadWrite,FileShare.None);
  try{file.Write(bytes);file.Flush(true);return file;}catch{file.Dispose();throw;}
 }
 static Context Guard(string action){
  Need(action is "enable" or "restore" or "model","WFP_ACTION_REFUSED");
  string machine=Environment.MachineName;
  Need(OperatingSystem.IsWindows()&&Environment.Is64BitProcess&&IntPtr.Size==8&&
       Marshal.SizeOf<Value>()==16&&Marshal.OffsetOf<Value>(nameof(Value.Data)).ToInt32()==8&&
       !machine.Contains("LS5",StringComparison.OrdinalIgnoreCase)&&!machine.Contains("PC4",StringComparison.OrdinalIgnoreCase)&&
       Env("GITHUB_ACTIONS")=="true"&&Env("RUNNER_ENVIRONMENT")=="github-hosted"&&
       Env("GITHUB_REPOSITORY")==Repo&&Env("GITHUB_JOB")=="python-containment","WFP_HOSTED_DISPOSABLE_ONLY");
  Need(Regex.IsMatch(Env("EXACT_HEAD_SHA"),"^[0-9a-f]{40}$")&&
       Regex.IsMatch(Env("GITHUB_RUN_ID"),"^[1-9][0-9]{0,19}$")&&
       Regex.IsMatch(Env("GITHUB_RUN_ATTEMPT"),"^[1-9][0-9]{0,9}$"),"WFP_CONTEXT");
  string workspace=Env("GITHUB_WORKSPACE");
  Need(workspace.Length is >0 and <=2048&&Regex.IsMatch(workspace,@"^[A-Za-z]:\\")&&
       !workspace.Any(c=>c<32)&&Path.IsPathFullyQualified(workspace),"WFP_WORKSPACE");
  workspace=Path.GetFullPath(workspace).TrimEnd(Path.DirectorySeparatorChar);
  Need(Directory.Exists(Path.Combine(workspace,"python-containment-evidence")),"WFP_EVIDENCE_DIRECTORY_REQUIRED");
  return new(Env("EXACT_HEAD_SHA"),Env("GITHUB_RUN_ID"),Env("GITHUB_RUN_ATTEMPT"),machine,workspace);
 }
 static uint Get(IntPtr engine){
  IntPtr memory=IntPtr.Zero;
  try{uint result=FwpmEngineGetOption0(engine,CollectNetEvents,out memory);Need(result==0,"WFP_GET_"+result);Need(memory!=IntPtr.Zero,"WFP_GET_NULL");
   var value=Marshal.PtrToStructure<Value>(memory);Need(value.Type==FwpUint32&&value.Data<=1,"WFP_OPTION_VALUE");return value.Data;
  }finally{if(memory!=IntPtr.Zero)FwpmFreeMemory0(ref memory);}
 }
 static void Set(IntPtr engine,uint data){
  Need(data<=1,"WFP_OPTION_VALUE");var value=new Value{Type=FwpUint32,Data=data};uint result=FwpmEngineSetOption0(engine,CollectNetEvents,ref value);Need(result==0,"WFP_SET_"+result);
 }
 static void Validate(Prepared prepared,Enabled enabled,byte[] preparedBytes,Context context){
  Need(prepared.Schema==1&&prepared.Phase=="PREPARED"&&prepared.Context==context&&prepared.Option==CollectNetEvents&&prepared.Original<=1,"WFP_PREPARED_BINDING");
  Need(enabled.Schema==1&&enabled.Phase=="ENABLED"&&enabled.Context==context&&enabled.Observed==1&&
       enabled.PreparedSha256==Hash(preparedBytes),"WFP_ENABLED_BINDING");
 }
 static bool WriteRequired(string action,uint original,uint current){
  Need(original<=1&&current<=1,"WFP_OPTION_VALUE");
  Need(action is "enable" or "restore","WFP_ACTION_REFUSED");
  Need(action=="enable"?current==original:current==1,"WFP_CURRENT_CHANGED");
  return original==0;
 }
 // Optional pure managed checks for a later hosted model harness; no native or I/O.
 internal static void ModelTests(){
  var c=new Context(new string('a',40),"1","1","disposable","D:\\fixture");
  foreach(uint original in new uint[]{0,1}){
   var p=new Prepared(1,"PREPARED",c,0,original);byte[] raw=Canon(p);
   var e=new Enabled(1,"ENABLED",c,Hash(raw),1);Validate(Parse<Prepared>(raw),Parse<Enabled>(Canon(e)),raw,c);
   bool refused=false;try{Validate(p,e with{PreparedSha256=new string('0',64)},raw,c);}catch(InvalidOperationException){refused=true;}Need(refused,"WFP_MODEL_HASH_REFUSAL");
   refused=false;try{Validate(p,e,raw,c with{Attempt="2"});}catch(InvalidOperationException){refused=true;}Need(refused,"WFP_MODEL_CONTEXT_REFUSAL");
   refused=false;try{Parse<Prepared>(raw.Concat(new byte[]{32}).ToArray());}catch(InvalidOperationException){refused=true;}Need(refused,"WFP_MODEL_NONCANONICAL_REFUSAL");
   Need(WriteRequired("enable",original,original)==(original==0)&&WriteRequired("restore",original,1)==(original==0),"WFP_MODEL_TRANSITION");
   refused=false;try{WriteRequired("restore",original,0);}catch(InvalidOperationException){refused=true;}Need(refused,"WFP_MODEL_CHANGED_CURRENT_REFUSAL");
  }
 }
 internal static int Run(string action){
  IntPtr engine=IntPtr.Zero;string? reason=null;uint? original=null,current=null;bool writeAttempted=false;Context? context=null;
  try{
   context=Guard(action);string folder=Path.Combine(context.Workspace,"python-containment-evidence");
   string preparedPath=Path.Combine(folder,"wfp-collection-prepared.json"),enabledPath=Path.Combine(folder,"wfp-collection-enabled.json");
   // This assumption is essential: no competing WFP option writers on this VM.
   // File locking serializes this helper, NOT unrelated administrators/processes.
   if(action=="model"){ModelTests();}
   else if(action=="restore"){
    using var pf=new FileStream(preparedPath,FileMode.Open,FileAccess.Read,FileShare.None);
    using var ef=new FileStream(enabledPath,FileMode.Open,FileAccess.Read,FileShare.None);
    byte[] raw=Read(pf);var p=Parse<Prepared>(raw);var e=Parse<Enabled>(Read(ef));Validate(p,e,raw,context);original=p.Original;
    uint opened=FwpmEngineOpen0(null,10,IntPtr.Zero,IntPtr.Zero,out engine);Need(opened==0&&engine!=IntPtr.Zero,"WFP_OPEN_"+opened);
    current=Get(engine);
    bool restoreWrite=WriteRequired(action,original.Value,current.Value);
    using var intent=Create(Path.Combine(folder,"wfp-collection-restore-intent.json"),Canon(new{Schema=1,Phase="RESTORE_INTENT",Context=context,PreparedSha256=Hash(raw)}));
    if(restoreWrite){writeAttempted=true;Set(engine,0);current=Get(engine);Need(current==0,"WFP_RESTORE_READBACK");}
   }else{
    // Existing or partial attempts cannot be adopted or overwritten.
    Need(!File.Exists(preparedPath)&&!File.Exists(enabledPath),"WFP_EXISTING_STATE_REFUSED");
    uint opened=FwpmEngineOpen0(null,10,IntPtr.Zero,IntPtr.Zero,out engine);Need(opened==0&&engine!=IntPtr.Zero,"WFP_OPEN_"+opened);
    original=Get(engine);var p=new Prepared(1,"PREPARED",context,CollectNetEvents,original.Value);byte[] raw=Canon(p);
    using var pf=Create(preparedPath,raw);
    Need(!File.Exists(enabledPath),"WFP_EXISTING_ENABLED_REFUSED");
    // Refuse observed interference before changing global diagnostic collection.
    current=Get(engine);
    if(WriteRequired(action,original.Value,current.Value)){writeAttempted=true;Set(engine,1);}
    current=Get(engine);Need(current==1,"WFP_ENABLE_READBACK");
    using var ef=Create(enabledPath,Canon(new Enabled(1,"ENABLED",context,Hash(raw),1)));
   }
  }catch(Exception e){reason=e is InvalidOperationException?e.Message:"WFP_COLLECTION_"+e.GetType().Name;}
  finally{if(engine!=IntPtr.Zero){try{uint closed=FwpmEngineClose0(engine);if(closed!=0)reason??="WFP_CLOSE_"+closed;}catch{reason??="WFP_CLOSE_UNKNOWN";}}}
  Console.WriteLine(JsonSerializer.Serialize(new{schema=1,action,status=reason==null?"PASS":"BLOCKED",reason,context,
   original,current,global_option_write_attempted=writeAttempted,option="FWPM_ENGINE_COLLECT_NET_EVENTS_ONLY",
   assurance="DEDICATED_DISPOSABLE_GITHUB_VM_DIAGNOSTIC_ONLY",exclusive_vm_assumed=true,
   uncertain_state_policy="NO_AUTOMATIC_REPAIR_DISPOSABLE_VM_TEARDOWN_REQUIRED",
   external_nonrollback_anchor=false,reboot_recovery_proven=false,host_verified=false,
   execute_authorized=false,cleanup_authorized=false,physical="0/10 NOT_RUN",g1="BLOCKED"}));
  return reason==null?0:1;
 }
}
