import json
from .data_quality import completeness

CORE=("return_1m","range_pct","volume_ratio","delta_ratio","close_vs_poc")
MICRO=("book_imbalance","spread","bid_depth","ask_depth")
DERIV=("open_interest","funding_rate")

def event_quality(built):
    f=built.get("features",built)
    caps=built.get("capabilities",{})
    candle_quality=(built.get("quality_status") or f.get("data_quality") or "UNKNOWN").upper()
    core=completeness(CORE,f)
    micro=completeness(MICRO,f) if caps.get("orderbook") else 0.0
    deriv=completeness(DERIV,f) if caps.get("derivatives") else 0.0
    # Core trade/candle evidence is mandatory. Optional feeds enrich but do not fabricate evidence.
    if candle_quality!="GOOD" or core<0.8:
        status="DEGRADED" if candle_quality=="DEGRADED" else "INSUFFICIENT"
    elif caps.get("orderbook") and micro<0.5:
        status="DEGRADED"
    else:
        status="GOOD"
    score=0.65*core+0.25*micro+0.10*deriv
    return {"quality_status":status,"completeness":round(score,6),
            "ml_eligible":status=="GOOD" and core>=0.8,
            "components":{"core":core,"micro":micro,"derivatives":deriv}}
