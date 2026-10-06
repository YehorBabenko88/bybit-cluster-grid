from __future__ import annotations
from collections import defaultdict, deque
from dataclasses import dataclass
from math import sqrt
from statistics import median

@dataclass(frozen=True)
class MicroSignal:
    agent: str
    symbol: str
    ts_ms: int
    state: str
    score: float
    direction: int
    features: dict

class _AdaptiveAgent:
    """Research-only adaptive detector. Learns an instrument's own baseline."""
    def __init__(self, window=600, z_trigger=3.0, refractory=5):
        self.window=max(30,int(window)); self.z_trigger=float(z_trigger)
        self.refractory=max(0,int(refractory)); self.hist=defaultdict(lambda:deque(maxlen=self.window))
        self.cooldown=defaultdict(int)

    def restore(self,symbol,values):
        h=self.hist[symbol];h.clear()
        for v in list(values)[-self.window:]:
            try:h.append(float(v))
            except (TypeError,ValueError):pass

    def _score(self,symbol,value):
        h=self.hist[symbol]
        if len(h)<30:
            h.append(float(value)); return 0.0,"WARMUP"
        vals=list(h); center=median(vals)
        mad=median(abs(x-center) for x in vals)
        scale=max(1.4826*mad,1e-12)
        z=(float(value)-center)/scale
        h.append(float(value))
        if self.cooldown[symbol]>0:
            self.cooldown[symbol]-=1; return z,"REFRACTORY"
        if abs(z)>=self.z_trigger:
            self.cooldown[symbol]=self.refractory
            return z,"EXCITED"
        return z,"QUIET"

class OIAgent(_AdaptiveAgent):
    def __init__(self,**kw):
        super().__init__(**kw); self.prev={}
    def restore_prev(self,symbol,ts_ms,open_interest):
        self.prev[str(symbol)]=(int(ts_ms),float(open_interest))
    def update(self,symbol,ts_ms,open_interest,price=None):
        oi=float(open_interest); old=self.prev.get(symbol); self.prev[symbol]=(int(ts_ms),oi)
        if not old or old[1]<=0:return MicroSignal("oi",symbol,int(ts_ms),"WARMUP",0,0,{"oi":oi})
        dt=max((int(ts_ms)-old[0])/1000,1e-3); rate=(oi/old[1]-1)/dt
        z,state=self._score(symbol,rate)
        return MicroSignal("oi",symbol,int(ts_ms),state,z,1 if rate>0 else -1,{"oi":oi,"oi_return_per_s":rate,"price":price})

class DeltaAgent(_AdaptiveAgent):
    def update(self,symbol,ts_ms,delta,volume):
        v=max(abs(float(volume)),1e-12); ratio=float(delta)/v
        z,state=self._score(symbol,ratio)
        return MicroSignal("delta",symbol,int(ts_ms),state,z,1 if ratio>0 else -1,{"delta_ratio":ratio,"volume":float(volume)})

class BookVelocityAgent(_AdaptiveAgent):
    def update(self,symbol,ts_ms,metrics):
        # Activity, not direction, is anomalous; direction comes from depth pressure.
        rate=float(metrics.get("book_update_rate") or 0)
        z,state=self._score(symbol,rate)
        imbalance=float(metrics.get("imbalance") or 0)
        depth_rate=float(metrics.get("depth_change_rate") or 0)
        return MicroSignal("book_velocity",symbol,int(ts_ms),state,z,1 if imbalance>0 else (-1 if imbalance<0 else 0),
            {"book_update_rate":rate,"book_add_rate":metrics.get("book_add_rate"),
             "book_cancel_rate":metrics.get("book_cancel_rate"),"depth_change_rate":depth_rate,
             "imbalance":imbalance})

class LargeOrderAgent(_AdaptiveAgent):
    def update(self,symbol,ts_ms,walls):
        walls=list(walls or [])
        strongest=max(walls,key=lambda x:float(x.get("ratio") or 0),default={})
        ratio=float(strongest.get("ratio") or 0)
        z,state=self._score(symbol,ratio)
        side=strongest.get("side")
        return MicroSignal("large_order",symbol,int(ts_ms),state,z,1 if side=="bid" else (-1 if side=="ask" else 0),
            {"wall_ratio":ratio,"side":side,"price":strongest.get("price"),"qty":strongest.get("qty"),
             "lifetime_ms":strongest.get("lifetime_ms"),"replenishment_ratio":strongest.get("replenishment_ratio")})

class VolumeAgent(_AdaptiveAgent):
    def update(self,symbol,ts_ms,volume,delta=0):
        volume=float(volume); z,state=self._score(symbol,volume)
        direction=1 if float(delta)>0 else (-1 if float(delta)<0 else 0)
        return MicroSignal("volume",symbol,int(ts_ms),state,z,direction,{"volume":volume,"delta":float(delta)})

class MicrostructureConsensus:
    """No trading authority: discovers co-excitation patterns for later simulation."""
    def __init__(self,max_age_ms=3000,min_agents=2):
        self.max_age_ms=int(max_age_ms); self.min_agents=int(min_agents); self.last=defaultdict(dict)
    def update(self,signal):
        self.last[signal.symbol][signal.agent]=signal
        active=[s for s in self.last[signal.symbol].values()
                if signal.ts_ms-s.ts_ms<=self.max_age_ms and s.state=="EXCITED"]
        signed=sum((1 if s.direction>0 else -1 if s.direction<0 else 0)*abs(s.score) for s in active)
        return {"symbol":signal.symbol,"ts_ms":signal.ts_ms,"active_agents":[s.agent for s in active],
                "agent_count":len(active),"direction":1 if signed>0 else (-1 if signed<0 else 0),
                "strength":sum(abs(s.score) for s in active),
                "candidate":len(active)>=self.min_agents}
