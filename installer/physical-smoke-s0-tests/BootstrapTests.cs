// These fixtures run on genuine hosted Windows only; PureRejects uses no native calls.
using System;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Security.Principal;
using System.Threading;
using GridS0;
public static class BootstrapTests {
 public static string Phase="FIXTURE_BOOTSTRAP_START";
 static void Need(bool value) { if(!value) throw new InvalidOperationException("FIXTURE_BOOTSTRAP_CHECK"); }
 static void Block(Action action) { try { action(); } catch(InvalidOperationException) { return; } throw new InvalidOperationException("FIXTURE_BOOTSTRAP_EXPECTED_BLOCK"); }
 public static void Hosted(string root,string unusedImageSha,string head) {
  Need(Environment.GetEnvironmentVariable("GITHUB_ACTIONS")=="true" && Environment.GetEnvironmentVariable("RUNNER_ENVIRONMENT")=="github-hosted" && Environment.GetEnvironmentVariable("GITHUB_REPOSITORY")=="YehorBabenko88/bybit-cluster-grid" && Environment.GetEnvironmentVariable("GITHUB_JOB")=="s0-windows");
  Need(!String.Equals(Environment.MachineName,"LS5",StringComparison.OrdinalIgnoreCase) && !String.Equals(Environment.MachineName,"PC4",StringComparison.OrdinalIgnoreCase));
  PureRejects();
  string sid; using(var identity=WindowsIdentity.GetCurrent()) sid=identity.User.Value;
  TokenObserver.RequireStandard(sid);
  Phase="FIXTURE_INPUTS"; InputTests.Pure(); InputTests.Hosted(sid,head); Phase="FIXTURE_BOOTSTRAP_PACKAGE";
  string local=Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
  byte[] zip=File.ReadAllBytes(Path.Combine(root,"source.zip")); string sha=Hash(zip);
  string target=Path.Combine(local,"GridS0Package-"+Guid.NewGuid().ToString("D"));
  string canary=Path.Combine(root,"runtime","python.exe"); string original=Hash(File.ReadAllBytes(canary));
  string[] transactions=Directory.GetDirectories(local,".GridS0Transaction-*");
  Phase="FIXTURE_BOOTSTRAP_PLAN"; BootstrapReceipt plan=Bootstrap.PlanPackage(zip,sha,head,target,sid);
  Need(plan.Status=="PLAN_ONLY" && plan.RootIdentity==null && !plan.S0Execute && !plan.G1Execute && !plan.Cleanup && !Directory.Exists(target));
  Need(Directory.GetDirectories(local,".GridS0Transaction-*").Length==transactions.Length);
  Block(delegate { Bootstrap.StagePackage(zip,sha,head,target,sid,false); });
  Block(delegate { Bootstrap.StagePackage(zip,new string('0',64),head,target,sid,true); });
  Block(delegate { Bootstrap.StagePackage(zip,sha,head,Path.Combine(root,Path.GetFileName(target)),sid,true); });
  Block(delegate { Bootstrap.StagePackage(zip,sha,head,target,"S-1-5-18",true); });
  Need(!Directory.Exists(target));
  Phase="FIXTURE_BOOTSTRAP_STAGE"; BootstrapReceipt staged=Bootstrap.StagePackage(zip,sha,head,target,sid,true);
  Need(staged.Status=="STAGED_NO_EXECUTION_AUTHORITY" && staged.RootIdentity!=null && staged.ParentIdentity==plan.ParentIdentity && staged.FileCount==plan.FileCount && staged.Bytes==plan.Bytes && !staged.S0Execute && !staged.G1Execute && !staged.Cleanup);
  Phase="FIXTURE_BOOTSTRAP_READBACK"; Need(Hash(File.ReadAllBytes(Path.Combine(target,"source.zip")))==sha);
  string publishedIdentity=staged.RootIdentity;
  Phase="FIXTURE_BOOTSTRAP_REUSE"; Block(delegate { Bootstrap.StagePackage(zip,sha,head,target,sid,true); });
  Need(Hash(File.ReadAllBytes(Path.Combine(target,"source.zip")))==sha && Hash(File.ReadAllBytes(canary))==original);
  // Two independent validated calls may race; exactly one may publish the fresh name.
  Phase="FIXTURE_BOOTSTRAP_RACE"; string race=Path.Combine(local,"GridS0Package-"+Guid.NewGuid().ToString("D")); int winners=0,blocked=0; Exception unexpected=null;
  ThreadStart attempt=delegate { try { Bootstrap.StagePackage(zip,sha,head,race,sid,true); Interlocked.Increment(ref winners); } catch(InvalidOperationException) { Interlocked.Increment(ref blocked); } catch(Exception error) { unexpected=error; } };
  Thread first=new Thread(attempt), second=new Thread(attempt); first.Start(); second.Start(); Need(first.Join(45000) && second.Join(45000));
  Need(unexpected==null && winners==1 && blocked==1 && Hash(File.ReadAllBytes(Path.Combine(race,"source.zip")))==sha && Hash(File.ReadAllBytes(canary))==original);
  string receipt="{\"scope\":\"HOSTED_BOOTSTRAP_NOT_PHYSICAL\",\"head\":\""+head+"\",\"package_sha256\":\""+sha+"\",\"status\":\"PASS\",\"plan_no_write\":true,\"unapproved_rejected\":true,\"wrong_sha_rejected\":true,\"wrong_sid_rejected\":true,\"outside_parent_rejected\":true,\"stage_closure\":true,\"existing_target_rejected\":true,\"concurrent_no_replace\":true,\"canary_unchanged\":true,\"s0_execute\":false,\"g1_execute\":false,\"cleanup\":false}";
  using(var stream=new FileStream(Path.Combine(root,"temp","bootstrap.json"),FileMode.CreateNew,FileAccess.Write,FileShare.None)) { byte[] bytes=Encoding.UTF8.GetBytes(receipt); stream.Write(bytes,0,bytes.Length); stream.Flush(true); }
  // Owned successful/partial fixture roots deliberately remain; no auto cleanup/adoption.
 }
 public static void PureRejects() {
  Reject(new byte[0], new string('0',64));
  Reject(new byte[]{80,75,3,4}, new string('0',64));
  Reject(new byte[]{80,75,3,4}, "bad");
  foreach(string manifest in new[]{"{}", "{\"schema\":1,\"schema\":1}", "{\"schema\":true}", "{\"schema\":1.0}", "{\"schema\":01}", "{\"schema\":1e0}"}) {
   byte[] zip=Archive(manifest); Reject(zip,Hash(zip));
  }
  try { Bootstrap.StagePackage(new byte[0],"bad","bad","invalid","invalid",false); }
  catch(InvalidOperationException) { return; }
  throw new Exception("UNAPPROVED_STAGE_ACCEPTED");
 }
 static byte[] Archive(string manifest) {
  using(var output=new MemoryStream()) {
   using(var zip=new ZipArchive(output,ZipArchiveMode.Create,true)) {
    foreach(string name in new[]{"s0-package.json","runtime/python.exe","runtime/python._pth","runtime/python312._pth","runtime/App/s0.py","runtime/stdlib.zip"}) {
     var entry=zip.CreateEntry(name); entry.ExternalAttributes=unchecked((int)0x81a40000u);
     using(var stream=entry.Open()) { byte[] b=Encoding.UTF8.GetBytes(name=="s0-package.json"?manifest:""); stream.Write(b,0,b.Length); }
    }
   }
   return output.ToArray();
  }
 }
 static string Hash(byte[] data) { using(var sha=SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(data)).Replace("-","").ToLowerInvariant(); }
 static void Reject(byte[] data,string sha) {
  try { Bootstrap.PlanPackage(data,sha,new string('a',40),"invalid","invalid"); }
  catch (InvalidOperationException) { return; }
  throw new Exception("BOOTSTRAP_NEGATIVE_ACCEPTED");
 }
}
