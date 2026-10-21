"""Checks for the publication receipt verifier, separate from frozen739 tests."""
import copy,json,pathlib
import pytest
from independent_audit.publication_gate import validate_events,validate_junit,verify_shared
ROOT=pathlib.Path(__file__).resolve().parents[1]
EXPECTED=json.loads((ROOT/'independent_audit/publication_inventory.json').read_text())['nodes']

def events():
    return {'nodes':EXPECTED,'calls':[{'nodeid':n,'outcome':'passed','xfail':False} for n in EXPECTED],
            'subtests':[{'outcome':'passed','xfail':False} for _ in range(78)],'bad_reports':[]}

def test_recorded_junit_and_complete_events_are_valid():
    validate_events(events(),EXPECTED)
    validate_junit((ROOT/'independent_audit/evidence/offline-junit.xml').read_text(),EXPECTED)
    verify_shared(ROOT)

@pytest.mark.parametrize('kind',['missing','duplicate','wrong','subcount','skip','xfail','error'])
def test_bad_live_receipts_rejected(kind):
    r=copy.deepcopy(events())
    if kind=='missing':r['calls'].pop()
    elif kind=='duplicate':r['calls'][-1]=r['calls'][0]
    elif kind=='wrong':r['nodes']=r['nodes'][:-1]+['tests/fake.py::test_fake']
    elif kind=='subcount':r['subtests'].pop()
    elif kind=='skip':r['calls'][0]['outcome']='skipped'
    elif kind=='xfail':r['calls'][0]['xfail']=True
    else:r['bad_reports']=['setup-error']
    with pytest.raises(ValueError):validate_events(r,EXPECTED)

@pytest.mark.parametrize('kind',['scope','skip','suitecount','missing'])
def test_bad_junit_rejected(kind):
    import xml.etree.ElementTree as E
    root=E.parse(ROOT/'independent_audit/evidence/offline-junit.xml').getroot()
    suite=next(root.iter('testsuite'));case=next(root.iter('testcase'))
    if kind=='scope':case.set('classname','forged')
    elif kind=='skip':E.SubElement(case,'skipped')
    elif kind=='suitecount':suite.set('tests','739')
    else:suite.remove(case)
    with pytest.raises(ValueError):validate_junit(E.tostring(root,encoding='unicode'),EXPECTED)

def test_inherited_jobs_cannot_run_on_review_branch():
    import re
    for p in (ROOT/'.github/workflows').glob('*.yml'):
        text=p.read_text()
        if p.name in ('offline-rc-review.yml','windows-lab-planning.yml','lab-witness-l1.yml','lab-airgap-a.yml','pgdata-intent-offline.yml','pc4-sid-acl-offline.yml'):
            assert 'services:' not in text and 'self-hosted' not in text
            continue
        jobs=text.split('jobs:\n',1)[1]
        for job in re.split(r'(?m)^  [A-Za-z0-9_-]+:\n',jobs)[1:]:
            first=job.splitlines()[0]
            assert first.startswith('    if:') and "github.head_ref != 'review/offline-rc-20261020'" in first and "github.ref_name != 'review/offline-rc-20261020'" in first,p.name

def test_raw_inventory_reconciles_legacy_without_parameter_corruption():
    old=json.loads((ROOT/'independent_audit/evidence/inventory.json').read_text())['nodes']
    assert [n.replace(chr(92),'/') for n in EXPECTED]==old
    assert len(set(EXPECTED))==739
