"""Explicit fixture-only driver; no target/root/path options, SQL or executors."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from installer.ownership_session import ModelFixture, PrototypeBlocked, run_session


def exercise(factory):
    cases=0
    for mutation in (None,'replace','hardlink','acl','extra','prepared','retired','duplicate','torn','foreign'):
        p=factory();saved=[]
        if mutation:p.inject(mutation,'owner.jsonl' if mutation in ('prepared','retired','duplicate','torn','foreign') else 'tasks.plan.json')
        def consume(v):
            if len(p.pinned)!=len(p.expected) or p.locks!=['release','preparation']:
                raise AssertionError('Lifetime not held')
            if v.read('tasks.plan.json')!=p.expected['tasks.plan.json']:raise AssertionError('Wrong bytes')
            saved.append(v)
        r=run_session(p,consume)
        wanted='BLOCKED' if mutation else 'PASS'
        if r['synthetic_result']!=wanted or not r['resources_released']:raise AssertionError(r)
        if r['status']!='BLOCKED' or r['execution_authorized'] or r['physical_ready']:raise AssertionError('Authority leak')
        if p.live or p.locks or p.opened!=p.closed:raise AssertionError('Resource leak')
        for v in saved:
            try:v.read('tasks.plan.json')
            except PrototypeBlocked:pass
            else:raise AssertionError('Expired borrowed view accepted')
        cases+=1
    return cases


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',choices=('model','native'),default='model')
    args=parser.parse_args()
    factory=ModelFixture
    if args.backend=='native':
        from installer.ownership_native_fixture import new_native_fixture,fixture_policy
        fixture_policy();factory=new_native_fixture
    cases=exercise(factory)
    print(json.dumps({'schema':1,'status':'BLOCKED','assurance':'SYNTHETIC_ONLY',
                      'synthetic_result':'PASS','execution_authorized':False,
                      'physical_ready':False,'backend':args.backend,'cases':cases}))
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except Exception:
        print(json.dumps({'schema':1,'status':'BLOCKED','synthetic_result':'BLOCKED',
                          'code':'FIXTURE_SUITE_FAILED','execution_authorized':False,'physical_ready':False}))
        sys.exit(2)
