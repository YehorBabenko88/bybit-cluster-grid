from datetime import timedelta
from .observer_checkpoint import ObserverCheckpoint

class ObserverRecovery:
    """Replays closed persisted minutes after restart before live observation resumes."""
    def __init__(self,pool,pipeline):
        self.pool=pool; self.pipeline=pipeline
        self.checkpoint=ObserverCheckpoint(pool)

    async def catch_up(self,symbol,batch=1000):
        last,_=await self.checkpoint.load(symbol)
        processed=0; gaps=0; prev=last
        while True:
            rows=await self.pool.fetch("""SELECT c.*,m.eligible,m.quality_status AS feature_quality,
                    m.regime,m.regime_score,m.features,m.capabilities
                FROM candles_1m c LEFT JOIN market_features_1m m
                  ON m.symbol=c.symbol AND m.ts=c.ts
                WHERE c.symbol=$1 AND ($2::timestamptz IS NULL OR c.ts>$2)
                ORDER BY c.ts ASC LIMIT $3""",symbol,last,batch)
            if not rows: break
            for r in rows:
                row=dict(r); ts=row["ts"]
                gap=False
                if prev is not None and ts-prev>timedelta(minutes=1):
                    gaps+=1; gap=True
                features=dict(row.get("features") or {})
                capabilities=dict(row.get("capabilities") or {})
                built={"features":features,"capabilities":capabilities,
                       "quality_status":row.get("feature_quality") or row.get("quality_status") or "UNKNOWN",
                       "eligible":bool(row.get("eligible"))}
                if gap:
                    built["quality_status"]="DEGRADED"
                    built["eligible"]=False
                    built["features"]["observer_gap_before"]=True
                await self.pipeline.on_candle(row,built)
                await self.checkpoint.save(symbol,ts,{"gap_before":gap})
                last=prev=ts; processed+=1
            if len(rows)<batch: break
        return {"processed":processed,"gaps":gaps,"last_ts":last}
