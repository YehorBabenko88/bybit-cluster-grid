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

def test_hosted_payload_over_one_mib_uses_bounded_same_handle_writes(monkeypatch):
    from tests.test_s0_windows import Fake
    from s0_smoke import windows as w
    api=Fake();original=api.inspect;events=[]
    monkeypatch.setattr(probe,'require_hosted',lambda *args:None)
    def inspect(handle):
        value=original(handle);value['acl']=w.root_acl('S-1-5-1000')
        if handle=='C:\\safe\\payload':value['directory']=False
        return value
    api.inspect=inspect
    api.create_file=lambda path,sddl:events.append(('create',path,sddl)) or path
    api.write=lambda handle,data:events.append(('write',handle,len(data)))
    api.flush=lambda handle:events.append(('flush',handle))
    raw=b'x'*(2*1024*1024+7)
    with pytest.raises(w.WindowsBlocked):w.create_fresh_file('C:\\safe\\payload','S-1-5-1000',raw,api=api)
    assert not events
    probe.create_hosted_payload('C:\\safe\\payload','S-1-5-1000',raw,api=api)
    assert [x[2] for x in events if x[0]=='write']==[1024*1024,1024*1024,7]
    assert sum(x[0]=='create' for x in events)==1
    assert events[-1]==('flush','C:\\safe\\payload')
    assert 'C:\\safe\\payload' in api.closed


def test_hosted_payload_rejects_hardlink_before_first_write(monkeypatch):
    from tests.test_s0_windows import Fake
    from s0_smoke import windows as w
    api=Fake();original=api.inspect;writes=[]
    monkeypatch.setattr(probe,'require_hosted',lambda *args:None)
    def inspect(handle):
        value=original(handle);value['acl']=w.root_acl('S-1-5-1000')
        if handle=='C:\\safe\\payload':value.update(directory=False,links=2)
        return value
    api.inspect=inspect;api.create_file=lambda *args:'C:\\safe\\payload';api.write=lambda *args:writes.append(args)
    with pytest.raises(w.WindowsBlocked):probe.create_hosted_payload('C:\\safe\\payload','S-1-5-1000',b'x'*(1024*1024+1),api=api)
    assert not writes

def test_hosted_payload_gate_blocks_before_any_open(monkeypatch):
    from tests.test_s0_windows import Fake
    api=Fake()
    def blocked(*args):raise ValueError('HOSTED_WINDOWS_ONLY')
    monkeypatch.setattr(probe,'require_hosted',blocked)
    with pytest.raises(ValueError,match='HOSTED_WINDOWS_ONLY'):
        probe.create_hosted_payload('C:\\safe\\payload','S-1-5-1000',b'x',api=api)
    assert not api.opens


def test_hosted_payload_size_and_types_block_before_create(monkeypatch):
    from tests.test_s0_windows import Fake
    from s0_smoke import windows as w
    monkeypatch.setattr(probe,'require_hosted',lambda *args:None)
    for data,archive in [(True,False),('x',False),(b'x',1),(b'x'*(64*1024*1024+1),False)]:
        api=Fake()
        with pytest.raises(w.WindowsBlocked):probe.create_hosted_payload('C:\\safe\\payload','S-1-5-1000',data,archive=archive,api=api)
        assert not api.opens


def test_hosted_payload_partial_write_closes_only_created_handle(monkeypatch):
    from tests.test_s0_windows import Fake
    from s0_smoke import windows as w
    api=Fake();original=api.inspect;writes=[]
    monkeypatch.setattr(probe,'require_hosted',lambda *args:None)
    def inspect(handle):
        value=original(handle);value['acl']=w.root_acl('S-1-5-1000')
        if handle=='C:\\safe\\payload':value['directory']=False
        return value
    def write(handle,data):
        writes.append((handle,len(data)))
        if len(writes)==2:raise w.WindowsBlocked()
    api.inspect=inspect;api.create_file=lambda *args:'C:\\safe\\payload';api.write=write
    api.flush=lambda *args:pytest.fail('flush after partial failure')
    with pytest.raises(w.WindowsBlocked):probe.create_hosted_payload('C:\\safe\\payload','S-1-5-1000',b'x'*(2*1024*1024+1),api=api)
    assert len(writes)==2 and api.closed.count('C:\\safe\\payload')==1
