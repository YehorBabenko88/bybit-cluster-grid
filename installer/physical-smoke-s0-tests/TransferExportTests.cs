// Hosted opaque fixtures only: these bytes cannot establish TLS or SSH acceptance.
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using GridS0;
public static class TransferExportTests {
 public static string Phase="FIXTURE_EXPORT_START";
 static void Need(bool b) { if(!b) throw new InvalidOperationException("FIXTURE_EXPORT_CHECK"); }
 static void Block(Action a) { try { a(); } catch(InvalidOperationException) { return; } throw new InvalidOperationException("FIXTURE_EXPORT_EXPECTED_BLOCK"); }
 static string Hash(byte[] b) { using(var h=SHA256.Create()) return BitConverter.ToString(h.ComputeHash(b)).Replace("-","").ToLowerInvariant(); }
 static string Sddl(string sid) { return "O:"+sid+"D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;"+sid+")"; }
 static void NewDirectory(string path,string sid) { Need(!Directory.Exists(path) && !File.Exists(path)); var acl=new DirectorySecurity(); acl.SetSecurityDescriptorSddlForm(Sddl(sid)); Directory.CreateDirectory(path,acl); }
 static void NewFile(string path,byte[] bytes,string sid) { var acl=new FileSecurity(); acl.SetSecurityDescriptorSddlForm(Sddl(sid)); using(var f=new FileStream(path,FileMode.CreateNew,FileSystemRights.FullControl,FileShare.None,8192,FileOptions.None,acl)) { f.Write(bytes,0,bytes.Length); f.Flush(true); } }
 static object Decode(byte[] raw) { Type t=typeof(Bootstrap).GetNestedType("Json",BindingFlags.NonPublic); object p=Activator.CreateInstance(t,BindingFlags.NonPublic|BindingFlags.Instance,null,new object[]{raw},null); return t.GetMethod("Read",BindingFlags.NonPublic|BindingFlags.Instance).Invoke(p,null); }
 static byte[] Canonical(object value) { return Encoding.ASCII.GetBytes((string)typeof(Bootstrap).GetMethod("InputJson",BindingFlags.NonPublic|BindingFlags.Static).Invoke(null,new object[]{value})); }
 static string Target(string local) { return Path.Combine(local,"GridS0Input-"+Guid.NewGuid().ToString("D")); }
 public static void Hosted(string sid,string head) {
  Need(Environment.GetEnvironmentVariable("GITHUB_ACTIONS")=="true" && Environment.GetEnvironmentVariable("RUNNER_ENVIRONMENT")=="github-hosted" && Environment.GetEnvironmentVariable("GITHUB_REPOSITORY")=="YehorBabenko88/bybit-cluster-grid" && Environment.GetEnvironmentVariable("GITHUB_JOB")=="s0-windows");
  Need(!String.Equals(Environment.MachineName,"LS5",StringComparison.OrdinalIgnoreCase) && !String.Equals(Environment.MachineName,"PC4",StringComparison.OrdinalIgnoreCase)); TokenObserver.RequireStandard(sid);
  string local=ProfileApi.Parent(), run=Guid.NewGuid().ToString("D"), pair=Path.Combine(local,"GridS0-"+run), role=Path.Combine(pair,"PC4"), packageSha=new string('b',64);
  NewDirectory(pair,sid); NewDirectory(role,sid); NewDirectory(Path.Combine(role,"temp"),sid);
  object plan=Decode(Encoding.ASCII.GetBytes("{\"bybit_url\":\"wss://stream.bybit.com/v5/public/linear\",\"coordinator_ip\":\"100.64.0.1\",\"duration_seconds\":300,\"head\":\""+head+"\",\"hostnames\":{\"LS5\":\"LS5\",\"PC4\":\"PC4\"},\"operator_sids\":{\"LS5\":\""+sid+"\",\"PC4\":\"S-1-5-21-4-5-6-1002\"},\"port\":49152,\"profile\":\"PHYSICAL_SMOKE_S0\",\"run_id\":\""+run+"\",\"schema\":1,\"symbol\":\"BTCUSDT\",\"worker_ip\":\"100.64.0.2\"}"));
  var files=new Dictionary<string,byte[]>(StringComparer.Ordinal); var pins=new Dictionary<string,object>(StringComparer.Ordinal);
  foreach(string name in new[]{"ca.pem","tls-cert.pem","peer-cert.pem","tls-key.pem"}) { byte[] bytes=Encoding.ASCII.GetBytes("OPAQUE HOSTED EXPORT FIXTURE, NOT TLS: "+name); files.Add(name,bytes); pins.Add(name,Hash(bytes)); }
  var config=new Dictionary<string,object> {{"schema",1L},{"profile","PHYSICAL_SMOKE_S0"},{"plan",plan},{"role","PC4"},{"package_sha256",packageSha},{"files",pins}};
  files.Add("config.json",Canonical(config)); files.Add("stop.json",Canonical(new Dictionary<string,object> {{"head",head},{"run_id",run},{"role","PC4"},{"stop",false}}));
  foreach(var item in files) NewFile(Path.Combine(role,item.Key),item.Value,sid);
  string target=Target(local); int transactions=Directory.GetDirectories(local,".GridS0Transaction-*").Length;
  Phase="FIXTURE_EXPORT_PLAN"; var planned=ProfileApi.PlanTransferExport(role,head,run,packageSha,target,sid); Need(planned.Materialization.Status=="PLAN_ONLY" && planned.Materialization.FileCount==1 && !Directory.Exists(target) && Directory.GetDirectories(local,".GridS0Transaction-*").Length==transactions);
  Block(delegate { ProfileApi.StageTransferExport(role,head,run,packageSha,target,sid,false); });
  Block(delegate { ProfileApi.StageTransferExport(pair,head,run,packageSha,target,sid,true); });
  Block(delegate { ProfileApi.StageTransferExport(role,head,run,packageSha,target,"S-1-5-21-1-2-3-1001",true); });
  Phase="FIXTURE_EXPORT_STAGE"; var staged=ProfileApi.StageTransferExport(role,head,run,packageSha,target,sid,true); string path=Path.Combine(target,"pc4-role.zip"); byte[] payload=File.ReadAllBytes(path);
  Need(staged.Materialization.Status=="STAGED_NO_EXECUTION_AUTHORITY" && staged.Size==payload.LongLength && staged.Size==planned.Size && staged.PayloadSha256==Hash(payload) && staged.PayloadSha256==planned.PayloadSha256 && !staged.S0Execute && !staged.G1Execute && !staged.Cleanup && Directory.GetFiles(target).Length==1 && Directory.GetDirectories(target).Length==0);
  Phase="FIXTURE_EXPORT_SOURCE_STABLE"; foreach(var item in files) Need(Hash(File.ReadAllBytes(Path.Combine(role,item.Key)))==Hash(item.Value));
  Phase="FIXTURE_EXPORT_READBACK"; using(var memory=new MemoryStream(payload,false)) using(var zip=new ZipArchive(memory,ZipArchiveMode.Read,false)) { Need(zip.Entries.Count==6); var names=new HashSet<string>(StringComparer.Ordinal); foreach(var entry in zip.Entries) { Need(files.ContainsKey(entry.FullName) && names.Add(entry.FullName)); using(var input=entry.Open()) using(var output=new MemoryStream()) { input.CopyTo(output); Need(Hash(output.ToArray())==Hash(files[entry.FullName])); } } }
  Phase="FIXTURE_EXPORT_KNOWN_HOSTS"; TransferTransportTests.HostedKnownHosts(target,staged.Materialization.RootIdentity,staged.PayloadSha256,head,run,sid);
  Phase="FIXTURE_EXPORT_REUSE"; Block(delegate { ProfileApi.StageTransferExport(role,head,run,packageSha,target,sid,true); });
  // Mutate only our newly created fixture bytes; production export must reject both.
  string fresh=Target(local); Phase="FIXTURE_EXPORT_DIGEST"; using(var f=new FileStream(Path.Combine(role,"tls-key.pem"),FileMode.Truncate,FileAccess.Write,FileShare.None)) { f.WriteByte(0); f.Flush(true); } Block(delegate { ProfileApi.PlanTransferExport(role,head,run,packageSha,fresh,sid); });
  using(var f=new FileStream(Path.Combine(role,"tls-key.pem"),FileMode.Truncate,FileAccess.Write,FileShare.None)) { byte[] bytes=files["tls-key.pem"]; f.Write(bytes,0,bytes.Length); f.Flush(true); }
  Phase="FIXTURE_EXPORT_ROLE"; config["role"]="LS5"; byte[] wrong=Canonical(config); using(var f=new FileStream(Path.Combine(role,"config.json"),FileMode.Truncate,FileAccess.Write,FileShare.None)) { f.Write(wrong,0,wrong.Length); f.Flush(true); } Block(delegate { ProfileApi.PlanTransferExport(role,head,run,packageSha,fresh,sid); });
  using(var f=new FileStream(Path.Combine(role,"config.json"),FileMode.Truncate,FileAccess.Write,FileShare.None)) { byte[] bytes=files["config.json"]; f.Write(bytes,0,bytes.Length); f.Flush(true); }
  Phase="FIXTURE_EXPORT_UNCHANGED"; foreach(var item in files) Need(Hash(File.ReadAllBytes(Path.Combine(role,item.Key)))==Hash(item.Value)); Need(Hash(File.ReadAllBytes(path))==staged.PayloadSha256 && !Directory.Exists(fresh));
  // No TLS/SSH use, no source ACL changes, no existing-resource adoption, no cleanup.
 }
}
