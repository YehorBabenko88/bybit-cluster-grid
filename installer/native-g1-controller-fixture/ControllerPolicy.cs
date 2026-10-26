using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
internal record Permit(int Schema,string Head,string Run,string Attempt,string Nonce,long Expires,Identity Root,Identity Marker,Identity Journal,string ImageHash);
internal record SignedPermit(string Payload,string Signature);
internal static class ControllerPolicy {
 internal static void Need(bool b,string code="CONTROLLER_REFUSED"){if(!b)throw new Blocked(code);}
 internal static void ResourceBinding(object expected,object candidate){Need(ReferenceEquals(expected,candidate),"CLEANUP_RESOURCE_BINDING");}
 internal static string ChildEnvironment(string windows,string local){
  foreach(string path in new[]{windows,local})Need(path!=null&&path.Length<=2048&&Regex.IsMatch(path,@"^[A-Za-z]:\\")&&!path.Any(c=>c<32),"REQUIRED_CHILD_KNOWN_FOLDER");
  return "LOCALAPPDATA="+local+"\0SystemRoot="+windows+"\0WINDIR="+windows+"\0\0";
 }
 internal static void ChildToken(TokenFact facts,string user,uint maximumIntegrity=4096){
  Need(facts.User==user,"CHILD_TOKEN_USER");Need(!facts.Elevated,"CHILD_TOKEN_ELEVATED");Need(facts.Integrity<=maximumIntegrity,"CHILD_TOKEN_INTEGRITY_"+facts.Integrity);
  Need(!facts.Groups.Any(g=>g.Sid=="S-1-5-32-544"&&(g.Attributes&4)!=0&&(g.Attributes&16)==0),"CHILD_ENABLED_ADMINISTRATORS");
 }
 internal static void ImageObservation(bool queried,bool matches,bool exited,bool preverified){Need(queried?matches:(exited&&preverified),"IMAGE_IDENTITY_OR_UNVERIFIED_EXIT");}
 internal static byte[] Canon<T>(T x)=>JsonSerializer.SerializeToUtf8Bytes(x);
 internal static T Parse<T>(byte[] b){Need(b.Length>0&&b.Length<=16384);try{var x=JsonSerializer.Deserialize<T>(b,new JsonSerializerOptions{MaxDepth=8})!;Need(x!=null&&Canon(x).AsSpan().SequenceEqual(b));return x;}catch(JsonException){throw new Blocked("PARSE_REFUSED");}}
 internal static SignedPermit Sign(Permit p,RSA key)=>new(Convert.ToBase64String(Canon(p)),Convert.ToBase64String(key.SignData(Canon(p),HashAlgorithmName.SHA256,RSASignaturePadding.Pss)));
 internal static Permit Verify(byte[] wire,byte[] publicKey,byte[] pinned,Permit expected,HashSet<string> used,long now){
  Need(CryptographicOperations.FixedTimeEquals(SHA256.HashData(publicKey),pinned),"KEY_PIN");
  var s=Parse<SignedPermit>(wire);byte[] data,sig;try{data=Convert.FromBase64String(s.Payload);sig=Convert.FromBase64String(s.Signature);}catch(FormatException){throw new Blocked("BASE64_REFUSED");}
  Need(data.Length<=8192&&sig.Length==256,"SIGNATURE_SIZE");using var key=RSA.Create();key.ImportSubjectPublicKeyInfo(publicKey,out int read);Need(read==publicKey.Length&&key.KeySize==2048);Need(key.VerifyData(data,sig,HashAlgorithmName.SHA256,RSASignaturePadding.Pss),"SIGNATURE");
  var p=Parse<Permit>(data);Need(p==expected&&p.Schema==1&&Regex.IsMatch(p.Head,"^[0-9a-f]{40}$")&&Regex.IsMatch(p.Run,"^[1-9][0-9]{0,19}$")&&Regex.IsMatch(p.Attempt,"^[1-9][0-9]{0,9}$")&&Guid.TryParseExact(p.Nonce,"D",out _)&&Regex.IsMatch(p.ImageHash,"^[0-9A-F]{64}$"),"BINDING");Policy.Object(p.Root,true);Policy.Object(p.Marker,false);Policy.Object(p.Journal,false);Need(p.Root.Volume==p.Marker.Volume&&p.Root.Volume==p.Journal.Volume&&p.Root.FileId!=p.Marker.FileId&&p.Marker.FileId!=p.Journal.FileId&&p.Root.FileId!=p.Journal.FileId);Need(p.Expires>now&&p.Expires<=now+300,"EXPIRED");Need(used.Add(p.Nonce),"REPLAY");return p;
 }
 internal static bool Transition(string? a,string b)=> (a,b) is (null,"PREPARED") or ("PREPARED","RESUME_INTENT") or ("RESUME_INTENT","EXITED") or ("EXITED","CLEANUP_INTENT") or ("CLEANUP_INTENT","MARKER_DELETE_PENDING");
}
internal sealed class Guardian {
 internal string Anchor{get;private set;}="";internal string? Phase{get;private set;}
 OwnedChild? boundChild;bool faulted;readonly OwnedFixture fixture;readonly Permit permit;internal Guardian(OwnedFixture f,Permit p){fixture=f;permit=p;}
 internal void Append(string phase,bool fail=false){ControllerPolicy.Need(phase!="MARKER_DELETE_PENDING");Guard();WritePhase(phase,fail);}
 internal void CompleteMarkerDisposition(bool fail=false){ControllerPolicy.Need(Phase=="CLEANUP_INTENT");PendingGuard();WritePhase("MARKER_DELETE_PENDING",fail);}
 void PendingGuard(){ControllerPolicy.Need(permit.Expires>DateTimeOffset.UtcNow.ToUnixTimeSeconds(),"PERMIT_EXPIRED");ControllerPolicy.Need(fixture.Binding.Target==permit.Marker&&Native.Id(fixture.Root)==permit.Root&&Native.Id(fixture.Journal)==permit.Journal);fixture.GuardMarkerDeletePending();}
 internal void RecoverMarkerDeletePending(){ControllerPolicy.Need(!faulted&&Phase=="MARKER_DELETE_PENDING");PendingGuard();Validate(FixtureNative.Read(fixture.Journal),Anchor);}
 void WritePhase(string phase,bool fail){ControllerPolicy.Need(!faulted&&ControllerPolicy.Transition(Phase,phase));string previous=Anchor;byte[] body=ControllerPolicy.Canon(new{permit,phase,previous});string digest=Convert.ToHexString(SHA256.HashData(body));byte[] line=ControllerPolicy.Canon(new{permit,phase,previous,digest}).Concat(new byte[]{10}).ToArray();try{FixtureNative.AppendFlush(fixture.Journal,line,fail);}catch{faulted=true;throw;}Anchor=digest;Phase=phase;}
 internal void Guard(){ControllerPolicy.Need(permit.Expires>DateTimeOffset.UtcNow.ToUnixTimeSeconds(),"PERMIT_EXPIRED");fixture.Guard(fixture.Old);ControllerPolicy.Need(Native.Id(fixture.Root)==permit.Root&&Native.Id(fixture.Target)==permit.Marker&&Native.Id(fixture.Journal)==permit.Journal);}
 internal OwnedChild CreateChild(byte[] payload,string hash,string sid){Guard();ControllerPolicy.Need(!faulted&&Phase=="PREPARED"&&boundChild==null&&hash==permit.ImageHash,"CHILD_AUTHORIZATION_BINDING");var owned=new OwnedChild(payload,hash,sid);try{Guard();boundChild=owned;return owned;}catch{owned.Dispose();throw;}}
 internal void RequireChild(OwnedChild candidate){ControllerPolicy.Need(boundChild!=null,"MISSING_BOUND_CHILD");ControllerPolicy.ResourceBinding(boundChild!,candidate);}
 internal void RequireFixture(OwnedFixture candidate){ControllerPolicy.ResourceBinding(fixture,candidate);Guard();}
 internal void Recover(){ControllerPolicy.Need(!faulted);Guard();Validate(FixtureNative.Read(fixture.Journal),Anchor);}
 internal static void Validate(byte[] bytes,string anchor){ControllerPolicy.Need(bytes.Length>0&&bytes.Length<=65536&&bytes[^1]==10&&Regex.IsMatch(anchor,"^[0-9A-F]{64}$"));int count=0;string previous="";string? phase=null;Permit? binding=null;foreach(var line in new UTF8Encoding(false,true).GetString(bytes).Split('\n')[..^1]){ControllerPolicy.Need(++count<=5);using var d=JsonDocument.Parse(line,new JsonDocumentOptions{MaxDepth=8});var e=d.RootElement;ControllerPolicy.Need(e.EnumerateObject().Select(x=>x.Name).SequenceEqual(new[]{"permit","phase","previous","digest"}));var p=ControllerPolicy.Parse<Permit>(Encoding.UTF8.GetBytes(e.GetProperty("permit").GetRawText()));string next=e.GetProperty("phase").GetString()!,prev=e.GetProperty("previous").GetString()!,hash=e.GetProperty("digest").GetString()!;ControllerPolicy.Need((binding==null||binding==p)&&prev==previous&&ControllerPolicy.Transition(phase,next));ControllerPolicy.Need(hash==Convert.ToHexString(SHA256.HashData(ControllerPolicy.Canon(new{permit=p,phase=next,previous=prev}))));ControllerPolicy.Need(Encoding.UTF8.GetString(ControllerPolicy.Canon(new{permit=p,phase=next,previous=prev,digest=hash}))==line);binding=p;phase=next;previous=hash;}ControllerPolicy.Need(previous==anchor);}
}


