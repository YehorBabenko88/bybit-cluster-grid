"""Ownership and actual write-boundary races against an isolated CI schema."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
import uuid

import asyncpg
import pytest
import httpx
from types import SimpleNamespace
from unittest.mock import AsyncMock

from grid.collection_ownership import SCHEMA,grant_assignments,wal_envelope
from grid.fenced_ingest import ingest_owned,OwnershipExpired

pytestmark=pytest.mark.skipif(not os.environ.get('POSTGRES_DSN'),reason='isolated PostgreSQL required')


@asynccontextmanager
async def database():
    schema='collection_test_'+uuid.uuid4().hex
    admin=await asyncpg.connect(os.environ['POSTGRES_DSN'])
    pool=None
    try:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        async def setup(c):await c.execute(f'SET search_path TO "{schema}"')
        pool=await asyncpg.create_pool(os.environ['POSTGRES_DSN'],min_size=2,max_size=5,setup=setup)
        for sql in SCHEMA:await pool.execute(sql)
        await pool.execute('CREATE TABLE canonical_writes(symbol text,value integer)')
        yield pool
    finally:
        if pool:await pool.close()
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


def test_expiry_session_restart_receipts_and_quarantine():
    async def run():
        async with database() as pool:
            a,b=str(uuid.uuid4()),str(uuid.uuid4())
            grant=(await grant_assignments(pool,'old',a,['BTCUSDT']))['BTCUSDT']
            # No ACK and a fresh CONTROL client cannot steal a live grant.
            assert await grant_assignments(pool,'new',b,['BTCUSDT'])=={}
            assert await grant_assignments(pool,'old',b,['BTCUSDT'])=={}
            again=(await grant_assignments(pool,'old',a,['BTCUSDT']))['BTCUSDT']
            assert again['generation']==grant['generation']
            await pool.execute("UPDATE collection_ownership SET lease_until=clock_timestamp()-interval '1 second'")
            candidates=await asyncio.gather(grant_assignments(pool,'new',b,['BTCUSDT']),
                                           grant_assignments(pool,'other',str(uuid.uuid4()),['BTCUSDT']))
            assert sum(bool(x) for x in candidates)==1
            winner=0 if candidates[0] else 1
            node='new' if winner==0 else 'other'
            new=candidates[winner]['BTCUSDT']
            assert new['generation']==grant['generation']+1
            async def persist(c,row):
                await c.execute('INSERT INTO canonical_writes VALUES($1,$2)',row['symbol'],row['value'])
            stale=wal_envelope({'symbol':'BTCUSDT','value':1},grant)
            result=await ingest_owned(pool,'old','event',stale,persist)
            assert result['disposition']=='QUARANTINED'
            assert await pool.fetchval('SELECT count(*) FROM canonical_writes')==0
            stored=await pool.fetchval('SELECT payload FROM collection_ingest_receipts')
            assert json.loads(stored)==stale
            row=wal_envelope({'symbol':'BTCUSDT','value':2},new)
            results=await asyncio.gather(ingest_owned(pool,node,'event',row,persist),
                                         ingest_owned(pool,node,'event',row,persist))
            assert all(r['disposition']=='LIVE' for r in results)
            assert await pool.fetchval('SELECT count(*) FROM canonical_writes')==1
            with pytest.raises(ValueError,match='different bytes'):
                await ingest_owned(pool,node,'event',{**row,'value':99},persist)
            legacy=await ingest_owned(pool,'old','event',{'symbol':'BTCUSDT','value':0},persist)
            assert legacy['disposition']=='QUARANTINED'
    asyncio.run(run())


def test_delayed_transaction_blocks_takeover_then_rolls_back():
    async def run():
        async with database() as pool:
            a,b=str(uuid.uuid4()),str(uuid.uuid4())
            grant=(await grant_assignments(pool,'old',a,['BTCUSDT']))['BTCUSDT']
            await pool.execute("UPDATE collection_ownership SET lease_until=clock_timestamp()+interval '250 milliseconds'")
            entered=asyncio.Event()
            async def persist(c,row):
                await c.execute('INSERT INTO canonical_writes VALUES($1,$2)','BTCUSDT',1)
                entered.set()
                await asyncio.sleep(.4)
            task=asyncio.create_task(ingest_owned(pool,'old','event',wal_envelope({'symbol':'BTCUSDT'},grant),persist))
            await entered.wait()
            successor=asyncio.create_task(grant_assignments(pool,'new',b,['BTCUSDT']))
            await asyncio.sleep(.1)
            assert not successor.done()
            with pytest.raises(OwnershipExpired):await task
            assert (await successor)['BTCUSDT']['generation']==2
            assert await pool.fetchval('SELECT count(*) FROM canonical_writes')==0
            assert await pool.fetchval('SELECT count(*) FROM collection_ingest_receipts')==0
    asyncio.run(run())


def test_actual_http_ingest_is_fenced_on_postgres_write(monkeypatch):
    from grid import coordinator
    async def run():
        async with database() as pool:
            await pool.execute('CREATE TABLE market_events(symbol text,event_ts timestamptz,event_type text,payload jsonb)')
            session=str(uuid.uuid4())
            grant=(await grant_assignments(pool,'worker',session,['BTCUSDT']))['BTCUSDT']
            monkeypatch.setattr(coordinator,'db',SimpleNamespace(pool=pool))
            monkeypatch.setattr(coordinator,'authenticate_agent',AsyncMock(return_value=True))
            monkeypatch.setattr(coordinator,'runtime_state',AsyncMock(return_value={'state':'ACTIVE'}))
            monkeypatch.setattr(coordinator,'control_disk_state',lambda:{'state':'NORMAL'})
            payload=wal_envelope({'symbol':'BTCUSDT','event_ts':1000,'event_type':'test','payload':{'value':1}},grant)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=coordinator.app),base_url='http://synthetic') as client:
                headers={'X-Node-ID':'worker','X-Node-Credential':'test'}
                result=await client.post('/ingest/event',json=payload,headers=headers)
                assert result.status_code==200 and result.json()['disposition']=='LIVE'
                await pool.execute("UPDATE collection_ownership SET lease_until=clock_timestamp()-interval '1 second'")
                later=wal_envelope({**payload,'payload':{'value':2}},grant)
                result=await client.post('/ingest/event',json=later,headers=headers)
                assert result.status_code==200 and result.json()['disposition']=='QUARANTINED'
            assert await pool.fetchval('SELECT count(*) FROM market_events')==1
    asyncio.run(run())


def test_real_minute_features_and_derived_state_roll_back_together(monkeypatch):
    from grid import coordinator
    from grid.db import Database
    from grid.migrations import apply_migrations
    from grid.storage import Storage
    from grid.unified_features import UnifiedFeatureBuilder
    from grid.derived_pipeline import DerivedPipeline
    async def run():
        async with database() as pool:
            db=Database();db.pool=pool
            await db.ensure_schema();await apply_migrations(pool)
            storage=Storage.__new__(Storage)
            storage.pool=pool;storage.feature_builder=UnifiedFeatureBuilder()
            await storage.feature_builder.start(pool)
            storage.derived=DerivedPipeline(pool);await storage.derived.start()
            storage.scientific=None
            monkeypatch.setattr(coordinator,'db',db)
            monkeypatch.setattr(coordinator,'ingest_storage',storage)
            monkeypatch.setattr(coordinator,'ingest_lock',asyncio.Lock())
            monkeypatch.setattr(coordinator,'authenticate_agent',AsyncMock(return_value=True))
            monkeypatch.setattr(coordinator,'runtime_state',AsyncMock(return_value={'state':'ACTIVE'}))
            monkeypatch.setattr(coordinator,'control_disk_state',lambda:{'state':'NORMAL'})
            session=str(uuid.uuid4());grant=(await grant_assignments(pool,'worker',session,['BTCUSDT']))['BTCUSDT']
            payload=wal_envelope({'symbol':'BTCUSDT','start_ms':1700000000000,'open':100,'high':101,'low':99,'close':100,
                       'buy_volume':1,'sell_volume':0,'delta':1,'trade_count':1,'poc_price':100,
                       'levels':[{'price':100,'buy_volume':1,'sell_volume':0,'delta':1,'volume':1,'buy_count':1,'sell_count':0}]},grant)
            await pool.execute("ALTER TABLE poc_lifecycle ADD CONSTRAINT inject_failure CHECK(symbol <> 'BTCUSDT')")
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=coordinator.app),base_url='http://synthetic') as client:
                headers={'X-Node-ID':'worker','X-Node-Credential':'test'}
                with pytest.raises(asyncpg.CheckViolationError):
                    await client.post('/ingest/minute',json=payload,headers=headers)
                for table in ('candles_1m','footprint_1m','market_features_1m','poc_lifecycle','collection_ingest_receipts'):
                    assert await pool.fetchval('SELECT count(*) FROM '+table)==0
                assert storage.feature_builder.last_ts=={}
                assert storage.derived.poc.open=={}
                await pool.execute('ALTER TABLE poc_lifecycle DROP CONSTRAINT inject_failure')
                result=await client.post('/ingest/minute',json=payload,headers=headers)
                assert result.status_code==200 and result.json()['disposition']=='LIVE'
                assert await pool.fetchval('SELECT count(*) FROM market_features_1m')==1
                assert await pool.fetchval('SELECT count(*) FROM poc_lifecycle')==1
                assert 'BTCUSDT' in storage.feature_builder.last_ts
    asyncio.run(run())
