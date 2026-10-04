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


def test_corrupt_primary_checkpoint_recovers_from_backup(tmp_path):
    async def run():
        wal=SegmentWAL(tmp_path,max_bytes=100000)
        ids=[await wal.append({"n":n}) for n in range(4)]
        await wal.ack(ids[0])
        await wal.ack(ids[1])
        # Simulate a torn primary checkpoint write after a sudden power loss.
        wal.checkpoint.write_text("CORRUPT",encoding="ascii")
        restarted=SegmentWAL(tmp_path,max_bytes=100000)
        recovered=restarted.recover()
        assert [row["n"] for _,row in recovered]==[1,2,3]
        # Replaying one extra idempotent record is safe; replaying from zero is not.
        assert restarted._checkpoint_id()==ids[0]
    asyncio.run(run())


def test_wal_rejects_write_before_exceeding_capacity(tmp_path):
    async def run():
        wal=SegmentWAL(tmp_path,max_bytes=180)
        await wal.append({"payload":"x"*40})
        before=wal.bytes_used()
        try:
            await wal.append({"payload":"y"*200})
            assert False,"capacity guard did not fire"
        except BufferError:
            pass
        assert wal.bytes_used()==before
    asyncio.run(run())


def test_checkpoint_staging_paths_are_distinct(tmp_path):
    async def run():
        wal=SegmentWAL(tmp_path,max_bytes=100000)
        first=await wal.append({"n":1})
        second=await wal.append({"n":2})
        await wal.ack(first)
        await wal.ack(second)
        assert wal._checkpoint_id()==second
        assert wal.checkpoint.read_text(encoding="ascii").strip()==str(second)
        assert wal.checkpoint_backup.read_text(encoding="ascii").strip()==str(first)
        assert not (tmp_path/"checkpoint.next").exists()
        assert not (tmp_path/"checkpoint.backup.next").exists()
    asyncio.run(run())
