"""Archive ingestion fixtures replace only native destination lock operations.

The real orchestration and contention/cancellation loop still run; this proves
no actual OS multi-process lock/ACL. Native/process tests remain unexecuted.
"""
import pytest

@pytest.fixture(autouse=True)
def archive_lock_inert_backend(request,monkeypatch):
    if not any(name in request.node.path.name for name in ('archive_ingestion','archive_lock_contract')):
        yield
        return
    from market_data import archive_file_lock
    held=set()
    def acquire(handle):
        key=str(handle.name)
        if key in held:raise BlockingIOError('synthetic lock contention')
        held.add(key)
    def release(handle):held.remove(str(handle.name))
    monkeypatch.setattr(archive_file_lock,'_lock',acquire)
    monkeypatch.setattr(archive_file_lock,'_unlock',release)
    yield
    assert not held
