using System;
using System.Reflection;
using System.Collections.Generic;
using System.IO.Compression;
using System.IO;
using System.Text;
using System.Security.Cryptography;
using GridS0;
public static class InputTests {
 public static string Phase="FIXTURE_INPUTS_START";
 const string Head="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", Run="12345678-1234-4234-8234-123456789abc";
 const string Plan="{\"bybit_url\":\"wss://stream.bybit.com/v5/public/linear\",\"coordinator_ip\":\"100.64.0.1\",\"duration_seconds\":300,\"head\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"hostnames\":{\"LS5\":\"LS5\",\"PC4\":\"PC4\"},\"operator_sids\":{\"LS5\":\"S-1-5-21-1-2-3-1001\",\"PC4\":\"S-1-5-21-4-5-6-1002\"},\"port\":49152,\"profile\":\"PHYSICAL_SMOKE_S0\",\"run_id\":\"12345678-1234-4234-8234-123456789abc\",\"schema\":1,\"symbol\":\"BTCUSDT\",\"worker_ip\":\"100.64.0.2\"}";
 static string Hash(byte[] b) { using(var sha=SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(b)).Replace("-","").ToLowerInvariant(); }
 static object Decode(byte[] raw) { Type type=typeof(Bootstrap).GetNestedType("Json",BindingFlags.NonPublic); object json=Activator.CreateInstance(type,BindingFlags.NonPublic|BindingFlags.Instance,null,new object[]{raw},null); return type.GetMethod("Read",BindingFlags.NonPublic|BindingFlags.Instance).Invoke(json,null); }
 static void Validate(string value) { object plan=Decode(Encoding.ASCII.GetBytes(value)); typeof(Bootstrap).GetMethod("ValidateInputPlan",BindingFlags.NonPublic|BindingFlags.Static).Invoke(null,new object[]{plan,Head,Run}); }
 static void Reject(string value) { try { Validate(value); } catch(TargetInvocationException e) { if(e.InnerException is InvalidOperationException) return; throw; } throw new Exception("INPUT_NEGATIVE_ACCEPTED"); }
 static void Need(bool value) { if(!value) throw new InvalidOperationException("FIXTURE_INPUT_CHECK"); }
 static void Block(Action action) { try { action(); } catch(InvalidOperationException) { return; } throw new InvalidOperationException("FIXTURE_INPUT_EXPECTED_BLOCK"); }
 public static void Hosted(string sid,string head) {
  Need(Environment.GetEnvironmentVariable("GITHUB_ACTIONS")=="true" && Environment.GetEnvironmentVariable("RUNNER_ENVIRONMENT")=="github-hosted" && Environment.GetEnvironmentVariable("GITHUB_REPOSITORY")=="YehorBabenko88/bybit-cluster-grid" && Environment.GetEnvironmentVariable("GITHUB_JOB")=="s0-windows");
  Need(!String.Equals(Environment.MachineName,"LS5",StringComparison.OrdinalIgnoreCase) && !String.Equals(Environment.MachineName,"PC4",StringComparison.OrdinalIgnoreCase));
  TokenObserver.RequireStandard(sid);
  string run=Guid.NewGuid().ToString("D"); byte[] raw=Encoding.ASCII.GetBytes(Plan.Replace(Head,head).Replace(Run,run).Replace("S-1-5-21-1-2-3-1001",sid)); string sha=Hash(raw);
  string local=ProfileApi.Parent(), target=Path.Combine(local,"GridS0Input-"+Guid.NewGuid().ToString("D"));
  int count=Directory.GetDirectories(local,".GridS0Transaction-*").Length;
  Phase="FIXTURE_INPUT_PLAN"; BootstrapReceipt plan=ProfileApi.PlanInput(raw,sha,head,run,target,sid); Need(plan.Status=="PLAN_ONLY" && plan.FileCount==1 && plan.Bytes==raw.LongLength && plan.RootIdentity==null && !Directory.Exists(target));
  Need(Directory.GetDirectories(local,".GridS0Transaction-*").Length==count);
  Block(delegate { ProfileApi.StagePlanInput(raw,sha,head,run,target,sid,false); });
  Block(delegate { ProfileApi.StagePlanInput(raw,sha,head,run,target,"S-1-5-18",true); });
  Need(!Directory.Exists(target) && Directory.GetDirectories(local,".GridS0Transaction-*").Length==count);
  Phase="FIXTURE_INPUT_STAGE"; BootstrapReceipt staged=ProfileApi.StagePlanInput(raw,sha,head,run,target,sid,true);
  Phase="FIXTURE_INPUT_RECEIPT"; string input=Path.Combine(target,"s0-plan.json"); Need(staged.Status=="STAGED_NO_EXECUTION_AUTHORITY" && staged.RootIdentity!=null && staged.ParentIdentity==plan.ParentIdentity && staged.FileCount==1 && staged.Bytes==raw.LongLength && !staged.S0Execute && !staged.G1Execute && !staged.Cleanup);
  Phase="FIXTURE_INPUT_READBACK"; Need(Directory.GetFiles(target,"*",SearchOption.AllDirectories).Length==1 && Directory.GetDirectories(target).Length==0 && Hash(File.ReadAllBytes(input))==sha);
  Phase="FIXTURE_INPUT_REUSE"; Block(delegate { ProfileApi.StagePlanInput(raw,sha,head,run,target,sid,true); });
  Need(Hash(File.ReadAllBytes(input))==sha && Directory.GetFiles(target).Length==1);
  HostedRoleImport(sid,head,local);
  // Retain the owned hosted fixture; no cleanup and no physical execution.
 }
 static byte[] Canonical(object value) { return Encoding.ASCII.GetBytes((string)typeof(Bootstrap).GetMethod("InputJson",BindingFlags.NonPublic|BindingFlags.Static).Invoke(null,new object[]{value})); }
 static byte[] RoleArchive(Dictionary<string,byte[]> files) {
  using(var output=new MemoryStream()) { using(var archive=new ZipArchive(output,ZipArchiveMode.Create,true)) { foreach(var item in files) { var entry=archive.CreateEntry(item.Key); entry.ExternalAttributes=unchecked((int)0x81a40000u); using(var stream=entry.Open()) stream.Write(item.Value,0,item.Value.Length); } } return output.ToArray(); }
 }
 static void HostedRoleImport(string sid,string head,string local) {
  // Opaque synthetic bytes exercise the import contract only, never TLS validity.
  string run=Guid.NewGuid().ToString("D"), packageSha=new string('b',64);
  object plan=Decode(Encoding.ASCII.GetBytes(Plan.Replace(Head,head).Replace(Run,run).Replace("S-1-5-21-4-5-6-1002",sid)));
  var files=new Dictionary<string,byte[]>(StringComparer.Ordinal); var pins=new Dictionary<string,object>(StringComparer.Ordinal);
  foreach(string name in new[]{"ca.pem","tls-cert.pem","peer-cert.pem","tls-key.pem"}) { byte[] fake=Encoding.ASCII.GetBytes("SYNTHETIC HOSTED IMPORT FIXTURE, NOT TLS: "+name); files.Add(name,fake); pins.Add(name,Hash(fake)); }
  files.Add("config.json",Canonical(new Dictionary<string,object> {{"schema",1L},{"profile","PHYSICAL_SMOKE_S0"},{"plan",plan},{"role","PC4"},{"package_sha256",packageSha},{"files",pins}}));
  files.Add("stop.json",Canonical(new Dictionary<string,object> {{"head",head},{"run_id",run},{"role","PC4"},{"stop",false}}));
  byte[] zip=RoleArchive(files); string sha=Hash(zip), target=Path.Combine(local,"GridS0Input-"+Guid.NewGuid().ToString("D")); int count=Directory.GetDirectories(local,".GridS0Transaction-*").Length;
  Phase="FIXTURE_ROLE_IMPORT_PLAN"; BootstrapReceipt planned=ProfileApi.PlanRoleImport(zip,sha,head,run,packageSha,target,sid);
  Need(planned.Status=="PLAN_ONLY" && planned.FileCount==6 && planned.RootIdentity==null && !Directory.Exists(target) && Directory.GetDirectories(local,".GridS0Transaction-*").Length==count);
  Phase="FIXTURE_ROLE_IMPORT_NEGATIVES";
  Block(delegate { ProfileApi.StageRoleImport(zip,sha,head,run,packageSha,target,sid,false); });
  Block(delegate { ProfileApi.StageRoleImport(zip,sha,head,run,packageSha,target,"S-1-5-18",true); });
  Block(delegate { ProfileApi.StageRoleImport(zip,new string('0',64),head,run,packageSha,target,sid,true); });
  byte[] original=files["tls-key.pem"]; files["tls-key.pem"]=Encoding.ASCII.GetBytes("SYNTHETIC ALTERED KEY"); byte[] changed=RoleArchive(files); files["tls-key.pem"]=original;
  Block(delegate { ProfileApi.StageRoleImport(changed,Hash(changed),head,run,packageSha,target,sid,true); });
  Need(!Directory.Exists(target) && Directory.GetDirectories(local,".GridS0Transaction-*").Length==count);
  Phase="FIXTURE_ROLE_IMPORT_STAGE"; BootstrapReceipt staged=ProfileApi.StageRoleImport(zip,sha,head,run,packageSha,target,sid,true);
  Need(staged.Status=="STAGED_NO_EXECUTION_AUTHORITY" && staged.FileCount==6 && staged.Bytes==planned.Bytes && staged.ParentIdentity==planned.ParentIdentity && staged.RootIdentity!=null && !staged.S0Execute && !staged.G1Execute && !staged.Cleanup);
  Phase="FIXTURE_ROLE_IMPORT_READBACK"; string pc4=Path.Combine(target,"PC4"); Need(Directory.GetDirectories(target).Length==1 && Directory.Exists(pc4) && Directory.GetDirectories(pc4).Length==0 && Directory.GetFiles(target).Length==0);
  var expected=new HashSet<string>(StringComparer.Ordinal); long total=0;
  foreach(var item in files) { string path=Path.Combine(pc4,item.Key); expected.Add(path); Need(Hash(File.ReadAllBytes(path))==Hash(item.Value)); total+=item.Value.LongLength; }
  Need(expected.SetEquals(Directory.GetFiles(target,"*",SearchOption.AllDirectories)) && total==staged.Bytes);
  Phase="FIXTURE_ROLE_IMPORT_REUSE"; Block(delegate { ProfileApi.StageRoleImport(zip,sha,head,run,packageSha,target,sid,true); });
  foreach(var item in files) Need(Hash(File.ReadAllBytes(Path.Combine(pc4,item.Key)))==Hash(item.Value));
  if(ProfileApi.UserProfile) {
   Phase="FIXTURE_PROFILE_RECEIVER_IMPORT";string slotRoot=Path.Combine(local,"GridS0Input-"+Guid.NewGuid().ToString("D")),importRoot=Path.Combine(local,"GridS0Input-"+Guid.NewGuid().ToString("D"));
   var slot=Bootstrap.StageTransferSlotAtUserProfileV1(head,run,sha,zip.LongLength,slotRoot,sid,true);
   using(var lease=Bootstrap.OpenTransferSlotAtUserProfileV1(slotRoot,slot.Materialization.RootIdentity,slot.IncomingIdentity,head,run,sha,zip.LongLength,sid,true)) {
    using(var writer=new FileStream(Path.Combine(slotRoot,"incoming.zip"),FileMode.Open,FileAccess.Write,FileShare.ReadWrite)) { writer.Write(zip,0,zip.Length);writer.Flush(true); }
    Need(lease.Verify().PayloadSha256==sha);
    Block(delegate { Bootstrap.PlanTransferImport(lease,head,run,packageSha,importRoot,sid); });
    Need(Bootstrap.PlanTransferImportAtUserProfileV1(lease,head,run,packageSha,importRoot,sid).Status=="PLAN_ONLY");
    Block(delegate { Bootstrap.StageTransferImportAtUserProfileV1(lease,head,run,packageSha,importRoot,sid,false); });
    Need(Bootstrap.StageTransferImportAtUserProfileV1(lease,head,run,packageSha,importRoot,sid,true).RootIdentity!=null);
    Need(File.Exists(Path.Combine(importRoot,"PC4","config.json")));
    Block(delegate { Bootstrap.StageTransferImportAtUserProfileV1(lease,head,run,packageSha,importRoot,sid,true); });
   }
  }
 }
 public static void Pure() {
  Validate(Plan);
  foreach(string text in new[]{Plan.Replace("49152","55432"),Plan.Replace("300","299"),Plan.Replace("100.64.0.1","8.8.8.8"),Plan.Replace("100.64.0.1","100.064.0.1"),Plan.Replace("100.64.0.2","100.64.0.1"),Plan.Replace("\"schema\":1","\"schema\":true"),Plan.Replace("S-1-5-21-1-2-3-1001","S-1-5-21-4294967296-2-3-1001")}) Reject(text);
  byte[] bytes=Encoding.ASCII.GetBytes(Plan);
  // SID binding fails before token observation; this pure test never invokes Win32.
  try { ProfileApi.PlanInput(bytes,Hash(bytes),Head,Run,"invalid","S-1-5-18"); } catch(InvalidOperationException) { return; }
  throw new Exception("INPUT_SID_BINDING_ACCEPTED");
 }
}
