import time

class QuorumPolicy:
    """Prefer shared-state leadership; allow single-node control in isolated degraded mode."""
    def __init__(self,node_id,peer_timeout=30):
        self.node_id=node_id; self.peer_timeout=float(peer_timeout)
    def decide(self,db_ok,peers,now=None):
        now=time.time() if now is None else float(now)
        live=[p for p in peers if now-float(p.get("last_seen",0))<=self.peer_timeout]
        if db_ok:return {"mode":"SHARED","telegram":True,"mutations":True}
        others=[p for p in live if p.get("node_id")!=self.node_id]
        if not others:
            return {"mode":"ISOLATED_LAST_NODE","telegram":True,"mutations":False}
        return {"mode":"NO_LEADER","telegram":False,"mutations":False}
