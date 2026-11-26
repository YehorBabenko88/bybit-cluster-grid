"""Cross-process advisory lock for a single archive destination.

Uses a stable sibling lock file. The lock is held for the complete download,
validation, and receipt publication transaction.
"""
from __future__ import annotations

from contextlib import contextmanager, asynccontextmanager
import asyncio
import os
from pathlib import Path
import time
from math import isfinite
import stat



def guard_archive_destination(destination):
    """Reject existing redirections before IO; protected ownership is still required."""
    raw=str(destination)
    if raw.startswith(('\\\\','//')):raise ValueError('nonlocal archive destination')
    path=Path(os.path.abspath(raw))
    related=[path,*[path.with_name(path.name+suffix) for suffix in
        ('.partial','.partial.json','.partial.json.tmp','.audit.json','.audit.json.partial','.lock')]]
    for target in related:
        for part in (*reversed(target.parents),target):
            try:info=part.lstat()
            except FileNotFoundError:continue
            if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&1024:
                raise ValueError('linked archive destination')
            if part==target and (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1):
                raise ValueError('archive file identity rejected')
    return path

@contextmanager
def archive_file_lock(destination: str | Path, *, timeout: float = 120.0):
    if type(timeout) not in (int,float) or not isfinite(timeout) or not 0 <= timeout <= 120:
        raise ValueError("timeout must be nonnegative")
    path = guard_archive_destination(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+b") as handle:
        _prepare_lock_file(handle)
        deadline = time.monotonic() + timeout
        while True:
            try:
                _lock(handle)
                break
            except (BlockingIOError, PermissionError):
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"archive lock timed out: {path}")
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        try:
            yield
        finally:
            _unlock(handle)


def _lock(handle):
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle):
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@asynccontextmanager
async def async_archive_file_lock(destination: str | Path, *, timeout: float = 120.0):
    """Async-friendly lock: never block the event loop while waiting."""
    if type(timeout) not in (int,float) or not isfinite(timeout) or not 0 <= timeout <= 120:
        raise ValueError("timeout must be nonnegative")
    path = guard_archive_destination(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+b") as handle:
        _prepare_lock_file(handle)
        deadline = time.monotonic() + timeout
        acquired = False
        try:
            while not acquired:
                try:
                    _lock(handle)
                    acquired = True
                except (BlockingIOError, PermissionError):
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"archive lock timed out: {path}")
                    await asyncio.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            yield
        finally:
            if acquired:
                _unlock(handle)


def _prepare_lock_file(handle):
    """Position the file cursor without modifying shared lock data."""
    # Locking a byte beyond EOF is supported by Windows msvcrt.locking;
    # no shared lock-file writes are necessary.
    handle.seek(0)
