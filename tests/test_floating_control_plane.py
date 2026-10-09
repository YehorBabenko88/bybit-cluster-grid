from grid.control_plane_failover import QuorumPolicy
from grid.ml_experiment_factory import expand_grid

def test_last_node_keeps_telegram_but_blocks_shared_mutations():
    q=QuorumPolicy("a",peer_timeout=30)
    x=q.decide(False,[{"node_id":"a","last_seen":100}],now=100)
    assert x=={"mode":"ISOLATED_LAST_NODE","telegram":True,"mutations":False}

def test_partition_with_live_peer_does_not_create_two_emergency_leaders():
    q=QuorumPolicy("a",peer_timeout=30)
    x=q.decide(False,[{"node_id":"a","last_seen":100},{"node_id":"b","last_seen":95}],now=100)
    assert x["mode"]=="NO_LEADER" and not x["telegram"]

def test_experiment_grid_is_deterministic():
    a=list(expand_grid({"depth":[4,6],"lr":[.1,.05]}))
    b=list(expand_grid({"lr":[.1,.05],"depth":[4,6]}))
    assert a==b and len(a)==4


def test_leader_loop_recovers_after_database_outage():
    import asyncio
    from grid.floating_leader import FloatingLeader

    class FlakyLeader(FloatingLeader):
        def __init__(self):
            super().__init__(pool=None,node_id="node-a",renew_seconds=.01)
            self.calls=0
        async def campaign(self):
            self.calls+=1
            if self.calls==1:
                raise ConnectionError("postgres down")
            self.is_leader=True
            self.epoch=123
            return True
        async def renew(self):
            self.stop()
            return True

    async def run():
        gained=[]
        leader=FlakyLeader()
        await asyncio.wait_for(leader.run(on_gain=lambda epoch: _record(gained,epoch)),timeout=1)
        assert leader.calls>=2
        assert gained==[123]

    async def _record(items,value):
        items.append(value)

    asyncio.run(run())


def test_leader_db_failure_fails_closed_and_calls_loss_once():
    import asyncio
    from grid.floating_leader import FloatingLeader

    class FailingRenew(FloatingLeader):
        def __init__(self):
            super().__init__(pool=None,node_id="node-a",renew_seconds=.01)
            self.is_leader=True
            self.epoch=77
            self.calls=0
        async def renew(self):
            self.calls+=1
            if self.calls==1:
                raise ConnectionError("postgres lost")
            self.stop()
            return False
        async def campaign(self):
            self.stop()
            return False

    async def run():
        lost=[]
        leader=FailingRenew()
        async def loss():
            lost.append("lost")
        # Pretend leadership was already observed by the loop before the outage.
        original_renew=leader.renew
        first=True
        async def wrapped():
            nonlocal first
            if first:
                first=False
                return True
            return await original_renew()
        leader.renew=wrapped
        await asyncio.wait_for(leader.run(on_loss=loss),timeout=1)
        assert leader.is_leader is False
        assert leader.epoch is None
        assert lost==["lost"]

    asyncio.run(run())


def test_floating_leader_epochs_are_database_serialized():
    from pathlib import Path
    source=Path("grid/floating_leader.py").read_text(encoding="utf-8")
    assert "FOR UPDATE" in source
    assert "get('epoch',0))+1" in source
    assert "int(time.time()*1000)" not in source
