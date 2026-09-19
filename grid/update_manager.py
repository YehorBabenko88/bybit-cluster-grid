import hashlib, os, pathlib, shutil, zipfile

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def verify_package(path,expected_sha):
    return bool(expected_sha) and sha256_file(path).lower()==expected_sha.lower()

def _safe_extract(zip_path,destination):
    dest=pathlib.Path(destination).resolve()
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            target=(dest/info.filename).resolve()
            if target!=dest and dest not in target.parents:
                raise ValueError("unsafe path in release archive")
        z.extractall(dest)

def _version_key(v):
    parts=[]
    for p in v.replace("-",".").split("."):
        parts.append((0,int(p)) if p.isdigit() else (1,p))
    return tuple(parts)

def install_release(package_path,version,install_root):
    root=pathlib.Path(install_root)
    releases=root/"releases"; releases.mkdir(parents=True,exist_ok=True)
    target=releases/version; staging=releases/(version+".staging")
    if staging.exists(): shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        _safe_extract(package_path,staging)
        if target.exists(): shutil.rmtree(target)
        os.replace(staging,target)
    except Exception:
        shutil.rmtree(staging,ignore_errors=True)
        raise
    return target

def switch_current(install_root,version):
    root=pathlib.Path(install_root)
    target=root/"releases"/version
    if not (target/"run_worker.py").exists():
        raise ValueError("release is not runnable")
    tmp=root/"current.version.tmp"; marker=root/"current.version"
    tmp.write_text(version,encoding="utf-8")
    os.replace(tmp,marker)

def current_version(install_root):
    p=pathlib.Path(install_root)/"current.version"
    return p.read_text(encoding="utf-8").strip() if p.exists() else None

def rollback(install_root):
    root=pathlib.Path(install_root)/"releases"
    if not root.exists(): return None
    current=current_version(install_root)
    versions=sorted(
        [p.name for p in root.iterdir() if p.is_dir() and not p.name.endswith(".staging")],
        key=_version_key,reverse=True
    )
    if current in versions:
        i=versions.index(current)
        candidates=versions[i+1:]
    else:
        candidates=versions
    prev=next((v for v in candidates if (root/v/"run_worker.py").exists()),None)
    if prev: switch_current(install_root,prev)
    return prev
