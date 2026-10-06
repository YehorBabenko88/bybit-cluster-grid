"""Unified training policy for historical priors, live learning and paper simulation."""
from __future__ import annotations

SOURCE_POLICIES={
    "HISTORICAL_STRATTESTER":{
        "may_seed_features":True,"may_seed_hypotheses":True,"may_validate_live":False,
        "may_paper_trade":False,"requires_l2":False},
    "LIVE_GRID":{
        "may_seed_features":True,"may_seed_hypotheses":True,"may_validate_live":True,
        "may_paper_trade":False,"requires_l2":False},
    "LIVE_L2":{
        "may_seed_features":True,"may_seed_hypotheses":True,"may_validate_live":True,
        "may_paper_trade":False,"requires_l2":True},
    "SIMULATION_GATE":{
        "may_seed_features":False,"may_seed_hypotheses":False,"may_validate_live":False,
        "may_paper_trade":True,"requires_l2":False},
}

SCALP_TARGETS=("impulse_entry","level_break","level_rejection","follow_through","failed_breakout")

def training_source_policy(source):
    try:return dict(SOURCE_POLICIES[str(source)])
    except KeyError:raise ValueError("unknown training source")

def paper_eligible(*,scientific_status,simulation_status,phase):
    return (str(scientific_status)=="VALIDATED"
            and str(simulation_status)=="SIMULATION_PASSED"
            and str(phase)=="PAPER_TRADING")

def historical_feature_allowed(name):
    from .scalp_ontology import FEATURE_CAPABILITY
    return FEATURE_CAPABILITY.get(str(name))!="LIVE_ONLY"

def merge_training_context(historical,live):
    """Live values override historical priors only when actually observed."""
    out=dict(historical or {})
    for k,v in dict(live or {}).items():
        if v is not None:out[k]=v
    return out

def conflict_flags(historical,live):
    flags=[]
    h=dict(historical or {});l=dict(live or {})
    for k,v in h.items():
        if k in l and l[k] is not None and v is not None:
            try:
                a=float(v);b=float(l[k])
                scale=max(abs(a),abs(b),1e-12)
                if abs(a-b)/scale>1.0:flags.append({"feature":k,"kind":"REGIME_SHIFT","historical":a,"live":b})
            except (TypeError,ValueError):
                if v!=l[k]:flags.append({"feature":k,"kind":"CATEGORY_SHIFT","historical":v,"live":l[k]})
    return flags
