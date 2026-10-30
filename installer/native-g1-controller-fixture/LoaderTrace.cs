using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;
internal record LoaderFact(uint Event,string Detail);
// Diagnostic events only for a newly created owned debuggee. Never attaches by PID.
internal static class LoaderTrace {
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool WaitForDebugEventEx(IntPtr data,uint timeout);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool ContinueDebugEvent(uint process,uint thread,uint status);
 [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr handle);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern uint K32GetMappedFileNameW(IntPtr process,IntPtr address,StringBuilder path,uint size);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern uint QueryDosDeviceW(string name,StringBuilder target,uint size);
 [DllImport("kernel32.dll")]static extern uint GetFileType(IntPtr handle);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern uint GetFinalPathNameByHandleW(IntPtr handle,StringBuilder path,uint length,uint flags);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool ReadProcessMemory(IntPtr process,IntPtr address,byte[] buffer,UIntPtr size,out UIntPtr read);
 static string FileName(IntPtr file,Action<SafeFileHandle,string> validate){ControllerPolicy.Need(file!=IntPtr.Zero,"LOADER_FILE_UNOBSERVED");try{ControllerPolicy.Need(GetFileType(file)==1,"DEBUG_FILE_TYPE");var b=new StringBuilder(32768);uint n=GetFinalPathNameByHandleW(file,b,32768,0);ControllerPolicy.Need(n>0&&n<32768,"LOADER_PATH_UNOBSERVED");using var borrowed=new SafeFileHandle(file,false);validate(borrowed,b.ToString());return b.ToString();}finally{CloseHandle(file);}}
 internal static bool InitialBreakpoint(uint exception,uint firstChance,bool handled,string mapped,string expected)=>exception==0x80000003&&firstChance==1&&!handled&&string.Equals(mapped,expected,StringComparison.OrdinalIgnoreCase);
 internal static void Pump(IntPtr process,uint ownedPid,uint timeout,List<LoaderFact> facts,Action<SafeFileHandle,string> validate){
  ControllerPolicy.Need(IntPtr.Size==8,"DEBUG_LAYOUT_UNSUPPORTED");long until=Environment.TickCount64+timeout;int count=0;bool initialHandled=false;
  string windows=Environment.GetFolderPath(Environment.SpecialFolder.Windows);Policy.Components(windows+"\\System32\\ntdll.dll");var device=new StringBuilder(32768);ControllerPolicy.Need(QueryDosDeviceW(windows[..2],device,32768)>0,"DEBUG_SYSTEM_MAPPING");string expectedNtdll=device.ToString()+windows[2..]+"\\System32\\ntdll.dll";
  var data=Marshal.AllocHGlobal(176);try{while(Environment.TickCount64<until){
   if(!WaitForDebugEventEx(data,500)){int error=Marshal.GetLastWin32Error();ControllerPolicy.Need(error is 121 or 1460,"DEBUG_WAIT_"+error);continue;}
   uint kind=unchecked((uint)Marshal.ReadInt32(data)),pid=unchecked((uint)Marshal.ReadInt32(data,4)),tid=unchecked((uint)Marshal.ReadInt32(data,8));ControllerPolicy.Need(pid==ownedPid&&tid>0&&++count<=1024,"DEBUG_EVENT_BINDING");uint status=0x10002;
   // Event process/thread handles are closed by Windows at the corresponding EXIT continuation.
   // Only image/DLL file handles belong to this debugger; never close event process/thread handles.
   if(kind==3)facts.Add(new(kind,FileName(Marshal.ReadIntPtr(data,16),validate)));
   else if(kind==2){}
   else if(kind==6)facts.Add(new(kind,FileName(Marshal.ReadIntPtr(data,16),validate)));
   else if(kind==1){uint exception=unchecked((uint)Marshal.ReadInt32(data,16)),first=unchecked((uint)Marshal.ReadInt32(data,168));var mapped=new StringBuilder(32768);uint n=K32GetMappedFileNameW(process,Marshal.ReadIntPtr(data,32),mapped,32768);string origin=n>0&&n<32768?mapped.ToString():"UNOBSERVED";facts.Add(new(kind,"exception:"+exception.ToString("X8")+":"+origin));if(InitialBreakpoint(exception,first,initialHandled,origin,expectedNtdll))initialHandled=true;else status=0x80010001;}
   else if(kind==8){var address=Marshal.ReadIntPtr(data,16);bool unicode=Marshal.ReadInt16(data,24)!=0;int n=unchecked((ushort)Marshal.ReadInt16(data,26));if(n>0&&n<=4096){var b=new byte[n*(unicode?2:1)];if(ReadProcessMemory(process,address,b,(UIntPtr)b.Length,out var read)&&read.ToUInt64()==(ulong)b.Length)facts.Add(new(kind,(unicode?Encoding.Unicode:Encoding.UTF8).GetString(b).TrimEnd('\0')));}}
   else if(kind==5)facts.Add(new(kind,"exit:"+unchecked((uint)Marshal.ReadInt32(data,16)).ToString("X8")));
   else ControllerPolicy.Need(kind is 4 or 7,"DEBUG_EVENT_UNKNOWN");
   ControllerPolicy.Need(ContinueDebugEvent(pid,tid,status),"DEBUG_CONTINUE");if(kind==5)return;
  }throw new Blocked("DEBUG_DEADLINE");}finally{Marshal.FreeHGlobal(data);}
 }
}
