import asyncio
import math

import pytest

from grid.storage import Storage


def test_failed_replay_wakes_producers_instead_of_hanging():
    async def scenario():
        storage=Storage.__new__(Storage)
        storage.replay_done=asyncio.Event()
        storage.replay_error=None
        storage.replay_started_at=0.0
        storage.replay_sent=0
        storage.replay_ids=set()
        def broken_pending():
            yield 1, {"n":1}
            raise RuntimeError("corrupt WAL segment")
        class Queue:
            async def put(self,*args):
                pass
        storage.write_queue=Queue()
        # Disable startup jitter to isolate the replay failure path.
        from grid import storage as storage_module
        original=storage_module.settings.replay_start_jitter_seconds
        storage_module.settings.replay_start_jitter_seconds=0
        try:
            with pytest.raises(RuntimeError,match="corrupt WAL"):
                await storage._replay(broken_pending())
            assert storage.replay_done.is_set()
            with pytest.raises(RuntimeError,match="WAL replay failed"):
                await asyncio.wait_for(storage.save({"n":2}),timeout=1)
        finally:
            storage_module.settings.replay_start_jitter_seconds=original
    asyncio.run(scenario())


def test_replay_rate_rejects_nan_infinity_and_negative():
    storage=Storage.__new__(Storage)
    storage.replay_rate=3.0
    for value in [float("nan"),float("inf"),-1,"invalid"]:
        storage.set_replay_rate(value)
        assert storage.replay_rate==3.0
    storage.set_replay_rate(0)
    assert storage.replay_rate==0
    storage.set_replay_rate(2.5)
    assert math.isclose(storage.replay_rate,2.5)
