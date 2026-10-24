"""Strict consistency receipt for CI-only native fixtures; never physical authority."""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

MODEL = 'signed-permit tampered-data tampered-signature wrong-key wrong-head wrong-run wrong-nonce expired replay noncanonical-permit truncated-journal unknown-recovery-anchor invalid-transitions child-environment-allowlist child-environment-missing child-token-user child-token-enabled-admin child-token-deny-only-admin child-token-elevated child-token-high-integrity'.split()
NATIVE = 'held-process-identity-job-token live-cleanup-refused unknown-cleanup-refused cooperative-exit stable-guardian-recovery bounded-marker-cleanup forced-owned-process-stop flush-failure-retention'.split()
ROOT = Path(__file__).resolve().parents[1]
FIELDS = {'schema','kind','status','reason','cases','head','repository','run_id','attempt','host_verified','execute_authorized','cleanup_authorized','physical','g1'}


def need(ok):
    if not ok:
        raise ValueError('CONTROLLER_EVIDENCE_REFUSED')


def load(path):
    data = path.read_bytes()
    need(0 < len(data) <= 131072)
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result)
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs)


def validate(value, kind, head, run, attempt):
    need(type(value) is dict and set(value) == FIELDS)
    need(type(value['schema']) is int and value['schema'] == 1)
    need(value['head'] == head and re.fullmatch('[0-9a-f]{40}', head))
    need(value['run_id'] == run and re.fullmatch('[1-9][0-9]{0,19}', run))
    need(value['attempt'] == attempt and re.fullmatch('[1-9][0-9]{0,9}', attempt))
    need(value['repository'] == 'YehorBabenko88/bybit-cluster-grid')
    need(value['kind'] == kind and value['status'] == 'PASS' and value['reason'] is None)
    need(all(value[k] is False for k in ('host_verified','execute_authorized','cleanup_authorized')))
    need(value['physical'] == '0/10 NOT_RUN' and value['g1'] == 'BLOCKED')
    names = MODEL if kind == 'MODEL_TESTS' else NATIVE
    need(value['cases'] == [dict(name=n, outcome='PASS') for n in names])
    return names


def source_hashes(head):
    paths = subprocess.check_output(['git','ls-tree','-r','--name-only',head], cwd=ROOT, text=True).splitlines()
    prefixes = ('installer/native-g1-controller-fixture/', 'installer/native-acl-observer/', 'installer/native-acl-transaction-fixture/')
    selected = [p for p in paths if p.startswith(prefixes)]
    selected += ['integration/controller_evidence.py','.github/workflows/native-g1-controller.yml']
    need(len(selected) >= 12)
    return {p: hashlib.sha256(subprocess.check_output(['git','show',f'{head}:{p}'], cwd=ROOT)).hexdigest() for p in sorted(set(selected))}


def receipt(folder, head, run, attempt, *, create=False):
    names = []
    for file, kind in [('model.json','MODEL_TESTS'),('native.json','HOSTED_FIXTURE_TESTS')]:
        names += validate(load(folder/file), kind, head, run, attempt)
    if create:
        suite = ET.Element('testsuite', tests=str(len(names)), failures='0', errors='0', skipped='0', head=head, run_id=run, attempt=attempt)
        for name in names:
            ET.SubElement(suite,'testcase', classname='native_controller_ci_fixture', name=name)
        ET.ElementTree(suite).write(folder/'junit.xml', encoding='utf-8', xml_declaration=True)
        rows = [dict(name=n,head=head,run_id=run,attempt=attempt,outcome='PASS',assurance='CI_FIXTURE_ONLY',physical='0/10 NOT_RUN',execute_authorized=False,cleanup_authorized=False) for n in names]
        (folder/'events.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows), encoding='utf-8')
        files = {p: hashlib.sha256((folder/p).read_bytes()).hexdigest() for p in ('model.json','native.json','junit.xml','events.jsonl')}
        (folder/'manifest.json').write_text(json.dumps(dict(head=head,run_id=run,attempt=attempt,files=files,sources=source_hashes(head)),sort_keys=True),encoding='utf-8')
    manifest = load(folder/'manifest.json')
    need(set(manifest) == {'head','run_id','attempt','files','sources'})
    need((manifest['head'],manifest['run_id'],manifest['attempt']) == (head,run,attempt))
    need(manifest['sources'] == source_hashes(head))
    need(set(manifest['files']) == {'model.json','native.json','junit.xml','events.jsonl'})
    for path, digest in manifest['files'].items():
        need(hashlib.sha256((folder/path).read_bytes()).hexdigest() == digest)
    raw = (folder/'junit.xml').read_bytes()
    need(len(raw) < 131072 and b'<!' not in raw)
    xml = ET.fromstring(raw)
    need(xml.tag == 'testsuite' and xml.attrib == dict(tests=str(len(names)),failures='0',errors='0',skipped='0',head=head,run_id=run,attempt=attempt))
    need([c.attrib for c in xml] == [dict(classname='native_controller_ci_fixture',name=n) for n in names])
    need(all(c.tag == 'testcase' and len(c) == 0 for c in xml))
    need(all(not (node.text or '').strip() and not (node.tail or '').strip() for node in xml.iter()))
    rows = (folder/'events.jsonl').read_text(encoding='utf-8').splitlines()
    expected = [dict(name=n,head=head,run_id=run,attempt=attempt,outcome='PASS',assurance='CI_FIXTURE_ONLY',physical='0/10 NOT_RUN',execute_authorized=False,cleanup_authorized=False) for n in names]
    need(rows == [json.dumps(r) for r in expected])
    return dict(tests=len(names),head=head,physical='0/10 NOT_RUN',g1='BLOCKED')


if __name__ == '__main__':
    mode, folder, head, run, attempt = sys.argv[1:]
    need(mode in ('create','verify'))
    print(json.dumps(receipt(Path(folder),head,run,attempt,create=mode == 'create')))
