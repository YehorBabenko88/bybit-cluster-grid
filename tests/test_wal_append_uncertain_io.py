"""An ambiguous WAL append freezes its owner until explicit fresh recovery."""
import asyncio
import builtins

import pytest

from grid import segment_wal as module
from grid.segment_wal import SegmentWAL


def test_fsync_failure_cannot_reuse_allocated_id_with_different_payload(tmp_path,monkeypatch):
    async def scenario():
        wal=SegmentWAL(tmp_path)
        with monkeypatch.context() as failed:
            failed.setattr(module.os,'fsync',lambda fd:(_ for _ in ()).throw(OSError('synthetic fsync refusal')))
            with pytest.raises(OSError):await wal.append({'sequence':1})
        assert wal.recover()==[(1,{'sequence':1})]
        with pytest.raises(RuntimeError):await wal.append({'sequence':2})
        restored=SegmentWAL(tmp_path)
        assert await restored.append({'sequence':2})==2
        assert restored.recover()==[(1,{'sequence':1}),(2,{'sequence':2})]
        await restored.ack(1);await restored.ack(2)
    asyncio.run(scenario())


class FaultyAppend:
    def __init__(self,stream,stage):self.stream=stream;self.stage=stage
    def __enter__(self):self.stream.__enter__();return self
    def __exit__(self,*args):
        result=self.stream.__exit__(*args)
        if self.stage=='close':raise OSError('synthetic close refusal')
        return result
    def write(self,record):
        if self.stage in ('write','short'):
            count=len(record)//2;self.stream.write(record[:count])
            if self.stage=='write':raise OSError('synthetic partial write')
            return count
        return self.stream.write(record)
    def flush(self):
        self.stream.flush()
        if self.stage=='flush':raise OSError('synthetic flush refusal')
    def fileno(self):return self.stream.fileno()


def faulty_open(monkeypatch,stage):
    original=builtins.open
    def opening(path,mode='r',*args,**kwargs):
        stream=original(path,mode,*args,**kwargs)
        return FaultyAppend(stream,stage) if mode=='ab' else stream
    monkeypatch.setattr(builtins,'open',opening)


@pytest.mark.parametrize('stage',['write','short','flush','close'])
def test_uncertain_write_owner_refuses_further_append_and_fresh_owner_recovers(tmp_path,monkeypatch,stage):
    async def scenario():
        wal=SegmentWAL(tmp_path)
        with monkeypatch.context() as failed:
            faulty_open(failed,stage)
            with pytest.raises(OSError):await wal.append({'sequence':1})
        with pytest.raises(RuntimeError):await wal.append({'sequence':2})
        restored=SegmentWAL(tmp_path)
        prefix=[] if stage in ('write','short') else [(1,{'sequence':1})]
        assert restored.recover()==prefix
        expected=1 if not prefix else 2
        assert await restored.append({'sequence':2})==expected
        assert restored.recover()==prefix+[(expected,{'sequence':2})]
    asyncio.run(scenario())


def test_capacity_preflight_refusal_remains_retryable_without_new_owner(tmp_path):
    async def scenario():
        wal=SegmentWAL(tmp_path,max_bytes=1)
        with pytest.raises(BufferError):await wal.append({'sequence':1})
        wal.max_bytes=10000
        assert await wal.append({'sequence':1})==1
        assert wal.recover()==[(1,{'sequence':1})]
    asyncio.run(scenario())


def test_complete_prefix_ack_remains_available_after_partial_rotated_append(tmp_path,monkeypatch):
    async def scenario():
        wal=SegmentWAL(tmp_path,segment_bytes=1)
        assert await wal.append({'sequence':1})==1
        with monkeypatch.context() as failed:
            faulty_open(failed,'write')
            with pytest.raises(OSError):await wal.append({'sequence':2})
        await wal.ack(1)
        with pytest.raises(RuntimeError):await wal.append({'sequence':3})
        restored=SegmentWAL(tmp_path,segment_bytes=1)
        assert restored.recover()==[]
        assert await restored.append({'sequence':3})==2
        await restored.ack(2)
    asyncio.run(scenario())


def test_serialization_failure_before_io_does_not_freeze_owner(tmp_path):
    async def scenario():
        wal=SegmentWAL(tmp_path)
        with pytest.raises(TypeError):await wal.append({'invalid':object()})
        assert await wal.append({'sequence':1})==1
    asyncio.run(scenario())


def test_waiting_append_cannot_follow_ambiguous_owner_write(tmp_path,monkeypatch):
    async def scenario():
        wal=SegmentWAL(tmp_path)
        with monkeypatch.context() as failed:
            failed.setattr(module.os,'fsync',lambda fd:(_ for _ in ()).throw(OSError('synthetic fsync refusal')))
            results=await asyncio.gather(wal.append({'sequence':1}),wal.append({'sequence':2}),return_exceptions=True)
        assert isinstance(results[0],OSError) and isinstance(results[1],RuntimeError)
        assert wal.recover()==[(1,{'sequence':1})]
        with pytest.raises(ValueError):await wal.ack(1)
    asyncio.run(scenario())


def test_existing_storage_boundary_cannot_allocate_after_uncertain_wal_append(tmp_path,monkeypatch):
    from grid.storage import Storage
    async def scenario():
        wal=SegmentWAL(tmp_path);queued=[]
        class Queue:
            async def put(self,record_id,row):queued.append(record_id)
        storage=Storage.__new__(Storage);storage.spool=wal;storage.write_queue=Queue()
        storage.replay_done=asyncio.Event();storage.replay_done.set();storage._enqueue_lock=asyncio.Lock()
        with monkeypatch.context() as failed:
            failed.setattr(module.os,'fsync',lambda fd:(_ for _ in ()).throw(OSError('synthetic fsync refusal')))
            with pytest.raises(OSError):await storage.save({'sequence':1})
        with pytest.raises(RuntimeError):await storage.save({'sequence':2})
        assert wal.recover()==[(1,{'sequence':1})] and queued==[]
    asyncio.run(scenario())
