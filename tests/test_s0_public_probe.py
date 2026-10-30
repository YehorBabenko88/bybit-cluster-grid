"""Pure fixtures only: never run the real public diagnostic from local tests."""
import importlib.util
from pathlib import Path

import pytest


def module():
    path = Path(__file__).resolve().parents[1] / 'tools' / 'probe_s0_public_ci.py'
    assert path.is_file(), 'public diagnostic source must exist'
    spec = importlib.util.spec_from_file_location('s0_public_probe_test', path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def environment():
    return dict(GITHUB_ACTIONS='true', RUNNER_ENVIRONMENT='github-hosted', RUNNER_OS='Windows',
        GITHUB_REPOSITORY='YehorBabenko88/bybit-cluster-grid', GITHUB_JOB='s0-windows',
        EXACT_HEAD_SHA='a'*40, GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='2')


def test_closed_hosted_context_only_reads_required_metadata():
    class Opaque:
        def __str__(self): raise AssertionError('must not stringify environment values')
    env = environment(); env['BYBIT_API_KEY'] = Opaque()
    assert module().hosted_context(env, 'fv-az-fixture') == dict(head='a'*40, run_id='123', attempt='2')


@pytest.mark.parametrize('key,value', [('GITHUB_ACTIONS','false'), ('RUNNER_ENVIRONMENT','self-hosted'),
    ('RUNNER_OS','Linux'), ('GITHUB_REPOSITORY','other/repo'), ('GITHUB_JOB','s0-linux'),
    ('EXACT_HEAD_SHA','a'*39), ('GITHUB_RUN_ID','0'), ('GITHUB_RUN_ATTEMPT',True)])
def test_invalid_context_fails_closed(key, value):
    env = environment(); env[key] = value
    with pytest.raises(ValueError): module().hosted_context(env, 'fv-az-fixture')


@pytest.mark.parametrize('host', ['LS5', 'pc4', 'LS5.example'])
def test_real_physical_hostname_is_blocked(host):
    with pytest.raises(ValueError): module().hosted_context(environment(), host)


def test_classification_requires_ack_and_both_topics():
    classify = module().validate_observation
    assert classify(True, 1, 1) == 'OBSERVED_PUBLIC_NOT_PHYSICAL'
    for ack, books, trades in [(False,1,1), (True,0,1), (True,1,0), (False,0,0)]:
        assert classify(ack, books, trades, error='INCOMPLETE') == 'BLOCKED'
    assert classify(True,1,1,error='HTTP_ERROR',http_status=403) == 'BLOCKED'


@pytest.mark.parametrize('args', [(True, True, 1), (True, -1, 1), (True, 4, 1),
    (1,1,1), (True,1,1,'HTTP_ERROR',True), (True,1,1,'HTTP_ERROR',999),
    (True,1,1,None,403), (True,1,1,'secret exception text',None)])
def test_classifier_rejects_impossible_or_opaque_records(args):
    with pytest.raises(ValueError): module().validate_observation(*args)

def test_public_protocol_diagnostics_never_echo_unknown_or_secret_errors():
    detail=module().protocol_detail
    assert detail(ValueError('S0_REDIRECT_BLOCKED'))=='S0_REDIRECT_BLOCKED'
    for error in (ValueError('secret token=never-export'),ValueError('x'*1000000),ValueError(None),ValueError('a','b')):
        assert detail(error)=='UNKNOWN_VALUE_ERROR'
