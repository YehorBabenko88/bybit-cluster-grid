"""Offline-only PG16 assessment. Never binds ports, launches children or changes resources."""
import sys
sys.dont_write_bytecode = True
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from installer.isolated_postgres_plan import ProvisioningBlocked, validate_postgres_plan
from installer.windows_preflight import physical, unique_object


def need(value, code):
    if not value:
        raise ProvisioningBlocked(code)


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def snapshot_check(e, plan, commit, owner, now):
    keys={'schema','execution_authorized','physical_ready','commit_sha','plan_sha256','status','node_id','run_id','data_root','captured_at','inventory_complete',
          'runtime_stopped','local_fixed_disk','path_physical','root_absent','new_ancestors_absent',
          'hardlinks_absent','postgres_identities_absent','tasks_clear','ports','acl'}
    need(type(e) is dict and set(e)==keys and type(e['schema']) is int and e['schema']==1
         and e['status']=='SNAPSHOT_ONLY', 'HOST_EVIDENCE_INVALID_OR_BLOCKED')
    need(e['execution_authorized'] is False and e['physical_ready'] is False,'EVIDENCE_CANNOT_AUTHORIZE_EXECUTION')
    need(e['commit_sha']==commit,'SNAPSHOT_COMMIT_MISMATCH')
    need(e['plan_sha256']==digest(plan),'SNAPSHOT_PLAN_MISMATCH')
    need(e['node_id']==plan['node_id'], 'HOST_IDENTITY_MISMATCH')
    need(e['run_id']==plan['run_id'], 'RUN_ID_MISMATCH')
    need(e['data_root']==plan['data_root'], 'PATH_IDENTITY_MISMATCH')
    for field,code in [('inventory_complete','INVENTORY_INCOMPLETE'),('runtime_stopped','RUNTIME_NOT_STOPPED'),
        ('local_fixed_disk','DRIVE_NOT_FIXED_LOCAL'),('path_physical','PATH_REDIRECTED_OR_UNKNOWN'),
        ('root_absent','PGDATA_ALREADY_EXISTS'),('new_ancestors_absent','PREEXISTING_UNOWNED_ANCESTOR'),
        ('hardlinks_absent','HARDLINK_OR_IDENTITY_UNKNOWN'),('postgres_identities_absent','POSTGRES_IDENTITY_PRESENT_OR_UNKNOWN'),
        ('tasks_clear','TASK_REFERENCE_OR_IDENTITY_UNKNOWN')]:
        need(e[field] is True,code)
    try:
        need(type(e['captured_at']) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',e['captured_at']), 'SNAPSHOT_STALE_OR_INVALID')
        captured=dt.datetime.strptime(e['captured_at'],'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)
        need(0 <= (now-captured).total_seconds() <= 30, 'SNAPSHOT_STALE_OR_INVALID')
    except (ValueError,TypeError,OverflowError):
        raise ProvisioningBlocked('SNAPSHOT_STALE_OR_INVALID') from None
    acl=e['acl']
    need(type(acl) is dict and set(acl)=={'owner_sid','protected','writable_sids','sha256'}
         and type(acl['sha256']) is str and re.fullmatch('[0-9a-f]{64}',acl['sha256']), 'ACL_EVIDENCE_INVALID')
    need(type(owner) is str and re.fullmatch(r'S-1-5-21-\d+-\d+-\d+-\d+',owner)
         and acl['owner_sid']==owner, 'ACL_OWNER_MISMATCH')
    need(acl['protected'] is True,'ACL_INHERITANCE_UNSAFE')
    need(type(acl['writable_sids']) is list and all(type(s) is str and s in {owner,'S-1-5-18','S-1-5-32-544'} for s in acl['writable_sids']), 'ACL_UNTRUSTED_WRITER')
    need(type(e['ports']) is list and len(e['ports'])<=65536,'PORT_INVENTORY_INVALID')
    for p in e['ports']:
        need(type(p) is dict and set(p)=={'transport','port'} and p['transport'] in ('tcp','udp')
             and type(p['port']) is int and 1<=p['port']<=65535,'PORT_INVENTORY_INVALID')
        need(p['port']!=plan['port'],'PORT_OCCUPIED')


def assess(plan, commit, *, mode='PlanOnly', evidence=None, adapter_plan=None,
           expected_owner_sid=None, reservations=None, now=None):
    r={'schema':1,'status':'BLOCKED','mode':mode if mode in ('PlanOnly','PreflightReadOnly') else 'UNSUPPORTED',
       'execution_authorized':False,'physical_ready':False,'checks':{},'blockers':[],
       'ownership':{'pgdata':'UNPROVEN'},'port_state':'NOT_RESERVED',
       'evidence_trust':'UNAUTHENTICATED_METADATA_NOT_AUTHORIZATION'}
    try:
        need(type(commit) is str and re.fullmatch('[0-9a-f]{40}',commit) and commit!='0'*40,'COMMIT_INVALID')
        r['commit_sha']=commit
        need(mode in ('PlanOnly','PreflightReadOnly'),'MODE_UNSUPPORTED')
        validated=validate_postgres_plan(plan)
        r['plan_sha256']=digest(plan)
        r['checks']['plan']='VALIDATED_METADATA_ONLY'
        r['blockers']+=validated['blockers']
    except (ProvisioningBlocked,TypeError,ValueError,OverflowError) as exc:
        r['blockers']=[str(exc) if isinstance(exc,ProvisioningBlocked) else 'PLAN_INVALID']
        return r
    r['checks']['adapter']='BLOCKED'
    if type(adapter_plan) is not dict:
        r['blockers'].append('ADAPTER_PLAN_REQUIRED')
    else:
        try:
            need(all(adapter_plan.get(k)==v for k,v in [('run_id',plan['run_id']),('node_id',plan['node_id']),('postgres_port',plan['port']),('version',commit)]), 'ADAPTER_IDENTITY_MISMATCH')
            need(type(adapter_plan.get('root')) is str and type(adapter_plan.get('plan_sha256')) is str
                 and re.fullmatch('[0-9a-f]{64}',adapter_plan['plan_sha256']), 'ADAPTER_EVIDENCE_INVALID')
            r['adapter_metadata_sha256']=digest(adapter_plan)
            # Schema1's separate run/node/pgdata layout cannot match adapter postgres/data.
            # Do not translate either contract or manufacture ownership for the other.
            need(str(PureWindowsPath(adapter_plan['root'])/'postgres'/'data')==plan['data_root'], 'ADAPTER_LAYOUT_INCOMPATIBLE')
            r['blockers'].append('ADAPTER_CONTRACT_REVIEW_REQUIRED')
        except (ProvisioningBlocked,TypeError,ValueError) as exc:
            r['blockers'].append(str(exc) if isinstance(exc,ProvisioningBlocked) else 'ADAPTER_EVIDENCE_INVALID')
    if mode=='PlanOnly':
        if evidence is not None:
            r['blockers'].append('PLAN_ONLY_EVIDENCE_FORBIDDEN')
        else:
            r['status']='PLAN_ONLY'
    else:
        r['checks']['host_evidence']='BLOCKED'
        try:
            snapshot_check(evidence,plan,commit,expected_owner_sid,now or dt.datetime.now(dt.timezone.utc))
            r['checks']['host_evidence']='METADATA_ONLY'
            r['ownership']={'pgdata':'ABSENT_UNOWNED','ancestor_acl_sha256':evidence['acl']['sha256'],
                            'asserted_owner_sid':evidence['acl']['owner_sid']}
            r['port_state']='OBSERVED_ONLY_NOT_RESERVED'
        except (ProvisioningBlocked,TypeError,ValueError,KeyError,OverflowError) as exc:
            r['blockers'].append(str(exc) if isinstance(exc,ProvisioningBlocked) else 'HOST_EVIDENCE_INVALID_OR_BLOCKED')
    try:
        claims=[] if reservations is None else reservations
        need(type(claims) is list and len(claims)<=4096,'RESERVATION_INVENTORY_INVALID')
        seen=set()
        for claim in claims:
            need(type(claim) is dict and set(claim)=={'node_id','port','run_id'}
                 and type(claim['node_id']) is str and re.fullmatch('[A-Z][A-Z0-9_-]{0,14}',claim['node_id'])
                 and type(claim['port']) is int and 20000<=claim['port']<=49999
                 and type(claim['run_id']) is str and re.fullmatch('[0-9a-f]{32}',claim['run_id']), 'RESERVATION_INVENTORY_INVALID')
            key=(claim['node_id'],claim['port'])
            if key in seen:r['blockers'].append('DUPLICATE_PORT_RESERVATION')
            seen.add(key)
            if key==(plan['node_id'],plan['port']):r['blockers'].append('PORT_RESERVATION_CONFLICT')
    except (ProvisioningBlocked,TypeError,ValueError) as exc:
        r['blockers'].append(str(exc) if isinstance(exc,ProvisioningBlocked) else 'RESERVATION_INVENTORY_INVALID')
    if any(c in r['blockers'] for c in ('DUPLICATE_PORT_RESERVATION','PORT_RESERVATION_CONFLICT','RESERVATION_INVENTORY_INVALID')):r['status']='BLOCKED'
    r['blockers']=sorted(set(r['blockers']))
    return r


def read_json(path):
    need(physical(path) and path.is_file() and path.stat().st_nlink==1 and path.stat().st_size<=1024**2,'INPUT_FILE_UNSAFE')
    with path.open('rb') as f:raw=f.read(1024**2+1)
    need(len(raw)<=1024**2,'INPUT_FILE_UNSAFE')
    return json.loads(raw.decode('utf-8-sig'),object_pairs_hook=unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--commit',required=True)
    p.add_argument('--mode',choices=['PlanOnly','PreflightReadOnly'],default='PlanOnly')
    p.add_argument('--evidence',type=Path);p.add_argument('--adapter-plan',type=Path)
    p.add_argument('--owner-sid');p.add_argument('--reservations',type=Path)
    a=p.parse_args()
    try:
        need(a.mode!='PlanOnly' or a.evidence is None,'PLAN_ONLY_EVIDENCE_FORBIDDEN')
        r=assess(read_json(a.plan),a.commit,mode=a.mode,
                 evidence=read_json(a.evidence) if a.evidence else None,
                 adapter_plan=read_json(a.adapter_plan) if a.adapter_plan else None,
                 expected_owner_sid=a.owner_sid,reservations=read_json(a.reservations) if a.reservations else None)
    except Exception:
        r={'schema':1,'status':'BLOCKED','execution_authorized':False,'physical_ready':False,'blockers':['INPUT_INVALID_OR_UNSAFE']}
    print(json.dumps(r,sort_keys=True))
    return 0 if r['status']=='PLAN_ONLY' else 2


if __name__=='__main__':
    sys.exit(main())
