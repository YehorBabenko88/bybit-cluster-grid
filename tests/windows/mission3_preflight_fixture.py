"""Disposable native-preflight fixtures only; no source activation or authority."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
import zipfile

p=argparse.ArgumentParser()
p.add_argument('--root',required=True,type=Path)
p.add_argument('--upstream',required=True,type=Path)
p.add_argument('--git',required=True)
p.add_argument('--publisher',required=True)
a=p.parse_args()
root=a.root;source=root/'trusted-source';source.mkdir()
for name in ('integration/source_guard.py','unified_system/__init__.py','unified_system/module_catalog.py','unified_system/release_manifest.py','unified_system/package_preflight.py'):
    target=source/name;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(a.upstream/name,target)
env={k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')}
env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_SYSTEM=os.devnull,GIT_NO_REPLACE_OBJECTS='1',GIT_NO_LAZY_FETCH='1',GIT_TERMINAL_PROMPT='0')
def git(*args):return subprocess.check_output([a.git,'-C',str(source),*args],env=env,stderr=subprocess.DEVNULL,timeout=20).decode().strip()
git('init');git('config','core.autocrlf','false');git('config','core.hooksPath',os.devnull);git('config','core.attributesFile',os.devnull);git('config','core.fsmonitor','false')
git('add','.');git('-c','user.name=CI Fixture','-c','user.email=ci@example.invalid','commit','-m','Synthetic native preflight source fixture')
package=root/'package';(package/'modules').mkdir(parents=True)
modules={}
for name in ('unified-system','grid','strattester','math','meta_analyse','terminan'):
    path=package/'modules'/(name+'.zip')
    # The preflight validates descriptor closure and hashes, NOT Git bundle
    # materialization. This labelled test payload must never be activated.
    with zipfile.ZipFile(path,'w') as archive:archive.writestr('source.bundle',b'SYNTHETIC_PREFLIGHT_HASH_FIXTURE_NOT_A_DEPLOYABLE_BUNDLE')
    modules[name]=dict(version='1.0.0',commit='a'*40,tree='b'*40,api_major=1,dependencies={},artifact=dict(path='modules/'+name+'.zip',sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size),provenance=dict(repository='synthetic-fixture/'+name,run_id='123',attempt=1,workflow_sha='a'*40))
manifest=dict(schema='unified.release.v3',release_id='synthetic-preflight-only',sequence=1,publisher_sha256=a.publisher,modules=modules,execution_authority=False,trading_authorized=False)
def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
valid=canonical(manifest);(package/'release.json').write_bytes(valid);(root/'valid-manifest.json').write_bytes(valid)
missing=json.loads(valid);del missing['modules']['meta_analyse'];(root/'missing-module.json').write_bytes(canonical(missing))
bad_schema=json.loads(valid);bad_schema['schema']='unified.release.v99';(root/'wrong-schema.json').write_bytes(canonical(bad_schema))
(root/'noncanonical.json').write_bytes(b' '+valid)
marker=root/'UNTRUSTED_CODE_EXECUTED'
ambient=root/'ambient';(ambient/'unified_system').mkdir(parents=True)
(ambient/'unified_system/__init__.py').write_text('from pathlib import Path\nPath('+repr(str(marker))+').write_text("ambient")\n')
(root/'fake-python.cmd').write_text('@echo untrusted>"'+str(marker)+'"\n')
(root/'fake-preflight.py').write_text('from pathlib import Path\nPath('+repr(str(marker))+').write_text("raw-script")\n')
honest=source/'unified_system/release_manifest.py'
malicious=('from pathlib import Path\nPath('+repr(str(marker))+').write_text("cache")\n').encode()
assert len(malicious)<honest.stat().st_size
poison=root/'poison.py';poison.write_bytes(malicious+b' '*(honest.stat().st_size-len(malicious)))
os.utime(poison,ns=(honest.stat().st_atime_ns,honest.stat().st_mtime_ns))
cache=root/'poisoned-cache';cache.mkdir()
previous=sys.pycache_prefix
try:
    sys.pycache_prefix=str(cache);target=importlib.util.cache_from_source(str(honest))
finally:sys.pycache_prefix=previous
py_compile.compile(str(poison),cfile=target,dfile=str(honest),doraise=True)
policy=dict(source_head=git('rev-parse','HEAD'),source_tree=git('rev-parse','HEAD^{tree}'),preflight_sha256=hashlib.sha256((source/'unified_system/package_preflight.py').read_bytes()).hexdigest(),guard_sha256=hashlib.sha256((source/'integration/source_guard.py').read_bytes()).hexdigest())
(root/'policy.json').write_text(json.dumps(policy))
