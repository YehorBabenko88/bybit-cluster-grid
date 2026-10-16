"""Byte matches cannot bridge the native ownership/consumer lifetime boundary."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from installer.isolated_postgres_preflight import assess

COMMIT = '9a7b0735f0ea265854abbf3bfc6cc3c7b897ddf3'


@pytest.mark.parametrize('claim', [
    'canonical_bytes', 'exclusive_handles', 'directory_pin', 'ancestors_pinned',
    'acl_protected', 'generic_rights_safe', 'single_link', 'physical_volume',
    'native_api_success', 'toctou_rechecked', 'mutex_held', 'consumer_in_scope',
])
def test_serialized_proof_cannot_complete_a_native_session(claim):
    request = {'schema': 2, 'adapter_plan_sha256': 'a'*64}
    evidence = {'schema': 1, 'kind': 'OWNERSHIP_CONTRACT_DIAGNOSTIC',
                'byte_contract': 'MATCHED_UNAUTHENTICATED', claim: True,
                'captured_at': '2099-01-01T00:00:00Z'}
    result = assess(request, COMMIT, mode='PreflightReadOnly', evidence=evidence)
    assert result['status'] == 'BLOCKED'
    assert result['blockers'] == ['SCHEMA2_LOCAL_OWNERSHIP_VERIFIER_REQUIRED']
    assert not result['execution_authorized'] and not result['physical_ready']
    assert 'data_root' not in result


@pytest.mark.skipif(os.name != 'nt', reason='Both Windows engines mandatory in Windows CI')
@pytest.mark.parametrize('shell', ['powershell.exe', 'pwsh'])
def test_actual_ps_byte_match_report_cannot_authorize_mapping(shell):
    executable = shutil.which(shell)
    assert executable, f'Required Windows engine missing: {shell}'
    fixture = Path(__file__).resolve().parents[1] / 'installer/tests/test-isolated-ownership-contract.ps1'
    child = subprocess.run([executable, '-NoProfile', '-ExecutionPolicy', 'Bypass',
                            '-File', str(fixture), '-EmitReport'],
                           check=True, capture_output=True, text=True, timeout=30)
    report = json.loads(child.stdout.lstrip('\ufeff'))
    assert report['cases'] == 60
    assert report['providers_invoked'] == 0
    # Frozen ASCII adapter contract: both engines must match the same bytes/hash.
    assert report['plan_sha256'] == '4c8d6803b100d58e3bcc211768ffa0555cb3d932341d5cacec275a01cb6e77f5'
    e = report['canonical_assessment']
    assert e['byte_contract'] == 'MATCHED_UNAUTHENTICATED'
    assert e['status'] == 'BLOCKED'
    assert e['code'] == 'GRID_OWNERSHIP_NATIVE_SESSION_REQUIRED'
    assert e['execution_authorized'] is False and e['physical_ready'] is False
    # Feed the real serializer output through the receiving side; it still cannot
    # create native proof, even if freshly generated and exact bytes matched.
    r = assess({'schema': 2, 'adapter_plan_sha256': report['plan_sha256']},
               COMMIT, mode='PreflightReadOnly', evidence=e, adapter_plan=report)
    assert r['status'] == 'BLOCKED'
    assert r['blockers'] == ['SCHEMA2_LOCAL_OWNERSHIP_VERIFIER_REQUIRED']
