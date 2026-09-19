from __future__ import annotations
import json
from .level_pipeline import LevelPipeline
from .level_generator import _period
from .poc_lifecycle import PocLifecycleTracker,PocLevel
from .control_state import set_consumer_watermark
from .retention_v2 import register_consumer

class DerivedPipeline:
    """Continue imported history with live causal features, HTF levels and POC lifecycle."""
    def __init__(self,pool,poc_max_open=5000):
        self.pool=pool
        self.levels=LevelPipeline(pool)
        self.poc=PocLifecycleTracker(max_open=int(poc_max_open))
        self.warmed=set()
        self.started=False

    async def start(self):
        if self.started:return
        await self.levels.restore_active()
        rows=await self.pool.fetch("""WITH ranked AS (
          SELECT *,row_number() OVER(PARTITION BY symbol ORDER BY source_ts DESC) rn
          FROM poc_lifecycle WHERE status<>'ACCEPTED')
          SELECT * FROM ranked WHERE rn<=5000 ORDER BY symbol,source_ts""")
        for r in rows:
            x=PocLevel(r["source_ts"],float(r["poc_price"]),float(r["source_close"] or r["poc_price"]))
            x.status=r["status"];x.first_touch_ts=r["first_touch_ts"];x.first_touch_minutes=r["first_touch_minutes"]
            x.first_touch_kind=r["first_touch_kind"];x.cross_ts=r["cross_ts"];x.acceptance_ts=r["acceptance_ts"]
            x.touch_count=int(r["touch_count"] or 0);x.max_distance_pct=float(r["max_distance_pct"] or 0)
            self.poc.open.setdefault(r["symbol"],[]).append(x)
        for ds,consumer in (
            ("candles_1m","unified_features"),("candles_1m","level_pipeline"),
            ("candles_1m","poc_lifecycle"),("footprint_1m","unified_features"),
            ("footprint_1m","poc_lifecycle")):
            await register_consumer(self.pool,ds,consumer,required=True,active=True)
        self.started=True

    async def _warm_generator(self,symbol,ts):
        if symbol in self.warmed:return
        for tf in self.levels.generator.timeframes:
            start,_=_period(ts,tf)
            row=await self.pool.fetchrow("""WITH u AS (
              SELECT ts,open,high,low,close,0 pri FROM ohlcv_1m
                WHERE symbol=$1 AND ts>=$2 AND ts<$3
              UNION ALL
              SELECT ts,open,high,low,close,1 pri FROM candles_1m
                WHERE symbol=$1 AND ts>=$2 AND ts<$3
            ), d AS (
              SELECT DISTINCT ON(ts) ts,open,high,low,close FROM u ORDER BY ts,pri DESC
            )
            SELECT min(ts) min_ts,max(ts) max_ts,max(high) high,min(low) low,
              (array_agg(open ORDER BY ts))[1] open,
              (array_agg(close ORDER BY ts DESC))[1] close
            FROM d""",symbol,start,ts)
            if row and row["min_ts"] is not None:
                _,end=_period(ts,tf)
                self.levels.generator.current[(symbol,tf)]={
                    "start":start,"end":end,"high":float(row["high"]),"low":float(row["low"]),
                    "open":float(row["open"]),"close":float(row["close"])}
        self.warmed.add(symbol)

    async def _persist_poc(self,symbol,x,ts):
        await self.pool.execute("""UPDATE poc_lifecycle SET status=$3,first_touch_ts=$4,
          first_touch_minutes=$5,first_touch_kind=$6,cross_ts=$7,acceptance_ts=$8,
          touch_count=$9,max_distance_pct=$10,last_checked_ts=$11
          WHERE symbol=$1 AND source_ts=$2""",
          symbol,x.source_ts,x.status,x.first_touch_ts,x.first_touch_minutes,x.first_touch_kind,
          x.cross_ts,x.acceptance_ts,int(x.touch_count),float(x.max_distance_pct),ts)

    async def on_candle(self,row,built):
        if not self.started:await self.start()
        symbol=row["symbol"];ts=row["ts"]
        await self._warm_generator(symbol,ts)
        level_events=await self.levels.on_candle(row,built)

        changed=self.poc.observe(symbol,ts,row["open"],row["high"],row["low"],row["close"])
        seen=set()
        for _,x in changed:
            key=x.source_ts
            if key in seen:continue
            seen.add(key);await self._persist_poc(symbol,x,ts)

        new=self.poc.register(symbol,ts,row.get("poc_price"),row["close"])
        if new is not None:
            features=built.get("features",built)
            await self.pool.execute("""INSERT INTO poc_lifecycle
              (symbol,source_ts,poc_price,source_close,source_regime,source_features,status,last_checked_ts)
              VALUES($1,$2,$3,$4,$5,$6::jsonb,'NAKED',$2)
              ON CONFLICT(symbol,source_ts) DO UPDATE SET poc_price=EXCLUDED.poc_price,
              source_close=EXCLUDED.source_close,source_regime=EXCLUDED.source_regime,
              source_features=EXCLUDED.source_features""",
              symbol,ts,row["poc_price"],row["close"],built.get("regime"),
              json.dumps(features,default=str))

        for ds,consumer in (
            ("candles_1m","unified_features"),("candles_1m","level_pipeline"),
            ("candles_1m","poc_lifecycle"),("footprint_1m","unified_features"),
            ("footprint_1m","poc_lifecycle")):
            await set_consumer_watermark(self.pool,ds,consumer,symbol,ts,required=True)
        return {"level_events":len(level_events),"poc_changes":len(changed),"poc_registered":new is not None}
