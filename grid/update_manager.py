import hashlib, logging, os, pathlib, shutil
log=logging.getLogger("update_manager")

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def verify_package(path,expected_sha):
    return sha256_file(path).lower()==expected_sha.lower()

def install_release(package_path,version,install_root):
    root=pathlib.Path(install_root)
    releases=root/"releases"; releases.mkdir(parents=True,exist_ok=True)
    target=releases/version; staging=releases/(version+".staging")
    if staging.exists(): shutil.rmtree(staging)
    staging.mkdir(parents=True)
    shutil.unpack_archive(package_path,staging)
    if target.exists(): shutil.rmtree(target)
    os.replace(staging,target)
    return target

def switch_current(install_root,version):
    root=pathlib.Path(install_root)
    tmp=root/"current.version.tmp"; marker=root/"current.version"
    tmp.write_text(version,encoding="utf-8")
    os.replace(tmp,marker)

def current_version(install_root):
    p=pathlib.Path(install_root)/"current.version"
    return p.read_text(encoding="utf-8").strip() if p.exists() else None

def rollback(install_root):
    root=pathlib.Path(install_root)/"releases"
    current=current_version(install_root)
    versions=sorted([p.name for p in root.iterdir() if p.is_dir() and not p.name.endswith(".staging")],reverse=True)
    prev=next((v for v in versions if v!=current),None)
    if prev: switch_current(install_root,prev)
    return prev
