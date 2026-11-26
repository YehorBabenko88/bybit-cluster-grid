"""Report-level adversarial controls for both actual reviewed test rosters."""
import hashlib,json,runpy,types
from pathlib import Path
root=Path(__file__).resolve().parent
Guard=runpy.run_path(str(root/'canonical_test_gate.py'))['StrictTestRoster']

def check(expected,count):
 def control(change):
  g=Guard(expected,expected_count=count);s=types.SimpleNamespace(items=[types.SimpleNamespace(nodeid=x) for x in expected],exitstatus=0)
  g.pytest_collection_finish(s)
  for node in expected:
   for phase in ('setup','call','teardown'):g.pytest_runtest_logreport(types.SimpleNamespace(nodeid=node,when=phase,outcome='passed'))
  change(g,s);g.pytest_sessionfinish(s,0);return g.accepted,s.exitstatus
 assert control(lambda g,s:None)==(True,0)
 changes={
 'skipped':lambda g,s:g.pytest_runtest_logreport(types.SimpleNamespace(nodeid=expected[0],when='call',outcome='skipped')),
 'xfail':lambda g,s:g.pytest_runtest_logreport(types.SimpleNamespace(nodeid=expected[0],when='call',outcome='skipped',wasxfail='expected')),
 'xpass':lambda g,s:g.pytest_runtest_logreport(types.SimpleNamespace(nodeid=expected[0],when='call',outcome='passed',wasxfail='expected')),
 'missing_phase':lambda g,s:g.reports.pop((expected[0],'teardown')),
 'deselected':lambda g,s:g.pytest_deselected([s.items[0]]),
 'collection_error':lambda g,s:g.pytest_collectreport(types.SimpleNamespace(outcome='failed')),
 'collection_skip':lambda g,s:g.pytest_collectreport(types.SimpleNamespace(outcome='skipped')),
 'unexpected_roster':lambda g,s:g.pytest_collection_finish(types.SimpleNamespace(items=s.items+[types.SimpleNamespace(nodeid='unexpected')])),
 'incomplete_roster':lambda g,s:g.pytest_collection_finish(types.SimpleNamespace(items=s.items[:-1])),
 'duplicate_report':lambda g,s:g.pytest_runtest_logreport(types.SimpleNamespace(nodeid=expected[0],when='call',outcome='passed')),
 'empty_reports':lambda g,s:g.reports.clear(),
 }
 for name,change in changes.items():assert control(change)==(False,1),name
 for nodes,expected_count in ((expected,True),(expected,count-1),(expected+[expected[0]],count+1)):
  try:Guard(nodes,expected_count=expected_count)
  except ValueError:pass
  else:raise AssertionError('invalid roster constructor accepted')
 return {'cases':count,'positive':1,'negative_reports':list(changes),'negative_constructors':3}

# Ordered902 source-custody manifest; complete prior889 prefix is frozen at publicda9.
CANONICAL_ROSTER_SHA256='d235fb38d3f0d207200af95ada41d1ad58605f663dca317e38aa442d719b6fbe'
def canonical_roster():
 expected=json.loads((root/'canonical_test_roster.json').read_text())
 if (type(expected) is not list or len(expected)!=902
     or any(type(node) is not str or not 1<=len(node)<=2048 for node in expected) or len(set(expected))!=902
     or hashlib.sha256(json.dumps(expected,separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest()!=CANONICAL_ROSTER_SHA256):
  raise ValueError('exact ordered902 canonical obligations required')
 return expected
results=[check(json.loads((root/'frozen_consumer_roster.json').read_text()),14),check(canonical_roster(),902)]
print(json.dumps({'all_passed':True,'results':results}))
