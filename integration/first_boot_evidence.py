"""Versioned, bounded, non-authorizing first-boot receipts."""
import hashlib
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as E
from .first_boot_policy import ROOT

REQUIRED=('schema-preparation','registry-1-48','preparation-idempotent','runtime-minimum-rights','read-only-role',
 'foreground-coordinator','concurrent-enrollment','enrollment-replay-rejected','two-real-workers','infra-no-market',
 'ingest-auth-rejected','infra-ingest-locked','fleet-stop-ack','pilot-validation','fleet-resume-ack','exclusive-assignments',
 'synthetic-pipeline-postgres','duplicate-ingest-idempotent','changed-delivery-rejected','worker-crash-restart',
 'coordinator-crash-recovery','postgres-restart-recovery','persisted-state-restart','controlled-shutdown','catalog-unchanged','owned-cleanup')


class Evidence:
    def __init__(self,path,head):
        self.path=Path(path);self.path.mkdir()  # never adopt previous run evidence
        self.head=head;self.started=time.time();self.rows=[];self.processes=[]
    def case(self,name,detail=None):
        if name not in REQUIRED or any(r['name']==name for r in self.rows):raise RuntimeError('FIRST_BOOT_CASE_INVENTORY')
        self.rows.append(dict(schema=1,name=name,status='ISOLATED_E2E_PASS',head=self.head,run_id=os.environ['GITHUB_RUN_ID'],
            attempt=os.environ['GITHUB_RUN_ATTEMPT'],at=time.time(),detail=detail,physical='0/10 NOT_RUN',execute='NOT_AUTHORIZED',cleanup='NOT_AUTHORIZED',deployment='NO-GO'))
    def finish(self,error=None):
        seen={r['name'] for r in self.rows}
        missing=[n for n in REQUIRED if n not in seen]
        context=dict(head=self.head,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'])
        rows=self.rows+[dict(schema=1,name=n,status='BLOCKED',**context,at=time.time(),detail=None,
            physical='0/10 NOT_RUN',execute='NOT_AUTHORIZED',cleanup='NOT_AUTHORIZED',deployment='NO-GO') for n in missing]
        (self.path/'events.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows),encoding='utf-8')
        suite=E.Element('testsuite',**context,name='real_isolated_first_boot',tests=str(len(REQUIRED)),failures=str(len(missing)),errors='0',skipped='0')
        for name in REQUIRED:
            node=E.SubElement(suite,'testcase',classname='real_isolated_first_boot',name=name)
            if name in missing:E.SubElement(node,'failure',message='BLOCKED_NOT_EXECUTED_OR_FAILED')
        E.ElementTree(suite).write(self.path/'results.xml',encoding='utf-8',xml_declaration=True)
        summary=dict(schema=1,**context,tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=ROOT,text=True).strip(),
            core_status='ISOLATED_E2E_PASS' if not missing and not error else 'BLOCKED',whole_system='PARTIAL',
            started_at=self.started,ended_at=time.time(),python=sys.version,os=platform.platform(),error_class=error,required=list(REQUIRED),
            missing=missing,processes=self.processes,configuration=dict(api_bind='127.0.0.1',market_data='SYNTHETIC_LOOPBACK_ONLY',
             workers=2,database='ATTESTED_DISPOSABLE_POSTGRES18',external_credentials=False),
            blocked_components=['production-native-apply','authenticated-bootstrap-custody','physical-windows-tokens','real-tailscale-oauth-provisioning','ML-training-dependency/runtime'],
            physical='0/10 NOT_RUN',execute='NOT_AUTHORIZED',cleanup='NOT_AUTHORIZED',deployment='NO-GO')
        (self.path/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.path.iterdir() if p.is_file()}
        sources=subprocess.check_output(['git','ls-files','grid','integration'],cwd=ROOT,text=True).splitlines()
        source_hashes={n:hashlib.sha256(subprocess.check_output(['git','show',self.head+':'+n],cwd=ROOT)).hexdigest() for n in sources}
        (self.path/'sha256.json').write_text(json.dumps(dict(**context,files=hashes,source_sha256=source_hashes),indent=2),encoding='utf-8')
        return not missing and error is None
