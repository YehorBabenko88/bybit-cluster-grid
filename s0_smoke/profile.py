"""Explicit parent policy. Import is inert; no fallback or host authorization."""
import ctypes
import hashlib
import json
import ntpath
import os
import re
import uuid
from .windows import WindowsBlocked, Win32, Custody, require_operator


def validate_profile_paths(shell, token, volume):
    if (type(shell) is not str or type(token) is not str or type(volume) is not str
            or re.fullmatch(r'[A-Za-z]:\\',volume) is None or shell.casefold()!=token.casefold()
            or not shell.casefold().startswith(volume.casefold()) or len(shell)<=3
            or ntpath.normpath(shell)!=shell or '/' in shell or shell.endswith('\\')):
        raise WindowsBlocked('S0_USER_PROFILE_PATH_BLOCKED')
    try:
        if len(shell.encode('utf-16le'))>480: raise WindowsBlocked()
    except UnicodeError: raise WindowsBlocked() from None
    for part in shell[3:].split('\\'):
        if (not part or part.rstrip(' .')!=part or any(ord(c)<32 or c in ':<>"|?*%~' for c in part)
                or re.fullmatch(r'CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[0-9¹²³]|LPT[0-9¹²³]',part.split('.')[0].upper())):
            raise WindowsBlocked('S0_USER_PROFILE_PATH_BLOCKED')
    return shell


def _resolve(api,sid):
    t=api.t
    def bind(lib,name,args,result):
        f=getattr(lib,name);f.argtypes=args;f.restype=result;return f
    before=api.current_identity();require_operator(before)
    if before.sid!=sid:raise WindowsBlocked('S0_USER_PROFILE_SID_MISMATCH')
    token=t.HANDLE();thread=t.HANDLE();raw=t.LPVOID()
    process=bind(api.k,'GetCurrentProcess',[],t.HANDLE)
    thread_handle=bind(api.k,'GetCurrentThread',[],t.HANDLE)
    open_process=bind(api.a,'OpenProcessToken',[t.HANDLE,t.DWORD,t.LPVOID],t.BOOL)
    open_thread=bind(api.a,'OpenThreadToken',[t.HANDLE,t.DWORD,t.BOOL,t.LPVOID],t.BOOL)
    info=bind(api.a,'GetTokenInformation',[t.HANDLE,t.DWORD,t.LPVOID,t.DWORD,t.LPVOID],t.BOOL)
    package=bind(api.k,'GetCurrentPackageFullName',[t.LPVOID,t.LPVOID],ctypes.c_long)
    shell=ctypes.WinDLL('shell32',use_last_error=True);userenv=ctypes.WinDLL('userenv',use_last_error=True)
    ole=ctypes.WinDLL('ole32',use_last_error=True)
    known=bind(shell,'SHGetKnownFolderPath',[t.LPVOID,t.DWORD,t.HANDLE,t.LPVOID],ctypes.c_long)
    query=bind(userenv,'GetUserProfileDirectoryW',[t.HANDLE,t.LPWSTR,t.LPVOID],t.BOOL)
    free=bind(ole,'CoTaskMemFree',[t.LPVOID],None)
    try:
        if open_thread(thread_handle(),8,True,ctypes.byref(thread)) or ctypes.get_last_error()!=1008:raise WindowsBlocked()
        if not open_process(process(),8,ctypes.byref(token)):raise WindowsBlocked()
        app=t.DWORD();size=t.DWORD()
        if not info(token,29,ctypes.byref(app),4,ctypes.byref(size)) or size.value!=4 or app.value!=0:raise WindowsBlocked()
        count=t.DWORD()
        if package(ctypes.byref(count),None)!=15700 or count.value:raise WindowsBlocked()
        guid=ctypes.create_string_buffer(uuid.UUID('5e6c858f-0e22-4760-9afe-ea3317b67173').bytes_le)
        if known(guid,0x4000,None,ctypes.byref(raw))!=0 or not raw.value:raise WindowsBlocked()
        length=0
        while length<=240 and ctypes.c_uint16.from_address(raw.value+2*length).value:length+=1
        if not 3<length<=240:raise WindowsBlocked()
        value=ctypes.wstring_at(raw,length)
        count=t.DWORD()
        if query(token,None,ctypes.byref(count)) or ctypes.get_last_error()!=122 or not 4<count.value<=241:raise WindowsBlocked()
        bound=count.value;buffer=ctypes.create_unicode_buffer(bound)
        if not query(token,buffer,ctypes.byref(count)) or not 0<count.value<=bound:raise WindowsBlocked()
        value=validate_profile_paths(value,buffer.value,api.system_volume_root())
        after=api.current_identity();require_operator(after)
        if (before.sid,before.pid,before.creation_filetime)!=(after.sid,after.pid,after.creation_filetime):raise WindowsBlocked()
        return value
    finally:
        if raw.value:free(raw)
        if token.value:api.close(token)
        if thread.value:api.close(thread)


def parent_path(mode,sid,*,api=None):
    if mode=='LocalAppData':
        value=os.environ.get('LOCALAPPDATA')
        if not value:raise WindowsBlocked()
        return value
    if mode!='UserProfileV1':raise WindowsBlocked('S0_UNKNOWN_PARENT_CONTRACT')
    api=api or Win32()
    return api.user_profile_v1(sid) if hasattr(api,'user_profile_v1') else _resolve(api,sid)


class ParentLease:
    def __init__(self,mode,sid,*,api=None):self.mode=mode;self.sid=sid;self.api=api;self.custody=None
    def __enter__(self):
        self.path=parent_path(self.mode,self.sid,api=self.api)
        self.custody=Custody(self.path,self.sid,api=self.api,_strict_root=False,_profile_v1=self.mode=='UserProfileV1')
        self.custody.__enter__()
        try:self.guard();return self
        except BaseException:self.__exit__(None,None,None);raise
    def guard(self):
        if self.custody is None or parent_path(self.mode,self.sid,api=self.api).casefold()!=self.path.casefold():raise WindowsBlocked()
        self.custody.guard()
    def binding(self):
        self.guard();owner,protected,acl=self.custody.security[-1]
        digest=hashlib.sha256(json.dumps(dict(owner=owner,protected=protected,acl=acl.hex()),sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return dict(parent_scope=self.mode,parent_id=list(self.custody.identities[-1]),parent_acl_sha256=digest)
    def __exit__(self,*args):
        if self.custody is not None:self.custody.__exit__(*args);self.custody=None
