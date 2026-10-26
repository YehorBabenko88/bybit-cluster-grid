"""Actual CPython/Grid negative lifecycle probe. Only the native hosted parent launches it."""
import asyncio,ctypes,ctypes.wintypes as W,json,os,pathlib,socket,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parent
CASES=['isolated-python','no-parent-secrets','closed-import-paths','own-data-rw','foreign-read-denied','foreign-write-denied','source-write-denied','source-write-dac-denied','parent-handle-not-inherited','loopback-denied','documentation-network-denied','subprocess-denied','native-dependencies','real-coordinator-fails-closed','real-worker-infra-only','dll-module-closure']
rows=[]
def need(ok):
    if not ok:raise RuntimeError('BOUNDARY_NOT_PROVEN')
def case(name,fn):
    fn();rows.append(dict(name=name,outcome='PASS'))
def denied(action):
    try:action()
    except PermissionError as e:
        need(e.winerror==5);return
    raise RuntimeError('EXPECTED_ACCESS_DENIED')
def main():
    cfg=json.loads((ROOT/'config.json').read_text());data=ROOT/'Data'
    # Remove current-directory/PATH DLL lookup before third-party or Grid imports.
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    need(kernel.SetDefaultDllDirectories(0x1000)!=0)
    dll_directory=os.add_dll_directory(str(ROOT/'DLLs'))
    case('isolated-python',lambda:need(sys.flags.isolated==1 and sys.flags.no_site==1 and sys.flags.dont_write_bytecode==1 and sys.executable.lower()==str(ROOT/'python.exe').lower()))
    case('no-parent-secrets',lambda:need(not any(k in os.environ for k in ('GRID_PARENT_SECRET','GITHUB_TOKEN','ACTIONS_RUNTIME_TOKEN','TELEGRAM_BOT_TOKEN','PYTHONPATH','PYTHONHOME','PATH'))))
    def paths():
        for p in sys.path:need(pathlib.Path(p).resolve().is_relative_to(ROOT))
    case('closed-import-paths',paths)
    def own():
        p=data/'own.txt';p.write_text('synthetic');need(p.read_text()=='synthetic')
    case('own-data-rw',own)
    case('foreign-read-denied',lambda:denied(lambda:pathlib.Path(cfg['canary']).read_bytes()))
    case('foreign-write-denied',lambda:denied(lambda:pathlib.Path(cfg['canary']).write_bytes(b'not-allowed')))
    case('source-write-denied',lambda:denied(lambda:(ROOT/'Source/grid/worker.py').open('ab')))
    def write_dac():
        k=ctypes.WinDLL('kernel32',use_last_error=True);k.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,W.LPVOID,W.DWORD,W.DWORD,W.HANDLE];k.CreateFileW.restype=W.HANDLE
        h=k.CreateFileW(str(ROOT/'Source/grid/worker.py'),0x40000,7,None,3,0x200000,None)
        if h not in (None,ctypes.c_void_p(-1).value):k.CloseHandle(W.HANDLE(h));raise RuntimeError('WRITE_DAC_OPENED')
        need(ctypes.get_last_error()==5)
    case('source-write-dac-denied',write_dac)
    def inherited():
        k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetFileInformationByHandleEx.argtypes=[W.HANDLE,ctypes.c_int,W.LPVOID,W.DWORD];k.GetFileInformationByHandleEx.restype=W.BOOL
        buf=ctypes.create_string_buffer(24);ok=k.GetFileInformationByHandleEx(W.HANDLE(cfg['inherited']),18,buf,24)
        if ok:
            volume=int.from_bytes(buf.raw[:8],'little');identity=buf.raw[8:24].hex().upper()
            need(volume!=cfg['expected_volume'] or identity!=cfg['expected_id'])
        else:need(ctypes.get_last_error()==6)
    case('parent-handle-not-inherited',inherited)
    def network(host,port):
        with socket.socket() as s:
            s.settimeout(2)
            try:s.connect((host,port))
            except OSError as e:need(getattr(e,'winerror',None)==10013 or e.errno in (13,10013));return
            raise RuntimeError('NETWORK_ALLOWED')
    case('loopback-denied',lambda:network('127.0.0.1',cfg['port']))
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
    error=None;cfg={}
    try:cfg=main()
    except BaseException as e:error=type(e).__name__
    result=dict(schema=1,head=cfg.get('head'),run_id=cfg.get('run_id'),attempt=cfg.get('attempt'),pid=os.getpid(),python_version=sys.version,status='PASS' if error is None else 'BLOCKED',error=error,cases=rows,physical='0/10 NOT_RUN',execute_authorized=False,cleanup_authorized=False,whole_system='PARTIAL')
    (ROOT/'Data/result.json').write_text(json.dumps(result),encoding='utf-8')
    raise SystemExit(0 if error is None else 1)
