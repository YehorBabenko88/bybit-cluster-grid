from pathlib import Path
import pytest
from tools import run_grid_handoff_probe as probe
ROOT=Path(__file__).resolve().parents[2]


def test_standalone_fixture_changes_only_runtime_entry_in_memory():
    raw=(ROOT/'installer/physical-smoke-s0-tests/UserProfileTests.cs').read_text()
    output=probe.instrument_fixture(raw)
    assert output.count('HandoffProbe.Run(sourceRoot,head,sid);')==1
    assert output.split(' static void RuntimeActions(')[1]==raw.split(' static void RuntimeActions(')[1]
    assert (ROOT/'installer/physical-smoke-s0-tests/UserProfileTests.cs').read_text()==raw


@pytest.mark.parametrize('raw',['', ' public static void HostedRuntime(', ' static void RuntimeActions('*2])
def test_unrecognized_source_cannot_be_instrumented(raw):
    with pytest.raises(ValueError,match='PROBE_SOURCE_SHAPE_BLOCKED'):probe.instrument_fixture(raw)


def test_probe_cannot_spawn_outside_real_hosted_gate(monkeypatch):
    def blocked(*args):raise ValueError('HOSTED_WINDOWS_ONLY')
    def spawn(*args,**kw):raise AssertionError('SPAWN_BEFORE_GATE')
    monkeypatch.setattr(probe,'require_hosted',blocked);monkeypatch.setattr(probe.subprocess,'Popen',spawn)
    with pytest.raises(ValueError,match='HOSTED_WINDOWS_ONLY'):probe.run()


def test_probe_keeps_watchdogs_and_has_no_physical_acceptance_receipt():
    native=(ROOT/'installer/maintenance/HandoffProbe.cs').read_text()
    child=(ROOT/'installer/maintenance/HandoffChild.ps1').read_text()
    assert 'WaitForExit(30000)' in native and 'Kill(' not in native and 'GetProcessById' not in native
    assert 'TokenObserver.RequireStandard(sid)' in native
    assert 'RunAtUserProfileV1' in child and 'SystemExit(0)' in child
    assert 'SystemExit(0)' not in (ROOT/'installer/physical-smoke-s0.ps1').read_text()
    assert 'user-profile-runtime.json' not in native and 'user-profile.json' not in native
