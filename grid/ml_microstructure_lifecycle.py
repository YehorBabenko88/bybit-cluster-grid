import asyncio,logging
from datetime import datetime,timezone
from .ml_microstructure_samples import ContinuousMicrostructureSamples

log=logging.getLogger("micro_ml_lifecycle")


def parse_horizons(value):
    if isinstance(value,(tuple,list)):
        return tuple(sorted({int(x) for x in value if int(x)>0}))
    out=set()
    for item in str(value or "").split(","):
        item=item.strip()
        if item:
            n=int(item)
            if n>0: out.add(n)
    return tuple(sorted(out))


class MicrostructureMLLifecycle:
    """Restart-safe CONTROL loop for freezing and maturing live ML samples."""
    def __init__(self,pool,horizons=(60,300,900),interval_seconds=60):
        self.pool=pool
        self.samples=ContinuousMicrostructureSamples(pool,parse_horizons(horizons))
        self.interval=max(1,int(interval_seconds))
        self.stop_event=asyncio.Event()

    async def tick(self,through_ts=None):
        through_ts=through_ts or datetime.now(timezone.utc)
        symbols=await self.pool.fetch("""SELECT DISTINCT symbol FROM microstructure_samples
          WHERE known_at<=$1 ORDER BY symbol""",through_ts)
        materialized=labelled=0
        for row in symbols:
            symbol=row["symbol"]
            materialized+=await self.samples.materialize(symbol,through_ts)
            labelled+=await self.samples.label_ready(symbol,through_ts)
        counts=await self.pool.fetchrow("""SELECT
          count(*) FILTER (WHERE target_ready=true AND quality_status='GOOD') AS ready,
          count(*) FILTER (WHERE target_ready=false) AS pending,
          count(*) FILTER (WHERE quality_status<>'GOOD') AS degraded
          FROM microstructure_ml_samples""")
        return {"symbols":len(symbols),"materialized":materialized,"labelled":labelled,
                "ready":int(counts["ready"] or 0),"pending":int(counts["pending"] or 0),
                "degraded":int(counts["degraded"] or 0)}

    async def run(self):
        while not self.stop_event.is_set():
            try:
                stats=await self.tick()
                log.info("microstructure ML lifecycle",extra={"event":"micro_ml_lifecycle",
                         "component":str(stats)})
            except Exception:
                log.exception("microstructure ML lifecycle failed",
                              extra={"event":"micro_ml_lifecycle_failed"})
            try:
                await asyncio.wait_for(self.stop_event.wait(),timeout=self.interval)
            except asyncio.TimeoutError:
                pass

    def stop(self):
        self.stop_event.set()
