from .control_version_vector import freshest_dominating
from .control_snapshot_ring import ControlSnapshotRing

class FailoverBootstrap:
    """Recover control state first; leadership may start only after state is fenced."""
    def __init__(self,journal,ring,election):
        self.journal=journal;self.ring=ring;self.election=election

    async def recover(self,peer_replicas=None):
        candidates=[]
        local=self.journal.load()
        if local["version"]>0:candidates.append({"state":local["state"],"source":"local"})
        snap=self.ring.newest()
        if snap["version"]>0:candidates.append({"state":snap["state"],"source":"snapshot"})
        candidates.extend(peer_replicas or [])
        if candidates:
            best=freshest_dominating(candidates)
            current=self.journal.load()
            # Journal version is local write generation; state carries per-key fencing versions.
            self.journal.apply(current["version"]+1,best["state"])
            self.ring.store(current["version"]+1,best["state"])
        return self.journal.load()

    async def recover_then_campaign(self,peer_replicas=None):
        state=await self.recover(peer_replicas)
        leader=await self.election.campaign()
        return {"leader":leader,"state":state,"epoch":self.election.epoch if leader else None}
