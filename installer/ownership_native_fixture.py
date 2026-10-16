"""Opt-in hosted Windows CI fixture backend; no caller-supplied target path.

Import is inert. There is no general native ownership API or production executor.
Only new GUID fixtures may be created; no existing resource is adopted or cleaned.
"""
import ctypes as C
from ctypes import wintypes as W
import os
import struct
from pathlib import Path
import tempfile
import uuid

from installer.ownership_session import (ACL, State, Handle, ModelFixture,
                                         OPEN_ARGS, JOURNAL, PrototypeBlocked)


def fixture_policy():
    expected={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted',
              'RUNNER_OS':'Windows','CI':'true',
              'GITHUB_REPOSITORY':'YehorBabenko88/bybit-cluster-grid',
              'GRID_OWNERSHIP_NATIVE_FIXTURES':'1'}
    if os.name!='nt' or any(os.environ.get(k)!=v for k,v in expected.items()):
        raise PrototypeBlocked('NATIVE_FIXTURE_POLICY_BLOCKED')
    parent=os.environ.get('RUNNER_TEMP','')
    if not parent or parent.startswith(('\\\\','//')) or not Path(parent).is_absolute():
        raise PrototypeBlocked('NATIVE_FIXTURE_TEMP_INVALID')
    return Path(parent)


def _directory_names(raw):
    # FILE_ID_BOTH_DIR_INFO: FileNameLength@60, UTF16 name@104, next@0.
    # Parse bounded copied bytes, never dereference an untrusted native offset.
    offset=0;names=[]
    try:
        while True:
            if offset+104>len(raw):raise ValueError()
            nxt=struct.unpack_from('<I',raw,offset)[0]
            length=struct.unpack_from('<I',raw,offset+60)[0]
            end=offset+104+length
            if not length or length%2 or length>520 or end>len(raw):raise ValueError()
            name=raw[offset+104:end].decode('utf-16-le',errors='strict')
            if any(c in name for c in ('\\','/','\x00')) or name in names:raise ValueError()
            names.append(name)
            if len(names)>32:raise ValueError()
            if not nxt:break
            if nxt%8 or nxt<104+length:raise ValueError()
            offset+=nxt
        return names
    except (ValueError,UnicodeError,struct.error):
        raise PrototypeBlocked('NATIVE_DIRECTORY_DATA_INVALID') from None


class _Info(C.Structure):
    _fields_=[(n,W.DWORD) for n in ('attrs','creation_lo','creation_hi','access_lo','access_hi',
                                   'write_lo','write_hi','volume','size_hi','size_lo','links','index_hi','index_lo')]


class _AclSize(C.Structure):
    _fields_=[('count',W.DWORD),('used',W.DWORD),('free',W.DWORD)]


class _Native:
    def __init__(self):
        fixture_policy()  # Before loading ANY native API.
        self.uncertain=False
        self.k=C.WinDLL('kernel32.dll',use_last_error=True,winmode=0x800)
        self.a=C.WinDLL('advapi32.dll',use_last_error=True,winmode=0x800)
        P=C.c_void_p;D=W.DWORD;H=W.HANDLE;B=W.BOOL;S=W.LPCWSTR
        self._bind(self.k,'CreateFileW',[S,D,D,P,D,D,H],H)
        self._bind(self.k,'CloseHandle',[H],B)
        self._bind(self.k,'GetFileInformationByHandle',[H,C.POINTER(_Info)],B)
        self._bind(self.k,'GetFileInformationByHandleEx',[H,D,P,D],B)
        self._bind(self.k,'SetFilePointerEx',[H,C.c_longlong,P,D],B)
        self._bind(self.k,'ReadFile',[H,P,D,C.POINTER(D),P],B)
        self._bind(self.k,'GetCurrentProcess',[],H)
        self._bind(self.k,'CreateMutexW',[P,B,S],H)
        self._bind(self.k,'WaitForSingleObject',[H,D],D)
        self._bind(self.k,'ReleaseMutex',[H],B)
        self._bind(self.k,'LocalFree',[P],P)
        self._bind(self.a,'OpenProcessToken',[H,D,C.POINTER(H)],B)
        self._bind(self.a,'GetTokenInformation',[H,D,P,D,C.POINTER(D)],B)
        self._bind(self.a,'ConvertSidToStringSidW',[P,C.POINTER(P)],B)
        self._bind(self.a,'ConvertStringSecurityDescriptorToSecurityDescriptorW',[S,D,C.POINTER(P),C.POINTER(D)],B)
        self._bind(self.a,'SetFileSecurityW',[S,D,P],B)
        self._bind(self.a,'GetSecurityInfo',[H,D,D,C.POINTER(P),C.POINTER(P),C.POINTER(P),C.POINTER(P),C.POINTER(P)],D)
        self._bind(self.a,'GetSecurityDescriptorControl',[P,C.POINTER(W.WORD),C.POINTER(D)],B)
        self._bind(self.a,'GetAclInformation',[P,P,D,D],B)
        self._bind(self.a,'GetAce',[P,D,C.POINTER(P)],B)
        if C.sizeof(_Info)!=52:raise PrototypeBlocked('NATIVE_ABI_UNSUPPORTED')
        self.owner=self._token_owner()

    @staticmethod
    def _bind(lib,name,args,result):
        fn=getattr(lib,name);fn.argtypes=args;fn.restype=result

    @staticmethod
    def check(ok):
        if not ok:raise PrototypeBlocked('NATIVE_API_FAILED')

    def free(self,p):
        if p and self.k.LocalFree(p):
            self.uncertain=True;raise PrototypeBlocked('NATIVE_FREE_FAILED')

    def sid(self,p):
        if not p:raise PrototypeBlocked('NATIVE_SECURITY_INFO_FAILED')
        text=C.c_void_p()
        self.check(self.a.ConvertSidToStringSidW(p,C.byref(text)))
        try:return C.wstring_at(text)
        finally:self.free(text)

    def _token_owner(self):
        token=W.HANDLE();needed=W.DWORD()
        self.check(self.a.OpenProcessToken(self.k.GetCurrentProcess(),8,C.byref(token)))
        try:
            # TokenOwner=4. The elevated token default owner may be Administrators.
            self.a.GetTokenInformation(token,4,None,0,C.byref(needed))
            if C.get_last_error()!=122 or not 0<needed.value<=8192:raise PrototypeBlocked('NATIVE_TOKEN_UNSUPPORTED')
            buf=C.create_string_buffer(needed.value)
            self.check(self.a.GetTokenInformation(token,4,buf,len(buf),C.byref(needed)))
            return self.sid(C.c_void_p.from_buffer(buf))
        finally:self.close(token)

    def protect(self,path,*,unsafe=False):
        # Only called on freshly factory-created fixture objects, never an input path.
        sd=C.c_void_p()
        dacl='D:' if unsafe else 'D:P'
        sddl=dacl+'(A;;FA;;;'+self.owner+')(A;;FA;;;SY)(A;;FA;;;BA)'
        self.check(self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl,1,C.byref(sd),None))
        try:
            flags=0x20000004 if unsafe else 0x80000004  # unprotect/protect DACL
            self.check(self.a.SetFileSecurityW(str(path),flags,sd))
        finally:self.free(sd)

    def acl(self,h):
        owner=C.c_void_p();dacl=C.c_void_p();sd=C.c_void_p()
        error=self.a.GetSecurityInfo(h,1,5,C.byref(owner),None,C.byref(dacl),None,C.byref(sd))
        if error:raise PrototypeBlocked('NATIVE_SECURITY_INFO_FAILED')
        try:
            if not owner or not sd or not dacl:raise PrototypeBlocked('NATIVE_NULL_DACL')
            control=W.WORD();revision=W.DWORD()
            self.check(self.a.GetSecurityDescriptorControl(sd,C.byref(control),C.byref(revision)))
            if control.value&0x500:raise PrototypeBlocked('NATIVE_INHERITED_ACL')
            size=_AclSize();self.check(self.a.GetAclInformation(dacl,C.byref(size),C.sizeof(size),2))
            if size.count>32:raise PrototypeBlocked('NATIVE_ACL_UNSUPPORTED')
            aces=[]
            for i in range(size.count):
                ptr=C.c_void_p();self.check(self.a.GetAce(dacl,i,C.byref(ptr)))
                if not ptr:raise PrototypeBlocked('NATIVE_ACE_UNSUPPORTED')
                base=ptr.value;kind=C.c_ubyte.from_address(base).value
                flags=C.c_ubyte.from_address(base+1).value
                length=C.c_ushort.from_address(base+2).value
                if kind not in (0,1) or length<16:raise PrototypeBlocked('NATIVE_ACE_UNSUPPORTED')
                mask=C.c_uint32.from_address(base+4).value
                aces.append((kind,flags,mask,self.sid(base+8)))
            return ACL(self.sid(owner),bool(control.value&0x1000),tuple(aces))
        finally:self.free(sd)

    def open(self,path,options):
        if options!=OPEN_ARGS:raise PrototypeBlocked('UNSAFE_OPEN_FLAGS')
        h=self.k.CreateFileW(str(path),options['access'],options['share'],None,
                             options['creation'],options['flags'],None)
        if h in (None,0,C.c_void_p(-1).value):raise PrototypeBlocked('NATIVE_OPEN_FAILED')
        return h

    def close(self,h):
        if not self.k.CloseHandle(h):
            self.uncertain=True;raise PrototypeBlocked('NATIVE_API_FAILED')

    def state(self,h):
        info=_Info();self.check(self.k.GetFileInformationByHandle(h,C.byref(info)))
        return State(info.volume,(info.index_hi<<32)|info.index_lo,info.attrs,info.links,
                     (info.size_hi<<32)|info.size_lo,self.acl(h),(info.write_hi<<32)|info.write_lo)

    def read(self,h):
        state=self.state(h)
        if state.size>65536:raise PrototypeBlocked('NATIVE_FILE_TOO_LARGE')
        self.check(self.k.SetFilePointerEx(h,0,None,0))
        buf=C.create_string_buffer(state.size+1);read=W.DWORD()
        self.check(self.k.ReadFile(h,buf,len(buf),C.byref(read),None))
        return buf.raw[:read.value]

    def names(self,h):
        names=[]
        for page in range(32):
            buf=C.create_string_buffer(16384)
            ok=self.k.GetFileInformationByHandleEx(h,11 if page==0 else 10,buf,len(buf))
            if not ok:
                if C.get_last_error()==18:return names  # ERROR_NO_MORE_FILES only.
                raise PrototypeBlocked('NATIVE_DIRECTORY_API_FAILED')
            for name in _directory_names(buf.raw):
                if name in ('.','..'):continue
                if name in names or len(names)>=32:raise PrototypeBlocked('NATIVE_TREE_LIMIT')
                names.append(name)
        raise PrototypeBlocked('NATIVE_TREE_LIMIT')

    def mutex(self,name):
        h=self.k.CreateMutexW(None,False,name)
        if not h:raise PrototypeBlocked('NATIVE_MUTEX_FAILED')
        wait=self.k.WaitForSingleObject(h,0)
        if wait!=0:
            try:
                # WAIT_ABANDONED grants ownership: release it even though proof blocks.
                if wait==0x80 and not self.k.ReleaseMutex(h):
                    self.uncertain=True;raise PrototypeBlocked('NATIVE_API_FAILED')
            finally:self.close(h)
            raise PrototypeBlocked('NATIVE_MUTEX_BUSY_OR_ABANDONED')
        return h


_TOKEN=object()


class _WindowsFixture(ModelFixture):
    backend='NATIVE_GUID_FIXTURE'

    def __init__(self,root,native,token):
        if token is not _TOKEN:raise PrototypeBlocked('FACTORY_ONLY')
        super().__init__();self._root=root;self._native=native;self.owner=native.owner
        self._mutex_prefix='Local\\GridOwnershipPrototype_'+uuid.uuid4().hex+'_'
        self._mutex_handles={}
        self.identities={}
        for name in self.expected:
            h=self.open(name,**OPEN_ARGS)
            try:
                s=self.state(h);self.identities[name]=(s.volume,s.identity)
            finally:self.close(h)
        if len({i[0] for i in self.identities.values()})!=1:raise PrototypeBlocked('NATIVE_VOLUME_MISMATCH')

    def _path(self,name):
        if name not in self.expected:raise PrototypeBlocked('FIXTURE_NAME_INVALID')
        return self._root.joinpath(*name.split('/')) if name else self._root

    def acquire(self,name):
        h=self._native.mutex(self._mutex_prefix+name)
        self._mutex_handles[name]={'handle':h,'released':False};self.locks.append(name)

    @property
    def cleanup_uncertain(self):
        return self._native.uncertain

    def release(self,name):
        if not self.locks or self.locks[-1]!=name:raise PrototypeBlocked('MUTEX_SCOPE')
        record=self._mutex_handles[name]
        if not record['released']:
            if not self._native.k.ReleaseMutex(record['handle']):
                self._native.uncertain=True
                raise PrototypeBlocked('NATIVE_API_FAILED')
            record['released']=True
        # Retain registry through either failure, so a bounded drain can retry.
        self._native.close(record['handle'])
        del self._mutex_handles[name]
        super().release(name)

    def open(self,name,**options):
        raw=self._native.open(self._path(name),options)
        h=Handle(name,raw);self.live.append(h);self.opened+=1;return h

    def state(self,h):
        if h.closed:raise PrototypeBlocked('HANDLE_CLOSED')
        return self._native.state(h.node)

    def read(self,h):
        if h.closed:raise PrototypeBlocked('HANDLE_CLOSED')
        return self._native.read(h.node)

    def close(self,h):
        if h.closed:return
        self._native.close(h.node);h.closed=True;self.live.remove(h);self.closed+=1

    def tree(self):
        found={''}
        # Enumerate the SAME retained directory handles, never path-based scandir.
        for h in self.pinned:
            if self.expected[h.name] is not None:continue
            if h.closed:raise PrototypeBlocked('HANDLE_CLOSED')
            for name in self._native.names(h.node):
                found.add((h.name+'/' if h.name else '')+name)
                if len(found)>32:raise PrototypeBlocked('NATIVE_TREE_LIMIT')
        return found

    def inject(self,what,name):
        path=self._path(name)
        if what=='acl':self._native.protect(path,unsafe=True)
        elif what=='bytes':
            with path.open('wb') as f:f.write(b'changed')
        elif what=='replace' and self.pinned:
            os.rename(path,self._root/('renamed-'+uuid.uuid4().hex))
        elif what=='replace':
            replacement=self._root/('replacement-'+uuid.uuid4().hex)
            with replacement.open('xb') as f:f.write(self.expected[name])
            os.replace(replacement,path)
        elif what=='hardlink':os.link(path,self._root/('link-'+uuid.uuid4().hex))
        elif what in ('prepared','retired','duplicate','torn','foreign') and name=='owner.jsonl':
            data={'prepared':JOURNAL.splitlines(keepends=True)[0],
                  'retired':JOURNAL+b'RETIRED\n','duplicate':JOURNAL+JOURNAL,
                  'torn':JOURNAL[:-5],'foreign':JOURNAL.replace(b'a'*64,b'f'*64)}[what]
            with path.open('wb') as f:f.write(data)
        elif what=='extra':
            with (self._root/'foreign').open('xb') as f:f.write(b'extra')
        else:raise PrototypeBlocked('FIXTURE_MUTATION_UNSUPPORTED')


def new_native_fixture():
    """No path argument. Never reuses/adopts/deletes a directory or existing file."""
    parent=fixture_policy();native=_Native()
    root=Path(tempfile.mkdtemp(prefix='grid-ownership-prototype-'+uuid.uuid4().hex+'-',dir=parent))
    native.protect(root)
    # Factory owns this newly created GUID tree only. No recursive cleanup exists.
    template=ModelFixture()
    for name,content in template.expected.items():
        if not name:continue
        path=root.joinpath(*name.split('/'))
        if content is None:path.mkdir()
        else:
            with path.open('xb') as f:f.write(content)
        native.protect(path)
    return _WindowsFixture(root,native,_TOKEN)
