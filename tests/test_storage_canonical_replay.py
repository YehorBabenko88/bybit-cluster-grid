import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from grid.storage import Storage


class Connection:
    def __init__(self):
        self.canonical = dict(open=100, high=105, low=95, close=104,
                              buy_volume=10, sell_volume=2, delta=8,
                              trade_count=12, poc_price=103,
                              quality_status="GOOD", quality_reasons=[])

    @asynccontextmanager
    async def transaction(self):
        yield self

    async def fetchval(self, sql, *args):
        if "INSERT INTO candles_1m" in sql:
            return None
        return 12

    async def fetchrow(self, sql, *args):
        return self.canonical


class Pool:
    def __init__(self):
        self.connection = Connection()

    @asynccontextmanager
    async def acquire(self):
        yield self.connection

    async def fetchrow(self, sql, *args):
        return await self.connection.fetchrow(sql, *args)


def test_equal_count_replay_uses_canonical_candle_for_features():
    async def run():
        storage = Storage.__new__(Storage)
        storage.pool = Pool()
        storage.feature_builder = type("Builder", (), {
            "build": AsyncMock(return_value={"features": {}}),
            "persist": AsyncMock(),
        })()
        storage.scientific = None
        storage.derived = type("Derived", (), {"on_candle": AsyncMock()})()
        incoming = dict(symbol="BTCUSDT", start_ms=0, open=1, high=2, low=1,
                        close=1, buy_volume=1, sell_volume=0, delta=1,
                        trade_count=12, poc_price=1, levels=[])
        await storage._save_direct(incoming)
        passed = storage.feature_builder.build.await_args.args[1]
        assert passed["close"] == 104
        assert passed["high"] == 105
        assert passed["poc_price"] == 103

    asyncio.run(run())
