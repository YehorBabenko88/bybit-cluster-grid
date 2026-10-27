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
 static int Main(string[] args){bool debugged=args.SequenceEqual(new[]{"--hosted-python-tests"});string folder=debugged?"python-containment-evidence":"python-undebugged-evidence";string? error=null;JsonElement? observed=null;string? outputHash=null,inputHash=null,diagnosticHash=null,diagnosticError=null,resultError=null;string parentStage="initial";var networkHost=new List<object>();int files=0;int? pid=null;IReadOnlyList<LoaderFact> loaderEvents=Array.Empty<LoaderFact>();try{
  ControllerPolicy.Need((debugged||args.SequenceEqual(new[]{"--hosted-python-undebugged-tests"}))&&OperatingSystem.IsWindows()&&!new[]{"PC4","LS5"}.Contains(Environment.MachineName,StringComparer.OrdinalIgnoreCase)&&Env("GITHUB_ACTIONS")=="true"&&Env("RUNNER_ENVIRONMENT")=="github-hosted"&&Env("GITHUB_REPOSITORY")=="YehorBabenko88/bybit-cluster-grid"&&Env("GITHUB_JOB")=="python-containment","HOSTED_PYTHON_ONLY");
  ControllerPolicy.Need(Regex.IsMatch(Env("EXACT_HEAD_SHA"),"^[0-9a-f]{40}$")&&Regex.IsMatch(Env("GITHUB_RUN_ID"),"^[1-9][0-9]{0,19}$")&&Regex.IsMatch(Env("GITHUB_RUN_ATTEMPT"),"^[1-9][0-9]{0,9}$"),"PYTHON_CONTEXT");
  string manifest=System.IO.Path.Combine(Env("GITHUB_WORKSPACE"),"python-input","manifest.json");ControllerPolicy.Need(new FileInfo(manifest).Length is >0 and <10000000,"PYTHON_MANIFEST_SIZE");byte[] raw=File.ReadAllBytes(manifest);inputHash=Hash(raw);ControllerPolicy.Need(inputHash==Env("PYTHON_INPUT_SHA256"),"PYTHON_MANIFEST_PIN");var input=JsonSerializer.Deserialize<PythonInput>(raw)!;
  ControllerPolicy.Need(input!=null&&input.Schema==1&&input.Head==Env("EXACT_HEAD_SHA")&&input.Run==Env("GITHUB_RUN_ID")&&input.Attempt==Env("GITHUB_RUN_ATTEMPT")&&input.Files.Count<=20000&&input.Files.Keys.Distinct(StringComparer.OrdinalIgnoreCase).Count()==input.Files.Count&&input.Files.Values.All(x=>x.Length>=0&&x.Length<=32*1024*1024&&Regex.IsMatch(x.Sha256,"^[0-9A-F]{64}$"))&&input.Files.Values.Sum(x=>x.Length)<=512*1024*1024,"PYTHON_MANIFEST_BINDING");
  using var token=Native.CaptureToken();string sid=Native.TokenFacts(token).User;using var canary=new OwnedFixture(Env("EXACT_HEAD_SHA"),Env("GITHUB_RUN_ID"),Env("GITHUB_RUN_ATTEMPT"),sid);string outside=System.IO.Path.Combine(canary.Path,"outside.fixture");Identity outsideId;string outsideSd;
  using(var created=FixtureNative.Create(canary.Root,"outside.fixture",false,new RawSecurityDescriptor("D:P(A;;FA;;;SY)(A;;FA;;;"+sid+")"))){FixtureNative.AppendFlush(created,System.Text.Encoding.UTF8.GetBytes("synthetic nonsecret canary"));outsideId=Native.Id(created);outsideSd=FixtureNative.Descriptor(created);}
  using var foreign=CreateFileW(outside,0x80020000,7,IntPtr.Zero,3,0x200000,IntPtr.Zero);ControllerPolicy.Need(!foreign.IsInvalid&&Native.Id(foreign)==outsideId&&FixtureNative.Descriptor(foreign)==outsideSd,"FOREIGN_CANARY_PIN");string outsideHash=Hash(FixtureNative.Read(foreign));
  ControllerPolicy.Need(DuplicateHandle(new IntPtr(-1),foreign,new IntPtr(-1),out var inheritable,0,true,2),"PYTHON_INHERIT_CANARY");using var inheritanceCanary=inheritable;
  var listener=new TcpListener(IPAddress.Loopback,0);var listener6=new TcpListener(IPAddress.IPv6Loopback,0);listener6.Server.DualMode=false;bool started4=false,started6=false;try{
   foreach(var pair in new[]{(4,listener,IPAddress.Loopback),(6,listener6,IPAddress.IPv6Loopback)}){
    int family=pair.Item1;var target=pair.Item2;networkHost.Add(new{family,stage="socket",success=true});parentStage="family"+family+"_bind_listen";target.Start(4);if(family==4)started4=true;else started6=true;networkHost.Add(new{family,stage="bind",success=true});networkHost.Add(new{family,stage="listen",success=true});
    parentStage="family"+family+"_connect_accept";using var control=new TcpClient(family==4?AddressFamily.InterNetwork:AddressFamily.InterNetworkV6);using var connectDeadline=new CancellationTokenSource(TimeSpan.FromSeconds(3));control.ConnectAsync(pair.Item3,((IPEndPoint)target.LocalEndpoint).Port,connectDeadline.Token).GetAwaiter().GetResult();networkHost.Add(new{family,stage="connect",success=true});using var accepted=target.AcceptTcpClient();networkHost.Add(new{family,stage="accept",success=true});
   }
   var id=Native.Id(foreign);object config=new{parent_pid=Environment.ProcessId,head=input!.Head,run_id=input.Run,attempt=input.Attempt,canary=outside,inherited=inheritanceCanary.DangerousGetHandle().ToInt64(),expected_volume=id.Volume,expected_id=id.FileId,port6=((IPEndPoint)listener6.LocalEndpoint).Port,port=((IPEndPoint)listener.LocalEndpoint).Port};
   Environment.SetEnvironmentVariable("GRID_PARENT_SECRET",Guid.NewGuid().ToString("D"));PythonBundle? bundle=null;
   using var child=new OwnedChild(sid,(package,moniker)=>bundle=new PythonBundle(package,moniker,sid,input,inputHash,config,debugged));files=bundle!.FileCount;pid=checked((int)child.ProcessId);child.Guard();child.Resume();
   void Copy(string name,byte[] bytes){using var copy=new FileStream(System.IO.Path.Combine(Env("GITHUB_WORKSPACE"),folder,name),FileMode.CreateNew,FileAccess.Write,FileShare.Read);copy.Write(bytes);copy.Flush(true);}
   void CaptureResult(){byte[] result=bundle.Result();outputHash=Hash(result);using var document=JsonDocument.Parse(result);observed=document.RootElement.Clone();ControllerPolicy.Need(observed.Value.GetProperty("pid").GetInt32()==pid,"PYTHON_PROCESS_ID_MISMATCH");Copy("child.json",result);}
   void CaptureDiagnostics(){byte[] bytes=bundle.Diagnostics();diagnosticHash=Hash(bytes);Copy("diagnostics.txt",bytes);}
   try{child.Wait(90000);}catch{loaderEvents=child.LoaderEvents;if(child.Exited){try{CaptureDiagnostics();}catch(Exception secondary){diagnosticError=secondary is Blocked db?db.Code:secondary.GetType().Name;}try{CaptureResult();}catch(Exception secondary){resultError=secondary is Blocked rb?rb.Code:secondary.GetType().Name;}}throw;}
   loaderEvents=child.LoaderEvents;CaptureDiagnostics();CaptureResult();
   ControllerPolicy.Need(!listener.Pending()&&!listener6.Pending(),"PYTHON_NETWORK_REACHED_PARENT");canary.Guard(canary.Old);ControllerPolicy.Need(Native.Id(foreign)==outsideId&&FixtureNative.Descriptor(foreign)==outsideSd&&Hash(FixtureNative.Read(foreign))==outsideHash,"FOREIGN_CANARY_CHANGED");ControllerPolicy.Need(observed.HasValue&&observed.Value.GetProperty("status").GetString()=="PASS","PYTHON_RESULT_REFUSED");
  }finally{
   foreach(var pair in new[]{(4,listener,started4),(6,listener6,started6)}){try{networkHost.Add(new{family=pair.Item1,stage="no-pending-after-child",success=pair.Item3&&!pair.Item2.Pending()});}catch{error??="PARENT_PENDING_UNKNOWN";}finally{try{pair.Item2.Stop();}catch{error??="PARENT_LISTENER_CLOSE_UNKNOWN";}}}
  }
 }catch(Exception e){error=e is Blocked b?b.Code:e is OperationCanceledException?"PARENT_"+parentStage+"_CONNECT_DEADLINE":e is SocketException se?"PARENT_"+parentStage+"_SOCKET_"+se.NativeErrorCode:"PYTHON_NATIVE_FAILURE_"+e.GetType().Name;}
 Console.WriteLine(JsonSerializer.Serialize(new{schema=1,head=Env("EXACT_HEAD_SHA"),run_id=Env("GITHUB_RUN_ID"),attempt=Env("GITHUB_RUN_ATTEMPT"),status=error==null?"PASS":"BLOCKED",reason=error,input_manifest_sha256=inputHash,result_sha256=outputHash,diagnostic_sha256=diagnosticHash,diagnostic_error=diagnosticError,result_error=resultError,files,pid,debugged,network_host=networkHost,loader_events=loaderEvents,python=observed,assurance=debugged?"HOSTED_DEBUGGED_PYTHON_NEGATIVE_BOUNDARY_ONLY":"HOSTED_UNDEBUGGED_PYTHON_DIAGNOSTIC_ONLY",host_verified=false,execute_authorized=false,cleanup_authorized=false,physical="0/10 NOT_RUN",whole_system="PARTIAL",network_transport="BLOCKED_NO_CAPABILITIES"}));return error==null?0:1;
 }
}
