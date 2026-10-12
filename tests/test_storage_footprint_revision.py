import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from grid.storage import Storage


class FakeConnection:
    def __init__(self):
        self.statements = []
        self.count = None

    @asynccontextmanager
    async def transaction(self):
        yield self

    async def fetchval(self, sql, *args):
        self.statements.append(("fetchval", sql, args))
        if sql.lstrip().startswith("INSERT INTO candles_1m"):
            return self.count
        return 0

    async def execute(self, sql, *args):
        self.statements.append(("execute", sql, args))

    async def executemany(self, sql, args):
        self.statements.append(("executemany", sql, args))


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def test_accepted_revision_replaces_stale_footprint_levels_in_transaction():
    async def run():
        connection = FakeConnection()
        connection.count = True
        storage = Storage.__new__(Storage)
        storage.pool = FakePool(connection)
        storage.feature_builder = type("Builder", (), {
            "build": AsyncMock(return_value={}),
            "persist": AsyncMock(),
        })()
        storage.scientific = None
        storage.derived = type("Derived", (), {"on_candle": AsyncMock()})()
        row = dict(
            symbol="BTCUSDT", start_ms=0, open=100, high=101, low=99,
            close=100, buy_volume=2, sell_volume=1, delta=1,
            trade_count=3, poc_price=100, levels=[
                dict(price=100, buy_volume=2, sell_volume=1, delta=1,
                     volume=3, buy_count=2, sell_count=1)
            ],
        )
        with patch("grid.storage.SegmentWAL"):
            await storage._save_direct(row)
        sql_order = [sql for _, sql, _ in connection.statements]
        deletes = [i for i, sql in enumerate(sql_order)
                   if "DELETE FROM footprint_1m" in sql]
        inserts = [i for i, sql in enumerate(sql_order)
                   if "INSERT INTO footprint_1m" in sql]
        assert len(deletes) == 1
        assert len(inserts) == 1
        assert deletes[0] < inserts[0]
        assert connection.statements[deletes[0]][2][0] == "BTCUSDT"
        assert connection.statements[deletes[0]][2][1] == datetime.fromtimestamp(
            0, tz=timezone.utc
        )

    asyncio.run(run())


def test_rejected_older_revision_does_not_delete_footprint():
    async def run():
        connection = FakeConnection()
        connection.count = None
        storage = Storage.__new__(Storage)
        storage.pool = FakePool(connection)
        storage.feature_builder = type("Builder", (), {
            "build": AsyncMock(return_value={}),
            "persist": AsyncMock(),
        })()
        storage.scientific = None
        storage.derived = type("Derived", (), {"on_candle": AsyncMock()})()
        row = dict(
            symbol="BTCUSDT", start_ms=0, open=100, high=100, low=100,
            close=100, buy_volume=1, sell_volume=0, delta=1,
            trade_count=1, poc_price=100, levels=[],
        )
        async def old_count(sql, *args):
            connection.statements.append(("fetchval", sql, args))
            if sql.lstrip().startswith("INSERT INTO candles_1m"):
                return None
            return 2
        connection.fetchval = old_count
        with patch("grid.storage.SegmentWAL"):
            await storage._save_direct(row)
        assert not any(
            "DELETE FROM footprint_1m" in sql
            for _, sql, _ in connection.statements
        )
        storage.feature_builder.build.assert_not_awaited()

    asyncio.run(run())
