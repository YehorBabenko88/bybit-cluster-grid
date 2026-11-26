"""Causal scalp-entry generators.

Every decision is made from observations whose known_at <= decision_time.
No L2/OI is fabricated when historical coverage does not provide it.
"""
from __future__ import annotations
from dataclasses import dataclass
from .execution import Signal

@dataclass(frozen=True)
class ScalpEntry:
    pattern:str
    decision_time:int
    direction:str
    reference:float
    signal:Signal
    metadata:dict

def _known_bar(b,bar_ms): return int(b["t"])+int(bar_ms)
def _vol_at(snaps,t):
    xs=[x for x in snaps if x.known_at<=t]
    return xs[-1] if xs else None
def _profile_at(profiles,t):
    xs=[x for x in profiles if x.known_at<=t]
    return xs[-1] if xs else None
def _flow_at(rows,t):
    xs=[x for x in rows if int(x.get("known_at",x["t"]))<=t]
    return xs[-1] if xs else None
def _risk(side,entry,atr_pct,rr=1.5,stop_atr=.75):
    d=max(float(entry)*max(float(atr_pct),.0005)*float(stop_atr),float(entry)*.0005)
    if side=="long": return entry-d,entry+d*rr
    return entry+d,entry-d*rr

def sweep_reclaim_entries(bars,smc_events,volatility=(),*,bar_ms=60_000):
    rows=list(bars);out=[]
    by_t={int(b["t"]):b for b in rows}
    for e in smc_events:
        if e.kind not in ("bullish_liquidity_sweep","bearish_liquidity_sweep"):continue
        b=by_t.get(int(e.event_time))
        if b is None:continue
        decision=max(int(e.known_at),_known_bar(b,bar_ms))
        side="long" if e.kind.startswith("bullish") else "short"
        entry=float(b["close"]);v=_vol_at(volatility,decision);atr=v.atr_pct if v else .002
        sl,tp=_risk(side,entry,atr)
        out.append(ScalpEntry("SCALP_SWEEP_RECLAIM",decision,side,float(e.value["level"]),
          Signal(decision,side,"market",None,sl,tp),
          {"level":float(e.value["level"]),"sweep_event_time":int(e.event_time),
           "volatility_regime":getattr(getattr(v,"regime",None),"value","UNKNOWN")}))
    return tuple(out)

def breakout_retest_volume_entries(bars,smc_events,volatility=(),*,bar_ms=60_000,
                                   retest_tolerance=.0015,min_volume_expansion=1.20,max_wait_bars=20):
    rows=list(bars);out=[]
    for e in smc_events:
        if e.kind not in ("bullish_bos","bearish_bos"):continue
        side="long" if e.kind.startswith("bullish") else "short";level=float(e.value["level"])
        for b in rows:
            decision=_known_bar(b,bar_ms)
            if decision<=int(e.known_at):continue
            if int(b["t"])-int(e.event_time)>max_wait_bars*bar_ms:break
            touched=(float(b["low"])<=level*(1+retest_tolerance) and float(b["close"])>level) if side=="long" else (
                     float(b["high"])>=level*(1-retest_tolerance) and float(b["close"])<level)
            if not touched:continue
            v=_vol_at(volatility,decision)
            if v is None or float(v.volume_expansion)<min_volume_expansion:continue
            entry=float(b["close"]);sl,tp=_risk(side,entry,v.atr_pct)
            out.append(ScalpEntry("SCALP_BREAKOUT_RETEST_VOLUME",decision,side,level,
              Signal(decision,side,"market",None,sl,tp),
              {"level":level,"bos_known_at":int(e.known_at),"volume_expansion":float(v.volume_expansion),
               "volatility_regime":v.regime.value}))
            break
    return tuple(out)

def volatility_expansion_entries(bars,volatility,*,bar_ms=60_000,min_volume_expansion=1.35,
                                 min_percentile=.60,min_body_atr=.50):
    rows=list(bars);out=[]
    snaps={int(x.event_time):x for x in volatility}
    for b in rows:
        v=snaps.get(int(b["t"]))
        if v is None:continue
        decision=max(int(v.known_at),_known_bar(b,bar_ms))
        if float(v.percentile)<min_percentile or float(v.volume_expansion)<min_volume_expansion:continue
        body=float(b["close"])-float(b["open"])
        if abs(body)<float(b["close"])*float(v.atr_pct)*min_body_atr:continue
        side="long" if body>0 else "short";entry=float(b["close"]);sl,tp=_risk(side,entry,v.atr_pct)
        out.append(ScalpEntry("SCALP_VOL_EXPANSION_CONTINUATION",decision,side,entry,
          Signal(decision,side,"market",None,sl,tp),
          {"volume_expansion":float(v.volume_expansion),"volatility_percentile":float(v.percentile),
           "volatility_regime":v.regime.value}))
    return tuple(out)

def poc_reclaim_entries(bars,profiles,flow=(),volatility=(),*,bar_ms=60_000):
    rows=list(bars);out=[]
    prev=None
    for b in rows:
        decision=_known_bar(b,bar_ms);p=_profile_at(profiles,decision)
        if p is None or prev is None:prev=b;continue
        poc=float(p.poc);side=None
        if float(prev["close"])<poc<=float(b["close"]):side="long"
        elif float(prev["close"])>poc>=float(b["close"]):side="short"
        if side:
            f=_flow_at(flow,decision)
            delta=float(f.get("delta",0)) if f else 0.0
            if f is not None and ((side=="long" and delta<=0) or (side=="short" and delta>=0)):
                prev=b;continue
            v=_vol_at(volatility,decision);atr=v.atr_pct if v else .002
            entry=float(b["close"]);sl,tp=_risk(side,entry,atr)
            out.append(ScalpEntry("SCALP_POC_RECLAIM",decision,side,poc,
              Signal(decision,side,"market",None,sl,tp),
              {"poc":poc,"poc_mode":p.mode.value,"delta":delta,
               "volatility_regime":getattr(getattr(v,"regime",None),"value","UNKNOWN")}))
        prev=b
    return tuple(out)
