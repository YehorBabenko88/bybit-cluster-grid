using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
internal static class ControllerMain {
 internal static readonly string[] ModelCases={"signed-permit","tampered-data","tampered-signature","wrong-key","wrong-head","wrong-run","wrong-nonce","expired","replay","noncanonical-permit","truncated-journal","unknown-recovery-anchor","invalid-transitions","child-environment-allowlist","child-environment-missing","child-token-user","child-token-enabled-admin","child-token-deny-only-admin","child-token-elevated","child-token-high-integrity","live-image-query-failure","exited-image-without-preverification","exited-preverified-held-image","queried-image-mismatch"};
 internal static readonly string[] NativeCases={"held-process-identity-job-token","live-cleanup-refused","unknown-cleanup-refused","cooperative-exit","stable-guardian-recovery","bounded-marker-cleanup","forced-owned-process-stop","job-close-kills-owned-suspended-child","flush-failure-retention"};
 static string? executedImageHash;static readonly List<object> cases=new();static void Test(string name,Action a){a();cases.Add(new{name,outcome="PASS"});}
 static void Refuse(Action a){try{a();}catch(Blocked){return;}throw new Blocked("EXPECTED_REFUSAL_MISSING");}
 static string Env(string n)=>Environment.GetEnvironmentVariable(n)??"";
 static Permit Sample()=>new(1,new string('a',40),"1","1",Guid.NewGuid().ToString("D"),DateTimeOffset.UtcNow.ToUnixTimeSeconds()+120,new(1,new string('1',32),1,16),new(1,new string('2',32),1,32),new(1,new string('3',32),1,32),new string('A',64));
 static void Models(){using var key=RSA.Create(2048);byte[] pub=key.ExportSubjectPublicKeyInfo(),pin=SHA256.HashData(pub);var p=Sample();long now=DateTimeOffset.UtcNow.ToUnixTimeSeconds();var signed=ControllerPolicy.Sign(p,key);byte[] wire=ControllerPolicy.Canon(signed);void Verify(byte[] w,Permit expected,HashSet<string>? used=null)=>ControllerPolicy.Verify(w,pub,pin,expected,used??new(),now);
 Test("signed-permit",()=>Verify(wire,p));
 Test("tampered-data",()=>Refuse(()=>Verify(ControllerPolicy.Canon(signed with{Payload=Convert.ToBase64String(ControllerPolicy.Canon(p with{Run="2"}))}),p)));
 Test("tampered-signature",()=>{var b=Convert.FromBase64String(signed.Signature);b[0]^=1;Refuse(()=>Verify(ControllerPolicy.Canon(signed with{Signature=Convert.ToBase64String(b)}),p));});
 Test("wrong-key",()=>{using var other=RSA.Create(2048);Refuse(()=>ControllerPolicy.Verify(wire,other.ExportSubjectPublicKeyInfo(),pin,p,new(),now));});
 Test("wrong-head",()=>Refuse(()=>Verify(wire,p with{Head=new string('b',40)})));Test("wrong-run",()=>Refuse(()=>Verify(wire,p with{Run="2"})));Test("wrong-nonce",()=>Refuse(()=>Verify(wire,p with{Nonce=Guid.NewGuid().ToString("D")})));
 Test("expired",()=>{var q=p with{Expires=now-1};Refuse(()=>Verify(ControllerPolicy.Canon(ControllerPolicy.Sign(q,key)),q));});Test("replay",()=>{var used=new HashSet<string>();Verify(wire,p,used);Refuse(()=>Verify(wire,p,used));});Test("noncanonical-permit",()=>Refuse(()=>Verify(Encoding.UTF8.GetBytes(" "+Encoding.UTF8.GetString(wire)),p)));
 Test("truncated-journal",()=>Refuse(()=>Guardian.Validate(Encoding.UTF8.GetBytes("{"),new string('A',64))));Test("unknown-recovery-anchor",()=>Refuse(()=>Guardian.Validate(new byte[]{10},"unknown")));Test("invalid-transitions",()=>ControllerPolicy.Need(!ControllerPolicy.Transition(null,"CLEANED")&&!ControllerPolicy.Transition("PREPARED","EXITED")&&!ControllerPolicy.Transition("EXITED","RESUME_INTENT")));
 Test("child-environment-allowlist",()=>ControllerPolicy.Need(ControllerPolicy.ChildEnvironment(@"C:\Windows",@"C:\Users\fixture\AppData\Local")=="LOCALAPPDATA=C:\\Users\\fixture\\AppData\\Local\0SystemRoot=C:\\Windows\0WINDIR=C:\\Windows\0\0"));
 Test("child-environment-missing",()=>Refuse(()=>ControllerPolicy.ChildEnvironment(@"C:\Windows","")));
 var ordinary=new TokenFact("S-1-5-21-1-2-3-1001",false,4096,new(),"");
 Test("child-token-user",()=>Refuse(()=>ControllerPolicy.ChildToken(ordinary,"S-1-5-21-1-2-3-1002")));
 Test("child-token-enabled-admin",()=>Refuse(()=>ControllerPolicy.ChildToken(ordinary with{Groups=new(){new("S-1-5-32-544",4)}},ordinary.User)));
 Test("child-token-deny-only-admin",()=>ControllerPolicy.ChildToken(ordinary with{Groups=new(){new("S-1-5-32-544",16)}},ordinary.User));
 Test("child-token-elevated",()=>Refuse(()=>ControllerPolicy.ChildToken(ordinary with{Elevated=true},ordinary.User)));
 Test("child-token-high-integrity",()=>Refuse(()=>ControllerPolicy.ChildToken(ordinary with{Integrity=8192},ordinary.User)));

 Test("live-image-query-failure",()=>Refuse(()=>ControllerPolicy.ImageObservation(false,false,false,true)));
 Test("exited-image-without-preverification",()=>Refuse(()=>ControllerPolicy.ImageObservation(false,false,true,false)));
 Test("exited-preverified-held-image",()=>ControllerPolicy.ImageObservation(false,false,true,true));
 Test("queried-image-mismatch",()=>Refuse(()=>ControllerPolicy.ImageObservation(true,false,true,true)));

 }
 static void Hosted(){ControllerPolicy.Need(OperatingSystem.IsWindows()&&Env("GITHUB_ACTIONS")=="true"&&Env("RUNNER_ENVIRONMENT")=="github-hosted"&&Env("GITHUB_REPOSITORY")=="YehorBabenko88/bybit-cluster-grid"&&Env("GITHUB_JOB")=="controller-fixture"&&Regex.IsMatch(Env("EXACT_HEAD_SHA"),"^[0-9a-f]{40}$")&&Regex.IsMatch(Env("GITHUB_RUN_ID"),"^[1-9][0-9]{0,19}$")&&Regex.IsMatch(Env("GITHUB_RUN_ATTEMPT"),"^[1-9][0-9]{0,9}$"),"HOSTED_CONTEXT_REQUIRED");
 using var token=Native.CaptureToken();string sid=Native.TokenFacts(token).User;string path=Path.Combine(Env("GITHUB_WORKSPACE"),"installer","native-g1-controller-fixture","bin","native-child.exe");using var input=File.OpenHandle(path,FileMode.Open,FileAccess.Read,FileShare.Read);Policy.Object(Native.Id(input),false);byte[] payload=FixtureNative.Read(input);ControllerPolicy.Need(payload.Length>1&&payload.Length<65536&&payload[0]==77&&payload[1]==90,"COMPILED_FIXTURE_REQUIRED");string imageHash=Convert.ToHexString(SHA256.HashData(payload));executedImageHash=imageHash.ToLowerInvariant();
 OwnedFixture New()=>new(Env("EXACT_HEAD_SHA"),Env("GITHUB_RUN_ID"),Env("GITHUB_RUN_ATTEMPT"),sid);
 Guardian Prepare(OwnedFixture f){var p=new Permit(1,Env("EXACT_HEAD_SHA"),Env("GITHUB_RUN_ID"),Env("GITHUB_RUN_ATTEMPT"),Guid.NewGuid().ToString("D"),DateTimeOffset.UtcNow.ToUnixTimeSeconds()+120,Native.Id(f.Root),Native.Id(f.Target),Native.Id(f.Journal),imageHash);using var key=RSA.Create(2048);byte[] publicKey=key.ExportSubjectPublicKeyInfo();byte[] independentlyPinned=SHA256.HashData(publicKey);ControllerPolicy.Verify(ControllerPolicy.Canon(ControllerPolicy.Sign(p,key)),publicKey,independentlyPinned,p,new(),DateTimeOffset.UtcNow.ToUnixTimeSeconds());var g=new Guardian(f,p);g.Append("PREPARED");return g;}
 using(var f=New()){var g=Prepare(f);using var child=new OwnedChild(payload,imageHash,sid);Test("held-process-identity-job-token",child.Guard);Test("live-cleanup-refused",()=>Refuse(()=>OwnedChild.Cleanup(f,child,g)));Test("unknown-cleanup-refused",()=>Refuse(()=>OwnedChild.Cleanup(f,null,g)));g.Append("RESUME_INTENT");child.Resume();Test("cooperative-exit",child.Wait);g.Append("EXITED");Test("stable-guardian-recovery",g.Recover);Test("bounded-marker-cleanup",()=>OwnedChild.Cleanup(f,child,g));}
 using(var f=New()){var g=Prepare(f);using var child=new OwnedChild(payload,imageHash,sid);g.Append("RESUME_INTENT");Test("forced-owned-process-stop",child.Stop);g.Append("EXITED");}
 using(var f=New()){var g=Prepare(f);using var child=new OwnedChild(payload,imageHash,sid);g.Append("RESUME_INTENT");Test("job-close-kills-owned-suspended-child",child.CloseJobStop);g.Append("EXITED");}
 Test("flush-failure-retention",()=>{using var f=New();var g=Prepare(f);string anchor=g.Anchor;Refuse(()=>g.Append("RESUME_INTENT",true));ControllerPolicy.Need(g.Anchor==anchor&&g.Phase=="PREPARED");g.Guard();ControllerPolicy.Need(FixtureNative.Read(f.Journal).Length>0);});
 }
 static int Main(string[] args){string kind=args.Length==1?args[0]:"";string? error=null;try{ControllerPolicy.Need(kind is "--model-tests" or "--hosted-fixture-tests","PHYSICAL_EXECUTE_CLEANUP_REFUSED");if(kind=="--model-tests")Models();else Hosted();ControllerPolicy.Need(cases.Count==(kind=="--model-tests"?ModelCases.Length:NativeCases.Length),"MISSING_CASE");}catch(Exception e){error=e is Blocked b?b.Code:"CONTROLLER_FAILURE";if(e.Data.Contains("fixture_diagnostic"))Console.Error.WriteLine(JsonSerializer.Serialize(e.Data["fixture_diagnostic"]));}Console.WriteLine(JsonSerializer.Serialize(new{schema=1,kind=kind=="--model-tests"?"MODEL_TESTS":"HOSTED_FIXTURE_TESTS",status=error==null?"PASS":"BLOCKED",reason=error,cases,tested_image_sha256=executedImageHash,head=Env("EXACT_HEAD_SHA"),repository=Env("GITHUB_REPOSITORY"),run_id=Env("GITHUB_RUN_ID"),attempt=Env("GITHUB_RUN_ATTEMPT"),host_verified=false,execute_authorized=false,cleanup_authorized=false,physical="0/10 NOT_RUN",g1="BLOCKED"}));return error==null?0:1;}
}

