import asyncio,logging,socket,uuid
from .ml_concurrency import acquire_service_lease
from .ml_adaptive_load import AdaptiveConcurrency
log=logging.getLogger("ml_orchestrator")

STARTING="STARTING"; RECOVERING="RECOVERING"; OBSERVING="OBSERVING"
DISPATCHING="DISPATCHING"; DEGRADED="DEGRADED"; DRAINING="DRAINING"

class MLOrchestratorService:
    """Control loop only. Heavy compute belongs to leased compute workers."""
    def __init__(self,pool,dispatcher,health_reader,interval=5):
        self.pool=pool; self.dispatcher=dispatcher; self.health_reader=health_reader
        self.interval=float(interval); self.owner=f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self.state=STARTING; self.stop_event=asyncio.Event()
        self.concurrency=AdaptiveConcurrency(min_workers=0,max_workers=4)

    async def recover(self):
        self.state=RECOVERING
        # Expired jobs become claimable by workers; live leases are never stolen.
        await self.pool.execute("""UPDATE ml_jobs SET status='queued',lease_owner=NULL,lease_until=NULL,
          error=COALESCE(error,'recovered after expired lease')
          WHERE status IN ('running','assigned') AND lease_until<now()""")
        self.state=OBSERVING

    async def tick(self):
        leader=await acquire_service_lease(self.pool,"ml-orchestrator-leader",self.owner,30,
                                           {"state":self.state})
        if not leader:
            self.state=OBSERVING; return {"leader":False}
        h=await self.health_reader()
        workers=self.concurrency.update(float(h.get("cpu_pct",100)),float(h.get("ram_pct",100)),
          float(h.get("db_latency_ms",9999)),float(h.get("db_queue_ratio",1)),
          float(h.get("disk_free_gb",0)))
        if workers<=0:
            self.state=DEGRADED
            return {"leader":True,"workers":0,"health":h}
        self.state=DISPATCHING
        dispatched=await self.dispatcher(workers,h)
        self.state=OBSERVING
        return {"leader":True,"workers":workers,"dispatched":dispatched,"health":h}

    async def run(self):
        await self.recover()
        while not self.stop_event.is_set():
            try: await self.tick()
            except Exception:
                self.state=DEGRADED; log.exception("orchestrator tick failed")
            try: await asyncio.wait_for(self.stop_event.wait(),timeout=self.interval)
            except asyncio.TimeoutError: pass
        self.state=DRAINING

    def stop(self): self.stop_event.set()
