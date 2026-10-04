import asyncio, logging, time
log=logging.getLogger("write_queue")

class BoundedWriteQueue:
    """Bounded in-memory backpressure boundary. Never silently drops queued writes."""
    def __init__(self,writer,maxsize=5000,workers=2,retry_base_seconds=1,retry_max_seconds=30):
        self.writer=writer
        self.q=asyncio.Queue(maxsize=maxsize)
        self.workers=max(1,int(workers))
        self.tasks=[]
        self.writes=0
        self.failures=0
        self.total_latency=0.0
        self.started=time.monotonic()
        self.retry_base_seconds=float(retry_base_seconds)
        self.retry_max_seconds=float(retry_max_seconds)

    async def start(self):
        if not self.tasks:
            self.tasks=[asyncio.create_task(self._run(i)) for i in range(self.workers)]

    async def put(self,*args):
        await self.q.put(args)

    async def close(self,drain_timeout=5):
        # Try to flush in-memory items first. If CONTROL/DB is unavailable,
        # bounded shutdown cancels retry loops; every accepted item remains in
        # the durable WAL and is replayed on the next start.
        if not self.tasks:
            return
        try:
            await asyncio.wait_for(self.q.join(),timeout=max(0.0,float(drain_timeout)))
        except asyncio.TimeoutError:
            log.warning("write queue drain timed out; durable WAL will replay pending records",
                        extra={"event":"write_queue_drain_timeout","queue_depth":self.q.qsize()})
        tasks=list(self.tasks); self.tasks=[]
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)

    def metrics(self):
        elapsed=max(.001,time.monotonic()-self.started)
        return {
            "queue_depth":self.q.qsize(),
            "queue_capacity":self.q.maxsize,
            "queue_ratio":self.q.qsize()/max(1,self.q.maxsize),
            "writes_per_sec":self.writes/elapsed,
            "write_failures":self.failures,
            "avg_write_latency_ms":(self.total_latency/max(1,self.writes))*1000,
        }

    async def _run(self,worker_id):
        delay=self.retry_base_seconds
        while True:
            item=await self.q.get()
            try:
                while True:
                    started=time.monotonic()
                    try:
                        await self.writer(*item)
                        self.total_latency+=time.monotonic()-started
                        self.writes+=1
                        delay=self.retry_base_seconds
                        break
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        self.failures+=1
                        log.exception("database write failed; retrying",extra={"event":"db_retry","delay":delay})
                        await asyncio.sleep(delay)
                        delay=min(self.retry_max_seconds,delay*2)
            finally:
                self.q.task_done()

# Compatibility alias; despite the historic name this queue is memory-bounded, not disk durable.
DurableWriteQueue=BoundedWriteQueue
