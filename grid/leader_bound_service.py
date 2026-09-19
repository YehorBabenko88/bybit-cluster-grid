class LeaderBoundService:
    """Starts a singleton service only while this node owns the current leader epoch."""
    def __init__(self,start,stop):
        self.start=start; self.stop=stop; self.running=False; self.epoch=None
    async def gain(self,epoch):
        if self.running:return
        self.epoch=epoch
        await self.start(epoch)
        self.running=True
    async def lose(self):
        if not self.running:return
        await self.stop()
        self.running=False; self.epoch=None
