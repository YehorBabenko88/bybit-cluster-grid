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


def test_native_identity_pins_participate_in_read_share_checks_and_ci_tracks_commands():
    native = (ROOT / 'installer/physical-smoke-s0/S0Bootstrap.cs').read_text()
    assert '0x80000000|0x20000|0x80|(deletion?' in native
    workflow = (ROOT / '.github/workflows/physical-smoke-s0.yml').read_text()
    assert "'docs/PHYSICAL_SMOKE_S0_BOOTSTRAP_COMMANDS.md'" in workflow.split('workflow_dispatch:')[0]


# Fresh-token object DACL is CI setup, not a mutation in the read-only observer.
def test_ci_token_object_defaults_do_not_change_physical_observer():
    fixture = (ROOT / 'installer/physical-smoke-s0-tests/Fixture.cs').read_text()
    assert 'SetFreshTokenDefaultDacl(token,freshSid)' in fixture
    assert 'SetTokenInformation(freshToken,6,tokenDefault,IntPtr.Size)' in fixture
    observer = (ROOT / 'installer/physical-smoke-s0/TokenObserver.cs').read_text()
    assert 'SetTokenInformation' not in observer
    assert 'SetSecurityInfo' not in observer


def _check_postfailure_probe(tmp_path,monkeypatch,runtime):
    import json
    from tools import verify_s0_portable_ci as tool
    calls=[]
    class Process:
        returncode=0
        def __init__(self,args,**kwargs):calls.append(args)
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def communicate(self,timeout):assert timeout==100;return b'DIAGNOSTIC_ONLY',b''
    class Custody:
        def guard(self):calls.append('guard')
    monkeypatch.setattr(tool,'require_hosted',lambda *args:calls.append('host-gate'))
    monkeypatch.setattr(tool.subprocess,'Popen',Process);monkeypatch.setattr(tool,'ROOT',tmp_path)
    (tmp_path/'s0-results').mkdir()
    tool.record_failed_loader_probe(tmp_path,tmp_path,{},'a'*40,'b'*64,Custody(),runtime=runtime)
    receipt=json.loads((tmp_path/'s0-results'/('runtime-postfailure.json' if runtime else 'cold-loader-postfailure.json')).read_text())
    assert receipt['scope']=='POST_FAILURE_DIAGNOSTIC_NOT_ACCEPTANCE'
    assert receipt['original_failure_preserved'] is True
    assert receipt['execute'] is False and receipt['cleanup'] is False
    assert receipt['expected_zip_sha256']=='b'*64
    assert calls[0]=='host-gate' and calls[1]=='guard' and calls[2][1]==('--runtime-diagnostic-parent' if runtime else '--loader-diagnostic-parent')
    assert calls[2][3]=='b'*64

def test_postfailure_probe_success_never_becomes_acceptance(tmp_path,monkeypatch):
    _check_postfailure_probe(tmp_path,monkeypatch,False)

def test_runtime_postfailure_probe_success_never_becomes_acceptance(tmp_path,monkeypatch):
    _check_postfailure_probe(tmp_path,monkeypatch,True)
    native=(ROOT/'installer/physical-smoke-s0/S0UserProfile.cs').read_text()
    launcher=(ROOT/'installer/physical-smoke-s0/S0Launcher.cs').read_text()
    dispatcher=(ROOT/'installer/physical-smoke-s0.ps1').read_text()
    assert 'RunDiagnosticAtUserProfileV1' in native and 'S0_HOSTED_DIAGNOSTIC_ONLY' in native
    assert 'finally { traceRuntime=false; }' in native
    for stage in ('PROFILE_ENTER','PROFILE_HELD','SOURCE_HOLD','SOURCE_HELD','PROCESS_ENTER','PROCESS_CREATED','PROCESS_RESUMED','PROCESS_WAIT_RETURN','SOURCE_RECHECKED'):
        assert 'TraceRuntime("'+stage+'")' in native+launcher
    assert '$DiagnosticStages) { $result = [GridS0.ProcessHost]::RunDiagnosticAtUserProfileV1' in dispatcher


def test_postfailure_probe_cannot_launch_outside_hosted_gate(monkeypatch):
    import pytest
    from tools import verify_s0_portable_ci as tool
    def blocked(*args):raise RuntimeError('HOSTED_REQUIRED')
    def unexpected(*args,**kwargs):raise AssertionError('spawn before host gate')
    monkeypatch.setattr(tool,'require_hosted',blocked);monkeypatch.setattr(tool.subprocess,'Popen',unexpected)
    with pytest.raises(RuntimeError,match='HOSTED_REQUIRED'):
        tool.record_failed_loader_probe(ROOT,ROOT,{},'a'*40,'b'*64,None)
