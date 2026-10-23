"""Pure untrusted-evidence verification. No paths, host observations or I/O.

Consistent JSONL/JUnit/digests never authenticate the producer or physical host.
Caller must obtain expected run/head/SIDs independently. No execution authority.
"""
import hashlib
import re
import xml.etree.ElementTree as ET
from installer.vm_lab_json import load
from installer.pc4_sid_acl_evidence import validate, CASES, ROLES

PROOFS=frozenset({'handle_relative','no_reparse','single_link','stable_file_identity',
    'stable_parent_identity','exclusive_ancestor_custody','same_volume',
    'all_process_handles_exited','receipts_match','no_unknown_children'})


def cleanup_plan(facts):
    status='BLOCKED'
    if type(facts) is dict and set(facts)==PROOFS:
        if any(v is False for v in facts.values()):status='FAIL'
    return {'status':status,'cleanup_authorized':False,'host_verified':False,
            'reason':'NATIVE_HANDLE_RELATIVE_DELETE_NOT_IMPLEMENTED_OR_AUTHORIZED'}


def verify(files, *, expected_run, expected_head, expected_sids):
    result={'status':'BLOCKED','host_verified':False,'physical_attestation':False,
            'cleanup_authorized':False,'execution_authorized':False,'deployment_authorized':False}
    try:
        def need(ok):
            if not ok:raise ValueError('EVIDENCE_BLOCKED')
        need(type(expected_head) is str and re.fullmatch('[0-9a-f]{40}',expected_head))
        required={'manifest.json','results.jsonl','junit.xml','shutdown.json','completed.json','sha256.json'}
        need(type(files) is dict and required.issubset(files) and len(files)<=32)
        need(all(type(n) is str and re.fullmatch(r'[A-Za-z0-9_-]+\.(json|jsonl|xml|txt)',n)
                 and type(b) is bytes and len(b)<=131072 for n,b in files.items()))
        need(len({n.casefold() for n in files})==len(files))
        index=load(files['sha256.json'].decode('utf-8'))
        need(type(index) is dict and set(index)==set(files)-{'sha256.json'})
        need(all(type(v) is str and re.fullmatch('[0-9a-f]{64}',v)
                 and hashlib.sha256(files[n]).hexdigest()==v for n,v in index.items()))
        manifest=load(files['manifest.json'].decode('utf-8'))
        need(manifest['run_id']==expected_run and manifest['source_sha']==expected_head
             and manifest['expected_sids']==expected_sids)
        need(all(manifest[k] is False for k in ('execution_authorized','readiness_passed','airgap_verified')))
        completed=load(files['completed.json'].decode('utf-8'))
        for document in (manifest,completed):
            for flag in ('physical_attestation','host_verified','execution_authorized','cleanup_authorized',
                         'deployment_authorized','readiness_passed','airgap_verified'):
                if flag in document:need(document[flag] is False)
        need(completed['run_id']==expected_run and type(completed['reported_cases']) is int
             and completed['reported_cases']==10 and completed['physical_attestation'] is False
             and completed['airgap_verified'] is False)
        shutdown=load(files['shutdown.json'].decode('utf-8'))
        need(type(shutdown) is dict and set(shutdown)==set(ROLES))
        for state in shutdown.values():
            need(state['status']=='EXIT_CONFIRMED' and type(state['exit_code']) is int
                 and state['exit_code']==0 and state['signal_failed'] is False)
        records=validate(files['results.jsonl'].decode('utf-8'),expected_run=expected_run,
                         expected_sids=expected_sids,expected_sha256=index['results.jsonl'])
        need(records['format_valid'] and records['reported_passes']==10)
        raw=files['junit.xml'];need(b'<!' not in raw)
        xml=ET.fromstring(raw)
        suites=list(xml.iter('testsuite'));need(len(suites)==1)
        need(all(suites[0].get(k)=='0' for k in ('failures','errors','skipped')))
        need(suites[0].get('tests')=='10')
        need(not any(list(xml.iter(tag)) for tag in ('failure','error','skipped')))
        expected=sorted(('PC4.'+r,c) for r in ROLES for c in CASES)
        need(sorted((c.get('classname'),c.get('name')) for c in xml.iter('testcase'))==expected)
        result['status']='OFFLINE_FORMAT_PASS'
    except (ValueError,TypeError,KeyError,AttributeError,UnicodeError,RecursionError,ET.ParseError):
        pass
    return result
