"""Pure synthetic staging model. No host observation or execution authority.

Only JSON, hashes and lexical Windows paths; no filesystem/native/process access.
Policy is an independent input, not an authenticated provisioning authorization.
"""
import hashlib
import ntpath
import re

from installer.vm_lab_json import load

SYSTEM = 'S-1-5-18'
ADMINS = 'S-1-5-32-544'
FULL = 0x1F01FF
RX = 0x1200A9
MODIFY = 0x1301BF
GATES = ('S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7')


class Unknown(ValueError):
    pass


def need(value):
    if not value:
        raise ValueError('MODEL_REJECTED')


def known(value):
    if value is None:
        raise Unknown('MODEL_UNKNOWN')
    return value


def keys(obj, names):
    need(type(obj) is dict and set(obj) == set(names.split()))


def flag(value, expected):
    known(value)
    need(type(value) is bool and value is expected)


def sid(value):
    known(value)
    need(type(value) is str and re.fullmatch(r'S-1-5-21-(?:[1-9][0-9]{0,9}-){3}[1-9][0-9]{0,9}', value))
    need(all(int(n) <= 0xFFFFFFFF for n in value.split('-')[4:]))
    return value


def path(value):
    known(value)
    need(type(value) is str and len(value) <= 240 and re.match(r'^[A-Z]:\\', value))
    if len(value) == 3:
        return value
    need(not value.endswith('\\') and '/' not in value and ':' not in value[2:])
    for part in value[3:].split('\\'):
        need(bool(re.fullmatch(r'[A-Za-z0-9_.-]+', part)) and part not in ('.', '..'))
        need(not part.endswith(('.', ' ')))
        need(part.split('.')[0].upper() not in {'CON','PRN','AUX','NUL',
            *('COM'+str(n) for n in range(1,10)), *('LPT'+str(n) for n in range(1,10))})
    return value


def below(child, parent):
    return child.casefold().startswith(parent.casefold().rstrip('\\')+'\\')


def ancestors(value):
    result=[]
    while True:
        parent=ntpath.dirname(value)
        if parent == value:
            return result
        result.append(parent)
        value=parent


def hashes(value):
    need(type(value) is dict and 1 <= len(value) <= 32)
    for name,digest in value.items():
        path(name)
        need(type(digest) is str and re.fullmatch('[0-9a-f]{64}',digest))
    need(len({name.casefold() for name in value}) == len(value))


def policy_check(p):
    keys(p, 'schema operator_sid untrusted_sids run_id source_commit source_files toolchain_files roots volume')
    need(p['schema']=='grid-staging-policy-1')
    sid(p['operator_sid'])
    need(type(p['untrusted_sids']) is list and 1 <= len(p['untrusted_sids']) <= 16)
    for v in p['untrusted_sids']:
        sid(v)
    need(len(set(p['untrusted_sids']))==len(p['untrusted_sids']) and p['operator_sid'] not in p['untrusted_sids'])
    need(type(p['run_id']) is str and re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}',p['run_id']))
    need(type(p['source_commit']) is str and re.fullmatch('[0-9a-f]{40}',p['source_commit']))
    keys(p['roots'],'source temp evidence')
    roots=list(p['roots'].values())
    for root in roots:
        path(root); need(len(root)>3)
    need(len({r.casefold() for r in roots})==3)
    need(not any(below(a,b) for a in roots for b in roots if a!=b))
    need(p['roots']['temp'].endswith('\\'+p['run_id']) and p['roots']['evidence'].endswith('\\'+p['run_id']))
    hashes(p['source_files']); hashes(p['toolchain_files'])
    need(all(below(f,p['roots']['source']) for f in p['source_files']))
    need(not set(p['source_files']) & set(p['toolchain_files']))
    need(not any(f.casefold()==r.casefold() or below(f,r) or below(r,f)
                 for f in p['toolchain_files'] for r in roots))
    files=list(p['source_files'])+list(p['toolchain_files'])
    keys(p['volume'],'drive identity')
    need(type(p['volume']['drive']) is str and re.fullmatch('[A-Z]:',p['volume']['drive']))
    need(type(p['volume']['identity']) is str and re.fullmatch('[A-Za-z0-9-]{1,80}',p['volume']['identity']))
    need(all(f[:2]==p['volume']['drive'] for f in files+roots))
    need(len({f.casefold() for f in files})==len(files))
    need(not any(below(f,g) for f in files for g in files if f!=g))


def gate_identity(s,p):
    keys(s['identity'],'sid elevated groups')
    need(sid(s['identity']['sid'])==p['operator_sid'])
    flag(s['identity']['elevated'],True)
    known(s['identity']['groups'])
    need(s['identity']['groups']==[ADMINS])
    keys(s['authorization'],'scope host_observation execute')
    need(s['authorization']['scope']=='SYNTHETIC_MODEL_ONLY')
    flag(s['authorization']['host_observation'],False)
    flag(s['authorization']['execute'],False)


def objects_check(s,p):
    keys(s['volume'],'drive identity kind custody_trusted')
    need(s['volume']['drive']==p['volume']['drive'] and s['volume']['identity']==p['volume']['identity'])
    need(s['volume']['kind']=='FIXED')
    flag(s['volume']['custody_trusted'],True)
    need(type(s['objects']) is list and 1 <= len(s['objects']) <= 128)
    table={}
    for n in s['objects']:
        keys(n,'path kind owner dacl_protected aces reparse sha256')
        name=path(n['path'])
        need(name.casefold() not in table)
        table[name.casefold()]=n
        need(n['kind'] in ('DIRECTORY','FILE'))
    files={**p['source_files'],**p['toolchain_files']}
    required=set(files) | set(p['roots'].values())
    for name in tuple(required):
        required.update(ancestors(name))
    need(set(table)=={n.casefold() for n in required})
    for name in required:
        n=table[name.casefold()]
        need(n['path']==name)  # canonical spelling, no ambiguous case mappings
        need(n['kind']==('FILE' if name in files else 'DIRECTORY'))
        flag(n['reparse'],False)
        flag(n['dacl_protected'],True)
        writable=any(name==p['roots'][r] or below(name,p['roots'][r]) for r in ('temp','evidence'))
        known(n['owner'])
        need(n['owner'] in ((SYSTEM,ADMINS,p['operator_sid']) if writable else (SYSTEM,ADMINS)))
        known(n['aces'])
        need(type(n['aces']) is list and len(n['aces'])==3)
        expected={SYSTEM:FULL,ADMINS:FULL,p['operator_sid']:MODIFY if writable else RX}
        seen=set()
        for ace in n['aces']:
            keys(ace,'sid type mask inherited')
            known(ace['sid']);known(ace['mask'])
            need(type(ace['sid']) is str and ace['sid'] in expected and ace['sid'] not in seen)
            seen.add(ace['sid'])
            need(ace['type']=='ALLOW' and type(ace['mask']) is int and ace['mask']==expected[ace['sid']])
            flag(ace['inherited'],False)
        if name in files:
            known(n['sha256']); need(n['sha256']==files[name])
        else:
            need(n['sha256'] is None)


def gate_source(s,p):
    v=s['source'];keys(v,'commit hashes_before hashes_at_use hashes_after custody_continuous')
    need(v['commit']==p['source_commit'])
    for key in ('hashes_before','hashes_at_use','hashes_after'):
        known(v[key]); hashes(v[key]);need(v[key]==p['source_files'])
    flag(v['custody_continuous'],True)


def gate_temp(s,p):
    v=s['temp'];keys(v,'TEMP TMP fresh empty shared')
    need(path(v['TEMP'])==path(v['TMP'])==p['roots']['temp'])
    flag(v['fresh'],True);flag(v['empty'],True);flag(v['shared'],False)


def gate_toolchain(s,p):
    v=s['toolchain'];keys(v,'resolved_files search_paths_trusted working_directory_trusted profiles_disabled ps_version bitness')
    known(v['resolved_files']);hashes(v['resolved_files']);need(v['resolved_files']==p['toolchain_files'])
    for key in ('search_paths_trusted','working_directory_trusted','profiles_disabled'):
        flag(v[key],True)
    need(v['ps_version']=='5.1' and type(v['bitness']) is int and v['bitness']==64)


def gate_evidence(s,p):
    v=s['evidence'];keys(v,'fresh overwrite outside_temp exclusive_creation')
    for key in ('fresh','outside_temp','exclusive_creation'):
        flag(v[key],True)
    flag(v['overwrite'],False)


def gate_lifecycle(s,p):
    v=s['lifecycle'];keys(v,'cleanup_authorized unknown_contents reuse')
    for key in v:
        flag(v[key],False)


def validate(snapshot_raw, policy_raw):
    out=dict(schema='grid-staging-result-1',model_status='FAIL',HOST_VERIFIED=False,
             execution_authorized=False,physical_passes=0,physical_tests='0/10 NOT_RUN',
             gates={g:dict(model='BLOCKED',host='BLOCKED',code='NOT_EVALUATED') for g in GATES},
             snapshot_sha256=None,policy_sha256=None)
    try:
        s,p=load(snapshot_raw),load(policy_raw)
        out['snapshot_sha256']=hashlib.sha256(snapshot_raw.encode('utf-8')).hexdigest()
        out['policy_sha256']=hashlib.sha256(policy_raw.encode('utf-8')).hexdigest()
        policy_check(p)
        keys(s,'schema identity objects source temp toolchain evidence lifecycle authorization volume')
        need(s['schema']=='grid-staging-snapshot-1')
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):
        out['gates']={g:dict(model='FAIL',host='BLOCKED',code='INVALID_CONTRACT') for g in GATES}
        return out
    for gate,fn in zip(GATES,(gate_identity,objects_check,gate_source,gate_temp,gate_toolchain,gate_evidence,gate_lifecycle)):
        try:
            fn(s,p);state,code='PASS','SYNTHETIC_ASSERTION_ONLY'
        except Unknown:
            state,code='BLOCKED','MODEL_UNKNOWN'
        except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):
            state,code='FAIL','MODEL_REJECTED'
        out['gates'][gate]=dict(model=state,host='BLOCKED',code=code)
    states=[g['model'] for g in out['gates'].values()]
    out['model_status']='FAIL' if 'FAIL' in states else ('BLOCKED' if 'BLOCKED' in states else 'OFFLINE_MODEL_PASS')
    return out
