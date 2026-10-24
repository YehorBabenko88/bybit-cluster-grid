import copy
import json
import subprocess
import sys
import pytest


@pytest.mark.parametrize('url',['https://api.bybit.com','http://localhost:99','http://127.0.0.1.evil:99','http://u:p@127.0.0.1:99','http://127.0.0.1:5432','http://127.0.0.1:55432','http://127.0.0.1:55433'])
def test_lab_endpoints_refuse_external_alias_credentials_and_reserved_ports(url):
    from integration.first_boot_policy import loopback_endpoint
    with pytest.raises(ValueError):loopback_endpoint(url)


def test_loopback_endpoint_accepts_only_explicit_owned_test_port():
    from integration.first_boot_policy import loopback_endpoint
    assert loopback_endpoint('http://127.0.0.1:18901')==('127.0.0.1',18901)


def test_execute_refuses_before_provider_on_local_host():
    from integration.first_boot_policy import require_ci
    with pytest.raises(RuntimeError,match='HOSTED'):require_ci({})


@pytest.mark.parametrize('field,value',[('RUNNER_ENVIRONMENT','self-hosted'),('RUNNER_OS','Windows'),('GITHUB_JOB','other'),('DOCKER_HOST','tcp://foreign'),('EXACT_HEAD_SHA','HEAD'),('GITHUB_RUN_ID','0')])
def test_unknown_ci_context_is_blocked(field,value,monkeypatch):
    from integration.first_boot_policy import require_ci
    monkeypatch.setattr(sys,'platform','linux')
    env=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',RUNNER_OS='Linux',GITHUB_JOB='pg18',
             GITHUB_REPOSITORY='YehorBabenko88/bybit-cluster-grid',GITHUB_RUN_ID='1',GITHUB_RUN_ATTEMPT='1',EXACT_HEAD_SHA='a'*40)
    env[field]=value
    with pytest.raises(RuntimeError):require_ci(env)


def test_default_entrypoint_is_plan_only():
    p=subprocess.run([sys.executable,'-m','integration.first_boot'],capture_output=True,text=True,timeout=15)
    assert p.returncode==0
    value=json.loads(p.stdout)
    assert value['status']=='PLAN_ONLY' and value['physical']=='0/10 NOT_RUN' and value['execute']=='NOT_AUTHORIZED'


def test_synthetic_feed_payloads_are_labelled_and_deterministic():
    from integration.synthetic_feed import instrument_payload,trade_payload
    assert len(instrument_payload()['result']['list'])==2
    row=trade_payload('BTCUSDT',120001,1)
    assert row['data'][0]['i'].startswith('SYNTHETIC-') and row['topic']=='publicTrade.BTCUSDT'
    assert row['data'][0]==row['data'][1]  # deliberate duplicate for real dedup test


def test_subtest_report_cannot_inflate_primary_inventory_or_hide_failure():
    from _pytest.subtests import SubtestReport
    from types import SimpleNamespace
    from tools.check_first_boot_offline import BootReceipt
    receipt=BootReceipt()
    report=SubtestReport(nodeid='tests/x.py::test_x',location=('tests/x.py',1,'test_x'),keywords={},outcome='passed',longrepr=None,when='call')
    report.context=SimpleNamespace(msg=None,kwargs={'case':'negative'})
    receipt.pytest_runtest_logreport(report)
    assert receipt.passed==[] and len(receipt.subtests)==1
    report.outcome='failed';receipt.pytest_runtest_logreport(report)
    assert receipt.bad
