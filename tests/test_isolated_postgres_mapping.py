import pytest
from installer.isolated_postgres_preflight import assess
from test_isolated_postgres_plan import example

COMMIT = '3ec6786bc6e94f2f478278c1ce9f3f07deaa5447'


def test_legacy_preview_is_blocked_without_path_reinterpretation():
    plan = example()
    original = dict(plan)
    result = assess(plan, COMMIT)
    assert result['status'] == 'BLOCKED'
    assert 'LEGACY_SCHEMA1_MAPPING_FORBIDDEN' in result['blockers']
    assert plan == original
    assert result['execution_authorized'] is False


@pytest.mark.parametrize('state', ['PREPARED', 'COMMITTED', 'RETIRED', 'TORN', 'FOREIGN'])
@pytest.mark.parametrize('mode', ['PlanOnly', 'PreflightReadOnly'])
def test_serialized_adapter_ownership_cannot_enable_schema2(state, mode):
    request = {'schema': 2, 'adapter_root': 'C:\\GridLab\\' + 'a'*32 + '_LAB01',
               'adapter_plan_sha256': 'a'*64}
    evidence = {'state': state, 'captured_at': '2099-01-01T00:00:00Z',
                'path_physical': True, 'hardlinks_absent': True,
                'status': 'MAPPING_VERIFIED_READ_ONLY', 'execution_authorized': False}
    result = assess(request, COMMIT, mode=mode, evidence=evidence, adapter_plan=evidence)
    assert result['status'] == 'BLOCKED'
    assert 'SCHEMA2_LOCAL_OWNERSHIP_VERIFIER_REQUIRED' in result['blockers']
    assert result['execution_authorized'] is False
    assert result['physical_ready'] is False
    assert 'data_root' not in result


@pytest.mark.parametrize('root', [r'\\server\GridLab', r'Z:\GridLab',
                                  r'C:\GridLab\alias', r'C:\production', None])
def test_schema2_never_trusts_alternate_root_or_caller_pgdata(root):
    request = {'schema': 2, 'adapter_root': root, 'data_root': r'C:\foreign\pgdata'}
    result = assess(request, COMMIT)
    assert result['status'] == 'BLOCKED'
    assert 'SCHEMA2_LOCAL_OWNERSHIP_VERIFIER_REQUIRED' in result['blockers']
    assert 'data_root' not in result

