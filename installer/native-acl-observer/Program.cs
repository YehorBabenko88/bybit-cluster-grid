#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.IO;
// Read-only observation; never host attestation or mutation authority.
using System.Text.Json;
using Microsoft.Win32.SafeHandles;
internal static class Program
{
 internal static readonly JsonSerializerOptions Json=new(){PropertyNamingPolicy=JsonNamingPolicy.CamelCase};
 static int Main(string[] args)
 {
  if(args.Length==1 && args[0]=="--self-test")return PolicyTests.Run();
  var handles=new List<SafeFileHandle>();
  try {
   bool injected=args.Length==3 && args[0]=="--test-fault";
   if(injected){if(!new[]{"TOKEN_OPEN","TOKEN_QUERY","IDENTITY","DESCRIPTOR","ACCESS_CHECK","PRIVILEGE"}.Contains(args[1]))throw new Blocked("FAULT_UNKNOWN");Native.Fault=args[1];}
   bool session=args.Length==2 && args[0]=="--session";
   if(!OperatingSystem.IsWindows() || !(args.Length==1 || session || injected))throw new Blocked("ARGUMENT_OR_PLATFORM");
   var components=Policy.Components(args[injected?2:(session?1:0)]);
   using var token=Native.CaptureToken();var facts=Native.TokenFacts(token);var rows=new List<Observation>();
   for(int i=0;i<components.Length;i++){
    var h=i==0?Native.OpenRoot(components[0]):Native.OpenChild(handles[^1],components[i],i<components.Length-1);handles.Add(h);
    var row=Native.Observe(h,token,i);Policy.Object(row.Identity,i<components.Length-1);
    if(rows.Count>0 && row.Identity.Volume!=rows[0].Identity.Volume)throw new Blocked("VOLUME_CHANGED");
    rows.Add(row);
   }
   if(session){
    Console.WriteLine(JsonSerializer.Serialize(new{schema=1,fault_injection=Native.Fault!=null,status="BLOCKED",observation="HELD",host_verified=false,
     physical_attestation=false,apply_authorized=false,execute_authorized=false,cleanup_authorized=false,
     effectiveRightsStatus="BLOCKED_MIC_ALL_PRINCIPALS_AND_PRIVILEGES_NOT_PROVEN",chain=rows,token=facts},Json));Console.Out.Flush();
    // Console.In does not consistently decode redirected stream preambles across shells.
    using var input=new StreamReader(Console.OpenStandardInput(),new System.Text.UTF8Encoding(false,true),true,128,true);
    var line=input.ReadLineAsync();if(!line.Wait(TimeSpan.FromSeconds(20)))throw new Blocked("SESSION_COMMAND_TIMEOUT");
    if(input.CurrentEncoding.CodePage!=65001)throw new Blocked("SESSION_ENCODING");
    Policy.SessionCommand(line.Result);
   }
   // Reobserve original handles, never resolve the pathname again.
   for(int i=0;i<rows.Count;i++)Policy.Unchanged(rows[i],Native.Observe(handles[i],token,i));
   if(facts.Fingerprint!=Native.TokenFacts(token).Fingerprint)throw new Blocked("TOKEN_CHANGED");
   Console.WriteLine(JsonSerializer.Serialize(new {schema=1,fault_injection=Native.Fault!=null,status="BLOCKED",observation="OBSERVED",host_verified=false,
    physical_attestation=false,apply_authorized=false,execute_authorized=false,cleanup_authorized=false,
    reason="ALL_PRINCIPALS_WRITERS_AND_BOOTSTRAP_NOT_PROVEN",effectiveRightsStatus="BLOCKED_MIC_ALL_PRINCIPALS_AND_PRIVILEGES_NOT_PROVEN",token=facts,chain=rows},Json));
   return 0;
  }catch(Exception e)when(e is Blocked or System.ComponentModel.Win32Exception or IOException or UnauthorizedAccessException or
    ArgumentException or NotSupportedException or OverflowException or System.Security.SecurityException){
   Console.WriteLine(JsonSerializer.Serialize(new {schema=1,fault_injection=Native.Fault!=null,status="BLOCKED",observation="REJECTED",host_verified=false,
    physical_attestation=false,apply_authorized=false,execute_authorized=false,cleanup_authorized=false,
    native_error=e is Blocked error?error.NativeError:null,reason=e is Blocked b?b.Code:"NATIVE_API_OR_STRUCTURE_FAILURE"},Json));return 2;
  }finally{for(int i=handles.Count-1;i>=0;i--)handles[i].Dispose();}
 }
}
internal sealed class Blocked(string code,int? nativeError=null):Exception(code){public string Code{get;}=code;public int? NativeError{get;}=nativeError;}
internal record Identity(ulong Volume,string FileId,uint Links,uint Attributes);
internal record AceFact(string Sid,int Mask,int Flags,string Type);
internal record Observation(int Depth,Identity Identity,string Owner,string Group,string DescriptorSha256,bool Protected,List<AceFact> Aces,Dictionary<string,string> EffectiveRights);
internal record GroupFact(string Sid,uint Attributes);
internal record TokenFact(string User,bool Elevated,uint Integrity,List<GroupFact> Groups,string Fingerprint);
internal static class Policy
{
 // Data/list-directory read access is needed for Windows sharing accounting;
 // attribute/control-only handles do not exclude DELETE opens. No data is read.
 public const uint ShareReadAccess=0x120081;
 public static void SessionCommand(string? value){
  if(value==null)throw new Blocked("SESSION_INPUT_EOF");
  if(value!="recheck")throw new Blocked("SESSION_COMMAND_INVALID");
 }

 public static void ScalarProbe(bool success,int error,int size){
  if(success || size!=4 || (error!=122 && error!=24))throw new Blocked("TOKEN_SCALAR_PROBE",error);
 }
 public static bool ScalarElevation(uint value){
  if(value>1)throw new Blocked("TOKEN_SCALAR_VALUE");return value==1;
 }

 public static string[] Components(string path){
  if(path.Length<4 || path.Length>240 || path[0]<'A' || path[0]>'Z' || path[1]!=':' || path[2]!='\\')throw new Blocked("PATH_FORM");
  if(path.Any(c=>c<32 || c>126 || "/%~*?\"<>|".Contains(c)) || path[3..].Contains(':'))throw new Blocked("PATH_ALIAS");
  var parts=path[3..].Split('\\');
  foreach(var p in parts){var stem=p.Split('.')[0].ToUpperInvariant();
   if(p.Length==0 || p=="." || p==".." || p.EndsWith(' ') || p.EndsWith('.') || new[]{"CON","PRN","AUX","NUL","CONIN$","CONOUT$"}.Contains(stem) ||
    (stem.Length==4 && (stem.StartsWith("COM") || stem.StartsWith("LPT")) && stem[3]>='1' && stem[3]<='9'))throw new Blocked("PATH_ALIAS");
  }return new[]{path[..3]}.Concat(parts).ToArray();
 }
 public static void Object(Identity id,bool parent){
  if((id.Attributes&0x400)!=0)throw new Blocked("REPARSE");
  if(id.Volume==0 || id.Links==0 || !System.Text.RegularExpressions.Regex.IsMatch(id.FileId,"^[0-9A-F]{32}$") || id.FileId.All(c=>c=='0'))throw new Blocked("IDENTITY_UNKNOWN");
  if(parent && (id.Attributes&0x10)==0)throw new Blocked("PARENT_NOT_DIRECTORY");
  if((id.Attributes&0x10)==0 && id.Links!=1)throw new Blocked("HARDLINK");
 }
 public static void Unchanged(Observation a,Observation b){
  if(a.Identity!=b.Identity || a.DescriptorSha256!=b.DescriptorSha256 || !a.EffectiveRights.OrderBy(x=>x.Key).SequenceEqual(b.EffectiveRights.OrderBy(x=>x.Key)))throw new Blocked("OBSERVATION_CHANGED");
 }
 public static void RootMapping(string mapping,string finalName){
  if(!System.Text.RegularExpressions.Regex.IsMatch(mapping,@"^\\Device\\HarddiskVolume[0-9]+$") ||
    !string.Equals(finalName,mapping+"\\",StringComparison.OrdinalIgnoreCase))throw new Blocked("ROOT_MAPPING_UNPROVEN");
 }
 public static void GroupLayout(int count,int size,int pointerSize){
  int offset=pointerSize==8?8:4;int stride=pointerSize==8?16:8;
  if((pointerSize!=4 && pointerSize!=8) || count<0 || count>4096 || size<4 || offset+(long)count*stride>size)throw new Blocked("TOKEN_GROUP_STRUCTURE");
 }
 public static void SidBounds(long delta,int size,int minimum,int count){
  if(delta<minimum || delta>size-8 || count<0 || count>15 || delta+8+4L*count>size)throw new Blocked("TOKEN_SID_BOUNDS");
 }
 // Evidence flags only; permission evaluation belongs to native AccessCheck.
 public static void GroupFlags(uint flags){if((flags&~0xE000007Fu)!=0 || ((flags&0x10)!=0 && (flags&4)!=0))throw new Blocked("GROUP_FLAGS_INVALID");}
}
