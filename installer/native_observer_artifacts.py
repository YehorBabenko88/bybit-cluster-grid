"""Offline reinspection of downloaded GitHub bytes. Never executes extracted/native code."""
import argparse
import hashlib
import io
import json
import re
from pathlib import Path, PurePosixPath
import subprocess
import xml.etree.ElementTree as E
import zipfile
from installer.native_observer_ci import AUTH, ROOT, require, verify_rows, verify_transaction, verify_pure
from installer.vm_lab_json import load


def verify_xml(raw, expected, head, run, attempt):
    require(type(raw) is bytes and 0<len(raw)<=4_000_000 and b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper(),'XML_UNSAFE')
    try:root=E.fromstring(raw)
    except E.ParseError:raise ValueError('XML_INVALID') from None
    suites=list(root.iter('testsuite'));require(suites,'XML_SUITE')
    for s in suites:
        require((s.get('head'),s.get('run_id'),s.get('attempt'))==(head,run,attempt),'XML_CONTEXT')
        require(all(s.get(k)=='0' for k in ('errors','failures','skipped')),'XML_COUNTER')
        require(s.get('tests')==str(len(list(s.iter('testcase')))),'XML_COUNT')
    require(not any(list(root.iter(tag)) for tag in ('error','failure','skipped')),'XML_FALSE_PASS')
    actual=[(c.get('classname'),c.get('name')) for c in root.iter('testcase')]
    require(sorted(actual)==sorted(map(tuple,expected)) and len(set(actual))==len(actual),'XML_INVENTORY')


def inspect_archive(raw, metadata, head, run, attempt, expected_name):
    """Metadata is separately acquired from GitHub, never read from inside the ZIP.

    Checks byte consistency only; a caller-supplied API snapshot is not authentication.
    """
    require(type(head) is str and re.fullmatch('[0-9a-f]{40}',head) and type(run) is str and run.isdecimal() and type(attempt) is str and attempt.isdecimal(),'EXPECTED_CONTEXT')
    require(type(raw) is bytes and len(raw)<=32_000_000,'ZIP_SIZE')
    workflow=metadata['run'];artifact=metadata['artifact']
    require(workflow['head_sha']==head and str(workflow['id'])==run and str(workflow['run_attempt'])==attempt and
            workflow['status']=='completed' and workflow['conclusion']=='success','GITHUB_RUN_NOT_ACCEPTED')
    require(artifact['name']==expected_name and not artifact['expired'] and artifact['workflow_run']['head_sha']==head and
            str(artifact['workflow_run']['id'])==run and type(artifact['id']) is int and artifact['id']>0,'GITHUB_ARTIFACT_CONTEXT')
    digest=hashlib.sha256(raw).hexdigest();require(artifact['digest']=='sha256:'+digest,'GITHUB_ZIP_DIGEST')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        info=archive.infolist();names=[i.filename for i in info]
        require(len(names)==len(set(names)) and len(names)<200 and sum(i.file_size for i in info)<64_000_000,'ZIP_INVENTORY')
        require(all(not n.startswith('/') and '\\' not in n and '..' not in PurePosixPath(n).parts and ':' not in n for n in names),'ZIP_PATH')
        require(all(not i.flag_bits&1 and i.file_size<16_000_000 for i in info),'ZIP_ENTRY')
        files={n:archive.read(n) for n in names if not n.endswith('/')}
    def get(name):
        require(name in files,'ARTIFACT_MISSING:'+name);return files[name]
    receipt=load(get('native-observer-receipt.json').decode('utf-8-sig'))
    require(set(receipt)=={'head','run_id','attempt','source_sha256','binary_sha256','transaction_binary_sha256','artifacts','native_cases','pure_cases','transaction_cases','journal_model_cases','bootstrap_handoff','physical','execute','cleanup','deployment'},'RECEIPT_SCHEMA')
    require(receipt['bootstrap_handoff']=='BLOCKED_NOT_CONSUMED','BOOTSTRAP_NOT_PROVEN')
    require((receipt['head'],receipt['run_id'],receipt['attempt'])==(head,run,attempt),'RECEIPT_CONTEXT')
    require((receipt['physical'],receipt['execute'],receipt['cleanup'],receipt['deployment'])==('0/10 NOT_RUN','NOT_AUTHORIZED','NOT_AUTHORIZED','NO-GO'),'RECEIPT_AUTHORITY')
    def blob(name):return subprocess.check_output(['git','show',head+':'+name],cwd=ROOT)
    inventory=load(blob('tests/fixtures/native_observer_inventory.json').decode())
    expected_sources={n:hashlib.sha256(blob(n)).hexdigest() for n in inventory['source_files']}
    require(receipt['source_sha256']==expected_sources,'SOURCE_DIGESTS')
    required={'native-observer.jsonl','native-observer-pure.json','native-observer.xml','native-observer-pure.xml','native-observer-python.xml','native-observer-python.jsonl',
              'native-observer-transaction.json','native-observer-transaction.jsonl','native-observer-transaction.xml','native-observer-journal-model.json','native-observer-journal-model.xml'}
    require(set(receipt['artifacts'])==required,'ARTIFACT_CLOSURE')
    for name,sha in receipt['artifacts'].items():require(hashlib.sha256(get(name)).hexdigest()==sha,'ARTIFACT_DIGEST')
    for component,key in [('native-acl-observer','binary_sha256'),('native-acl-transaction-fixture','transaction_binary_sha256')]:
        directory=f'installer/{component}/bin/Release/net8.0-windows/'
        hashes={n.removeprefix(directory):hashlib.sha256(v).hexdigest() for n,v in files.items() if n.startswith(directory)}
        stem='NativeAclObserver' if component=='native-acl-observer' else 'NativeAclTransactionFixture'
        require({stem+s for s in ('.exe','.dll','.deps.json','.runtimeconfig.json')}<=set(hashes),'BINARY_REQUIRED')
        require(hashes==receipt[key],'BINARY_CLOSURE')
    rows=[load(line) for line in get('native-observer.jsonl').decode('utf-8-sig').splitlines()]
    verify_rows(rows,inventory['native_cases'],head,run,attempt)
    tx=load(get('native-observer-transaction.json').decode('utf-8-sig'));verify_transaction(tx,inventory['transaction_cases'],head,run,attempt)
    require([load(line) for line in get('native-observer-transaction.jsonl').decode().splitlines()]==tx['cases'],'TX_JSONL')
    pure=load(get('native-observer-pure.json').decode('utf-8-sig'))
    verify_pure(pure,inventory['pure_cases'])
    model=load(get('native-observer-journal-model.json').decode('utf-8-sig'))
    require(model['status']=='OFFLINE_TEST_PASS' and model['cases']==inventory['journal_cases'] and all(model[k] is False for k in AUTH),'JOURNAL_CONTEXT')
    python=[load(line) for line in get('native-observer-python.jsonl').decode().splitlines()]
    require([r['case'] for r in python]==inventory['python_nodes'],'PYTHON_CASES')
    require(all(r['head']==head and r['run_id']==run and r['attempt']==attempt and r['outcome']=='PASS' and r['kind']=='SYNTHETIC_PYTHON' and all(r[k] is False for k in AUTH) for r in python),'PYTHON_CONTEXT')
    for suffix,key,classname in [('', 'native_cases','hosted_guid_observer'),('-pure','pure_cases','synthetic_managed_policy'),
                               ('-transaction','transaction_cases','hosted_guid_transaction'),('-journal-model','journal_cases','synthetic_journal_model')]:
        verify_xml(get('native-observer'+suffix+'.xml'),[(classname,n) for n in inventory[key]],head,run,attempt)
    verify_xml(get('native-observer-python.xml'),inventory['python_junit_cases'],head,run,attempt)
    require((receipt['native_cases'],receipt['pure_cases'],receipt['transaction_cases'],receipt['journal_model_cases'])==
            tuple(len(inventory[k]) for k in ('native_cases','pure_cases','transaction_cases','journal_cases')),'RECEIPT_COUNTS')
    return dict(status='OFFLINE_ARTIFACT_CONSISTENT',head=head,run_id=run,attempt=attempt,artifact_id=artifact['id'],zip_sha256=digest,
                host_verified=False,physical_attestation=False,execute_authorized=False,apply_authorized=False,cleanup_authorized=False,
                custody_authenticated=False,deployment='NO-GO')


def main():
    p=argparse.ArgumentParser();p.add_argument('--zip',required=True);p.add_argument('--metadata',required=True)
    for name in ('head','run','attempt','name'):p.add_argument('--'+name,required=True)
    a=p.parse_args();report=inspect_archive(Path(a.zip).read_bytes(),load(Path(a.metadata).read_text(encoding='utf-8-sig')),a.head,a.run,a.attempt,a.name)
    print(json.dumps(report,sort_keys=True))


if __name__=='__main__':main()
