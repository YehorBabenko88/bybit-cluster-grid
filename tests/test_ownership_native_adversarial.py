"""Real adversarial kernel tests, opted-in hosted Windows CI GUID fixtures ONLY."""
import ctypes as C
import os
import threading

import pytest

from installer.ownership_native_fixture import new_native_fixture,fixture_policy
from installer.ownership_adversarial_fixture import FixtureAdversary
from installer.ownership_session import run_session,PrototypeBlocked

pytestmark=pytest.mark.skipif(os.environ.get('GRID_OWNERSHIP_NATIVE_FIXTURES')!='1',
                              reason='Adversarial native fixtures require explicit hosted-CI gate')


def new():
    fixture_policy();p=new_native_fixture()
    baseline=run_session(p,lambda v:v.read('tasks.plan.json'))
    assert baseline['synthetic_result']=='PASS' and baseline['resources_released'],baseline
    return p,FixtureAdversary(p)


def clean(p,r):
    assert r['status']=='BLOCKED' and not r['execution_authorized'] and not r['physical_ready']
    assert not p.live and not p.locks and not p._mutex_handles
    assert p.opened==p.closed


def privilege_skip(e):
    if e.winerror in (5,1314):pytest.skip('BLOCKED_UNPROVEN: junction privileges unavailable')
    raise e


def test_real_junction_before_session(record_property):
    p,a=new()
    try:a.junction()
    except OSError as e:privilege_skip(e)
    called=[];r=run_session(p,lambda _:called.append(True));clean(p,r)
    assert r['synthetic_result']=='BLOCKED' and not called
    assert r['code'] in ('REPARSE_OR_TYPE_CHANGED','IDENTITY_CHANGED'),r
    record_property('observed','JUNCTION_CREATED_SESSION_BLOCKED')


def test_real_junction_while_pinned(record_property):
    p,a=new();out=[];returned=[]
    def consume(v):
        try:a.junction();out.append('CREATED')
        except OSError as e:
            if e.winerror in (5,1314):out.append('PRIVILEGE_UNPROVEN');return
            assert e.winerror==32;out.append('DENIED')
        try:returned.append(v.read('tasks.plan.json'))
        except PrototypeBlocked:pass
    r=run_session(p,consume);clean(p,r)
    if out==['PRIVILEGE_UNPROVEN']:pytest.skip('BLOCKED_UNPROVEN: junction privileges unavailable')
    assert (out==['DENIED'] and r['synthetic_result']=='PASS') or (out==['CREATED'] and r['synthetic_result']=='BLOCKED'),r
    if out==['CREATED']:assert not returned
    record_property('observed','JUNCTION_'+out[0]+'_SYNTHETIC_ONLY')


@pytest.mark.parametrize('ancestor',['','data','postgres'])
def test_real_pinned_ancestor_rename(ancestor,record_property):
    p,a=new();out=[];returned=[]
    def consume(v):
        try:a.rename_ancestor(ancestor);out.append('RENAMED')
        except OSError as e:
            assert e.winerror in (5,32);out.append('DENIED')
        try:returned.append(v.read('tasks.plan.json'))
        except PrototypeBlocked:pass
    r=run_session(p,consume);clean(p,r)
    assert (out==['DENIED'] and r['synthetic_result']=='PASS') or (out==['RENAMED'] and r['synthetic_result']=='BLOCKED'),r
    if out==['RENAMED']:assert not returned
    record_property('observed','ANCESTOR_'+out[0]+'_SYNTHETIC_ONLY')


def test_real_protected_acl_change_mid_callback(record_property):
    p,a=new();read=[];mutated=[]
    def consume(v):
        assert v.read('tasks.plan.json')==p.expected['tasks.plan.json']
        a.acl();mutated.append(True)
        read.append(v.read('tasks.plan.json'))  # Preserve the original ACL cause.
    r=run_session(p,consume);clean(p,r)
    assert mutated and r['synthetic_result']=='BLOCKED' and not read
    assert r['code']=='ACL_FOREIGN_WRITER',r
    record_property('observed','FOREIGN_GENERIC_WRITE_ACL_BLOCKED')


def test_real_acl_replace_restore_aba_limit(record_property):
    p,a=new();out=[];returned=[]
    def consume(v):
        a.acl();a.acl(restore=True)
        try:v.read('tasks.plan.json');out.append('READ_RETURNED')
        except PrototypeBlocked:out.append('READ_BLOCKED')
    r=run_session(p,consume);clean(p,r)
    # This is an explicit limitation measurement, NOT an ownership success test.
    assert out and r['synthetic_result'] in ('PASS','BLOCKED')
    record_property('observed','ACL_ABA_UNDETECTED_LIMIT' if r['synthetic_result']=='PASS' else 'ACL_ABA_DETECTED_THIS_RUN')


def test_real_hardlink_race_mid_callback(record_property):
    p,a=new();out=[];returned=[]
    def consume(v):
        try:p.inject('hardlink','tasks.plan.json');out.append('CREATED')
        except OSError as e:
            assert e.winerror in (5,32);out.append('DENIED')
        returned.append(v.read('tasks.plan.json'))  # Propagate original tree/link cause.
    r=run_session(p,consume);clean(p,r)
    assert (out==['DENIED'] and r['synthetic_result']=='PASS') or (out==['CREATED'] and r['synthetic_result']=='BLOCKED'),r
    if out==['CREATED']:assert not returned
    if out==['CREATED']:assert r['code'] in ('TREE_CHANGED','LINK_COUNT_INVALID','STATE_CHANGED'),r
    record_property('observed','HARDLINK_'+out[0]+'_SYNTHETIC_ONLY')


def test_real_concurrent_namespace_mutation(record_property):
    p,a=new();ready=threading.Event();stop=threading.Event();errors=[];returned=[]
    t=threading.Thread(target=a.marker,args=(ready,stop,errors))
    def consume(v):
        t.start()
        try:
            assert ready.wait(10) and not errors
            try:returned.append(v.read('tasks.plan.json'))
            except PrototypeBlocked:pass
        finally:stop.set();t.join(10)
    r=run_session(p,consume);clean(p,r)
    assert t.ident is not None and ready.is_set() and not t.is_alive() and not errors and not returned
    assert r['synthetic_result']=='BLOCKED'
    record_property('observed','CONCURRENT_NAMESPACE_BLOCKED')


def test_bounded_kernel_exhaustion_unproven(monkeypatch,record_property):
    p,a=new();opened=[];original=p._native.open
    def quota(*args):
        if len(opened)==4:raise PrototypeBlocked('NATIVE_OPEN_FAILED')
        h=original(*args);opened.append(h);return h
    monkeypatch.setattr(p._native,'open',quota)
    r=run_session(p,lambda _:pytest.fail('quota failure allowed consumer'));clean(p,r)
    assert len(opened)==4 and r['synthetic_result']=='BLOCKED'
    record_property('observed','BOUNDED_FOUR_REAL_HANDLES_QUOTA_BLOCKED')
    pytest.skip('BLOCKED_UNPROVEN: global kernel exhaustion forbidden; bounded real-handle quota injection validated')


@pytest.mark.parametrize('fault',['close','release'])
def test_cleanup_fault_injection_over_real_handles(fault,monkeypatch,record_property):
    p,a=new();fired=[]
    if fault=='close':
        original=p._native.close
        def fail_once(h):
            if not fired:
                fired.append(True);p._native.uncertain=True;raise PrototypeBlocked('NATIVE_API_FAILED')
            original(h)
        monkeypatch.setattr(p._native,'close',fail_once)
    else:
        original=p._native.k.ReleaseMutex
        def fail_once(h):
            if not fired:fired.append(True);return False
            return original(h)
        monkeypatch.setattr(p._native.k,'ReleaseMutex',fail_once)
    consumed=[]
    def consume(v):v.read('tasks.plan.json');consumed.append(True)
    r=run_session(p,consume);clean(p,r)
    if fault=='release':assert consumed
    assert r['code']=='CLEANUP_UNCERTAIN',r
    assert fired and r['synthetic_result']=='BLOCKED' and not r['resources_released']
    record_property('observed','INJECTED_'+fault.upper()+'_REAL_RESOURCES_DRAINED')


def test_real_abandoned_fixture_mutex(record_property):
    p,a=new();k=p._native.k;name=p._mutex_prefix+'release'
    anchor=k.CreateMutexW(None,False,name);assert anchor
    errors=[]
    def abandon():
        if k.WaitForSingleObject(anchor,0)!=0:errors.append('WAIT_FAILED')
        # Deliberately exit this disposable test thread owning our GUID mutex.
    t=threading.Thread(target=abandon)
    try:
        t.start();t.join(10);assert not t.is_alive() and not errors
        called=[];r=run_session(p,lambda _:called.append(True));clean(p,r)
        assert r['synthetic_result']=='BLOCKED' and not called
        assert r['code']=='NATIVE_MUTEX_BUSY_OR_ABANDONED'
        record_property('observed','REAL_ABANDONED_MUTEX_BLOCKED_AND_RELEASED')
    finally:p._native.close(anchor)


def test_real_expired_view_cannot_poison_next_session(record_property):
    p,a=new();old=[];errors=[]
    r=run_session(p,lambda v:old.append(v));clean(p,r);assert r['synthetic_result']=='PASS'
    def consume(v):
        def stale():
            old[0].close()
            try:old[0].read('tasks.plan.json')
            except PrototypeBlocked:errors.append(True)
        t=threading.Thread(target=stale);t.start();t.join(10);assert not t.is_alive()
        assert v.read('tasks.plan.json')==p.expected['tasks.plan.json']
    r=run_session(p,consume);clean(p,r)
    assert errors and r['synthetic_result']=='PASS'
    record_property('observed','EXPIRED_VIEW_ISOLATED_FROM_NEW_SESSION')


@pytest.mark.parametrize('registry',['file','mutex-dict','mutex-stack'])
def test_real_acquisition_registration_abort(registry,monkeypatch,record_property):
    from test_ownership_adversarial_model import RefuseAppend,RefuseSet
    p,a=new();closed=[];original=p._native.close
    def track(h):original(h);closed.append(h)
    monkeypatch.setattr(p._native,'close',track)
    if registry=='file':
        p.live=RefuseAppend()
        with pytest.raises(MemoryError):p.open('tasks.plan.json',**__import__('installer.ownership_session',fromlist=['OPEN_ARGS']).OPEN_ARGS)
    else:
        if registry=='mutex-dict':p._mutex_handles=RefuseSet()
        else:p.locks=RefuseAppend()
        with pytest.raises(MemoryError):p.acquire('release')
    assert len(closed)==1 and not p.live and not p.locks and not p._mutex_handles
    record_property('observed','REGISTRATION_ABORT_RAW_RESOURCE_CLOSED')
