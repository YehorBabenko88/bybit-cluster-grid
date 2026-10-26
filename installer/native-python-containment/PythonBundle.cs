using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Win32.SafeHandles;
internal record PythonFile(string Sha256,long Length);
internal record PythonInput(int Schema,string Head,string Run,string Attempt,string Python,Dictionary<string,PythonFile> Files,Dictionary<string,string> Origins);
internal sealed class PythonBundle:IOwnedExecutable {
 [DllImport("userenv.dll",CharSet=CharSet.Unicode)]static extern int GetAppContainerFolderPath(string sid,out IntPtr path);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern SafeFileHandle CreateFileW(string path,uint access,uint share,IntPtr attributes,uint disposition,uint flags,IntPtr template);
 [DllImport("advapi32.dll")]static extern uint SetSecurityInfo(SafeFileHandle h,int type,uint info,IntPtr owner,IntPtr group,IntPtr dacl,IntPtr sacl);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool DuplicateHandle(IntPtr sourceProcess,SafeFileHandle source,IntPtr targetProcess,out SafeFileHandle target,uint access,bool inherit,uint options);
 readonly List<SafeFileHandle> handles=new();
 readonly List<(SafeFileHandle H,Identity Id,string Sd)> mutablePins=new();
 readonly List<(SafeFileHandle H,Identity Id,string Sd,string? Hash)> pins=new();
 readonly Dictionary<string,SafeFileHandle> directories=new(StringComparer.OrdinalIgnoreCase);
 readonly RawSecurityDescriptor rx;
 SafeFileHandle? result,diagnosticRead,diagnosticWrite;
 public SafeFileHandle? OutputHandle=>diagnosticWrite;
 public bool TraceLoader=>true;
 public string Path{get;private set;}="";public string WorkingDirectory{get;private set;}="";
 public string RootPath{get;private set;}="";public string ResultPath=>System.IO.Path.Combine(WorkingDirectory,"result.json");
 public string CommandLine=>"\""+Path+"\" -I -B -S \""+System.IO.Path.Combine(RootPath,"driver.py")+"\" --native-child";
 public string EnvironmentBlock{get;private set;}="";
 internal string InputHash{get;private set;}="";internal int FileCount{get;private set;}
 static byte[] Read(SafeFileHandle h){long length=RandomAccess.GetLength(h);ControllerPolicy.Need(length>=0&&length<=32*1024*1024,"PYTHON_FILE_SIZE");var b=new byte[(int)length];int offset=0;while(offset<b.Length){int n=RandomAccess.Read(h,b.AsSpan(offset),offset);ControllerPolicy.Need(n>0,"PYTHON_FILE_READ");offset+=n;}return b;}
 static string Hash(byte[] b)=>Convert.ToHexString(SHA256.HashData(b));
 void Remember(SafeFileHandle h,bool directory,string? hash=null){handles.Add(h);var id=Native.Id(h);Policy.Object(id,directory);pins.Add((h,id,FixtureNative.Descriptor(h),hash));}
 static void Low(SafeFileHandle h){var raw=new RawSecurityDescriptor("S:(ML;OICI;NW;;;LW)");var acl=raw.SystemAcl!;var bytes=new byte[acl.BinaryLength];acl.GetBinaryForm(bytes,0);var p=Marshal.AllocHGlobal(bytes.Length);try{Marshal.Copy(bytes,0,p,bytes.Length);ControllerPolicy.Need(SetSecurityInfo(h,1,0x10,IntPtr.Zero,IntPtr.Zero,IntPtr.Zero,p)==0,"PYTHON_DATA_LOW_LABEL");}finally{Marshal.FreeHGlobal(p);}}
 SafeFileHandle Directory(SafeFileHandle parent,string name,RawSecurityDescriptor descriptor,bool low=false){
  Identity id;string sd;using(var made=FixtureNative.Create(parent,name,true,descriptor)){if(low)Low(made);id=Native.Id(made);sd=FixtureNative.Descriptor(made);}
  var h=Native.OpenChild(parent,name,true);ControllerPolicy.Need(Native.Id(h)==id&&FixtureNative.Descriptor(h)==sd,"PYTHON_DIRECTORY_REPLACED");Remember(h,true);return h;
 }
 SafeFileHandle ParentFor(string relative){var parts=relative.Split('/');var h=directories[""];string key="";foreach(string p in parts[..^1]){key=key.Length==0?p:key+"/"+p;if(!directories.TryGetValue(key,out var next)){next=Directory(h,p,rx);directories.Add(key,next);}h=next;}return h;}
 SafeFileHandle File(SafeFileHandle parent,string name,byte[] bytes,RawSecurityDescriptor descriptor,string absolute,bool writable=false){
  Identity id;string sd;using(var made=FixtureNative.Create(parent,name,false,descriptor)){if(writable)Low(made);for(int n=0;n<bytes.Length;n+=131072)FixtureNative.AppendFlush(made,bytes[n..Math.Min(bytes.Length,n+131072)]);id=Native.Id(made);sd=FixtureNative.Descriptor(made);}
  var held=CreateFileW(absolute,0x80020000,writable?3u:1u,IntPtr.Zero,3,0x200000,IntPtr.Zero);ControllerPolicy.Need(!held.IsInvalid,"PYTHON_FILE_PIN");ControllerPolicy.Need(Native.Id(held)==id&&FixtureNative.Descriptor(held)==sd&&Hash(Read(held))==Hash(bytes),"PYTHON_FILE_REPLACED");
  if(writable){handles.Add(held);mutablePins.Add((held,id,sd));}else Remember(held,false,Hash(bytes));return held;
 }
 internal PythonBundle(string package,string moniker,string user,PythonInput input,string inputHash,object config){
  rx=new RawSecurityDescriptor("D:P(A;;FA;;;SY)(A;;FA;;;"+user+")(A;;0x1200a9;;;"+package+")");
  IntPtr pointer=IntPtr.Zero;
  try{
   ControllerPolicy.Need(GetAppContainerFolderPath(package,out pointer)==0&&pointer!=IntPtr.Zero,"PYTHON_PROFILE");string profile=(Marshal.PtrToStringUni(pointer)??"").TrimEnd('\\');ControllerPolicy.Need(profile.EndsWith("\\Packages\\"+moniker+"\\AC",StringComparison.OrdinalIgnoreCase),"PYTHON_PROFILE_MAPPING");
   SafeFileHandle? parent=null;foreach(string part in Policy.Components(profile)){var h=parent==null?Native.OpenRoot(part):Native.OpenChild(parent,part,true);Remember(h,true);parent=h;}
   string name="python-"+Guid.NewGuid().ToString("D");RootPath=System.IO.Path.Combine(profile,name);var root=Directory(parent!,name,rx);directories.Add("",root);
   foreach(var (relative,pin) in input.Files.OrderBy(x=>x.Key,StringComparer.Ordinal)){
    ControllerPolicy.Need(relative.Length>0&&relative.Length<=240&&!relative.Contains('\\')&&!relative.Contains(':')&&!relative.StartsWith('/'),"PYTHON_RELATIVE_PATH");var components=Policy.Components("C:\\"+relative.Replace('/','\\'));ControllerPolicy.Need(components.Length>1);
    string source=System.IO.Path.Combine(Environment.GetEnvironmentVariable("GITHUB_WORKSPACE")!,"python-input",relative.Replace('/','\\'));
    using var sourceHandle=CreateFileW(source,0x80020000,1,IntPtr.Zero,3,0x200000,IntPtr.Zero);ControllerPolicy.Need(!sourceHandle.IsInvalid,"PYTHON_SOURCE_OPEN");var sourceId=Native.Id(sourceHandle);Policy.Object(sourceId,false);byte[] bytes=Read(sourceHandle);ControllerPolicy.Need(bytes.Length==pin.Length&&Hash(bytes)==pin.Sha256&&Native.Id(sourceHandle)==sourceId,"PYTHON_SOURCE_PIN");
    File(ParentFor(relative),relative.Split('/')[^1],bytes,rx,System.IO.Path.Combine(RootPath,relative.Replace('/','\\')));FileCount++;
   }
   ControllerPolicy.Need(FileCount>10&&FileCount<=20000,"PYTHON_CLOSURE_SIZE");InputHash=inputHash;
   WorkingDirectory=System.IO.Path.Combine(RootPath,"Data");var dataSd=new RawSecurityDescriptor("D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;"+user+")(A;OICI;0x1301bf;;;"+package+")");var data=Directory(root,"Data",dataSd,true);
   result=File(data,"result.json",Array.Empty<byte>(),new RawSecurityDescriptor("D:P(A;;FA;;;SY)(A;;FA;;;"+user+")(A;;0x12019f;;;"+package+")"),ResultPath,true);
   string diagnosticPath=System.IO.Path.Combine(WorkingDirectory,"stderr.txt");diagnosticRead=File(data,"stderr.txt",Array.Empty<byte>(),new RawSecurityDescriptor("D:P(A;;FA;;;SY)(A;;FA;;;"+user+")"),diagnosticPath,true);
   using(var write=CreateFileW(diagnosticPath,0x100084,7,IntPtr.Zero,3,0x200000,IntPtr.Zero)){ControllerPolicy.Need(!write.IsInvalid&&Native.Id(write)==Native.Id(diagnosticRead),"DIAGNOSTIC_WRITE_ID");ControllerPolicy.Need(DuplicateHandle(new IntPtr(-1),write,new IntPtr(-1),out diagnosticWrite,0,true,2),"DIAGNOSTIC_HANDLE_DUPLICATE");handles.Add(diagnosticWrite);}
   File(root,"config.json",JsonSerializer.SerializeToUtf8Bytes(config),rx,System.IO.Path.Combine(RootPath,"config.json"));
   Path=System.IO.Path.Combine(RootPath,"pythonw.exe");ControllerPolicy.Need(input.Files.ContainsKey("pythonw.exe")&&input.Files.ContainsKey("python.exe")&&input.Files.ContainsKey("driver.py")&&input.Files.ContainsKey("python._pth"),"PYTHON_CLOSURE_REQUIRED");
   var env=new SortedDictionary<string,string>(StringComparer.OrdinalIgnoreCase){["SystemRoot"]=Environment.GetFolderPath(Environment.SpecialFolder.Windows),["WINDIR"]=Environment.GetFolderPath(Environment.SpecialFolder.Windows),["LOCALAPPDATA"]=WorkingDirectory,["USERPROFILE"]=WorkingDirectory,["TEMP"]=WorkingDirectory,["TMP"]=WorkingDirectory,["ProgramData"]=WorkingDirectory,["NODE_ID"]="synthetic-contained-worker",["POSTGRES_DSN"]="postgresql://synthetic:nonsecret@127.0.0.1:1/never",["COORDINATOR_URL"]="http://127.0.0.1:1",["GRID_CONTROL_JOURNAL"]=System.IO.Path.Combine(WorkingDirectory,"control-state.json"),["GRID_CONTROL_SNAPSHOTS"]=System.IO.Path.Combine(WorkingDirectory,"snapshots"),["BYBIT_REST_URL"]="http://192.0.2.1:9",["BYBIT_WS_URL"]="ws://192.0.2.1:9",["ROLE"]="worker",["NODE_ROLE"]="WORKER"};
   EnvironmentBlock=string.Join("\0",env.Select(x=>x.Key+"="+x.Value))+"\0\0";Guard();
  }catch{Dispose();throw;}finally{if(pointer!=IntPtr.Zero)Marshal.FreeCoTaskMem(pointer);}
 }
 public void Guard(){foreach(var p in pins){ControllerPolicy.Need(Native.Id(p.H)==p.Id&&FixtureNative.Descriptor(p.H)==p.Sd,"PYTHON_CUSTODY_DRIFT");if(p.Hash!=null)ControllerPolicy.Need(Hash(Read(p.H))==p.Hash,"PYTHON_CONTENT_DRIFT");}foreach(var p in mutablePins)ControllerPolicy.Need(Native.Id(p.H)==p.Id&&FixtureNative.Descriptor(p.H)==p.Sd,"PYTHON_MUTABLE_REPLACED");}
 internal byte[] Diagnostics(){Guard();ControllerPolicy.Need(diagnosticRead!=null);var b=Read(diagnosticRead!);ControllerPolicy.Need(b.Length<=262144,"DIAGNOSTIC_SIZE");return b;}
 internal byte[] Result(){Guard();ControllerPolicy.Need(result!=null);var bytes=Read(result!);ControllerPolicy.Need(bytes.Length>0&&bytes.Length<=65536,"PYTHON_RESULT_BOUND");return bytes;}
 public void Dispose(){for(int i=handles.Count-1;i>=0;i--)handles[i].Dispose();handles.Clear();pins.Clear();mutablePins.Clear();result=null;diagnosticRead=null;diagnosticWrite=null;}
}
