"""Build the inert S0 portable runtime on exact hosted Windows CI only.

Importing this module is inert. No physical execution or network installation.
"""
from __future__ import annotations
import hashlib
import importlib.metadata as metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import stat
import subprocess
import sys
import zipfile

DEPENDENCIES = frozenset('aiohttp aiohappyeyeballs aiosignal attrs frozenlist multidict propcache yarl idna cryptography cffi pycparser typing_extensions'.split())
LIMIT = 512 * 1024 * 1024
FILE_LIMIT = 64 * 1024 * 1024
FILE_COUNT_LIMIT = 20000
PTH = b'stdlib.zip\nDLLs\nSite\nApp\n'

def require_hosted(env, hostname):
    expected = dict(GITHUB_ACTIONS='true', RUNNER_ENVIRONMENT='github-hosted', RUNNER_OS='Windows', GITHUB_REPOSITORY='YehorBabenko88/bybit-cluster-grid', GITHUB_JOB='s0-windows')
    if any(env.get(k) != v for k,v in expected.items()):
        raise ValueError('HOSTED_WINDOWS_ONLY')
    for host in (hostname, env.get('COMPUTERNAME',''), env.get('HOSTNAME','')):
        if host.split('.')[0].casefold() in ('ls5','pc4'):
            raise ValueError('PHYSICAL_HOST_FORBIDDEN')

def validate_members(files, limit=LIMIT):
    if len(files) > FILE_COUNT_LIMIT: raise ValueError('PACKAGE_FILE_COUNT')
    seen = set(); total = 0
    for name, data in files.items():
        parts = name.split('/')
        if not name or '\\' in name or ':' in name or any(not p or p in ('.','..') or p.rstrip(' .') != p or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?',p) for p in parts):
            raise ValueError('UNSAFE_MEMBER')
        if name.casefold() in seen: raise ValueError('MEMBER_COLLISION')
        if len(data) > FILE_LIMIT: raise ValueError('PACKAGE_FILE_TOO_LARGE')
        seen.add(name.casefold()); total += len(data)
    if total > limit: raise ValueError('PACKAGE_TOO_LARGE')

def safe_distribution_member(name):
    try: validate_members({name:b''})
    except ValueError: return False
    parts = PurePosixPath(name).parts
    return not any(p.casefold() in ('__pycache__','scripts','bin') for p in parts) and not name.lower().endswith(('.pth','.pyc','.pyo','.exe'))

def regular_bytes(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info,'st_file_attributes',0) & 0x400 or info.st_size > FILE_LIMIT:
        raise ValueError('UNSAFE_SOURCE_FILE')
    # Reject reparse ancestors as well as leafs.
    for parent in path.parents:
        if getattr(parent.lstat(),'st_file_attributes',0) & 0x400: raise ValueError('REPARSE_SOURCE')
    return path.read_bytes()

def make_manifest(files, **pins):
    validate_members(files)
    return dict(schema=1,profile='PHYSICAL_SMOKE_S0',authority=dict(s0_execute=False,g1_execute=False,cleanup=False),files={n:dict(sha256=hashlib.sha256(b).hexdigest(),size=len(b)) for n,b in sorted(files.items())},**pins)

def validate_manifest(files, manifest):
    validate_members(files)
    fields={'schema','profile','authority','files','head','tree','run_id','attempt','python','source'}
    if type(manifest) is not dict or set(manifest) != fields: raise ValueError('BAD_MANIFEST')
    if type(manifest['schema']) is not int or manifest['schema'] != 1 or manifest['profile'] != 'PHYSICAL_SMOKE_S0': raise ValueError('BAD_MANIFEST')
    authority=manifest['authority']
    if type(authority) is not dict or set(authority) != {'s0_execute','g1_execute','cleanup'} or any(value is not False for value in authority.values()): raise ValueError('BAD_AUTHORITY')
    for name in ('head','tree'):
        if type(manifest[name]) is not str or re.fullmatch('[0-9a-f]{40}',manifest[name]) is None: raise ValueError('BAD_SOURCE_CONTEXT')
    for name in ('run_id','attempt'):
        if type(manifest[name]) is not str or re.fullmatch('[1-9][0-9]{0,19}',manifest[name]) is None: raise ValueError('BAD_CI_CONTEXT')
    if type(manifest['python']) is not str or re.fullmatch(r'3\.12\.(?:0|[1-9][0-9]{0,2})',manifest['python']) is None: raise ValueError('BAD_PYTHON_CONTEXT')
    source=manifest['source']
    if type(source) is not dict or not source or len(source)>FILE_COUNT_LIMIT: raise ValueError('BAD_SOURCE_CONTEXT')
    for name,digest in source.items():
        allowed = type(name) is str and (re.fullmatch(r's0_smoke/[A-Za-z_][A-Za-z_0-9]*\.py',name) is not None or name in ('installer/physical-smoke-s0.ps1','docs/PHYSICAL_SMOKE_S0.md','installer/physical-smoke-s0/S0Launcher.cs'))
        if not allowed or type(digest) is not str or re.fullmatch('[0-9a-f]{64}',digest) is None: raise ValueError('BAD_SOURCE_CONTEXT')
    if type(manifest['files']) is not dict: raise ValueError('BAD_FILE_PINS')
    for pin in manifest['files'].values():
        if type(pin) is not dict or set(pin) != {'sha256','size'} or type(pin['size']) is not int or not 0<=pin['size']<=FILE_LIMIT or type(pin['sha256']) is not str or re.fullmatch('[0-9a-f]{64}',pin['sha256']) is None: raise ValueError('BAD_FILE_PINS')
    actual = {n:dict(sha256=hashlib.sha256(b).hexdigest(),size=len(b)) for n,b in files.items()}
    if actual != manifest.get('files'): raise ValueError('FILE_PIN_MISMATCH')

def archive_bytes(files, manifest):
    validate_manifest(files,manifest)
    members = dict(files); members['s0-package.json'] = json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()
    validate_members(members)
    out = io.BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(members.items()):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=0o100644 << 16
            archive.writestr(info,data)
    return out.getvalue()

def validate_dependency_closure(requirements, parse=None):
    if parse is None:
        # Builder-only parser, never shipped in App/Site.
        from packaging.requirements import Requirement
        def parse(text):
            requirement = Requirement(text)
            return re.sub(r"[-_.]+", "_", requirement.name).lower(), requirement.marker is None or requirement.marker.evaluate({'extra': ''})
    for entries in requirements.values():
        for entry in entries:
            name, active = parse(entry)
            if active and (name not in DEPENDENCIES or name not in requirements):
                raise ValueError('UNREVIEWED_DEPENDENCY_CLOSURE:'+name)

def dependency_files():
    files={}
    validate_dependency_closure({name: metadata.distribution(name).requires or [] for name in DEPENDENCIES})
    for name in sorted(DEPENDENCIES):
        distribution=metadata.distribution(name)
        if name in ('aiohttp','cryptography') and distribution.version != {'aiohttp':'3.14.5','cryptography':'50.0.2'}[name]: raise ValueError('REVIEWED_VERSION_REQUIRED')
        entries=distribution.files
        if not entries: raise ValueError('DISTRIBUTION_FILES_REQUIRED')
        has_license=False
        for entry in entries:
            member=str(entry).replace('\\','/')
            # Wheel RECORD commonly lists launchers outside Site; never copy them.
            if not safe_distribution_member(member): continue
            data=regular_bytes(Path(distribution.locate_file(entry)).absolute())
            target='runtime/Site/'+member
            if target in files: raise ValueError('DISTRIBUTION_COLLISION')
            files[target]=data
            if 'license' in member.casefold() or 'copying' in member.casefold(): has_license=True
        if not has_license: raise ValueError('DEPENDENCY_LICENSE_REQUIRED:'+name)
    return files

def build():
    require_hosted(os.environ,socket.gethostname())
    if sys.platform != 'win32' or sys.version_info[:2] != (3,12): raise ValueError('CPYTHON_312_WINDOWS_REQUIRED')
    root=Path(__file__).resolve().parents[1]
    def git(*args): return subprocess.check_output(['git',*args],cwd=root).decode().strip()
    head=git('rev-parse','HEAD')
    if head != os.environ.get('EXACT_HEAD_SHA'): raise ValueError('EXACT_HEAD_REQUIRED')
    from tools.check_ddl_free_ci import verify_checkout
    verify_checkout(root,head)
    files={}; source={}
    names=git('ls-tree','-r','--name-only','HEAD').splitlines()
    wanted=[n for n in names if n.startswith('s0_smoke/') and n.endswith('.py')]
    wanted += ['installer/physical-smoke-s0.ps1','docs/PHYSICAL_SMOKE_S0.md','installer/physical-smoke-s0/S0Launcher.cs']
    if 's0_smoke/cli.py' not in wanted: raise ValueError('CLI_REQUIRED')
    for name in wanted:
        # Ship Git object bytes: receipt remains exact despite checkout CRLF.
        data=subprocess.check_output(['git','show',head+':'+name],cwd=root)
        source[name]=hashlib.sha256(data).hexdigest()
        target='runtime/App/'+name if name.startswith('s0_smoke/') else name
        files[target]=data
    # Entry point is source controlled, never generated executable authority.
    entry='s0_smoke/entry.py'
    if entry not in wanted: raise ValueError('ENTRYPOINT_REQUIRED')
    files['runtime/App/s0.py']=files['runtime/App/'+entry]
    runtime=Path(sys.executable).parent
    files['native/S0Launcher.dll']=regular_bytes(root/'s0-native-build'/'S0Launcher.dll')
    files['runtime/python.exe']=regular_bytes(runtime/'python.exe')
    for path in sorted(runtime.glob('*.dll')): files['runtime/'+path.name]=regular_bytes(path)
    for path in sorted((runtime/'DLLs').glob('*')):
        if path.suffix.lower() in ('.dll','.pyd'): files['runtime/DLLs/'+path.name]=regular_bytes(path)
    stdlib={}
    for path in sorted((runtime/'Lib').rglob('*')):
        if not path.is_file(): continue
        relative=path.relative_to(runtime/'Lib').as_posix()
        if any(p.casefold() in ('site-packages','test','tests','__pycache__','ensurepip','idlelib','tkinter','turtledemo') for p in PurePosixPath(relative).parts) or path.suffix.lower() not in ('.py','.txt','.json','.pem'): continue
        stdlib[relative]=regular_bytes(path)
    validate_members(stdlib)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(stdlib.items()):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED; z.writestr(info,data)
    files['runtime/stdlib.zip']=out.getvalue()
    files['runtime/python._pth']=PTH; files['runtime/python312._pth']=PTH
    files['runtime/LICENSE.txt']=regular_bytes(runtime/'LICENSE.txt')
    files.update(dependency_files())
    pins=dict(head=head,tree=git('rev-parse','HEAD^{tree}'),run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],python=sys.version.split()[0],source=source)
    manifest=make_manifest(files,**pins); payload=archive_bytes(files,manifest)
    verify_checkout(root,head)
    destination=root/'s0-package'; destination.mkdir(exist_ok=False)
    filename='physical-smoke-s0-windows-py312-'+head+'.zip'
    (destination/filename).write_bytes(payload)
    receipt=dict(schema=1,profile='PHYSICAL_SMOKE_S0',package=filename,sha256=hashlib.sha256(payload).hexdigest(),size=len(payload),authority=manifest['authority'],**pins)
    (destination/'package-receipt.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n',encoding='utf-8')

if __name__ == '__main__': build()


