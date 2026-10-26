"""Create measured inputs only on a GitHub-hosted Windows runner. Never execute Python."""
import hashlib,io,json,os,re,sys,subprocess,zipfile
from pathlib import Path
from tools.check_ddl_free_ci import verify_checkout
ROOT=Path(__file__).resolve().parents[1]

def need(ok):
    if not ok: raise ValueError("PYTHON_BUNDLE_REFUSED")

def relative(name):
    need(type(name) is str and 0<len(name)<=240)
    for p in name.split("/"):
        need(re.fullmatch(r"[A-Za-z0-9_.-]+",p) is not None and p not in (".","..") and not p.endswith("."))
        need(p.split(".")[0].upper() not in {"CON","PRN","AUX","NUL",*("COM"+str(n) for n in range(1,10)),*("LPT"+str(n) for n in range(1,10))})
    return name

def hosted():
    expected=dict(GITHUB_ACTIONS="true",RUNNER_ENVIRONMENT="github-hosted",GITHUB_REPOSITORY="YehorBabenko88/bybit-cluster-grid",GITHUB_JOB="python-containment")
    need(all(os.environ.get(k)==v for k,v in expected.items()))
    need(re.fullmatch("[0-9a-f]{40}",os.environ.get("EXACT_HEAD_SHA","")) is not None)
    for k in ("GITHUB_RUN_ID","GITHUB_RUN_ATTEMPT"):need(re.fullmatch("[1-9][0-9]{0,19}",os.environ.get(k,"")) is not None)

def regular(path):
    for p in (path,*path.parents):
        st=p.lstat();need(not p.is_symlink() and not (getattr(st,"st_file_attributes",0)&0x400))
    need(path.is_file() and path.stat().st_nlink==1)
    b=path.read_bytes();need(0<=len(b)<=32*1024*1024)
    return b

def build():
    hosted();need(sys.platform=="win32" and os.environ.get("COMPUTERNAME","").upper() not in ("PC4","LS5"))
    head=os.environ["EXACT_HEAD_SHA"];verify_checkout(ROOT,head)
    output=ROOT/"python-input";output.mkdir();files={};origins={};folded=set();total=0
    def add(name,b,origin):
        nonlocal total
        relative(name);need(name.casefold() not in folded and len(files)<20000 and len(b)<=32*1024*1024)
        total+=len(b);need(total<=512*1024*1024);folded.add(name.casefold());p=output/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        files[name]=dict(Sha256=hashlib.sha256(b).hexdigest().upper(),Length=len(b));origins[name]=origin
    base=Path(sys.base_prefix)
    add("python.exe",regular(base/"python.exe"),"setup-python")
    for p in sorted(base.glob("*.dll")):add(p.name,regular(p),"setup-python")
    for p in sorted((base/"DLLs").glob("*")):
        if p.is_file() and p.suffix.lower() in (".pyd",".dll"):add("DLLs/"+p.name,regular(p),"setup-python")
    std=io.BytesIO()
    with zipfile.ZipFile(std,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted((base/"Lib").rglob("*")):
            rel=p.relative_to(base/"Lib")
            if any(x in ("site-packages","__pycache__","test","tests","tkinter","idlelib","ensurepip","turtledemo") for x in rel.parts):continue
            if p.is_file() and p.suffix==".py":z.writestr(zipfile.ZipInfo(relative(rel.as_posix())),regular(p),compress_type=zipfile.ZIP_DEFLATED)
    add("stdlib.zip",std.getvalue(),"setup-python-stdlib")
    for p in sorted((base/"Lib"/"site-packages").rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix.lower() not in (".pyc",".exe"):
            add("Site/"+p.relative_to(base/"Lib"/"site-packages").as_posix(),regular(p),"pinned-requirements-resolved")
    for n in subprocess.check_output(["git","ls-files","grid"],cwd=ROOT,text=True).splitlines():
        if n.endswith(".py"):add("Source/"+n,subprocess.check_output(["git","show",head+":"+n],cwd=ROOT),"git:"+head)
    add("driver.py",subprocess.check_output(["git","show",head+":integration/windows_python_probe.py"],cwd=ROOT),"git:"+head)
    pth="stdlib.zip\nDLLs\nSite\nSource\n"
    add(f"python{sys.version_info.major}{sys.version_info.minor}._pth",pth.encode(),"fixed-isolated-paths")
    add("python._pth",pth.encode(),"fixed-isolated-paths")
    manifest=dict(Schema=1,Head=head,Run=os.environ["GITHUB_RUN_ID"],Attempt=os.environ["GITHUB_RUN_ATTEMPT"],Python=sys.version,Files=files,Origins=origins)
    raw=json.dumps(manifest,sort_keys=True).encode();(output/"manifest.json").write_bytes(raw);verify_checkout(ROOT,head)
    digest=hashlib.sha256(raw).hexdigest();print(json.dumps(dict(head=head,files=len(files),bytes=total,manifest_sha256=digest)))
    with open(os.environ["GITHUB_ENV"],"a",encoding="utf-8") as f:f.write("PYTHON_INPUT_SHA256="+digest+"\n")

if __name__=="__main__":build()
