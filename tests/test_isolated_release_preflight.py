import hashlib
import json
import pytest
from installer.isolated_release_preflight import verify


def release(root):
    files = {'run_coordinator.py': 'raise RuntimeError("TARGET_MUST_NOT_RUN")',
             'grid/control_runtime.py': 'pass', 'grid/collection_ownership.py': 'pass',
             'grid/retention.py': 'pass'}
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())
    manifest = {'version': 'a' * 40, 'files': {
        name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()}}
    (root / 'release-manifest.json').write_text(json.dumps(manifest))


def test_integrity_preflight_never_executes_target_or_authorizes_database(tmp_path):
    release(tmp_path)
    result = verify(tmp_path, 'a' * 40, 'CONTROL')
    assert result['release']['status'] == 'PASS'
    assert result['activation_authorized'] is False
    assert result['database_checked'] is False


@pytest.mark.parametrize('damage', ['hash', 'missing-fencing', 'extra-python', 'manifest', 'sha'])
def test_isolated_preflight_preserves_modern_integrity_guards(tmp_path, damage):
    release(tmp_path)
    if damage == 'hash':
        (tmp_path / 'grid/control_runtime.py').write_text('changed')
    elif damage == 'missing-fencing':
        (tmp_path / 'grid/collection_ownership.py').unlink()
    elif damage == 'extra-python':
        (tmp_path / 'unverified.py').write_text('pass')
    elif damage == 'manifest':
        (tmp_path / 'release-manifest.json').write_text('{broken')
    assert verify(tmp_path, 'b' * 40 if damage == 'sha' else 'a' * 40, 'CONTROL')['release']['status'] == 'BLOCKED'
