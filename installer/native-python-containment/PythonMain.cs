using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.AccessControl;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Win32.SafeHandles;
internal static class PythonMain {
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool DuplicateHandle(IntPtr sourceProcess,SafeFileHandle source,IntPtr targetProcess,out SafeFileHandle target,uint access,bool inherit,uint options);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern SafeFileHandle CreateFileW(string path,uint access,uint share,IntPtr attributes,uint disposition,uint flags,IntPtr template);
 static string Env(string n)=>Environment.GetEnvironmentVariable(n)??"";
 static string Hash(byte[] b)=>Convert.ToHexString(SHA256.HashData(b)).ToLowerInvariant();
 static int Main(string[] args){string? error=null;JsonElement? observed=null;string? outputHash=null,inputHash=null;int files=0;int? pid=null;try{
  ControllerPolicy.Need(args.SequenceEqual(new[]{"--hosted-python-tests"})&&OperatingSystem.IsWindows()&&!new[]{"PC4","LS5"}.Contains(Environment.MachineName,StringComparer.OrdinalIgnoreCase)&&Env("GITHUB_ACTIONS")=="true"&&Env("RUNNER_ENVIRONMENT")=="github-hosted"&&Env("GITHUB_REPOSITORY")=="YehorBabenko88/bybit-cluster-grid"&&Env("GITHUB_JOB")=="python-containment","HOSTED_PYTHON_ONLY");
  ControllerPolicy.Need(Regex.IsMatch(Env("EXACT_HEAD_SHA"),"^[0-9a-f]{40}$")&&Regex.IsMatch(Env("GITHUB_RUN_ID"),"^[1-9][0-9]{0,19}$")&&Regex.IsMatch(Env("GITHUB_RUN_ATTEMPT"),"^[1-9][0-9]{0,9}$"),"PYTHON_CONTEXT");
  string manifest=System.IO.Path.Combine(Env("GITHUB_WORKSPACE"),"python-input","manifest.json");ControllerPolicy.Need(new FileInfo(manifest).Length is >0 and <10000000,"PYTHON_MANIFEST_SIZE");byte[] raw=File.ReadAllBytes(manifest);inputHash=Hash(raw);ControllerPolicy.Need(inputHash==Env("PYTHON_INPUT_SHA256"),"PYTHON_MANIFEST_PIN");var input=JsonSerializer.Deserialize<PythonInput>(raw)!;
  ControllerPolicy.Need(input!=null&&input.Schema==1&&input.Head==Env("EXACT_HEAD_SHA")&&input.Run==Env("GITHUB_RUN_ID")&&input.Attempt==Env("GITHUB_RUN_ATTEMPT")&&input.Files.Count<=20000&&input.Files.Keys.Distinct(StringComparer.OrdinalIgnoreCase).Count()==input.Files.Count&&input.Files.Values.All(x=>x.Length>=0&&x.Length<=32*1024*1024&&Regex.IsMatch(x.Sha256,"^[0-9A-F]{64}$"))&&input.Files.Values.Sum(x=>x.Length)<=512*1024*1024,"PYTHON_MANIFEST_BINDING");
  using var token=Native.CaptureToken();string sid=Native.TokenFacts(token).User;using var canary=new OwnedFixture(Env("EXACT_HEAD_SHA"),Env("GITHUB_RUN_ID"),Env("GITHUB_RUN_ATTEMPT"),sid);string outside=System.IO.Path.Combine(canary.Path,"outside.fixture");Identity outsideId;string outsideSd;
  using(var created=FixtureNative.Create(canary.Root,"outside.fixture",false,new RawSecurityDescriptor("D:P(A;;FA;;;SY)(A;;FA;;;"+sid+")"))){FixtureNative.AppendFlush(created,System.Text.Encoding.UTF8.GetBytes("synthetic nonsecret canary"));outsideId=Native.Id(created);outsideSd=FixtureNative.Descriptor(created);}
  using var foreign=CreateFileW(outside,0x80020000,7,IntPtr.Zero,3,0x200000,IntPtr.Zero);ControllerPolicy.Need(!foreign.IsInvalid&&Native.Id(foreign)==outsideId&&FixtureNative.Descriptor(foreign)==outsideSd,"FOREIGN_CANARY_PIN");string outsideHash=Hash(FixtureNative.Read(foreign));
  ControllerPolicy.Need(DuplicateHandle(new IntPtr(-1),foreign,new IntPtr(-1),out var inheritable,0,true,2),"PYTHON_INHERIT_CANARY");using var inheritanceCanary=inheritable;
  var listener=new TcpListener(IPAddress.Loopback,0);listener.Start(4);try{
   var id=Native.Id(foreign);object config=new{head=input!.Head,run_id=input.Run,attempt=input.Attempt,canary=outside,inherited=inheritanceCanary.DangerousGetHandle().ToInt64(),expected_volume=id.Volume,expected_id=id.FileId,port=((IPEndPoint)listener.LocalEndpoint).Port};
   Environment.SetEnvironmentVariable("GRID_PARENT_SECRET",Guid.NewGuid().ToString("D"));PythonBundle? bundle=null;
   using var child=new OwnedChild(sid,(package,moniker)=>bundle=new PythonBundle(package,moniker,sid,input,inputHash,config));files=bundle!.FileCount;pid=checked((int)child.ProcessId);child.Guard();child.Resume();
   try{child.Wait(90000);}finally{if(child.Exited){byte[] result=bundle.Result();outputHash=Hash(result);using var document=JsonDocument.Parse(result);observed=document.RootElement.Clone();ControllerPolicy.Need(observed.Value.GetProperty("pid").GetInt32()==pid,"PYTHON_PROCESS_ID_MISMATCH");using var copy=new FileStream(System.IO.Path.Combine(Env("GITHUB_WORKSPACE"),"python-containment-evidence","child.json"),FileMode.CreateNew,FileAccess.Write,FileShare.Read);copy.Write(result);copy.Flush(true);}}
   ControllerPolicy.Need(!listener.Pending(),"PYTHON_NETWORK_REACHED_PARENT");canary.Guard(canary.Old);ControllerPolicy.Need(Native.Id(foreign)==outsideId&&FixtureNative.Descriptor(foreign)==outsideSd&&Hash(FixtureNative.Read(foreign))==outsideHash,"FOREIGN_CANARY_CHANGED");ControllerPolicy.Need(observed.HasValue&&observed.Value.GetProperty("status").GetString()=="PASS","PYTHON_RESULT_REFUSED");
  }finally{listener.Stop();}
 }catch(Exception e){error=e is Blocked b?b.Code:"PYTHON_NATIVE_FAILURE_"+e.GetType().Name;}
 Console.WriteLine(JsonSerializer.Serialize(new{schema=1,head=Env("EXACT_HEAD_SHA"),run_id=Env("GITHUB_RUN_ID"),attempt=Env("GITHUB_RUN_ATTEMPT"),status=error==null?"PASS":"BLOCKED",reason=error,input_manifest_sha256=inputHash,result_sha256=outputHash,files,pid,python=observed,assurance="HOSTED_PYTHON_NEGATIVE_BOUNDARY_ONLY",host_verified=false,execute_authorized=false,cleanup_authorized=false,physical="0/10 NOT_RUN",whole_system="PARTIAL",network_transport="BLOCKED_NO_CAPABILITIES"}));return error==null?0:1;
 }
}
