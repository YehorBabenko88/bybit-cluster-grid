import asyncio
import asyncpg
from datetime import datetime,timezone
import json
from .config import settings
from .write_queue import BoundedWriteQueue
from .segment_wal import SegmentWAL
from .unified_features import UnifiedFeatureBuilder
from .derived_pipeline import DerivedPipeline
from .resources import NODE_ID
import os
import aiohttp


def ingest_headers():
    from .credential_store import node_credential
    return {
        "X-Grid-Token":settings.grid_shared_token,
        "X-Node-Credential":node_credential(),
        "X-Node-ID":NODE_ID,
    }


class Storage:
    def __init__(self):
        self.pool=None
        self.http=None
        self.replay_task=None
        self.replay_done=asyncio.Event(); self.replay_done.set()
        self.feature_builder=UnifiedFeatureBuilder()
        self.derived=None
        root=os.path.join(os.getenv("ProgramData",os.getcwd()),"BybitClusterGrid","spool")
        self.spool=SegmentWAL(root,max_bytes=int(settings.spool_max_gb*1024**3))
        # WAL checkpoint advances monotonically, therefore commit/ack is deliberately ordered.
        self.write_queue=BoundedWriteQueue(self._save_spooled,maxsize=5000,workers=1)
    async def start(self):
        self.remote=(settings.role!="coordinator")
        if not self.remote:
            self.pool=await asyncpg.create_pool(settings.postgres_dsn,min_size=1,max_size=5)
            self.derived=DerivedPipeline(self.pool)
            await self.derived.start()
        if self.remote:
            self.http=aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
        await self.write_queue.start()
        pending=self.spool.iter_recover()
        self.replay_done.clear()
        self.replay_task=asyncio.create_task(self._replay(pending))
    async def _replay(self,pending):
        try:
            for record_id,row in pending:
                await self.write_queue.put(record_id,row)
        finally:
            self.replay_done.set()

    async def save(self,row):
        await self.replay_done.wait()
        if self.spool.ratio()>=settings.spool_critical_ratio:
            raise BufferError("Grid WAL critical threshold reached; load shedding required")
        record_id=await self.spool.append(row)
        await self.write_queue.put(record_id,row)

    async def close(self,drain_timeout=5):
        if self.replay_task is not None and not self.replay_task.done():
            self.replay_task.cancel()
            await asyncio.gather(self.replay_task,return_exceptions=True)
        self.replay_task=None
        await self.write_queue.close(drain_timeout)
        if self.http is not None:
            await self.http.close(); self.http=None
        if self.pool is not None:
            await self.pool.close(); self.pool=None

    def metrics(self):
        m=self.write_queue.metrics()
        m['spool_bytes']=self.spool.bytes_used()
        m['spool_ratio']=self.spool.ratio()
        return m

    async def _save_spooled(self,record_id,row):
        if self.remote:
            if self.http is None:
                raise RuntimeError("remote ingest session is not started")
            async with self.http.post(settings.coordinator_url+"/ingest/minute",
                json=row,headers=ingest_headers()) as resp:
                if resp.status!=200:
                    raise RuntimeError("CONTROL ingest rejected: "+str(resp.status))
        else:
            await self._save_direct(row)
        await self.spool.ack(record_id)

    async def _save_direct(self,row):
        ts=datetime.fromtimestamp(row["start_ms"]/1000,tz=timezone.utc)
        async with self.pool.acquire() as c:
            async with c.transaction():
                accepted=await c.fetchval("""INSERT INTO candles_1m(symbol,ts,open,high,low,close,buy_volume,sell_volume,delta,trade_count,poc_price,quality_status,quality_reasons)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb)
                ON CONFLICT(symbol,ts) DO UPDATE SET open=EXCLUDED.open,high=EXCLUDED.high,low=EXCLUDED.low,close=EXCLUDED.close,
                buy_volume=EXCLUDED.buy_volume,sell_volume=EXCLUDED.sell_volume,delta=EXCLUDED.delta,trade_count=EXCLUDED.trade_count,poc_price=EXCLUDED.poc_price,quality_status=EXCLUDED.quality_status,quality_reasons=EXCLUDED.quality_reasons
                WHERE EXCLUDED.trade_count > candles_1m.trade_count
                RETURNING TRUE""",
                row["symbol"],ts,row["open"],row["high"],row["low"],row["close"],row["buy_volume"],row["sell_volume"],row["delta"],row["trade_count"],row["poc_price"],row.get("quality_status","UNKNOWN"),json.dumps(row.get("quality_reasons",[])))
                # A smaller/equal late fragment must not overwrite the footprint that
                # belongs to the already accepted, more complete minute. Equal WAL
                # retries still continue below so a prior partial commit can finish
                # feature/derived persistence idempotently.
                regressive=False
                if accepted:
                    await c.executemany("""INSERT INTO footprint_1m(symbol,ts,price,buy_volume,sell_volume,delta,volume,buy_count,sell_count)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
                    ON CONFLICT(symbol,ts,price) DO UPDATE SET buy_volume=EXCLUDED.buy_volume,sell_volume=EXCLUDED.sell_volume,
                    delta=EXCLUDED.delta,volume=EXCLUDED.volume,buy_count=EXCLUDED.buy_count,sell_count=EXCLUDED.sell_count""",
                    [(row["symbol"],ts,x["price"],x["buy_volume"],x["sell_volume"],x["delta"],x["volume"],x["buy_count"],x["sell_count"]) for x in row["levels"]])
                else:
                    current_trade_count=await c.fetchval(
                        "SELECT trade_count FROM candles_1m WHERE symbol=$1 AND ts=$2",
                        row["symbol"],ts,
                    )
                    regressive=(current_trade_count is not None and current_trade_count > row["trade_count"])
        if regressive:
            return
        feature_row=dict(row); feature_row["ts"]=ts
        built=await self.feature_builder.build(self.pool,feature_row)
        await self.feature_builder.persist(self.pool,built)
        await self.derived.on_candle(feature_row,built)
