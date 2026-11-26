# Original Meta82 selected pure lock orchestration cases; OS lock backend is inert.
import asyncio,pytest
from market_data.archive_file_lock import archive_file_lock,async_archive_file_lock

@pytest.mark.asyncio
async def test_async_lock_serializes_tasks(tmp_path):
    target = tmp_path / "trades.csv.gz"
    events = []

    async def worker(name):
        async with async_archive_file_lock(target):
            events.append((name, "start"))
            await asyncio.sleep(0.02)
            events.append((name, "end"))

    await asyncio.gather(worker("a"), worker("b"))
    assert len(events) == 4
    assert events[0][0] == events[1][0]
    assert events[2][0] == events[3][0]
    assert events[0][0] != events[2][0]


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_hold_lock(tmp_path):
    target = tmp_path / "trades.csv.gz"
    async with async_archive_file_lock(target):
        waiter = asyncio.create_task(_wait_for_lock(target))
        await asyncio.sleep(0.05)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
    async with async_archive_file_lock(target, timeout=0.2):
        pass


async def _wait_for_lock(target):
    async with async_archive_file_lock(target):
        return True


@pytest.mark.asyncio
async def test_cancelled_thread_read_keeps_lock_until_competing_writer(tmp_path, monkeypatch):
    """A cancelled archive read must finish before another task writes its path."""
    import threading
    from market_data import archive_ingestion

    target = tmp_path / "trades.csv.gz"
    target.write_bytes(b"old")
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    events = []

    def slow_receipt(*_args):
        entered.set()
        assert release.wait(5), "timed out waiting to release reader"
        finished.set()
        events.append("reader-finished")
        return None

    monkeypatch.setattr(archive_ingestion, "_load_receipt", slow_receipt)
    task = asyncio.create_task(archive_ingestion.acquire_archive(
        None, "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz", target
    ))
    writer = None
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()

        async def competing_writer():
            async with async_archive_file_lock(target, timeout=3):
                assert finished.is_set(), "writer entered before cancelled thread exited"
                events.append("writer-start")
                target.write_bytes(b"new")

        writer = asyncio.create_task(competing_writer())
        await asyncio.sleep(0.1)
        assert not writer.done(), "writer bypassed active cancelled reader"
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        if writer is not None:
            await asyncio.wait_for(writer, timeout=5)
    assert events == ["reader-finished", "writer-start"]
    assert target.read_bytes() == b"new"


@pytest.mark.asyncio
async def test_repeated_cancellation_does_not_release_lock_early(tmp_path, monkeypatch):
    """Even a second cancel while joining the worker cannot race a writer."""
    import threading
    from market_data import archive_ingestion

    target = tmp_path / "trades.csv.gz"
    target.write_bytes(b"old")
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def slow_receipt(*_args):
        entered.set()
        assert release.wait(5)
        finished.set()
        return None

    monkeypatch.setattr(archive_ingestion, "_load_receipt", slow_receipt)
    task = asyncio.create_task(archive_ingestion.acquire_archive(
        None, "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2025-01-01.csv.gz", target
    ))
    writer = None
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()

        async def write_after_reader():
            async with async_archive_file_lock(target, timeout=3):
                assert finished.is_set()
                target.write_bytes(b"new")

        writer = asyncio.create_task(write_after_reader())
        await asyncio.sleep(0.1)
        assert not writer.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        if writer is not None:
            await asyncio.wait_for(writer, timeout=5)
    assert target.read_bytes() == b"new"


