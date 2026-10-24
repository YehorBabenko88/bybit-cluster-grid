#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
internal record TxBinding(int Schema,string Head,string Run,string Attempt,string Id,Identity Root,Identity Target,string Old,string New);
internal record TxRecord(TxBinding Binding,int Sequence,string Phase,string Previous,string Digest);
// Test-only corruption detector. Neither hash chaining nor an in-memory anchor authenticates custody.
internal static class JournalModel
{
 static readonly string[] Phases={"PREPARED","INTENT","APPLIED","VERIFIED","COMMITTED"};
 static void Need(bool ok){if(!ok)throw new Blocked("FIXTURE_JOURNAL_BLOCKED");}
 static string Hash(TxBinding b,int s,string p,string prev)=>Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(new{Binding=b,Sequence=s,Phase=p,Previous=prev})));
 static void Binding(TxBinding b){
  Need(b.Schema==1 && Regex.IsMatch(b.Head,"^[0-9a-f]{40}$") && Regex.IsMatch(b.Run,"^[1-9][0-9]{0,19}$") && Regex.IsMatch(b.Attempt,"^[1-9][0-9]{0,9}$") && Guid.TryParseExact(b.Id,"D",out _));
  Policy.Object(b.Root,true);Policy.Object(b.Target,false);
  Need(b.Root.Volume==b.Target.Volume && b.Root.FileId!=b.Target.FileId && (b.Target.Attributes&0x10)==0 && b.Old!=b.New);
  foreach(string sd in new[]{b.Old,b.New}){Need(sd.Length>0 && sd.Length<131072);try{Need(Convert.FromBase64String(sd).Length>0);}catch(FormatException){throw new Blocked("FIXTURE_DESCRIPTOR_ENCODING");}}
 }
 public static List<TxRecord> Append(List<TxRecord> rows,TxBinding b,string phase){
  Binding(b);Need(rows.Count<7 && Transition(rows.Count==0?null:rows[^1].Phase,phase));
  if(rows.Count!=0)Validate(rows,b,rows[^1].Digest);
  string prev=rows.Count==0?new string('0',64):rows[^1].Digest;
  var result=new List<TxRecord>(rows){new(b,rows.Count,phase,prev,Hash(b,rows.Count,phase,prev))};return result;
 }
 public static void Validate(List<TxRecord> rows,TxBinding expected,string anchor){
  Binding(expected);Need(rows.Count>0 && rows.Count<=7 && Regex.IsMatch(anchor,"^[0-9A-F]{64}$"));
  string prev=new('0',64);
  for(int n=0;n<rows.Count;n++){var r=rows[n];Need(r.Binding==expected && r.Sequence==n && Transition(n==0?null:rows[n-1].Phase,r.Phase) && r.Previous==prev && r.Digest==Hash(expected,n,r.Phase,prev));prev=r.Digest;}
  Need(prev==anchor);
 }
 static bool Transition(string? previous,string next){
  if(previous==null)return next=="PREPARED";
  if(next=="RESTORE_INTENT")return previous is "INTENT" or "APPLIED" or "VERIFIED" or "COMMITTED";
  if(previous=="RESTORE_INTENT")return next=="RESTORED";
  int p=Array.IndexOf(Phases,previous);return p>=0 && p<Phases.Length-1 && Phases[p+1]==next;
 }
 public static string Classify(List<TxRecord> rows,TxBinding expected,string current){
  Validate(rows,expected,rows.Count>0?rows[^1].Digest:"");
  if(current==expected.Old && rows[^1].Phase is "PREPARED" or "INTENT" or "RESTORE_INTENT" or "RESTORED")return "UNCHANGED";
  if(rows.Count>=2 && rows[^1].Phase!="RESTORED" && current==expected.New)return "RESTORE_REQUIRES_FIXTURE_APPROVAL";
  throw new Blocked("FIXTURE_RECOVERY_DIVERGED");
 }
 public static byte[] Encode(List<TxRecord> rows)=>Encoding.UTF8.GetBytes(string.Concat(rows.Select(r=>JsonSerializer.Serialize(r)+"\n")));
 static void Unique(JsonElement e){
  if(e.ValueKind==JsonValueKind.Object){var keys=new HashSet<string>();foreach(var p in e.EnumerateObject()){Need(keys.Add(p.Name));Unique(p.Value);}}
  else if(e.ValueKind==JsonValueKind.Array)foreach(var v in e.EnumerateArray())Unique(v);
 }
 public static List<TxRecord> Parse(byte[] bytes){
  Need(bytes.Length>0 && bytes.Length<=262144 && bytes[^1]==10);
  try{
   string text=new UTF8Encoding(false,true).GetString(bytes);Need(!text.Contains('\r'));
   var result=new List<TxRecord>();
   foreach(var line in text.Split('\n')[..^1]){
    using var doc=JsonDocument.Parse(line,new JsonDocumentOptions{MaxDepth=16});Unique(doc.RootElement);
    var r=JsonSerializer.Deserialize<TxRecord>(line)??throw new Blocked("FIXTURE_JOURNAL_NULL");
    // Exact reserialization also rejects unknown keys, absent fields, alternate number forms and duplicate keys.
    Need(JsonSerializer.Serialize(r)==line);result.Add(r);
   }Need(result.Count>0 && result.Count<=7);return result;
  }catch(Exception e)when(e is JsonException or DecoderFallbackException or ArgumentException or NullReferenceException){throw new Blocked("FIXTURE_JOURNAL_PARSE");}
 }
}
