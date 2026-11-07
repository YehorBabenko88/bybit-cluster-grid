"""Proposed requirement RED on exact PR268, not a new wire/runtime implementation.

Real collector -> real Database.insert_event SQL -> volatile fake connection
-> real feature reader using a predicate-faithful fake pool. No PostgreSQL,
provider send, durable restart or authority claim. No producer/consumer code or
wire is changed by this proposed requirement test.
"""
import asyncio
import copy
from datetime import datetime,timezone
import json
import time

import pytest

from grid import microstructure as market
from grid.db import Database
from grid.unified_features import UnifiedFeatureBuilder


class VolatileSQLFixture:
    def __init__(self):self.records=[];self.sql=[]
    def acquire(self):return self
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return None
    async def execute(self,sql,*args):
        assert 'INSERT INTO market_events' in sql
        symbol,stamp,kind,payload=args
        self.sql.append((sql,args))
        # Mirrors actual DB SQL to_timestamp(event_ts/1000.0), not receipt time.
        self.records.append({'id':len(self.records)+1,'symbol':symbol,
          'event_ts':datetime.fromtimestamp(stamp/1000,timezone.utc),
          'event_type':kind,'payload':json.loads(payload)})
        return 'INSERT 0 1'
    async def fetchrow(self,sql,*args):
        if 'orderbook_snapshot' not in sql:return None
        assert 'event_ts<=$2' in sql and "event_ts>=$2-($3 * interval '1 second')" in sql
        assert 'ORDER BY event_ts DESC LIMIT 1' in sql
        symbol,query,age=args
        selected=[r for r in self.records if r['symbol']==symbol
          and r['event_type']=='orderbook_snapshot'
          and 0<=(query-r['event_ts']).total_seconds()<=age]
        return copy.deepcopy(max(selected,key=lambda r:r['event_ts'])) if selected else None


class Socket:
    def __init__(self,items):self.items=iter([json.dumps({'op':'subscribe','success':True}),*items])
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return None
    async def send(self,_):pass
    async def recv(self):
        try:value=next(self.items)
        except StopIteration:raise asyncio.CancelledError
        if isinstance(value,BaseException):raise value
        return value


def image(stamp,seq=100,update=10,kind='snapshot',bids=None,asks=None):
    return json.dumps({'topic':'orderbook.50.BTCUSDT','type':kind,'ts':stamp,
      'data':{'seq':seq,'u':update,'b':[['100','1']] if bids is None else bids,
              'a':[['101','2']] if asks is None else asks}})


async def ingest(monkeypatch,pool,sockets):
    async def ready():pass
    async def no_delay(_):pass
    stream=iter(sockets)
    monkeypatch.setattr(market,'wait_for_internet',ready)
    monkeypatch.setattr(market.websockets,'connect',lambda *a,**k:next(stream))
    monkeypatch.setattr(market.asyncio,'sleep',no_delay)
    db=Database();db.pool=pool
    with pytest.raises(asyncio.CancelledError):
        await market.MicrostructureCollector(db).run_batch(['BTCUSDT'])


async def query(pool,stamp):
    row={'symbol':'BTCUSDT','ts':datetime.fromtimestamp(stamp/1000,timezone.utc),
      'open':100,'high':102,'low':99,'close':101,'buy_volume':8,'sell_volume':2,
      'delta':6,'poc_price':100,'quality_status':'GOOD'}
    return await UnifiedFeatureBuilder().build(pool,row)


def assert_unavailable(built):
    assert built['capabilities']['orderbook'] is False, 'F06: previous AVAILABLE row survived observed invalidation'
    for key in ('book_imbalance','spread','bid_depth','ask_depth'):
        assert built['features'][key] is None


@pytest.mark.parametrize('reason',['empty_delta','sequence_gap','malformed_levels',
                                  'older_exchange_time_gap','stale_snapshot_replay'])
def test_observed_invalidation_beats_previous_available_within_two_seconds(monkeypatch,reason):
    async def run():
        start=int(time.time()*1000)-10000;pool=VolatileSQLFixture()
        if reason=='empty_delta':bad=image(start+500,101,11,'delta',asks=[['101','0']])
        elif reason=='sequence_gap':bad=image(start+500,99,11,'delta')
        elif reason=='malformed_levels':bad=image(start+500,101,11,'delta',bids=[['x','1']])
        elif reason=='older_exchange_time_gap':bad=image(start-500,99,11,'delta')
        else:bad=image(start+500,99,11,'delta')
        frames=[image(start),bad]
        if reason=='stale_snapshot_replay':frames.append(image(start-100,98,8))
        await ingest(monkeypatch,pool,[Socket(frames)])
        assert pool.sql and all('INSERT INTO market_events' in sql for sql,_ in pool.sql)
        assert_unavailable(await query(pool,start+2000))
    asyncio.run(run())


def test_reconnect_without_new_snapshot_cannot_use_old_connection_book(monkeypatch):
    async def run():
        start=int(time.time()*1000)-10000;pool=VolatileSQLFixture()
        await ingest(monkeypatch,pool,[Socket([image(start),RuntimeError('fixture disconnect')]),Socket([])])
        assert_unavailable(await query(pool,start+2000))
    asyncio.run(run())


def test_new_producer_instance_before_snapshot_cannot_reuse_persisted_old_book(monkeypatch):
    async def run():
        start=int(time.time()*1000)-10000;pool=VolatileSQLFixture()
        await ingest(monkeypatch,pool,[Socket([image(start)])])
        # New collector/Database instances, existing volatile fixture rows.
        # This models visibility across restart, NOT durable storage recovery.
        await ingest(monkeypatch,pool,[Socket([])])
        assert_unavailable(await query(pool,start+2000))
    asyncio.run(run())


def test_positive_control_valid_snapshot_is_current_before_any_loss(monkeypatch):
    async def run():
        start=int(time.time()*1000)-10000;pool=VolatileSQLFixture()
        await ingest(monkeypatch,pool,[Socket([image(start)])])
        result=await query(pool,start+2000)
        assert result['capabilities']['orderbook'] is True
        assert result['features']['spread']==1
    asyncio.run(run())
