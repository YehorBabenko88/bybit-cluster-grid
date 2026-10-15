"""Real storage/WAL code; faults restricted to pytest temp files and fake HTTP."""
import asyncio,builtins,errno
from contextlib import asynccontextmanager
import pytest
from grid.segment_wal import SegmentWAL
from grid.collection_ownership import wal_envelope
from grid.storage import Storage
from test_owned_wal_receipts import HTTP

def test_coordinator_disconnect_retains_wal_until_durable_receipt(tmp_path):
    class Offline:
        @asynccontextmanager
        async def post(self,*a,**k):
            raise ConnectionError('synthetic coordinator disconnect')
            yield
    async def run():
        wal=SegmentWAL(tmp_path)
        row=wal_envelope({'symbol':'BTCUSDT'},{'generation':7,'session':'fixture-session'})
        rid=await wal.append(row)
        storage=Storage.__new__(Storage);storage.spool=wal;storage.remote=True;storage.replay_ids=set();storage.http=Offline()
        with pytest.raises(ConnectionError):await storage._save_spooled(rid,row)
        assert list(wal.iter_recover())==[(rid,row)]
        storage.http=HTTP('LIVE')
        await storage._save_spooled(rid,row)
        assert list(wal.iter_recover())==[]
        wal.close()
    asyncio.run(run())

def test_enospc_append_isolated_to_fixture_does_not_ack(tmp_path,monkeypatch):
    import grid.segment_wal as module
    async def run():
        wal=SegmentWAL(tmp_path);first=await wal.append({'safe':1})
        def disk_full(path,mode='r',*a,**k):
            if mode=='ab' and Path(path).parent==tmp_path:
                raise OSError(errno.ENOSPC,'synthetic capacity failure')
            return builtins.open(path,mode,*a,**k)
        with monkeypatch.context() as patch:
            patch.setattr(module,'open',disk_full,raising=False)
            with pytest.raises(OSError) as exc:await wal.append({'unsafe':2})
            assert exc.value.errno==errno.ENOSPC
        assert wal._checkpoint_id()==0
        wal.close()
        reopened=SegmentWAL(tmp_path)
        assert list(reopened.iter_recover())==[(first,{'safe':1})]
        reopened.close()
    asyncio.run(run())
from pathlib import Path
