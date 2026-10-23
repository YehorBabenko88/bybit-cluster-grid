"""Strict synthetic ACL CI receipts. No host inventory or authority."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
NATIVE_CASES=['inherited-directory-write','leaf-rx-does-not-prove-parent-safe','env-readable-before',
 'partial-before-set-fault','failure-preserves-original','secret-users-removed','fixture-only-sddl-rollback',
 'all-users-removed','idempotent-repeat','new-release-inherits-no-users-write','junction-blocked',
 'symlink-blocked','hardlink-count-observed','hardlink-blocked','system-root-outside-fixture-blocked','evidence-not-physical']


def verify_native(rows,head,run,attempt):
    if [r.get('case') for r in rows]!=NATIVE_CASES:raise ValueError('NATIVE_CASE_INVENTORY_MISMATCH')
    keys={'case','outcome','head','run_id','attempt','scope','host_verified','physical_attestation','execute_authorized','cleanup_authorized'}
    for r in rows:
        if (set(r)!=keys or r['outcome']!='PASS' or r['head']!=head or r['run_id']!=run or r['attempt']!=attempt
                or r['scope']!='HOSTED_GUID_ACL_LAYOUT_ONLY' or any(r[k] is not False for k in
                ('host_verified','physical_attestation','execute_authorized','cleanup_authorized'))):
            raise ValueError('NATIVE_RECEIPT_INVALID')


def verify_junit(path,nodes,cases):
    tree=ET.parse(path);suites=list(tree.iter('testsuite'));actual=list(tree.iter('testcase'))
    if (not suites or sum(int(s.get('tests',0)) for s in suites)!=len(nodes)
            or any(int(s.get(k,0))!=0 for s in suites for k in ('skipped','errors','failures'))
            or sorted([c.get('classname'),c.get('name')] for c in actual)!=cases
            or any(c.find(k) is not None for c in actual for k in ('skipped','failure','error'))):
        raise ValueError('JUNIT_INVENTORY_MISMATCH')


def sources(head):
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=head:raise ValueError('CHECKOUT_HEAD_MISMATCH')
    inventory=json.loads((ROOT/'tests/fixtures/ls5_acl_inventory.json').read_text())
    result={}
    for p in inventory['source_files']:
        blob=subprocess.check_output(['git','show',head+':'+p],cwd=ROOT)
        raw=(ROOT/p).read_bytes().replace(b'\r\n',b'\n')
        if raw!=blob:raise ValueError('SOURCE_DIFFERS_FROM_HEAD')
        result[p]=hashlib.sha256(blob).hexdigest()
    return result


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--native',action='store_true');args=parser.parse_args()
    head=os.environ['EXACT_HEAD_SHA'];run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT']
    hashes=sources(head)
    if args.native:
        from installer.vm_lab_json import load
        rows=[load(line) for line in (ROOT/'ls5-acl-windows.jsonl').read_text(encoding='utf-8-sig').splitlines()]
        verify_native(rows,head,run,attempt)
        suite=ET.Element('testsuite',name='HOSTED_GUID_ACL_LAYOUT_ONLY',tests=str(len(rows)),failures='0',errors='0',skipped='0')
        for r in rows:ET.SubElement(suite,'testcase',classname='ls5_acl_guid_fixture',name=r['case'])
        ET.ElementTree(suite).write('ls5-acl-native.xml',encoding='utf-8',xml_declaration=True)
        verify_junit('ls5-acl-native.xml',NATIVE_CASES,sorted([['ls5_acl_guid_fixture',c] for c in NATIVE_CASES]))
        files=['ls5-acl-windows.jsonl','ls5-acl-native.xml'];count=len(rows)
    else:
        import pytest
        inventory=json.loads((ROOT/'tests/fixtures/ls5_acl_inventory.json').read_text())
        nodes=[];calls=[];bad=[]
        class Receipt:
            def pytest_collection_finish(self,session):nodes.extend(x.nodeid for x in session.items)
            def pytest_runtest_logreport(self,report):
                if hasattr(report,'wasxfail') or report.outcome!='passed':bad.append([report.nodeid,report.when,report.outcome])
                if report.when=='call' and report.outcome=='passed':calls.append(report.nodeid)
        code=pytest.main(['-q','-p','no:cacheprovider',*inventory['files'],'--junitxml=ls5-acl-offline.xml','--basetemp=.ls5-ci-temp'],plugins=[Receipt()])
        if code or bad or sorted(nodes)!=inventory['nodes'] or sorted(calls)!=inventory['nodes']:raise ValueError('PYTEST_RECEIPT_MISMATCH')
        verify_junit('ls5-acl-offline.xml',nodes,inventory['junit_cases'])
        (ROOT/'ls5-acl-offline.jsonl').write_text(''.join(json.dumps(dict(case=n,outcome='PASS',head=head,run_id=run,attempt=attempt,
            physical_attestation=False,host_verified=False,execute_authorized=False,cleanup_authorized=False))+'\n' for n in sorted(calls)),encoding='utf-8')
        files=['ls5-acl-offline.xml','ls5-acl-offline.jsonl'];count=len(nodes)
    receipt=dict(head=head,run_id=run,attempt=attempt,count=count,source_sha256=hashes,
        artifacts={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files},physical='0/10 NOT_RUN',
        execute='NOT_AUTHORIZED',cleanup='NOT_AUTHORIZED',deployment='NO-GO')
    (ROOT/('ls5-acl-native-receipt.json' if args.native else 'ls5-acl-offline-receipt.json')).write_text(json.dumps(receipt,sort_keys=True,indent=2),encoding='utf-8')
    print('OFFLINE_OR_GUID_LAYOUT_ONLY; PHYSICAL_NOT_RUN; NO_AUTHORITY')


if __name__=='__main__':main()
