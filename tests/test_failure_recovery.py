import asyncio
from grid.segment_wal import SegmentWAL
from grid.write_queue import BoundedWriteQueue

def test_db_outage_retries_then_drains_wal(tmp_path):
    async def run():
        wal=SegmentWAL(tmp_path,max_bytes=100000)
        attempts={"n":0}; committed=[]
        async def db_writer(record_id,row):
            attempts["n"]+=1
            if attempts["n"]<=2:
                raise ConnectionError("postgres unavailable")
            committed.append(row["n"])
            await wal.ack(record_id)
        q=BoundedWriteQueue(db_writer,maxsize=10,workers=1,retry_base_seconds=.01,retry_max_seconds=.02)
        await q.start()
        for n in range(3):
            rid=await wal.append({"n":n})
            await q.put(rid,{"n":n})
        await asyncio.wait_for(q.q.join(),8)
        assert committed==[0,1,2]
        assert wal.recover()==[]
        assert q.metrics()["write_failures"]==2
        for t in q.tasks: t.cancel()
    asyncio.run(run())

def test_restart_replays_only_uncheckpointed_records(tmp_path):
    async def run():
        wal=SegmentWAL(tmp_path,max_bytes=100000)
        ids=[]
        for n in range(4):
            ids.append(await wal.append({"n":n}))
        await wal.ack(ids[1])
        # Simulate process death: construct a new WAL object from the same directory.
        recovered=SegmentWAL(tmp_path,max_bytes=100000).recover()
        assert [row["n"] for _,row in recovered]==[2,3]
    asyncio.run(run())

def test_upsert_style_retry_does_not_lose_checkpoint_order(tmp_path):
    async def run():
        wal=SegmentWAL(tmp_path,max_bytes=100000)
        committed={}
        for n in range(3):
            rid=await wal.append({"symbol":"BTC","minute":n})
            # Simulates idempotent PostgreSQL ON CONFLICT upsert.
            row={"symbol":"BTC","minute":n}
            committed[(row["symbol"],row["minute"])]=row
            committed[(row["symbol"],row["minute"])]=row
            await wal.ack(rid)
        assert len(committed)==3
        assert wal.recover()==[]
    asyncio.run(run())
