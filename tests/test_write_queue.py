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
        assert m["inflight_writes"]==0
        assert m["worker_tasks_alive"]==1
        assert m["retrying_workers"]==0
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
        assert q.metrics()["inflight_writes"]==2  # blocked put(3) has not been admitted
        gate.set()
        await asyncio.wait_for(blocked,1)
        await asyncio.wait_for(q.q.join(),1)
        for t in q.tasks: t.cancel()
    asyncio.run(run())


def test_retry_failure_recency_is_reported_and_recovery_keeps_history():
    async def run():
        attempts = 0

        async def writer(value):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ConnectionError("transient test failure")

        q = BoundedWriteQueue(writer, maxsize=2, workers=1,
                              retry_base_seconds=0.01, retry_max_seconds=0.02)
        assert q.metrics()["seconds_since_last_failure"] is None
        await q.start()
        try:
            await q.put("record")
            await asyncio.wait_for(q.q.join(), 2)
            metrics = q.metrics()
            assert attempts == 2
            assert metrics["write_failures"] == 1
            assert metrics["retrying_workers"] == 0
            assert metrics["seconds_since_last_failure"] is not None
            assert metrics["seconds_since_last_failure"] >= 0
            assert metrics["queue_depth"] == 0
        finally:
            await q.close()
    asyncio.run(run())


def test_retrying_worker_visible_until_shutdown():
    async def run():
        attempted=asyncio.Event()
        async def writer(value):
            attempted.set()
            raise ConnectionError("CONTROL unavailable")
        q=BoundedWriteQueue(writer,workers=1,retry_base_seconds=60,retry_max_seconds=60)
        await q.start()
        await q.put("durable-wal-record")
        await asyncio.wait_for(attempted.wait(),1)
        await asyncio.sleep(0)
        assert q.metrics()["retrying_workers"]==1
        assert q.metrics()["inflight_writes"]==1
        await q.close(drain_timeout=0)
        assert q.metrics()["retrying_workers"]==0
        assert q.metrics()["worker_tasks_alive"]==0
    asyncio.run(run())
