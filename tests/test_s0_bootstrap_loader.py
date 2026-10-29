"""Offline source regressions; these never execute Windows native APIs."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_loader_authenticates_captured_bytes_before_loading_native_code():
    source = (ROOT / 'installer/physical-smoke-s0-bootstrap.ps1').read_text()
    assert source.index('$actual -cne $ExpectedSha256') < source.index('[Reflection.Assembly]::Load($helper)')
    assert source.index('[Reflection.Assembly]::Load($helper)') < source.index('[GridS0.Bootstrap]::PlanPackage(')
    assert '[IO.FileShare]::Read)' in source
    assert '[string]$Action = \'Plan\'' in source
    assert "if ($Action -eq 'Stage' -and -not $Approved)" in source


def test_loader_has_no_extraction_compiler_or_system_mutator():
    source = (ROOT / 'installer/physical-smoke-s0-bootstrap.ps1').read_text().lower()
    for forbidden in ('expand-archive', 'invoke-expression', 'scriptblock', 'executionpolicy',
                      'set-acl', 'icacls', 'start-process', 'stop-process', 'new-item',
                      'add-type -path', 'createprocess', 'logonuser'):
        assert forbidden not in source
    assert 's0_bootstrap_fresh_console_required' in source
    assert '536870912' in source
    assert '4194304' in source
    assert '.copyto(' not in source
    assert '$total -gt $entries[0].length' in source


def test_token_output_does_not_serialize_host_sid_or_groups():
    source = (ROOT / 'installer/physical-smoke-s0-bootstrap.ps1').read_text()
    output = source.split('[pscustomobject]@{', 1)[1].split('\n', 1)[0]
    assert '$facts.Sid' not in output
    assert '$facts.Groups;' not in output
    assert 'Execute=$false' in output and 'Cleanup=$false' in output


def test_initial_literal_loader_matches_reviewed_script_body():
    source = (ROOT / 'installer/physical-smoke-s0-bootstrap.ps1').read_text()
    body = source[source.index('Set-StrictMode'):]
    doc = (ROOT / 'docs/PHYSICAL_SMOKE_S0_BOOTSTRAP_COMMANDS.md').read_text(encoding='utf-8')
    assert body in doc
    assert 'BLOCKED/null argv' in doc


def test_token_policy_rejects_disabled_elevated_privilege_presence():
    source = (ROOT / 'installer/physical-smoke-s0/TokenObserver.cs').read_text()
    assert '!StandardPrivileges.Contains(p.Name)' in source
    assert 'o.Groups.Length==0' in source


def test_hosted_receipt_temp_is_new_protected_directory_not_admin_default():
    source = (ROOT / 'tools/verify_s0_portable_ci.py').read_text()
    assert "create_fresh_root(fixture/'temp',identity.sid)" in source
    assert "(fixture/'temp').mkdir()" not in source


def test_role_import_retains_pc4_input_namespace():
    source = (ROOT / 'installer/physical-smoke-s0/S0Inputs.cs').read_text()
    assert '"PC4/"+item.Key' in source
    assert 'config.json' in source


def test_hosted_test_driver_is_outside_closed_package_tree():
    source = (ROOT / 'tools/verify_s0_portable_ci.py').read_text()
    assert "create_fresh_file(native_build/'bootstrap-loader-test.ps1'" in source
    assert "create_fresh_file(fixture/'temp/bootstrap-loader-test.ps1'" not in source
