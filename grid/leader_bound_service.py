class LeaderBoundService:
    """Starts a singleton service only while this node owns the current leader epoch."""
    def __init__(self,start,stop):
        self.start=start; self.stop=stop; self.running=False; self.epoch=None

    async def gain(self,epoch):
        if self.running:
            if self.epoch != epoch:
                raise RuntimeError("leader epoch changed without stopping prior service")
            return
        # A failed startup must not leave an epoch that looks active.
        try:
            await self.start(epoch)
        except BaseException:
            self.running=False
            self.epoch=None
            raise
        self.epoch=epoch
        self.running=True

    async def lose(self):
        if not self.running:
            self.epoch=None
            return
        # Keep the running marker on stop failure so the next attempt retries
        # shutdown rather than starting a second singleton.
        await self.stop()
        self.running=False
        self.epoch=None
