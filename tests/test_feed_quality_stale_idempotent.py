from grid.data_quality import AVAILABLE, STALE, FeedQuality


def test_repeated_stale_checks_count_one_outage():
    quality=FeedQuality("BTCUSDT")
    quality.mark("orderbook",AVAILABLE)
    quality.last_update["orderbook"]=0
    assert quality.stale_check("orderbook",1)
    first=quality.missing_counts["orderbook"]
    assert first==1
    assert quality.stale_check("orderbook",1)
    assert quality.missing_counts["orderbook"]==first
    assert quality.get("orderbook")["status"]==STALE


def test_recovered_feed_can_count_a_new_outage():
    quality=FeedQuality("BTCUSDT")
    quality.mark("orderbook",AVAILABLE)
    quality.last_update["orderbook"]=0
    assert quality.stale_check("orderbook",1)
    quality.mark("orderbook",AVAILABLE)
    quality.last_update["orderbook"]=0
    assert quality.stale_check("orderbook",1)
    assert quality.missing_counts["orderbook"]==1
