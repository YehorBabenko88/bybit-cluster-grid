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
        # Reconciliation and reservation cleanup are one transaction. A running
        # job with a valid lease keeps its reservation; terminal/requeued jobs
        # cannot retain capacity, even if the old reservation expiry is future.
        async with self.pool.acquire() as c:
            async with c.transaction():
                await c.execute("""UPDATE ml_jobs SET status='queued',lease_owner=NULL,lease_until=NULL,
                  not_before=clock_timestamp()+interval '5 seconds',
                  error=COALESCE(error,'recovered after expired lease')
                  WHERE status IN ('running','assigned') AND lease_until<clock_timestamp()
                    AND attempts<max_attempts""")
                await c.execute("""UPDATE ml_jobs SET status='failed',finished_at=clock_timestamp(),
                  lease_until=NULL,error=COALESCE(error,'max attempts exhausted after expired lease')
                  WHERE status IN ('running','assigned') AND lease_until<clock_timestamp()
                    AND attempts>=max_attempts""")
                await c.execute("""DELETE FROM ml_resource_reservations r
                  WHERE r.expires_at<clock_timestamp() OR NOT EXISTS (
                    SELECT 1 FROM ml_jobs j WHERE j.id=r.job_id
                    AND j.status IN ('assigned','running')
                    AND j.lease_until>=clock_timestamp())""")
        self.state=OBSERVING

    async def tick(self):
        leader=await acquire_service_lease(self.pool,"ml-orchestrator-leader",self.owner,30,
                                           {"state":self.state})
        if not leader:
            self.state=OBSERVING; return {"leader":False}
        # Only the current leader may reconcile jobs. Repeating this on each
        # tick also recovers leases that expire long after process startup.
        await self.recover()
        h=await self.health_reader()
        workers=self.concurrency.update(float(h.get("cpu_pct",100)),float(h.get("ram_pct",100)),
          float(h.get("db_latency_ms",9999)),float(h.get("db_queue_ratio",1)),
          float(h.get("disk_free_gb",0)))
        if workers<=0:
            self.state=DEGRADED
            return {"leader":True,"workers":0,"health":h}
        # Recovery and health probes can outlast the leadership TTL. Never
        # dispatch on an earlier leadership decision without reacquiring it.
        leader=await acquire_service_lease(self.pool,"ml-orchestrator-leader",self.owner,30,
                                           {"state":self.state})
        if not leader:
            self.state=OBSERVING
            return {"leader":False,"workers":0,"health":h}
        self.state=DISPATCHING
        dispatched=await self.dispatcher(workers,h,leader_owner=self.owner)
        self.state=OBSERVING
        return {"leader":True,"workers":workers,"dispatched":dispatched,"health":h}

    async def run(self):
        while not self.stop_event.is_set():
            try: await self.tick()
            except Exception:
                self.state=DEGRADED; log.exception("orchestrator tick failed")
            try: await asyncio.wait_for(self.stop_event.wait(),timeout=self.interval)
            except asyncio.TimeoutError: pass
        self.state=DRAINING

    def stop(self): self.stop_event.set()
