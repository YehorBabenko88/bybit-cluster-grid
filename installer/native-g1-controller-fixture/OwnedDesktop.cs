using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Text;

// Hosted factory only. Never opens/modifies winsta0/default or an existing station.
internal sealed class OwnedDesktop:IDisposable {
 [StructLayout(LayoutKind.Sequential)]struct SA{public uint size;public IntPtr descriptor;public int inherit;}
 [DllImport("user32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern IntPtr CreateWindowStationW(string name,uint flags,uint access,ref SA sa);
 [DllImport("user32.dll",SetLastError=true)]static extern IntPtr GetProcessWindowStation();
 [DllImport("user32.dll",SetLastError=true)]static extern bool SetProcessWindowStation(IntPtr station);
 [DllImport("user32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern IntPtr CreateDesktopW(string name,IntPtr device,IntPtr mode,uint flags,uint access,ref SA sa);
 [DllImport("user32.dll",SetLastError=true)]static extern bool CloseDesktop(IntPtr desktop);
 [DllImport("user32.dll",SetLastError=true)]static extern bool CloseWindowStation(IntPtr station);
 [DllImport("user32.dll",SetLastError=true)]static extern bool GetUserObjectSecurity(IntPtr handle,ref uint info,IntPtr data,uint size,out uint needed);
 [DllImport("user32.dll",SetLastError=true)]static extern bool SetUserObjectSecurity(IntPtr handle,ref uint info,IntPtr data);
 [DllImport("user32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern bool GetUserObjectInformationW(IntPtr handle,int info,StringBuilder data,uint size,out uint needed);
 IntPtr station,desktop;readonly string stationName="g1-ci-"+Guid.NewGuid().ToString("D");
 readonly byte[] stationDescriptor,desktopDescriptor;
 internal string Name=>stationName+"\\owned";
 static byte[] Descriptor(string user,string package,string mask){
  string full=mask=="0x2037f"?"0xf037f":"0xf01ff";
  var d=new RawSecurityDescriptor("O:BAG:BAD:P(A;;"+full+";;;SY)(A;;"+full+";;;BA)(A;;"+mask+";;;"+user+")(A;;"+mask+";;;"+package+")S:(ML;;NW;;;LW)");
  var bytes=new byte[d.BinaryLength];d.GetBinaryForm(bytes,0);return bytes;
 }
 static IntPtr Buffer(byte[] bytes){var p=Marshal.AllocHGlobal(bytes.Length);Marshal.Copy(bytes,0,p,bytes.Length);return p;}
 static void Need(bool ok,string code){if(!ok)throw new Blocked(code+"_WIN32_"+Marshal.GetLastWin32Error());}
 internal OwnedDesktop(string user,string package){
  stationDescriptor=Descriptor(user,package,"0x2037f");desktopDescriptor=Descriptor(user,package,"0x201ff");
  // Bootstrap namespace grants only SYSTEM/Administrators, owned by Administrators.
  // Unprivileged processes cannot race desktop creation before final access is granted.
  var bootstrap=new RawSecurityDescriptor("O:BAG:BAD:P(A;;0xf037f;;;SY)(A;;0xf037f;;;BA)S:(ML;;NW;;;LW)");var bytes=new byte[bootstrap.BinaryLength];bootstrap.GetBinaryForm(bytes,0);
  var p=Buffer(bytes);IntPtr old=GetProcessWindowStation();bool switched=false;
  try{
   Need(old!=IntPtr.Zero,"WINDOW_STATION_CONTEXT");var sa=new SA{size=(uint)Marshal.SizeOf<SA>(),descriptor=p};
   station=CreateWindowStationW(stationName,1,0xf037f,ref sa);Need(station!=IntPtr.Zero,"CREATE_ONLY_WINDOW_STATION");
   Need(SetProcessWindowStation(station),"SET_PRIVATE_WINDOW_STATION");switched=true;
   var d=Buffer(desktopDescriptor);
   try{sa.descriptor=d;desktop=CreateDesktopW("owned",IntPtr.Zero,IntPtr.Zero,0,0xf01ff,ref sa);Need(desktop!=IntPtr.Zero,"CREATE_PRIVATE_DESKTOP");}
   finally{Marshal.FreeHGlobal(d);}
   Need(SetProcessWindowStation(old),"RESTORE_WINDOW_STATION");switched=false;
   var next=Buffer(stationDescriptor);
   try{uint info=0x17;Need(SetUserObjectSecurity(station,ref info,next),"PUBLISH_OWNED_STATION_ACCESS");}
   finally{Marshal.FreeHGlobal(next);}
   Guard();
  }catch{try{if(switched){Need(SetProcessWindowStation(old),"RESTORE_WINDOW_STATION_ON_FAILURE");switched=false;}}finally{Dispose();}throw;}
  finally{try{if(switched)Need(SetProcessWindowStation(old),"RESTORE_WINDOW_STATION_FINALLY");}finally{Marshal.FreeHGlobal(p);}}
 }
 static byte[] AclBytes(GenericAcl acl){var b=new byte[acl.BinaryLength];acl.GetBinaryForm(b,0);return b;}
 static void Verify(IntPtr handle,string name,byte[] expected){
  var actualName=new StringBuilder(512);Need(GetUserObjectInformationW(handle,2,actualName,1024,out uint used)&&used<=1024,"PRIVATE_GUI_NAME");ControllerPolicy.Need(actualName.ToString()==name,"PRIVATE_GUI_NAME_DRIFT");
  uint info=0x17;bool probe=GetUserObjectSecurity(handle,ref info,IntPtr.Zero,0,out uint size);ControllerPolicy.Need(!probe&&Marshal.GetLastWin32Error()==122&&size>=20&&size<=65536,"PRIVATE_GUI_DESCRIPTOR_SIZE");
  var p=Marshal.AllocHGlobal((int)size);
  try{
   Need(GetUserObjectSecurity(handle,ref info,p,size,out uint actual)&&actual==size,"PRIVATE_GUI_DESCRIPTOR");var bytes=new byte[size];Marshal.Copy(p,bytes,0,(int)size);var sd=new RawSecurityDescriptor(bytes,0);var wanted=new RawSecurityDescriptor(expected,0);
   ControllerPolicy.Need(sd.Owner?.Value==wanted.Owner?.Value&&sd.Group?.Value==wanted.Group?.Value&&(sd.ControlFlags&ControlFlags.DiscretionaryAclProtected)!=0&&sd.DiscretionaryAcl!=null&&sd.SystemAcl!=null,"PRIVATE_GUI_CUSTODY");
   ControllerPolicy.Need(AclBytes(sd.DiscretionaryAcl!).AsSpan().SequenceEqual(AclBytes(wanted.DiscretionaryAcl!))&&AclBytes(sd.SystemAcl!).AsSpan().SequenceEqual(AclBytes(wanted.SystemAcl!)),"PRIVATE_GUI_ACL_DRIFT");
  }finally{Marshal.FreeHGlobal(p);}
 }
 internal void Guard(){ControllerPolicy.Need(station!=IntPtr.Zero&&desktop!=IntPtr.Zero,"PRIVATE_GUI_HANDLES");Verify(station,stationName,stationDescriptor);Verify(desktop,"owned",desktopDescriptor);}
 public void Dispose(){if(desktop!=IntPtr.Zero){CloseDesktop(desktop);desktop=IntPtr.Zero;}if(station!=IntPtr.Zero){CloseWindowStation(station);station=IntPtr.Zero;}}
}
