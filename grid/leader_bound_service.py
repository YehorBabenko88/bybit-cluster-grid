class LeaderBoundService:
    """Starts a singleton service only while this node owns the current leader epoch."""
    def __init__(self,start,stop):
        self.start=start; self.stop=stop; self.running=False; self.epoch=None; self.cleanup_pending=False

    async def gain(self,epoch):
        if self.running:
            if self.cleanup_pending:
                raise RuntimeError("prior service cleanup incomplete")
            if self.epoch != epoch:
                raise RuntimeError("leader epoch changed without stopping prior service")
            return
        # Start may create tasks before raising: stop those tasks before retry.
        self.epoch=epoch
        self.running=True
        try:
            await self.start(epoch)
        except BaseException:
            self.cleanup_pending=True
            await self.lose()
            raise

    async def lose(self):
        if not self.running:
            self.epoch=None
            return
        # Keep the running marker on stop failure so the next attempt retries
        # shutdown rather than starting a second singleton.
        await self.stop()
        self.running=False
        self.epoch=None
        self.cleanup_pending=False
