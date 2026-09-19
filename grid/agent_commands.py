import asyncio, logging, os, pathlib, subprocess, tempfile, collections
import aiohttp
from .update_manager import rollback,verify_package,install_release,switch_current,current_version
log=logging.getLogger("agent_commands")

def _roots():
    program_files=os.environ.get("ProgramFiles",r"C:\Program Files")
    program_data=os.environ.get("ProgramData",r"C:\ProgramData")
    return pathlib.Path(program_files)/"BybitClusterGrid",pathlib.Path(program_data)/"BybitClusterGrid"

async def _download(url,path):
    async with aiohttp.ClientSession() as session:
        async with session.get(url,timeout=aiohttp.ClientTimeout(total=600)) as r:
            r.raise_for_status()
            with open(path,"wb") as out:
                async for chunk in r.content.iter_chunked(1024*1024):
                    out.write(chunk)

async def _update(payload):
    version=str(payload["version"])
    url=str(payload["package_url"])
    expected=str(payload["sha256"])
    if not url.lower().startswith("https://"):
        raise ValueError("release URL must use HTTPS")
    install_root,data_root=_roots()
    downloads=data_root/"downloads"; downloads.mkdir(parents=True,exist_ok=True)
    package=downloads/(version+".zip.part")
    await _download(url,package)
    if not verify_package(package,expected):
        package.unlink(missing_ok=True)
        raise RuntimeError("release SHA256 mismatch")
    final=downloads/(version+".zip")
    os.replace(package,final)
    target=install_release(final,version,install_root)
    python=data_root/"runtime"/"venv"/"Scripts"/"python.exe"
    preflight=data_root/"installer"/"preflight.ps1"
    p=subprocess.run([
        "powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(preflight),
        "-ReleaseDir",str(target),"-Python",str(python)
    ],capture_output=True,text=True,timeout=300)
    if p.returncode:
        raise RuntimeError("release preflight failed: "+(p.stderr or p.stdout)[-2000:])
    previous=current_version(install_root)
    switch_current(install_root,version)
    return {"state":"update_staged","version":version,"previous":previous}

def _grid_log_tail(lines=120,max_bytes=24000):
    _,data_root=_roots()
    candidates=[data_root/"logs"/"grid.jsonl",pathlib.Path("logs")/"grid.jsonl"]
    path=next((p for p in candidates if p.exists() and p.is_file()),None)
    if not path: return {"lines":[],"message":"grid log not found"}
    lines=max(1,min(int(lines),300))
    with open(path,"rb") as fh:
        dq=collections.deque(fh,maxlen=lines)
    text_lines=[]
    used=0
    for raw in reversed(dq):
        line=raw.decode("utf-8","replace").rstrip()
        size=len(line.encode("utf-8"))
        if used+size>max_bytes: break
        text_lines.append(line); used+=size
    text_lines.reverse()
    return {"lines":text_lines,"bytes":used}

async def execute_command(worker,cmd):
    action=cmd["action"]; payload=cmd.get("payload") or {}
    if action=="pause":
        worker.enabled=False
        worker.wanted=set()
        await worker.reconcile()
        return {"state":"paused"}
    if action=="resume":
        worker.enabled=True
        return {"state":"running"}
    if action=="log_tail":
        return _grid_log_tail(payload.get("lines",120))
    if action=="restart":
        asyncio.get_running_loop().call_later(1.0,lambda:os._exit(75))
        return {"state":"restarting"}
    if action=="update":
        result=await _update(payload)
        asyncio.get_running_loop().call_later(2.0,lambda:os._exit(75))
        return result
    if action=="rollback":
        install_root,_=_roots()
        version=rollback(install_root)
        if not version: raise RuntimeError("no previous release")
        asyncio.get_running_loop().call_later(1.0,lambda:os._exit(75))
        return {"state":"rollback","version":version}
    if action=="uninstall":
        _,data_root=_roots()
        script=data_root/"installer"/"uninstall.ps1"
        if not script.exists(): raise RuntimeError("local uninstall script missing")
        args=["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(script)]
        if payload.get("purge_data"): args.append("--purge-data")
        subprocess.Popen(args,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        return {"state":"uninstall_started"}
    raise ValueError(f"unsupported command: {action}")
