using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Security.Principal;
using System.Text;
namespace GridS0 {
 public static partial class Bootstrap {
  static readonly string[] RoleFiles={"ca.pem","tls-cert.pem","peer-cert.pem","tls-key.pem","config.json","stop.json"};
  public static BootstrapReceipt PlanInput(byte[] canonicalPlan,string expectedSha,string expectedHead,string expectedRunId,string targetRoot,string expectedSid) { return Input(canonicalPlan,expectedSha,expectedHead,expectedRunId,targetRoot,expectedSid,false); }
  public static BootstrapReceipt StagePlanInput(byte[] canonicalPlan,string expectedSha,string expectedHead,string expectedRunId,string targetRoot,string expectedSid,bool approved) { Need(approved); return Input(canonicalPlan,expectedSha,expectedHead,expectedRunId,targetRoot,expectedSid,true); }
  static BootstrapReceipt Input(byte[] raw,string sha,string head,string run,string target,string sid,bool stage,ParentKind kind=ParentKind.LocalAppData) {
   byte[] captured=CaptureInput(raw,sha,1048576); var plan=Obj(new Json(captured).Read()); ValidateInputPlan(plan,head,run);
   Need(Str(Obj(plan["operator_sids"],"LS5","PC4")["LS5"])==sid); CanonicalInput(captured,plan);
   var p=new Package(); p.Files.Add("s0-plan.json",captured); p.Bytes=captured.LongLength;
   return Publish(p,null,sha,head,target,sid,"GridS0Input-",stage,kind);
  }
  public static BootstrapReceipt PlanRoleImport(byte[] sixFileZip,string expectedSha,string expectedHead,string expectedRunId,string expectedPackageSha,string targetRoot,string expectedSid) { return ImportRole(sixFileZip,expectedSha,expectedHead,expectedRunId,expectedPackageSha,targetRoot,expectedSid,false); }
  public static BootstrapReceipt StageRoleImport(byte[] sixFileZip,string expectedSha,string expectedHead,string expectedRunId,string expectedPackageSha,string targetRoot,string expectedSid,bool approved) { Need(approved); return ImportRole(sixFileZip,expectedSha,expectedHead,expectedRunId,expectedPackageSha,targetRoot,expectedSid,true); }
  static BootstrapReceipt ImportRole(byte[] raw,string sha,string head,string run,string packageSha,string target,string sid,bool stage,ParentKind kind=ParentKind.LocalAppData) {
   byte[] captured=CaptureInput(raw,sha,6291456); Need(Match(packageSha,"[0-9a-f]{64}")); var p=new Package();
   using(var memory=new MemoryStream(captured,false)) using(var zip=new ZipArchive(memory,ZipArchiveMode.Read,false)) {
    Need(zip.Entries.Count==6); var seen=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
    foreach(var e in zip.Entries) {
     Need(Array.IndexOf(RoleFiles,e.FullName)>=0 && seen.Add(e.FullName) && e.Length>0 && e.Length<=1048576);
     uint attributes=(uint)e.ExternalAttributes, mode=attributes>>16; Need((attributes&0x410)==0 && ((mode&0xf000)==0 || (mode&0xf000)==0x8000));
     using(var input=e.Open()) using(var output=new MemoryStream()) { byte[] buffer=new byte[8192]; int read; long count=0; while((read=input.Read(buffer,0,buffer.Length))!=0) { count+=read; Need(count<=e.Length); output.Write(buffer,0,read); } Need(count==e.Length); p.Files.Add(e.FullName,output.ToArray()); p.Bytes+=count; }
    }
   }
   var c=Obj(new Json(p.Files["config.json"]).Read(),"schema","profile","plan","role","package_sha256","files");
   Need(Num(c["schema"])==1 && Str(c["profile"])=="PHYSICAL_SMOKE_S0" && Str(c["role"])=="PC4" && Str(c["package_sha256"])==packageSha);
   var plan=Obj(c["plan"]); ValidateInputPlan(plan,head,run); Need(Str(Obj(plan["operator_sids"],"LS5","PC4")["PC4"])==sid);
   var pins=Obj(c["files"],"ca.pem","tls-cert.pem","peer-cert.pem","tls-key.pem"); foreach(var item in pins) { string digest=Str(item.Value); Need(Match(digest,"[0-9a-f]{64}") && Hash(p.Files[item.Key])==digest); }
   CanonicalInput(p.Files["config.json"],c);
   var stop=Obj(new Json(p.Files["stop.json"]).Read(),"head","run_id","role","stop"); Need(Str(stop["head"])==head && Str(stop["run_id"])==run && Str(stop["role"])=="PC4" && stop["stop"] is bool && !(bool)stop["stop"]); CanonicalInput(p.Files["stop.json"],stop);
   // The archive is flat for transport, but cli.prepare consumes InputRoot/PC4/config.json.
   // Prefix only after every archive member, config pin and stop record is validated.
   var publication=new Package();
   foreach(var item in p.Files) publication.Files.Add("PC4/"+item.Key,item.Value);
   publication.Bytes=p.Bytes;
   // TLS semantic validation remains the Python prepare/runtime gate; import grants no execution.
   return Publish(publication,null,sha,head,target,sid,"GridS0Input-",stage,kind);
  }
  static byte[] CaptureInput(byte[] raw,string sha,int limit) { Need(raw!=null && raw.Length>0 && raw.Length<=limit && Match(sha,"[0-9a-f]{64}")); byte[] copy=(byte[])raw.Clone(); Need(Hash(copy)==sha); return copy; }
  static void ValidateInputPlan(Dictionary<string,object> p,string head,string run) {
   Obj(p,"schema","profile","head","run_id","duration_seconds","symbol","bybit_url","coordinator_ip","worker_ip","port","operator_sids","hostnames");
   Need(Num(p["schema"])==1 && Str(p["profile"])=="PHYSICAL_SMOKE_S0" && Match(head,"[0-9a-f]{40}") && Str(p["head"])==head);
   Need(Match(run,"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}") && Str(p["run_id"])==run);
   Need(Num(p["duration_seconds"])==300 && Str(p["symbol"])=="BTCUSDT" && Str(p["bybit_url"])=="wss://stream.bybit.com/v5/public/linear");
   InputIP(Str(p["coordinator_ip"])); InputIP(Str(p["worker_ip"])); Need(Str(p["coordinator_ip"])!=Str(p["worker_ip"])); long port=Num(p["port"]); Need(port>=49152 && port<=65535 && port!=55432 && port!=55433);
   var names=Obj(p["hostnames"],"LS5","PC4"); foreach(object v in names.Values) Need(Match(Str(v),"[A-Z0-9](?:[A-Z0-9-]{0,13}[A-Z0-9])?")); Need(Str(names["LS5"])!=Str(names["PC4"]));
   var ids=Obj(p["operator_sids"],"LS5","PC4"); foreach(object v in ids.Values) { string value=Str(v); Need(value.Length<=200 && Match(value,"S-1-5-21(?:-(?:0|[1-9][0-9]{0,9})){4}")); foreach(string n in value.Substring(9).Split('-')) { uint parsed; Need(UInt32.TryParse(n,out parsed)); } } Need(Str(ids["LS5"])!=Str(ids["PC4"]));
  }
  static void InputIP(string value) { Need(Match(value,"[0-9]{1,3}(?:\\.[0-9]{1,3}){3}")); var pieces=value.Split('.'); byte[] parts=new byte[4]; for(int i=0;i<4;i++) { Need((pieces[i].Length==1 || pieces[i][0]!='0') && Byte.TryParse(pieces[i],out parts[i])); } Need(parts[0]==10 || parts[0]==100 && parts[1]>=64 && parts[1]<=127 || parts[0]==172 && parts[1]>=16 && parts[1]<=31 || parts[0]==192 && parts[1]==168); }
  static void CanonicalInput(byte[] raw,object value) { Need(Encoding.UTF8.GetString(raw)==InputJson(value)); }
  static string InputJson(object value) {
   var d=value as Dictionary<string,object>; if(d!=null) { var keys=new List<string>(d.Keys); keys.Sort(StringComparer.Ordinal); var pieces=new List<string>(); foreach(string key in keys) pieces.Add(InputJson(key)+":"+InputJson(d[key])); return "{"+String.Join(",",pieces.ToArray())+"}"; }
   if(value is long) return ((long)value).ToString(System.Globalization.CultureInfo.InvariantCulture); if(value is bool) return (bool)value?"true":"false";
   Need(value is string); var result=new StringBuilder("\""); foreach(char c in (string)value) { if(c=='"') result.Append("\\\""); else if(c=='\\') result.Append("\\\\"); else if(c=='\b') result.Append("\\b"); else if(c=='\f') result.Append("\\f"); else if(c=='\n') result.Append("\\n"); else if(c=='\r') result.Append("\\r"); else if(c=='\t') result.Append("\\t"); else if(c<32 || c>126) result.Append("\\u"+((int)c).ToString("x4")); else result.Append(c); } return result.Append('"').ToString();
  }
 }
}
