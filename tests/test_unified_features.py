import asyncio
from datetime import datetime,timezone
from grid.unified_features import UnifiedFeatureBuilder

class Pool:
    def __init__(self,book=None,deriv=None): self.book=book; self.deriv=deriv
    async def fetchrow(self,sql,*args):
        return self.book if "orderbook_snapshot" in sql else self.deriv

def row(q="GOOD"):
    return {"symbol":"BTC","ts":datetime.now(timezone.utc),"open":100,"high":102,"low":99,"close":101,
            "buy_volume":8,"sell_volume":2,"delta":6,"poc_price":100,"quality_status":q}

def test_unified_features_preserve_missing_capabilities_as_null():
    async def run():
        b=UnifiedFeatureBuilder()
        x=await b.build(Pool(),row())
        assert x["eligible"] is True
        assert x["capabilities"]["orderbook"] is False
        assert x["features"]["book_imbalance"] is None
        assert x["features"]["open_interest"] is None
    asyncio.run(run())

def test_unified_features_merge_microstructure():
    async def run():
        p=Pool({"event_ts":row()["ts"],"payload":{"imbalance":"0.7","spread":"1","bid_depth":"10","ask_depth":"4"}},
               {"event_ts":row()["ts"],"payload":{"open_interest":"123","funding_rate":"0.001"}})
        x=await UnifiedFeatureBuilder().build(p,row())
        assert x["capabilities"]["orderbook"] and x["capabilities"]["derivatives"]
        assert x["features"]["book_imbalance"]==0.7
        assert x["features"]["open_interest"]==123.0
    asyncio.run(run())

def test_degraded_candle_is_hard_ineligible_even_with_microstructure():
    async def run():
        p=Pool({"event_ts":row()["ts"],"payload":{"imbalance":0.2}},
               {"event_ts":row()["ts"],"payload":{"open_interest":1}})
        x=await UnifiedFeatureBuilder().build(p,row("DEGRADED"))
        assert x["eligible"] is False
    asyncio.run(run())
