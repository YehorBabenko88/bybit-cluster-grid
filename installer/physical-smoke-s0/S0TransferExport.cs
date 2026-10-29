using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;
namespace GridS0 {
 public sealed class TransferExportReceipt {
  public BootstrapReceipt Materialization { get; internal set; }
  public string PayloadSha256 { get; internal set; }
  public long Size { get; internal set; }
  public bool S0Execute { get { return false; } }
  public bool G1Execute { get { return false; } }
  public bool Cleanup { get { return false; } }
 }
 public static partial class Bootstrap {
  public static TransferExportReceipt PlanTransferExport(string sourcePC4RoleRoot,string head,string run,string packageSha,string targetRoot,string sid) { return TransferExport(sourcePC4RoleRoot,head,run,packageSha,targetRoot,sid,false); }
  public static TransferExportReceipt StageTransferExport(string sourcePC4RoleRoot,string head,string run,string packageSha,string targetRoot,string sid,bool approved) { Need(approved); return TransferExport(sourcePC4RoleRoot,head,run,packageSha,targetRoot,sid,true); }
  static void ExportClosure(string root) {
   var expected=new HashSet<string>(StringComparer.Ordinal); foreach(string name in RoleFiles) expected.Add(Path.Combine(root,name));
   Need(expected.SetEquals(Directory.GetFiles(root))); string[] directories=Directory.GetDirectories(root); Need(directories.Length<=1);
   if(directories.Length==1) Need(directories[0]==Path.Combine(root,"temp") && Directory.GetFileSystemEntries(directories[0]).Length==0);
  }
  static TransferExportReceipt TransferExport(string source,string head,string run,string packageSha,string target,string sid,bool stage,ParentKind kind=ParentKind.LocalAppData) {
   using(var profile=kind==ParentKind.UserProfileV1?HoldUserProfileV1(sid):null) {
   TransferContext(head,run,packageSha,1,sid); TokenObserver.RequireStandard(sid);
   string local=profile!=null?profile.ParentPath:ParentPath(sid,kind);
   string pair=Path.Combine(local,"GridS0-"+run), expected=Path.Combine(pair,"PC4"); Need(source!=null && source==Path.GetFullPath(source) && String.Equals(source,expected,StringComparison.OrdinalIgnoreCase));
   using(var ancestry=new Pins(source,sid)) {
    string roleId=Inspect(ancestry.Parent,source,true,true,sid);
    using(var pairHandle=Open(pair,true,false)) {
     string pairId=Inspect(pairHandle,pair,true,true,sid); ExportClosure(source);
     var streams=new SortedDictionary<string,FileStream>(StringComparer.Ordinal); var identities=new Dictionary<string,string>(StringComparer.Ordinal);
     Microsoft.Win32.SafeHandles.SafeFileHandle temporary=null; string tempId=null;
     try {
      string temp=Path.Combine(source,"temp"); if(Directory.Exists(temp)) { temporary=Open(temp,true,false); tempId=Inspect(temporary,temp,true,true,sid); }
      var files=new SortedDictionary<string,byte[]>(StringComparer.Ordinal); long total=0;
      foreach(string name in RoleFiles) {
       string path=Path.Combine(source,name); var handle=TransferReadHandle(path); FileStream stream;
       try { stream=new FileStream(handle,FileAccess.Read,8192,false); } catch { handle.Dispose(); throw; }
       streams.Add(name,stream); identities.Add(name,Inspect(handle,path,false,true,sid)); byte[] bytes=TransferRead(stream,1048576); Need(bytes.Length>0); total+=bytes.LongLength; Need(total<=TransferLimit); files.Add(name,bytes);
      }
      var c=Obj(new Json(files["config.json"]).Read(),"schema","profile","plan","role","package_sha256","files");
      Need(Num(c["schema"])==1 && Str(c["profile"])=="PHYSICAL_SMOKE_S0" && Str(c["role"])=="PC4" && Str(c["package_sha256"])==packageSha);
      var plan=Obj(c["plan"]); ValidateInputPlan(plan,head,run); Need(Str(Obj(plan["operator_sids"],"LS5","PC4")["LS5"])==sid); CanonicalInput(files["config.json"],c);
      var pins=Obj(c["files"],"ca.pem","tls-cert.pem","peer-cert.pem","tls-key.pem"); foreach(var item in pins) { string digest=Str(item.Value); Need(Match(digest,"[0-9a-f]{64}") && Hash(files[item.Key])==digest); }
      var stop=Obj(new Json(files["stop.json"]).Read(),"head","run_id","role","stop"); Need(Str(stop["head"])==head && Str(stop["run_id"])==run && Str(stop["role"])=="PC4" && stop["stop"] is bool && !(bool)stop["stop"]); CanonicalInput(files["stop.json"],stop);
      byte[] payload; using(var output=new MemoryStream()) {
       using(var zip=new ZipArchive(output,ZipArchiveMode.Create,true)) foreach(var item in files) {
        var entry=zip.CreateEntry(item.Key,CompressionLevel.Optimal); entry.LastWriteTime=new DateTimeOffset(1980,1,1,0,0,0,TimeSpan.Zero); entry.ExternalAttributes=unchecked((int)0x81a40000u);
        using(var content=entry.Open()) content.Write(item.Value,0,item.Value.Length);
       }
       payload=output.ToArray(); Need(payload.LongLength>0 && payload.LongLength<=TransferLimit);
      }
      ancestry.Check(); Need(Inspect(ancestry.Parent,source,true,true,sid)==roleId && Inspect(pairHandle,pair,true,true,sid)==pairId); ExportClosure(source);
      if(temporary!=null) Need(Inspect(temporary,Path.Combine(source,"temp"),true,true,sid)==tempId);
      foreach(var item in streams) Need(Inspect(item.Value.SafeFileHandle,Path.Combine(source,item.Key),false,true,sid)==identities[item.Key]);
      if(profile!=null) profile.Check(); string sha=Hash(payload); var publication=new Package(); publication.Files.Add("pc4-role.zip",payload); publication.Bytes=payload.LongLength;
      var receipt=new TransferExportReceipt { Materialization=Publish(publication,null,sha,head,target,sid,"GridS0Input-",stage,kind),PayloadSha256=sha,Size=payload.LongLength };
      ancestry.Check(); ExportClosure(source); return receipt;
     } finally { foreach(var stream in streams.Values) stream.Dispose(); if(temporary!=null) temporary.Dispose(); }
    }
   }

   }
  }
 }
}
