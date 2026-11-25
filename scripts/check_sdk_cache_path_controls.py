"""Inert DOS8.3/case alias controls; no native link/short-path operation."""
from pathlib import Path,PureWindowsPath
from types import SimpleNamespace
from unittest.mock import patch
import runpy,stat,tempfile,json
root=Path(__file__).resolve().parent
api=runpy.run_path(str(root/'sdk_cache_custody.py'));globals_=api['_ordinary_directory'].__globals__
short=PureWindowsPath('C:/Users/RUNNER~1/AppData/Local/Temp/unified-sdk-cache-fixture')
long=PureWindowsPath('C:/Users/runneradmin/AppData/Local/Temp/unified-sdk-cache-fixture')
state={}
class FakePath:
 def __init__(self,value):self.value=value.value if isinstance(value,FakePath) else PureWindowsPath(value)
 def __str__(self):return str(self.value)
 def __eq__(self,other):return isinstance(other,FakePath) and self.value==other.value
 def __hash__(self):return hash(self.value)
 def __truediv__(self,name):return FakePath(self.value/name)
 def absolute(self):return self
 @property
 def parents(self):return tuple(FakePath(p)for p in self.value.parents)
 @property
 def parent(self):return FakePath(self.value.parent)
 def lstat(self):
  text=str(self);state['checked'].add(text)
  canonical=text.replace('RUNNER~1','runneradmin')
  inode=hash(canonical.lower())
  if state.get('mismatch') and self.value==long:inode+=1
  return SimpleNamespace(st_mode=stat.S_IFLNK if text==state.get('symlink') else stat.S_IFDIR,
   st_file_attributes=1024 if text==state.get('reparse') else 0,st_dev=1,st_ino=inode)
 def is_symlink(self):return str(self)==state.get('symlink')
 def resolve(self,strict=False):
  state['resolves']+=1
  required={str(p)for p in (*reversed(self.parents),self)}
  state['resolve_prechecked'].append(required<=state['checked'])
  return FakePath(str(self).replace('RUNNER~1','runneradmin'))
 def exists(self):return False
class FakeTemporary:
 def __init__(self,*args,**kwargs):pass
 def __enter__(self):return str(short)
 def __exit__(self,*args):pass
results=[]
def run_case(label,*,reparse=None,symlink=None,mismatch=False,accept=False):
 state.clear();state.update(checked=set(),resolves=0,resolve_prechecked=[],reparse=reparse,symlink=symlink,mismatch=mismatch)
 with patch.dict(globals_,{'Path':FakePath,'_external':lambda *args:None}),patch.object(tempfile,'TemporaryDirectory',FakeTemporary):
  try:
   with api['fresh_sdk_cache']() as cache:assert cache==FakePath(long/'bytecode')
  except (AssertionError,ValueError):
   if accept:raise
   results.append(label)
  else:
   if not accept:raise AssertionError('unsafe alias accepted: '+label)
   assert state['resolve_prechecked'] and all(state['resolve_prechecked'])
   results.append(label)
run_case('ordinary_dos83_alias_canonicalized_after_ancestor_checks',accept=True)
run_case('lexical_reparse_ancestor_refused',reparse=str(short.parents[3]))
run_case('lexical_symlink_ancestor_refused',symlink=str(short.parents[2]))
run_case('canonical_reparse_ancestor_refused',reparse=str(long.parents[3]))
run_case('different_directory_identity_refused',mismatch=True)
with api['fresh_sdk_cache'](source_roots=(root.parent,)) as cache:
 assert not cache.exists() and cache.parent.resolve()==cache.parent
results.append('actual_ordinary_temp_owner_and_unused_cache_preserved')
print(json.dumps({'controls':results,'all_passed':True,'scope':'mock alias/link attributes plus ordinary private temp; no actual short-path/link manipulation'}))
