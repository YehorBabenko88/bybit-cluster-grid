"""Exact-head frozen739/78 offline publication gate. Never deployment authority."""
import argparse,collections,hashlib,json,os,pathlib,subprocess,sys,uuid,xml.etree.ElementTree as E
ROOT=pathlib.Path(__file__).resolve().parents[1]
SHARED={'installer/pgdata_cross_contract.py':'ff492592757a277661e60d554f73ebbb11b04b7e1f7bee9f0757562ac68392fd',
 'tests/test_pgdata_cross_contract.py':'dc76589fe660509c53ecefc957019b8f2448c42bb0ff429ebb1701b4f8dc8192'}
def need(value,code):
    if not value:raise ValueError(code)
def verify_shared(root):
    for p,h in SHARED.items():need(hashlib.sha256((root/p).read_bytes()).hexdigest()==h,'SHARED_BLOB_SHA256_MISMATCH:'+p)
def validate_events(r,expected):
    need(len(expected)==739 and len(set(expected))==739,'FROZEN_INVENTORY_INVALID')
    need(len(r['nodes'])==739 and set(r['nodes'])==set(expected),'COLLECTION_MISMATCH')
    calls=r['calls'];sub=r['subtests']
    need(len(calls)==739 and collections.Counter(x['nodeid'] for x in calls)==collections.Counter(expected),'LIVE_TEST_IDENTITIES_MISMATCH')
    need(len(sub)==78,'LIVE_SUBTEST_COUNT_MISMATCH')
    need(not r['bad_reports'] and all(x['outcome']=='passed' and x['xfail'] is False for x in calls+sub),'SKIP_XFAIL_ERROR_OR_FAILURE')
    need(r.get('exitstatus',0)==0,'PYTEST_EXIT_FAILURE')
def validate_junit(xml,expected):
    root=E.fromstring(xml);suites=list(root.iter('testsuite'));cases=list(root.iter('testcase'))
    need(len(suites)==1 and len(cases)==739,'JUNIT_CASE_COUNT_MISMATCH')
    need(all(suites[0].get(k)=='0' for k in ('failures','errors','skipped')),'JUNIT_NOT_ALL_PASSED')
    # pytest9 adds successful subtests to suite.tests but emits739 testcase rows.
    need(suites[0].get('tests')=='817','JUNIT_TEST_PLUS_SUBTEST_TOTAL_MISMATCH')
    need(not any(x.tag in ('failure','error','skipped') for x in root.iter()),'JUNIT_BAD_RESULT')
    # Keep class names in collected unittest node IDs, without inventing a path.
    expected_pairs=[]
    for n in expected:
        path,_,tail=n.partition('::');p=tail.split('::')
        i=next(i for i,part in enumerate(p) if part.startswith('test_'))
        expected_pairs.append(('.'.join([path[:-3].replace('/','.'),*p[:i]]),'::'.join(p[i:])))
    need(collections.Counter((c.get('classname'),c.get('name')) for c in cases)==collections.Counter(expected_pairs),'JUNIT_IDENTITIES_MISMATCH')
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--expected-sha',required=True);a=p.parse_args()
    sha=subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    need(sha==a.expected_sha and len(sha)==40,'CHECKOUT_HEAD_MISMATCH');verify_shared(ROOT)
    from importlib.metadata import version
    need(version('pytest')=='9.1.1' and version('cryptography')=='50.0.2','PINNED_DEPENDENCY_MISMATCH')
    os.chdir(ROOT)
    frozen=json.loads((ROOT/'independent_audit/publication_inventory.json').read_text())
    need(len(frozen['files'])==35,'FILE_INVENTORY_MISMATCH')
    out=ROOT/'publication-results';out.mkdir(exist_ok=True)
    temp=ROOT/('t-'+uuid.uuid4().hex[:12]);need(not temp.exists() and temp.parent==ROOT,'TEST_TEMP_UNSAFE')
    env=os.environ.copy()
    for k in ('POSTGRES_DSN','DATABASE_URL','GRID_DISPOSABLE_POSTGRES_TESTS','GRID_TEST_POSTGRES_CONTAINER_ID','GRID_OWNERSHIP_NATIVE_FIXTURES'):env.pop(k,None)
    env.update(PYTHONDONTWRITEBYTECODE='1',GRID_REQUIRE_TEST_ATTESTATION='1',GRID_OFFLINE_EVENT_RECEIPT=str(out/'live-events.json'))
    result=subprocess.run([sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider','-p','independent_audit.publication_plugin',
      '--strict-markers','--basetemp='+str(temp),'--junitxml='+str(out/'junit.xml'),*frozen['files']],cwd=ROOT,env=env)
    need(result.returncode==0,'OFFLINE_TESTS_FAILED')
    live=json.loads((out/'live-events.json').read_text());validate_events(live,frozen['nodes'])
    validate_junit((out/'junit.xml').read_text(),frozen['nodes'])
    former=frozen['former10']
    need(len(former)==10 and len(set(former))==10 and set(former)<=set(live['nodes']),'FORMER10_MISSING')
    report=dict(head_sha=sha,source_rc_sha='6d1b64de05c4b6f29b12153c4da4b20fcb28bce3',collected=739,passed=739,subtests_passed=78,
      junit_testcase_rows=739,junit_tests_total=817,former_regressions_passed=10,skipped=0,xfail=0,errors=0,failures=0,
      shared_sha256=SHARED,execution_authorized=False,readiness_passed=False,physical_ready=False,schema2_enabled=False,guest_cases='12 NOT_RUN')
    (out/'head-receipt.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report))
    return 0
if __name__=='__main__':raise SystemExit(main())
