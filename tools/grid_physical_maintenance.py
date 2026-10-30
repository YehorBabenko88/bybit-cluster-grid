"""Strict offline maintenance evidence. No host calls, SQL or execution permission."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from tools.s0_independent_acceptance import check as verify_s0

GATES=frozenset(('host','resources','python','token','postgres','ssh','tailscale','firewall','services','tasks','directories','source','package'))
FIELDS=frozenset(('schema','head','tree','run_id','node','scope','observed_utc','checks','execute','cleanup','deployment'))
LIMIT=1024*1024


def need(value):
    if not value:raise ValueError('MAINTENANCE_EVIDENCE_BLOCKED')


def strict_json(raw):
    try:
        need(type(raw) is bytes and len(raw)<=LIMIT)
        def pairs(items):
            result={}
            for key,value in items:
                need(key not in result);result[key]=value
            return result
        return json.loads(raw.decode('utf-8-sig'),object_pairs_hook=pairs,parse_constant=lambda _:need(False))
    except (TypeError,UnicodeError,RecursionError,json.JSONDecodeError):
        raise ValueError('MAINTENANCE_JSON_BLOCKED') from None


def context(head,tree,run_id,node):
    need(type(head) is str and re.fullmatch('[0-9a-f]{40}',head))
    need(type(tree) is str and re.fullmatch('[0-9a-f]{40}',tree))
    need(type(run_id) is str and str(uuid.UUID(run_id))==run_id and uuid.UUID(run_id).version==4)
    need(type(node) is str and node in ('LS5','PC4'))


def evaluate(record,head,tree,run_id,node):
    result=dict(schema='grid-maintenance-verdict-1',model='BLOCKED',physical='BLOCKED',execute=False,cleanup=False,deployment='NO-GO')
    try:
        context(head,tree,run_id,node)
        result.update(head=head,tree=tree,run_id=run_id,node=node)
        need(type(record) is dict and set(record)==FIELDS)
        need(record['schema']=='grid-maintenance-1' and all(record[k]==v for k,v in dict(head=head,tree=tree,run_id=run_id,node=node).items()))
        need(record['execute'] is False and record['cleanup'] is False and record['deployment']=='NO-GO')
        need(record['scope'] in ('SYNTHETIC_OFFLINE','UNATTESTED_READ_ONLY'))
        stamp=record['observed_utc'];need(type(stamp) is str and stamp.endswith('Z'))
        parsed=datetime.fromisoformat(stamp[:-1]+'+00:00');need(parsed.utcoffset().total_seconds()==0)
        checks=record['checks'];need(type(checks) is dict and set(checks)==GATES)
        for row in checks.values():
            need(type(row) is dict and set(row)=={'status','reason','data'})
            need(type(row['status']) is str and row['status']=='PASS')
            need(type(row['reason']) is str and re.fullmatch('[A-Z0-9_]{1,100}',row['reason']))
            need(type(row['data']) is list and len(row['data'])<=2000)
        result['model']='OFFLINE_MODEL_PASS'
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):pass
    return result


def stage_plan(head,run_id,node):
    context(head,'0'*40,run_id,node)
    stages=[]
    for action in ('Inventory','PlanOnly','Preflight','Stage','Prepare','Execute','Evidence','Cleanup'):
        mutates=action in ('Stage','Prepare','Execute','Cleanup')
        stages.append(dict(action=action,mutates=mutates,status='BLOCKED',argv=None,
                           reason='AUTHENTICATED_ACTION_SPECIFIC_OWNER_GRANT_AND_REVIEWED_EXECUTOR_REQUIRED' if mutates else 'READ_ONLY_OPERATOR_REVIEW_REQUIRED'))
    return dict(schema='grid-maintenance-plan-1',head=head,run_id=run_id,node=node,stages=stages,
                approval_binding=['action','head','tree','host_identity','operator_sid','run_id','resources','issued_at','expires_at','nonce'],
                authorization='NOT_AUTHORIZED',execute=False,cleanup=False,deployment='NO-GO',g1_phases=[dict(phase=i,status='BLOCKED',argv=None) for i in range(1,21)])


def verify_junit(raw,names):
    try:
        need(type(raw) is bytes and len(raw)<=LIMIT and b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper())
        root=ET.fromstring(raw);need(root.tag in ('testsuite','testsuites'))
        cases=list(root.iter('testcase'));need(cases and len(cases)==len(names))
        need({case.get('name') for case in cases}==set(names))
        for suite in root.iter('testsuite'):
            need(all(suite.get(key)=='0' for key in ('errors','failures','skipped')))
            need(int(suite.get('tests','-1'))==len(list(suite.iter('testcase'))))
        need(not any(list(case) for case in cases))
        return len(cases)
    except (ET.ParseError,TypeError,OverflowError,RecursionError):raise ValueError('MAINTENANCE_JUNIT_BLOCKED') from None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('snapshot','head','tree','run-id','node'):p.add_argument('--'+key,required=True)
    args=p.parse_args()
    try:
        path=Path(args.snapshot);need(path.stat().st_size<=LIMIT)
        result=evaluate(strict_json(path.read_bytes()),args.head,args.tree,args.run_id,args.node)
    except (ValueError,OSError):result=dict(model='BLOCKED',physical='BLOCKED',execute=False,cleanup=False,deployment='NO-GO')
    print(json.dumps(result,sort_keys=True));return 0 if result['model']=='OFFLINE_MODEL_PASS' else 1


def verify_ci_zip(raw,outer_sha,expected,pins,phase,inventory):
    """Caller obtains digest/context separately from GitHub, source pins from Git blobs."""
    from tools.s0_independent_acceptance import archive_members
    need(type(raw) is bytes and len(raw)<=16*LIMIT and hashlib.sha256(raw).hexdigest()==outer_sha)
    need(set(expected)=={'head','tree','run_id','attempt'} and phase in ('offline','mocked'))
    need(all(type(x) is str for x in expected.values()))
    files=archive_members(raw)
    record=strict_json(files['manifest-'+phase+'.json'])
    need(set(record)=={'head','tree','run_id','attempt','scope','mode','execute','cleanup','deployment','files','sources'})
    need(all(record[k]==v for k,v in expected.items()))
    need(record['scope']=='OFFLINE_OR_HOSTED_NOT_PHYSICAL' and record['mode']==phase)
    need(record['execute'] is False and record['cleanup'] is False and record['deployment']=='NO-GO')
    need(record['sources']==pins and pins and all(re.fullmatch('[0-9a-f]{64}',s) for s in pins.values()))
    expected_files={'tests.xml','python.jsonl'} if phase=='offline' else {'powershell.xml','powershell.json'}
    need(type(record['files']) is dict and set(record['files'])==expected_files)
    for name,digest in record['files'].items():need(hashlib.sha256(files[name]).hexdigest()==digest)
    if phase=='offline':
        events=[strict_json(line) for line in files['python.jsonl'].splitlines()]
        need(events and all(set(x)=={'name','status'} and x['status']=='TEST_PASS' for x in events))
        names={x['name'] for x in events};need(len(names)==len(events) and names==set(inventory))
        verify_junit(files['tests.xml'],names)
    else:
        from tools.grid_maintenance_ci import PS_NAMES
        verify_junit(files['powershell.xml'],PS_NAMES)
        mocked=strict_json(files['powershell.json'])
        need(set(mocked)=={'scope','status','cases','names','execute','cleanup'})
        need(mocked['scope']=='SYNTHETIC_OFFLINE_NOT_PHYSICAL' and mocked['status']=='PASS')
        need(type(mocked['cases']) is int and mocked['cases']==len(PS_NAMES))
        need(type(mocked['names']) is list and len(mocked['names'])==len(PS_NAMES) and set(mocked['names'])==PS_NAMES)
        need(mocked['execute'] is False and mocked['cleanup'] is False)
    return dict(status='OFFLINE_EVIDENCE_CONSISTENT_NOT_AUTHORIZATION',physical='BLOCKED',execute=False,cleanup=False,deployment='NO-GO')

if __name__=='__main__':raise SystemExit(main())
