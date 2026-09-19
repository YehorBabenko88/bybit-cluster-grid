import json
from .level_generator import HistoricalLevelGenerator
from .historical_levels import HistoricalLevelTracker

class LevelPipeline:
    """Causal HTF level generation, persistence and event classification."""
    def __init__(self,pool,generator=None,tracker=None):
        self.pool=pool
        self.generator=generator or HistoricalLevelGenerator()
        self.tracker=tracker or HistoricalLevelTracker()

    async def restore_active(self,symbol=None):
        sql="""SELECT symbol,timeframe,level_kind,source_ts,price,available_ts,test_count
               FROM historical_levels WHERE active=true"""
        args=[]
        if symbol:
            sql+=" AND symbol=$1"; args=[symbol]
        rows=await self.pool.fetch(sql,*args)
        for r in rows:
            side="RESISTANCE" if r["level_kind"]=="HIGH" else "SUPPORT"
            x=self.tracker.register(r["symbol"],r["timeframe"],r["level_kind"],r["source_ts"],r["price"],side)
            x.tests=int(r["test_count"] or 0)
        return len(rows)

    async def on_candle(self,row,built_features):
        symbol=row["symbol"]; ts=row["ts"]
        for lv in self.generator.on_candle(row):
            await self.pool.execute("""INSERT INTO historical_levels
                (symbol,timeframe,level_kind,source_ts,price,available_ts,active)
                VALUES($1,$2,$3,$4,$5,$6,true)
                ON CONFLICT(symbol,timeframe,level_kind,source_ts) DO UPDATE
                SET price=EXCLUDED.price,available_ts=EXCLUDED.available_ts""",
                lv.symbol,lv.timeframe,lv.kind,lv.source_ts,lv.price,lv.available_ts)
            side="RESISTANCE" if lv.kind=="HIGH" else "SUPPORT"
            self.tracker.register(lv.symbol,lv.timeframe,lv.kind,lv.source_ts,lv.price,side)

        features=built_features.get("features",built_features)
        events=self.tracker.observe(symbol,ts,row["open"],row["high"],row["low"],row["close"],features)
        for typ,level,detail in events:
            direction=detail.get("direction")
            pre=detail.get("pre_features",level.pre_features)
            event_features=detail.get("event_features",features)
            outcome={k:v for k,v in detail.items() if k not in ("pre_features","event_features","direction")}
            await self.pool.execute("""INSERT INTO level_events
                (symbol,timeframe,level_kind,source_ts,level_price,event_ts,event_type,direction,
                 pre_features,event_features,outcome)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10::jsonb,$11::jsonb)
                ON CONFLICT(symbol,timeframe,level_kind,source_ts,event_ts,event_type) DO NOTHING""",
                symbol,level.timeframe,level.kind,level.source_ts,level.price,ts,typ,direction,
                json.dumps(pre,default=str),json.dumps(event_features,default=str),json.dumps(outcome,default=str))
            if typ=="FIRST_CROSS":
                await self.pool.execute("""UPDATE historical_levels SET first_cross_ts=$1,test_count=test_count+1
                    WHERE symbol=$2 AND timeframe=$3 AND level_kind=$4 AND source_ts=$5""",
                    ts,symbol,level.timeframe,level.kind,level.source_ts)
            elif typ=="ACCEPTED_BREAK":
                await self.pool.execute("""UPDATE historical_levels SET active=false
                    WHERE symbol=$1 AND timeframe=$2 AND level_kind=$3 AND source_ts=$4""",
                    symbol,level.timeframe,level.kind,level.source_ts)
        return events
