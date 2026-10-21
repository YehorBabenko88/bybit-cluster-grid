"""Untrusted PC4 evidence format accounting, never physical attestation."""
import hashlib
import re
import uuid
import xml.etree.ElementTree as E
from installer.vm_lab_json import load
from vm_principal_lab.sid_validation import valid_sid

CASES=('token','own_write','own_read','foreign_read_denied','foreign_write_denied')
ROLES=('Collector','Storage')
BENIGN={'SeChangeNotifyPrivilege','SeShutdownPrivilege','SeUndockPrivilege',
        'SeIncreaseWorkingSetPrivilege','SeTimeZonePrivilege'}
CODES={'OK','ACCESS_DENIED_5','TOKEN_UNSAFE','OWN_IO_FAILED',
       'ACCESS_UNEXPECTEDLY_ALLOWED','ERROR_NOT_ACCESS_DENIED','TIMEOUT'}

def _need(ok):
    if not ok: raise ValueError('PC4_EVIDENCE_INVALID')

def validate(raw, *, expected_run, expected_sids, expected_sha256):
    records=[];valid=False
    try:
        _need(type(expected_run) is str and str(uuid.UUID(expected_run))==expected_run and uuid.UUID(expected_run).version==4)
        _need(type(expected_sids) is dict and set(expected_sids)==set(ROLES))
        for role,rid in zip(ROLES,('1003','1004')):
            sid=expected_sids[role]
            _need(valid_sid(sid) and re.fullmatch(r'S-1-5-21-\d+-\d+-\d+-'+rid,sid) is not None)
        _need(len(set(expected_sids.values()))==2)
        _need(expected_sids['Collector'].rsplit('-',1)[0]==expected_sids['Storage'].rsplit('-',1)[0])
        _need(type(raw) is str and len(raw.encode('utf-8'))<=131072 and raw.endswith('\n') and '\r' not in raw)
        _need(type(expected_sha256) is str and re.fullmatch('[0-9a-f]{64}',expected_sha256) is not None)
        _need(hashlib.sha256(raw.encode('utf-8')).hexdigest()==expected_sha256)
        lines=raw[:-1].split('\n');_need(len(lines)==10)
        records=[load(line) for line in lines]
        pids={}
        for r,(role,case) in zip(records,((a,b) for a in ROLES for b in CASES)):
            _need(type(r) is dict and set(r)=={'schema','source','run_id','role','case','outcome','code','pid','facts'})
            _need(type(r['schema']) is int and r['schema']==1 and r['source']=='NATIVE_PC4_LOCAL')
            _need(r['run_id']==expected_run and r['role']==role and r['case']==case)
            _need(type(r['outcome']) is str and r['outcome'] in ('PASS','FAIL'))
            _need(type(r['code']) is str and r['code'] in CODES)
            _need(type(r['pid']) is int and r['pid']>0)
            if role in pids:_need(pids[role]==r['pid'])
            else:pids[role]=r['pid']
            if r['outcome']=='PASS':_need(r['code']==('ACCESS_DENIED_5' if case.startswith('foreign_') else 'OK'))
            else:_need(r['code'] not in ('OK','ACCESS_DENIED_5'))
            if case=='token':
                f=r['facts']
                _need(type(f) is dict and set(f)=={'sid','admin_group','elevated','integrity_rid','impersonating','privileges'})
                _need(f['sid']==expected_sids[role] and f['admin_group'] is False and f['elevated'] is False and f['impersonating'] is False)
                _need(type(f['integrity_rid']) is int and 0<f['integrity_rid']<=8192)
                _need(type(f['privileges']) is list and 0<len(f['privileges'])<=32)
                seen=set()
                for p in f['privileges']:
                    _need(type(p) is dict and set(p)=={'name','enabled'})
                    name=p['name'];_need(type(name) is str and name in BENIGN and name not in seen)
                    _need(type(p['enabled']) is bool and (not p['enabled'] or name=='SeChangeNotifyPrivilege'))
                    seen.add(name)
            else:_need(r['facts'] is None)
        _need(len(set(pids.values()))==2)
        valid=True
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):pass
    return {'format_valid':valid,'reported_passes':sum(r['outcome']=='PASS' for r in records) if valid else 0,
            'cases':[{'role':r['role'],'case':r['case'],'outcome':r['outcome'],'code':r['code']} for r in records] if valid else [],
            'physical_attestation':False,'airgap_verified':False,'execution_authorized':False,
            'readiness_passed':False,'error':None if valid else 'PC4_EVIDENCE_INVALID'}

def render_junit(result):
    valid=result.get('format_valid') is True
    cases=result['cases'] if valid else [{'role':'FORMAT','case':'evidence','outcome':'FAIL','code':'PC4_EVIDENCE_INVALID'}]
    failures=sum(c['outcome']!='PASS' for c in cases)
    root=E.Element('testsuite',name='PC4_SID_ACL_REPORTED_NOT_ATTESTED',tests=str(len(cases)),failures=str(failures),errors='0',skipped='0')
    for c in cases:
        e=E.SubElement(root,'testcase',classname='PC4.'+c['role'],name=c['case'])
        if c['outcome']!='PASS':E.SubElement(e,'failure',message=c['code'])
    return E.tostring(root,encoding='unicode')
