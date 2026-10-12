import asyncio
from grid.book_tape_research import BookTapeResearch
from grid.scientific_event_router import route_market_event


def test_boolean_trade_fields_rejected_by_book_tape():
    learner=BookTapeResearch()
    for field in ("close","buy_volume","sell_volume"):
        payload={"close":100,"buy_volume":2,"sell_volume":1}
        payload[field]=True
        result=learner.observe({"symbol":"BTCUSDT","event_type":"trade_tape_250ms",
                                "event_ts":1000,"payload":payload})
        assert result["reason"]=="invalid_trade_bucket"
    result=learner.observe({"symbol":"BTCUSDT","event_type":"trade_tape_250ms",
                            "event_ts":True,"payload":{"close":100,"buy_volume":2,"sell_volume":1}})
    assert result["reason"]=="invalid_trade_bucket"


def test_router_rejects_invalid_price_and_volume_before_agents():
    class Orchestrator:
        def __init__(self):self.latest_trade={}
    async def scenario():
        orchestrator=Orchestrator()
        for payload,reason in [
            ({"close":0,"buy_volume":2,"sell_volume":1},"invalid_trade_price"),
            ({"close":100,"buy_volume":-2,"sell_volume":3},"invalid_trade_volume"),
            ({"close":100,"buy_volume":1e308,"sell_volume":1e308},"invalid_trade_volume"),
        ]:
            result=await route_market_event(orchestrator,None,"BTCUSDT",1000,
                                            "trade_tape_250ms",payload,"train")
            assert result["reason"]==reason
            assert not orchestrator.latest_trade
    asyncio.run(scenario())
