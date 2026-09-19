from collections import deque
from statistics import mean

WINDOWS=(1,3,5,15,30)

class RollingEventFeatures:
    """Causal rolling features; snapshot() only uses observations strictly before the event row."""
    def __init__(self,max_minutes=60):
        self.max_minutes=int(max_minutes); self.rows={}

    def push(self,symbol,ts,features):
        q=self.rows.setdefault(symbol,deque(maxlen=self.max_minutes+5))
        q.append((ts,dict(features)))

    def snapshot(self,symbol,event_ts):
        hist=[(ts,f) for ts,f in self.rows.get(symbol,()) if ts<event_ts]
        out={}
        for n in WINDOWS:
            rows=hist[-n:]
            out.update(_window(rows,n))
        return out

def _window(rows,n):
    p=f"pre_{n}m_"
    if not rows:
        return {p+"samples":0}
    keys=("delta_ratio","volume_ratio","range_pct","realized_volatility","book_imbalance",
          "spread","bid_depth","ask_depth","book_update_rate","book_add_rate",
          "book_cancel_rate","depth_change_rate","open_interest","funding_rate")
    out={p+"samples":len(rows)}
    for k in keys:
        vals=[_num(f.get(k)) for _,f in rows]
        vals=[v for v in vals if v is not None]
        if vals:
            out[p+k+"_mean"]=mean(vals)
            out[p+k+"_last"]=vals[-1]
            out[p+k+"_change"]=vals[-1]-vals[0] if len(vals)>1 else 0.0
            if len(vals)>2:
                d1=vals[-1]-vals[-2]; d0=vals[-2]-vals[-3]
                out[p+k+"_accel"]=d1-d0
    return out

def _num(v):
    try: return float(v) if v is not None else None
    except (TypeError,ValueError): return None
