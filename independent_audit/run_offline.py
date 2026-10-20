"""Bounded RC audit runner. Default: PlanOnly, no installer/host/DB execution."""
import argparse,contextlib,io,json,os,pathlib,subprocess,sys,uuid,xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE_TESTS=['test_isolated_postgres_plan','test_isolated_postgres_preflight',
 'test_isolated_postgres_windows_contract','test_isolated_postgres_mapping',
 'test_isolated_ownership_contract','test_ownership_session_prototype',
 'test_ownership_adversarial_model','test_ownership_threat_boundary',
 'test_vm_lab_plan','test_vm_lab_robustness','test_vm_lab_evidence','test_vm_test_attestation']

def files():
    manifest=json.loads((ROOT/'independent_audit/composition.json').read_text())
    names={p for paths in manifest['changed'].values() for p in paths if p.startswith('tests/test_') and p.endswith('.py')}
    names.update('tests/'+n+'.py' for n in BASE_TESTS)
    names.add('independent_audit/test_combined.py')
    assert all((ROOT/p).is_file() for p in names),'Required offline source missing'
    return sorted(names)

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--run-tests',action='store_true',help='Execute only the bounded offline test inventory')
    args=a.parse_args();names=files()
    if not args.run_tests:
        print(json.dumps(dict(mode='PlanOnly',files=names,physical_ready=False,
          execution_authorized=False,schema2_enabled=False,infrastructure_operations=[]),indent=2))
        return 0
    if os.name!='nt':
        raise SystemExit('Windows PS5.1/7 contracts mandatory in this RC inventory; use Windows workspace')
    from importlib.metadata import version
    assert version('cryptography')=='50.0.2','Use reviewed isolated pinned test-crypto venv; no automatic dependency installation'
    import pytest
    os.chdir(ROOT);sys.path.insert(0,str(ROOT))
    class Inventory:
        nodes=[]
        def pytest_collection_finish(self,session):
            self.nodes=[item.nodeid.replace(chr(92),'/') for item in session.items]
    inventory=Inventory();log=io.StringIO()
    with contextlib.redirect_stdout(log):
        collected=pytest.main(['--collect-only','-q','-p','no:cacheprovider',*names],plugins=[inventory])
    assert int(collected)==0 and inventory.nodes,'Offline collection failed: '+log.getvalue()
    assert len(inventory.nodes)==len(set(inventory.nodes)),'Duplicate collection identities'
    out=ROOT/'independent_audit/evidence';out.mkdir(exist_ok=True)
    (out/'inventory.json').write_text(json.dumps(dict(files=names,nodes=inventory.nodes),indent=2),encoding='utf8')
    temp=ROOT/('t-'+uuid.uuid4().hex[:12]);assert temp.parent==ROOT and not temp.exists()
    env=os.environ.copy()
    for name in ('POSTGRES_DSN','DATABASE_URL','GRID_DISPOSABLE_POSTGRES_TESTS','GRID_TEST_POSTGRES_CONTAINER_ID','GRID_OWNERSHIP_NATIVE_FIXTURES'):
        env.pop(name,None)
    env.update(PYTHONDONTWRITEBYTECODE='1',GRID_REQUIRE_TEST_ATTESTATION='1')
    receipt=out/'offline-junit.xml'
    result=subprocess.run([sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',
       '--strict-markers','--basetemp='+str(temp),'--junitxml='+str(receipt),*names],cwd=ROOT,env=env)
    assert result.returncode==0,'Offline tests failed'
    suites=list(ET.parse(receipt).iter('testsuite'))
    assert suites and all(int(s.get(k,0))==0 for s in suites for k in ('failures','errors','skipped')),'No skips/xfails/failures/errors allowed'
    print(json.dumps(dict(mode='OFFLINE_TESTED_ONLY',collected=len(inventory.nodes),
        junit_tests=sum(int(s.get('tests',0)) for s in suites),physical_ready=False,
        execution_authorized=False,schema2_enabled=False,guest_cases='12 NOT_RUN')))
    return 0
if __name__=='__main__':raise SystemExit(main())
