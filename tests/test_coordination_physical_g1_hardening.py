"""Regression tests for physical G1 guard boundaries, no host or SQL mutations."""
import ast
import json
from pathlib import Path
from installer.ls5_network_offline import evaluate

def test_network_policy_rejects_oversize_and_bad_unicode():
    for raw in ('x' * 65537, '\ud800', '\udfff', b'{}', json.dumps({'x':'ðŸ˜€' * 16385}, ensure_ascii=False)):
        result = evaluate(raw)
        assert result['policy_valid'] is False
        assert result['execution_authorized'] is False
        assert result['physical_ready'] is False

def test_pg18_credential_validation_survives_optimized_python():
    source = (Path(__file__).resolve().parent / '_pg18_database.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    # Under -O, assert nodes disappear; a required security guard must be an explicit raise.
    guards = [n for n in ast.walk(tree) if isinstance(n, ast.Raise) and
              isinstance(n.exc, ast.Call) and
              isinstance(n.exc.func, ast.Name) and n.exc.func.id == 'RuntimeError' and
              n.exc.args and isinstance(n.exc.args[0], ast.Constant) and
              n.exc.args[0].value == 'PG18_INVALID_ROLE_SECRET_NO_MUTATIONS']
    assert guards
    assert 'assert len(secret)' not in source

import subprocess
import sys
import pytest
from test_ls5_network_offline import baseline

@pytest.mark.parametrize('size,valid',[(65536,True),(65537,False)])
def test_valid_policy_byte_boundary(size,valid):
    raw=json.dumps(baseline(),ensure_ascii=False)
    raw += ' ' * (size-len(raw.encode('utf8')))
    assert len(raw.encode('utf8'))==size
    assert evaluate(raw)['policy_valid'] is valid

@pytest.mark.parametrize('optimized',[False,True])
def test_invalid_credentials_fail_before_any_provider_or_connection(optimized):
    program=r'''
import asyncio, os, sys
sys.path.insert(0,'tests')
import _pg18_database as fixture
calls=[]
def forbidden(*args,**kwargs):
    calls.append('FORBIDDEN'); raise RuntimeError('PROVIDER_OR_CONNECTION_CALLED')
fixture.attest=forbidden
fixture.asyncpg.connect=forbidden
async def run():
    for value in (None, True, 64, [], {}, '', 'a'*63, 'a'*65, 'x'*65537, 'A'*64, "'"+'a'*63, '\ud800', '\U0001f600'*64):
        # Synthetic mapping permits malformed values without writing native environment.
        fixture.os.environ={'GRID_PG18_PASSWORD':value}
        try:
            async with fixture.database():
                raise RuntimeError('UNEXPECTED_ADMISSION')
        except RuntimeError as exc:
            if str(exc)!='PG18_INVALID_ROLE_SECRET_NO_MUTATIONS': raise
    if calls: raise RuntimeError('SIDE_EFFECT_BEFORE_VALIDATION')
asyncio.run(run())
'''
    result=subprocess.run([sys.executable,*(['-O'] if optimized else []),'-c',program],
                          capture_output=True,text=True,timeout=30)
    assert result.returncode==0, result.stderr

from test_ls5_trusted_bootstrap import sample, check, EXEC, VERSION

def test_active_release_is_independent_of_trusted_source_head():
    p,o=sample()
    candidate='38e6ab40928cbdd6a2d6d84cbb05b4628167258f'
    old=EXEC+'\\releases\\'+VERSION+'\\grid\\coordinator.py'
    new=EXEC+'\\releases\\'+candidate+'\\grid\\coordinator.py'
    p['active_release']=o['active_release']=candidate
    p['inventory'][new]=p['inventory'].pop(old)
    for entry in o['files']:
        if entry['path']==old: entry['path']=new
    assert p['head'] != candidate
    result=check(p,o)
    assert result['model_status']=='OFFLINE_MODEL_PASS'
    assert result['status']=='BLOCKED' and not result['host_verified']
    assert not result['execute_authorized']

@pytest.mark.parametrize('attack',['missing_release_path','observation_drift','bad_commit'])
def test_release_rebinding_never_loosens_source_binding(attack):
    p,o=sample()
    if attack=='missing_release_path':p['active_release']=o['active_release']='a'*40
    elif attack=='observation_drift':o['active_release']='a'*40
    else:p['active_release']=o['active_release']='not-a-commit'
    assert check(p,o)['model_status']=='FAIL'
