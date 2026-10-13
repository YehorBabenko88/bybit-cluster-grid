"""One participating OS process owns a WAL directory, including recovery/repair."""
import asyncio
import os
from pathlib import Path
import threading
import weakref

_owners=weakref.WeakValueDictionary()
_registry_lock=threading.RLock()


class DirectoryOwner:
    def __init__(self,root):
        self.pid=os.getpid();self.next_id=0;self.faulted=False;self.retired={}
        self.lock=asyncio.Lock();self.sync_lock=threading.RLock()
        self.file=open(Path(root)/'directory.owner.lock','a+b')
        try:
            os.set_inheritable(self.file.fileno(),False)
            self.file.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise RuntimeError('WAL directory is owned by another process') from exc

    def check(self):
        if self.pid!=os.getpid() or self.file.closed:
            raise RuntimeError('WAL directory owner is closed or belongs to another process')

    def __del__(self):
        # Closing, not explicitly unlocking, is safe for inherited fork FDs.
        handle=getattr(self,'file',None)
        if handle is not None:handle.close()


def acquire_directory(root):
    key=os.path.normcase(str(Path(root).resolve()))
    with _registry_lock:
        owner=_owners.get(key)
        if owner is not None and owner.pid==os.getpid():
            owner.check();return owner
        if owner is not None:
            owner.file.close()  # only this child's inherited descriptor
        owner=DirectoryOwner(root)
        _owners[key]=owner
        return owner


def _after_fork():
    global _owners,_registry_lock
    for owner in list(_owners.values()):owner.file.close()
    _owners=weakref.WeakValueDictionary()
    _registry_lock=threading.RLock()


if hasattr(os,'register_at_fork'):
    os.register_at_fork(after_in_child=_after_fork)
