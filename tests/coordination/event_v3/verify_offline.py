"""Exact-source cross-platform MODEL checks, never real consensus evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))

import pytest


def main(expected, output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    verify=runpy.run_path('lab/consul/source_receipt.py')['verify']
    before=verify(expected)
    before.update(scope='OFFLINE_MODEL_ONLY',platform=sys.platform)
    (output/'source-before.json').write_text(json.dumps(before,indent=2))
    class Inventory:
        ids=[]
        def pytest_collection_finish(self,session):
            self.ids=[item.nodeid for item in session.items]
    inventory=Inventory()
    xml=output/'tests.xml'
    rc=pytest.main(['tests/coordination/test_event_ordered_v3.py',
        'tests/coordination/test_consul_authority.py','tests/coordination/test_coordination_commands.py',
        '--noconftest','-p','no:cacheprovider','-q','--basetemp='+str(output/'temp'),
        '--junitxml='+str(xml)],plugins=[inventory])
    root=ET.parse(xml).getroot();cases=root.findall('.//testcase')
    after=verify(expected);after.update(scope='OFFLINE_MODEL_ONLY',platform=sys.platform,
        expected_case_count=84,collected_ids=inventory.ids,observed_count=len(cases),pytest_exit=rc,
        junit_sha256=hashlib.sha256(xml.read_bytes()).hexdigest(),
        python=sys.version,qualification='HTTP_MODEL_NOT_CONSUL_QUORUM_OR_PHYSICAL',runtime_go=False)
    (output/'source-after.json').write_text(json.dumps(after,indent=2))
    assert rc==0 and len(inventory.ids)==len(set(inventory.ids))==len(cases)==84
    assert not root.findall('.//skipped') and not root.findall('.//failure') and not root.findall('.//error')
    expected_junit=[]
    for nodeid in inventory.ids:
        parts=nodeid.split('::')
        expected_junit.append(('.'.join([parts[0].removesuffix('.py').replace('/','.'),*parts[1:-1]]),parts[-1]))
    assert sorted(expected_junit)==sorted((c.get('classname'),c.get('name')) for c in cases)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();main(args.expected,args.output)
