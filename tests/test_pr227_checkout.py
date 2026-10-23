"""Offline tests, using only disposable Git fixtures; no SQL or physical calls."""
import subprocess

import pytest
from tools import check_ddl_free_ci as gate


@pytest.fixture
def checkout(tmp_path):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=tmp_path).decode().strip()
    git('init', '-q')
    (tmp_path / 'source.py').write_text('original = True\n')
    git('add', 'source.py')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
    return tmp_path, git('rev-parse', 'HEAD')


def test_checkout_exact_clean(checkout):
    gate.verify_checkout(*checkout)


def test_checkout_substitution_rejected(checkout):
    root, sha = checkout
    (root / 'source.py').write_text('original = False\n')
    with pytest.raises(RuntimeError, match='CHECKOUT_DIRTY'):
        gate.verify_checkout(root, sha)


def test_checkout_wrong_head_rejected(checkout):
    root, _ = checkout
    with pytest.raises(RuntimeError, match='CHECKOUT_HEAD_MISMATCH'):
        gate.verify_checkout(root, '0' * 40)


def test_staged_substitution_rejected(checkout):
    root, sha = checkout
    (root / 'source.py').write_text('original = False\n')
    subprocess.check_call(['git', 'add', 'source.py'], cwd=root)
    with pytest.raises(RuntimeError, match='CHECKOUT_DIRTY'):
        gate.verify_checkout(root, sha)
