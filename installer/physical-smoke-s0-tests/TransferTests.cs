// Hosted synthetic transfer-slot fixtures; no SSH and no TLS claim.
using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using GridS0;
public static class TransferTests {
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateHardLinkW(string link,string existing,IntPtr attributes);
 public static string Phase="FIXTURE_TRANSFER_START";
 static void Need(bool b) { if(!b) throw new InvalidOperationException("FIXTURE_TRANSFER_CHECK"); }
 static void Block(Action a) { try { a(); } catch(InvalidOperationException) { return; } throw new InvalidOperationException("FIXTURE_TRANSFER_EXPECTED_BLOCK"); }
 static string Hash(byte[] b) { using(var h=SHA256.Create()) return BitConverter.ToString(h.ComputeHash(b)).Replace("-","").ToLowerInvariant(); }
 static string Target(string local) { return Path.Combine(local,"GridS0Input-"+Guid.NewGuid().ToString("D")); }
 static void WriteExisting(string path,byte[] bytes) { using(var f=new FileStream(path,FileMode.Truncate,FileAccess.Write,FileShare.ReadWrite)) { f.Write(bytes,0,bytes.Length); f.Flush(true); } }
 public static void Hosted(string sid,string head) {
  Need(Environment.GetEnvironmentVariable("GITHUB_ACTIONS")=="true" && Environment.GetEnvironmentVariable("RUNNER_ENVIRONMENT")=="github-hosted" && Environment.GetEnvironmentVariable("GITHUB_REPOSITORY")=="YehorBabenko88/bybit-cluster-grid" && Environment.GetEnvironmentVariable("GITHUB_JOB")=="s0-windows");
  Need(!String.Equals(Environment.MachineName,"LS5",StringComparison.OrdinalIgnoreCase) && !String.Equals(Environment.MachineName,"PC4",StringComparison.OrdinalIgnoreCase)); TokenObserver.RequireStandard(sid);
  string local=ProfileApi.Parent(), run=Guid.NewGuid().ToString("D"), target=Target(local); byte[] payload=Encoding.ASCII.GetBytes("SYNTHETIC TRANSFER PAYLOAD, NOT A ROLE ARCHIVE"); string sha=Hash(payload);
  int transactions=Directory.GetDirectories(local,".GridS0Transaction-*").Length;
  Phase="FIXTURE_TRANSFER_PLAN"; TransferSlotReceipt plan=ProfileApi.PlanTransferSlot(head,run,sha,payload.LongLength,target,sid); Need(plan.Materialization.Status=="PLAN_ONLY" && plan.IncomingIdentity==null && !Directory.Exists(target) && Directory.GetDirectories(local,".GridS0Transaction-*").Length==transactions);
  Block(delegate { ProfileApi.StageTransferSlot(head,run,sha,payload.LongLength,target,sid,false); });
  Phase="FIXTURE_TRANSFER_STAGE"; TransferSlotReceipt slot=ProfileApi.StageTransferSlot(head,run,sha,payload.LongLength,target,sid,true); string incoming=Path.Combine(target,"incoming.zip");
  Need(slot.IncomingIdentity!=null && slot.Materialization.RootIdentity!=null && Directory.GetFiles(target).Length==2 && new FileInfo(incoming).Length==0);
  Phase="FIXTURE_TRANSFER_UNAPPROVED_LEASE";
  Block(delegate { ProfileApi.OpenTransferSlot(target,slot.Materialization.RootIdentity,slot.IncomingIdentity,head,run,sha,payload.LongLength,sid,false).Dispose(); });
  Need(!File.Exists(Path.Combine(target,"lease.json")) && Directory.GetFiles(target).Length==2);
  Phase="FIXTURE_TRANSFER_LEASE";
  using(var lease=ProfileApi.OpenTransferSlot(target,slot.Materialization.RootIdentity,slot.IncomingIdentity,head,run,sha,payload.LongLength,sid,true)) {
   Phase="FIXTURE_TRANSFER_CLAIM_PRESENT"; Need(File.Exists(Path.Combine(target,"lease.json")) && Directory.GetFiles(target).Length==3);
   Phase="FIXTURE_TRANSFER_SECOND_LEASE"; Block(delegate { ProfileApi.OpenTransferSlot(target,slot.Materialization.RootIdentity,slot.IncomingIdentity,head,run,sha,payload.LongLength,sid,true).Dispose(); });
   // Held identity handles permit truncating this exact empty object, but no rename/delete.
   Phase="FIXTURE_TRANSFER_REPLACEMENT"; bool replacementBlocked=false; try { File.Move(incoming,Path.Combine(target,"replaced.zip")); } catch(IOException) { replacementBlocked=true; } catch(UnauthorizedAccessException) { replacementBlocked=true; } Need(replacementBlocked && !File.Exists(Path.Combine(target,"replaced.zip")));
   Phase="FIXTURE_TRANSFER_PARENT_REPLACEMENT"; bool parentBlocked=false; try { Directory.Move(target,target+".replacement"); } catch(IOException) { parentBlocked=true; } catch(UnauthorizedAccessException) { parentBlocked=true; } Need(parentBlocked && !Directory.Exists(target+".replacement"));
   using(var writer=new FileStream(incoming,FileMode.Truncate,FileAccess.Write,FileShare.ReadWrite)) {
    writer.Write(payload,0,payload.Length); writer.Flush(true);
    Phase="FIXTURE_TRANSFER_LIVE_WRITER"; Block(delegate { lease.Verify(); });
   }
   Phase="FIXTURE_TRANSFER_CAPTURE"; Need(lease.Verify().PayloadSha256==sha);
  }
  Phase="FIXTURE_TRANSFER_REUSE";
  WriteExisting(incoming,new byte[0]); Need(new FileInfo(incoming).Length==0 && File.Exists(Path.Combine(target,"lease.json")));
  Block(delegate { ProfileApi.OpenTransferSlot(target,slot.Materialization.RootIdentity,slot.IncomingIdentity,head,run,sha,payload.LongLength,sid,true).Dispose(); });
  Phase="FIXTURE_TRANSFER_CONCURRENT_LEASE";
  string raced=Target(local); var racedSlot=ProfileApi.StageTransferSlot(head,run,sha,payload.LongLength,raced,sid,true);
  int winners=0,blocked=0; Exception unexpected=null;
  using(var start=new ManualResetEvent(false)) {
   ThreadStart attempt=delegate { start.WaitOne(); try { using(var candidate=ProfileApi.OpenTransferSlot(raced,racedSlot.Materialization.RootIdentity,racedSlot.IncomingIdentity,head,run,sha,payload.LongLength,sid,true)) Interlocked.Increment(ref winners); } catch(InvalidOperationException) { Interlocked.Increment(ref blocked); } catch(Exception error) { unexpected=error; } };
   Thread first=new Thread(attempt),second=new Thread(attempt); first.Start(); second.Start(); start.Set(); Need(first.Join(45000) && second.Join(45000));
  }
  Need(unexpected==null && winners==1 && blocked==1 && File.Exists(Path.Combine(raced,"lease.json")) && new FileInfo(Path.Combine(raced,"incoming.zip")).Length==0);
  Block(delegate { ProfileApi.OpenTransferSlot(raced,racedSlot.Materialization.RootIdentity,racedSlot.IncomingIdentity,head,run,sha,payload.LongLength,sid,true).Dispose(); });
  string bad=Target(local); var badSlot=ProfileApi.StageTransferSlot(head,run,sha,payload.LongLength,bad,sid,true);
  using(var lease=ProfileApi.OpenTransferSlot(bad,badSlot.Materialization.RootIdentity,badSlot.IncomingIdentity,head,run,sha,payload.LongLength,sid,true)) {
   Phase="FIXTURE_TRANSFER_BAD_SHA"; WriteExisting(Path.Combine(bad,"incoming.zip"),new byte[payload.Length]); Block(delegate { lease.Verify(); });
   Phase="FIXTURE_TRANSFER_BAD_SIZE"; WriteExisting(Path.Combine(bad,"incoming.zip"),new byte[1]); Block(delegate { lease.Verify(); });
  }
  Phase="FIXTURE_TRANSFER_HARDLINK"; string hard=Target(local); var hardSlot=ProfileApi.StageTransferSlot(head,run,sha,payload.LongLength,hard,sid,true);
  Need(CreateHardLinkW(Path.Combine(bad,"new-hardlink.zip"),Path.Combine(hard,"incoming.zip"),IntPtr.Zero));
  Block(delegate { ProfileApi.OpenTransferSlot(hard,hardSlot.Materialization.RootIdentity,hardSlot.IncomingIdentity,head,run,sha,payload.LongLength,sid,true).Dispose(); });
  Phase="FIXTURE_TRANSFER_EXPIRED"; string expired=Target(local); var old=ProfileApi.StageTransferSlot(head,run,sha,payload.LongLength,expired,sid,true);
  string metadata=Path.Combine(expired,"slot.json"); Type jsonType=typeof(Bootstrap).GetNestedType("Json",BindingFlags.NonPublic); object parser=Activator.CreateInstance(jsonType,BindingFlags.NonPublic|BindingFlags.Instance,null,new object[]{File.ReadAllBytes(metadata)},null); var value=(Dictionary<string,object>)jsonType.GetMethod("Read",BindingFlags.NonPublic|BindingFlags.Instance).Invoke(parser,null);
  value["created_utc"]=DateTime.UtcNow.AddSeconds(-301).ToString("yyyy-MM-ddTHH:mm:ss.fffffffZ",System.Globalization.CultureInfo.InvariantCulture); string canonical=(string)typeof(Bootstrap).GetMethod("InputJson",BindingFlags.NonPublic|BindingFlags.Static).Invoke(null,new object[]{value}); WriteExisting(metadata,Encoding.ASCII.GetBytes(canonical));
  Block(delegate { ProfileApi.OpenTransferSlot(expired,old.Materialization.RootIdentity,old.IncomingIdentity,head,run,sha,payload.LongLength,sid,true).Dispose(); });
  // All owned roots, including failures, remain; no overwrite adoption or cleanup.
 }
}
