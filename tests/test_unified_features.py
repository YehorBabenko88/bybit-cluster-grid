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


from grid.unified_features import _payload_dict


def test_payload_dict_accepts_mapping():
    payload={"mark_price":"2693.44"}
    assert _payload_dict(payload) is payload


def test_payload_dict_decodes_json_string():
    assert _payload_dict('{"mark_price":"2693.44","funding_rate":"0.0001"}') == {
        "mark_price":"2693.44","funding_rate":"0.0001"
    }


def test_payload_dict_handles_none():
    assert _payload_dict(None) == {}


def test_payload_dict_rejects_malformed_json():
    assert _payload_dict('{"mark_price":') == {}


def test_payload_dict_rejects_non_object_json():
    assert _payload_dict('["not","an","object"]') == {}


class RetentionPool:
    def __init__(self):
        self.calls=[]
    async def execute(self,sql,*args):
        self.calls.append((sql,args))
        return "INSERT 0 1"
    async def fetch(self,sql,*args):
        self.calls.append((sql,args))
        return []

def test_unified_feature_consumer_registers_market_events():
    async def run():
        p=RetentionPool()
        b=UnifiedFeatureBuilder()
        await b.start(p)
        assert b.started is True
        assert any(
            "INSERT INTO retention_consumers" in sql
            and args[:2]==("market_events","unified_features")
            and args[2:]==(True,True)
            for sql,args in p.calls
        )
        before=len(p.calls)
        await b.start(p)
        assert len(p.calls)==before
    asyncio.run(run())

def test_persist_advances_market_event_watermark_only_after_feature_write():
    async def run():
        p=RetentionPool()
        b=UnifiedFeatureBuilder()
        ts=datetime.now(timezone.utc)
        built={
            "symbol":"BTC","ts":ts,"eligible":True,"quality_status":"GOOD",
            "regime":"QUIET","regime_score":1.0,
            "features":{"book_imbalance":0.1},
            "capabilities":{"candle":True,"footprint":True,"orderbook":True,"derivatives":True},
        }
        await b.persist(p,built)
        assert len(p.calls)==2
        assert "INSERT INTO market_features_1m" in p.calls[0][0]
        assert "INSERT INTO consumer_watermarks" in p.calls[1][0]
        assert p.calls[1][1][:4]==("market_events","unified_features","BTC",ts)
        assert p.calls[1][1][4] is True
    asyncio.run(run())


def test_feature_builder_hydrates_restart_state_and_resets_on_minute_gap():
    from pathlib import Path
    text=Path("grid/unified_features.py").read_text(encoding="utf-8")
    assert "row_number() OVER(PARTITION BY symbol ORDER BY ts DESC)" in text
    assert "FROM candles_1m WHERE quality_status='GOOD'" in text
    assert "ts-previous!=timedelta(minutes=1)" in text
    assert 'source["quality_status"]="DEGRADED"' in text
    assert '"minute_gap"' in text
