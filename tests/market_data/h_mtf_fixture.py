"""Shared synthetic source rows for H independent MTF acceptance tests.

Only fixture construction: original Grid producer and minute_record own hashes;
no second math kernel, provider, real SQL, trading or provenance authority.
"""
from market_data.provenance import producer, minute_record

NOW = (1800000120000 // 900000) * 900000 + 45000
BOUNDARY = (NOW // 900000) * 900000


def minutes(width, buy=0.1, sell=0.3):
    source = producer("h-r28-synthetic", "a"*40,
                      "wss://stream.bybit.com/v5/public/linear")
    start = BOUNDARY - width * 60000
    records = []
    for i in range(width):
        tick = start + i * 60000
        row = {
            "symbol": "BTCUSDT", "start_ms": tick,
            "source_event_start_ms":tick + 1,
            "source_event_end_ms":tick + 59000,
            "source_provenance": source,
            "open": 1.0, "high":2.0, "low":1.0, "close":2.0,
            "buy_volume":buy, "sell_volume":sell,
            "delta":buy-sell, "trade_count":2, "poc_price":2.0,
            "quality_status":"GOOD", "quality_reasons":[],
            "levels":[{"price":2.0, "buy_volume":buy, "sell_volume":sell,
                       "delta":buy-sell, "volume":buy+sell,
                       "buy_count":1, "sell_count":1}]
        }
        records.append(minute_record(row, NOW, "h-r28-synthetic"))
    return records


