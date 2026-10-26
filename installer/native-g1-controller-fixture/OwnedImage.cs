using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Cryptography;
using Microsoft.Win32.SafeHandles;

// A fresh CREATE-only file under this new GUID AppContainer profile. RETAIN, no deletion.
internal interface IOwnedExecutable:IDisposable {
 string Path{get;} string CommandLine{get;} string WorkingDirectory{get;}
 string EnvironmentBlock{get;} void Guard();
}
internal sealed class OwnedImage:IOwnedExecutable {
 [DllImport("userenv.dll",CharSet=CharSet.Unicode)]static extern int GetAppContainerFolderPath(string sid,out IntPtr path);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern SafeFileHandle CreateFileW(string path,uint access,uint share,IntPtr attributes,uint disposition,uint flags,IntPtr template);
 readonly List<(SafeFileHandle Handle,Identity Id,string Descriptor)> parents=new();
 SafeFileHandle? image;Identity? identity;string descriptor="";readonly string digest;
 public string Path{get;}="";
 public string CommandLine=>"\""+Path+"\"";
 public string WorkingDirectory=>Environment.GetFolderPath(Environment.SpecialFolder.System);
 public string EnvironmentBlock=>ControllerPolicy.ChildEnvironment(Environment.GetFolderPath(Environment.SpecialFolder.Windows),Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData));
 internal OwnedImage(string package,string moniker,string user,byte[] payload,string hash){
  ControllerPolicy.Need(payload.Length>1&&payload.Length<65536&&payload[0]==77&&payload[1]==90&&Convert.ToHexString(SHA256.HashData(payload))==hash,"FIXTURE_IMAGE_PAYLOAD");digest=hash;
  IntPtr pointer=IntPtr.Zero;
  try{
   ControllerPolicy.Need(GetAppContainerFolderPath(package,out pointer)==0&&pointer!=IntPtr.Zero,"OWNED_PROFILE_PATH");string folder=(Marshal.PtrToStringUni(pointer)??"").TrimEnd('\\');
   ControllerPolicy.Need(folder.EndsWith("\\Packages\\"+moniker+"\\AC",StringComparison.OrdinalIgnoreCase),"OWNED_PROFILE_MAPPING");var components=Policy.Components(folder);
   foreach(string part in components){var h=parents.Count==0?Native.OpenRoot(part):Native.OpenChild(parents[^1].Handle,part,true);try{var id=Native.Id(h);Policy.Object(id,true);parents.Add((h,id,FixtureNative.Descriptor(h)));}catch{h.Dispose();throw;}}
   var sd=new RawSecurityDescriptor("D:P(A;;FA;;;SY)(A;;FA;;;"+user+")(A;;0x1200a9;;;"+package+")");
   Identity created;
   using(var write=FixtureNative.Create(parents[^1].Handle,"fixture-child.exe",false,sd)){FixtureNative.AppendFlush(write,payload);created=Native.Id(write);Policy.Object(created,false);descriptor=FixtureNative.Descriptor(write);var actual=new RawSecurityDescriptor(Convert.FromBase64String(descriptor),0);var rights=new Dictionary<string,int>{{"S-1-5-18",0x1f01ff},{user,0x1f01ff},{package,0x1200a9}};ControllerPolicy.Need(actual.Owner!=null&&actual.Group!=null&&new[]{user,"S-1-5-32-544","S-1-5-18"}.Contains(actual.Owner.Value)&&(actual.ControlFlags&ControlFlags.DiscretionaryAclProtected)!=0&&actual.DiscretionaryAcl!=null&&actual.DiscretionaryAcl.Count==3&&actual.DiscretionaryAcl.Cast<GenericAce>().All(a=>a is CommonAce c&&!c.IsCallback&&c.AceFlags==AceFlags.None&&c.AceQualifier==AceQualifier.AccessAllowed&&rights.TryGetValue(c.SecurityIdentifier.Value,out int mask)&&c.AccessMask==mask),"OWNED_IMAGE_DACL");}
   Path=System.IO.Path.Combine(folder,"fixture-child.exe");
   // OPEN_REPARSE_POINT + share-read only. Fail if any writer won the close/reopen barrier.
   image=CreateFileW(Path,0x80020000,1,IntPtr.Zero,3,0x200000,IntPtr.Zero);ControllerPolicy.Need(!image.IsInvalid,"OWNED_IMAGE_PIN");identity=Native.Id(image);ControllerPolicy.Need(identity==created,"OWNED_IMAGE_REPLACED");Guard();
  }catch{Dispose();throw;}finally{if(pointer!=IntPtr.Zero)Marshal.FreeCoTaskMem(pointer);}
 }
 public void Guard(){
  ControllerPolicy.Need(image!=null&&!image.IsClosed&&!image.IsInvalid&&identity!=null,"OWNED_IMAGE_HANDLE");Policy.Object(Native.Id(image!),false);
  ControllerPolicy.Need(Native.Id(image!)==identity&&FixtureNative.Descriptor(image!)==descriptor&&Convert.ToHexString(SHA256.HashData(FixtureNative.Read(image!)))==digest,"OWNED_IMAGE_CUSTODY");
  foreach(var p in parents)ControllerPolicy.Need(Native.Id(p.Handle)==p.Id&&FixtureNative.Descriptor(p.Handle)==p.Descriptor,"OWNED_PROFILE_ANCESTOR_DRIFT");
 }
 public void Dispose(){image?.Dispose();image=null;for(int n=parents.Count-1;n>=0;n--)parents[n].Handle.Dispose();parents.Clear();}
}
