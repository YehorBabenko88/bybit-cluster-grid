"""Harmless literal bytecode controls; no SDK/domain/provider/child execution."""
from pathlib import Path
import hashlib,importlib,importlib.util,runpy,sys,tempfile
from importlib import _bootstrap_external as bootstrap
root=Path(__file__).resolve().parent
api=runpy.run_path(str(root/'sdk_cache_custody.py'))
if len(sys.argv)!=2:raise AssertionError('one unused startup cache path required')
cache=Path(sys.argv[1]).absolute();results=[]
def refused(call,label):
 try:call()
 except AssertionError:results.append(label)
 else:raise AssertionError('unsafe cache control accepted: '+label)
def audit(event,args):
 if event in ('subprocess.Popen','os.system','socket.__new__') or event.startswith('ctypes.'):raise AssertionError('FORBIDDEN '+event)
sys.addaudithook(audit)
with tempfile.TemporaryDirectory(prefix='inert-sdk-bytecode-') as directory:
 directory=str(api['_canonical_directory'](Path(directory)))
 source=Path(directory)/'market_math.py';source.write_bytes(b'EXECUTED_POLICY="APPROVED_SOURCE"\n')
 original_prefix=sys.pycache_prefix
 try:
  sys.pycache_prefix=None
  old_cache=Path(importlib.util.cache_from_source(str(source)));old_cache.parent.mkdir()
  wrong=compile('EXECUTED_POLICY="UNAPPROVED_BYTECODE"\n',str(source),'exec')
  old_cache.write_bytes(bootstrap._code_to_hash_pyc(wrong,b'12345678',checked=False))
  sys.path.insert(0,directory)
  module=importlib.import_module('market_math')
  assert module.EXECUTED_POLICY=='UNAPPROVED_BYTECODE' # -B alone still reads it.
 finally:sys.pycache_prefix=original_prefix
 refused(lambda:api['claim_sdk_cache'](cache),'preloaded_unchecked_hash_refused')
 sys.modules.pop('market_math',None)
 cache.mkdir()
 refused(lambda:api['claim_sdk_cache'](cache),'existing_cache_refused')
 cache.rmdir()
 original_option=sys._xoptions['pycache_prefix'];sys._xoptions['pycache_prefix']=str(cache)+'-wrong'
 try:refused(lambda:api['claim_sdk_cache'](cache),'missing_startup_binding_refused')
 finally:sys._xoptions['pycache_prefix']=original_option
 custody=api['claim_sdk_cache'](cache,source_roots=(root.parent,))
 importlib.invalidate_caches();module=importlib.import_module('market_math')
 assert module.EXECUTED_POLICY=='APPROVED_SOURCE'
 api['verify_module_cache'](custody,module,source.resolve());results.append('old_unchecked_hash_ignored_under_fresh_startup_prefix')
 cached=module.__cached__;spec_cached=module.__spec__.cached
 alias_cache=importlib.util.cache_from_source(str(source.with_name('RUNNER~1.py')))
 assert alias_cache!=cached and Path(alias_cache).is_relative_to(cache)
 module.__cached__=alias_cache;module.__spec__.cached=alias_cache
 try:refused(lambda:api['verify_module_cache'](custody,module,source.resolve()),'foreign_source_cache_inside_same_fresh_prefix_refused')
 finally:module.__cached__=cached;module.__spec__.cached=spec_cached
 module.__cached__=str(old_cache)
 try:refused(lambda:api['verify_module_cache'](custody,module,source.resolve()),'foreign_module_cache_refused')
 finally:module.__cached__=cached
 injected=cache/'injected.pyc';injected.write_bytes(b'inert fixture')
 try:refused(lambda:api['verify_sdk_cache'](custody),'post_claim_cache_population_refused')
 finally:injected.unlink()
 sys.modules.pop('market_math',None);sys.path.remove(directory)
print(__import__('json').dumps({'controls':results,'all_passed':True,'scope':'inert literal fixture Python import only; no actual SDK/domain execution'}))
