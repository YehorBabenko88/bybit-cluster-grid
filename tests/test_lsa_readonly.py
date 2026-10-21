"""Offline source contract; no host identities, policies or tokens are queried."""
import hashlib
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = '1067b36e81e3ff613a68dd54d3dd186128666ab7'

def test_pinned_physical_package_unchanged():
    paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', BASE,
        'lab/pc4', 'docs/PC4_SID_ACL_PHYSICAL_TEST_RUNBOOK.md'], cwd=ROOT).decode().splitlines()
    assert len(paths) == 7
    for path in paths:
        original = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT)
        current = (ROOT / path).read_bytes().replace(b'\r\n', b'\n')
        assert hashlib.sha256(original.replace(b'\r\n', b'\n')).digest() == hashlib.sha256(current).digest()

def test_native_surface_read_only():
    code = (ROOT / 'lab/lsa-readonly/LsaRights.cs').read_text()
    for name in ['LsaOpenPolicy', 'LsaEnumerateAccountRights', 'LsaFreeMemory',
                 'LsaClose', 'LsaNtStatusToWinError']:
        assert name in code
    for forbidden in ['LsaAddAccountRights', 'LsaRemoveAccountRights', 'AdjustTokenPrivileges',
                      'CreateProcess', 'LogonUser', 'SetSecurityInfo']:
        assert forbidden not in code
    assert '0x800' in code and '0xC0000034' in code

def test_default_has_no_native_or_group_queries():
    code = (ROOT / 'lab/lsa-readonly/Get-LocalLogonRights.ps1').read_text()
    stop = code.index('if (-not $CollectLocal)')
    assert stop < code.index('Add-Type') < code.index('Get-LocalUser')
    assert 'effective_rights = \'UNKNOWN\'' in code
    assert 'execution_authorized = $false' in code
    for forbidden in ['Enable-LocalUser', 'Set-Acl', 'Start-Process', 'Start-Service',
                      'secedit', 'ntrights', 'Invoke-Command']:
        assert forbidden not in code

def test_mock_gate_is_mandatory():
    code = (ROOT / '.github/workflows/pc4-sid-acl-offline.yml').read_text()
    assert code.count('./lab/lsa-readonly/Test-Offline.ps1') == 2
    assert 'tests/test_lsa_readonly.py' in code
