"""SYNTHETIC_ONLY in-process lifetime model. Never authorizes Grid ownership.

Callbacks/providers are trusted test code, not a sandbox. No target path API.
Native use is restricted to the separate disposable hosted-CI fixture factory.
"""
from dataclasses import dataclass, replace
import threading
from types import MappingProxyType


class PrototypeBlocked(RuntimeError):
    pass


_REPORT_CODES=frozenset(('ACL_FOREIGN_WRITER', 'ACL_INVALID', 'ACL_NONCANONICAL', 'ACL_UNSUPPORTED', 'API_UNAVAILABLE', 'BYTES_CHANGED', 'FACTORY_ONLY', 'FIXTURE_MUTATION_UNSUPPORTED', 'FIXTURE_NAME_INVALID', 'HANDLE_CLOSED', 'HANDLE_CLOSED_OR_DIRECTORY', 'IDENTITY_CHANGED', 'IDENTITY_UNAVAILABLE', 'LINK_COUNT_INVALID', 'MUTEX_SCOPE', 'NATIVE_ABI_UNSUPPORTED', 'NATIVE_ACE_UNSUPPORTED', 'NATIVE_ACL_UNSUPPORTED', 'NATIVE_API_FAILED', 'NATIVE_DIRECTORY_API_FAILED', 'NATIVE_DIRECTORY_DATA_INVALID', 'NATIVE_FILE_TOO_LARGE', 'NATIVE_FIXTURE_POLICY_BLOCKED', 'NATIVE_FIXTURE_TEMP_INVALID', 'NATIVE_FREE_FAILED', 'NATIVE_INHERITED_ACL', 'NATIVE_MUTEX_BUSY_OR_ABANDONED', 'NATIVE_MUTEX_FAILED', 'NATIVE_NULL_DACL', 'NATIVE_OPEN_FAILED', 'NATIVE_SECURITY_INFO_FAILED', 'NATIVE_TOKEN_UNSUPPORTED', 'NATIVE_TREE_LIMIT', 'NATIVE_VOLUME_MISMATCH', 'PATH_MISSING', 'PATH_REPLACED', 'READ_NOT_ALLOWED', 'READ_REENTRY', 'REPARSE_OR_TYPE_CHANGED', 'SESSION_INVALIDATED', 'SESSION_POISONED', 'STATE_CHANGED', 'TREE_CHANGED', 'UNSAFE_OPEN_FLAGS', 'VIEW_CLOSED', 'VIEW_EXPIRED', 'VIEW_THREAD_CHANGED'))

OWNER='S-1-5-21-100-200-300-1001'
WRITE_MASK=2|4|16|64|256|65536|262144|524288|0x40000000|0x10000000
KNOWN_RIGHTS=0xF01F01FF
FLAGS=0x02000000|0x00200000
OPEN_ARGS=dict(access=0x80000000,share=1,creation=3,flags=FLAGS)
JOURNAL=(b'{"schema":1,"plan_sha256":"'+b'a'*64+b'","state":"PREPARED"}\n'+
         b'{"schema":1,"plan_sha256":"'+b'a'*64+b'","state":"COMMITTED"}\n')
DIRECTORIES=('', 'data','data/wal','postgres','postgres/data','releases')
FILES=MappingProxyType({'deployment-plan.json':b'{"kind":"SYNTHETIC_ONLY"}',
                       'tasks.plan.json':b'{"enabled":false}',
                       'isolated.env.template':b'# SYNTHETIC_ONLY, NOT ACTIVE\n',
                       'postgresql.conf.template':b'# SYNTHETIC_ONLY, NO DATABASE\n',
                       'owner.jsonl':JOURNAL})


@dataclass(frozen=True)
class ACL:
    owner: str
    protected: bool
    # ACE type, flags, unsigned access mask, SID. No effective-access assumptions.
    aces: tuple


@dataclass(frozen=True)
class State:
    volume: int
    identity: int
    attributes: int
    links: int
    size: int
    acl: ACL
    stamp: int=0


@dataclass(eq=False)
class Handle:
    name: str
    node: object
    closed: bool=False


class ModelFixture:
    """In-memory object/handle model; forced mutations simulate hostile races."""
    backend='MODEL'

    def __init__(self):
        self.expected=MappingProxyType({**{n:None for n in DIRECTORIES},**FILES})
        acl=ACL(OWNER,True,((0,0,0x1F01FF,OWNER),))
        self.owner=OWNER
        self.nodes={n:{'state':State(1,i+1,16 if b is None else 128,1,
                                   0 if b is None else len(b),acl),'bytes':b}
                    for i,(n,b) in enumerate(self.expected.items())}
        self.identities={n:(v['state'].volume,v['state'].identity) for n,v in self.nodes.items()}
        self.guard=threading.Lock();self.poisoned=False;self.current_lifetime=None
        self.live=[];self.pinned=[];self.locks=[];self.opened=0;self.closed=0
        self.failure=None;self.open_requests=[]

    def fail(self,operation):
        if self.failure in (operation,'unsupported'):
            raise PrototypeBlocked('API_UNAVAILABLE')

    def acquire(self,name):
        self.fail('mutex');self.locks.append(name)

    def release(self,name):
        if not self.locks or self.locks[-1]!=name:raise PrototypeBlocked('MUTEX_SCOPE')
        self.locks.pop()

    def open(self,name,**options):
        self.fail('open')
        if options!=OPEN_ARGS:raise PrototypeBlocked('UNSAFE_OPEN_FLAGS')
        self.open_requests.append(dict(options))
        if name not in self.nodes:raise PrototypeBlocked('PATH_MISSING')
        h=Handle(name,self.nodes[name]);self.live.append(h);self.opened+=1;return h

    def state(self,h):
        self.fail('state')
        if h.closed:raise PrototypeBlocked('HANDLE_CLOSED')
        return h.node['state']

    def read(self,h):
        self.fail('read')
        if h.closed or h.node['bytes'] is None:raise PrototypeBlocked('HANDLE_CLOSED_OR_DIRECTORY')
        return h.node['bytes']

    def tree(self):
        self.fail('enumerate');return set(self.nodes)

    def close(self,h):
        if h.closed:return
        h.closed=True;self.live.remove(h);self.closed+=1
        # Conservatively model an uncertain API return without leaking a test handle.
        self.fail('close')

    def inject(self,what,name):
        node=self.nodes[name];s=node['state']
        if what=='replace':self.nodes[name]={'state':replace(s,identity=s.identity+100),'bytes':node['bytes']}
        elif what=='reparse':node['state']=replace(s,attributes=s.attributes|1024)
        elif what=='hardlink':node['state']=replace(s,links=2)
        elif what=='acl':node['state']=replace(s,acl=replace(s.acl,protected=False))
        elif what=='closed':self.close(self.pinned[-1])
        elif what=='extra':self.nodes['postgres/data/foreign']=dict(node)
        else:
            content={'prepared':JOURNAL.splitlines(keepends=True)[0],
                     'retired':JOURNAL+b'RETIRED\n','duplicate':JOURNAL+JOURNAL,
                     'torn':JOURNAL[:-5],'foreign':JOURNAL.replace(b'a'*64,b'f'*64)}.get(what,b'changed')
            node['bytes']=content;node['state']=replace(s,size=len(content),stamp=s.stamp+1)


def valid_state(p,name,s):
    if not isinstance(s,State) or not s.volume or not s.identity:raise PrototypeBlocked('IDENTITY_UNAVAILABLE')
    if (s.volume,s.identity)!=p.identities[name]:raise PrototypeBlocked('IDENTITY_CHANGED')
    if s.attributes&1024 or bool(s.attributes&16)!=(p.expected[name] is None):raise PrototypeBlocked('REPARSE_OR_TYPE_CHANGED')
    if s.links!=1:raise PrototypeBlocked('LINK_COUNT_INVALID')
    a=s.acl
    if not isinstance(a,ACL) or a.owner!=p.owner or a.protected is not True:raise PrototypeBlocked('ACL_INVALID')
    allowed_seen=False
    for kind,flags,mask,sid in a.aces:
        if kind==1 and allowed_seen:raise PrototypeBlocked('ACL_NONCANONICAL')
        allowed_seen=allowed_seen or kind==0
        if kind not in (0,1) or flags!=0 or mask<0 or mask&~KNOWN_RIGHTS:raise PrototypeBlocked('ACL_UNSUPPORTED')
        if kind==0 and mask&WRITE_MASK and sid not in (p.owner,'S-1-5-18','S-1-5-32-544'):
            raise PrototypeBlocked('ACL_FOREIGN_WRITER')


class _Lifetime:
    def __init__(self):self.active=True;self.poisoned=False


class _BorrowedView:
    def __init__(self,provider,verify,hook,lifetime):
        self._p=provider;self._verify=verify;self._hook=hook;self._lifetime=lifetime
        self._active=True;self._reading=threading.Lock();self._thread=threading.get_ident()

    def read(self,name):
        if not self._active or not self._lifetime.active:raise PrototypeBlocked('VIEW_EXPIRED')
        if threading.get_ident()!=self._thread:
            self._lifetime.poisoned=True;raise PrototypeBlocked('VIEW_THREAD_CHANGED')
        if self._lifetime.poisoned or self._p.poisoned:raise PrototypeBlocked('VIEW_EXPIRED')
        if not self._reading.acquire(False):
            self._lifetime.poisoned=True;raise PrototypeBlocked('READ_REENTRY')
        try:
            if name not in FILES:raise PrototypeBlocked('READ_NOT_ALLOWED')
            self._verify();self._hook('before_read',self._p,name)
            h=next(h for h in self._p.pinned if h.name==name)
            data=self._p.read(h)
            self._hook('after_read',self._p,name);self._verify()
            if data!=self._p.expected[name]:raise PrototypeBlocked('BYTES_CHANGED')
            return data
        except Exception:
            self._lifetime.poisoned=True;raise
        finally:self._reading.release()

    def close(self):
        if self._lifetime.active:
            self._active=False;self._lifetime.poisoned=True


def run_session(provider,consumer,*,hook=None):
    """Discard callback output; invalidate borrowed views BEFORE releasing resources."""
    p=provider
    r={'schema':1,'status':'BLOCKED','assurance':'SYNTHETIC_ONLY',
       'synthetic_result':'BLOCKED','execution_authorized':False,'physical_ready':False,
       'code':'SESSION_BLOCKED','resources_released':False,'backend':p.backend}
    if not p.guard.acquire(False):
        current=p.current_lifetime
        if current is not None:current.poisoned=True
        r['code']='SESSION_REENTRY';return r
    if p.live or p.locks:
        p.poisoned=True;r['code']='SESSION_PREEXISTING_RESOURCES'
        p.guard.release();return r
    lifetime=_Lifetime();p.current_lifetime=lifetime
    locks=[];held=[];view=None;ok=False;cleanup_ok=True;close_failed=[False]
    def close(h):
        try:p.close(h)
        except Exception:
            close_failed[0]=True;raise
    fire=hook or (lambda *_:None)
    try:
        if p.poisoned:raise PrototypeBlocked('SESSION_POISONED')
        for name in ('release','preparation'):
            p.acquire(name);locks.append(name)
        p.pinned=held
        baseline={}
        for name in p.expected:
            h=p.open(name,**OPEN_ARGS);held.append(h)
            s=p.state(h);valid_state(p,name,s);baseline[name]=s
            fire('after_open',p,name)
        def verify():
            if lifetime.poisoned or p.poisoned or p.locks!=['release','preparation']:raise PrototypeBlocked('SESSION_INVALIDATED')
            if p.tree()!=set(p.expected):raise PrototypeBlocked('TREE_CHANGED')
            for h in held:
                s=p.state(h);valid_state(p,h.name,s)
                if s!=baseline[h.name]:raise PrototypeBlocked('STATE_CHANGED')
                probe=p.open(h.name,**OPEN_ARGS)
                try:
                    if p.state(probe)!=s:raise PrototypeBlocked('PATH_REPLACED')
                finally:close(probe)
                wanted=p.expected[h.name]
                if wanted is not None and p.read(h)!=wanted:raise PrototypeBlocked('BYTES_CHANGED')
        verify();fire('after_verify',p,None)
        fire('before_consumer',p,None);verify()
        view=_BorrowedView(p,verify,fire,lifetime)
        consumer(view)
        fire('after_consumer',p,None);verify()
        if not view._active:raise PrototypeBlocked('VIEW_CLOSED')
        ok=True
    except BaseException as exc:
        p.poisoned=True
        if not isinstance(exc,Exception):raise
        r['code']=str(exc) if isinstance(exc,PrototypeBlocked) and str(exc) in _REPORT_CODES else 'SESSION_FAILED'
    finally:
        lifetime.active=False
        if view is not None:view._active=False
        for h in reversed(held):
            try:close(h)
            except Exception:cleanup_ok=False;p.poisoned=True
        # A failed probe close is also owned by this session, not just its pins.
        # Retry/drain only this provider registry once; uncertainty never becomes PASS.
        for h in list(reversed(p.live)):
            try:close(h)
            except Exception:cleanup_ok=False;p.poisoned=True
        for name in reversed(locks):
            try:p.release(name)
            except Exception:
                cleanup_ok=False;p.poisoned=True;break
        for name in list(reversed(p.locks)):
            try:p.release(name)
            except Exception:
                cleanup_ok=False;p.poisoned=True;break
        cleanup_ok=cleanup_ok and not close_failed[0] and not getattr(p,'cleanup_uncertain',False)
        p.pinned=[]
        r['resources_released']=cleanup_ok and not p.live and not p.locks
        if ok and r['resources_released']:r.update(synthetic_result='PASS',code='SYNTHETIC_LIFETIME_ONLY')
        if not cleanup_ok:r['code']='CLEANUP_UNCERTAIN'
        p.current_lifetime=None
        p.guard.release()
    return r
