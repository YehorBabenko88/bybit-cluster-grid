from grid.data_quality import FeedQuality, AVAILABLE, MISSING


def test_snapshot_does_not_mutate_after_subsequent_marks():
    quality=FeedQuality("BTCUSDT")
    quality.mark("orderbook",AVAILABLE)
    before=quality.snapshot()
    quality.mark("orderbook",MISSING,"sequence gap")
    assert before["feeds"]["orderbook"]["status"]==AVAILABLE
    assert before["missing_counts"]["orderbook"]==0
    assert quality.snapshot()["feeds"]["orderbook"]["status"]==MISSING


def test_snapshot_cannot_mutate_live_feed_quality():
    quality=FeedQuality("BTCUSDT")
    quality.mark("ticker",AVAILABLE)
    snapshot=quality.snapshot()
    snapshot["feeds"]["ticker"]["status"]="corrupted"
    snapshot["missing_counts"]["ticker"]=999
    snapshot["last_update"]["ticker"]=0
    assert quality.get("ticker")["status"]==AVAILABLE
    assert quality.missing_counts["ticker"]==0
    assert quality.last_update["ticker"]!=0
