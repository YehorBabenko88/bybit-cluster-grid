// Genuine hosted disposable NTFS only; never run on LS5/PC4.
using System;
using System.IO;
using System.Text;
using System.Security.Cryptography;
using GridS0;
public static class TransferTransportTests {
 public static string Phase="FIXTURE_TRANSPORT_START";
 static void Need(bool b) { if(!b) throw new InvalidOperationException("FIXTURE_TRANSPORT_CHECK"); }
 static void Block(Action a) { try { a(); } catch(InvalidOperationException) { return; } throw new InvalidOperationException("FIXTURE_TRANSPORT_EXPECTED_BLOCK"); }
 static string Hash(byte[] b) { using(var h=SHA256.Create()) return BitConverter.ToString(h.ComputeHash(b)).Replace("-","").ToLowerInvariant(); }
 static string Target(string local) { return Path.Combine(local,"GridS0Input-"+Guid.NewGuid().ToString("D")); }
 static byte[] Wire() { byte[] b=new byte[51]; b[3]=11; Encoding.ASCII.GetBytes("ssh-ed25519").CopyTo(b,4); b[18]=32; for(int i=0;i<32;i++) b[19+i]=(byte)(i+1); return b; }
 static string Fingerprint(byte[] wire) { using(var h=SHA256.Create()) return "SHA256:"+Convert.ToBase64String(h.ComputeHash(wire)).TrimEnd('='); }
 public static void Pure() {
  string head=new string('a',40),run="12345678-1234-4234-8234-123456789abc",sid="S-1-5-21-1-2-3-1001",blob=Convert.ToBase64String(Wire()),fp=Fingerprint(Wire());
  foreach(string host in new[]{"8.8.8.8","100.064.0.1","host","127.0.0.1","100.64.0.1;cmd"}) Block(delegate { ProfileApi.PlanTransferProbe(head,run,host,blob,fp,"unused",sid); });
  Block(delegate { ProfileApi.PlanTransferProbe(head,run,"100.64.0.1",blob,"SHA256:"+new string('A',43),"unused",sid); });
  Block(delegate { ProfileApi.PlanTransferProbe(head,run,"100.64.0.1",blob+"=",fp,"unused",sid); });
  byte[] extended=new byte[52]; Wire().CopyTo(extended,0); string bad=Convert.ToBase64String(extended);
  Block(delegate { ProfileApi.PlanTransferProbe(head,run,"100.64.0.1",bad,Fingerprint(extended),"unused",sid); });
  Block(delegate { ProfileApi.StageTransferProbe(head,run,"100.64.0.1",blob,fp,"unused",sid,false); });
 }
 public static void Hosted(string sid,string head) {
  Need(Environment.GetEnvironmentVariable("GITHUB_ACTIONS")=="true" && Environment.GetEnvironmentVariable("RUNNER_ENVIRONMENT")=="github-hosted" && Environment.GetEnvironmentVariable("GITHUB_REPOSITORY")=="YehorBabenko88/bybit-cluster-grid" && Environment.GetEnvironmentVariable("GITHUB_JOB")=="s0-windows");
  Need(!String.Equals(Environment.MachineName,"LS5",StringComparison.OrdinalIgnoreCase) && !String.Equals(Environment.MachineName,"PC4",StringComparison.OrdinalIgnoreCase)); TokenObserver.RequireStandard(sid); Pure();
  string local=ProfileApi.Parent(),run=Guid.NewGuid().ToString("D"),root=Target(local),host="100.64.0.2",blob=Convert.ToBase64String(Wire()),fp=Fingerprint(Wire());
  int count=Directory.GetDirectories(local,".GridS0Transaction-*").Length;
  Phase="FIXTURE_TRANSPORT_PLAN"; var plan=ProfileApi.PlanTransferProbe(head,run,host,blob,fp,root,sid);
  Need(plan.Materialization.Status=="PLAN_ONLY" && plan.Profile=="PUBLIC_TRANSFER_PROBE_NOT_ROLE_ARCHIVE" && !Directory.Exists(root) && Directory.GetDirectories(local,".GridS0Transaction-*").Length==count);
  Phase="FIXTURE_TRANSPORT_STAGE"; var staged=ProfileApi.StageTransferProbe(head,run,host,blob,fp,root,sid,true);
  string payload=Path.Combine(root,"pc4-role.zip"),known=Path.Combine(root,"known_hosts");
  Need(Directory.GetFiles(root).Length==2 && Hash(File.ReadAllBytes(known))==staged.KnownHostsSha256 && File.ReadAllText(known)==host+" ssh-ed25519 "+blob+"\n");
  Phase="FIXTURE_TRANSPORT_SENDER";
  using(var lease=ProfileApi.OpenTransferSender(root,staged.Materialization.RootIdentity,staged.PayloadSha256,staged.KnownHostsSha256,sid)) {
   var verified=lease.Verify(); Need(verified.PayloadSha256==staged.PayloadSha256 && verified.KnownHostsSha256==staged.KnownHostsSha256 && verified.Size==staged.Size);
   foreach(string path in new[]{payload,known}) {
    bool blocked=false; try { using(var writer=new FileStream(path,FileMode.Open,FileAccess.Write,FileShare.ReadWrite)) {} } catch(IOException) { blocked=true; } catch(UnauthorizedAccessException) { blocked=true; } Need(blocked);
    blocked=false; try { File.Move(path,path+".replacement"); } catch(IOException) { blocked=true; } catch(UnauthorizedAccessException) { blocked=true; } Need(blocked);
   }
   Need(lease.Verify().PayloadSha256==staged.PayloadSha256);
   File.WriteAllBytes(Path.Combine(root,"extra.txt"),new byte[]{1}); Block(delegate { lease.Verify(); });
  }
  Block(delegate { ProfileApi.OpenTransferSender(root,staged.Materialization.RootIdentity,staged.PayloadSha256,staged.KnownHostsSha256,sid).Dispose(); });
 }
 public static void HostedKnownHosts(string root,string rootId,string sha,string head,string run,string sid) {
  string host="100.64.0.2",blob=Convert.ToBase64String(Wire()),fp=Fingerprint(Wire());
  Phase="FIXTURE_TRANSPORT_KNOWN_PLAN"; var plan=ProfileApi.PlanTransferKnownHosts(root,rootId,sha,head,run,host,blob,fp,sid);
  Need(plan.Status=="PLAN_ONLY" && !File.Exists(Path.Combine(root,"known_hosts")));
  Block(delegate { ProfileApi.StageTransferKnownHosts(root,rootId,sha,head,run,host,blob,fp,sid,false); });
  Block(delegate { ProfileApi.PlanTransferKnownHosts(root,rootId,sha,head,run,"100.64.0.3",blob,fp,sid); });
  Block(delegate { ProfileApi.PlanTransferKnownHosts(root,rootId,sha,head,run,host,blob,"SHA256:"+new string('A',43),sid); });
  Phase="FIXTURE_TRANSPORT_KNOWN_STAGE"; var receipt=ProfileApi.StageTransferKnownHosts(root,rootId,sha,head,run,host,blob,fp,sid,true);
  Need(receipt.Status=="STAGED_NO_EXECUTION_AUTHORITY" && receipt.KnownHostsSha256==plan.KnownHostsSha256 && Directory.GetFiles(root).Length==2);
  using(var lease=ProfileApi.OpenTransferSender(root,rootId,sha,receipt.KnownHostsSha256,sid)) Need(lease.Verify().PayloadSha256==sha);
  Block(delegate { ProfileApi.StageTransferKnownHosts(root,rootId,sha,head,run,host,blob,fp,sid,true); });
 }

}
