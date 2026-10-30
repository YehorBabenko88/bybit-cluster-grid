"""Regression contracts for mandatory matrix and artifact topology."""
from pathlib import Path
import subprocess,sys
import yaml
ROOT=Path(__file__).resolve().parents[2]


def workflow():return yaml.safe_load((ROOT/'.github/workflows/grid-physical-maintenance.yml').read_text())


def test_offline_artifact_topology_remains_compatible():
    steps=workflow()['jobs']['s0-offline']['steps']
    artifacts=[x['with'] for x in steps if str(x.get('uses','')).startswith('actions/upload-artifact@')]
    assert len(artifacts)==2
    assert artifacts[0]['path']=='s0-results/' and artifacts[1]['path']=='maintenance-results/'
    assert artifacts[0]['name'].startswith('s0-offline-') and artifacts[1]['name'].startswith('maintenance-offline-')


def test_required_gate_runs_independent_external_digest_consumer_even_after_failures():
    gate=workflow()['jobs']['required-maintenance']
    assert set(gate['needs'])=={'s0-offline','s0-windows'} and gate['if']=='${{ always() }}'
    consumers=[x for x in gate['steps'] if 'verify-matrix' in x.get('run','')]
    assert len(consumers)==1 and consumers[0]['if']=='${{ always() }}'
    assert gate['permissions']=={'contents':'read','actions':'read'}
    native=workflow()['jobs']['s0-windows']
    assert native['strategy']['matrix']=={'shell':['powershell','pwsh'],'python':['3.11','3.12']}
    assert native['strategy']['fail-fast'] is False
    assert not any(x.get('continue-on-error') for x in native['steps'])


def test_collection_inventory_names_are_stable_across_processes():
    command=[sys.executable,'-m','pytest','--collect-only','-q','-p','no:cacheprovider','tests/maintenance']
    first=subprocess.check_output(command,cwd=ROOT,text=True)
    second=subprocess.check_output(command,cwd=ROOT,text=True)
    a=[x for x in first.splitlines() if x.startswith('tests/maintenance/')]
    b=[x for x in second.splitlines() if x.startswith('tests/maintenance/')]
    assert a and a==b
