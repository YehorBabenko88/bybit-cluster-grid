import asyncio,logging
log=logging.getLogger("ml_observer")

class DatabaseObserver:
    """LISTEN/NOTIFY is only a wake-up hint; reconciliation query is authoritative."""
    def __init__(self,pool,reconcile,channel="grid_ml_events",poll_seconds=30):
        self.pool=pool; self.reconcile=reconcile; self.channel=channel
        self.poll_seconds=int(poll_seconds); self.wakeup=asyncio.Event(); self.conn=None

    async def start(self):
        self.conn=await self.pool.acquire()
        await self.conn.add_listener(self.channel,self._notify)

    def _notify(self,*_):
        self.wakeup.set()

    async def run(self):
        while True:
            # Clear before reconciliation so a notification arriving while it
            # runs remains latched for the next pass rather than getting lost.
            self.wakeup.clear()
            try:
                await self.reconcile()
            except Exception:
                log.exception("ml observer reconciliation failed")
            try:
                await asyncio.wait_for(self.wakeup.wait(),timeout=self.poll_seconds)
            except asyncio.TimeoutError:
                pass

    async def close(self):
        if self.conn:
            await self.conn.remove_listener(self.channel,self._notify)
            await self.pool.release(self.conn); self.conn=None

async def notify_ml_event(conn,kind,identifier=""):
    # Payload is deliberately tiny; consumers re-read authoritative rows from DB.
    payload=(kind+":"+str(identifier))[:7000]
    await conn.execute("SELECT pg_notify('grid_ml_events',$1)",payload)
