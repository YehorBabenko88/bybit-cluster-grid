"""Run a Grid service child and confirm a pending release after stable uptime."""
import argparse, os, pathlib, subprocess, sys, threading, time

def _read(path):
    try:return pathlib.Path(path).read_text(encoding="utf-8-sig").strip()
    except OSError:return ""

def _atomic(path,value):
    p=pathlib.Path(path); tmp=p.with_name(p.name+".tmp")
    with open(tmp,"w",encoding="utf-8") as f:
        f.write(str(value)); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,p)

def _confirm(root,version,proc,delay):
    time.sleep(delay)
    root=pathlib.Path(root)
    pending=root/"pending.version"
    if _read(pending)!=version or proc.poll() is not None:return
    pending.unlink(missing_ok=True)
    (root/"pending-crashes.txt").unlink(missing_ok=True)

def _after_exit(root,version,runtime):
    root=pathlib.Path(root); pending=root/"pending.version"
    if _read(pending)!=version or runtime>=60:return False
    crash=root/"pending-crashes.txt"
    try:count=int(_read(crash) or "0")
    except ValueError:count=0
    count+=1; _atomic(crash,count)
    if count<3:return False
    prev=_read(root/"previous.version")
    candidate=root/"releases"/prev
    if not prev or prev==version or not candidate.is_dir():return False
    _atomic(root/"current.version",prev)
    pending.unlink(missing_ok=True); crash.unlink(missing_ok=True)
    return True

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--install-root",required=True)
    ap.add_argument("--version",required=True)
    ap.add_argument("--cwd",required=True)
    ap.add_argument("--stable-seconds",type=int,default=60)
    ap.add_argument("command",nargs=argparse.REMAINDER)
    a=ap.parse_args(argv)
    cmd=list(a.command)
    if cmd and cmd[0]=="--":cmd=cmd[1:]
    if not cmd:raise SystemExit("missing child command")
    started=time.monotonic()
    proc=subprocess.Popen(cmd,cwd=a.cwd)
    t=threading.Thread(target=_confirm,args=(a.install_root,a.version,proc,max(1,a.stable_seconds)),daemon=True)
    t.start()
    code=proc.wait()
    runtime=time.monotonic()-started
    rolled=_after_exit(a.install_root,a.version,runtime)
    return 75 if rolled else int(code)

if __name__=="__main__":
    raise SystemExit(main())
