import asyncio, logging, time
log=logging.getLogger("write_queue")

class BoundedWriteQueue:
    """Bounded in-memory backpressure boundary. Never silently drops queued writes."""
    def __init__(self,writer,maxsize=5000,workers=2):
        self.writer=writer
        self.q=asyncio.Queue(maxsize=maxsize)
        self.workers=max(1,int(workers))
        self.tasks=[]
        self.writes=0
        self.failures=0
        self.total_latency=0.0
        self.started=time.monotonic()

    async def start(self):
        if not self.tasks:
            self.tasks=[asyncio.create_task(self._run(i)) for i in range(self.workers)]

    async def put(self,*args):
        await self.q.put(args)

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
        delay=1
        while True:
            item=await self.q.get()
            try:
                while True:
                    started=time.monotonic()
                    try:
                        await self.writer(*item)
                        self.total_latency+=time.monotonic()-started
                        self.writes+=1
                        delay=1
                        break
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        self.failures+=1
                        log.exception("database write failed; retrying",extra={"event":"db_retry","delay":delay})
                        await asyncio.sleep(delay)
                        delay=min(30,delay*2)
            finally:
                self.q.task_done()

# Compatibility alias; despite the historic name this queue is memory-bounded, not disk durable.
DurableWriteQueue=BoundedWriteQueue
