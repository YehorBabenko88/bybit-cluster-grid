from collections import defaultdict
from datetime import datetime, timezone
from .models import Trade, PriceCluster

class FootprintBuilder:
    def __init__(self, tick_size: float, interval_s: int = 60):
        self.tick_size = tick_size
        self.interval_ms = interval_s * 1000
        self.buckets = {}

    def _price_key(self, price: float) -> int:
        return round(price / self.tick_size)

    def add(self, t: Trade):
        start = (t.ts_ms // self.interval_ms) * self.interval_ms
        b = self.buckets.setdefault((t.symbol, start), {
            "open": t.price, "high": t.price, "low": t.price, "close": t.price,
            "buy": 0.0, "sell": 0.0, "trades": 0, "levels": defaultdict(PriceCluster),
            "quality_status":"GOOD", "quality_reasons":[]
        })
        b["high"] = max(b["high"], t.price); b["low"] = min(b["low"], t.price); b["close"] = t.price
        lvl = b["levels"][self._price_key(t.price)]
        # Bybit publicTrade S=Buy means buyer was taker/aggressor.
        if t.side.lower() == "buy":
            b["buy"] += t.qty; lvl.buy_qty += t.qty; lvl.buy_count += 1
        else:
            b["sell"] += t.qty; lvl.sell_qty += t.qty; lvl.sell_count += 1
        b["trades"] += 1

    def mark_degraded(self, symbol: str, ts_ms: int, reason: str):
        start=(ts_ms // self.interval_ms)*self.interval_ms
        b=self.buckets.get((symbol,start))
        if b is not None:
            b["quality_status"]="DEGRADED"
            if reason not in b["quality_reasons"]: b["quality_reasons"].append(reason)

    def pop_closed(self, now_ms: int):
        out=[]
        for key in list(self.buckets):
            symbol,start=key
            if start + self.interval_ms > now_ms: continue
            b=self.buckets.pop(key)
            poc_key=max(b["levels"], key=lambda k:b["levels"][k].volume)
            out.append({
                "symbol":symbol,"start_ms":start,"open":b["open"],"high":b["high"],"low":b["low"],"close":b["close"],
                "buy_volume":b["buy"],"sell_volume":b["sell"],"delta":b["buy"]-b["sell"],"trade_count":b["trades"],
                "poc_price":poc_key*self.tick_size,
                "quality_status":b["quality_status"],"quality_reasons":b["quality_reasons"],
                "levels":[{"price":k*self.tick_size,"buy_volume":v.buy_qty,"sell_volume":v.sell_qty,
                           "delta":v.delta,"volume":v.volume,"buy_count":v.buy_count,"sell_count":v.sell_count}
                          for k,v in sorted(b["levels"].items())]
            })
        return out
