"""Actual WAL IDs must survive caller cancellation before ordered queue admission."""
import asyncio

import pytest

from grid.segment_wal import SegmentWAL
from grid.storage import Storage


@pytest.mark.parametrize('mode',['cancel','timeout'])
def test_cancel_after_append_reuses_single_retained_handoff(tmp_path,mode):
    async def scenario():
        wal=SegmentWAL(tmp_path/'wal');entered=asyncio.Event();release=asyncio.Event();queued=[]
        class Spool:
            def ratio(self):return 0.
            async def append(self,row):return await wal.append(row)
        class Queue:
            async def put(self,record_id,row):
                entered.set();await release.wait();queued.append(record_id)
        storage=Storage.__new__(Storage);storage.spool=Spool();storage.write_queue=Queue()
        storage.replay_done=asyncio.Event();storage.replay_done.set();storage._enqueue_lock=asyncio.Lock()
        row={'symbol':'BTCUSDT','start_ms':600000}
        first=asyncio.create_task(storage.save(row));retry=None
        try:
            await asyncio.wait_for(entered.wait(),1)
            if mode=='cancel':
                first.cancel()
                with pytest.raises(asyncio.CancelledError):await first
            else:
                with pytest.raises(asyncio.TimeoutError):await asyncio.wait_for(first,.01)
            retry=asyncio.create_task(storage.save(row));await asyncio.sleep(.02)
            assert [record_id for record_id,_ in wal.recover()]==[1]
            release.set();await asyncio.wait_for(retry,1)
            assert queued==[1]
            await wal.ack(1)
        finally:
            release.set()
            for task in (first,retry):
                if task is not None and not task.done():task.cancel()
            await asyncio.gather(*(task for task in (first,retry) if task is not None),return_exceptions=True)
    asyncio.run(scenario())


def test_completed_retained_receipt_survives_other_row_until_observed(tmp_path):
    async def scenario():
        wal=SegmentWAL(tmp_path/'wal');queued=[]
        class Spool:
            def ratio(self):return 0.
            async def append(self,row):return await wal.append(row)
        class Queue:
            async def put(self,record_id,row):queued.append(record_id)
        storage=Storage.__new__(Storage);storage.spool=Spool();storage.write_queue=Queue()
        storage.replay_done=asyncio.Event();storage.replay_done.set();storage._enqueue_lock=asyncio.Lock()
        row={'symbol':'BTCUSDT','start_ms':600000}
        receipt=await storage.save_retained(row)
        await storage.save({'symbol':'ETHUSDT','start_ms':600000})
        retry=await storage.save_retained(row)
        assert retry==receipt and queued==[1,2] and [key for key,_ in wal.recover()]==[1,2]
        storage.acknowledge_admission(retry)
        assert not storage._admissions
    asyncio.run(scenario())


def test_retained_admission_cap_precedes_task_creation_and_append(tmp_path):
    async def scenario():
        wal=SegmentWAL(tmp_path/'wal')
        class Spool:
            def ratio(self):return 0.
            async def append(self,row):return await wal.append(row)
        class Queue:
            async def put(self,*args):pass
        storage=Storage.__new__(Storage);storage.spool=Spool();storage.write_queue=Queue()
        storage.replay_done=asyncio.Event();storage.replay_done.set();storage._enqueue_lock=asyncio.Lock();storage.MAX_PENDING_ADMISSIONS=1
        receipt=await storage.save_retained({'n':1})
        with pytest.raises(BufferError):await storage.save({'n':2})
        assert len(storage._admissions)==1 and [key for key,_ in wal.recover()]==[1]
        storage.acknowledge_admission(receipt);await storage.save({'n':2})
        assert [key for key,_ in wal.recover()]==[1,2]
    asyncio.run(scenario())


def test_unexpected_postappend_queue_failure_blocks_later_wal_ids(tmp_path):
    async def scenario():
        wal=SegmentWAL(tmp_path/'wal')
        class Spool:
            def ratio(self):return 0.
            async def append(self,row):return await wal.append(row)
        class Queue:
            async def put(self,*args):raise RuntimeError('synthetic queue failure')
        storage=Storage.__new__(Storage);storage.spool=Spool();storage.write_queue=Queue()
        storage.replay_done=asyncio.Event();storage.replay_done.set();storage._enqueue_lock=asyncio.Lock()
        with pytest.raises(RuntimeError):await storage.save({'n':1})
        with pytest.raises(RuntimeError):await storage.save({'n':2})
        assert [key for key,_ in wal.recover()]==[1]
    asyncio.run(scenario())


def test_shutdown_quiesces_handoff_and_new_owner_replays_original_id(monkeypatch,tmp_path):
    from grid.write_queue import BoundedWriteQueue
    async def scenario():
        monkeypatch.setenv('ProgramData',str(tmp_path))
        storage=Storage();entered=asyncio.Event()
        class BlockedQueue:
            async def put(self,*args):entered.set();await asyncio.Event().wait()
            async def close(self,*args):pass
        storage.write_queue=BlockedQueue()
        caller=asyncio.create_task(storage.save_retained({'n':1}))
        await asyncio.wait_for(entered.wait(),1)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):await caller
        await asyncio.wait_for(storage.close(.01),1)
        assert [key for key,_ in storage.spool.recover()]==[1]
        assert all(record['task'].done() for record in storage._admissions.values())
        with pytest.raises(RuntimeError):await storage.save({'n':2})
        restored=Storage();acks=[]
        async def writer(record_id,row):
            await restored.spool.ack(record_id);acks.append(record_id)
        restored.write_queue=BoundedWriteQueue(writer,maxsize=2,workers=1)
        await restored.write_queue.start()
        monkeypatch.setattr('grid.storage.settings.replay_start_jitter_seconds',0)
        try:
            await asyncio.wait_for(restored._replay(restored.spool.iter_recover()),1)
            await restored.save({'n':2});await asyncio.wait_for(restored.write_queue.q.join(),1)
            assert acks==[1,2] and restored.spool.recover()==[]
        finally:await restored.close(.1)
    asyncio.run(scenario())


def test_compatibility_save_cannot_acknowledge_another_retained_owner(tmp_path):
    async def scenario():
        wal=SegmentWAL(tmp_path/'wal');queued=[]
        class Spool:
            def ratio(self):return 0.
            async def append(self,row):return await wal.append(row)
        class Queue:
            async def put(self,record_id,row):queued.append(record_id)
        storage=Storage.__new__(Storage);storage.spool=Spool();storage.write_queue=Queue()
        storage.replay_done=asyncio.Event();storage.replay_done.set();storage._enqueue_lock=asyncio.Lock()
        row={'n':1};receipt=await storage.save_retained(row)
        await storage.save(row)
        retry=await storage.save_retained(row)
        assert receipt==retry and queued==[1] and [key for key,_ in wal.recover()]==[1]
        storage.acknowledge_admission(receipt)
    asyncio.run(scenario())
