using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

// A separate stock-CPython experiment. Never an alternate Grid acceptance path.
internal static class TransportMain {
 static string Env(string key)=>Environment.GetEnvironmentVariable(key)??"";
 static string Hash(byte[] raw)=>Convert.ToHexString(SHA256.HashData(raw));
 static void Need(bool ok,string code)=>ControllerPolicy.Need(ok,code);
 static object Address(EndPoint? endpoint)=>endpoint is IPEndPoint p?new{host=p.Address.ToString(),port=p.Port}:(object)new{unknown=true};
 static void Copy(string folder,string name,byte[] raw){using var f=new FileStream(System.IO.Path.Combine(Env("GITHUB_WORKSPACE"),folder,name),FileMode.CreateNew,FileAccess.Write,FileShare.Read);f.Write(raw);f.Flush(true);}
 static object Control(string phase,string family,TcpListener listener,Socket bound,bool listening){
  var clock=Stopwatch.StartNew();long started=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();string result="UNKNOWN";int? error=null;
  using var cancellation=new CancellationTokenSource(TimeSpan.FromSeconds(3));
  using var client=new TcpClient(family=="IPv4"?AddressFamily.InterNetwork:AddressFamily.InterNetworkV6);
  try{
   if(listening){
    Task<TcpClient> accepting=listener.AcceptTcpClientAsync(cancellation.Token).AsTask();
    try{client.ConnectAsync(((IPEndPoint)listener.LocalEndpoint).Address,((IPEndPoint)listener.LocalEndpoint).Port,cancellation.Token).GetAwaiter().GetResult();using var peer=accepting.GetAwaiter().GetResult();Need(peer.Client.RemoteEndPoint!.Equals(client.Client.LocalEndPoint)&&peer.Client.LocalEndPoint!.Equals(client.Client.RemoteEndPoint),"CONTROL_PEER");result="SUCCESS";}
    finally{cancellation.Cancel();try{using var unexpected=accepting.WaitAsync(TimeSpan.FromSeconds(3)).GetAwaiter().GetResult();}catch(OperationCanceledException){}}
   }else{client.ConnectAsync(((IPEndPoint)bound.LocalEndPoint!).Address,((IPEndPoint)bound.LocalEndPoint!).Port,cancellation.Token).GetAwaiter().GetResult();result="UNEXPECTED_CONNECTION";}
  }catch(SocketException e){error=e.NativeErrorCode;result="SOCKET_ERROR";}catch(OperationCanceledException){result="DEADLINE";}
  return new{phase,family,mode=listening?"listener":"bound-not-listening",target=Address(listening?listener.LocalEndpoint:bound.LocalEndPoint),result,winerror=error,started_utc_ms=started,elapsed_ms=clock.ElapsedMilliseconds};
 }
 internal static (PythonInput Input,string ManifestHash) ReadInput(string directory,string pinName){
  Need((directory,pinName) is ("transport-input","TRANSPORT_INPUT_SHA256") or ("pipe-input","PIPE_INPUT_SHA256"),"TRANSPORT_INPUT_PROFILE");
   string host=Environment.MachineName.Replace("-","").Replace("_","");
   Need(OperatingSystem.IsWindows()&&Environment.Is64BitProcess&&!host.Contains("LS5",StringComparison.OrdinalIgnoreCase)&&!host.Contains("PC4",StringComparison.OrdinalIgnoreCase)&&Env("GITHUB_ACTIONS")=="true"&&Env("RUNNER_ENVIRONMENT")=="github-hosted"&&Env("GITHUB_REPOSITORY")=="YehorBabenko88/bybit-cluster-grid"&&Env("GITHUB_JOB")=="python-containment","HOSTED_TRANSPORT_ONLY");
   Need(Regex.IsMatch(Env("EXACT_HEAD_SHA"),"^[0-9a-f]{40}$")&&Regex.IsMatch(Env("GITHUB_RUN_ID"),"^[1-9][0-9]{0,19}$")&&Regex.IsMatch(Env("GITHUB_RUN_ATTEMPT"),"^[1-9][0-9]{0,9}$"),"TRANSPORT_CONTEXT");
   Need(TransportFacts.ModelTests(),"TCP_DECODER_MODELS");
   string manifest=System.IO.Path.Combine(Env("GITHUB_WORKSPACE"),directory,"manifest.json");Need(new FileInfo(manifest).Length is >0 and <10000000,"TRANSPORT_MANIFEST_SIZE");byte[] raw=File.ReadAllBytes(manifest);string inputHash=Hash(raw).ToLowerInvariant();Need(inputHash==Env(pinName),"TRANSPORT_MANIFEST_PIN");var input=JsonSerializer.Deserialize<PythonInput>(raw)!;
   Need(input!=null&&input.Schema==1&&input.Head==Env("EXACT_HEAD_SHA")&&input.Run==Env("GITHUB_RUN_ID")&&input.Attempt==Env("GITHUB_RUN_ATTEMPT")&&input.Files.Count is >10 and <=20000&&input.Files.Keys.Distinct(StringComparer.OrdinalIgnoreCase).Count()==input.Files.Count&&input.Origins.Keys.ToHashSet().SetEquals(input.Files.Keys),"TRANSPORT_INPUT_BINDING");
   foreach(var (name,pin) in input!.Files){Need(pin.Length>=0&&pin.Length<=32*1024*1024&&Regex.IsMatch(pin.Sha256,"^[0-9A-F]{64}$"),"TRANSPORT_FILE_PIN");Need(name is "driver.py" or "stdlib.zip" or "python.exe" or "pythonw.exe" or "python._pth" or "pythonw._pth"||Regex.IsMatch(name,@"^python3[0-9]+\._pth$")||Regex.IsMatch(name,@"^[A-Za-z0-9_. ()-]+\.dll$")||Regex.IsMatch(name,@"^DLLs/[A-Za-z0-9_. ()-]+\.(dll|pyd)$"),"NONSTOCK_INPUT");}
   Need(input.Files.Values.Sum(x=>x.Length)<=512*1024*1024,"TRANSPORT_INPUT_TOTAL");
  return (input!,inputHash);
 }
 internal static int Run(bool debugged){
  string folder=debugged?"transport-debugged-evidence":"transport-undebugged-evidence";string? error=null;object? identity=null,parent=null,configuration=null;JsonElement? observed=null;string? inputHash=null,resultHash=null;var controls=new List<object>();var endpoints=new List<object>();var accepts=new List<object>();var snapshots=new List<object>();IReadOnlyList<LoaderFact> loader=Array.Empty<LoaderFact>();bool samplerJoined=false;int? exitCode=null;
  try{
   var measured=ReadInput("transport-input","TRANSPORT_INPUT_SHA256");var input=measured.Input;inputHash=measured.ManifestHash;
   using var original=Native.CaptureToken();var originalFacts=Native.TokenFacts(original);using var ownProcess=Process.GetCurrentProcess();parent=new{pid=Environment.ProcessId,creation_time=ownProcess.StartTime.ToFileTimeUtc(),token=originalFacts};
   using var closed4=new Socket(AddressFamily.InterNetwork,SocketType.Stream,ProtocolType.Tcp);using var closed6=new Socket(AddressFamily.InterNetworkV6,SocketType.Stream,ProtocolType.Tcp);closed4.ExclusiveAddressUse=true;closed6.ExclusiveAddressUse=true;closed6.DualMode=false;closed4.Bind(new IPEndPoint(IPAddress.Loopback,0));closed6.Bind(new IPEndPoint(IPAddress.IPv6Loopback,0));
   var listener4=new TcpListener(IPAddress.Loopback,0);var listener6=new TcpListener(IPAddress.IPv6Loopback,0);listener4.ExclusiveAddressUse=true;listener6.ExclusiveAddressUse=true;listener6.Server.DualMode=false;
   var pairs=new[]{("IPv4",listener4,closed4),("IPv6",listener6,closed6)};
   try{
    listener4.Start(4);listener6.Start(4);
    foreach(var (family,listener,bound) in pairs){
     foreach(bool listening in new[]{true,false}){
      var endpoint=(IPEndPoint)(listening?listener.LocalEndpoint:bound.LocalEndPoint!);endpoints.Add(new{family,host=endpoint.Address.ToString(),port=endpoint.Port,mode=listening?"listener":"bound-not-listening",backlog=listening?4:0,exclusive=true,dual_mode=false,ready_utc_ms=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),ready_monotonic=Stopwatch.GetTimestamp()});controls.Add(Control("before",family,listener,bound,listening));
     }
    }
    string nonce=Guid.NewGuid().ToString("N");object[][] targets=pairs.SelectMany(x=>new[]{new object[]{x.Item1,((IPEndPoint)x.Item2.LocalEndpoint).Address.ToString(),((IPEndPoint)x.Item2.LocalEndpoint).Port,"listener"},new object[]{x.Item1,((IPEndPoint)x.Item3.LocalEndPoint!).Address.ToString(),((IPEndPoint)x.Item3.LocalEndPoint!).Port,"bound-not-listening"}}).ToArray();
    object config=new{schema=1,head=input.Head,run_id=input.Run,attempt=input.Attempt,nonce,parent_pid=Environment.ProcessId,endpoints=targets};configuration=config;PythonBundle? bundle=null;string package="";
    using var child=new OwnedChild(originalFacts.User,(sid,moniker)=>{package=sid;return bundle=new PythonBundle(sid,moniker,originalFacts.User,input,inputHash,config,debugged,"transport-input");});
    identity=child.SecuritySnapshot(originalFacts.User,package);
    using var acceptingCancellation=new CancellationTokenSource();var accepting=new List<(string Family,Task<TcpClient> Task)>();
    using var samplingCancellation=new CancellationTokenSource();string? sampleError=null;
    uint parentPid=checked((uint)Environment.ProcessId),childPid=child.ProcessId;
    // Background sampling owns no process/image/file handles. PID correlation is
    // not identity attestation; held process identity is checked around sampling.
    void Sample(string phase){object tables=TransportFacts.Snapshot(parentPid,childPid);lock(snapshots){Need(snapshots.Count<60,"TCP_SAMPLE_BOUND");snapshots.Add(new{phase,utc_ms=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),monotonic=Stopwatch.GetTimestamp(),identity_binding="PIDS_FROM_HELD_PRE_RESUME_CHECK_NOT_PER_SAMPLE_ATTESTATION",tables});}}
    Task sampling=Task.CompletedTask;
    try{
     foreach(var item in pairs)accepting.Add((item.Item1,item.Item2.AcceptTcpClientAsync(acceptingCancellation.Token).AsTask()));
     Sample("suspended");
     sampling=Task.Run(async()=>{try{while(true){await Task.Delay(1000,samplingCancellation.Token);Sample("running");}}catch(OperationCanceledException){}catch(Exception e){sampleError=e is Blocked b?b.Code:e.GetType().Name;}});
     child.Guard();
     child.Resume();
     try{child.Wait(90000);exitCode=0;}catch(Exception e){error=e is Blocked b?b.Code:e.GetType().Name;}
    }finally{
     samplingCancellation.Cancel();try{sampling.WaitAsync(TimeSpan.FromSeconds(3)).GetAwaiter().GetResult();samplerJoined=true;}catch{error??="TCP_SAMPLER_JOIN_UNKNOWN";}
     if(sampleError!=null)error??="TCP_SAMPLER_"+sampleError;
     acceptingCancellation.Cancel();
     foreach(var item in accepting){
      try{using var accepted=item.Task.WaitAsync(TimeSpan.FromSeconds(3)).GetAwaiter().GetResult();accepts.Add(new{family=item.Family,status="ACCEPTED_NOT_AUTHENTICATED",local=Address(accepted.Client.LocalEndPoint),remote=Address(accepted.Client.RemoteEndPoint)});error??="UNEXPECTED_HOST_ACCEPT";}
      catch(OperationCanceledException){accepts.Add(new{family=item.Family,status="CANCELLED_NO_ACCEPT"});}
      catch(Exception e){accepts.Add(new{family=item.Family,status="UNKNOWN",reason=e.GetType().Name});error??="ACCEPT_JOIN_UNKNOWN";}
     }
    }
    loader=child.LoaderEvents;
    if(child.Exited){
     child.Guard();
     try{byte[] result=bundle!.Result();resultHash=Hash(result).ToLowerInvariant();observed=JsonDocument.Parse(result).RootElement.Clone();Need(observed.Value.GetProperty("pid").GetInt32()==child.ProcessId,"RESULT_PID");Copy(folder,"child.json",result);}catch(Exception e){error??="RESULT_"+(e is Blocked b?b.Code:e.GetType().Name);}
     try{Copy(folder,"diagnostics.txt",bundle!.Diagnostics());}catch(Exception e){error??="STDERR_"+e.GetType().Name;}
     Sample("exited");
    }else error??="OWNED_CHILD_STILL_RUNNING";
    foreach(var (family,listener,bound) in pairs)foreach(bool listening in new[]{true,false})controls.Add(Control("after",family,listener,bound,listening));
   }finally{listener4.Stop();listener6.Stop();}
  }catch(Exception e){error??=e is Blocked b?b.Code:"TRANSPORT_PARENT_"+e.GetType().Name;}
  // A diagnostic result and exit0 from the child are not network policy proof.
  object[] samples;lock(snapshots)samples=snapshots.ToArray();
  Console.WriteLine(JsonSerializer.Serialize(new{schema=1,head=Env("EXACT_HEAD_SHA"),run_id=Env("GITHUB_RUN_ID"),attempt=Env("GITHUB_RUN_ATTEMPT"),profile="GRID_FREE_DIAGNOSTIC_ONLY",debugged,status="BLOCKED",reason=error??"POLICY_CAUSE_UNKNOWN",parent,config=configuration,child_identity=identity,input_manifest_sha256=inputHash,result_sha256=resultHash,endpoints,host_controls=controls,accepts,tcp_snapshots=samples,sampler_joined=samplerJoined,child_exit_code=exitCode,loader_events=loader,child=observed,host_verified=false,execute_authorized=false,cleanup_authorized=false,physical="0/10 NOT_RUN",whole_system="PARTIAL",fixture_teardown="HELD_HANDLES_CLOSED_DISPOSABLE_VM_TEARDOWN_REQUIRED"}));return 1;
 }
}
