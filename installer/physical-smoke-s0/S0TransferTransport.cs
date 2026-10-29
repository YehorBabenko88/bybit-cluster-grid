// C#5 / .NET Framework 4.8. No SSH, process, socket or network operations.
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Win32.SafeHandles;
namespace GridS0 {
 public sealed class TransferProbeReceipt {
  public BootstrapReceipt Materialization { get; internal set; }
  public string PayloadSha256 { get; internal set; }
  public long Size { get; internal set; }
  public string KnownHostsSha256 { get; internal set; }
  public string Profile { get { return "PUBLIC_TRANSFER_PROBE_NOT_ROLE_ARCHIVE"; } }
  public bool S0Execute { get { return false; } }
  public bool G1Execute { get { return false; } }
  public bool Cleanup { get { return false; } }
 }
 public sealed class TransferKnownHostsReceipt {
  public string RootIdentity { get; internal set; }
  public string PayloadSha256 { get; internal set; }
  public long Size { get; internal set; }
  public string KnownHostsSha256 { get; internal set; }
  public string Status { get; internal set; }
  public bool S0Execute { get { return false; } }
  public bool G1Execute { get { return false; } }
  public bool Cleanup { get { return false; } }
 }
 public sealed class TransferSenderVerificationReceipt {
  public string PayloadSha256 { get; internal set; }
  public long Size { get; internal set; }
  public string KnownHostsSha256 { get; internal set; }
  public string Status { get { return "VERIFIED_NOT_AUTHORIZATION"; } }
  public bool S0Execute { get { return false; } }
  public bool G1Execute { get { return false; } }
  public bool Cleanup { get { return false; } }
 }
 public static partial class Bootstrap {
  static byte[] TransferHostLine(string host,string blob,string fingerprint) {
   InputIP(host);
   Need(blob!=null && blob.Length==68 && Match(fingerprint,"SHA256:[A-Za-z0-9+/]{43}"));
   byte[] raw; try { raw=Convert.FromBase64String(blob); } catch(FormatException) { throw new InvalidOperationException("S0_TRANSFER_HOST_KEY_BLOCKED"); }
   Need(raw.Length==51 && Convert.ToBase64String(raw)==blob);
   Need(raw[0]==0 && raw[1]==0 && raw[2]==0 && raw[3]==11 && Encoding.ASCII.GetString(raw,4,11)=="ssh-ed25519" && raw[15]==0 && raw[16]==0 && raw[17]==0 && raw[18]==32);
   using(var hash=SHA256.Create()) Need("SHA256:"+Convert.ToBase64String(hash.ComputeHash(raw)).TrimEnd('=')==fingerprint);
   return Encoding.ASCII.GetBytes(host+" ssh-ed25519 "+blob+"\n");
  }
  public static TransferProbeReceipt PlanTransferProbe(string head,string run,string hostIP,string ed25519Base64Blob,string fullSHA256Fingerprint,string targetNewInputUUID,string sid) { return TransferProbe(head,run,hostIP,ed25519Base64Blob,fullSHA256Fingerprint,targetNewInputUUID,sid,false); }
  public static TransferProbeReceipt StageTransferProbe(string head,string run,string hostIP,string ed25519Base64Blob,string fullSHA256Fingerprint,string targetNewInputUUID,string sid,bool approved) { Need(approved); return TransferProbe(head,run,hostIP,ed25519Base64Blob,fullSHA256Fingerprint,targetNewInputUUID,sid,true); }
  static TransferProbeReceipt TransferProbe(string head,string run,string host,string blob,string fingerprint,string target,string sid,bool stage,ParentKind kind=ParentKind.LocalAppData) {
   TransferContext(head,run,new string('0',64),1,sid); byte[] known=TransferHostLine(host,blob,fingerprint);
   byte[] json=Encoding.ASCII.GetBytes(InputJson(new Dictionary<string,object> {{"profile","PUBLIC_TRANSFER_PROBE_NOT_ROLE_ARCHIVE"},{"head",head},{"run_id",run},{"marker","NO_KEYS"}}));
   byte[] payload;
   using(var output=new MemoryStream()) {
    using(var zip=new ZipArchive(output,ZipArchiveMode.Create,true)) {
     var entry=zip.CreateEntry("probe.json",CompressionLevel.Optimal); entry.LastWriteTime=new DateTimeOffset(1980,1,1,0,0,0,TimeSpan.Zero); entry.ExternalAttributes=unchecked((int)0x81a40000u);
     using(var content=entry.Open()) content.Write(json,0,json.Length);
    }
    payload=output.ToArray();
   }
   Need(payload.Length>0 && payload.Length<=TransferLimit); string sha=Hash(payload); var package=new Package(); package.Files.Add("pc4-role.zip",payload); package.Files.Add("known_hosts",known); package.Bytes=payload.LongLength+known.LongLength;
   return new TransferProbeReceipt { Materialization=Publish(package,null,sha,head,target,sid,"GridS0Input-",stage,kind),PayloadSha256=sha,Size=payload.LongLength,KnownHostsSha256=Hash(known) };
  }
  static void SenderRoot(string root,string rootId,string payloadSha,string sid,ParentKind kind=ParentKind.LocalAppData) {
   Need(Match(rootId,"[0-9a-f]{8}:[0-9a-f]{16}") && Match(payloadSha,"[0-9a-f]{64}")); TokenObserver.RequireStandard(sid);
   string local=ParentPath(sid,kind);
   Need(root!=null && root.Length<=240 && root==Path.GetFullPath(root) && String.Equals(Path.GetDirectoryName(root),local,StringComparison.OrdinalIgnoreCase) && Match(Path.GetFileName(root),"GridS0Input-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"));
  }
  static void SenderClosure(string root,bool known) {
   Need(Directory.GetDirectories(root).Length==0); var expected=new HashSet<string>(StringComparer.Ordinal) { Path.Combine(root,"pc4-role.zip") }; if(known) expected.Add(Path.Combine(root,"known_hosts"));
   Need(expected.SetEquals(Directory.GetFiles(root)));
  }
  static FileStream SenderStream(string path,string sid,out string identity) {
   var handle=TransferReadHandle(path);
   try { identity=Inspect(handle,path,false,true,sid); return new FileStream(handle,FileAccess.Read,8192,false); } catch { handle.Dispose(); throw; }
  }
  static byte[] SenderBytes(FileStream stream,int limit) { stream.Position=0; return TransferRead(stream,limit); }
  public static TransferSenderLease OpenTransferSender(string root,string rootId,string payloadSHA,string knownHostsSHA,string sid) {
   SenderRoot(root,rootId,payloadSHA,sid); Need(Match(knownHostsSHA,"[0-9a-f]{64}")); return new TransferSenderLease(root,rootId,payloadSHA,knownHostsSHA,sid);
  }
  public sealed class TransferSenderLease:IDisposable {
   readonly object gate=new object(); readonly string root,rootId,payloadSha,knownSha,sid; string payloadId,knownId; long size;
   Pins pins; UserProfileLease profile; FileStream payload,known; bool disposed;
   internal TransferSenderLease(string r,string rid,string sha,string kh,string s,ParentKind kind=ParentKind.LocalAppData) {
    root=r;rootId=rid;payloadSha=sha;knownSha=kh;sid=s;
    try {
     if(kind==ParentKind.UserProfileV1) { profile=HoldUserProfileV1(sid); Need(String.Equals(Path.GetDirectoryName(root),profile.ParentPath,StringComparison.OrdinalIgnoreCase)); }
     pins=new Pins(root,sid); Need(Inspect(pins.Parent,root,true,true,sid)==rootId); SenderClosure(root,true);
     payload=SenderStream(Path.Combine(root,"pc4-role.zip"),sid,out payloadId); known=SenderStream(Path.Combine(root,"known_hosts"),sid,out knownId);
     byte[] bytes=SenderBytes(payload,TransferLimit); Need(bytes.Length>0 && Hash(bytes)==payloadSha); size=bytes.LongLength;
     Need(Hash(SenderBytes(known,1024))==knownSha); VerifyCore();
    } catch { Dispose(); throw; }
   }
   void VerifyCore() {
    Need(!disposed); TokenObserver.RequireStandard(sid); if(profile!=null) profile.Check(); pins.Check(); SenderClosure(root,true);
    Need(Inspect(pins.Parent,root,true,true,sid)==rootId && Inspect(payload.SafeFileHandle,Path.Combine(root,"pc4-role.zip"),false,true,sid)==payloadId && Inspect(known.SafeFileHandle,Path.Combine(root,"known_hosts"),false,true,sid)==knownId);
    byte[] bytes=SenderBytes(payload,TransferLimit); Need(bytes.LongLength==size && Hash(bytes)==payloadSha && Hash(SenderBytes(known,1024))==knownSha); pins.Check(); SenderClosure(root,true);
   }
   public TransferSenderVerificationReceipt Verify() { lock(gate) { VerifyCore(); return new TransferSenderVerificationReceipt { PayloadSha256=payloadSha,Size=size,KnownHostsSha256=knownSha }; } }
   public void Dispose() { lock(gate) { if(disposed) return; disposed=true; if(known!=null) known.Dispose(); if(payload!=null) payload.Dispose(); if(pins!=null) pins.Dispose(); if(profile!=null) profile.Dispose(); } }
  }
  public static TransferKnownHostsReceipt PlanTransferKnownHosts(string exportRoot,string rootId,string payloadSHA,string head,string run,string hostIP,string ed25519Base64Blob,string fullSHA256Fingerprint,string sid) { return TransferKnownHosts(exportRoot,rootId,payloadSHA,head,run,hostIP,ed25519Base64Blob,fullSHA256Fingerprint,sid,false); }
  public static TransferKnownHostsReceipt StageTransferKnownHosts(string exportRoot,string rootId,string payloadSHA,string head,string run,string hostIP,string ed25519Base64Blob,string fullSHA256Fingerprint,string sid,bool approved) { Need(approved); return TransferKnownHosts(exportRoot,rootId,payloadSHA,head,run,hostIP,ed25519Base64Blob,fullSHA256Fingerprint,sid,true); }
  static TransferKnownHostsReceipt TransferKnownHosts(string root,string rootId,string sha,string head,string run,string host,string blob,string fingerprint,string sid,bool stage,ParentKind kind=ParentKind.LocalAppData) {
   using(var profile=kind==ParentKind.UserProfileV1?HoldUserProfileV1(sid):null) {
   TransferContext(head,run,sha,1,sid); byte[] known=TransferHostLine(host,blob,fingerprint); SenderRoot(root,rootId,sha,sid,kind);
   using(var pins=new Pins(root,sid)) {
    Need(Inspect(pins.Parent,root,true,true,sid)==rootId); SenderClosure(root,false); Absent(Path.Combine(root,"known_hosts")); string payloadId;
    using(var payload=SenderStream(Path.Combine(root,"pc4-role.zip"),sid,out payloadId)) {
     byte[] bytes=SenderBytes(payload,TransferLimit); Need(bytes.Length>0 && Hash(bytes)==sha); ValidateSenderRole(bytes,head,run,host,sid);
     pins.Check(); SenderClosure(root,false); Need(Inspect(pins.Parent,root,true,true,sid)==rootId && Inspect(payload.SafeFileHandle,Path.Combine(root,"pc4-role.zip"),false,true,sid)==payloadId);
     if(profile!=null) { profile.Check(); Need(String.Equals(Path.GetDirectoryName(root),profile.ParentPath,StringComparison.OrdinalIgnoreCase)); }
   if(stage) {
      using(var security=new Security(sid)) WriteMember(root,"known_hosts",known,security,sid,new HashSet<string>(StringComparer.OrdinalIgnoreCase));
      string knownId; using(var captured=SenderStream(Path.Combine(root,"known_hosts"),sid,out knownId)) Need(Hash(SenderBytes(captured,1024))==Hash(known));
      SenderClosure(root,true);
     }
     pins.Check(); Need(Inspect(pins.Parent,root,true,true,sid)==rootId && Inspect(payload.SafeFileHandle,Path.Combine(root,"pc4-role.zip"),false,true,sid)==payloadId && Hash(SenderBytes(payload,TransferLimit))==sha);
     return new TransferKnownHostsReceipt { RootIdentity=rootId,PayloadSha256=sha,Size=bytes.LongLength,KnownHostsSha256=Hash(known),Status=stage?"STAGED_NO_EXECUTION_AUTHORITY":"PLAN_ONLY" };
    }
   }

   }
  }
  static void ValidateSenderRole(byte[] bytes,string head,string run,string host,string sid) {
   var files=new Dictionary<string,byte[]>(StringComparer.Ordinal);
   using(var memory=new MemoryStream(bytes,false)) using(var zip=new ZipArchive(memory,ZipArchiveMode.Read,false)) {
    Need(zip.Entries.Count==6); long total=0;
    foreach(var entry in zip.Entries) {
     Need(Array.IndexOf(RoleFiles,entry.FullName)>=0 && !files.ContainsKey(entry.FullName) && entry.Length>0 && entry.Length<=1048576);
     uint attributes=(uint)entry.ExternalAttributes,mode=attributes>>16; Need((attributes&0x410)==0 && ((mode&0xf000)==0 || (mode&0xf000)==0x8000));
     using(var content=entry.Open()) { byte[] raw=TransferRead(content,1048576); Need(raw.LongLength==entry.Length); total+=raw.LongLength; Need(total<=TransferLimit); files.Add(entry.FullName,raw); }
    }
   }
   var c=Obj(new Json(files["config.json"]).Read(),"schema","profile","plan","role","package_sha256","files");
   Need(Num(c["schema"])==1 && Str(c["profile"])=="PHYSICAL_SMOKE_S0" && Str(c["role"])=="PC4" && Match(Str(c["package_sha256"]),"[0-9a-f]{64}")); CanonicalInput(files["config.json"],c);
   var plan=Obj(c["plan"]); ValidateInputPlan(plan,head,run); Need(Str(plan["worker_ip"])==host && Str(Obj(plan["operator_sids"],"LS5","PC4")["LS5"])==sid);
   var hashes=Obj(c["files"],"ca.pem","tls-cert.pem","peer-cert.pem","tls-key.pem"); foreach(var item in hashes) Need(Match(Str(item.Value),"[0-9a-f]{64}") && Hash(files[item.Key])==Str(item.Value));
   var stop=Obj(new Json(files["stop.json"]).Read(),"head","run_id","role","stop"); Need(Str(stop["head"])==head && Str(stop["run_id"])==run && Str(stop["role"])=="PC4" && stop["stop"] is bool && !(bool)stop["stop"]); CanonicalInput(files["stop.json"],stop);
  }
 }
}
