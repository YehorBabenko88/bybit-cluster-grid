"""Adversarial helpers: hosted-CI factory fixtures only; no root/target CLI.

No recursive cleanup. The only delete-on-close marker is atomically CREATE_NEW
inside the fixture; it never adopts a pathname or deletes a pre-existing file.
"""
import ctypes as C
from ctypes import wintypes as W
import os
import re
import struct
import uuid

from installer.ownership_native_fixture import _WindowsFixture,fixture_policy
from installer.ownership_session import FLAGS,PrototypeBlocked


def _junction_buffer(target):
    if not isinstance(target,str) or not re.fullmatch(r'[A-Z]:\\[^\x00/:]+(?:\\[^\x00/:]+)*',target):
        raise PrototypeBlocked('FIXTURE_NAME_INVALID')
    substitute=('\\??\\'+target).encode('utf-16-le');display=target.encode('utf-16-le')
    paths=substitute+b'\0\0'+display+b'\0\0'
    if len(paths)>16000:raise PrototypeBlocked('FIXTURE_NAME_INVALID')
    return struct.pack('<IHHHHHH',0xA0000003,8+len(paths),0,0,len(substitute),len(substitute)+2,len(display))+paths


class FixtureAdversary:
    def __init__(self,p):
        fixture_policy()
        if type(p) is not _WindowsFixture:raise PrototypeBlocked('FACTORY_ONLY')
        self.p=p;self.n=p._native
        self.n._bind(self.n.k,'DeviceIoControl',
                     [W.HANDLE,W.DWORD,C.c_void_p,W.DWORD,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p],W.BOOL)

    @staticmethod
    def _valid_handle(h):
        if h in (None,0,C.c_void_p(-1).value):raise C.WinError(C.get_last_error())
        return h

    def junction(self):
        # Both the empty mountpoint AND target are fixed directories created by
        # this same fixture factory. No arbitrary junction target is accepted.
        source=self.p._path('postgres/data');target=self.p._path('releases')
        data=_junction_buffer(str(target))
        h=self._valid_handle(self.n.k.CreateFileW(str(source),0x40000000,7,None,3,FLAGS,None))
        try:
            buf=C.create_string_buffer(data);returned=W.DWORD()
            if not self.n.k.DeviceIoControl(h,0x900A4,buf,len(data),None,0,C.byref(returned),None):
                raise C.WinError(C.get_last_error())
        finally:self.n.close(h)

    def rename_ancestor(self,name):
        if name not in ('','data','postgres'):raise PrototypeBlocked('FIXTURE_NAME_INVALID')
        source=self.p._path(name)
        target=source.with_name(source.name+'-adversarial-'+uuid.uuid4().hex)
        os.rename(source,target)  # Only the factory-created entry, never its parent.

    def acl(self,*,restore=False):
        self.n.protect(self.p._path('tasks.plan.json'),foreign_writer=not restore)

    def marker(self,ready,stop,errors):
        h=None
        try:
            path=self.p._root/('adversarial-marker-'+uuid.uuid4().hex)
            # DELETE|READ, CREATE_NEW, DELETE_ON_CLOSE; no existing file adoption.
            h=self._valid_handle(self.n.k.CreateFileW(str(path),0x80010000,1,None,1,0x04000000,None))
            ready.set()
            if not stop.wait(20):errors.append('MARKER_TIMEOUT')
        except Exception:errors.append('MARKER_API_FAILED');ready.set()
        finally:
            if h is not None:
                try:self.n.close(h)
                except Exception:errors.append('MARKER_CLOSE_FAILED')
