"""Native fixture tests are opt-in, hosted Windows CI only; NEVER run locally."""
import os
import errno
import pytest
from installer.ownership_session import run_session
from installer.ownership_native_fixture import new_native_fixture, fixture_policy

pytestmark=pytest.mark.skipif(os.environ.get('GRID_OWNERSHIP_NATIVE_FIXTURES')!='1',
                              reason='Native disposable fixtures require explicit hosted-CI gate')


def new():
    fixture_policy()  # Missing/false markers FAIL an opted-in job; never silently skip.
    return new_native_fixture()


def test_native_handles_live_during_consumer_and_view_expires():
    from installer.ownership_session import PrototypeBlocked
    p=new();saved=[]
    def consume(v):
        assert len(p.pinned)==len(p.expected)
        assert p.locks==['release','preparation']
        assert all(p.state(h).identity for h in p.pinned)
        assert len({p.state(h).volume for h in p.pinned})==1
        assert v.read('tasks.plan.json')==p.expected['tasks.plan.json']
        saved.append(v)
    r=run_session(p,consume)
    assert r['synthetic_result']=='PASS',r
    assert r['status']=='BLOCKED' and r['resources_released']
    assert p.opened==p.closed and not p.live
    with pytest.raises(PrototypeBlocked):saved[0].read('tasks.plan.json')


@pytest.mark.parametrize('mutation',['replace','bytes'])
def test_native_writer_and_rename_attempts_denied_while_pinned(mutation):
    p=new();denied=[]
    def consume(v):
        try:p.inject(mutation,'tasks.plan.json')
        except OSError as e:
            assert getattr(e,'winerror',None) in (5,32) or e.errno in (errno.EACCES,errno.EPERM),e
            denied.append(True)
        assert v.read('tasks.plan.json')==p.expected['tasks.plan.json']
    r=run_session(p,consume)
    assert denied and r['synthetic_result']=='PASS',r
    assert p.opened==p.closed and r['resources_released']


@pytest.mark.parametrize('mutation',['replace','hardlink','acl','extra'])
def test_native_preexisting_mutation_blocks_callback(mutation):
    p=new();p.inject(mutation,'tasks.plan.json');called=[]
    r=run_session(p,lambda _:called.append(True))
    assert r['synthetic_result']=='BLOCKED' and not called,r
    assert r['resources_released'] and not p.live


def test_native_acl_changes_after_verification_block_consumer():
    p=new();called=[]
    def race(stage,p,name):
        if stage=='before_consumer':p.inject('acl','tasks.plan.json')
    r=run_session(p,lambda _:called.append(True),hook=race)
    assert r['synthetic_result']=='BLOCKED' and not called,r
    assert r['resources_released'] and p.opened==p.closed


def test_native_callback_exception_releases_pins_and_mutexes():
    p=new()
    def consume(_):raise RuntimeError('PRIVATE secret')
    r=run_session(p,consume)
    assert r['synthetic_result']=='BLOCKED' and 'PRIVATE' not in str(r)
    assert r['resources_released'] and not p.live and not p.locks

@pytest.mark.parametrize('journal',['prepared','retired','duplicate','torn','foreign'])
def test_native_partial_journal_never_reaches_consumer(journal):
    p=new();p.inject(journal,'owner.jsonl');called=[]
    r=run_session(p,lambda _:called.append(True))
    assert r['synthetic_result']=='BLOCKED' and not called,r
    assert r['resources_released'] and p.opened==p.closed


def test_native_premature_handle_closure_poisoned_the_session():
    p=new()
    def consume(v):p.close(p.pinned[-1])
    r=run_session(p,consume)
    assert r['synthetic_result']=='BLOCKED' and r['resources_released']
    assert p.opened==p.closed


@pytest.mark.parametrize('name',['release','preparation'])
def test_native_fixture_mutex_contention_does_not_release_another_threads_lock(name):
    import threading
    p=new();ready=threading.Event();stop=threading.Event();errors=[]
    def owner():
        h=None
        try:
            h=p._native.mutex(p._mutex_prefix+name);ready.set()
            if not stop.wait(20):raise AssertionError('contention test timed out')
        except Exception as e:errors.append(type(e).__name__);ready.set()
        finally:
            if h:
                p._native.check(p._native.k.ReleaseMutex(h));p._native.close(h)
    t=threading.Thread(target=owner);t.start()
    try:
        assert ready.wait(10) and not errors
        r=run_session(p,lambda _:pytest.fail('contention allowed consumer'))
        assert r['synthetic_result']=='BLOCKED',r
        assert r['resources_released'] and not p.live and not p.locks
    finally:stop.set();t.join(10)
    assert not t.is_alive() and not errors
