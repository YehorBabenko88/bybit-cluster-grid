"""Exercise the real minute/feature/derived call path inside one transaction."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest

from grid import coordinator
from grid.storage import Storage
from grid.fenced_ingest import ConnectionPool


def test_minute_analytical_state_is_not_published_on_rollback(monkeypatch):
    async def run():
        class Builder:
            def __init__(self):self.count=0
            async def build(self,pool,row):self.count+=1;return {}
            async def persist(self,pool,built):await pool.execute('feature-write')
        class Derived:
            def __init__(self,pool):self.pool=pool;self.levels=SimpleNamespace(pool=pool);self.count=0
            async def on_candle(self,row,built):
                self.count+=1
                await self.pool.execute('derived-write')
        storage=Storage.__new__(Storage)
        storage.pool=object();storage.feature_builder=Builder();storage.derived=Derived(storage.pool);storage.scientific=None
        rows=[]
        class Connection:
            @asynccontextmanager
            async def transaction(self):yield
            async def fetchval(self,sql,*args):return True
            async def execute(self,sql,*args):rows.append(sql)
            async def executemany(self,sql,*args):rows.append(sql)
        async def failing_gate(pool,node,kind,payload,persist):
            await persist(ConnectionPool(Connection()),payload)
            raise ConnectionError('commit lost')
        monkeypatch.setattr(coordinator,'ingest_storage',storage)
        monkeypatch.setattr(coordinator,'db',SimpleNamespace(pool=storage.pool))
        monkeypatch.setattr(coordinator,'ingest_lock',asyncio.Lock())
        monkeypatch.setattr(coordinator,'authenticate_agent',AsyncMock(return_value=True))
        monkeypatch.setattr(coordinator,'runtime_state',AsyncMock(return_value={'state':'ACTIVE'}))
        monkeypatch.setattr(coordinator,'control_disk_state',lambda:{'state':'NORMAL'})
        monkeypatch.setattr(coordinator,'ingest_owned',failing_gate)
        payload={'symbol':'BTCUSDT','start_ms':0,'open':100,'high':101,'low':99,'close':100,
                 'buy_volume':1,'sell_volume':0,'delta':1,'trade_count':1,'poc_price':100,'levels':[]}
        request=SimpleNamespace(json=AsyncMock(return_value=payload))
        with pytest.raises(ConnectionError):await coordinator.ingest_minute(request,x_node_id='worker',x_node_credential='test')
        assert storage.feature_builder.count==0 and storage.derived.count==0
        assert 'feature-write' in rows and 'derived-write' in rows
    asyncio.run(run())
