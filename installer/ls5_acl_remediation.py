"""Pure LS5 ACL snapshot/planning model. Never observes or mutates a host.

Model inputs, hashes and positive boolean observations are untrusted assertions,
not physical proof. No output authorizes ACL writes, execution or rollback.
"""
import copy
import hashlib
import json
import ntpath
import re
import uuid

SYSTEM='S-1-5-18'
ADMINS='S-1-5-32-544'
USERS='S-1-5-32-545'
FULL=0x1F01FF
RX=0x1200A9
READ=0x120089
MODIFY=0x1301BF
DATA=r'C:\ProgramData\BybitClusterGrid'
CODE=r'C:\Program Files\BybitClusterGrid'
ACTIVE='9ab1f5b85ec471ea21ec89f1b76740c0b01537b6'
LAUNCHER_HASH='f1a1a49c22f71cf5a65beb3d8512c088805c39afc96633d93a852f7a360111f6'
TASKS={'BybitClusterGridAgent','BybitClusterGridCoordinator','BybitClusterGridArchivePipeline'}
PROOFS={'inventory_complete','ancestors_verified','identities_verified','source_integrity_verified',
        'toolchain_verified','role_inventory_complete','all_releases_verified',
        'all_launch_paths_verified','process_inventory_complete','unrelated_resources_unmodified'}


def desired_acl(profile,kind,roles):
    if profile not in ('boundary','code','secret','data') or kind not in ('file','directory'):
        raise ValueError('ACL_PROFILE_INVALID')
    if type(roles) is not dict or set(roles)!={'service','custodian'} or roles['custodian']!=ADMINS:
        raise ValueError('ACL_ROLE_UNKNOWN')
    service=roles['service']
    if service!=SYSTEM and (type(service) is not str or not re.fullmatch(r'S-1-5-21-\d+-\d+-\d+-\d+',service)):
        raise ValueError('ACL_SERVICE_SID_UNKNOWN')
    rights={SYSTEM:FULL,ADMINS:FULL}
    if service not in rights:
        rights[service]={'boundary':RX,'code':RX,'secret':READ,'data':MODIFY}[profile]
    flags=3 if kind=='directory' else 0
    return [dict(sid=sid,mask=mask,flags=flags,inherited=False,type='allow') for sid,mask in sorted(rights.items())]


def canonical(path):
    if type(path) is not str or len(path)>240 or not path.startswith('C:\\') or '/' in path:
        raise ValueError('ACL_PATH_UNKNOWN')
    if any(c in path for c in '\x00\r\n%~*?"') or ':' in path[2:]:raise ValueError('ACL_PATH_ALIAS')
    parts=path[3:].split('\\')
    if any(not p or p in ('.','..') or p.endswith((' ','.')) for p in parts):raise ValueError('ACL_PATH_ALIAS')
    reserved={'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}
    if any(p.split('.')[0].upper() in reserved for p in parts):raise ValueError('ACL_DEVICE_PATH')
    normalized=ntpath.normpath(path).casefold()
    roots=(DATA.casefold(),CODE.casefold())
    if not any(normalized==r or normalized.startswith(r+'\\') for r in roots):raise ValueError('ACL_SYSTEM_PATH_FORBIDDEN')
    return normalized


def path_profile(path):
    p=canonical(path)
    if p in (DATA.casefold(),CODE.casefold()):return 'boundary'
    relative=p.removeprefix(DATA.casefold()+'\\')
    if relative=='.env' or relative=='secrets' or relative.startswith('secrets\\'):return 'secret'
    if relative.split('\\')[0] in ('spool','logs','backups'):return 'data'
    # Deploy scripts and serialized models are potential executable inputs.
    # Do not grant a separate data writer until a safe consumption contract exists.
    return 'code'


def _objects(s):
    if type(s) is not dict or type(s.get('schema')) is not int or s['schema']!=1:raise ValueError('ACL_SCHEMA_UNKNOWN')
    if type(s.get('head')) is not str or not re.fullmatch('[0-9a-f]{40}',s['head']):raise ValueError('ACL_HEAD_UNKNOWN')
    run=s.get('run_id')
    if type(run) is not str or str(uuid.UUID(run))!=run or uuid.UUID(run).version!=4:raise ValueError('ACL_RUN_UNKNOWN')
    desired_acl('code','file',s.get('roles'))
    versions=s.get('releases')
    if (type(versions) is not list or len(versions)!=6 or len(set(versions))!=6
            or any(type(v) is not str or not re.fullmatch('[0-9a-f]{40}',v) for v in versions)
            or s.get('active_version')!=ACTIVE or ACTIVE not in versions):raise ValueError('ACL_RELEASE_INVENTORY_UNKNOWN')
    objects=s.get('objects')
    if type(objects) is not list or not 1<=len(objects)<=100000:raise ValueError('ACL_OBJECT_INVENTORY_UNKNOWN')
    seen=set();identities=set()
    for o in objects:
        path=canonical(o['path'])
        if path in seen:raise ValueError('ACL_PATH_COLLISION')
        seen.add(path)
        identity=o.get('identity')
        if type(identity) is not str or not identity or identity in identities:raise ValueError('ACL_IDENTITY_UNKNOWN')
        identities.add(identity)
        if type(o.get('sddl')) is not str or not o['sddl']:raise ValueError('ACL_ORIGINAL_SDDL_MISSING')
        if o.get('owner') not in (SYSTEM,ADMINS):raise ValueError('ACL_OWNER_UNTRUSTED')
        if o.get('reparse') is not False or type(o.get('links')) is not int or o['links']!=1:raise ValueError('ACL_LINK_OR_REPARSE_UNSAFE')
        desired_acl(o['profile'],o['kind'],s['roles'])
        if o['profile']!=path_profile(o['path']):raise ValueError('ACL_PROFILE_PATH_MISMATCH')
        if o['profile']=='code' and o['kind']=='file':
            if not re.fullmatch('[0-9a-f]{64}',o.get('sha256','')):raise ValueError('ACL_CODE_HASH_UNKNOWN')
        if path==canonical(DATA+r'\installer\coordinator-launcher.ps1') and o.get('sha256')!=LAUNCHER_HASH:
            raise ValueError('ACL_BASELINE_LAUNCHER_MISMATCH')
        if type(o.get('aces')) is not list or type(o.get('protected')) is not bool:raise ValueError('ACL_DACL_UNKNOWN')
        for ace in o['aces']:
            if (type(ace) is not dict or set(ace)!={'sid','mask','flags','inherited','type'}
                    or type(ace['mask']) is not int or not 0<=ace['mask']<=0xFFFFFFFF
                    or type(ace['flags']) is not int or not 0<=ace['flags']<=31
                    or type(ace['inherited']) is not bool or ace['type'] not in ('allow','deny')):
                raise ValueError('ACL_ACE_UNKNOWN')
            if ace['sid'] not in (SYSTEM,ADMINS,USERS,'S-1-1-0','S-1-5-11',s['roles']['service']):
                raise ValueError('ACL_PRINCIPAL_UNCLASSIFIED')
    required={DATA,CODE,DATA+r'\installer',DATA+r'\runtime',DATA+r'\.env',DATA+r'\spool',
        DATA+r'\logs',DATA+r'\backups',DATA+r'\deploy',DATA+r'\ml-artifacts',
        DATA+r'\installer\coordinator-launcher.ps1',DATA+r'\runtime\venv',DATA+r'\runtime\venv\Scripts',
        DATA+r'\runtime\venv\Scripts\python.exe',DATA+r'\runtime\venv\Lib',
        DATA+r'\runtime\venv\Lib\site-packages',CODE+r'\current.version',CODE+r'\releases'}
    for version in versions:
        root=CODE+'\\releases\\'+version
        required.update((root,root+r'\grid',root+r'\grid\coordinator.py'))
    if not {canonical(p) for p in required}.issubset(seen):raise ValueError('ACL_REQUIRED_SCOPE_MISSING')
    files={DATA+r'\.env',DATA+r'\installer\coordinator-launcher.ps1',
           DATA+r'\runtime\venv\Scripts\python.exe',CODE+r'\current.version'}
    files.update(CODE+'\\releases\\'+v+r'\grid\coordinator.py' for v in versions)
    expected_kinds={canonical(p):('file' if p in files else 'directory') for p in required}
    kinds={canonical(o['path']):o['kind'] for o in objects}
    if any(kinds[p]!=kind for p,kind in expected_kinds.items()):raise ValueError('ACL_REQUIRED_KIND_MISMATCH')
    for path in kinds:
        if path in (DATA.casefold(),CODE.casefold()):continue
        if kinds.get(ntpath.dirname(path))!='directory':raise ValueError('ACL_PARENT_INVENTORY_MISSING')
    return objects


def assess(s):
    r=dict(status='BLOCKED',host_verified=False,execute_authorized=False,cleanup_authorized=False,
           deployment_authorized=False,findings=[])
    try:
        if type(s) is not dict or any(s.get(k) is not True for k in PROOFS):return r
        tasks=s.get('tasks')
        if type(tasks) is not dict or set(tasks)!=TASKS:return r
        if any(type(v) is not dict or v.get('state')!='Disabled' or v.get('enabled') is not False
               or v.get('principal_sid')!=s['roles']['service'] or v.get('action_verified') is not True
               for v in tasks.values()):return r
        if s.get('python_processes')!=[]:return r
        objects=_objects(s)
        for o in objects:
            expected=desired_acl(o['profile'],o['kind'],s['roles'])
            if not o['protected'] or o['aces']!=expected:r['findings'].append(dict(code='DACL_NOT_CANONICAL',path=o['path']))
        r['status']='FAIL' if r['findings'] else 'OFFLINE_MODEL_PASS'
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):pass
    return r


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def prepare(s):
    objects=_objects(s)
    assessment=assess(s)
    if assessment['status']=='BLOCKED':raise ValueError('ACL_PLAN_BLOCKED')
    return dict(schema=1,state='PREPARED',run_id=s['run_id'],head=s['head'],snapshot_sha256=_digest(s),
        cursor=0,originals={o['identity']:o['sddl'] for o in objects},
        changes=[dict(path=o['path'],identity=o['identity'],before_sddl=o['sddl'],
                      desired=desired_acl(o['profile'],o['kind'],s['roles'])) for o in objects],
        activation_authorized=False,apply_authorized=False,rollback_authorized=False)


def advance(j,s,index):
    expected=prepare(s)
    if type(j) is not dict or set(j)!=set(expected):raise ValueError('ACL_JOURNAL_INVALID')
    for key in set(expected)-{'state','cursor'}:
        if type(j[key]) is not type(expected[key]) or j[key]!=expected[key]:
            raise ValueError('ACL_JOURNAL_CHANGED')
    cursor=j['cursor'];count=len(expected['changes'])
    if type(cursor) is not int or type(index) is not int or index!=cursor:
        raise ValueError('ACL_JOURNAL_SEQUENCE_INVALID')
    valid=(j['state']=='PREPARED' and cursor==0 or
           j['state']=='APPLYING_MODEL_ONLY' and 0<cursor<count or
           j['state']=='COMMITTED_MODEL_ONLY' and cursor==count)
    if not valid:raise ValueError('ACL_JOURNAL_SEQUENCE_INVALID')
    if j['state']=='COMMITTED_MODEL_ONLY':return copy.deepcopy(j)
    result=copy.deepcopy(j);result['cursor']+=1
    result['state']='COMMITTED_MODEL_ONLY' if result['cursor']==len(result['changes']) else 'APPLYING_MODEL_ONLY'
    return result


def recover(j,s):
    # Original ACL may be insecure. No automatic restoration or activation.
    # Native identity/custody and post-write receipts require separate proof.
    return dict(status='BLOCKED',rollback_authorized=False,activation_authorized=False,
        reason='NATIVE_CUSTODY_AND_OPERATOR_RECOVERY_REVIEW_REQUIRED',
        snapshot_matches=(type(j) is dict and j.get('snapshot_sha256')==_digest(s)))


def main():
    import argparse
    from pathlib import Path
    from installer.vm_lab_json import load
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot')
    parser.add_argument('--expected-head')
    args=parser.parse_args()
    if not args.snapshot:
        print(json.dumps(dict(mode='PlanOnly',status='BLOCKED',host_verified=False,
                             execute_authorized=False,cleanup_authorized=False)))
        return
    try:
        with Path(args.snapshot).open('rb') as stream:
            raw=stream.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise ValueError('SNAPSHOT_TOO_LARGE')
        value=load(raw.decode('utf-8'))
        if not args.expected_head or value.get('head')!=args.expected_head:raise ValueError('HEAD_MISMATCH')
        result=assess(value)
    except (ValueError,TypeError,AttributeError,UnicodeError,OSError,RecursionError):
        result=dict(status='BLOCKED',host_verified=False,execute_authorized=False,cleanup_authorized=False)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
