"""Calibrate the pinned real pytest report protocol, including failing subtests."""
import argparse, importlib.metadata, json, os, platform, runpy, sys, tempfile
from pathlib import Path
root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('cache');parser.add_argument('--dependencies',required=True);args=parser.parse_args()
api=runpy.run_path(str(root/'sdk_cache_custody.py'))
custody=api['claim_sdk_cache'](Path(args.cache),source_roots=(root.parent,))
StrictTestRoster=runpy.run_path(str(root/'canonical_test_gate.py'))['StrictTestRoster']
sys.path.insert(0,str(Path(args.dependencies).resolve(strict=True)))
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
# No terminal or platform probing child is needed for these literal controls.
sys.modules['colorama']=None
platform.system=lambda:'Windows' if sys.platform=='win32' else 'Linux'
def audit(event,args):
 if event in ('subprocess.Popen','os.system','socket.__new__','sqlite3.connect') or event.startswith('ctypes.'):
  raise AssertionError('FORBIDDEN '+event)
sys.addaudithook(audit)
import pytest
assert pytest.__version__=='8.3.5', 'reviewed pytest 8.3.5 required'
assert importlib.metadata.version('pytest-asyncio')=='0.26.0', 'reviewed asyncio plugin 0.26.0 required'
results=[]
with tempfile.TemporaryDirectory(prefix='literal-pytest-protocol-') as temp:
 temp=str(api['_canonical_directory'](Path(temp)))
 for label, expression, accepted in [('passing','True',True),('failed_subtest','i != 1',False)]:
  source=Path(temp)/('test_'+label+'.py')
  source.write_text('import unittest\nclass Literal(unittest.TestCase):\n def test_subtests(self):\n  for i in range(3):\n   with self.subTest(i=i):\n    self.assertTrue('+expression+')\n')
  node=str(source)+'::Literal::test_subtests'
  gate=StrictTestRoster([node],expected_count=1)
  # pytest normalizes external absolute paths relative to the invocation cwd.
  previous=Path.cwd();os.chdir(temp)
  try:
   gate=StrictTestRoster([source.name+'::Literal::test_subtests'],expected_count=1)
   code=pytest.main(['-q','--color=no','-o','addopts=',str(source)],plugins=[gate])
  finally:os.chdir(previous)
  assert gate.accepted is accepted
  assert (int(code)==0) is accepted
  assert len(gate.reports)==3
  results.append({'control':label,'accepted':gate.accepted,'exit':int(code),'reports':len(gate.reports)})
api['verify_sdk_cache'](custody)
print(json.dumps({'pytest':pytest.__version__,'controls':results},sort_keys=True))
