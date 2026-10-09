"""Concurrent WAL producers must enqueue records in the same order as WAL IDs."""
import asyncio

from grid.storage import Storage
from grid.micro_event_storage import MicroEventStorage


class FakeSpool:
    def __init__(self):
        self.next_id = 0

    def ratio(self):
        return 0.0

    async def append(self, row):
        self.next_id += 1
        return self.next_id


class DelayedFirstPut:
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.ids = []

    async def put(self, record_id, row):
        if record_id == 1:
            self.entered.set()
            await self.release.wait()
        self.ids.append(record_id)


async def check_order(storage, submit):
    storage.spool = FakeSpool()
    storage.write_queue = DelayedFirstPut()
    storage._enqueue_lock = asyncio.Lock()
    storage.replay_done = asyncio.Event()
    storage.replay_done.set()
    if isinstance(storage, Storage):
        storage.replay_error = None

    first = asyncio.create_task(submit(storage, 1))
    await asyncio.wait_for(storage.write_queue.entered.wait(), 2)
    second = asyncio.create_task(submit(storage, 2))
    await asyncio.sleep(0)
    # The second producer must not enqueue WAL ID 2 ahead of ID 1.
    assert storage.write_queue.ids == []
    storage.write_queue.release.set()
    await asyncio.wait_for(asyncio.gather(first, second), 2)
    assert storage.write_queue.ids == [1, 2]


def test_minute_wal_append_and_enqueue_are_atomic_in_order():
    async def run():
        storage = Storage.__new__(Storage)
        await check_order(storage, lambda s, n: s.save({"n": n}))
    asyncio.run(run())


def test_micro_wal_append_and_enqueue_are_atomic_in_order():
    async def run():
        storage = MicroEventStorage.__new__(MicroEventStorage)
        await check_order(
            storage,
            lambda s, n: s.insert_event("BTCUSDT", n, "trade", {"n": n}),
        )
    asyncio.run(run())
