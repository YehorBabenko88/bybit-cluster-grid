import asyncio
import pytest
from grid.segment_wal import SegmentWAL
from grid.storage import Storage
from grid.micro_event_storage import MicroEventStorage
from tests.test_wal_enqueue_order import FakeSpool, DelayedFirstPut


def test_complete_unterminated_record_survives_next_append(tmp_path):
    async def run():
        wal = SegmentWAL(tmp_path)
        await wal.append({'n': 1})
        segment = wal._segments()[0]
        segment.write_bytes(segment.read_bytes().rstrip(b'\n'))
        wal = SegmentWAL(tmp_path)
        await wal.append({'n': 2})
        assert wal.recover() == [(1, {'n': 1}), (2, {'n': 2})]
    asyncio.run(run())


@pytest.mark.parametrize('cls', [Storage, MicroEventStorage])
def test_cancelled_admission_fails_closed(cls):
    async def run():
        storage = cls.__new__(cls)
        storage.spool = FakeSpool()
        storage.write_queue = DelayedFirstPut()
        storage._enqueue_lock = asyncio.Lock()
        storage.replay_done = asyncio.Event(); storage.replay_done.set()
        storage.replay_error = None
        async def submit(n):
            if cls is Storage:
                await storage.save({'n': n})
            else:
                await storage.insert_event('BTC', n, 'trade', {})
        first = asyncio.create_task(submit(1))
        await storage.write_queue.entered.wait()
        first.cancel()
        await asyncio.sleep(0)
        first.cancel()  # Repeated cancellation must not release the order lock.
        second = asyncio.create_task(submit(2))
        await asyncio.sleep(0)
        storage.write_queue.release.set()
        results = await asyncio.wait_for(asyncio.gather(first, second, return_exceptions=True), 2)
        assert isinstance(results[0], asyncio.CancelledError)
        assert isinstance(results[1], RuntimeError)
        assert storage.write_queue.ids == []
    asyncio.run(run())


@pytest.mark.parametrize('cls', [Storage, MicroEventStorage])
def test_replay_failure_wakes_waiters_fail_closed(cls, monkeypatch):
    async def run():
        storage = cls.__new__(cls)
        storage.replay_done = asyncio.Event()
        storage.replay_ids = set()
        storage.replay_error = None
        monkeypatch.setattr('grid.storage.settings.replay_start_jitter_seconds', 0)
        def broken():
            raise OSError('unreadable WAL')
            yield
        if cls is Storage:
            waiter = asyncio.create_task(storage.save({}))
        else:
            waiter = asyncio.create_task(storage.insert_event('BTC', 1, 'trade', {}))
        await asyncio.sleep(0)
        with pytest.raises(OSError):
            await storage._replay(broken())
        assert storage.replay_done.is_set()
        with pytest.raises(RuntimeError, match='replay failed'):
            await asyncio.wait_for(waiter, .2)
    asyncio.run(run())


@pytest.mark.parametrize('cls', [Storage, MicroEventStorage])
@pytest.mark.parametrize('rate', [float('nan'), float('inf'), float('-inf'), -1])
def test_invalid_replay_rate_does_not_change_rate(cls, rate):
    storage = cls.__new__(cls)
    storage.replay_rate = 10
    storage.set_replay_rate(rate)
    assert storage.replay_rate == 10


@pytest.mark.parametrize('cls', [Storage, MicroEventStorage])
def test_replay_cancellation_wakes_waiters(cls, monkeypatch):
    async def run():
        storage = cls.__new__(cls)
        storage.replay_done = asyncio.Event()
        storage.replay_ids = set()
        storage.replay_error = None
        storage.write_queue = DelayedFirstPut()
        monkeypatch.setattr('grid.storage.settings.replay_start_jitter_seconds', 0)
        replay = asyncio.create_task(storage._replay(iter([(1, {})])))
        await storage.write_queue.entered.wait()
        replay.cancel()
        with pytest.raises(asyncio.CancelledError):
            await replay
        assert storage.replay_done.is_set()
        assert isinstance(storage.replay_error, asyncio.CancelledError)
        with pytest.raises(RuntimeError, match='replay failed'):
            if cls is Storage:
                await storage.save({})
            else:
                await storage.insert_event('BTC', 1, 'trade', {})
    asyncio.run(run())


@pytest.mark.parametrize('cls', [Storage, MicroEventStorage])
@pytest.mark.parametrize('rate', [0, 2.5, '12'])
def test_valid_replay_rate_accepts_pause_and_finite_rates(cls, rate):
    storage = cls.__new__(cls)
    storage.replay_rate = 10
    storage.set_replay_rate(rate)
    assert storage.replay_rate == float(rate)


@pytest.mark.parametrize('cls', [Storage, MicroEventStorage])
def test_full_queue_cancel_is_bounded_and_next_producer_fails_closed(cls, tmp_path):
    async def run():
        storage = cls.__new__(cls)
        storage.spool = SegmentWAL(tmp_path)
        storage._enqueue_lock = asyncio.Lock()
        storage.replay_done = asyncio.Event(); storage.replay_done.set()
        storage.replay_error = None
        entered = asyncio.Event()
        class FullQueue:
            def __init__(self):
                self.q = asyncio.Queue(maxsize=1)
                self.q.put_nowait(('existing', {}))
            async def put(self, record_id, row):
                entered.set()
                await self.q.put((record_id, row))
        storage.write_queue = FullQueue()
        async def submit(n):
            if cls is Storage:
                await storage.save({'n': n})
            else:
                await storage.insert_event('BTC', n, 'trade', {})
        first = asyncio.create_task(submit(1))
        await entered.wait()
        second = asyncio.create_task(submit(2))
        await asyncio.sleep(0)
        first.cancel()
        await asyncio.sleep(0)
        first.cancel()
        done, pending = await asyncio.wait([first, second], timeout=.2)
        # Always release for cleanup so the RED run cannot hang asyncio.run.
        if pending:
            storage.write_queue.q.get_nowait()
            await asyncio.sleep(0)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        assert not pending, 'cancelled admission remains blocked on a full queue'
        assert first.cancelled()
        assert isinstance(second.exception(), RuntimeError)
        assert len(storage.spool.recover()) == 1
        assert storage.write_queue.q.qsize() == 1
    asyncio.run(run())


@pytest.mark.parametrize('cls', [Storage, MicroEventStorage])
def test_cancellation_after_successful_admission_keeps_storage_healthy(cls):
    async def run():
        storage = cls.__new__(cls)
        storage.spool = FakeSpool()
        storage._enqueue_lock = asyncio.Lock()
        storage.replay_done = asyncio.Event(); storage.replay_done.set()
        storage.replay_error = None
        parent = None
        class AdmittedQueue:
            def __init__(self):
                self.ids = []
            async def put(self, record_id, row):
                self.ids.append(record_id)
                if record_id == 1:
                    # Cancel the producer after the child has admitted its ID,
                    # before shield resumes the producer.
                    parent.cancel()
        storage.write_queue = AdmittedQueue()
        async def submit(n):
            if cls is Storage:
                await storage.save({'n': n})
            else:
                await storage.insert_event('BTC', n, 'trade', {})
        parent = asyncio.create_task(submit(1))
        with pytest.raises(asyncio.CancelledError):
            await parent
        assert storage.replay_error is None
        await submit(2)
        assert storage.write_queue.ids == [1, 2]
    asyncio.run(run())
