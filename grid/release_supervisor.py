"""Run a Grid service child and confirm a pending release after stable uptime."""
import argparse, contextlib, ctypes, hashlib, json, os, pathlib, subprocess, sys, threading, time, urllib.request

@contextlib.contextmanager
def _single_instance(install_root, mode):
    """Hold a Windows named mutex for the complete lifetime of the child."""
    if os.name != "nt":
        yield
        return
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel.ReleaseMutex.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    identity = str(pathlib.Path(install_root).resolve()).casefold() + ":" + str(mode)
    name = "Global\\BybitGridSupervisor_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
    handle = kernel.CreateMutexW(None, False, name)
    if not handle:
        raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
    acquired = False
    try:
        status = kernel.WaitForSingleObject(handle, 0)
        if status not in (0, 0x80):
            if status == 0x102:
                raise RuntimeError("Grid release supervisor already running")
            raise OSError(ctypes.get_last_error(), "WaitForSingleObject failed")
        acquired = True
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def _read(path):
    try:return pathlib.Path(path).read_text(encoding="utf-8-sig").strip()
    except OSError:return ""

def _atomic(path,value):
    p=pathlib.Path(path); tmp=p.with_name(p.name+".tmp")
    with open(tmp,"w",encoding="utf-8") as f:
        f.write(str(value)); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,p)

def _ready(mode,proc,ready_file):
    if mode=='worker':
        try:return pathlib.Path(ready_file).read_text(encoding='ascii').strip()==str(proc.pid)
        except (OSError,ValueError):return False
    if mode=='coordinator':
        try:
            with urllib.request.urlopen('http://127.0.0.1:8765/health',timeout=2) as resp:
                if resp.status!=200:return False
                payload=json.load(resp)
                return payload.get('ok') is True and payload.get('pid')==proc.pid
        except Exception:return False
    return False

def _confirm(root,version,proc,delay,mode=None,ready_file=None):
    time.sleep(delay)
    root=pathlib.Path(root)
    pending=root/"pending.version"
    if _read(pending)!=version or proc.poll() is not None:return
    if mode and not _ready(mode,proc,ready_file):return
    # Do not confirm a release while pointer recovery is still unresolved.
    if (root/"switch-journal.json").exists():return
    pending.unlink(missing_ok=True)
    (root/"pending-crashes.txt").unlink(missing_ok=True)

def _after_exit(root,version,runtime):
    root=pathlib.Path(root); pending=root/"pending.version"
    if _read(pending)!=version:return False
    if (root/"switch-journal.json").exists():return False
    if _read(root/"current.version")!=version:return False
    crash=root/"pending-crashes.txt"
    try:count=int(_read(crash) or "0")
    except ValueError:count=0
    count+=1; _atomic(crash,count)
    if count<3:return False
    prev=_read(root/"previous.version")
    candidate=root/"releases"/prev
    runnable=(candidate/"run_worker.py").exists() or (candidate/"grid"/"coordinator.py").exists()
    if not prev or prev==version or not runnable:return False
    _atomic(root/"current.version",prev)
    _atomic(root/"failed.version",version)
    pending.unlink(missing_ok=True); crash.unlink(missing_ok=True)
    return True

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--install-root",required=True)
    ap.add_argument("--version",required=True)
    ap.add_argument("--cwd",required=True)
    ap.add_argument("--stable-seconds",type=int,default=60)
    ap.add_argument("--readiness",choices=("worker","coordinator"))
    ap.add_argument("command",nargs=argparse.REMAINDER)
    a=ap.parse_args(argv)
    cmd=list(a.command)
    if cmd and cmd[0]=="--":cmd=cmd[1:]
    if not cmd:raise SystemExit("missing child command")
    with _single_instance(a.install_root, a.readiness):
        started=time.monotonic()
        env=os.environ.copy()
        ready_file=str(pathlib.Path(a.install_root)/"release-ready.txt")
        if a.readiness=="worker":
            pathlib.Path(ready_file).unlink(missing_ok=True)
            env["GRID_RELEASE_READY_FILE"]=ready_file
        proc=subprocess.Popen(cmd,cwd=a.cwd,env=env)
        t=threading.Thread(target=_confirm,args=(a.install_root,a.version,proc,max(1,a.stable_seconds),a.readiness,ready_file),daemon=True)
        t.start()
        code=proc.wait()
        runtime=time.monotonic()-started
        rolled=_after_exit(a.install_root,a.version,runtime)
        return 75 if rolled else int(code)
    
if __name__=="__main__":
    raise SystemExit(main())
