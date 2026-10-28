using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Win32.SafeHandles;

namespace GridS0 {
 public sealed class BootstrapReceipt {
  public string Head { get; internal set; }
  public string Sha256 { get; internal set; }
  public int FileCount { get; internal set; }
  public long Bytes { get; internal set; }
  public string ParentIdentity { get; internal set; }
  public string RootIdentity { get; internal set; }
  public string Status { get; internal set; }
  public bool S0Execute { get { return false; } }
  public bool G1Execute { get { return false; } }
  public bool Cleanup { get { return false; } }
 }
 // No command line entry point: callers must explicitly select StagePackage and approve.
 public static partial class Bootstrap {
  const long MaxZip=536870912, MaxFile=67108864;
  const uint Full=0x1f01ff, Dangerous=0x40|0x10000|0x40000|0x80000|0x10000000|0x40000000;
  const string SystemSid="S-1-5-18", AdminSid="S-1-5-32-544";
  const string Ti="S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464";
  static void Need(bool ok) { if(!ok) throw new InvalidOperationException("S0_BOOTSTRAP_BLOCKED"); }
  static bool Match(string s,string p) { return s!=null && Regex.IsMatch(s,"\\A(?:"+p+")\\z",RegexOptions.CultureInvariant); }
  static string Hash(byte[] b) { using(var h=SHA256.Create()) return BitConverter.ToString(h.ComputeHash(b)).Replace("-","").ToLowerInvariant(); }
  sealed class Package { internal SortedDictionary<string,byte[]> Files=new SortedDictionary<string,byte[]>(StringComparer.Ordinal); internal long Bytes; }
  static void Name(string n) {
   Need(n!=null && n.Length>0 && n.Length<=512 && n.IndexOf('\\')<0);
   foreach(string p in n.Split('/')) {
    Need(p.Length>0 && p!="." && p!=".." && p.TrimEnd(' ','.')==p);
    foreach(char c in p) Need(c>=32 && c<127 && ":<>\"|?*".IndexOf(c)<0);
    Need(!Match(p.Split('.')[0].ToUpperInvariant(),"CON|PRN|AUX|NUL|CONIN\\$|CONOUT\\$|COM[0-9]|LPT[0-9]"));
    Need(!Match(p.ToLowerInvariant(),"grid|asyncpg|psycopg|dotenv|pybit|ccxt|telegram"));
   }
  }
  static Dictionary<string,object> Obj(object x, params string[] fields) {
   var d=x as Dictionary<string,object>; Need(d!=null);
   if(fields.Length>0) { Need(d.Count==fields.Length); foreach(string f in fields) Need(d.ContainsKey(f)); }
   return d;
  }
  static string Str(object x) { Need(x is string); return (string)x; }
  static long Num(object x) { Need(x is long); return (long)x; }
  static bool IsSource(string name) {
   return Match(name,"s0_smoke/[A-Za-z_][A-Za-z_0-9]*\\.py") ||
    name=="installer/physical-smoke-s0.ps1" || name=="installer/physical-smoke-s0-bootstrap.ps1" ||
    name=="docs/PHYSICAL_SMOKE_S0.md" || name=="docs/PHYSICAL_SMOKE_S0_BOOTSTRAP_COMMANDS.md" || name=="docs/PHYSICAL_SMOKE_S0_INDEPENDENT_ACCEPTANCE.md" ||
    name=="installer/physical-smoke-s0/S0Launcher.cs" || name=="installer/physical-smoke-s0/S0Bootstrap.cs" || name=="installer/physical-smoke-s0/TokenObserver.cs" || name=="installer/physical-smoke-s0/S0Inputs.cs";
  }
  static Package Validate(byte[] zip,string sha,string head) {
   Need(zip!=null && zip.LongLength>0 && zip.LongLength<=MaxZip && Match(sha,"[0-9a-f]{64}") && Match(head,"[0-9a-f]{40}"));
   Need(Hash(zip)==sha); var p=new Package(); var seen=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
   using(var ms=new MemoryStream(zip,false)) using(var z=new ZipArchive(ms,ZipArchiveMode.Read,false)) {
    Need(z.Entries.Count>=6 && z.Entries.Count<=20001);
    foreach(var e in z.Entries) {
     Name(e.FullName); Need(seen.Add(e.FullName));
     uint mode=((uint)e.ExternalAttributes)>>16; Need((mode&0xf000)==0 || (mode&0xf000)==0x8000);
     Need((((uint)e.ExternalAttributes)&0x410)==0); // neither DOS directory nor reparse
     long limit=e.FullName=="s0-package.json"?1048576:MaxFile;
     Need(e.Length>=0 && e.Length<=limit); p.Bytes+=e.Length; Need(p.Bytes<=MaxZip);
     using(var input=e.Open()) using(var output=new MemoryStream()) {
      byte[] buffer=new byte[65536]; int read; long count=0;
      while((read=input.Read(buffer,0,buffer.Length))!=0) { count+=read; Need(count<=e.Length && count<=limit); output.Write(buffer,0,read); }
      Need(count==e.Length); p.Files.Add(e.FullName,output.ToArray());
     }
    }
   }
   Need(p.Files.ContainsKey("s0-package.json") && !p.Files.ContainsKey("source.zip"));
   var m=Obj(new Json(p.Files["s0-package.json"]).Read(),"schema","profile","head","tree","run_id","attempt","python","authority","files","source");
   Need(Num(m["schema"])==1 && Str(m["profile"])=="PHYSICAL_SMOKE_S0" && Str(m["head"])==head);
   Need(Match(Str(m["tree"]),"[0-9a-f]{40}") && Match(Str(m["python"]),"3\\.12\\.(?:0|[1-9][0-9]{0,2})"));
   foreach(string f in new[]{"run_id","attempt"}) Need(Match(Str(m[f]),"[1-9][0-9]{0,19}"));
   var authority=Obj(m["authority"],"s0_execute","g1_execute","cleanup"); foreach(object v in authority.Values) Need(v is bool && !(bool)v);
   var files=Obj(m["files"]); Need(files.Count>=5 && files.Count<=20000 && p.Files.Count==files.Count+1);
   foreach(var item in files) {
    Name(item.Key); var pin=Obj(item.Value,"sha256","size"); long size=Num(pin["size"]); string digest=Str(pin["sha256"]);
    Need(size>=0 && size<=MaxFile && Match(digest,"[0-9a-f]{64}") && p.Files.ContainsKey(item.Key));
    byte[] b=p.Files[item.Key]; Need(b.LongLength==size && Hash(b)==digest);
   }
   foreach(string f in new[]{"runtime/python.exe","runtime/python._pth","runtime/python312._pth","runtime/App/s0.py","runtime/stdlib.zip"}) Need(files.ContainsKey(f));
   foreach(string f in new[]{"runtime/python._pth","runtime/python312._pth"}) Need(Convert.ToBase64String(p.Files[f])==Convert.ToBase64String(Encoding.ASCII.GetBytes("stdlib.zip\nDLLs\nSite\nApp\n")));
   var source=Obj(m["source"]); Need(source.Count>0 && source.Count<=20000);
   foreach(var item in source) {
    string n=item.Key; Need(IsSource(n));
    string f=n.StartsWith("s0_smoke/",StringComparison.Ordinal)?"runtime/App/"+n:n;
    string digest=Str(item.Value); Need(Match(digest,"[0-9a-f]{64}") && files.ContainsKey(f) && Hash(p.Files[f])==digest);
   }
   // Reject a file/directory alias before creation (including differently cased aliases).
   var directories=new Dictionary<string,string>(StringComparer.OrdinalIgnoreCase);
   foreach(string name in p.Files.Keys) { int pos=name.IndexOf('/'); while(pos>=0) { string prefix=name.Substring(0,pos), spelling; if(directories.TryGetValue(prefix,out spelling)) Need(prefix==spelling); else directories.Add(prefix,prefix); pos=name.IndexOf('/',pos+1); } }
   foreach(string file in files.Keys) {
    string sourceName=file.StartsWith("runtime/App/s0_smoke/",StringComparison.Ordinal)?file.Substring(12):file;
    if(IsSource(sourceName)) Need(source.ContainsKey(sourceName));
   }
   foreach(string required in new[]{"s0_smoke/entry.py","s0_smoke/cli.py","installer/physical-smoke-s0.ps1","docs/PHYSICAL_SMOKE_S0.md","installer/physical-smoke-s0/S0Launcher.cs"}) Need(source.ContainsKey(required));
   var all=new HashSet<string>(p.Files.Keys,StringComparer.OrdinalIgnoreCase);
   foreach(string n in p.Files.Keys) { int at=n.IndexOf('/'); while(at>=0) { Need(!all.Contains(n.Substring(0,at))); at=n.IndexOf('/',at+1); } }
   return p;
  }
  public static BootstrapReceipt PlanPackage(byte[] zip,string expectedSha,string expectedHead,string targetRoot,string expectedSid) { return RunPackage(zip,expectedSha,expectedHead,targetRoot,expectedSid,false); }
  public static BootstrapReceipt StagePackage(byte[] zip,string expectedSha,string expectedHead,string targetRoot,string expectedSid,bool approved) { Need(approved); return RunPackage(zip,expectedSha,expectedHead,targetRoot,expectedSid,true); }
  static BootstrapReceipt RunPackage(byte[] zip,string sha,string head,string target,string sid,bool stage) {
   // Copy caller-owned bytes before authentication to prevent concurrent caller mutation.
   Need(zip!=null && zip.LongLength<=MaxZip); byte[] captured=(byte[])zip.Clone(); Package package=Validate(captured,sha,head);
   return Publish(package,captured,sha,head,target,sid,"GridS0Package-",stage);
  }
  static BootstrapReceipt Publish(Package package,byte[] sourceZipOrNull,string sha,string head,string target,string sid,string prefix,bool stage) {
   Need(prefix=="GridS0Package-" || prefix=="GridS0Input-");
   TokenObserver.RequireStandard(sid); new SecurityIdentifier(sid); Need(sid!=SystemSid && sid!=AdminSid);
   string local=Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData,Environment.SpecialFolderOption.DoNotVerify);
   Need(!String.IsNullOrEmpty(local)); local=Path.GetFullPath(local).TrimEnd('\\');
   Need(target!=null && target==Path.GetFullPath(target) && String.Equals(Path.GetDirectoryName(target),local,StringComparison.OrdinalIgnoreCase));
   string leaf=Path.GetFileName(target); Need(Match(leaf,Regex.Escape(prefix)+"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"));
   Need(target.Length<=240 && Match(local.Substring(0,3),"[A-Za-z]:\\\\"));
   using(var pins=new Pins(local,sid)) {
    Absent(target); var receipt=new BootstrapReceipt { Head=head,Sha256=sha,FileCount=package.Files.Count+(sourceZipOrNull==null?0:1),Bytes=package.Bytes+(sourceZipOrNull==null?0:sourceZipOrNull.LongLength),ParentIdentity=pins.ParentId,RootIdentity=null,Status="PLAN_ONLY" };
    if(!stage) return receipt;
    string txn=Path.Combine(local,".GridS0Transaction-"+Guid.NewGuid().ToString("D"));
    using(var security=new Security(sid)) {
     CreateDir(txn,security); Need(SetFileAttributesW(LongPath(txn),0x12));
     using(var root=Open(txn,true,true)) {
      string rootId=Inspect(root,txn,true,true,sid); var made=new HashSet<string>(StringComparer.OrdinalIgnoreCase); made.Add("");
      foreach(var item in package.Files) WriteMember(txn,item.Key,item.Value,security,sid,made);
      if(sourceZipOrNull!=null) WriteMember(txn,"source.zip",sourceZipOrNull,security,sid,made);
      pins.Check(); Need(Inspect(root,txn,true,true,sid)==rootId); Absent(target);
      Rename(root,pins.Parent,leaf); pins.Check();
      Need(Inspect(root,target,true,true,sid)==rootId);
      receipt.RootIdentity=rootId; receipt.Status="STAGED_NO_EXECUTION_AUTHORITY"; return receipt;
     }
    }
   }
  }
  static void WriteMember(string root,string name,byte[] bytes,Security sd,string sid,HashSet<string> made) {
   string relative=""; string[] parts=name.Split('/');
   for(int i=0;i<parts.Length-1;i++) { relative=relative.Length==0?parts[i]:relative+"\\"+parts[i]; if(made.Add(relative)) { string d=Path.Combine(root,relative); CreateDir(d,sd); using(var h=Open(d,true,false)) Inspect(h,d,true,true,sid); } }
   string path=Path.Combine(root,name.Replace('/','\\')); Need(path.Length<32760);
   var sa=sd.Attributes;
   using(var h=CreateFileW(LongPath(path),0x40000000|0x80000000|0x20000,0,ref sa,1,0x80|0x200000,IntPtr.Zero)) {
    Need(!h.IsInvalid); using(var stream=new FileStream(h,FileAccess.ReadWrite,65536,false)) {
     stream.Write(bytes,0,bytes.Length); stream.Flush(true); stream.Position=0;
     using(var hash=SHA256.Create()) Need(BitConverter.ToString(hash.ComputeHash(stream)).Replace("-","").ToLowerInvariant()==Hash(bytes));
     Inspect(h,path,false,true,sid);
    }
   }
  }
  static string LongPath(string path) { return "\\\\?\\"+path; }
  static void Absent(string path) { uint a=GetFileAttributesW(LongPath(path)); int error=Marshal.GetLastWin32Error(); Need(a==0xffffffff && (error==2 || error==3)); }
  sealed class Pins:IDisposable {
   internal SafeFileHandle Parent; internal string ParentId; readonly string sid; readonly List<SafeFileHandle> handles=new List<SafeFileHandle>(); readonly List<string> paths=new List<string>(), ids=new List<string>();
   internal Pins(string path,string s) { sid=s; try {
    string volume=Path.GetPathRoot(path); Need(GetDriveTypeW(volume)==3); var fs=new StringBuilder(32); Need(GetVolumeInformationW(volume,null,0,IntPtr.Zero,IntPtr.Zero,IntPtr.Zero,fs,32) && fs.ToString()=="NTFS");
    string current=volume; Pin(current); foreach(string part in path.Substring(volume.Length).Split('\\')) { Need(part.Length>0); current=Path.Combine(current,part); Pin(current); }
    Parent=handles[handles.Count-1]; ParentId=ids[ids.Count-1];
   } catch { Dispose(); throw; } }
   void Pin(string path) { var h=Open(path,true,false); handles.Add(h); paths.Add(path); ids.Add(Inspect(h,path,true,false,sid)); }
   internal void Check() { for(int i=0;i<handles.Count;i++) Need(Inspect(handles[i],paths[i],true,false,sid)==ids[i]); }
   public void Dispose() { foreach(var h in handles) h.Dispose(); }
  }
  static SafeFileHandle Open(string path,bool directory,bool deletion) {
   var h=CreateFileNoSecurity(LongPath(path),0x20000|0x80|(deletion?0x10000u:0u),3,IntPtr.Zero,3,0x200000|(directory?0x2000000u:0u),IntPtr.Zero);
   if(h.IsInvalid) { h.Dispose(); Need(false); } return h;
  }
  static string Inspect(SafeFileHandle h,string path,bool directory,bool strict,string sid) {
   Info info; Need(GetFileInformationByHandle(h,out info)); Need((info.Attributes&0x400)==0 && ((info.Attributes&16)!=0)==directory && (directory || info.Links==1));
   var final=new StringBuilder(32768); uint length=GetFinalPathNameByHandleW(h,final,32768,0); Need(length>0 && length<32768 && String.Equals(final.ToString(),"\\\\?\\"+path.TrimEnd('\\'),StringComparison.OrdinalIgnoreCase) || length>0 && length<32768 && path.Length==3 && String.Equals(final.ToString(),"\\\\?\\"+path,StringComparison.OrdinalIgnoreCase));
   IntPtr owner,dacl,sd; Need(GetSecurityInfo(h,1,5,out owner,IntPtr.Zero,out dacl,IntPtr.Zero,out sd)==0);
   try {
    uint size=GetSecurityDescriptorLength(sd); Need(size>=20 && size<=65536 && owner!=IntPtr.Zero && dacl!=IntPtr.Zero);
    byte[] raw=new byte[size]; Marshal.Copy(sd,raw,0,(int)size); var descriptor=new RawSecurityDescriptor(raw,0);
    string who=descriptor.Owner.Value; bool trusted=who==sid || who==SystemSid || who==AdminSid;
    string osAnchor=Path.GetPathRoot(Environment.GetFolderPath(Environment.SpecialFolder.Windows));
    Need(trusted || (!strict && directory && who==Ti && String.Equals(path,osAnchor,StringComparison.OrdinalIgnoreCase)));
    Need(descriptor.DiscretionaryAcl!=null && (descriptor.ControlFlags&ControlFlags.DiscretionaryAclPresent)!=0);
    if(strict) Need((descriptor.ControlFlags&ControlFlags.DiscretionaryAclProtected)!=0 && descriptor.DiscretionaryAcl.Count==3);
    var trustees=new HashSet<string>();
    foreach(GenericAce entry in descriptor.DiscretionaryAcl) {
     var ace=entry as CommonAce; Need(ace!=null && !ace.IsCallback && ((int)ace.AceFlags&~31)==0 && (ace.AceQualifier==AceQualifier.AccessAllowed || ace.AceQualifier==AceQualifier.AccessDenied));
     string trustee=ace.SecurityIdentifier.Value; bool known=trustee==sid || trustee==SystemSid || trustee==AdminSid;
     if(strict) Need(known && trustees.Add(trustee) && ace.AceQualifier==AceQualifier.AccessAllowed && ace.AceFlags==AceFlags.None && (uint)ace.AccessMask==Full);
     uint danger=Dangerous|(directory?0u:0x2u|0x4u|0x10u|0x100u);
     if(ace.AceQualifier==AceQualifier.AccessAllowed && (ace.AceFlags&AceFlags.InheritOnly)==0 && !known) Need(((uint)ace.AccessMask&danger)==0);
    }
    return info.Volume.ToString("x8")+":"+info.IndexHigh.ToString("x8")+info.IndexLow.ToString("x8");
   } finally { if(sd!=IntPtr.Zero) LocalFree(sd); }
  }
  sealed class Security:IDisposable {
   IntPtr pointer; internal SA Attributes;
   internal Security(string sid) { Need(ConvertStringSecurityDescriptorToSecurityDescriptorW("O:"+sid+"D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;"+sid+")",1,out pointer,IntPtr.Zero)); Attributes=new SA { Length=Marshal.SizeOf(typeof(SA)), Descriptor=pointer, Inherit=0 }; }
   public void Dispose() { if(pointer!=IntPtr.Zero) { LocalFree(pointer); pointer=IntPtr.Zero; } }
  }
  static void CreateDir(string path,Security sd) { var sa=sd.Attributes; Need(CreateDirectoryW(LongPath(path),ref sa)); }
  static void Rename(SafeFileHandle root,SafeFileHandle parent,string leaf) {
   byte[] name=Encoding.Unicode.GetBytes(leaf); int pointerOffset=IntPtr.Size==8?8:4, lengthOffset=pointerOffset+IntPtr.Size, nameOffset=lengthOffset+4;
   IntPtr buffer=Marshal.AllocHGlobal(nameOffset+name.Length); try {
    for(int i=0;i<nameOffset;i++) Marshal.WriteByte(buffer,i,0); // ReplaceIfExists is FALSE
    Marshal.WriteIntPtr(buffer,pointerOffset,parent.DangerousGetHandle()); Marshal.WriteInt32(buffer,lengthOffset,name.Length); Marshal.Copy(name,0,IntPtr.Add(buffer,nameOffset),name.Length);
    Need(SetFileInformationByHandle(root,3,buffer,(uint)(nameOffset+name.Length)));
   } finally { Marshal.FreeHGlobal(buffer); }
  }
  // Small bounded strict JSON parser: no duplicate keys, floating point or coercion.
  sealed class Json {
   readonly string text; int at; int depth;
   internal Json(byte[] bytes) { text=new UTF8Encoding(false,true).GetString(bytes); }
   internal object Read() { object result=Value(); White(); Need(at==text.Length); return result; }
   void White() { while(at<text.Length && " \t\r\n".IndexOf(text[at])>=0) at++; }
   char Take() { Need(at<text.Length); return text[at++]; }
   object Value() {
    White(); Need(++depth<=32); char c=Take(); object result;
    if(c=='{') { var d=new Dictionary<string,object>(StringComparer.Ordinal); White(); if(at<text.Length && text[at]=='}') { at++; result=d; } else { while(true) { White(); Need(Take()=='"'); string key=String(); White(); Need(Take()==':' && !d.ContainsKey(key)); d.Add(key,Value()); White(); char end=Take(); if(end=='}') break; Need(end==','); } result=d; } }
    else if(c=='"') result=String();
    else if(c=='t') { Literal("rue"); result=true; }
    else if(c=='f') { Literal("alse"); result=false; }
    else { Need(c>='0' && c<='9'); int start=at-1; while(at<text.Length && text[at]>='0' && text[at]<='9') at++; string n=text.Substring(start,at-start); long number=0; Need((n.Length==1 || n[0]!='0') && Int64.TryParse(n,out number)); result=number; }
    depth--; return result;
   }
   void Literal(string s) { foreach(char c in s) Need(Take()==c); }
   string String() { var b=new StringBuilder(); while(true) { char c=Take(); if(c=='"') break; Need(c>=32); if(c=='\\') { c=Take(); if(c=='u') { int value=0; for(int i=0;i<4;i++) { char h=Take(); int n="0123456789abcdef".IndexOf(Char.ToLowerInvariant(h)); Need(n>=0); value=value*16+n; } c=(char)value; } else { int index="\"\\/bfnrt".IndexOf(c); Need(index>=0); c="\"\\/\b\f\n\r\t"[index]; } } b.Append(c); Need(b.Length<=1048576); } string valueString=b.ToString(); for(int i=0;i<valueString.Length;i++) { if(Char.IsHighSurrogate(valueString[i])) { Need(i+1<valueString.Length && Char.IsLowSurrogate(valueString[++i])); } else Need(!Char.IsLowSurrogate(valueString[i])); } return valueString; }
  }
  [StructLayout(LayoutKind.Sequential)] struct SA { internal int Length; internal IntPtr Descriptor; internal int Inherit; }
  [StructLayout(LayoutKind.Sequential)] struct Info { internal uint Attributes; internal System.Runtime.InteropServices.ComTypes.FILETIME Creation,Access,Write; internal uint Volume,SizeHigh,SizeLow,Links,IndexHigh,IndexLow; }
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern SafeFileHandle CreateFileW(string p,uint access,uint share,ref SA sa,uint disposition,uint flags,IntPtr template);
  [DllImport("kernel32.dll",EntryPoint="CreateFileW",CharSet=CharSet.Unicode,SetLastError=true)] static extern SafeFileHandle CreateFileNoSecurity(string p,uint access,uint share,IntPtr sa,uint disposition,uint flags,IntPtr template);
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateDirectoryW(string p,ref SA sa);
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern uint GetFileAttributesW(string p);
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool SetFileAttributesW(string p,uint attributes);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetFileInformationByHandle(SafeFileHandle h,out Info info);
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern uint GetFinalPathNameByHandleW(SafeFileHandle h,StringBuilder path,uint size,uint flags);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool FlushFileBuffers(SafeFileHandle h);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetFileInformationByHandle(SafeFileHandle h,int kind,IntPtr info,uint size);
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern uint GetDriveTypeW(string root);
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool GetVolumeInformationW(string root,StringBuilder volume,uint size,IntPtr serial,IntPtr max,IntPtr flags,StringBuilder fs,uint fsSize);
  [DllImport("advapi32.dll",SetLastError=true)] static extern uint GetSecurityInfo(SafeFileHandle h,int type,uint requested,out IntPtr owner,IntPtr group,out IntPtr dacl,IntPtr sacl,out IntPtr sd);
  [DllImport("advapi32.dll")] static extern uint GetSecurityDescriptorLength(IntPtr sd);
  [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool ConvertStringSecurityDescriptorToSecurityDescriptorW(string s,uint revision,out IntPtr sd,IntPtr size);
  [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr p);
 }
}
