"""Fail-closed instrument/data lifecycle decisions."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone

@dataclass(frozen=True)
class FeedHealth:
    state:str
    age_seconds:float|None
    reason:str

def feed_health(last_event_at,*,now=None,stale_after_s=15,missing_state="UNAVAILABLE"):
    if last_event_at is None:return FeedHealth(missing_state,None,"never_observed")
    now=now or datetime.now(timezone.utc)
    age=max(0.0,(now-last_event_at).total_seconds())
    if age>float(stale_after_s):return FeedHealth("STALE",age,"freshness_timeout")
    return FeedHealth("LIVE",age,"fresh")

def operational_state(*,listed:bool,ohlcv:FeedHealth|None=None,trades:FeedHealth|None=None,
                      optional_feeds=(),history_samples=0,min_warmup_samples=60):
    if not listed:return "RETIRED"
    if int(history_samples)<int(min_warmup_samples):return "WARMING_UP"
    required=[x for x in (ohlcv,trades) if x is not None]
    if any(x.state not in ("LIVE","READY") for x in required):return "DEGRADED"
    return "ACTIVE"

def requirements_met(required,capabilities):
    """A strategy/method may run only when every declared feed is usable."""
    usable={"READY","LIVE","PARTIAL"}
    missing=[]
    for name in required:
        value=capabilities.get(name)
        if value not in usable:missing.append(name)
    return not missing,tuple(missing)


class FeedRecoveryGate:
    """Require consecutive fresh observations after a gap/reconnect."""
    def __init__(self,required_fresh=3):
        self.required=max(1,int(required_fresh));self.counts={}
    def observe(self,symbol,feed,healthy):
        key=(str(symbol),str(feed))
        if not healthy:
            self.counts[key]=0
            return "STALE"
        n=min(self.required,self.counts.get(key,0)+1);self.counts[key]=n
        return "LIVE" if n>=self.required else "RECOVERING"
    def reset_symbol(self,symbol):
        prefix=str(symbol)
        for key in list(self.counts):
            if key[0]==prefix:self.counts.pop(key,None)
