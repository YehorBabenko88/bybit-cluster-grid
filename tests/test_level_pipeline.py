import asyncio
from datetime import datetime,timedelta,timezone
from grid.level_pipeline import LevelPipeline

class FakePool:
    def __init__(self): self.calls=[]
    async def execute(self,sql,*args):
        self.calls.append((sql,args)); return "OK"
    async def fetch(self,sql,*args): return []

def candle(ts,h=101,l=99,c=100):
    return {"symbol":"BTC","ts":ts,"open":100,"high":h,"low":l,"close":c}

def test_pipeline_persists_completed_level_and_cross_event():
    async def run():
        p=FakePool(); x=LevelPipeline(p)
        a=datetime(2026,1,1,10,0,tzinfo=timezone.utc)
        await x.on_candle(candle(a,101,99,100),{"features":{"delta_ratio":.1}})
        await x.on_candle(candle(a+timedelta(minutes=59),105,97,100),{"features":{"delta_ratio":.2}})
        await x.on_candle(candle(a+timedelta(hours=1),103,98,102),{"features":{"delta_ratio":.3}})
        inserts=[c for c in p.calls if "INSERT INTO historical_levels" in c[0]]
        assert len(inserts)>=2
        assert any(c[1][1]=="1H" and c[1][2]=="HIGH" and c[1][4]==105.0 for c in inserts)
    asyncio.run(run())

def test_restore_active_levels():
    class P(FakePool):
        async def fetch(self,sql,*args):
            return [{"symbol":"ETH","timeframe":"1D","level_kind":"HIGH",
                     "source_ts":datetime(2026,1,1,tzinfo=timezone.utc),"price":2000,
                     "available_ts":datetime(2026,1,2,tzinfo=timezone.utc),"test_count":0}]
    async def run():
        p=P(); x=LevelPipeline(p)
        assert await x.restore_active()==1
        assert len(x.tracker.levels["ETH"])==1
    asyncio.run(run())
