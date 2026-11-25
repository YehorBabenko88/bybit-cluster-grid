"""Inert origin predicate controls; no SDK import, Git child or installed file mutation."""
from pathlib import Path,PurePosixPath
from types import ModuleType,SimpleNamespace
import hashlib,json,runpy,sys,tempfile,importlib.util
from unittest.mock import patch
root=Path(__file__).resolve().parent
runner=runpy.run_path(str(root/'check_frozen_consumer.py'))
verify=runner['verify_sdk_modules']
if len(sys.argv)!=2:raise AssertionError('one unused startup cache path required')
custody=runner['CACHE_API']['claim_sdk_cache'](sys.argv[1],source_roots=(root.parent,))
with tempfile.TemporaryDirectory(prefix='sdk-origin-controls-') as directory:
 site=runner['CACHE_API']['_canonical_directory'](Path(directory));path=site/'market_math.py';raw=b'# inert fixture\n';path.write_bytes(raw)
 expected={'market_math':{'distribution':'unified-math-kernels','relative_path':'market_math.py','sha256':hashlib.sha256(raw).hexdigest()}}
 module=ModuleType('market_math');module.__file__=str(path);module.__spec__=importlib.util.spec_from_file_location('market_math',path);module.__loader__=module.__spec__.loader;module.__cached__=module.__spec__.cached
 class Dist:
  files=[PurePosixPath('market_math.py')]
  def locate_file(self,relative):return site/relative
 previous=sys.modules.get('market_math');sys.modules['market_math']=module
 results=[]
 try:
  with patch.object(runner['metadata'],'distribution',lambda name:Dist()):
   verify(site/'different-source',expected,custody);results.append('positive')
   for mode in ('unowned','missing','wrong_path','bytes','unknown_module'):
    Dist.files=[PurePosixPath('market_math.py')];module.__file__=str(path);module.__spec__.origin=str(path);path.write_bytes(raw)
    if mode=='unowned':Dist.files=[]
    if mode=='missing':module.__file__=str(site/'missing.py')
    if mode=='wrong_path':shadow=site/'shadow.py';shadow.write_bytes(raw);module.__file__=str(shadow)
    if mode=='bytes':path.write_bytes(raw+b'changed')
    if mode=='unknown_module':sys.modules['terminan.unapproved']=ModuleType('terminan.unapproved')
    try:verify(site/'different-source',expected,custody)
    except (AssertionError,FileNotFoundError):results.append(mode)
    else:raise AssertionError('negative origin control accepted: '+mode)
    finally:sys.modules.pop('terminan.unapproved',None)
 finally:
  if previous is None:sys.modules.pop('market_math',None)
  else:sys.modules['market_math']=previous
builder=runpy.run_path(str(root/'build_sdk_source_manifest.py'))
heads=builder['SOURCES'];wrong=[False]
def git(args,**kwargs):
 term=str(kwargs['cwd'])=='term';distribution='unified-terminan' if term else 'unified-math-kernels'
 if args[-2:]==['rev-parse','HEAD']:return (('0'*40 if wrong[0] else heads[distribution])+'\n').encode()
 if 'ls-tree' in args:return b'terminan/__init__.py\n'
 return b'# immutable fixture source\n'
with patch('subprocess.check_output',git):
 manifest=builder['build_manifest']('term','math')
 assert len(manifest['modules'])==4
 assert manifest['modules']['market_math']['sha256']==hashlib.sha256(b'# immutable fixture source\n').hexdigest()
 wrong[0]=True
 try:builder['build_manifest']('term','math')
 except ValueError:results.append('wrong_git_revision')
 else:raise AssertionError('unapproved Git source accepted')
print(json.dumps({'controls':results,'all_passed':True,'scope':'inert modules/files and fake Git only'}))
