"""Detached, verified self-update helper for the CONTROL node."""
import argparse, asyncio, json, os, pathlib, subprocess, sys, time
from .agent_commands import _download
from .update_manager import verify_package,install_release,switch_current,current_version,mark_pending,clear_pending

def _roots():
    pf=pathlib.Path(os.environ.get("ProgramFiles",r"C:\Program Files"))
    pd=pathlib.Path(os.environ.get("ProgramData",r"C:\ProgramData"))
    return pf/"BybitClusterGrid",pd/"BybitClusterGrid"

def _status(data_root,**payload):
    path=pathlib.Path(data_root)/"control-update-status.json"
    tmp=path.with_name(path.name+".tmp")
    payload["updated_at"]=time.time()
    with open(tmp,"w",encoding="utf-8") as f:
        json.dump(payload,f,separators=(",",":"));f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def _unlock_own(data_root):
    lock=pathlib.Path(data_root)/"control-update.lock"
    try:
        if lock.read_text(encoding="ascii").strip()==str(os.getpid()):
            lock.unlink(missing_ok=True)
    except OSError:pass

def _role_preflight(target,data_root):
    python=data_root/"runtime"/"venv"/"Scripts"/"python.exe"
    preflight=data_root/"installer"/"preflight.ps1"
    p=subprocess.run(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(preflight),
        "-ReleaseDir",str(target),"-Python",str(python),"-Mode","CONTROL"],
        capture_output=True,text=True,timeout=300)
    if p.returncode:
        raise RuntimeError("CONTROL release preflight failed: "+(p.stderr or p.stdout)[-2000:])

def _restart_tasks():
    # Coordinator restart activates current.version. Archive follows the same
    # marker but is not authoritative for rollback.
    script=(
      'Stop-ScheduledTask -TaskName "BybitClusterGridArchivePipeline" -ErrorAction SilentlyContinue; '
      'Stop-ScheduledTask -TaskName "BybitClusterGridCoordinator" -ErrorAction SilentlyContinue; '
      'Start-Sleep -Seconds 2; '
      'Start-ScheduledTask -TaskName "BybitClusterGridCoordinator"; '
      'Start-ScheduledTask -TaskName "BybitClusterGridArchivePipeline" -ErrorAction SilentlyContinue'
    )
    flags=(getattr(subprocess,"CREATE_NO_WINDOW",0) |
           getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0) |
           getattr(subprocess,"DETACHED_PROCESS",0))
    subprocess.Popen(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-Command",script],
                     creationflags=flags,close_fds=True)

async def apply(version,url,sha256):
    if not str(url).lower().startswith("https://"):
        raise ValueError("release URL must use HTTPS")
    install_root,data_root=_roots()
    lock=data_root/"control-update.lock"
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:
        try: age=time.time()-lock.stat().st_mtime
        except OSError: age=0
        if age<=1800: raise RuntimeError("another CONTROL update is already running")
        lock.unlink(missing_ok=True)
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    with os.fdopen(fd,"w",encoding="ascii") as f:
        f.write(str(os.getpid()));f.flush();os.fsync(f.fileno())
    downloads=data_root/"downloads";downloads.mkdir(parents=True,exist_ok=True)
    _status(data_root,state="downloading",version=version)
    part=downloads/(version+".control.zip.part")
    final=downloads/(version+".control.zip")
    await _download(url,part)
    if not verify_package(part,sha256):
        part.unlink(missing_ok=True)
        raise RuntimeError("release SHA256 mismatch")
    os.replace(part,final)
    target=install_release(final,version,install_root)
    _status(data_root,state="preflight",version=version)
    _role_preflight(target,data_root)
    previous=current_version(install_root)
    mark_pending(install_root,version)
    try:
        switch_current(install_root,version)
    except Exception:
        clear_pending(install_root)
        raise
    _status(data_root,state="staged",version=version,previous=previous)
    # Let the invoking HTTP/Telegram handler commit its response/cursor before
    # the coordinator task is terminated.
    await asyncio.sleep(3)
    _restart_tasks()
    _unlock_own(data_root)
    return {"state":"control_update_staged","version":version,"previous":previous}

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--version",required=True)
    ap.add_argument("--url",required=True)
    ap.add_argument("--sha256",required=True)
    a=ap.parse_args(argv)
    try:
        result=asyncio.run(apply(a.version,a.url,a.sha256))
        print(json.dumps(result))
        return 0
    except Exception as e:
        try:
            _,data_root=_roots();_status(data_root,state="failed",version=getattr(a,"version",""),error=str(e)[:2000])
        except Exception:pass
        try:_unlock_own(data_root)
        except Exception:pass
        print(json.dumps({"state":"failed","error":str(e)[:2000]}),file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
