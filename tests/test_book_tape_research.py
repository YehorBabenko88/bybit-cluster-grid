from grid.book_tape_research import BookTapeResearch, VERSION


def event(ts,price,buy=10,sell=1,symbol="BTCUSDT"):
    return {"symbol":symbol,"event_type":"trade_tape_250ms","event_ts":ts,
            "payload":{"close":price,"buy_volume":buy,"sell_volume":sell}}


def test_warmup_and_causal_breakout_candidate():
    method=BookTapeResearch(window=16,min_history=8)
    for i in range(8):
        result=method.observe(event(1000+i*250,100+i*.01))
        assert result["eligible"] is False
    result=method.observe(event(3000,101,buy=40,sell=1))
    assert result["eligible"] is True
    assert result["version"]==VERSION
    assert result["patterns"]["jbe_proxy"] is True
    assert result["features"]["relative_volume"]>1.2
    assert result["direction"]==1
    assert result["decision"]=="PAPER_CANDIDATE"


def test_out_of_order_and_invalid_buckets_do_not_poison_state():
    method=BookTapeResearch(min_history=4)
    for i in range(4):
        method.observe(event(1000+i*250,100+i*.01))
    assert method.observe(event(1000,200))["reason"]=="replayed_or_out_of_order"
    assert method.observe(event(2100,200,buy=float("nan")))["reason"]=="invalid_trade_bucket"
    assert method.observe(event(2000,100.1))["eligible"] is True
    assert method.last_ts["BTCUSDT"]==2000


def test_symbol_isolation_and_research_only_abstention():
    method=BookTapeResearch(min_history=4)
    for i in range(4):
        method.observe(event(1000+i*250,100,symbol="BTCUSDT"))
    result=method.observe(event(2000,100,symbol="BTCUSDT"))
    assert result["direction"]==0
    assert result["decision"]=="ABSTAIN"
    assert "proxy_poc" in result["features"]
    assert method.observe(event(2000,200,symbol="ETHUSDT"))["reason"]=="warmup"


def test_missing_volume_and_unknown_event_rejected():
    method=BookTapeResearch(min_history=4)
    assert method.observe({"symbol":"BTCUSDT","event_type":"derivatives_ticker"})["eligible"] is False
    assert method.observe(event(1000,100,buy=0,sell=0))["reason"]=="invalid_trade_bucket"
    assert method.observe(event(1000,100,buy=-1))["reason"]=="invalid_trade_bucket"
