import asyncio
from datetime import datetime,timedelta,timezone
from grid.observer_quality import event_quality
from grid.observer_recovery import ObserverRecovery

def test_missing_optional_feeds_are_explicit_not_zero():
    b={"quality_status":"GOOD","features":{"return_1m":.01,"range_pct":.02,"volume_ratio":1.2,
       "delta_ratio":.2,"close_vs_poc":.001},"capabilities":{"orderbook":False,"derivatives":False}}
    q=event_quality(b)
    assert q["quality_status"]=="GOOD"
    assert q["components"]["micro"]==0 and q["components"]["derivatives"]==0

def test_missing_core_or_degraded_candle_blocks_ml():
    b={"quality_status":"DEGRADED","features":{"return_1m":.01},"capabilities":{}}
    q=event_quality(b)
    assert q["ml_eligible"] is False and q["quality_status"]=="DEGRADED"

class P:
    def __init__(self,rows): self.rows=rows; self.saved=[]
    async def fetchrow(self,sql,*args): return None
    async def fetch(self,sql,*args):
        out=self.rows[:args[-1]]; self.rows=self.rows[len(out):]; return out
    async def execute(self,sql,*args): self.saved.append((sql,args))

class Pipe:
    def __init__(self): self.seen=[]
    async def on_candle(self,row,built): self.seen.append((row,built))

def test_recovery_marks_minute_gap_degraded_and_checkpoints_after_processing():
    async def run():
        a=datetime(2026,1,1,tzinfo=timezone.utc)
        def r(n): return {"symbol":"BTC","ts":a+timedelta(minutes=n),"open":1,"high":1,"low":1,"close":1,
          "features":{},"capabilities":{},"eligible":True,"feature_quality":"GOOD","quality_status":"GOOD"}
        p=P([r(0),r(2)]); pipe=Pipe(); x=ObserverRecovery(p,pipe)
        out=await x.catch_up("BTC")
        assert out["gaps"]==1 and out["processed"]==2
        assert pipe.seen[1][1]["eligible"] is False
        assert pipe.seen[1][1]["features"]["observer_gap_before"] is True
        assert len(p.saved)==2
    asyncio.run(run())
