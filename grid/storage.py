import asyncpg
from datetime import datetime,timezone
import json
from .config import settings
from .write_queue import BoundedWriteQueue
from .segment_wal import SegmentWAL
from .unified_features import UnifiedFeatureBuilder
from .derived_pipeline import DerivedPipeline
import os

class Storage:
    def __init__(self):
        self.pool=None
        self.feature_builder=UnifiedFeatureBuilder()
        self.derived=None
        root=os.path.join(os.getenv("ProgramData",os.getcwd()),"BybitClusterGrid","spool")
        self.spool=SegmentWAL(root,max_bytes=int(settings.spool_max_gb*1024**3))
        # WAL checkpoint advances monotonically, therefore commit/ack is deliberately ordered.
        self.write_queue=BoundedWriteQueue(self._save_spooled,maxsize=5000,workers=1)
    async def start(self):
        self.pool=await asyncpg.create_pool(settings.postgres_dsn,min_size=1,max_size=5)
        await self.write_queue.start()
        self.derived=DerivedPipeline(self.pool)
        await self.derived.start()
        for record_id,row in self.spool.recover():
            await self.write_queue.put(record_id,row)
    async def save(self,row):
        if self.spool.ratio()>=settings.spool_critical_ratio:
            raise BufferError("Grid WAL critical threshold reached; load shedding required")
        record_id=await self.spool.append(row)
        await self.write_queue.put(record_id,row)

    def metrics(self):
        m=self.write_queue.metrics()
        m['spool_bytes']=self.spool.bytes_used()
        m['spool_ratio']=self.spool.ratio()
        return m

    async def _save_spooled(self,record_id,row):
        await self._save_direct(row)
        await self.spool.ack(record_id)

    async def _save_direct(self,row):
        ts=datetime.fromtimestamp(row["start_ms"]/1000,tz=timezone.utc)
        async with self.pool.acquire() as c:
            async with c.transaction():
                await c.execute("""INSERT INTO candles_1m(symbol,ts,open,high,low,close,buy_volume,sell_volume,delta,trade_count,poc_price,quality_status,quality_reasons)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb)
                ON CONFLICT(symbol,ts) DO UPDATE SET open=EXCLUDED.open,high=EXCLUDED.high,low=EXCLUDED.low,close=EXCLUDED.close,
                buy_volume=EXCLUDED.buy_volume,sell_volume=EXCLUDED.sell_volume,delta=EXCLUDED.delta,trade_count=EXCLUDED.trade_count,poc_price=EXCLUDED.poc_price,quality_status=EXCLUDED.quality_status,quality_reasons=EXCLUDED.quality_reasons""",
                row["symbol"],ts,row["open"],row["high"],row["low"],row["close"],row["buy_volume"],row["sell_volume"],row["delta"],row["trade_count"],row["poc_price"],row.get("quality_status","UNKNOWN"),json.dumps(row.get("quality_reasons",[])))
                await c.executemany("""INSERT INTO footprint_1m(symbol,ts,price,buy_volume,sell_volume,delta,volume,buy_count,sell_count)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT(symbol,ts,price) DO UPDATE SET buy_volume=EXCLUDED.buy_volume,sell_volume=EXCLUDED.sell_volume,
                delta=EXCLUDED.delta,volume=EXCLUDED.volume,buy_count=EXCLUDED.buy_count,sell_count=EXCLUDED.sell_count""",
                [(row["symbol"],ts,x["price"],x["buy_volume"],x["sell_volume"],x["delta"],x["volume"],x["buy_count"],x["sell_count"]) for x in row["levels"]])
        feature_row=dict(row); feature_row["ts"]=ts
        built=await self.feature_builder.build(self.pool,feature_row)
        await self.feature_builder.persist(self.pool,built)
        await self.derived.on_candle(feature_row,built)
