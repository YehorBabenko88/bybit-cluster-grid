"""Actual CPython/Grid negative lifecycle probe. Only the native hosted parent launches it."""
import asyncio,ctypes,ctypes.wintypes as W,json,os,pathlib,re,socket,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parent
CASES=['isolated-python','no-parent-secrets','closed-import-paths','own-data-rw','foreign-read-denied','foreign-write-denied','source-write-denied','source-write-dac-denied','parent-handle-not-inherited','parent-process-read-denied','loopback-denied','documentation-network-denied','subprocess-denied','native-dependencies','real-coordinator-fails-closed','real-worker-infra-only','dll-module-closure']
rows=[]
network_diagnostics=[]
network_isolation=[]
self_loopback=[]
def native_scope(root,host,args):
    p=pathlib.PureWindowsPath(root);guid=r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    if args!=['--native-child'] or host.upper() in ('LS5','PC4') or not re.fullmatch(r'[A-Za-z]:',p.drive) or p.parent.name!='AC' or p.parent.parent.parent.name!='Packages' or not re.fullmatch('python-'+guid,p.name) or not re.fullmatch('g1-fixture-'+guid,p.parent.parent.name):raise ValueError('PHYSICAL_OR_UNOWNED_PROBE_REFUSED')
class BoundaryFailure(RuntimeError):
    def __init__(self,code):super().__init__(code);self.code=code

def need(ok,code='BOUNDARY_NOT_PROVEN'):
    if not ok:raise BoundaryFailure(code)

def isolation_fact(status,capability):
    observed=type(status) is int and status==0 and type(capability) is int and capability in (0,1,2,3)
    return dict(status='OBSERVED' if observed else 'BLOCKED',api_status=status if type(status) is int and 0<=status<2**32 else None,missing_capability=capability if type(capability) is int and capability in (0,1,2,3) else None)

def isolation_diagnosis(host):
    try:
        api=ctypes.WinDLL(str(pathlib.Path(os.environ['SystemRoot'])/'System32/firewallapi.dll')).NetworkIsolationDiagnoseConnectFailureAndGetInfo
        api.argtypes=[W.LPCWSTR,ctypes.POINTER(ctypes.c_int)];api.restype=W.DWORD;cap=ctypes.c_int(4)
        return isolation_fact(api(host,ctypes.byref(cap)),cap.value)
    except (OSError,AttributeError) as error:return isolation_fact(getattr(error,'winerror',None),None)

def recv_exact(channel,n):
    need(type(n) is int and 0<n<=64,'SELF_IPC_LENGTH');data=b''
    while len(data)<n:
        part=channel.recv(n-len(data));need(type(part) is bytes and 0<len(part)<=n-len(data),'SELF_IPC_EOF_OR_LENGTH');data+=part
    return data

def self_ipc_proven(rows):
    expected=[dict(family=f,stage=s,result='SUCCESS',kind=None,winerror=None,errno=None,wsa_post_exception=None) for f in (4,6) for s in ('socket','connect','accept','exchange')]+[dict(family=4,stage=s,result='SUCCESS',kind=None,winerror=None,errno=None,wsa_post_exception=None) for s in ('stock-socketpair','stock-proactor')]
    return rows==expected

def socket_error(error):
    def number(value):return value if type(value) is int and -(2**31)<=value<2**32 else None
    kind='TIMEOUT' if isinstance(error,TimeoutError) else 'REFUSED' if isinstance(error,ConnectionRefusedError) else 'PERMISSION' if isinstance(error,PermissionError) else 'OSERROR'
    return dict(kind=kind,winerror=number(getattr(error,'winerror',None)),errno=number(getattr(error,'errno',None)))

def socket_trace(family,stage,operation,trace=None):
    sink=network_diagnostics if trace is None else trace
    try:
        result=operation();sink.append(dict(family=family,stage=stage,result='SUCCESS',kind=None,winerror=None,errno=None,wsa_post_exception=None));return result,None
    except OSError as error:
        # Python/ctypes may already have touched WSA TLS: never treat this as authoritative.
        ws=ctypes.WinDLL('ws2_32');ws.WSAGetLastError.restype=ctypes.c_int;post=ws.WSAGetLastError()
        fact=socket_error(error);sink.append(dict(family=family,stage=stage,result='ERROR',wsa_post_exception=post,**fact));return None,fact

def network_denial(winerror,errno):
    # Timeout/refusal/unknown does not prove an OS policy denial. Numeric facts only.
    w=str(winerror) if type(winerror) is int and -(2**31)<=winerror<2**32 else 'UNKNOWN'
    e=str(errno) if type(errno) is int and -(2**31)<=errno<2**32 else 'UNKNOWN'
    need(type(winerror) is int and winerror==10013,'NETWORK_WIN32_'+w+'_ERRNO_'+e)

def file_identity(raw):
    need(type(raw) is bytes and len(raw)==24,'FILE_ID_STRUCTURE')
    volume=int.from_bytes(raw[:8],'little');low=int.from_bytes(raw[8:16],'little');high=int.from_bytes(raw[16:24],'little')
    return volume,f'{high:016X}{low:016X}'

def unavailable_handle(error):
    # ctypes can surface STATUS_INVALID_HANDLE as an SEH OSError under our debugger.
    # This is handle absence, never ACL-denial evidence. Unknown statuses stay blocked.
    need(type(error) is int and error in (6,-1073741816,0xC0000008),'FOREIGN_HANDLE_STATE_UNKNOWN')

def win32_denial(opened,error):
    need(type(opened) is bool and opened is False and type(error) is int and error==5,'WIN32_ACCESS_DENIED_NOT_PROVEN_'+(str(error) if type(error) is int else 'UNKNOWN'))
def case(name,fn):
    fn();rows.append(dict(name=name,outcome='PASS'))
def denied_open(path,access):
    k=ctypes.WinDLL('kernel32',use_last_error=True);k.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,W.LPVOID,W.DWORD,W.DWORD,W.HANDLE];k.CreateFileW.restype=W.HANDLE
    h=k.CreateFileW(str(path),access,7,None,3,0x200000,None);error=ctypes.get_last_error();opened=h not in (None,ctypes.c_void_p(-1).value)
    if opened:need(k.CloseHandle(W.HANDLE(h))!=0,'UNEXPECTED_HANDLE_CLOSE_FAILED')
    win32_denial(opened,error)
def main():
    cfg=json.loads((ROOT/'config.json').read_text());data=ROOT/'Data'
    # Remove current-directory/PATH DLL lookup before third-party or Grid imports.
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    need(kernel.SetDefaultDllDirectories(0x1000)!=0)
    dll_directory=os.add_dll_directory(str(ROOT/'DLLs'))
    case('isolated-python',lambda:need(sys.flags.isolated==1 and sys.flags.no_site==1 and sys.flags.dont_write_bytecode==1 and sys.executable.lower()==str(ROOT/'pythonw.exe').lower()))
    case('no-parent-secrets',lambda:need(not any(k in os.environ for k in ('GRID_PARENT_SECRET','GITHUB_TOKEN','ACTIONS_RUNTIME_TOKEN','TELEGRAM_BOT_TOKEN','PYTHONPATH','PYTHONHOME','PATH'))))
    def paths():
        for p in sys.path:need(pathlib.Path(p).resolve().is_relative_to(ROOT))
    case('closed-import-paths',paths)
    def own():
        p=data/'own.txt';p.write_text('synthetic');need(p.read_text()=='synthetic')
    case('own-data-rw',own)
    case('foreign-read-denied',lambda:denied_open(pathlib.Path(cfg['canary']),0x80000000))
    case('foreign-write-denied',lambda:denied_open(pathlib.Path(cfg['canary']),0x40000000))
    case('source-write-denied',lambda:denied_open(ROOT/'Source/grid/worker.py',0x40000000))
    def write_dac():
        k=ctypes.WinDLL('kernel32',use_last_error=True);k.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,W.LPVOID,W.DWORD,W.DWORD,W.HANDLE];k.CreateFileW.restype=W.HANDLE
        h=k.CreateFileW(str(ROOT/'Source/grid/worker.py'),0x40000,7,None,3,0x200000,None)
        if h not in (None,ctypes.c_void_p(-1).value):k.CloseHandle(W.HANDLE(h));raise RuntimeError('WRITE_DAC_OPENED')
        need(ctypes.get_last_error()==5)
    case('source-write-dac-denied',write_dac)
    def inherited():
        k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetFileInformationByHandleEx.argtypes=[W.HANDLE,ctypes.c_int,W.LPVOID,W.DWORD];k.GetFileInformationByHandleEx.restype=W.BOOL
        buf=ctypes.create_string_buffer(24)
        try:ok=k.GetFileInformationByHandleEx(W.HANDLE(cfg['inherited']),18,buf,24)
        except OSError as exc:unavailable_handle(getattr(exc,'winerror',None));return
        if ok:
            volume,identity=file_identity(buf.raw)
            need(volume!=cfg['expected_volume'] or identity!=cfg['expected_id'])
        else:unavailable_handle(ctypes.get_last_error())
    case('parent-handle-not-inherited',inherited)
    def parent_process():
        k=ctypes.WinDLL('kernel32',use_last_error=True);k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
        h=k.OpenProcess(0x10,False,cfg['parent_pid']);error=ctypes.get_last_error();opened=h is not None
        if opened:need(k.CloseHandle(W.HANDLE(h))!=0,'PARENT_HANDLE_CLOSE_FAILED')
        win32_denial(opened,error)
    case('parent-process-read-denied',parent_process)
    connects=[]
    for family,af,host,port in ((4,socket.AF_INET,'127.0.0.1',cfg['port']),(6,socket.AF_INET6,'::1',cfg['port6'])):
        server,error=socket_trace(family,'socket',lambda:socket.socket(af,socket.SOCK_STREAM))
        if server is not None:
            with server:
                server.setblocking(False)
                _,bound=socket_trace(family,'bind',lambda:server.bind((host,0)))
                if bound is None:
                    _,listened=socket_trace(family,'listen',lambda:server.listen(1))
                    if listened is None:
                        own,own_error=socket_trace(family,'socket',lambda:socket.socket(af,socket.SOCK_STREAM),self_loopback)
                        if own is not None:
                            with own:
                                own.settimeout(2)
                                _,own_error=socket_trace(family,'connect',lambda:own.connect(server.getsockname()),self_loopback)
                                if own_error is None:
                                    pair,pair_error=socket_trace(family,'accept',server.accept,self_loopback)
                                    if pair is not None:
                                        with pair[0] as peer:
                                            peer.settimeout(2)
                                            def exchange():
                                                need(own.getsockname()==peer.getpeername() and own.getpeername()==peer.getsockname(),'SELF_ENDPOINT_MISMATCH')
                                                own.sendall(b'own');need(recv_exact(peer,3)==b'own','SELF_DATA_MISMATCH');peer.sendall(b'ack');need(recv_exact(own,3)==b'ack','SELF_ACK_MISMATCH')
                                            socket_trace(family,'exchange',exchange,self_loopback)
                        accepted,ignored=socket_trace(family,'accept',server.accept)
                        if accepted is not None:accepted[0].close();raise BoundaryFailure('UNEXPECTED_ACCEPT')
        client,error=socket_trace(family,'client-socket',lambda:socket.socket(af,socket.SOCK_STREAM))
        if client is not None:
            with client:
                client.settimeout(2)
                _,error=socket_trace(family,'connect',lambda:client.connect((host,port)))
                connects.append(error)
        else:connects.append(error)
        network_isolation.append(dict(family=family,**isolation_diagnosis(host)))
    if len(self_loopback)==8 and all(r['result']=='SUCCESS' for r in self_loopback):
        previous=socket.getdefaulttimeout();socket.setdefaulttimeout(2)
        try:
            def stock_pair():
                a,b=socket.socketpair()
                with a,b:
                    a.settimeout(2);b.settimeout(2);a.sendall(b'ipc');need(recv_exact(b,3)==b'ipc','STOCK_SOCKETPAIR_DATA')
            socket_trace(4,'stock-socketpair',stock_pair,self_loopback)
            if self_loopback[-1]['result']=='SUCCESS':
                def stock_loop():
                    loop=asyncio.new_event_loop();loop.close()
                socket_trace(4,'stock-proactor',stock_loop,self_loopback)
        finally:socket.setdefaulttimeout(previous)
    def loopback():
        for error in connects:
            need(error is not None,'NETWORK_ALLOWED')
            need(error['kind']!='TIMEOUT','NETWORK_TIMEOUT_NOT_POLICY_PROOF')
            network_denial(error['winerror'],error['errno'])
        need(self_ipc_proven(self_loopback),'SELF_IPC_UNPROVEN')
        need(len(network_isolation)==2 and all(r['status']=='OBSERVED' for r in network_isolation),'NETWORK_ISOLATION_DIAGNOSIS_UNKNOWN')
    case('loopback-denied',loopback)
    def network(host,port):
        with socket.socket() as client:
            client.settimeout(2)
            _,error=socket_trace(4,'documentation-connect',lambda:client.connect((host,port)))
            need(error is not None,'NETWORK_ALLOWED');network_denial(error['winerror'],error['errno'])
    case('documentation-network-denied',lambda:network('192.0.2.1',9))
    def child():
        try:subprocess.run([sys.executable,'-I','-S','-c','raise SystemExit(0)'],check=True,timeout=3)
        except PermissionError:return
        except OSError as e:need(e.winerror in (5,1816));return
        raise RuntimeError('DESCENDANT_CREATED')
    case('subprocess-denied',child)
    def native():
        import _ssl,_socket,_ctypes,asyncpg,pydantic_core
        for m in (_ssl,_socket,_ctypes,asyncpg,pydantic_core):need(pathlib.Path(m.__file__).resolve().is_relative_to(ROOT))
    case('native-dependencies',native)
    async def grid():
        import grid.coordinator as co
        from grid.worker import Worker
        try:await asyncio.wait_for(co.startup(),5)
        except PermissionError as exc:
            import traceback
            need(any(t.filename.replace("\\","/").endswith("grid/db.py") for t in traceback.extract_tb(exc.__traceback__)))
        else:raise RuntimeError('COORDINATOR_NOT_REFUSED')
        need(co.control_runtime is None and co.background_tasks==[] and co.ingest_storage is None)
        rows.append(dict(name='real-coordinator-fails-closed',outcome='PASS'))
        worker=Worker();task=asyncio.create_task(worker.run())
        try:
            await asyncio.sleep(2);need(not task.done() and worker.runtime_state=='INFRA_ONLY' and not worker.wanted and not worker.trade_tasks and worker.db is None)
        finally:
            task.cancel();results=await asyncio.gather(task,return_exceptions=True)
        need(isinstance(results[0],asyncio.CancelledError))
        rows.append(dict(name='real-worker-infra-only',outcome='PASS'))
    asyncio.run(grid());paths()
    for m in tuple(sys.modules.values()):
        p=getattr(m,'__file__',None)
        if p:need(pathlib.Path(p).resolve().is_relative_to(ROOT))
    def modules():
        kernel.K32EnumProcessModules.argtypes=[W.HANDLE,ctypes.POINTER(W.HMODULE),W.DWORD,ctypes.POINTER(W.DWORD)];kernel.K32EnumProcessModules.restype=W.BOOL
        handles=(W.HMODULE*1024)();needed=W.DWORD()
        need(kernel.K32EnumProcessModules(W.HANDLE(-1),handles,ctypes.sizeof(handles),ctypes.byref(needed)) and 0<needed.value<=ctypes.sizeof(handles) and needed.value%ctypes.sizeof(W.HMODULE)==0)
        kernel.GetModuleFileNameW.argtypes=[W.HMODULE,W.LPWSTR,W.DWORD];kernel.GetModuleFileNameW.restype=W.DWORD
        windows=pathlib.Path(os.environ['SystemRoot']).resolve()
        for h in handles[:needed.value//ctypes.sizeof(W.HMODULE)]:
            buf=ctypes.create_unicode_buffer(32768);n=kernel.GetModuleFileNameW(h,buf,len(buf));need(0<n<len(buf));p=pathlib.Path(buf.value).resolve()
            need(p.is_relative_to(ROOT) or p.is_relative_to(windows/'System32') or p.is_relative_to(windows/'WinSxS'))
    case('dll-module-closure',modules)
    need([r['name'] for r in rows]==CASES)
    return cfg
if __name__=='__main__':
    if len(sys.argv)==1:
        print(json.dumps(dict(status='PLAN_ONLY',host_calls=0,physical='0/10 NOT_RUN',execute_authorized=False,cleanup_authorized=False)));raise SystemExit(0)
    native_scope(str(ROOT),socket.gethostname(),sys.argv[1:])
    error=None;cfg={}
    code=None
    try:
        cfg=json.loads((ROOT/'config.json').read_text());main()
    except BaseException as e:
        error=type(e).__name__;code=e.code if isinstance(e,BoundaryFailure) else ('WINDOWS_ERROR_'+str(e.winerror) if isinstance(e,OSError) and type(getattr(e,'winerror',None)) is int else None)
    result=dict(schema=1,head=cfg.get('head'),run_id=cfg.get('run_id'),attempt=cfg.get('attempt'),pid=os.getpid(),python_version=sys.version,status='PASS' if error is None else 'BLOCKED',error=error,error_code=code,cases=rows,network_diagnostics=network_diagnostics,network_isolation=network_isolation,self_loopback=self_loopback,physical='0/10 NOT_RUN',execute_authorized=False,cleanup_authorized=False,whole_system='PARTIAL')
    (ROOT/'Data/result.json').write_text(json.dumps(result),encoding='utf-8')
    raise SystemExit(0 if error is None else 1)
