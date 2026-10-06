import hashlib, os, pathlib, shutil, time, zipfile

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

def install_release(package_path,version,install_root):
    root=pathlib.Path(install_root)
    releases=root/"releases"; releases.mkdir(parents=True,exist_ok=True)
    target=releases/version
    staging=releases/(version+".staging")
    replaced=releases/(version+".replaced")
    # Recover a power loss that happened after old target -> .replaced but
    # before staging -> target. Never discard the last runnable copy.
    if not target.exists() and replaced.exists():
        os.replace(replaced,target)
    if staging.exists(): shutil.rmtree(staging)
    if replaced.exists(): shutil.rmtree(replaced)
    staging.mkdir(parents=True)
    try:
        _safe_extract(package_path,staging)
        if target.exists():
            os.replace(target,replaced)
        try:
            os.replace(staging,target)
        except Exception:
            if not target.exists() and replaced.exists():
                os.replace(replaced,target)
            raise
        shutil.rmtree(replaced,ignore_errors=True)
    except Exception:
        shutil.rmtree(staging,ignore_errors=True)
        raise
    return target

def _release_runnable(target):
    return (target/"run_worker.py").exists() or (target/"run_coordinator.py").exists()

def _read_marker(root,name):
    p=pathlib.Path(root)/name
    try:return p.read_text(encoding="utf-8").strip() or None
    except (OSError,UnicodeError):return None

def _write_marker(root,name,value):
    root=pathlib.Path(root); marker=root/name; tmp=root/(name+".tmp")
    with open(tmp,"w",encoding="utf-8") as f:
        f.write(str(value)); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,marker)

def current_version(install_root):
    return _read_marker(install_root,"current.version")

def previous_version(install_root):
    return _read_marker(install_root,"previous.version")

def switch_current(install_root,version,record_previous=True):
    root=pathlib.Path(install_root)
    target=root/"releases"/version
    if not _release_runnable(target):
        raise ValueError("release is not runnable")
    current=current_version(root)
    if record_previous and current and current!=version:
        _write_marker(root,"previous.version",current)
    _write_marker(root,"current.version",version)

def _runnable_releases(install_root):
    releases=pathlib.Path(install_root)/"releases"
    if not releases.exists(): return []
    out=[p for p in releases.iterdir()
         if p.is_dir() and not p.name.endswith(".staging") and _release_runnable(p)]
    return sorted(out,key=lambda p:p.stat().st_mtime,reverse=True)

def rollback(install_root):
    root=pathlib.Path(install_root); releases=root/"releases"
    if not releases.exists(): return None
    current=current_version(root)
    explicit=previous_version(root)
    prev=None
    if explicit and explicit!=current and _release_runnable(releases/explicit):
        prev=explicit
    if not prev:
        prev=next((p.name for p in _runnable_releases(root) if p.name!=current),None)
    if prev:
        # Preserve the failed/current release as the next rollback target.
        switch_current(root,prev,record_previous=True)
    return prev

def cleanup_release_storage(install_root,data_root,keep_recent=2,older_than_seconds=86400):
    """Bound immutable release/update storage without touching current or rollback targets."""
    install_root=pathlib.Path(install_root); data_root=pathlib.Path(data_root)
    releases=install_root/"releases"; cutoff=time.time()-max(3600,int(older_than_seconds))
    protected={v for v in (current_version(install_root),previous_version(install_root)) if v}
    recent={p.name for p in _runnable_releases(install_root)[:max(0,int(keep_recent))]}
    protected|=recent
    removed_releases=[]; removed_staging=[]; removed_downloads=[]; removed_upgrades=[]

    if releases.exists():
        for p in releases.iterdir():
            try:
                if not p.is_dir() or p.stat().st_mtime>=cutoff: continue
                if p.name.endswith(".staging"):
                    shutil.rmtree(p); removed_staging.append(p.name)
                elif p.name not in protected and _release_runnable(p):
                    shutil.rmtree(p); removed_releases.append(p.name)
            except OSError:
                pass

    downloads=data_root/"downloads"
    if downloads.exists():
        for p in downloads.iterdir():
            try:
                if p.is_file() and p.stat().st_mtime<cutoff and p.suffix in (".zip",".part"):
                    p.unlink(); removed_downloads.append(p.name)
            except OSError:
                pass

    # Manual/local upgrade workspaces are reproducible from verified immutable artifacts.
    if data_root.exists():
        for p in data_root.glob("upgrade-*"):
            try:
                if p.is_dir() and p.stat().st_mtime<cutoff:
                    shutil.rmtree(p); removed_upgrades.append(p.name)
            except OSError:
                pass

    return {"releases":removed_releases,"staging":removed_staging,
            "downloads":removed_downloads,"upgrades":removed_upgrades,
            "protected":sorted(protected)}
