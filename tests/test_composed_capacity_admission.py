import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from grid.micro_event_storage import MicroEventStorage
from grid.segment_wal import SegmentWAL


def test_evidence_wal_capacity_refuses_before_queue_admission(tmp_path):
    async def run():
        wal=SegmentWAL(tmp_path/'wal',max_bytes=256)
        sink=MicroEventStorage.__new__(MicroEventStorage)
        sink.spool=wal;sink.replay_done=asyncio.Event();sink.replay_done.set()
        sink._enqueue_lock=asyncio.Lock();sink.write_queue=SimpleNamespace(put=AsyncMock())
        try:
            with pytest.raises(BufferError):
                await sink.insert_event('BTCUSDT',1,'public_trade_capture_evidence',{'raw':'x'*1000})
            assert wal.recover()==[]
            sink.write_queue.put.assert_not_awaited()
        finally:wal.close()
    asyncio.run(run())


def test_bounded_queue_cancellation_retains_all_durable_records(tmp_path):
    async def run():
        from grid.write_queue import BoundedWriteQueue
        wal=SegmentWAL(tmp_path/'wal')
        queue=BoundedWriteQueue(AsyncMock(),maxsize=1)
        try:
            first=await wal.append({'symbol':'BTCUSDT','value':1})
            second=await wal.append({'symbol':'BTCUSDT','value':2})
            await queue.put(first,{'value':1})
            blocked=asyncio.create_task(queue.put(second,{'value':2}))
            await asyncio.sleep(0)
            assert queue.q.qsize()==1 and not blocked.done()
            blocked.cancel();await asyncio.gather(blocked,return_exceptions=True)
            assert [rid for rid,_ in wal.recover()]==[first,second]
        finally:wal.close()
    asyncio.run(run())
