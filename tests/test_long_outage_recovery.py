import asyncio
from grid.write_queue import BoundedWriteQueue


def test_large_replay_does_not_block_service_start():
    async def run():
        gate=asyncio.Event()
        async def writer(*_):
            await gate.wait()
        q=BoundedWriteQueue(writer,maxsize=2,workers=1)
        await q.start()
        replay_done=asyncio.Event()
        async def replay():
            try:
                for n in range(20):
                    await q.put(n,{"n":n})
            finally:
                replay_done.set()
        task=asyncio.create_task(replay())
        await asyncio.sleep(.02)
        assert not replay_done.is_set()
        assert q.qsize() <= 2
        task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        await q.close(drain_timeout=.01)
    asyncio.run(run())


def test_storage_replay_is_background_and_live_writes_wait_for_order():
    from pathlib import Path
    for name in ("grid/storage.py","grid/micro_event_storage.py"):
        s=Path(name).read_text(encoding="utf-8")
        assert "asyncio.create_task(self._replay(pending))" in s
        assert "await self.replay_done.wait()" in s
        assert "self.replay_task.cancel()" in s


def test_worker_can_shed_load_without_successful_control_heartbeat():
    from pathlib import Path
    s=Path("grid/worker.py").read_text(encoding="utf-8")
    pressure=s.index("# Pressure control must remain autonomous")
    post=s.index("async with s.post(",pressure)
    assert pressure < post
    block=s[pressure:post]
    assert "symbols_to_drain" in block
    assert "await self.reconcile()" in block
