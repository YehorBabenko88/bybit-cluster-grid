import asyncio
from types import SimpleNamespace

import pytest
from grid import agent_commands as commands


@pytest.mark.parametrize('action',['update','repair','rollback','uninstall'])
def test_lab_never_enters_legacy_installer_paths(monkeypatch,action):
    monkeypatch.setenv('UNIFIED_DEPLOYMENT_MODE','LAB_SIMULATION')
    def denied(*args,**kwargs):raise AssertionError('legacy filesystem/process path reached')
    monkeypatch.setattr(commands,'_roots',denied)
    monkeypatch.setattr(commands.subprocess,'Popen',denied)
    with pytest.raises(RuntimeError,match='LAB_DEPLOYMENT_ACTUATOR_REQUIRED'):
        asyncio.run(commands.execute_command(SimpleNamespace(),dict(action=action,payload={})))


def test_legacy_script_invocation_keeps_current_execution_policy(monkeypatch,tmp_path):
    monkeypatch.delenv('UNIFIED_DEPLOYMENT_MODE',raising=False)
    installer=tmp_path/'installer';installer.mkdir();(installer/'uninstall.ps1').write_text("'inert test script'\n")
    monkeypatch.setattr(commands,'_roots',lambda:(tmp_path/'install',tmp_path))
    launched=[]
    monkeypatch.setattr(commands.subprocess,'Popen',lambda argv,**kw:launched.append(argv))
    result=asyncio.run(commands.execute_command(SimpleNamespace(),dict(action='uninstall',payload={})))
    assert result['state']=='uninstall_started'
    assert len(launched)==1
    assert '-ExecutionPolicy' not in launched[0] and 'Bypass' not in launched[0]
