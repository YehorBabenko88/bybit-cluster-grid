"""Read-only independent consistency gate; never physical or provenance attestation."""
import argparse
import hashlib
import os
from pathlib import Path,PurePosixPath
import subprocess
import xml.etree.ElementTree as E
from installer.vm_lab_json import load
from .first_boot_policy import ROOT
from .first_boot_evidence import REQUIRED


def need(value,reason):
    if not value:raise ValueError('FIRST_BOOT_EVIDENCE_'+reason)


def verify_summary(s,head,run,attempt):
    need(type(s) is dict and type(s.get('schema')) is int and s['schema']==1,'SCHEMA')
    need((s.get('head'),s.get('run_id'),s.get('attempt'))==(head,run,attempt),'CONTEXT')
    need(s.get('core_status')=='ISOLATED_E2E_PASS' and s.get('whole_system')=='PARTIAL' and s.get('error_class') is None and s.get('missing')==[],'BLOCKED_REQUIRED_STAGE')
    need(s.get('required')==list(REQUIRED),'INVENTORY')
    need((s.get('physical'),s.get('execute'),s.get('cleanup'),s.get('deployment'))==('0/10 NOT_RUN','NOT_AUTHORIZED','NOT_AUTHORIZED','NO-GO'),'FALSE_AUTHORITY')


def owned_file(root,name):
    need(type(name) is str and name and '\\' not in name and ':' not in name and not name.startswith('/') and '..' not in PurePosixPath(name).parts,'PATH')
    path=root/name
    need(path.is_file() and not path.is_symlink() and root.resolve() in path.resolve().parents,'FILE')
    return path


def verify(root,head,run,attempt):
    root=Path(root);index=load(owned_file(root,'sha256.json').read_text())
    need((index.get('head'),index.get('run_id'),index.get('attempt'))==(head,run,attempt),'INDEX_CONTEXT')
    need(type(index.get('files')) is dict and {'summary.json','results.xml','events.jsonl'}<=set(index['files']),'INDEX')
    for name,sha in index['files'].items():need(hashlib.sha256(owned_file(root,name).read_bytes()).hexdigest()==sha,'FILE_DIGEST')
    need({p.name for p in root.iterdir() if p.is_file()}==set(index['files'])|{'sha256.json'},'FILE_CLOSURE')
    summary=load(owned_file(root,'summary.json').read_text());verify_summary(summary,head,run,attempt)
    need(summary['tree']==subprocess.check_output(['git','rev-parse',head+'^{tree}'],cwd=ROOT,text=True).strip(),'TREE')
    expected_names=subprocess.check_output(['git','ls-tree','-r','--name-only',head,'grid','integration'],cwd=ROOT,text=True).splitlines()
    need(set(index['source_sha256'])==set(expected_names),'SOURCE_CLOSURE')
    for name,sha in index['source_sha256'].items():
        need(hashlib.sha256(subprocess.check_output(['git','show',head+':'+name],cwd=ROOT)).hexdigest()==sha,'SOURCE_DIGEST')
    raw=owned_file(root,'results.xml').read_bytes();need(b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper(),'XML_UNSAFE')
    suite=E.fromstring(raw)
    need(suite.tag=='testsuite' and (suite.get('head'),suite.get('run_id'),suite.get('attempt'))==(head,run,attempt),'XML_CONTEXT')
    need(suite.get('tests')==str(len(REQUIRED)) and all(suite.get(k)=='0' for k in ('errors','failures','skipped')),'XML_COUNTER')
    need([r.get('name') for r in suite]==list(REQUIRED) and all(r.tag=='testcase' and len(r)==0 for r in suite),'XML_CASES')
    events=[load(line) for line in owned_file(root,'events.jsonl').read_text().splitlines()]
    need(len(events)==len(REQUIRED) and {r['name'] for r in events}==set(REQUIRED),'JSONL_INVENTORY')
    for r in events:
        need((r.get('head'),r.get('run_id'),r.get('attempt'))==(head,run,attempt) and r.get('status')=='ISOLATED_E2E_PASS','JSONL_CONTEXT')
        need((r.get('physical'),r.get('execute'),r.get('cleanup'),r.get('deployment'))==('0/10 NOT_RUN','NOT_AUTHORIZED','NOT_AUTHORIZED','NO-GO'),'JSONL_AUTHORITY')
    need(all(type(p.get('exit_code')) is int for p in summary['processes']),'PROCESS_EXIT')
    return dict(status='ISOLATED_E2E_ARTIFACT_CONSISTENT',head=head,run_id=run,attempt=attempt,physical='0/10 NOT_RUN',deployment='NO-GO',provenance_authenticated=False)


if __name__=='__main__':
    import json
    p=argparse.ArgumentParser();p.add_argument('directory');a=p.parse_args()
    print(json.dumps(verify(a.directory,os.environ['EXACT_HEAD_SHA'],os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT'])))
