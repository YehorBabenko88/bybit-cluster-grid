from dataclasses import dataclass, field
from time import time

UNKNOWN="unknown"
AVAILABLE="available"
MISSING="missing"
STALE="stale"
UNSUPPORTED="unsupported"
DEGRADED="degraded"

@dataclass
class FeedQuality:
    symbol: str
    feeds: dict = field(default_factory=dict)
    missing_counts: dict = field(default_factory=dict)
    last_update: dict = field(default_factory=dict)

    def mark(self,feed,status=AVAILABLE,reason=None):
        self.feeds[feed]={"status":status,"reason":reason}
        if status==AVAILABLE:
            self.last_update[feed]=time()
            self.missing_counts[feed]=0
        elif status in (MISSING,STALE):
            self.missing_counts[feed]=self.missing_counts.get(feed,0)+1

    def get(self,feed):
        return self.feeds.get(feed,{"status":UNKNOWN,"reason":None})

    def stale_check(self,feed,max_age_s):
        last=self.last_update.get(feed)
        if last is not None and time()-last>max_age_s:
            if self.get(feed)["status"]!=STALE:
                self.mark(feed,STALE,f"no update for {int(time()-last)}s")
            return True
        return False

    def snapshot(self):
        return {
            "symbol":self.symbol,
            # Snapshot payloads must not change when the next feed update
            # mutates the live quality state while a DB write is pending.
            "feeds":{name:dict(value) for name,value in self.feeds.items()},
            "missing_counts":dict(self.missing_counts),
            "last_update":dict(self.last_update),
        }

def safe_float(value,default=None):
    if value is None or value=="":
        return default
    try:
        return float(value)
    except (TypeError,ValueError):
        return default

def completeness(required,values):
    present=sum(1 for k in required if values.get(k) is not None)
    return present/len(required) if required else 1.0
