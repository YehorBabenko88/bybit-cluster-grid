"""Additional pure regressions. No native APIs or fixture creation locally."""
import pytest
from installer.ownership_session import ModelFixture,PrototypeBlocked,run_session,OPEN_ARGS
from installer.ownership_native_fixture import _WindowsFixture


class FakeNative:
    owner='owner'
    uncertain=False
    def __init__(self):self.k=self;self.closed=[];self.released=[]
    def open(self,*_):return 123
    def mutex(self,*_):return 456
    def close(self,h):self.closed.append(h)
    def ReleaseMutex(self,h):self.released.append(h);return True


class RefuseAppend(list):
    def append(self,_):raise MemoryError('PRIVATE allocation failed')


class RefuseSet(dict):
    def __setitem__(self,k,v):raise MemoryError('PRIVATE allocation failed')


def native_model():
    p=object.__new__(_WindowsFixture);ModelFixture.__init__(p)
    p._native=FakeNative();p._root=__import__('pathlib').Path('unused')
    p._mutex_prefix='synthetic';p._mutex_handles={}
    return p


def test_file_registration_failure_closes_raw_handle_before_propagating():
    p=native_model();p.live=RefuseAppend()
    with pytest.raises(MemoryError):p.open('tasks.plan.json',**OPEN_ARGS)
    assert p._native.closed==[123]
    assert not p.live


@pytest.mark.parametrize('registry',['dict','stack'])
def test_mutex_registration_failure_releases_and_closes_raw_mutex(registry):
    p=native_model()
    if registry=='dict':p._mutex_handles=RefuseSet()
    else:p.locks=RefuseAppend()
    with pytest.raises(MemoryError):p.acquire('release')
    assert p._native.released==[456] and p._native.closed==[456]
    assert not p._mutex_handles and not p.locks


def test_session_refuses_to_adopt_or_close_preexisting_handles():
    p=ModelFixture();h=p.open('tasks.plan.json',**OPEN_ARGS)
    r=run_session(p,lambda _:pytest.fail('pre-existing scope adopted'))
    assert r['synthetic_result']=='BLOCKED' and p.live==[h] and not h.closed
    p.close(h)


def test_model_acl_aba_is_an_explicit_unproven_limit():
    p=ModelFixture();original=p.nodes['tasks.plan.json']['state'];changed=[]
    def race(stage,p,name):
        if stage=='before_consumer':
            p.inject('acl','tasks.plan.json');changed.append(True)
            p.nodes['tasks.plan.json']['state']=original
    r=run_session(p,lambda v:v.read('tasks.plan.json'),hook=race)
    assert changed and r['synthetic_result']=='PASS'  # Snapshot ABA limit, NOT ownership.
    assert r['status']=='BLOCKED' and not r['execution_authorized']

def test_ace_sid_bytes_are_bounded_before_decoding():
    import struct
    from installer.ownership_native_fixture import _ace
    sid=bytes((1,1))+b'\x00'*5+b'\x05'+struct.pack('<I',18)
    ace=struct.pack('<BBHI',0,0,8+len(sid),0x1F01FF)+sid
    assert _ace(ace)==(0,0,0x1F01FF,'S-1-5-18')
    for raw in (ace[:10],ace+b'\x00',ace[:9]+b'\xff'+ace[10:],
                struct.pack('<BBHI',9,0,len(ace),1)+sid,
                struct.pack('<BBHI',0,0,len(ace)+4,1)+sid):
        with pytest.raises(PrototypeBlocked):_ace(raw)

def test_expired_view_close_cannot_poison_a_later_session():
    p=ModelFixture();old=[]
    assert run_session(p,lambda v:old.append(v))['synthetic_result']=='PASS'
    r=run_session(p,lambda _:old[0].close())
    assert r['synthetic_result']=='PASS' and not p.poisoned


def test_expired_view_cross_thread_read_cannot_poison_a_later_session():
    import threading
    p=ModelFixture();old=[];failures=[]
    assert run_session(p,lambda v:old.append(v))['synthetic_result']=='PASS'
    def consume(_):
        def stale():
            try:old[0].read('tasks.plan.json')
            except PrototypeBlocked:failures.append(True)
        t=threading.Thread(target=stale);t.start();t.join(5)
        assert not t.is_alive()
    r=run_session(p,consume)
    assert failures and r['synthetic_result']=='PASS' and not p.poisoned

def test_junction_payload_requires_local_target():
    import struct
    from installer.ownership_adversarial_fixture import _junction_buffer
    data=_junction_buffer(r'C:\Temp\fixture\releases')
    tag,length,reserved=struct.unpack_from('<IHH',data)
    assert tag==0xA0000003 and reserved==0 and length==len(data)-8
    for target in ('\\\\server\\share','C:/temp','C:\\temp\x00foreign','relative'):
        with pytest.raises(PrototypeBlocked):_junction_buffer(target)

def test_adversarial_report_never_silently_accepts_skips_or_failures():
    import xml.etree.ElementTree as E
    from installer.tests.verify_ownership_adversarial import assess,EXPECTED,OBSERVATIONS
    def report():
        root=E.Element('testsuite')
        for name in sorted(EXPECTED):
            case=E.SubElement(root,'testcase',name=name)
            props=E.SubElement(case,'properties')
            E.SubElement(props,'property',name='observed',value=sorted(OBSERVATIONS[name])[0])
        return root
    r=assess(report(),'a'*40)
    assert r['status']=='BLOCKED' and r['tested_cases']==17
    xml=report();E.SubElement(xml[0],'skipped',message='ordinary skipped test')
    with pytest.raises(ValueError):assess(xml,'a'*40)
    xml=report();E.SubElement(xml[0],'failure')
    with pytest.raises(ValueError):assess(xml,'a'*40)
    xml=report()
    target=next(t for t in xml if t.get('name')=='test_bounded_kernel_exhaustion_unproven')
    E.SubElement(target,'skipped',message='BLOCKED_UNPROVEN: global exhaustion forbidden')
    r=assess(xml,'a'*40)
    assert r['unproven_cases']==1 and r['tested_cases']==16
    assert not r['execution_authorized'] and not r['physical_ready']

def test_report_rejects_passing_case_without_specific_observation():
    import xml.etree.ElementTree as E
    from installer.tests.verify_ownership_adversarial import assess,EXPECTED
    root=E.Element('testsuite')
    for name in sorted(EXPECTED):E.SubElement(root,'testcase',name=name)
    with pytest.raises(ValueError):assess(root,'a'*40)
