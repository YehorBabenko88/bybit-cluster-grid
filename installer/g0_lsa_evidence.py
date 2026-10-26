"""Strict direct-policy G0 evidence; never grants effective/physical authorization."""
import re
RIGHTS=('SeInteractiveLogonRight','SeRemoteInteractiveLogonRight','SeNetworkLogonRight','SeBatchLogonRight','SeServiceLogonRight','SeDenyInteractiveLogonRight','SeDenyRemoteInteractiveLogonRight','SeDenyNetworkLogonRight','SeDenyBatchLogonRight','SeDenyServiceLogonRight')
FIELDS=set('schema head run_id host mode collection subjects effective_rights group_completeness execution_authorized cleanup_authorized host_verified actor_tokens_created physical_tests'.split())
ROW=set('name expected_sid observed_sid state code ntstatus win32 cleanup_failed rights logon_rights'.split())
ERRORS={'OPEN_FAILED','ENUMERATE_FAILED','CLEANUP_FAILED','SID_MISMATCH','IDENTITY_FAILED','INVALID_HANDLE','API_OR_DATA_ERROR','UNSUPPORTED_RIGHT','INVALID_G0_SCOPE','ASSEMBLY_DIGEST_MISMATCH','ASSEMBLY_LOAD_FAILED','LSA_INVOCATION_FAILED'}
def need(ok):
    if not ok:raise ValueError('G0_LSA_EVIDENCE_BLOCKED')
def validate(v,*,head,run_id,expected_sids):
    need(type(v) is dict and set(v)==FIELDS)
    need(type(head) is str and re.fullmatch('[0-9a-f]{40}',head) and type(run_id) is str and re.fullmatch('[0-9a-f]{32}',run_id))
    need(v['schema']=='grid-g0-lsa-1' and (v['head'],v['run_id'],v['host'],v['mode'])==(head,run_id,'PC4','MemoryReadOnly'))
    need(v['effective_rights']=='UNKNOWN' and v['group_completeness']=='UNKNOWN' and v['physical_tests']=='0/10 NOT_RUN')
    need(all(v[k] is False for k in ['execution_authorized','cleanup_authorized','host_verified','actor_tokens_created']))
    need(set(expected_sids)=={'GridLabCollector','GridLabStorage'} and len(set(expected_sids.values()))==2)
    for name,sid in expected_sids.items():
        need(type(sid) is str and re.fullmatch(r'S-1-5-21-(?:[1-9][0-9]{0,9}-){3}100[34]',sid) and sid.endswith('1003' if name=='GridLabCollector' else '1004'))
        need(all(int(part)<=0xffffffff for part in sid.split('-')[4:]))
    need(expected_sids['GridLabCollector'].rsplit('-',1)[0]==expected_sids['GridLabStorage'].rsplit('-',1)[0])
    need(type(v['subjects']) is list and len(v['subjects'])==2);seen=set();complete=True
    for r in v['subjects']:
        need(type(r) is dict and set(r)==ROW and r['name'] in expected_sids and r['name'] not in seen);seen.add(r['name'])
        need(r['expected_sid']==expected_sids[r['name']] and r['observed_sid'] in [None,r['expected_sid']])
        need(all(type(r[k]) is int and 0<=r[k]<2**32 for k in ['ntstatus','win32']) and type(r['cleanup_failed']) is bool)
        need(type(r['rights']) is list and len(r['rights'])<=256 and all(type(x) is str and len(x)<=256 and re.fullmatch('Se[A-Za-z]+(?:Right|Privilege)',x) for x in r['rights']))
        need(len(set(r['rights']))==len(r['rights']) and all(not x.endswith('Right') or x in RIGHTS for x in r['rights']))
        need(type(r['logon_rights']) is dict and set(r['logon_rights'])==set(RIGHTS))
        if r['state']=='DIRECT_ONLY':
            need(r['observed_sid']==r['expected_sid'] and r['cleanup_failed'] is False)
            need((r['code']=='ENUMERATED' and r['ntstatus']==r['win32']==0) or (r['code']=='NO_DIRECT_ASSIGNMENTS' and r['ntstatus']==0xC0000034 and r['win32']==2 and not r['rights']))
            need(r['logon_rights']=={x:('ASSIGNED_DIRECT' if x in r['rights'] else 'NOT_DIRECTLY_ASSIGNED') for x in RIGHTS})
        else:
            complete=False;need(r['state']=='UNKNOWN' and r['code'] in ERRORS and not r['rights'] and all(x=='UNKNOWN' for x in r['logon_rights'].values()))
            need(not r['cleanup_failed'] or r['code']=='CLEANUP_FAILED')
    expected='DIRECT_POLICY_OBSERVED' if complete else 'BLOCKED';need(v['collection']==expected);return expected
