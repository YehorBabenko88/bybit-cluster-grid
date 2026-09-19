import asyncio
from grid.write_queue import BoundedWriteQueue

def test_queue_metrics_and_successful_write():
    async def run():
        seen=[]
        async def writer(x): seen.append(x)
        q=BoundedWriteQueue(writer,maxsize=4,workers=1)
        await q.start()
        await q.put("x")
        await asyncio.wait_for(q.q.join(),1)
        m=q.metrics()
        assert seen==["x"]
        assert m["writes_per_sec"]>0
        assert m["queue_depth"]==0
        for t in q.tasks: t.cancel()
    asyncio.run(run())

def test_full_queue_applies_backpressure_not_drop():
    async def run():
        gate=asyncio.Event()
        async def writer(x): await gate.wait()
        q=BoundedWriteQueue(writer,maxsize=1,workers=1)
        await q.start()
        await q.put(1)
        await asyncio.sleep(.02)
        await q.put(2)
        blocked=asyncio.create_task(q.put(3))
        await asyncio.sleep(.02)
        assert not blocked.done()
        assert q.metrics()["queue_ratio"]==1.0
        gate.set()
        await asyncio.wait_for(blocked,1)
        await asyncio.wait_for(q.q.join(),1)
        for t in q.tasks: t.cancel()
    asyncio.run(run())
