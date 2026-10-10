import asyncio
from grid.floating_leader import FloatingLeader

class Pool:
    async def execute(self,*args):return "UPDATE 0"

def test_loss_callback_failure_does_not_kill_election_loop():
    async def scenario():
        leader=FloatingLeader(Pool(),node_id="node",renew_seconds=0.01)
        async def campaign():
            leader.is_leader=True
            leader.epoch=7
            return True
        async def renew():
            leader.is_leader=False
            leader.epoch=None
            return False
        leader.campaign=campaign
        leader.renew=renew
        events=[]
        async def on_loss():
            events.append("loss")
            leader.stop()
            raise RuntimeError("cleanup failure")
        await asyncio.wait_for(leader.run(on_loss=on_loss),timeout=1)
        assert events==["loss"]
        assert leader.is_leader is False
        assert leader.epoch is None
    asyncio.run(scenario())
