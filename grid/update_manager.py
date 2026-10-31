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
    target=pathlib.Path(target)
    return ((target/"unified-release.json").is_file() and all((target/"modules"/name).is_dir() for name in ("unified-system","grid","strattester","math","meta_analyse","terminan")) or
            (target/"run_worker.py").exists() or
            (target/"run_coordinator.py").exists() or
            (target/"grid"/"coordinator.py").exists())

def _read_marker(root,name):
    p=pathlib.Path(root)/name
    try:return p.read_text(encoding="utf-8").strip() or None
    except (OSError,UnicodeError):return None

def _write_marker(root,name,value):
    import tempfile
    root=pathlib.Path(root);marker=root/name
    fd,tmp=tempfile.mkstemp(prefix='.'+name+'-',suffix='.tmp',dir=root)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            f.write(str(value)); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,marker)
    finally:
        try:pathlib.Path(tmp).unlink()
        except FileNotFoundError:pass

def current_version(install_root):
    return _read_marker(install_root,"current.version")

def previous_version(install_root):
    return _read_marker(install_root,"previous.version")

def pending_version(install_root):
    return _read_marker(install_root,"pending.version")

def clear_pending(install_root):
    root=pathlib.Path(install_root)
    for name in ("pending.version","pending-crashes.txt","pending-started.txt"):
        try:(root/name).unlink()
        except FileNotFoundError:pass

def switch_current(install_root,version,record_previous=True):
    root=pathlib.Path(install_root)
    target=root/"releases"/version
    if not _release_runnable(target):
        raise ValueError("release is not runnable")
    current=current_version(root)
    if record_previous and current and current!=version:
        _write_marker(root,"previous.version",current)
    _write_marker(root,"current.version",version)

def mark_pending(install_root,version):
    _write_marker(install_root,"pending.version",version)
    for name in ("pending-crashes.txt","pending-started.txt"):
        try:(pathlib.Path(install_root)/name).unlink()
        except FileNotFoundError:pass

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
        clear_pending(root)
    return prev

def cleanup_release_storage(install_root,data_root,keep_recent=2,older_than_seconds=86400):
    """Bound immutable release/update storage without touching current or rollback targets."""
    install_root=pathlib.Path(install_root); data_root=pathlib.Path(data_root)
    releases=install_root/"releases"; cutoff=time.time()-max(3600,int(older_than_seconds))
    protected={v for v in (current_version(install_root),previous_version(install_root),pending_version(install_root)) if v}
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


def stage_unified_release(artifacts, manifest, manifest_bytes, install_root,*,git_executable,git_sha256,signature_bytes):
    """Immutable v3 extension; preserve every legacy installer/marker contract.

    Caller verifies detached signature and enrollment first. ZIP files are
    opened once and hashed from the same bytes that are extracted. No links,
    Windows path aliases, duplicate casefold names or replacing releases.
    """
    import io,re,stat,tempfile
    root=pathlib.Path(install_root);releases=root/'releases';releases.mkdir(parents=True,exist_ok=True)
    version=manifest['release_id'];target=releases/version
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,79}',version):raise ValueError('release id')
    if target.exists():raise ValueError('immutable release already exists')
    staging=pathlib.Path(tempfile.mkdtemp(prefix=version+'.staging-',dir=releases))
    total=0
    try:
        for name,descriptor in manifest['modules'].items():
            path=pathlib.Path(artifacts[name])
            if path.is_symlink():raise ValueError('artifact link')
            with path.open('rb') as f:raw=f.read(536870913)
            artifact=descriptor['artifact']
            if len(raw)!=artifact['bytes'] or hashlib.sha256(raw).hexdigest()!=artifact['sha256']:raise ValueError('artifact integrity')
            dest=staging/'capsules'/name;dest.mkdir(parents=True)
            (dest/'artifact.zip').write_bytes(raw)
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries=archive.infolist();seen=set()
                if [entry.filename for entry in entries]!=['source.bundle']:raise ValueError('exact source bundle capsule required')
                if not 1<=len(entries)<=20000:raise ValueError('archive entries')
                for entry in entries:
                    rel=entry.filename.rstrip('/');parts=rel.split('/')
                    if (not rel or len(rel)>240 or '\\' in rel or ':' in rel or
                        any(not re.fullmatch('[A-Za-z0-9_ .-]+',p) or p in ('.','..') or p.endswith((' ','.')) or re.match(r'(?i)^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\.|$)',p) for p in parts) or
                        rel.casefold() in seen or stat.S_ISLNK(entry.external_attr>>16) or entry.flag_bits&1):raise ValueError('unsafe archive')
                    seen.add(rel.casefold());total+=entry.file_size
                    if total>1073741824:raise ValueError('expanded archive bound')
                    out=dest.joinpath(*parts)
                    if entry.is_dir():out.mkdir(parents=True,exist_ok=True)
                    else:
                        out.parent.mkdir(parents=True,exist_ok=True)
                        with archive.open(entry) as src,out.open('xb') as dst:
                            copied=0
                            while True:
                                chunk=src.read(1048576)
                                if not chunk:break
                                copied+=len(chunk)
                                if copied>entry.file_size:raise ValueError('archive size mismatch')
                                dst.write(chunk)
                            if copied!=entry.file_size:raise ValueError('archive truncated')
            materialize_source_capsule(dest/'source.bundle',staging/'modules'/name,descriptor,git_executable=git_executable,git_sha256=git_sha256)
        (staging/'unified-release.json').write_bytes(manifest_bytes)
        (staging/'unified-release.p7s').write_bytes(signature_bytes)
        os.rename(staging,target)
        return target
    except BaseException:
        shutil.rmtree(staging,ignore_errors=True)
        raise


def materialize_source_capsule(bundle,target,descriptor,*,git_executable,git_sha256):
    """Offline real Git checkout with raw blobs, no replacement/filter/hook path.

    Preserve committed Git identity for existing Terminan/Strattester guards.
    Runtime state must live outside this tree. No shared object alternates.
    """
    import subprocess
    git=pathlib.Path(git_executable)
    if not git.is_absolute() or git.is_symlink() or sha256_file(git)!=git_sha256:raise ValueError('externally pinned Git runtime required')
    env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_GLOBAL=os.devnull,GIT_NO_REPLACE_OBJECTS='1',GIT_TERMINAL_PROMPT='0')
    def command(*args):
        return subprocess.check_output([str(git),'-c','core.hooksPath='+os.devnull,'-c','core.autocrlf=false','-c','core.attributesFile='+os.devnull,'-c','transfer.fsckObjects=true','-c','fetch.fsckObjects=true',*args],env=env,stderr=subprocess.PIPE,timeout=30)
    command('clone','--no-hardlinks','--no-checkout',str(pathlib.Path(bundle).absolute()),str(target))
    target=pathlib.Path(target)
    (target/'.git/config').write_bytes(capsule_git_config())
    command('-C',str(target),'update-ref','refs/heads/release',descriptor['commit'])
    command('-C',str(target),'symbolic-ref','HEAD','refs/heads/release')
    if command('-C',str(target),'rev-parse','HEAD^{tree}').decode().strip()!=descriptor['tree']:raise ValueError('capsule commit/tree mismatch')
    if (target/'.git/objects/info/alternates').exists():raise ValueError('shared Git objects forbidden')
    total=0;seen_paths=set()
    for entry in command('-C',str(target),'ls-tree','-r','-z','-l','HEAD').split(b'\0'):
        if not entry:continue
        metadata,path=entry.split(b'\t',1);mode,kind,oid,size=metadata.split();parts=path.decode('utf-8').split('/')
        if kind!=b'blob' or mode not in (b'100644',b'100755') or any(p in ('','..','.') or any(c in p for c in ':\\<>|?*\"') or p.endswith(('.', ' ')) or p.casefold()=='.git' or __import__('re').match(r'(?i)^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\.|$)',p) for p in parts):raise ValueError('unsafe source capsule tree')
        normalized='/'.join(parts).casefold()
        if normalized in seen_paths:raise ValueError('casefold source path collision')
        seen_paths.add(normalized)
        total+=int(size)
        if total>536870912:raise ValueError('source capsule expanded limit')
        out=target.joinpath(*parts);out.parent.mkdir(parents=True,exist_ok=True)
        data=command('-C',str(target),'cat-file','blob',oid.decode())
        if len(data)!=int(size):raise ValueError('Git blob size mismatch')
        with out.open('xb') as f:f.write(data)
        if os.name!='nt':out.chmod(0o755 if mode==b'100755' else 0o644)
    command('-C',str(target),'read-tree','HEAD')
    if command('-C',str(target),'status','--porcelain','--untracked-files=all').strip():raise ValueError('materialized capsule is not clean')
    return target


def verify_materialized_identity(target,descriptor,*,git_executable,git_sha256):
    import subprocess
    git=pathlib.Path(git_executable)
    if not git.is_absolute() or git.is_symlink() or sha256_file(git)!=git_sha256:raise ValueError('trusted Git required')
    env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_GLOBAL=os.devnull,GIT_NO_REPLACE_OBJECTS='1',GIT_TERMINAL_PROMPT='0')
    for revision,expected in [('HEAD',descriptor['commit']),('HEAD^{tree}',descriptor['tree'])]:
        actual=subprocess.check_output([str(git),'--no-replace-objects','-c','core.hooksPath='+os.devnull,'-C',str(target),'rev-parse',revision],env=env,stderr=subprocess.PIPE,timeout=10).decode().strip()
        if actual!=expected:raise ValueError('recovery Git identity changed')


def capsule_git_config():
    # Fixed generated metadata: no remote, include, filter, fsmonitor or hook
    # command can be smuggled into a prepared capsule before registration.
    return ('[core]\n repositoryformatversion = 0\n bare = false\n filemode = false\n logallrefupdates = false\n autocrlf = false\n symlinks = false\n fsmonitor = false\n hooksPath = '+os.devnull+'\n attributesFile = '+os.devnull+'\n').encode()
