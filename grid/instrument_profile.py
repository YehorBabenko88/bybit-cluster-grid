from collections import deque
from statistics import median

class InstrumentProfile:
    """Online causal normalization/profile for symbol-specific scale and liquidity."""
    def __init__(self,maxlen=1440):
        self.rows={}; self.maxlen=int(maxlen)

    def push(self,symbol,features):
        q=self.rows.setdefault(symbol,deque(maxlen=self.maxlen)); q.append(dict(features))

    def snapshot(self,symbol):
        q=self.rows.get(symbol,())
        return {
            "history_samples":len(q),
            "median_range_pct":_med(q,"range_pct"),
            "median_volume_ratio":_med(q,"volume_ratio"),
            "median_realized_volatility":_med(q,"realized_volatility"),
            "median_spread":_med(q,"spread"),
            "median_bid_depth":_med(q,"bid_depth"),
            "median_ask_depth":_med(q,"ask_depth"),
            "median_open_interest":_med(q,"open_interest"),
        }

def _med(rows,key):
    vals=[]
    for r in rows:
        try:
            if r.get(key) is not None: vals.append(float(r[key]))
        except (TypeError,ValueError): pass
    return median(vals) if vals else None
