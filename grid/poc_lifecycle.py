from dataclasses import dataclass

NAKED="NAKED"
TOUCHED="TOUCHED"
CROSSED="CROSSED"
ACCEPTED="ACCEPTED"

@dataclass
class PocLevel:
    source_ts: object
    price: float
    source_close: float
    status: str=NAKED
    first_touch_ts: object=None
    first_touch_minutes: int=None
    first_touch_kind: str=None
    cross_ts: object=None
    acceptance_ts: object=None
    touch_count: int=0
    max_distance_pct: float=0.0
    consecutive_accept: int=0

class PocLifecycleTracker:
    """Tracks whether each historical minute POC is revisited; no assumption that revisit is inevitable."""
    def __init__(self,tolerance_pct=0.00015,accept_bars=2,max_open=5000):
        self.tolerance_pct=float(tolerance_pct); self.accept_bars=int(accept_bars)
        self.max_open=int(max_open); self.open={}

    def register(self,symbol,ts,poc_price,source_close):
        if poc_price is None: return None
        level=PocLevel(ts,float(poc_price),float(source_close))
        levels=self.open.setdefault(symbol,[])
        levels.append(level)
        if len(levels)>self.max_open: del levels[:len(levels)-self.max_open]
        return level

    def observe(self,symbol,ts,open_,high,low,close):
        events=[]
        o,h,l,c=map(float,(open_,high,low,close))
        for x in self.open.get(symbol,[]):
            if ts<=x.source_ts: continue
            p=x.price; tol=max(abs(p)*self.tolerance_pct,1e-18)
            x.max_distance_pct=max(x.max_distance_pct,abs(c-p)/max(abs(p),1e-18))
            touched=l-tol<=p<=h+tol
            if touched:
                x.touch_count+=1
                first_touch_now=x.first_touch_ts is None
                if first_touch_now:
                    x.first_touch_ts=ts
                    try: x.first_touch_minutes=max(1,int((ts-x.source_ts).total_seconds()//60))
                    except Exception: x.first_touch_minutes=None
                    if abs(o-p)<=tol: x.first_touch_kind="OPEN_AT_POC"
                    elif (o<p<c) or (o>p>c): x.first_touch_kind="BODY_CROSS"
                    else: x.first_touch_kind="WICK_TOUCH"
                    x.status=TOUCHED
                    events.append(("FIRST_TOUCH",x))
                elif not first_touch_now:
                    events.append(("TOUCH",x))
                if (o<p<c) or (o>p>c):
                    if x.cross_ts is None:
                        x.cross_ts=ts
                        events.append(("CROSSED",x))
                    x.status=CROSSED
            # Acceptance: consecutive closes near POC, deliberately stricter than a wick touch.
            if abs(c-p)<=tol:
                x.consecutive_accept+=1
                if x.consecutive_accept>=self.accept_bars and x.acceptance_ts is None:
                    x.acceptance_ts=ts; x.status=ACCEPTED; events.append(("ACCEPTED",x))
            else:
                x.consecutive_accept=0
        return events

    def horizons(self,symbol,now_ts,horizons=(5,15,60,240,1440)):
        out=[]
        for x in self.open.get(symbol,[]):
            try: age=int((now_ts-x.source_ts).total_seconds()//60)
            except Exception: continue
            for n in horizons:
                if age==n:
                    out.append({"source_ts":x.source_ts,"poc_price":x.price,"horizon_min":n,
                                "returned":x.first_touch_ts is not None and x.first_touch_minutes<=n,
                                "first_touch_minutes":x.first_touch_minutes,"status":x.status,
                                "max_distance_pct":x.max_distance_pct})
        return out
