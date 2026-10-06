"""Shared scalp-research ontology across historical bootstrap and live learning.

Historical-only fields never impersonate live L2 fields.
"""
from __future__ import annotations
from dataclasses import dataclass

EVENT_STATES=("LEVEL_APPROACH","IMPULSE_BUILDUP","BREAKOUT","REJECTION","FOLLOW_THROUGH","FAILURE")

FEATURE_CAPABILITY={
 "level_distance_bps":"HISTORICAL",
 "level_kind":"HISTORICAL",
 "volatility_regime":"HISTORICAL",
 "volume_expansion":"HISTORICAL",
 "turnover_expansion":"HISTORICAL",
 "delta_ratio":"HISTORICAL",
 "cvd_slope":"HISTORICAL",
 "open_interest_rate":"HISTORICAL",
 "funding_rate":"HISTORICAL",
 "long_short_ratio":"HISTORICAL",
 "tape_speed":"LIVE_OR_ARCHIVED_TRADES",
 "large_trade_ratio":"LIVE_OR_ARCHIVED_TRADES",
 "book_imbalance":"LIVE_ONLY",
 "book_velocity":"LIVE_ONLY",
 "cancel_rate":"LIVE_ONLY",
 "wall_ratio":"LIVE_ONLY",
 "wall_replenishment":"LIVE_ONLY",
 "spread_bps":"LIVE_ONLY",
}

@dataclass(frozen=True)
class ScalpContext:
    symbol:str
    event_ts_ms:int
    level_kind:str
    level_price:float
    direction:int
    state:str
    features:dict
    capabilities:dict

def normalize_direction(v):
    if isinstance(v,str):
        x=v.lower()
        if x in ("long","buy","bullish","up"):return 1
        if x in ("short","sell","bearish","down"):return -1
    try:return 1 if float(v)>0 else -1 if float(v)<0 else 0
    except (TypeError,ValueError):return 0

def capability_mask(features):
    return {k:FEATURE_CAPABILITY.get(k,"EXPERIMENTAL") for k in features}

def scalp_tokens(ctx:ScalpContext):
    f=ctx.features
    out=[
      f"state={ctx.state}",f"level={ctx.level_kind}",
      f"vol={f.get('volatility_regime','UNKNOWN')}",
      f"direction={ctx.direction}",
    ]
    for k in ("volume_expansion","tape_speed","book_imbalance","book_velocity","open_interest_rate","delta_ratio"):
        v=f.get(k)
        if v is None:continue
        try:x=float(v)
        except (TypeError,ValueError):continue
        if abs(x)>=3:b="EXTREME"
        elif abs(x)>=2:b="HIGH"
        elif abs(x)>=1:b="ELEVATED"
        else:b="NORMAL"
        out.append(f"{k}={b}")
    return tuple(sorted(out))

def validate_context(ctx:ScalpContext,historical=False):
    if ctx.state not in EVENT_STATES:return False,"invalid state"
    if ctx.direction not in (-1,1):return False,"direction required"
    if ctx.level_price<=0:return False,"level price required"
    if historical:
        forbidden=[k for k,v in ctx.features.items() if v is not None and FEATURE_CAPABILITY.get(k)=="LIVE_ONLY"]
        if forbidden:return False,"historical context contains live-only features: "+",".join(sorted(forbidden))
    return True,None
