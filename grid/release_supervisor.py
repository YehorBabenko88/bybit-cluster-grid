"""Run a Grid service child and confirm a pending release after stable uptime."""
import argparse, os, pathlib, subprocess, sys, threading, time, urllib.request, json

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
