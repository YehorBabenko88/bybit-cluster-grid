import asyncio,logging
from .floating_leader import FloatingLeader
from .control_replication import sync_control_to_local
from .control_plane_failover import QuorumPolicy

log=logging.getLogger("control_candidate")

class ControlCandidate:
    """DB-fenced control-plane candidacy. Never enables shared mutations without DB fencing."""
    def __init__(self,pool,node_id,journal,peers_provider,lease_seconds=20,renew_seconds=5):
        self.pool=pool;self.node_id=node_id;self.journal=journal;self.peers_provider=peers_provider
        self.election=FloatingLeader(pool,node_id,lease_seconds,renew_seconds)
        self.policy=QuorumPolicy(node_id,peer_timeout=max(30,lease_seconds*2))
        self.mode="FOLLOWER";self.is_leader=False

    async def tick(self):
        db_ok=True
        try:
            await sync_control_to_local(self.pool,self.journal)
            leader=await (self.election.renew() if self.election.is_leader else self.election.campaign())
        except Exception:
            db_ok=False;leader=False;self.election.is_leader=False
        peers=self.peers_provider() or []
        decision=self.policy.decide(db_ok,peers)
        if db_ok and leader:
            self.mode="LEADER";self.is_leader=True
        elif not db_ok:
            self.mode=decision["mode"];self.is_leader=False
        else:
            self.mode="FOLLOWER";self.is_leader=False
        return {"mode":self.mode,"leader":self.is_leader,
                "telegram":bool(self.is_leader or decision.get("telegram",False)),
                "mutations":bool(self.is_leader and decision.get("mutations",False))}

    async def run(self,stop_event=None):
        stop_event=stop_event or asyncio.Event()
        while not stop_event.is_set():
            try: await self.tick()
            except Exception: log.exception("control candidate tick failed")
            try: await asyncio.wait_for(stop_event.wait(),timeout=self.election.renew_seconds)
            except asyncio.TimeoutError: pass
