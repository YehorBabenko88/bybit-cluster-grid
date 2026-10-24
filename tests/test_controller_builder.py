"""Pure CI build-contract tests. Never invoke compiler, child or native APIs."""
import pytest
from tools import build_controller_child as b


def env():
    return dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',
        GITHUB_REPOSITORY='YehorBabenko88/bybit-cluster-grid',GITHUB_JOB='controller-fixture',
        EXACT_HEAD_SHA='a'*40,GITHUB_RUN_ID='12',GITHUB_RUN_ATTEMPT='1')


def test_synthetic_context_only():
    assert b.context(env(),'nt') is None


@pytest.mark.parametrize('key,value',[
    ('GITHUB_ACTIONS','false'),('RUNNER_ENVIRONMENT','self-hosted'),
    ('GITHUB_REPOSITORY','other/repo'),('GITHUB_JOB','other'),('EXACT_HEAD_SHA','HEAD'),
    ('GITHUB_RUN_ID','0'),('GITHUB_RUN_ATTEMPT','-1')])
def test_context_refusal(key,value):
    values=env();values[key]=value
    with pytest.raises(RuntimeError):b.context(values,'nt')


def test_unknown_platform():
    with pytest.raises(RuntimeError):b.context(env(),'posix')


@pytest.mark.parametrize('path',[
    'relative.bat',r'\\server\share\tool.exe','C:\\bad\x00.exe',r'C:\file:stream',
    'C:\\bad\n.exe',r'C:\bad%VAR%\tool.exe',r'C:\bad&calc.exe',r'C:\bad!x.exe',
    'C:\\bad"x.exe',r'C:\bad|x.exe',r'C:\bad>x.exe',r'C:\bad^x.exe'])
def test_cmd_path_substitution_refused(path):
    with pytest.raises(RuntimeError):b.quoted(path)


def test_ordinary_local_tool_path():
    assert b.quoted(r'C:\Program Files (x86)\Microsoft Visual Studio\cl.exe')=='"C:\\Program Files (x86)\\Microsoft Visual Studio\\cl.exe"'
