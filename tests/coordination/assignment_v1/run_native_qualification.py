"""Exact native snapshot/source qualification, NOT a job/resource/publication grant."""
import argparse,hashlib,json,os
from pathlib import Path
import re,subprocess,sys,types,unittest

def git(root,*args):return subprocess.check_output(['git','--no-replace-objects','-C',str(root),*args])
def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-head',required=True);p.add_argument('--support-root',required=True)
    a=p.parse_args();assert sys.flags.isolated and sys.dont_write_bytecode and sys.pycache_prefix is None
    script=Path(__file__).absolute();root=script.parents[3];support=Path(a.support_root).absolute()
    assert re.fullmatch('[0-9a-f]{40}',a.expected_head)
    assert git(root,'rev-parse','HEAD').decode().strip()==a.expected_head
    assert git(support,'rev-parse','HEAD').decode().strip()=='1f6b0b5c231853607f5bec780f1544cd32bf577d'
    raw=git(support,'show','f155126a95e80139b1b9679c1870ffd66c29360e:docs/intelligence/identity/run_qualification.py')
    assert hashlib.sha256(raw).hexdigest()=='e3733379da5e0cde84573f3279d265c91e16eceb8c94aeeda8983b51031216fe'
    guard=types.ModuleType('pinned_primary_guard');exec(compile(raw,'<pinned-primary-guard>','exec'),guard.__dict__)
    for ancestor in (script,*script.parents):guard.ordinary(ancestor)
    before=guard.inventory(root);support_before=guard.inventory(support)
    os.environ['A2_ASSIGNMENT_TEST_SUPPORT']=str(support)
    sys.path[:0]=[str(root),str(root/'tests/coordination/assignment_v1')]
    suite=unittest.defaultTestLoader.discover(str(root/'tests/coordination/assignment_v1'),pattern='test_*.py')
    def ids(s):
        for t in s:
            if isinstance(t,unittest.TestSuite):yield from ids(t)
            else:yield t.id()
    actual=list(ids(suite));expected=json.loads((script.parent/'NATIVE-EXPECTED-TESTS.json').read_bytes())
    assert len(actual)==len(set(actual))==len(expected)==len(set(expected))==18
    assert sorted(actual)==sorted(expected)
    r=unittest.TextTestRunner(verbosity=2).run(suite)
    assert guard.inventory(root)==before and guard.inventory(support)==support_before
    assert r.wasSuccessful() and r.testsRun==18 and not r.skipped
    print(json.dumps(dict(result='PASS',scope='CONSISTENT_NATIVE_RAW_READ_CAS_FAILOVER_RESTART_ONLY_NOT_ISSUED_GRANT',head=a.expected_head,tree=git(root,'rev-parse','HEAD^{tree}').decode().strip(),support_head='1f6b0b5c231853607f5bec780f1544cd32bf577d',raw_files=len(before),support_raw_files=len(support_before),tests=18,skips=0,exact_unique_ids=True,module_sha256=before['grid/authority_assignment_v1.py'])))
if __name__=='__main__':main()
