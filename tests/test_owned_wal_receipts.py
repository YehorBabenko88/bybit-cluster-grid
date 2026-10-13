import asyncio
from contextlib import asynccontextmanager
import time
import hashlib,json
from unittest.mock import AsyncMock

import pytest

from grid.collection_ownership import wal_envelope
from grid.storage import Storage
from grid.segment_wal import SegmentWAL


class Response:
    status=200
    def __init__(self,disposition):self.disposition=disposition
    async def json(self):
        return {'ownership_protocol':1,'disposition':self.disposition,'sha256':self.sha256}


class HTTP:
    def __init__(self,disposition):self.response=Response(disposition);self.rows=[]
    @asynccontextmanager
    async def post(self,url,json,headers,allow_redirects):
        assert allow_redirects is False
        self.rows.append(json)
        import json as codec
        self.response.sha256=hashlib.sha256(codec.dumps(json,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        yield self.response


@pytest.mark.parametrize('disposition',['LIVE','QUARANTINED','UNKNOWN'])
def test_wal_restart_keeps_grant_and_acks_only_durable_receipt(tmp_path,disposition):
    async def run():
        original=wal_envelope({'symbol':'BTCUSDT'}, {'generation':7,'session':'old-session'})
        wal=SegmentWAL(tmp_path)
        rid=await wal.append(original)
        restarted=SegmentWAL(tmp_path)
        row=list(restarted.iter_recover())[0][1]
        storage=Storage.__new__(Storage)
        storage.spool=restarted;storage.remote=True;storage.replay_ids=set();storage.http=HTTP(disposition)
        if disposition=='UNKNOWN':
            with pytest.raises(RuntimeError):await storage._save_spooled(rid,row)
            assert len(list(restarted.iter_recover()))==1
        else:
            await storage._save_spooled(rid,row)
            assert list(restarted.iter_recover())==[]
        assert storage.http.rows[0]['ownership']==original['ownership']
        assert storage.http.rows[0]['delivery_id']==original['delivery_id']
    asyncio.run(run())


def test_coordinator_local_replay_cannot_bypass_fencing(tmp_path):
    async def run():
        wal=SegmentWAL(tmp_path)
        row={'symbol':'BTCUSDT'};rid=await wal.append(row)
        storage=Storage.__new__(Storage)
        storage.spool=wal;storage.remote=False;storage.replay_ids=set()
        storage._save_direct=AsyncMock()
        with pytest.raises(RuntimeError,match='unfenced'):
            await storage._save_spooled(rid,row)
        storage._save_direct.assert_not_awaited()
        assert len(list(wal.iter_recover()))==1
    asyncio.run(run())
