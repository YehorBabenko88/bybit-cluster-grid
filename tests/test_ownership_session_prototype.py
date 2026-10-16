"""In-memory handle lifecycle and ownership-to-consumer race regressions."""
import pytest
from installer.ownership_session import ModelFixture, PrototypeBlocked, run_session


def passed(r):
    assert r['status'] == 'BLOCKED'
    assert r['assurance'] == 'SYNTHETIC_ONLY'
    assert not r['execution_authorized'] and not r['physical_ready']
    assert r['synthetic_result'] == 'PASS', r
    assert r['resources_released'] is True


def test_handles_and_mutexes_remain_live_until_callback_returns():
    p=ModelFixture(); borrowed=[]
    def consume(view):
        assert p.locks == ['release','preparation']
        assert all(not h.closed for h in p.pinned)
        assert len(p.pinned) == len(p.expected)
        assert view.read('tasks.plan.json') == p.expected['tasks.plan.json']
        borrowed.append(view)
    r=run_session(p,consume);passed(r)
    assert not p.locks and not p.live
    with pytest.raises(PrototypeBlocked):borrowed[0].read('tasks.plan.json')
    passed(run_session(p,lambda v:v.read('tasks.plan.json')))


@pytest.mark.parametrize('phase',['after_open','after_verify','before_consumer','before_read','after_read','after_consumer'])
@pytest.mark.parametrize('mutation',['replace','reparse','hardlink','acl','bytes','closed','extra'])
def test_mutation_never_yields_synthetic_pass(phase,mutation):
    p=ModelFixture(); fired=[]
    def race(stage,provider,name):
        if stage != phase or fired:return
        fired.append(True)
        provider.inject(mutation,'tasks.plan.json')
    r=run_session(p,lambda v:v.read('tasks.plan.json'),hook=race)
    assert fired
    assert r['synthetic_result'] == 'BLOCKED',r
    assert r['status']=='BLOCKED' and not r['execution_authorized']
    assert r['resources_released'] and not p.live and not p.locks


@pytest.mark.parametrize('failure',['open','state','read','enumerate','unsupported','mutex','close'])
def test_provider_failure_closes_every_remaining_resource(failure):
    p=ModelFixture();p.failure=failure
    r=run_session(p,lambda v:v.read('tasks.plan.json'))
    assert r['synthetic_result']=='BLOCKED'
    assert not p.locks
    if failure != 'close':assert not p.live and r['resources_released']
    else:assert r['resources_released'] is False and p.poisoned
    assert 'PRIVATE' not in str(r)


@pytest.mark.parametrize('journal',['prepared','retired','duplicate','torn','foreign'])
def test_partial_or_retired_journal_blocks_consumer(journal):
    p=ModelFixture();p.inject(journal,'owner.jsonl');called=[]
    r=run_session(p,lambda _:called.append(True))
    assert r['synthetic_result']=='BLOCKED' and not called
    assert not p.live and not p.locks


def test_reentry_poisoning_and_forced_view_closure_block_outer_session():
    p=ModelFixture();nested=[]
    def consume(v):nested.append(run_session(p,lambda _:None))
    r=run_session(p,consume)
    assert nested[0]['synthetic_result']=='BLOCKED'
    assert r['synthetic_result']=='BLOCKED' and not p.live
    q=ModelFixture();r=run_session(q,lambda v:v.close())
    assert r['synthetic_result']=='BLOCKED' and not q.live


def test_callback_exception_is_sanitized_and_handles_are_released():
    p=ModelFixture()
    def consume(_):raise RuntimeError('PRIVATE token=secret')
    r=run_session(p,consume)
    assert r['synthetic_result']=='BLOCKED' and 'PRIVATE' not in str(r)
    assert not p.live and not p.locks


def test_a_swallowed_read_failure_still_poisoned_the_session():
    p=ModelFixture()
    def consume(v):
        p.inject('bytes','tasks.plan.json')
        try:v.read('tasks.plan.json')
        except PrototypeBlocked:pass
    r=run_session(p,consume)
    assert r['synthetic_result']=='BLOCKED' and not p.live

@pytest.mark.parametrize('acl_case',['inherited','generic-write','generic-all','foreign-owner','null','callback-ace','unknown-right','noncanonical'])
def test_unsafe_acls_block_before_callback(acl_case):
    from dataclasses import replace
    from installer.ownership_session import ACL
    p=ModelFixture();node=p.nodes['tasks.plan.json'];a=node['state'].acl
    if acl_case=='inherited':a=replace(a,aces=((0,16,0x1F01FF,p.owner),))
    elif acl_case=='generic-write':a=replace(a,aces=((0,0,0x40000000,'S-1-1-0'),))
    elif acl_case=='generic-all':a=replace(a,aces=((0,0,0x10000000,'S-1-1-0'),))
    elif acl_case=='foreign-owner':a=replace(a,owner='S-1-1-0')
    elif acl_case=='null':a=None
    elif acl_case=='callback-ace':a=replace(a,aces=((9,0,1,p.owner),))
    elif acl_case=='unknown-right':a=replace(a,aces=((0,0,0x02000000,p.owner),))
    else:a=replace(a,aces=((0,0,1,p.owner),(1,0,1,p.owner)))
    node['state']=replace(node['state'],acl=a);called=[]
    r=run_session(p,lambda _:called.append(True))
    assert r['synthetic_result']=='BLOCKED' and not called
    assert not p.live and not p.locks


def test_cross_thread_borrowing_blocks_without_native_read():
    import threading
    p=ModelFixture();failures=[]
    def consume(v):
        def other_thread():
            try:v.read('tasks.plan.json')
            except PrototypeBlocked:failures.append(True)
        t=threading.Thread(target=other_thread);t.start();t.join(5)
        assert not t.is_alive()
    r=run_session(p,consume)
    assert failures and r['synthetic_result']=='BLOCKED'
    assert not p.live and not p.locks


def test_native_policy_fails_before_loading_or_creating_anything(monkeypatch):
    from installer import ownership_native_fixture as native
    monkeypatch.delenv('GRID_OWNERSHIP_NATIVE_FIXTURES',raising=False)
    monkeypatch.setattr(native.tempfile,'mkdtemp',lambda **_:pytest.fail('fixture created before guard'))
    monkeypatch.setattr(native,'_Native',lambda:pytest.fail('native API loaded before guard'))
    with pytest.raises(PrototypeBlocked,match='NATIVE_FIXTURE_POLICY_BLOCKED'):native.new_native_fixture()

def test_native_directory_page_parser_rejects_offsets_and_invalid_utf16():
    import struct
    from installer.ownership_native_fixture import _directory_names
    b=bytearray(128);struct.pack_into('<I',b,60,10);b[104:114]='hello'.encode('utf-16-le')
    assert _directory_names(bytes(b))==['hello']
    for offset,length in [(7,10),(120,10),(0,999999),(0,3),(0,0)]:
        bad=bytearray(b);struct.pack_into('<I',bad,0,offset);struct.pack_into('<I',bad,60,length)
        with pytest.raises(PrototypeBlocked):_directory_names(bytes(bad))
    bad=bytearray(b);struct.pack_into('<I',bad,60,2);bad[104:106]=b'\x00\xd8'
    with pytest.raises(PrototypeBlocked):_directory_names(bytes(bad))

def test_probe_close_failure_is_tracked_and_registry_is_drained():
    p=ModelFixture();original=p.close;fired=[]
    def fail_once(h):
        if h not in p.pinned and not fired:
            fired.append(True);raise PrototypeBlocked('API_UNAVAILABLE')
        original(h)
    p.close=fail_once
    r=run_session(p,lambda _:None)
    assert fired and r['synthetic_result']=='BLOCKED'
    assert r['resources_released'] is False
    assert not p.live and not p.locks


def test_identifier_shaped_consumer_secret_never_becomes_a_report_code():
    p=ModelFixture()
    def consume(_):raise PrototypeBlocked('PRIVATE_TOKEN')
    r=run_session(p,consume)
    assert r['synthetic_result']=='BLOCKED' and 'PRIVATE' not in str(r)

@pytest.mark.parametrize('failed_operation',['release','close'])
def test_native_mutex_bookkeeping_survives_failed_release_or_close_without_win32(failed_operation):
    from installer.ownership_native_fixture import _WindowsFixture
    class FakeNative:
        def __init__(self):self.k=self;self.uncertain=False;self.releases=0;self.closes=0
        def ReleaseMutex(self,h):
            self.releases+=1
            return not (failed_operation=='release' and self.releases==1)
        def close(self,h):
            self.closes+=1
            if failed_operation=='close' and self.closes==1:
                self.uncertain=True;raise PrototypeBlocked('NATIVE_API_FAILED')
    p=object.__new__(_WindowsFixture);ModelFixture.__init__(p)
    p._native=FakeNative();p.locks=['release']
    p._mutex_handles={'release':{'handle':123,'released':False}}
    with pytest.raises(PrototypeBlocked):p.release('release')
    assert 'release' in p._mutex_handles and p.locks==['release']
    p.release('release')
    assert not p._mutex_handles and not p.locks and p.cleanup_uncertain
    assert p._native.releases==(2 if failed_operation=='release' else 1)


def test_keyboard_interrupt_releases_and_poisons_the_fixture():
    p=ModelFixture()
    def consume(_):raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):run_session(p,consume)
    assert p.poisoned and not p.live and not p.locks

def test_two_native_mutexes_survive_inner_release_failure_without_out_of_order_cleanup():
    from installer.ownership_native_fixture import _WindowsFixture
    class FakeNative:
        def __init__(self):self.k=self;self.uncertain=False;self.fired=False;self.events=[]
        def ReleaseMutex(self,h):
            self.events.append(('release',h))
            if h=='preparation' and not self.fired:self.fired=True;return False
            return True
        def close(self,h):self.events.append(('close',h))
    class Fixture(_WindowsFixture):
        open=ModelFixture.open;state=ModelFixture.state;read=ModelFixture.read
        close=ModelFixture.close;tree=ModelFixture.tree
        def acquire(self,name):
            self._mutex_handles[name]={'handle':name,'released':False};self.locks.append(name)
    p=object.__new__(Fixture);ModelFixture.__init__(p)
    p._native=FakeNative();p._mutex_handles={}
    r=run_session(p,lambda v:v.read('tasks.plan.json'))
    assert r['synthetic_result']=='BLOCKED' and not r['resources_released']
    assert not p._mutex_handles and not p.locks and not p.live
    assert p._native.events==[('release','preparation'),('release','preparation'),
                             ('close','preparation'),('release','release'),('close','release')]
