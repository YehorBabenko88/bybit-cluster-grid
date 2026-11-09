"""Primary-source thirteen DATA/local Journal and OS lock contract tests; creates no Consul RPC or sessions."""
import argparse,hashlib,json,subprocess,sys,types,unittest
from pathlib import Path

def git(root,*args):return subprocess.check_output(['git','--no-replace-objects','-C',str(root),*args])

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--expected-head',required=True);parser.add_argument('--support-root',required=True)
    args=parser.parse_args();assert sys.flags.isolated and sys.dont_write_bytecode and sys.pycache_prefix is None
    script=Path(__file__).absolute();root=script.parents[4];support=Path(args.support_root).absolute()
    assert git(root,'rev-parse','HEAD').decode().strip()==args.expected_head
    assert git(support,'rev-parse','HEAD').decode().strip()=='1f6b0b5c231853607f5bec780f1544cd32bf577d'
    raw=git(support,'show','f155126a95e80139b1b9679c1870ffd66c29360e:docs/intelligence/identity/run_qualification.py')
    assert hashlib.sha256(raw).hexdigest()=='e3733379da5e0cde84573f3279d265c91e16eceb8c94aeeda8983b51031216fe'
    guard=types.ModuleType('pinned_primary_guard');exec(compile(raw,'<pinned-primary-guard>','exec'),guard.__dict__)
    for ancestor in (script,*script.parents):guard.ordinary(ancestor)
    before=guard.inventory(root);support_before=guard.inventory(support)
    assert support_before['unified_system/journal.py']=='9f170cf33f8cdd79baef6fa633d03bebf9eb4b594c54c9cf8dd6c7cb9810bbc3'
    sys.path[:0]=[str(root),str(support)]
    suite=unittest.defaultTestLoader.discover(str(root/'tests/coordination/assignment_v1/unqualified_registration'),pattern='test_*.py')
    def ids(items):
        for item in items:
            if isinstance(item,unittest.TestSuite):yield from ids(item)
            else:yield item.id()
    actual=list(ids(suite));expected=json.loads((script.parent/'EXPECTED-TESTS.json').read_bytes())
    assert len(actual)==len(set(actual))==len(expected)==len(set(expected))==13 and sorted(actual)==sorted(expected)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    assert guard.inventory(root)==before and guard.inventory(support)==support_before
    assert result.wasSuccessful() and result.testsRun==13 and not result.skipped
    print(json.dumps(dict(scope='PROPOSED_UNQUALIFIED_WORKER_DATA_LOCAL_CUSTODY_NO_NATIVE_RPC',result='PASS',head=args.expected_head,
        tree=git(root,'rev-parse','HEAD^{tree}').decode().strip(),tests=13,skips=0,exact_unique_ids=True,grid_raw_files=len(before),
        support_raw_files=len(support_before),codec_sha256=before[str(script.parent.relative_to(root)/'contract_data.py').replace('\\','/')],
        native_rpc_calls=0,native_write_implementation=False,local_adapter_implemented=True,module_sha256=before['grid/authority_assignment_v1.py'],worker_permission=False,production='NO_GO')))

if __name__=='__main__':main()
