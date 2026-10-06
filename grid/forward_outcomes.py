"""Causal forward-outcome labelling for research signals.

A label is emitted only after its horizon has elapsed. The component has no
trading authority and deliberately keeps feature snapshots immutable.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import log
from typing import Iterable

@dataclass(frozen=True)
class PendingOutcome:
    event_id:str
    symbol:str
    event_ts_ms:int
    horizon_ms:int
    reference_price:float
    event_type:str
    payload:dict

class ForwardOutcomeLedger:
    def __init__(self,horizons_s:Iterable[int]=(1,2,5,10,30,60),max_pending=200000):
        hs=sorted({int(x)*1000 for x in horizons_s if int(x)>0})
        if not hs: raise ValueError("at least one positive horizon is required")
        self.horizons_ms=tuple(hs);self.max_pending=max(1,int(max_pending))
        self.pending:list[PendingOutcome]=[]

    def register(self,event_id,symbol,ts_ms,price,event_type,payload=None):
        p=float(price)
        if p<=0: raise ValueError("reference price must be positive")
        if len(self.pending)+len(self.horizons_ms)>self.max_pending:
            raise BufferError("forward-outcome pending limit reached")
        snap=dict(payload or {})
        for h in self.horizons_ms:
            self.pending.append(PendingOutcome(str(event_id),str(symbol),int(ts_ms),h,p,str(event_type),snap.copy()))

    def observe(self,symbol,ts_ms,price):
        """Return labels matured by this observation; never uses future observations."""
        now=int(ts_ms);px=float(price)
        if px<=0:return []
        keep=[];out=[]
        for p in self.pending:
            if p.symbol!=symbol or now<p.event_ts_ms+p.horizon_ms:
                keep.append(p);continue
            lr=log(px/p.reference_price)
            out.append({"event_id":p.event_id,"symbol":p.symbol,"event_ts_ms":p.event_ts_ms,
                        "label_ts_ms":now,"horizon_ms":p.horizon_ms,
                        "reference_price":p.reference_price,"outcome_price":px,
                        "log_return":lr,"return_bps":lr*10000.0,
                        "event_type":p.event_type,"payload":p.payload})
        self.pending=keep
        return out

    def pending_count(self):return len(self.pending)
