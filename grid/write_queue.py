import asyncio, logging
log=logging.getLogger("write_queue")

class DurableWriteQueue:
    """Backpressure boundary between market streams and PostgreSQL."""
    def __init__(self, writer, maxsize=100000):
        self.writer=writer
        self.q=asyncio.Queue(maxsize=maxsize)
        self.task=None
    async def start(self):
        self.task=asyncio.create_task(self._run())
    async def put(self,*args):
        # Do not silently discard market data. Apply backpressure if DB is behind.
        await self.q.put(args)
    async def _run(self):
        delay=1
        while True:
            item=await self.q.get()
            while True:
                try:
                    await self.writer(*item)
                    delay=1
                    break
                except asyncio.CancelledError: raise
                except Exception:
                    log.exception("database write failed; retrying",extra={"event":"db_retry","delay":delay})
                    await asyncio.sleep(delay)
                    delay=min(30,delay*2)
            self.q.task_done()
