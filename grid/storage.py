import asyncpg
from datetime import datetime,timezone
from .config import settings
from .write_queue import BoundedWriteQueue

class Storage:
    def __init__(self):
        self.pool=None
        self.write_queue=BoundedWriteQueue(self._save_direct,maxsize=5000,workers=2)
    async def start(self):
        self.pool=await asyncpg.create_pool(settings.postgres_dsn,min_size=1,max_size=5)
        await self.write_queue.start()
    async def save(self,row):
        await self.write_queue.put(row)

    def metrics(self):
        return self.write_queue.metrics()

    async def _save_direct(self,row):
        ts=datetime.fromtimestamp(row["start_ms"]/1000,tz=timezone.utc)
        async with self.pool.acquire() as c:
            async with c.transaction():
                await c.execute("""INSERT INTO candles_1m(symbol,ts,open,high,low,close,buy_volume,sell_volume,delta,trade_count,poc_price)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                ON CONFLICT(symbol,ts) DO UPDATE SET open=EXCLUDED.open,high=EXCLUDED.high,low=EXCLUDED.low,close=EXCLUDED.close,
                buy_volume=EXCLUDED.buy_volume,sell_volume=EXCLUDED.sell_volume,delta=EXCLUDED.delta,trade_count=EXCLUDED.trade_count,poc_price=EXCLUDED.poc_price""",
                row["symbol"],ts,row["open"],row["high"],row["low"],row["close"],row["buy_volume"],row["sell_volume"],row["delta"],row["trade_count"],row["poc_price"])
                await c.executemany("""INSERT INTO footprint_1m(symbol,ts,price,buy_volume,sell_volume,delta,volume,buy_count,sell_count)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT(symbol,ts,price) DO UPDATE SET buy_volume=EXCLUDED.buy_volume,sell_volume=EXCLUDED.sell_volume,
                delta=EXCLUDED.delta,volume=EXCLUDED.volume,buy_count=EXCLUDED.buy_count,sell_count=EXCLUDED.sell_count""",
                [(row["symbol"],ts,x["price"],x["buy_volume"],x["sell_volume"],x["delta"],x["volume"],x["buy_count"],x["sell_count"]) for x in row["levels"]])
