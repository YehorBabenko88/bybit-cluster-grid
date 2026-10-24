"""Offline LS5/PC4 program contract. No host reads, sockets, SQL or executor."""
import argparse
import datetime as dt
import json
from pathlib import Path,PureWindowsPath
import re
from installer.vm_lab_json import check_value,load

CHECKS=('authorization','os','resources','python','dotnet','powershell','postgres','listeners',
        'processes','services','tasks','tailscale','ssh','firewall','paths','environment',
        'source','accounts','acl','health','connectivity','database_metadata')
DATA_KEYS={
 'authorization':set(), 'os':{'version','architecture'},
 'resources':{'logical_cpu','ram_bytes','drive','free_bytes'},
 'python':{'path','file_version'},'dotnet':{'path','file_version'},'powershell':{'path','file_version'},
 'postgres':{'service','state','start_mode'},'listeners':{'address','port','pid'},
 'processes':{'pid','parent_pid','name','path','created_utc','grid_candidate','identity_known'},
 'services':{'service','state','start_mode'},'tasks':{'name','state','enabled','principal_kind'},
 'tailscale':{'service','state','path','file_version'},'ssh':{'service','state','path','file_version'},
 'firewall':{'action','direction','profile','protocol','local_port'},
 'paths':{'path','exists','reparse'},'environment':{'name'},
 'source':{'path','sha256'},'accounts':{'name','sid_digest','enabled','administrator'},
 'acl':{'path','owner_digest','protected','ace_count','reparse'},'health':set(),
 'connectivity':set(),'database_metadata':set()}
ENV_NAMES={'POSTGRES_DSN','NODE_ROLE','NODE_ID','COORDINATOR_URL','COORDINATOR_CANDIDATES','BYBIT_REST_URL','BYBIT_WS_URL','BYBIT_ARCHIVE_BASE_URL','GRID_SHARED_TOKEN','NODE_CREDENTIAL','TELEGRAM_BOT_TOKEN','TELEGRAM_ALLOWED_CHAT_IDS','ProgramData','ProgramFiles'}
AUTH_KEYS={'execute','cleanup','deployment','production_database','schema2'}
SHA=re.compile(r'[0-9a-f]{40}\Z');RUN=re.compile(r'[0-9a-f]{32}\Z');DIGEST=re.compile(r'[0-9a-f]{64}\Z')


def need(ok,reason):
    if not ok:raise ValueError(reason)


def make_profile(head,run):
    need(type(head) is str and SHA.fullmatch(head),'HEAD')
    need(type(run) is str and RUN.fullmatch(run),'RUN')
    return dict(schema='grid-physical-plan-1',candidate_head=head,run_id=run,
        permissions={k:False for k in sorted(AUTH_KEYS)},
        nodes={n:dict(role='CONTROL' if n=='LS5' else 'WORKER',address=None,
                     root=chr(92).join(('C:','GridLab','FirstBoot',run,n))) for n in ('LS5','PC4')},
        ports=dict(api=29441,postgres=29442,synthetic=29443,worker_tunnel=29444),
        isolation=dict(api_bind='127.0.0.1',postgres_bind='127.0.0.1',postgres_instance='new_disposable',
                       network_isolation='INDEPENDENT_OS_POLICY_REQUIRED',remote_transport='EXISTING_APPROVED_SSH_TUNNEL'),
        market='SYNTHETIC_LOOPBACK_ONLY',postgres_version_num=180004,migrations=list(range(1,49)),
        roles={k:'grid_lab_'+run+'_'+k for k in ('owner','app','readonly')},
        executor=None,cleanup='RETAIN_UNLESS_SEPARATELY_AUTHORIZED_AND_HANDLE_VERIFIED')


def _profile(p):
    check_value(p)
    need(type(p) is dict and set(p)=={'schema','candidate_head','run_id','permissions','nodes','ports','isolation','market','postgres_version_num','migrations','roles','executor','cleanup'},'PROFILE_FIELDS')
    need(p['schema']=='grid-physical-plan-1','SCHEMA')
    need(type(p['candidate_head']) is str and SHA.fullmatch(p['candidate_head']),'HEAD')
    need(type(p['run_id']) is str and RUN.fullmatch(p['run_id']),'RUN')
    need(type(p['permissions']) is dict and set(p['permissions'])==AUTH_KEYS and all(v is False for v in p['permissions'].values()),'AUTHORITY_FORBIDDEN')
    need(type(p['nodes']) is dict and set(p['nodes'])=={'LS5','PC4'},'NODES')
    for n,row in p['nodes'].items():
        need(type(row) is dict and set(row)=={'role','address','root'},'NODE_FIELDS')
        need(row['role']==('CONTROL' if n=='LS5' else 'WORKER') and row['address'] is None,'UNVERIFIED_ADDRESS_NOT_ALLOWED')
        # Exact case-sensitive canonical path avoids ADS/UNC/dot/trailing alias acceptance.
        expected=chr(92).join(('C:','GridLab','FirstBoot',p['run_id'],n))
        need(type(row['root']) is str and row['root']==expected and PureWindowsPath(row['root']).is_absolute(),'ROOT')
    need(type(p['ports']) is dict and set(p['ports'])=={'api','postgres','synthetic','worker_tunnel'},'PORT_FIELDS')
    ports=list(p['ports'].values())
    need(all(type(v) is int and 1024<=v<=65535 and v not in (5432,55432,55433,8765) for v in ports) and len(set(ports))==4,'PORTS')
    need(p['isolation']==dict(api_bind='127.0.0.1',postgres_bind='127.0.0.1',postgres_instance='new_disposable',network_isolation='INDEPENDENT_OS_POLICY_REQUIRED',remote_transport='EXISTING_APPROVED_SSH_TUNNEL'),'ISOLATION')
    need(p['market']=='SYNTHETIC_LOOPBACK_ONLY' and type(p['postgres_version_num']) is int and p['postgres_version_num']==180004,'RUNTIME')
    need(type(p['migrations']) is list and all(type(v) is int for v in p['migrations']) and p['migrations']==list(range(1,49)),'MIGRATIONS')
    need(p['roles']=={k:'grid_lab_'+p['run_id']+'_'+k for k in ('owner','app','readonly')},'ROLES')
    need(p['executor'] is None and p['cleanup']=='RETAIN_UNLESS_SEPARATELY_AUTHORIZED_AND_HANDLE_VERIFIED','EXECUTOR_FORBIDDEN')


def validate_profile(profile):
    result=dict(status='BLOCKED',host_verified=False,g0='BLOCKED',g1='BLOCKED',g2='NO-GO',execution_authorized=False,cleanup_authorized=False)
    try:_profile(profile);result['status']='OFFLINE_MODEL_PASS'
    except (ValueError,TypeError,KeyError,OverflowError):result['reason']='INVALID_OR_UNSAFE_PROFILE'
    return result


def assess_snapshots(profile,snapshots,now):
    out=dict(offline_valid=False,g0='BLOCKED',g1='BLOCKED',g2='NO-GO',host_verified=False,blocked=[],failed=[],execution_authorized=False,cleanup_authorized=False)
    try:
        _profile(profile);check_value(snapshots)
        need(type(snapshots) is list and len(snapshots)==2,'NODE_COUNT')
        need(isinstance(now,dt.datetime) and now.tzinfo is not None,'CLOCK')
        seen=set();hosts=set()
        for s in snapshots:
            need(type(s) is dict and set(s)=={'schema','node','head','run_id','host_id','observed_utc','observation_kind','g1_authorized','g2_authorized','checks'},'SNAPSHOT_FIELDS')
            need(s['schema']=='grid-g0-observation-1' and s['node'] in profile['nodes'] and s['node'] not in seen,'NODE_ID');seen.add(s['node'])
            need(s['head']==profile['candidate_head'] and s['run_id']==profile['run_id'],'CONTEXT')
            need(type(s['host_id']) is str and DIGEST.fullmatch(s['host_id']) and s['host_id'] not in hosts,'HOST_ALIAS');hosts.add(s['host_id'])
            need(s['observation_kind']=='UNATTESTED_READ_ONLY' and s['g1_authorized'] is False and s['g2_authorized'] is False,'NO_AUTHORITY')
            observed=dt.datetime.fromisoformat(s['observed_utc'].replace('Z','+00:00'))
            need(observed.tzinfo is not None and 0<=(now-observed).total_seconds()<=900,'STALE_OR_FUTURE')
            need(type(s['checks']) is dict and set(s['checks'])==set(CHECKS),'MISSING_GATE')
            for name,row in s['checks'].items():
                need(type(row) is dict and set(row)=={'status','reason','data'},'CHECK_FIELDS')
                need(row['status'] in ('PASS','FAIL','BLOCKED') and type(row['reason']) is str and re.fullmatch('[A-Z0-9_]{1,80}',row['reason']),'CHECK_STATUS')
                need(type(row['data']) is list and len(row['data'])<=128,'DATA_SIZE')
                for d in row['data']:
                    need(type(d) is dict and set(d)<=DATA_KEYS[name],'UNSAFE_DATA_FIELDS')
                    if name=='environment':need(set(d)=={'name'} and d['name'] in ENV_NAMES,'ENV_NAME')
                    if name=='listeners':
                        need(type(d.get('port')) is int and 1<=d['port']<=65535,'PORT_TYPE')
                        if d['port'] in profile['ports'].values():out['failed'].append(s['node']+':PORT_CONFLICT')
                    if name=='paths' and d.get('exists') is True and d.get('path')==profile['nodes'][s['node']]['root']:out['failed'].append(s['node']+':ROOT_ALREADY_EXISTS')
                    for v in d.values():need(type(v) in (str,int,bool,type(None)) and (type(v) is not str or len(v)<=512),'UNSAFE_DATA_TYPE')
                if row['status']=='FAIL':out['failed'].append(s['node']+':'+name)
                elif row['status']=='BLOCKED':out['blocked'].append(s['node']+':'+name)
        out['offline_valid']=True
        out['blocked'].append('INDEPENDENT_G0_REVIEW_REQUIRED')
        out['g0']='NO-GO' if out['failed'] else 'BLOCKED'
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):out['blocked']=['INVALID_STALE_OR_UNSAFE_OBSERVATION']
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--head',required=True);parser.add_argument('--run-id',required=True);parser.add_argument('--snapshots',nargs=2)
    args=parser.parse_args();p=make_profile(args.head,args.run_id)
    if args.snapshots:
        snapshots=[load(Path(name).read_text(encoding='utf-8-sig')) for name in args.snapshots]
        result=assess_snapshots(p,snapshots,dt.datetime.now(dt.timezone.utc));print(json.dumps(result,indent=2));return 1
    print(json.dumps(dict(profile=p,assessment=validate_profile(p)),indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
