"""Primary-source actual inherited-proxy isolation and injection distinction."""
import argparse,hashlib,json,subprocess,sys,types,unittest
from pathlib import Path

def git(root,*args):return subprocess.check_output(['git','--no-replace-objects','-C',str(root),*args])

def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-head',required=True);p.add_argument('--support-root',required=True);args=p.parse_args()
    assert sys.flags.isolated and sys.dont_write_bytecode and sys.pycache_prefix is None
    script=Path(__file__).absolute();root=script.parents[4];support=Path(args.support_root).absolute()
    assert git(root,'rev-parse','HEAD').decode().strip()==args.expected_head
    assert git(support,'rev-parse','HEAD').decode().strip()=='1f6b0b5c231853607f5bec780f1544cd32bf577d'
    raw=git(support,'show','f155126a95e80139b1b9679c1870ffd66c29360e:docs/intelligence/identity/run_qualification.py')
    assert hashlib.sha256(raw).hexdigest()=='e3733379da5e0cde84573f3279d265c91e16eceb8c94aeeda8983b51031216fe'
    guard=types.ModuleType('pinned_primary_guard');exec(compile(raw,'<pinned-primary-guard>','exec'),guard.__dict__)
    for ancestor in (script,*script.parents):guard.ordinary(ancestor)
    before=guard.inventory(root);support_before=guard.inventory(support)
    print(json.dumps(dict(scope='PROXY_PRIMARY_BEFORE',head=args.expected_head,tree=git(root,'rev-parse','HEAD^{tree}').decode().strip(),
        grid_raw_files=len(before),support_raw_files=len(support_before),core_sha256=before['grid/coordination.py'])),flush=True)
    sys.path[:0]=[str(root),str(root/'tests/coordination/assignment_v1')]
    suite=unittest.defaultTestLoader.discover(str(script.parent),pattern='test_*.py')
    def ids(items):
        for item in items:
            if isinstance(item,unittest.TestSuite):yield from ids(item)
            else:yield item.id()
    actual=list(ids(suite));expected=['test_proxy.ProxyIsolationTests.test_actual_owned_client_ignores_captured_proxy_and_reads_real_three_voters',
        'test_proxy.ProxyIsolationTests.test_injected_client_remains_unowned_and_not_closed_by_authority']
    assert len(actual)==len(set(actual))==2 and sorted(actual)==sorted(expected)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    assert guard.inventory(root)==before and guard.inventory(support)==support_before
    print(json.dumps(dict(scope='PROXY_PRIMARY_AFTER',head=args.expected_head,source_prepost='PASS',tests_run=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),skips=len(result.skipped))),flush=True)
    assert result.wasSuccessful() and result.testsRun==2 and not result.skipped
    print(json.dumps(dict(scope='ACTUAL_OWNED_CLIENT_PROXY_FREE_CONSUL_READ_ONLY_NOT_REGISTRATION',result='PASS',head=args.expected_head,
        tree=git(root,'rev-parse','HEAD^{tree}').decode().strip(),grid_raw_files=len(before),support_raw_files=len(support_before),
        tests=2,skips=0,exact_unique_ids=True,core_sha256=before['grid/coordination.py'],native_registration_writes=0,job_effect_permission=False)))

if __name__=='__main__':main()
