from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    return yaml.safe_load((ROOT / '.github/workflows' / name).read_text())

def test_pg16_exclusions_have_mandatory_pg18_companion():
    jobs = load('preflight.yml')['jobs']
    companion = jobs['pg18-transaction-restore']
    assert companion['uses'] == './.github/workflows/ls5-postgres18-disposable.yml'
    assert companion['if'] == jobs['python-preflight']['if']
    unit = next(s for s in jobs['python-preflight']['steps'] if s.get('name') == 'Unit tests')
    for name in ('test_ls5_pg18_disposable.py', 'test_ls5_pg18_restore.py'):
        assert '--ignore=tests/' + name in unit['run']
    gate = jobs['required-preflight']
    assert set(gate['needs']) == {'python-preflight', 'pg18-transaction-restore'}
    assert 'always()' in gate['if']
    assert "needs.python-preflight.result" in gate['steps'][0]['env']['PYTHON_RESULT']
    assert "needs.pg18-transaction-restore.result" in gate['steps'][0]['env']['PG18_RESULT']
    assert '"$PYTHON_RESULT" = success' in gate['steps'][0]['run']
    assert '"$PG18_RESULT" = success' in gate['steps'][0]['run']

def test_pg18_reusable_gate_keeps_seven_real_tests():
    workflow = load('ls5-postgres18-disposable.yml')
    triggers = workflow.get('on', workflow.get(True))
    assert 'workflow_call' in triggers
    job = workflow['jobs']['pg18-lab']
    assert "github.event_name == 'pull_request'" in job['if']
    assert job['runs-on'] == 'ubuntu-latest'
    assert job['services']['postgres']['image'] == 'postgres:18.4'
    steps = job['steps']
    run = next(s['run'] for s in steps if s.get('name') == 'PostgreSQL 18 disposable transaction and restore tests')
    assert 'test_ls5_pg18_disposable.py' in run and 'test_ls5_pg18_restore.py' in run
    receipt = next(s for s in steps if s.get('name') == 'Verify test inventory and publish SHA256 receipt')
    assert receipt['if'] == 'always()'
    assert 'len(cases)==len(expected)' in receipt['run']
    assert 'not any(list(x) for x in cases)' in receipt['run']
