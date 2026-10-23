"""Synthetic policies only. No Windows identity/process/filesystem observation."""
import pytest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('mode,code',[('Cleanup','CLEANUP_NOT_AUTHORIZED'),('Execute','EXECUTE_NOT_AUTHORIZED')])
def test_unauthorized_modes_stop_before_host_observation(mode,code):
    source=(ROOT/'lab/pc4/Invoke-Pc4SidAcl.ps1').read_text()
    assert f"if(${mode}){{throw '{code}'}}" in source[:source.index('[Environment]::MachineName')]


def test_no_path_based_cleanup_implementation():
    source=(ROOT/'lab/pc4/Invoke-Pc4SidAcl.ps1').read_text()
    assert 'Remove-Item' not in source and '[IO.Directory]::Delete' not in source


def test_parent_observes_retained_process_handle():
    source=(ROOT/'lab/pc4/Invoke-Pc4SidAcl.ps1').read_text()
    assert 'ReadProcessHandle($processes[$role].Handle,$false)' in source
    assert '::Read($processes[$role].Id' not in source


def test_shutdown_is_a_recorded_failure_boundary():
    source=(ROOT/'lab/pc4/Invoke-Pc4SidAcl.ps1').read_text()
    assert 'Stop-Pc4Actor' in source
    assert 'ACTOR_SHUTDOWN_UNCONFIRMED' in source
    assert 'ACTOR_STARTED' in source
    assert '$r.exit_code -ne 0 -or $r.signal_failed' in source
