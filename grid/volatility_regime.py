from collections import deque
from statistics import median

QUIET="QUIET"
EXPANDING="EXPANDING"
VOLATILE="VOLATILE"
EXHAUSTION="EXHAUSTION"

class VolatilityRegimeDetector:
    """Stateful, direction-agnostic volatility regime detector with hysteresis."""
    def __init__(self,lookback=120,min_history=12,confirm=2,min_dwell=2):
        self.lookback=int(lookback); self.min_history=int(min_history)
        self.confirm=int(confirm); self.min_dwell=int(min_dwell)
        self.hist={}; self.state={}; self.pending={}; self.pending_n={}; self.dwell={}

    def update(self,symbol,features,eligible=True):
        h=self.hist.setdefault(symbol,deque(maxlen=self.lookback))
        state=self.state.setdefault(symbol,QUIET)
        ready=len(h)>=self.min_history
        score=self._score(features,h) if ready else 1.0
        target=self._target(state,score) if ready and eligible else state
        if target==state:
            self.pending[symbol]=None; self.pending_n[symbol]=0
            self.dwell[symbol]=self.dwell.get(symbol,0)+1
        else:
            if self.pending.get(symbol)==target:
                self.pending_n[symbol]=self.pending_n.get(symbol,0)+1
            else:
                self.pending[symbol]=target; self.pending_n[symbol]=1
            if self.pending_n[symbol]>=self.confirm and self.dwell.get(symbol,0)>=self.min_dwell:
                state=target; self.state[symbol]=state
                self.pending[symbol]=None; self.pending_n[symbol]=0; self.dwell[symbol]=0
        if eligible:
            h.append(self._raw(features))
        return {"regime":state,"regime_score":round(score,6),"regime_ready":ready}

    def _raw(self,f):
        return {
            "rv":max(0.0,_f(f.get("realized_volatility"))),
            "range":max(0.0,_f(f.get("range_pct"))),
            "volume":max(0.0,_f(f.get("volume_ratio"),1.0)),
        }

    def _score(self,f,h):
        cur=self._raw(f)
        rv0=_med(h,"rv"); rg0=_med(h,"range"); vol0=_med(h,"volume")
        rv=_ratio(cur["rv"],rv0)
        rg=_ratio(cur["range"],rg0)
        vol=_ratio(cur["volume"],vol0)
        # Cap isolated bad prints while keeping strong expansion visible.
        return 0.40*min(rv,4.0)+0.35*min(rg,4.0)+0.25*min(vol,4.0)

    def _target(self,state,score):
        if state==QUIET:
            return EXPANDING if score>=1.35 else QUIET
        if state==EXPANDING:
            if score>=1.85: return VOLATILE
            if score<1.10: return QUIET
            return EXPANDING
        if state==VOLATILE:
            return EXHAUSTION if score<1.30 else VOLATILE
        # EXHAUSTION: renewed expansion can restart; otherwise settle back to quiet.
        if score>=1.70: return EXPANDING
        if score<1.05: return QUIET
        return EXHAUSTION

def _med(h,key):
    vals=[x[key] for x in h if x[key]>0]
    return median(vals) if vals else 0.0

def _ratio(v,b):
    if b<=0: return 1.0 if v<=0 else 2.0
    return max(0.0,v/b)

def _f(v,default=0.0):
    try: return float(v) if v is not None else float(default)
    except (TypeError,ValueError): return float(default)
