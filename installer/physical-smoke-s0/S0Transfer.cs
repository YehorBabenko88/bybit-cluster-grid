using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Win32.SafeHandles;
namespace GridS0 {
 public sealed class TransferSlotReceipt {
  public BootstrapReceipt Materialization { get; internal set; }
  public string IncomingIdentity { get; internal set; }
  public string MetadataSha256 { get; internal set; }
  public bool S0Execute { get { return false; } }
  public bool G1Execute { get { return false; } }
  public bool Cleanup { get { return false; } }
 }
 public sealed class TransferVerificationReceipt {
  public string PayloadSha256 { get; internal set; }
  public long Size { get; internal set; }
  public string Status { get { return "VERIFIED_NOT_AUTHORIZATION"; } }
  public bool S0Execute { get { return false; } }
  public bool G1Execute { get { return false; } }
  public bool Cleanup { get { return false; } }
 }
 public static partial class Bootstrap {
  const int TransferLimit=6291456;
  public static TransferSlotReceipt PlanTransferSlot(string head,string run,string payloadSha,long size,string targetRoot,string sid) { return TransferSlot(head,run,payloadSha,size,targetRoot,sid,false); }
  public static TransferSlotReceipt StageTransferSlot(string head,string run,string payloadSha,long size,string targetRoot,string sid,bool approved) { Need(approved); return TransferSlot(head,run,payloadSha,size,targetRoot,sid,true); }
  static void TransferContext(string head,string run,string sha,long size,string sid) {
   Need(Match(head,"[0-9a-f]{40}") && Match(run,"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}") && Match(sha,"[0-9a-f]{64}") && size>0 && size<=TransferLimit);
   Need(Match(sid,"S-1-5-21(?:-(?:0|[1-9][0-9]{0,9})){4}")); foreach(string part in sid.Substring(9).Split('-')) { uint n; Need(UInt32.TryParse(part,out n)); }
  }
  static TransferSlotReceipt TransferSlot(string head,string run,string sha,long size,string target,string sid,bool stage) {
   TransferContext(head,run,sha,size,sid);
   var m=new Dictionary<string,object> {{"schema",1L},{"profile","PHYSICAL_SMOKE_S0_TRANSFER_SLOT"},{"head",head},{"run_id",run},{"payload_sha256",sha},{"size",size},{"operator_sid",sid},{"created_utc",DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ss.fffffffZ",System.Globalization.CultureInfo.InvariantCulture)}};
   byte[] metadata=Encoding.ASCII.GetBytes(InputJson(m)); var p=new Package(); p.Files.Add("incoming.zip",new byte[0]); p.Files.Add("slot.json",metadata); p.Bytes=metadata.LongLength;
   var receipt=new TransferSlotReceipt { Materialization=Publish(p,null,sha,head,target,sid,"GridS0Input-",stage),MetadataSha256=Hash(metadata) };
   if(stage) using(var pins=new Pins(target,sid)) { Need(Inspect(pins.Parent,target,true,true,sid)==receipt.Materialization.RootIdentity); using(var file=Open(Path.Combine(target,"incoming.zip"),false,false)) { receipt.IncomingIdentity=Inspect(file,Path.Combine(target,"incoming.zip"),false,true,sid); Info info; Need(GetFileInformationByHandle(file,out info) && info.SizeHigh==0 && info.SizeLow==0); } pins.Check(); }
   return receipt;
  }
  public static TransferSlotLease OpenTransferSlot(string root,string expectedRootId,string expectedFileId,string head,string run,string sha,long size,string sid,bool approved) {
   Need(approved); TransferContext(head,run,sha,size,sid); TokenObserver.RequireStandard(sid);
   Need(Match(expectedRootId,"[0-9a-f]{8}:[0-9a-f]{16}") && Match(expectedFileId,"[0-9a-f]{8}:[0-9a-f]{16}"));
   string local=Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData,Environment.SpecialFolderOption.DoNotVerify).TrimEnd('\\');
   Need(root!=null && root==Path.GetFullPath(root) && String.Equals(Path.GetDirectoryName(root),local,StringComparison.OrdinalIgnoreCase) && Match(Path.GetFileName(root),"GridS0Input-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"));
   return new TransferSlotLease(root,expectedRootId,expectedFileId,head,run,sha,size,sid);
  }
  public static BootstrapReceipt PlanTransferImport(TransferSlotLease lease,string head,string run,string packageSha,string target,string sid) {
   Need(lease!=null && lease.BoundHead==head && lease.BoundRun==run && lease.BoundSid==sid);
   return PlanRoleImport(lease.CaptureVerified(),lease.BoundSha,head,run,packageSha,target,sid);
  }
  public static BootstrapReceipt StageTransferImport(TransferSlotLease lease,string head,string run,string packageSha,string target,string sid,bool approved) {
   Need(approved && lease!=null && lease.BoundHead==head && lease.BoundRun==run && lease.BoundSid==sid);
   byte[] captured=lease.CaptureForImport();
   return StageRoleImport(captured,lease.BoundSha,head,run,packageSha,target,sid,true);
  }
  static SafeFileHandle TransferReadHandle(string path) { var h=CreateFileNoSecurity(LongPath(path),0x80000000|0x20000|0x80,1,IntPtr.Zero,3,0x200000,IntPtr.Zero); if(h.IsInvalid) { h.Dispose(); throw new InvalidOperationException("S0_TRANSFER_EXCLUSIVE_READ_BLOCKED"); } return h; }
  static byte[] TransferRead(Stream stream,int limit) { using(var output=new MemoryStream()) { byte[] buffer=new byte[8192]; int n; while((n=stream.Read(buffer,0,buffer.Length))>0) { Need(output.Length+n<=limit); output.Write(buffer,0,n); } return output.ToArray(); } }
  public sealed class TransferSlotLease:IDisposable {
   readonly string root,rootId,fileId,sha,sid,boundHead,boundRun; readonly long size; readonly Stopwatch clock=Stopwatch.StartNew(); readonly DateTime created;
   readonly object gate=new object();
   Pins pins; SafeFileHandle incoming; FileStream metadata,claim; string metadataId,metadataHash,claimId,claimHash; bool disposed,consumed;
   internal TransferSlotLease(string r,string rid,string fid,string head,string run,string digest,long length,string operatorSid) {
    root=r; rootId=rid; fileId=fid; boundHead=head; boundRun=run; sha=digest; size=length; sid=operatorSid;
    try {
     pins=new Pins(root,sid); Need(Inspect(pins.Parent,root,true,true,sid)==rootId); Closure(false);
     incoming=Open(Path.Combine(root,"incoming.zip"),false,false); Need(Inspect(incoming,Path.Combine(root,"incoming.zip"),false,true,sid)==fileId);
     Info info; Need(GetFileInformationByHandle(incoming,out info) && info.SizeHigh==0 && info.SizeLow==0);
     SafeFileHandle mh=TransferReadHandle(Path.Combine(root,"slot.json"));
     try { metadata=new FileStream(mh,FileAccess.Read,8192,false); } catch { mh.Dispose(); throw; }
     metadataId=Inspect(mh,Path.Combine(root,"slot.json"),false,true,sid); byte[] raw=TransferRead(metadata,1048576); metadataHash=Hash(raw);
     var m=Obj(new Json(raw).Read(),"schema","profile","head","run_id","payload_sha256","size","operator_sid","created_utc");
     Need(Num(m["schema"])==1 && Str(m["profile"])=="PHYSICAL_SMOKE_S0_TRANSFER_SLOT" && Str(m["head"])==head && Str(m["run_id"])==run && Str(m["payload_sha256"])==sha && Num(m["size"])==size && Str(m["operator_sid"])==sid); CanonicalInput(raw,m);
     DateTime parsed; Need(DateTime.TryParseExact(Str(m["created_utc"]),"yyyy-MM-ddTHH:mm:ss.fffffffZ",System.Globalization.CultureInfo.InvariantCulture,System.Globalization.DateTimeStyles.AssumeUniversal|System.Globalization.DateTimeStyles.AdjustToUniversal,out parsed)); created=parsed;
     Fresh(); pins.Check(); Closure(false);
     Need(Inspect(pins.Parent,root,true,true,sid)==rootId && Inspect(incoming,Path.Combine(root,"incoming.zip"),false,true,sid)==fileId);
     byte[] claimBytes=Encoding.ASCII.GetBytes(InputJson(new Dictionary<string,object> {{"schema",1L},{"profile","PHYSICAL_SMOKE_S0_TRANSFER_LEASE"},{"head",head},{"run_id",run},{"root_id",rootId},{"file_id",fileId},{"payload_sha256",sha},{"size",size},{"metadata_sha256",metadataHash}}));
     // CREATE_NEW is the persisted one-shot claim; never delete, replace or repair it.
     using(var security=new Security(sid)) WriteMember(root,"lease.json",claimBytes,security,sid,new HashSet<string>(StringComparer.OrdinalIgnoreCase));
     SafeFileHandle ch=TransferReadHandle(Path.Combine(root,"lease.json"));
     try { claim=new FileStream(ch,FileAccess.Read,8192,false); } catch { ch.Dispose(); throw; }
     claimId=Inspect(ch,Path.Combine(root,"lease.json"),false,true,sid); claimHash=Hash(claimBytes);
     Need(Hash(TransferRead(claim,1048576))==claimHash);
     Stable();
    } catch { Dispose(); throw; }
   }
   void Closure(bool claimed) { Need(Directory.GetDirectories(root).Length==0); var actual=new HashSet<string>(Directory.GetFiles(root),StringComparer.OrdinalIgnoreCase); var expected=new HashSet<string>(StringComparer.OrdinalIgnoreCase) { Path.Combine(root,"incoming.zip"),Path.Combine(root,"slot.json") }; if(claimed) expected.Add(Path.Combine(root,"lease.json")); Need(actual.SetEquals(expected)); }
   void Fresh() { Need(!disposed && !consumed && clock.ElapsedMilliseconds<=300000); TimeSpan age=DateTime.UtcNow-created; Need(age.TotalSeconds>=0 && age.TotalSeconds<=300); }
   void Stable() {
    Fresh();
    pins.Check(); Need(Inspect(pins.Parent,root,true,true,sid)==rootId && Inspect(incoming,Path.Combine(root,"incoming.zip"),false,true,sid)==fileId && Inspect(metadata.SafeFileHandle,Path.Combine(root,"slot.json"),false,true,sid)==metadataId && Inspect(claim.SafeFileHandle,Path.Combine(root,"lease.json"),false,true,sid)==claimId); Closure(true);
    metadata.Position=0; Need(Hash(TransferRead(metadata,1048576))==metadataHash);
    claim.Position=0; Need(Hash(TransferRead(claim,1048576))==claimHash);
   }
   internal string BoundHead { get { return boundHead; } }
   internal string BoundRun { get { return boundRun; } }
   internal string BoundSid { get { return sid; } }
   internal string BoundSha { get { return sha; } }
   internal byte[] CaptureForImport() { lock(gate) { byte[] bytes=CaptureVerifiedCore(); consumed=true; return bytes; } }
   public TransferVerificationReceipt Verify() { CaptureVerified(); return new TransferVerificationReceipt { PayloadSha256=sha,Size=size }; }
   internal byte[] CaptureVerified() { lock(gate) { return CaptureVerifiedCore(); } }
   byte[] CaptureVerifiedCore() {
    TokenObserver.RequireStandard(sid); Stable(); byte[] captured;
    using(var data=TransferReadHandle(Path.Combine(root,"incoming.zip"))) {
     Need(Inspect(data,Path.Combine(root,"incoming.zip"),false,true,sid)==fileId);
     using(var input=new FileStream(data,FileAccess.Read,8192,false)) { captured=TransferRead(input,TransferLimit); Need(captured.LongLength==size && Hash(captured)==sha); Stable(); }
    }
    return captured;
   }
   public void Dispose() { lock(gate) { if(disposed) return; disposed=true; if(claim!=null) claim.Dispose(); if(metadata!=null) metadata.Dispose(); if(incoming!=null) incoming.Dispose(); if(pins!=null) pins.Dispose(); } }
  }
 }
}
