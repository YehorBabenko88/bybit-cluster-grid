import asyncio
from datetime import datetime,timezone

from grid.unified_features import UnifiedFeatureBuilder


class FakePool:
    def __init__(self,micro):
        self.micro=micro
        self.queries=[]

    async def fetchrow(self,sql,*args):
        self.queries.append((sql,args))
        if "microstructure_samples" in sql:
            return self.micro
        if "derivatives_ticker" in sql:
            return None
        if "orderbook_snapshot" in sql:
            raise AssertionError("legacy book fallback must not run when causal micro sample exists")
        return None


def test_unified_features_prefer_known_at_microstructure_sample():
    ts=datetime(2026,1,1,tzinfo=timezone.utc)
    payload={
        "imbalance":.25,"spread":1.0,"bid_depth":100.0,"ask_depth":60.0,
        "bid_depth_10":70.0,"ask_depth_10":40.0,
        "added_bid":8.0,"removed_ask":5.0,
        "buy_volume":12.0,"sell_volume":4.0,"trade_count":7,
        "large_buy_volume":6.0,"large_sell_volume":0.0,
        "trade_available":True,"book_gap":False,"trade_gap":False,
    }
    pool=FakePool({"ts":ts,"known_at":ts,"payload":payload})
    row={
        "symbol":"BTCUSDT","ts":ts,"open":100.0,"high":101.0,"low":99.0,"close":100.5,
        "buy_volume":10.0,"sell_volume":5.0,"delta":5.0,"poc_price":100.0,
        "quality_status":"GOOD",
    }
    built=asyncio.run(UnifiedFeatureBuilder().build(pool,row))
    f=built["features"]
    assert built["capabilities"]["microstructure"] is True
    assert f["bid_depth_10"]==70.0
    assert f["micro_buy_volume"]==12.0
    assert f["large_buy_volume"]==6.0
    assert f["micro_trade_available"] is True
    micro_sql=pool.queries[0][0]
    assert "known_at<=$2" in micro_sql
