"""Actual sender, WAL, discovery, ASGI, lease fences and disposable PostgreSQL."""
import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx
import pytest
from grid.collection_ownership import grant_assignments,wal_envelope
from grid.control_runtime import Epoch,FencedPool,LeaderFenceError,epoch_context
from grid.fenced_ingest import ingest_owned,OwnershipExpired
from grid.micro_event_storage import MicroEventStorage,NODE_ID
from grid.segment_wal import SegmentWAL
from test_collection_ownership_postgres import database,http_leader

pytestmark=pytest.mark.skipif(not os.environ.get('POSTGRES_DSN'),reason='disposable CI database required')


def test_capture_lost_ack_takeover_replay_is_one_quarantined_record(monkeypatch,tmp_path):
    from grid import coordinator,active_control,credential_store
    async def run():
        async with database() as pool:
            db=SimpleNamespace(pool=pool)
            monkeypatch.setattr(coordinator,'db',db)
            await http_leader(monkeypatch,coordinator,db,pool)
            monkeypatch.setattr(coordinator,'authenticate_agent',AsyncMock(return_value=True))
            monkeypatch.setattr(coordinator,'runtime_state',AsyncMock(return_value={'state':'ACTIVE'}))
            monkeypatch.setattr(coordinator,'control_disk_state',lambda:{'state':'NORMAL'})
            monkeypatch.setattr(credential_store,'node_credential',lambda:'test')
            monkeypatch.setattr(active_control.settings,'coordinator_candidates',['http://old:8765','http://new:8765'])
            await pool.execute('CREATE TABLE market_events(symbol text,payload jsonb)')
            grant=(await grant_assignments(pool,NODE_ID,str(uuid.uuid4()),['BTCUSDT']))['BTCUSDT']
            row=wal_envelope({'symbol':'BTCUSDT','event_ts':1700000000123,
                'event_type':'public_trade_capture_evidence','payload':{'capture_stage':'PRE_AGGREGATION','trade_id':'t1'}},grant)
            state={'active':'http://old:8765','drop_ack':True};paths=[]
            async def probe(address):return {'ok':True,'control_leader':address==state['active'],
                                             'control_owner':'control','control_epoch':1}
            monkeypatch.setattr(active_control,'_probe',probe)
            class Reply:
                def __init__(self,response):self.response=response;self.status=response.status_code
                async def json(self):return self.response.json()
            class HTTP:
                @asynccontextmanager
                async def post(self,address,**kwargs):
                    paths.append(address)
                    assert kwargs.pop('allow_redirects') is False
                    assert address==state['active']+'/ingest/capture'
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=coordinator.app),base_url=state['active']) as client:
                        response=await client.post('/ingest/capture',**kwargs)
                    if state['drop_ack']:
                        state['drop_ack']=False
                        raise ConnectionError('response lost after PostgreSQL COMMIT')
                    yield Reply(response)
            wal=SegmentWAL(tmp_path/'wal')
            try:
                rid=await wal.append(row)
                sink=MicroEventStorage.__new__(MicroEventStorage)
                sink.spool=wal;sink.http=HTTP();sink.replay_ids={rid};sink.replay_rate=1000000
                sink._last_replay_send=0;sink.replay_sent=0
                with pytest.raises(ConnectionError):await sink._save_spooled(rid,row)
                assert len(wal.recover())==1
                assert await pool.fetchval('SELECT count(*) FROM collection_ingest_receipts')==1
                old=Epoch('test-control',1)
                await pool.execute("""UPDATE service_leases SET owner='successor',metadata='{"epoch":2}',
                  lease_until=clock_timestamp()+interval '30 seconds'""")
                monkeypatch.setattr(coordinator,'control_runtime',SimpleNamespace(ready=True,token=Epoch('successor',2)))
                state['active']='http://new:8765'
                await sink._save_spooled(rid,wal.recover()[0][1])
                assert wal.recover()==[]
                assert paths==['http://old:8765/ingest/capture','http://new:8765/ingest/capture']
                assert await pool.fetchval('SELECT count(*) FROM collection_ingest_receipts')==1
                assert await pool.fetchval('SELECT disposition FROM collection_ingest_receipts')=='QUARANTINED'
                assert await pool.fetchval('SELECT count(*) FROM market_events')==0
                with epoch_context(old):
                    with pytest.raises(LeaderFenceError):
                        await db.pool.execute("INSERT INTO canonical_writes VALUES('stale',1)")
                assert await pool.fetchval('SELECT count(*) FROM canonical_writes')==0
            finally:wal.close()
    asyncio.run(run())


def test_symbol_ttl_response_delay_cannot_outlive_lease_in_deferred_commit():
    async def run():
        async with database() as pool:
            grant=(await grant_assignments(pool,'node',str(uuid.uuid4()),['BTCUSDT']))['BTCUSDT']
            await pool.execute("""CREATE FUNCTION slow_commit() RETURNS trigger LANGUAGE plpgsql AS $$
              BEGIN PERFORM pg_sleep(.6);RETURN NEW;END $$""")
            await pool.execute("""CREATE CONSTRAINT TRIGGER delayed_commit AFTER INSERT ON canonical_writes
              DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION slow_commit()""")
            await pool.execute("UPDATE collection_ownership SET lease_until=clock_timestamp()+interval '800 milliseconds'")
            class DelayedConnection:
                def __init__(self,c):self.c=c
                def __getattr__(self,name):return getattr(self.c,name)
                async def fetchval(self,sql,*args):
                    value=await self.c.fetchval(sql,*args)
                    if 'extract(epoch' in sql:await asyncio.sleep(.3)
                    return value
            class DelayedPool:
                @asynccontextmanager
                async def acquire(self):
                    async with pool.acquire() as c:yield DelayedConnection(c)
            async def persist(c,row):await c.execute('INSERT INTO canonical_writes VALUES($1,1)',row['symbol'])
            with pytest.raises(OwnershipExpired):
                await ingest_owned(DelayedPool(),'node','minute',wal_envelope({'symbol':'BTCUSDT'},grant),persist)
            assert await pool.fetchval('SELECT count(*) FROM canonical_writes')==0
            assert await pool.fetchval('SELECT count(*) FROM collection_ingest_receipts')==0
    asyncio.run(run())
