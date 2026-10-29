"""Explicit, fail-closed Win32 custody. Importing this module performs no OS calls.

Trust boundary: the operator and Windows administrators, not a hostile OS/admin.
No existing security descriptor is ever modified.
"""
import ctypes
import ntpath
import struct
import sys
from dataclasses import dataclass

SYSTEM = 'S-1-5-18'
ADMINS = 'S-1-5-32-544'
TRUSTED_INSTALLER_OWNER = 'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464'
FULL = 0x1F01FF
DANGEROUS = 0x40 | 0x10000 | 0x40000 | 0x80000 | 0x10000000 | 0x40000000


class WindowsBlocked(RuntimeError):
    def __init__(self, code='WINDOWS_CUSTODY_BLOCKED'):
        self.code = code
        super().__init__(code)

def diagnostic_observation(path,info):
    """Lossless JSON diagnostic only; never an ACL acceptance decision."""
    if type(path) is not str or type(info) is not dict or type(info.get('acl')) is not bytes:
        raise WindowsBlocked()
    return dict(path=path,**{k:v for k,v in info.items() if k!='acl'},acl_hex=info['acl'].hex())


def decode_sid(data):
    if len(data) < 8 or data[0] != 1 or data[1] > 15 or len(data) != 8 + data[1]*4:
        raise WindowsBlocked()
    return 'S-1-' + str(int.from_bytes(data[2:8], 'big')) + ''.join(
        '-' + str(struct.unpack_from('<I', data, 8+4*i)[0]) for i in range(data[1]))


def encode_sid(value):
    try:
        parts = value.split('-')
        if parts[:2] != ['S', '1']: raise ValueError()
        authority = int(parts[2]); rids = [int(x) for x in parts[3:]]
        if len(rids) > 15: raise ValueError()
        return bytes([1, len(rids)]) + authority.to_bytes(6, 'big') + b''.join(struct.pack('<I', x) for x in rids)
    except (ValueError, OverflowError, struct.error):
        raise WindowsBlocked() from None


def validate_sd_regions(raw,owner_offset,dacl_offset):
    """Validate allocation-relative regions before any native pointer dereference."""
    if not isinstance(raw,bytes) or not 20<=len(raw)<=65536 or raw[0]!=1: raise WindowsBlocked()
    control=struct.unpack_from('<H',raw,2)[0]
    if not control & 4: raise WindowsBlocked()
    for offset in (owner_offset,dacl_offset):
        if type(offset) is not int or offset<20 or offset%4 or offset+8>len(raw): raise WindowsBlocked()
    owner_size=8+4*raw[owner_offset+1]
    if raw[owner_offset]!=1 or raw[owner_offset+1]>15 or owner_offset+owner_size>len(raw): raise WindowsBlocked()
    acl_size=struct.unpack_from('<H',raw,dacl_offset+2)[0]
    if acl_size<8 or dacl_offset+acl_size>len(raw): raise WindowsBlocked()
    if max(owner_offset,dacl_offset)<min(owner_offset+owner_size,dacl_offset+acl_size): raise WindowsBlocked()
    return raw[owner_offset:owner_offset+owner_size],raw[dacl_offset:dacl_offset+acl_size],control


def _aces(data):
    if len(data) < 8 or len(data) > 65536: raise WindowsBlocked()
    revision, reserved1, size, count, reserved2 = struct.unpack_from('<BBHHH', data)
    if revision not in (2, 4) or reserved1 or reserved2 or size != len(data) or count > 4096: raise WindowsBlocked()
    offset = 8; result = []
    for _ in range(count):
        if offset+8 > size: raise WindowsBlocked()
        kind, flags, length, mask = struct.unpack_from('<BBHI', data, offset)
        if kind not in (0, 1) or flags & ~0x1F or length < 16 or offset+length > size: raise WindowsBlocked()
        who = decode_sid(data[offset+8:offset+length])
        result.append((kind, flags, mask, who)); offset += length
    if offset != size: raise WindowsBlocked()
    return result


def validate_acl(data, trusted, *, root=False, file=False):
    aces = _aces(data)
    if root:
        if len(aces) != 3 or {x[3] for x in aces} != set(trusted): raise WindowsBlocked()
        if any(kind != 0 or flags != 0 or mask != FULL for kind, flags, mask, _ in aces): raise WindowsBlocked()
    for kind, flags, mask, who in aces:
        dangerous=DANGEROUS | (0x2 | 0x4 | 0x10 | 0x100 if file else 0)
        if kind == 0 and not flags & 8 and who not in trusted and mask & dangerous:
            raise WindowsBlocked()


def root_acl(operator_sid):
    aces = []
    for who in (SYSTEM, ADMINS, operator_sid):
        body = struct.pack('<I', FULL) + encode_sid(who)
        aces.append(struct.pack('<BBH', 0, 0, len(body)+4)+body)
    body = b''.join(aces)
    return struct.pack('<BBHHH', 2, 0, len(body)+8, 3, 0)+body


def admin_group_enabled(groups):
    return any(sid == ADMINS and attrs & 4 and not attrs & 16 for sid, attrs in groups)


@dataclass(frozen=True)
class Identity:
    sid: str
    pid: int
    creation_filetime: int
    elevated: bool
    integrity: str
    admin_enabled: bool
    image_path: str
    enabled_privileges: tuple[str, ...] | None = None


def decode_privileges(data, lookup):
    """Decode TOKEN_PRIVILEGES: DWORD count, then 12-byte LUID/attribute rows."""
    if len(data)<4 or len(data)>65536: raise WindowsBlocked()
    count=struct.unpack_from('<I',data)[0]
    if count>4096 or len(data)!=4+12*count: raise WindowsBlocked()
    enabled=[]
    for index in range(count):
        low,high,attributes=struct.unpack_from('<IiI',data,4+12*index)
        if attributes & ~0x80000007 or attributes & 4 and attributes & 2: raise WindowsBlocked()
        if attributes & 2:
            try: name=lookup(low,high)
            except Exception: raise WindowsBlocked() from None
            if (type(name) is not str or not 1<=len(name)<=256 or not name.isascii()
                    or not name.startswith('Se') or not name.endswith('Privilege') or not name.isalnum()):
                raise WindowsBlocked()
            enabled.append(name)
    return tuple(enabled)


def require_operator(identity):
    elevated=getattr(identity,'elevated',None)
    admin_enabled=getattr(identity,'admin_enabled',None)
    privileges=getattr(identity,'enabled_privileges',None)
    if (type(elevated) is not bool or elevated or
            type(admin_enabled) is not bool or admin_enabled or
            getattr(identity,'integrity',None) != 'S-1-16-8192' or
            type(privileges) is not tuple or
            any(type(name) is not str or name != 'SeChangeNotifyPrivilege'
                for name in privileges)):
        raise WindowsBlocked('OPERATOR_TOKEN_BLOCKED')


def current_identity(*, api=None):
    return (api or Win32()).current_identity()


def decode_tcp_listeners(raw,family,port):
    """Return whether port is absent in one bounded OWNER_PID_LISTENER table."""
    if type(port) is not int or not 1<=port<=65535 or type(family) is not int or family not in (2,23):
        raise WindowsBlocked()
    if not isinstance(raw,(bytes,bytearray)) or not 4<=len(raw)<=1024*1024: raise WindowsBlocked()
    count=struct.unpack_from('<I',raw)[0]
    stride,state_offset,port_offset=(24,0,8) if family==2 else (56,48,20)
    if count>4096 or len(raw)!=4+stride*count: raise WindowsBlocked()
    occupied=False
    for index in range(count):
        offset=4+stride*index
        if struct.unpack_from('<I',raw,offset+state_offset)[0]!=2: raise WindowsBlocked()
        if int.from_bytes(raw[offset+port_offset:offset+port_offset+2],'big')==port: occupied=True
    return not occupied


def port_available(port,*,api=None):
    if type(port) is not int or not 1<=port<=65535: raise WindowsBlocked()
    api=api or Win32()
    ipv4=decode_tcp_listeners(api.tcp_table(2),2,port)
    ipv6=decode_tcp_listeners(api.tcp_table(23),23,port)
    return ipv4 and ipv6


def _absolute(path):
    path = str(path)
    if '/' in path or '\x00' in path or path.startswith('\\\\'):
        raise WindowsBlocked()
    drive, tail = ntpath.splitdrive(path)
    if len(drive) != 2 or not drive[0].isascii() or not drive[0].isalpha() or drive[1] != ':' or not tail.startswith('\\'):
        raise WindowsBlocked()
    parts = tail[1:].split('\\')
    if parts == ['']: return drive+'\\'
    reserved={'CON','PRN','AUX','NUL','CONIN$','CONOUT$'}
    reserved.update('COM'+x for x in '123456789¹²³')
    reserved.update('LPT'+x for x in '123456789¹²³')
    for part in parts:
        if (not part or part in ('.','..') or part[-1] in '. ' or
                any(ord(c)<32 or c in ':<>"|?*' for c in part) or
                part.split('.')[0].upper() in reserved):
            raise WindowsBlocked()
    return ntpath.normpath(path)


class Custody:
    def __init__(self, root, operator_sid, files=(), *, api=None, _strict_root=True, _profile_v1=False):
        self.root = _absolute(root); encode_sid(operator_sid)
        self.operator_sid = operator_sid; self.files = tuple(_absolute(p) for p in files)
        prefix=self.root.rstrip('\\').casefold()+'\\'
        if any(not path.casefold().startswith(prefix) for path in self.files): raise WindowsBlocked()
        self.api = api; self.handles = []; self.identities = []; self.strict_root = _strict_root; self.expectations=[]; self.security=[];self.profile_v1=_profile_v1

    def _pin(self, path, directory, root=False):
        handle = self.api.open(path, directory)
        self.handles.append(handle)
        info = self.api.inspect(handle)
        self._validate(info,directory,root,path)
        self.identities.append(info['identity'])
        self.security.append((info['owner'],info['protected'],info['acl']))
        self.expectations.append((directory,root,path))

    def _validate(self, info, directory, root, path):
        if info['reparse'] or info['directory'] != directory or (not directory and info['links'] != 1): raise WindowsBlocked()
        trusted = {SYSTEM, ADMINS, self.operator_sid}
        if info['owner'] not in trusted:
            # Trusted OS servicing authority only at the actual OS volume anchor.
            # It is never an ACE trustee or a package/data owner exception.
            if info['owner']!=TRUSTED_INSTALLER_OWNER or root or not directory: raise WindowsBlocked()
            try:
                anchor=_absolute(self.api.system_volume_root())
                if anchor!=ntpath.splitdrive(anchor)[0]+'\\' or path.casefold()!=anchor.casefold(): raise WindowsBlocked()
            except Exception: raise WindowsBlocked() from None
        if root and not info['protected']: raise WindowsBlocked()
        validate_acl(info['acl'], trusted, root=root, file=not directory)
        if self.profile_v1:
            for kind,flags,mask,who in _aces(info['acl']):
                if kind==0 and not flags&8 and who not in trusted and mask&(0x10|0x100):raise WindowsBlocked()

    def __enter__(self):
        self.api = self.api or Win32()
        try:
            if self.api.local_volume(ntpath.splitdrive(self.root)[0]+'\\') is not True: raise WindowsBlocked()
            directories = set()
            for path in (self.root,) + self.files:
                parent = path if path == self.root else ntpath.dirname(path)
                while parent:
                    directories.add(parent)
                    previous = parent; parent = ntpath.dirname(parent)
                    if parent == previous: break
            for path in sorted(directories, key=lambda p: (len(p), p)):
                self._pin(path, True, path == self.root and self.strict_root)
            for path in self.files: self._pin(path, False)
            return self
        except BaseException:
            self.__exit__(None, None, None); raise

    def identity(self, handle):
        return self.api.inspect(handle)['identity']

    def guard(self):
        if len(self.handles) != len(self.identities) or len(self.handles) != len(self.expectations) or len(self.handles)!=len(self.security): raise WindowsBlocked()
        for handle, identity, (directory,root,path), security in zip(self.handles, self.identities,self.expectations,self.security):
            info=self.api.inspect(handle)
            if info['identity'] != identity or (info['owner'],info['protected'],info['acl'])!=security: raise WindowsBlocked()
            self._validate(info,directory,root,path)

    def __exit__(self, *args):
        while self.handles: self.api.close(self.handles.pop())
        self.identities.clear()
        self.expectations.clear()
        self.security.clear()


def create_fresh_root(path, operator_sid, *, api=None):
    path = _absolute(path); encode_sid(operator_sid)
    api = api or Win32()
    parent = ntpath.dirname(path)
    # Parent gets ancestor policy, not the fresh root's strict policy.
    with Custody(parent, operator_sid, api=api, _strict_root=False) as custody:
        api.create_directory(path, 'O:'+operator_sid+'D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;'+operator_sid+')')
        custody.guard()


def _protected_sddl(operator_sid):
    encode_sid(operator_sid)
    if operator_sid in (SYSTEM,ADMINS): raise WindowsBlocked()
    return 'O:'+operator_sid+'D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;'+operator_sid+')'


def _validate_mutable(info,operator_sid):
    if info['reparse'] or info['directory'] or info['links']!=1 or not info['protected']:
        raise WindowsBlocked()
    trusted={SYSTEM,ADMINS,operator_sid}
    if info['owner'] not in trusted: raise WindowsBlocked()
    validate_acl(info['acl'],trusted,root=True,file=True)


def create_fresh_file(path,operator_sid,data,*,api=None):
    """Create only a new protected file; never overwrite or alter an existing ACL."""
    if type(data) is not bytes or len(data)>1024*1024: raise WindowsBlocked()
    path=_absolute(path); sddl=_protected_sddl(operator_sid); api=api or Win32()
    with Custody(ntpath.dirname(path),operator_sid,api=api) as parent:
        handle=api.create_file(path,sddl)
        try:
            before=api.inspect(handle); _validate_mutable(before,operator_sid)
            parent.guard()
            api.write(handle,data); api.flush(handle)
            after=api.inspect(handle); _validate_mutable(after,operator_sid)
            if before['identity']!=after['identity']: raise WindowsBlocked()
            parent.guard()
        finally: api.close(handle)


class MutableFile:
    """Pin an existing protected file allowing writers while denying replacement.

    Callers hold parent Custody as well. This lease never truncates or writes.
    """
    def __init__(self,path,operator_sid,*,api=None):
        self.path=_absolute(path); _protected_sddl(operator_sid)
        self.operator_sid=operator_sid; self.api=api; self.handle=None; self.identity=None

    def __enter__(self):
        self.api=self.api or Win32()
        if self.api.local_volume(ntpath.splitdrive(self.path)[0]+'\\') is not True: raise WindowsBlocked()
        self.handle=self._open_handle()
        try:
            info=self.api.inspect(self.handle); _validate_mutable(info,self.operator_sid)
            self.identity=info['identity']; return self
        except BaseException:
            self.__exit__(None,None,None); raise

    def _open_handle(self):
        return self.api.open_mutable(self.path)

    def guard(self):
        if self.handle is None: raise WindowsBlocked()
        info=self.api.inspect(self.handle); _validate_mutable(info,self.operator_sid)
        if info['identity']!=self.identity: raise WindowsBlocked()

    def __exit__(self,*args):
        if self.handle is not None:
            handle=self.handle; self.handle=None; self.api.close(handle)
        self.identity=None


class ExclusiveFile(MutableFile):
    """Read-only exclusive claim lease; sharing failures never get a fallback."""
    def _open_handle(self):
        return self.api.open_exclusive(self.path)


class Win32:
    def __init__(self):
        if sys.platform != 'win32': raise WindowsBlocked('WINDOWS_REQUIRED')
        from ctypes import wintypes as t
        self.t = t
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.a = ctypes.WinDLL('advapi32', use_last_error=True)
        def bind(lib, name, args, result):
            fn = getattr(lib, name); fn.argtypes = args; fn.restype = result; return fn
        self._open = bind(self.k, 'CreateFileW', [t.LPCWSTR,t.DWORD,t.DWORD,t.LPVOID,t.DWORD,t.DWORD,t.HANDLE], t.HANDLE)
        self._close = bind(self.k, 'CloseHandle', [t.HANDLE], t.BOOL)
        self._info = bind(self.k, 'GetFileInformationByHandle', [t.HANDLE,t.LPVOID], t.BOOL)
        self._security = bind(self.a, 'GetSecurityInfo', [t.HANDLE,t.DWORD,t.DWORD,t.LPVOID,t.LPVOID,t.LPVOID,t.LPVOID,t.LPVOID], t.DWORD)
        self._control = bind(self.a, 'GetSecurityDescriptorControl', [t.LPVOID,t.LPVOID,t.LPVOID], t.BOOL)
        self._sd_length = bind(self.a, 'GetSecurityDescriptorLength', [t.LPVOID], t.DWORD)
        self._free = bind(self.k, 'LocalFree', [t.LPVOID], t.LPVOID)

    def open(self, path, directory):
        h = self._open(path, 0x20000 | 0x80000000, 3 if directory else 1, None, 3, 0x00200000 | (0x02000000 if directory else 0), None)
        if h in (None, ctypes.c_void_p(-1).value): raise WindowsBlocked()
        return h

    def close(self, handle):
        if not self._close(handle): raise WindowsBlocked()

    def system_volume_root(self):
        fn=self.k.GetSystemWindowsDirectoryW
        fn.argtypes=[self.t.LPWSTR,self.t.UINT];fn.restype=self.t.UINT
        buffer=ctypes.create_unicode_buffer(32768)
        length=fn(buffer,len(buffer))
        if not 0<length<len(buffer): raise WindowsBlocked()
        path=_absolute(buffer.value)
        return ntpath.splitdrive(path)[0]+'\\'

    def local_volume(self,drive):
        t=self.t
        drive_type=self.k.GetDriveTypeW
        drive_type.argtypes=[t.LPCWSTR]; drive_type.restype=t.UINT
        if drive_type(drive)!=3: raise WindowsBlocked()
        volume=self.k.GetVolumeInformationW
        volume.argtypes=[t.LPCWSTR,t.LPWSTR,t.DWORD,t.LPVOID,t.LPVOID,t.LPVOID,t.LPWSTR,t.DWORD]
        volume.restype=t.BOOL
        fs=ctypes.create_unicode_buffer(32)
        if not volume(drive,None,0,None,None,None,fs,len(fs)) or fs.value!='NTFS': raise WindowsBlocked()
        return True

    def tcp_table(self,family):
        if type(family) is not int or family not in (2,23): raise WindowsBlocked()
        t=self.t
        library=ctypes.WinDLL('iphlpapi',use_last_error=True)
        get_table=library.GetExtendedTcpTable
        get_table.argtypes=[t.LPVOID,t.LPVOID,t.BOOL,t.ULONG,t.DWORD,t.ULONG]
        get_table.restype=t.DWORD
        size=t.DWORD()
        status=get_table(None,ctypes.byref(size),False,family,3,0)
        if status not in (0,122) or not 4<=size.value<=1024*1024: raise WindowsBlocked()
        buffer=ctypes.create_string_buffer(size.value)
        if get_table(buffer,ctypes.byref(size),False,family,3,0)!=0 or not 4<=size.value<=len(buffer):
            raise WindowsBlocked()
        return buffer.raw[:size.value]

    def open_mutable(self,path):
        handle=self._open(path,0x80020000,3,None,3,0x00200000,None)
        if handle in (None,ctypes.c_void_p(-1).value): raise WindowsBlocked()
        return handle

    def open_exclusive(self,path):
        handle=self._open(path,0x80020000,0,None,3,0x00200000,None)
        if handle in (None,ctypes.c_void_p(-1).value): raise WindowsBlocked()
        return handle

    def create_file(self,path,sddl):
        t=self.t
        convert=self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert.argtypes=[t.LPCWSTR,t.DWORD,t.LPVOID,t.LPVOID]; convert.restype=t.BOOL
        class SA(ctypes.Structure):
            _fields_=[('length',t.DWORD),('descriptor',t.LPVOID),('inherit',t.BOOL)]
        descriptor=ctypes.c_void_p()
        if not convert(sddl,1,ctypes.byref(descriptor),None): raise WindowsBlocked()
        try:
            attrs=SA(ctypes.sizeof(SA),descriptor,False)
            handle=self._open(path,0x40020000,0,ctypes.byref(attrs),1,0x00200000,None)
            if handle in (None,ctypes.c_void_p(-1).value): raise WindowsBlocked('FRESH_FILE_BLOCKED')
            return handle
        finally: self._free(descriptor)

    def write(self,handle,data):
        if type(data) is not bytes or len(data)>1024*1024: raise WindowsBlocked()
        t=self.t; write=self.k.WriteFile
        write.argtypes=[t.HANDLE,t.LPVOID,t.DWORD,t.LPVOID,t.LPVOID]; write.restype=t.BOOL
        buffer=ctypes.create_string_buffer(data); written=t.DWORD()
        if not write(handle,buffer,len(data),ctypes.byref(written),None) or written.value!=len(data): raise WindowsBlocked()

    def flush(self,handle):
        flush=self.k.FlushFileBuffers
        flush.argtypes=[self.t.HANDLE]; flush.restype=self.t.BOOL
        if not flush(handle): raise WindowsBlocked()

    def inspect(self, handle):
        class Info(ctypes.Structure):
            _fields_ = [('attrs',ctypes.c_uint32),('times',ctypes.c_uint32*6),('volume',ctypes.c_uint32),('size_hi',ctypes.c_uint32),('size_lo',ctypes.c_uint32),('links',ctypes.c_uint32),('index_hi',ctypes.c_uint32),('index_lo',ctypes.c_uint32)]
        info = Info()
        if not self._info(handle, ctypes.byref(info)): raise WindowsBlocked()
        owner = ctypes.c_void_p(); dacl = ctypes.c_void_p(); sd = ctypes.c_void_p()
        if self._security(handle, 1, 5, ctypes.byref(owner), None, ctypes.byref(dacl), None, ctypes.byref(sd)): raise WindowsBlocked()
        try:
            if not owner.value or not dacl.value or not sd.value: raise WindowsBlocked()
            size=self._sd_length(sd)
            if not 20<=size<=65536: raise WindowsBlocked()
            owner_offset=owner.value-sd.value; dacl_offset=dacl.value-sd.value
            if owner_offset<20 or owner_offset+8>size or dacl_offset<20 or dacl_offset+8>size: raise WindowsBlocked()
            owner_raw,acl_raw,raw_control=validate_sd_regions(ctypes.string_at(sd,size),owner_offset,dacl_offset)
            who=decode_sid(owner_raw)
            control = ctypes.c_ushort(); revision = ctypes.c_uint32()
            if not self._control(sd, ctypes.byref(control), ctypes.byref(revision)): raise WindowsBlocked()
            if revision.value!=1 or control.value!=raw_control or not control.value&4: raise WindowsBlocked()
            return dict(identity=(info.volume,info.index_hi,info.index_lo), directory=bool(info.attrs&16), reparse=bool(info.attrs&0x400), links=info.links, owner=who, acl=acl_raw, protected=bool(control.value&0x1000))
        finally:
            if sd.value: self._free(sd)

    def create_directory(self, path, sddl):
        t = self.t
        convert = self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert.argtypes = [t.LPCWSTR,t.DWORD,t.LPVOID,t.LPVOID]; convert.restype=t.BOOL
        create = self.k.CreateDirectoryW
        create.argtypes=[t.LPCWSTR,t.LPVOID]; create.restype=t.BOOL
        class SA(ctypes.Structure):
            _fields_=[('length',t.DWORD),('descriptor',t.LPVOID),('inherit',t.BOOL)]
        sd=ctypes.c_void_p()
        if not convert(sddl,1,ctypes.byref(sd),None): raise WindowsBlocked()
        try:
            attrs=SA(ctypes.sizeof(SA),sd,False)
            if not create(path,ctypes.byref(attrs)): raise WindowsBlocked('FRESH_ROOT_BLOCKED')
        finally: self._free(sd)

    def current_identity(self):
        # Implemented below using only the current process token.
        return _current_identity(self)


def _current_identity(api):
    t=api.t
    def bind(lib,name,args,result):
        fn=getattr(lib,name); fn.argtypes=args; fn.restype=result; return fn
    get_process=bind(api.k,'GetCurrentProcess',[],t.HANDLE)
    get_pid=bind(api.k,'GetCurrentProcessId',[],t.DWORD)
    open_token=bind(api.a,'OpenProcessToken',[t.HANDLE,t.DWORD,t.LPVOID],t.BOOL)
    get_token=bind(api.a,'GetTokenInformation',[t.HANDLE,t.DWORD,t.LPVOID,t.DWORD,t.LPVOID],t.BOOL)
    get_times=bind(api.k,'GetProcessTimes',[t.HANDLE,t.LPVOID,t.LPVOID,t.LPVOID,t.LPVOID],t.BOOL)
    get_image=bind(api.k,'QueryFullProcessImageNameW',[t.HANDLE,t.DWORD,t.LPWSTR,t.LPVOID],t.BOOL)
    lookup_privilege=bind(api.a,'LookupPrivilegeNameW',[t.LPCWSTR,t.LPVOID,t.LPWSTR,t.LPVOID],t.BOOL)
    token=t.HANDLE(); process=get_process()
    if not open_token(process,8,ctypes.byref(token)): raise WindowsBlocked()
    def read_token(kind):
        needed=t.DWORD()
        get_token(token,kind,None,0,ctypes.byref(needed))
        if not 0 < needed.value <= 65536: raise WindowsBlocked()
        buf=ctypes.create_string_buffer(needed.value)
        if not get_token(token,kind,buf,len(buf),ctypes.byref(needed)): raise WindowsBlocked()
        if needed.value != len(buf): raise WindowsBlocked()
        return buf
    def privilege_name(low,high):
        luid=struct.pack('<Ii',low,high)
        luid_buffer=ctypes.create_string_buffer(luid)
        length=t.DWORD(257); name=ctypes.create_unicode_buffer(257)
        if not lookup_privilege(None,luid_buffer,name,ctypes.byref(length)) or not 0<length.value<=256:
            raise WindowsBlocked()
        return name.value
    def token_sid(buf, offset=0):
        pointer=ctypes.c_void_p.from_buffer(buf,offset).value
        base=ctypes.addressof(buf)
        if pointer is None or pointer < base or pointer+8 > base+len(buf): raise WindowsBlocked()
        header=ctypes.string_at(pointer,8); size=8+4*header[1]
        if pointer+size > base+len(buf): raise WindowsBlocked()
        return decode_sid(ctypes.string_at(pointer,size))
    class Group(ctypes.Structure):
        _fields_=[('sid',t.LPVOID),('attributes',t.DWORD)]
    class Groups(ctypes.Structure):
        _fields_=[('count',t.DWORD),('groups',Group*1)]
    try:
        user=read_token(1); sid=token_sid(user)
        elevation=read_token(20)
        if len(elevation)<4: raise WindowsBlocked()
        elevated=bool(struct.unpack_from('<I',elevation)[0])
        integrity=token_sid(read_token(25))
        privileges=read_token(3)
        enabled_privileges=decode_privileges(privileges.raw,privilege_name)
        groups=read_token(2); count=struct.unpack_from('<I',groups)[0]
        if count>4096 or Groups.groups.offset+count*ctypes.sizeof(Group)>len(groups): raise WindowsBlocked()
        decoded=[]
        for i in range(count):
            offset=Groups.groups.offset+i*ctypes.sizeof(Group)
            decoded.append((token_sid(groups,offset),Group.from_buffer(groups,offset).attributes))
        times=[ctypes.c_uint64() for _ in range(4)]
        if not get_times(process,*[ctypes.byref(value) for value in times]): raise WindowsBlocked()
        length=t.DWORD(32768); image=ctypes.create_unicode_buffer(length.value)
        if not get_image(process,0,image,ctypes.byref(length)) or not image.value: raise WindowsBlocked()
        return Identity(sid,get_pid(),times[0].value,elevated,integrity,admin_group_enabled(decoded),image.value,enabled_privileges)
    finally: api.close(token)
