"""Strict hosted native UserProfile V1 evidence, never physical approval."""
import hashlib
import json
import re
from pathlib import Path
import xml.etree.ElementTree as E
from s0_smoke.policy import load_json

CASES=frozenset(('cold_first_loader','native_profile_plan','unapproved_stage','sid_mismatch',
 'no_local_fallback','atomic_protected_stage','uuid_reuse','source_write_and_replacement',
 'native_python_token_job','runtime_prepare_preflight_status_stop','runtime_execute_evidence_blocked','native_python_profile_resolution','owned_deadline_shutdown',
 'input_and_import','receiver_replay_race','export_identity_and_scope','sender_and_known_hosts',
 'parent_delete_child_dac_owner','same_file_acl_drift','file_id_fault_rejected','junction_reparse','hardlink_source'))
FIELDS={'scope','head','package_sha256','fixture_id','cases','pid','creation_filetime','exit_code','deadline_pid','deadline_exit_code','deadline_timed_out','execute','cleanup'}
RUNTIME_CASES=frozenset(('runtime_prepare_preflight_status_stop','runtime_execute_evidence_blocked'))
CORE_CASES=CASES-RUNTIME_CASES

def validate_runtime_raw(raw,context,pin):
    if type(raw) is not bytes or not 0<len(raw)<=4096:raise ValueError('S0_USER_PROFILE_RUNTIME_BLOCKED')
    value=load_json(raw)
    if (type(value) is not dict or set(value)!={'scope','head','package_sha256','fixture_id','run_id','attempt','cases','execute','cleanup'}
            or value['scope']!='HOSTED_NATIVE_USER_PROFILE_RUNTIME_NOT_PHYSICAL' or value['package_sha256']!=pin
            or any(type(value.get(k)) is not str or value[k]!=context[k] for k in ('head','run_id','attempt'))
            or value['execute'] is not False or value['cleanup'] is not False
            or type(value['cases']) is not list or len(value['cases'])!=2 or any(type(n) is not str for n in value['cases']) or set(value['cases'])!=RUNTIME_CASES):
        raise ValueError('S0_USER_PROFILE_RUNTIME_BLOCKED')
    return value


def validate_profile_raw(raw,head,pin):
    value=load_json(raw)
    if (type(value) is not dict or set(value)!=FIELDS
            or type(head) is not str or re.fullmatch('[0-9a-f]{40}',head) is None
            or type(pin) is not str or re.fullmatch('[0-9a-f]{64}',pin) is None
            or value['head']!=head or value['package_sha256']!=pin
            or value['scope']!='HOSTED_NATIVE_USER_PROFILE_CORE_NOT_PHYSICAL'
            or type(value['fixture_id']) is not str or re.fullmatch(r's0-portable-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}',value['fixture_id']) is None
            or value['deadline_timed_out'] is not True or value['execute'] is not False or value['cleanup'] is not False
            or type(value['cases']) is not list or len(value['cases'])!=len(CORE_CASES)
            or any(type(n) is not str for n in value['cases']) or set(value['cases'])!=CORE_CASES
            or any(type(value[n]) is not int or not 0<value[n]<2**64 for n in ('pid','deadline_pid','creation_filetime'))
            or type(value['exit_code']) is not int or value['exit_code']!=0
            or type(value['deadline_exit_code']) is not int or not 0<=value['deadline_exit_code']<2**32
            or value['deadline_exit_code']==259):
        raise ValueError('S0_USER_PROFILE_RECEIPT_BLOCKED')
    return value


def collect_profile(directory,fixture,context,pin):
    directory=Path(directory)
    runtime=(Path(fixture)/'temp/user-profile-runtime.json').read_bytes()
    if not 0<len(runtime)<=4096:raise ValueError('S0_USER_PROFILE_RUNTIME_BLOCKED')
    runtime_value=validate_runtime_raw(runtime,context,pin)
    raw=(Path(fixture)/'temp/user-profile.json').read_bytes()
    if not 0<len(raw)<=16384:raise ValueError('S0_USER_PROFILE_RECEIPT_BLOCKED')
    value=validate_profile_raw(raw,context['head'],pin)
    if runtime_value['fixture_id']!=value['fixture_id']:raise ValueError('S0_USER_PROFILE_FIXTURE_MISMATCH')
    (directory/'native-userprofile-raw.json').write_bytes(raw)
    (directory/'native-userprofile-runtime.json').write_bytes(runtime)
    suite=E.Element('testsuite',dict(name='native_user_profile_v1',tests=str(len(CASES)),errors='0',failures='0',skipped='0',**context))
    for name in sorted(CASES):E.SubElement(suite,'testcase',dict(classname='HostedNativeUserProfile',name=name))
    xml=E.tostring(suite,encoding='utf-8',xml_declaration=True)
    (directory/'native-userprofile.xml').write_bytes(xml)
    rows=b''.join((json.dumps(dict(context,node=name,status='HOSTED_NATIVE_PASS_NOT_PHYSICAL',execute=False,cleanup=False),sort_keys=True)+'\n').encode() for name in sorted(CASES))
    (directory/'native-userprofile.jsonl').write_bytes(rows)
    record=dict(value,**context,raw_sha256=hashlib.sha256(raw).hexdigest(),runtime_sha256=hashlib.sha256(runtime).hexdigest(),junit_sha256=hashlib.sha256(xml).hexdigest(),jsonl_sha256=hashlib.sha256(rows).hexdigest())
    record.update(scope='HOSTED_NATIVE_USER_PROFILE_NOT_PHYSICAL',cases=sorted(CASES))
    (directory/'native-userprofile.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')


def verify_profile_bundle(read,context,pin):
    record=load_json(read('native-userprofile.json'))
    if type(record) is not dict or set(record)!=FIELDS|set(context)|{'raw_sha256','runtime_sha256','junit_sha256','jsonl_sha256'}:raise ValueError('S0_USER_PROFILE_RECEIPT_BLOCKED')
    if any(record.get(k)!=v or type(record.get(k)) is not str for k,v in context.items()):raise ValueError('S0_USER_PROFILE_CONTEXT_BLOCKED')
    for name,key in [('native-userprofile-raw.json','raw_sha256'),('native-userprofile-runtime.json','runtime_sha256'),('native-userprofile.xml','junit_sha256'),('native-userprofile.jsonl','jsonl_sha256')]:
        if hashlib.sha256(read(name)).hexdigest()!=record[key]:raise ValueError('S0_USER_PROFILE_DIGEST_BLOCKED')
    raw=validate_profile_raw(read('native-userprofile-raw.json'),context['head'],pin)
    runtime_value=validate_runtime_raw(read('native-userprofile-runtime.json'),context,pin)
    if runtime_value['fixture_id']!=raw['fixture_id']:raise ValueError('S0_USER_PROFILE_FIXTURE_MISMATCH')
    combined=dict(raw,scope='HOSTED_NATIVE_USER_PROFILE_NOT_PHYSICAL',cases=sorted(CASES))
    if any(type(record[k]) is not type(v) or record[k]!=v for k,v in combined.items()):raise ValueError('S0_USER_PROFILE_RECEIPT_BLOCKED')
    xml=read('native-userprofile.xml')
    if len(xml)>65536 or b'<!' in xml:raise ValueError('S0_USER_PROFILE_JUNIT_BLOCKED')
    suite=E.fromstring(xml)
    if (suite.tag!='testsuite' or suite.attrib!=dict(name='native_user_profile_v1',tests=str(len(CASES)),errors='0',failures='0',skipped='0',**context)
            or suite.text not in (None,'') or suite.tail not in (None,'') or len(suite)!=len(CASES)):
        raise ValueError('S0_USER_PROFILE_JUNIT_BLOCKED')
    for case,name in zip(suite,sorted(CASES)):
        if case.tag!='testcase' or case.attrib!=dict(classname='HostedNativeUserProfile',name=name) or len(case) or case.text or case.tail:raise ValueError('S0_USER_PROFILE_JUNIT_BLOCKED')
    rows=[load_json(row) for row in read('native-userprofile.jsonl').splitlines()]
    expected=[dict(context,node=name,status='HOSTED_NATIVE_PASS_NOT_PHYSICAL',execute=False,cleanup=False) for name in sorted(CASES)]
    if rows!=expected or any(type(row) is not dict or row.get('execute') is not False or row.get('cleanup') is not False for row in rows):raise ValueError('S0_USER_PROFILE_JSONL_BLOCKED')
    return record
