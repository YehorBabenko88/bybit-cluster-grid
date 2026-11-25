"""Out-of-sample entry-pattern screening.

Purpose: reject entry families that are persistently loss-making, not optimize them
until they fit one historical interval.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import sqrt

@dataclass(frozen=True)
class EntryPatternVerdict:
    pattern:str
    status:str
    samples:int
    profitable_folds:int
    losing_folds:int
    mean_expectancy:float
    mean_profit_factor:float
    reasons:tuple[str,...]

def _metric(x,name,default=0.0):
    if isinstance(x,dict):return float(x.get(name,default) or default)
    return float(getattr(x,name,default) or default)

def screen_entry_pattern(pattern,fold_metrics,*,min_folds=3,min_samples=60,
                         min_profitable_fraction=.60,min_expectancy=0.0,
                         min_profit_factor=1.05,max_loss_fold_fraction=.50):
    xs=list(fold_metrics);samples=sum(int(_metric(x,"trades")) for x in xs)
    ex=[_metric(x,"expectancy") for x in xs];pf=[_metric(x,"profit_factor") for x in xs]
    profitable=sum(1 for a,b in zip(ex,pf) if a>min_expectancy and b>=min_profit_factor)
    losing=sum(1 for a,b in zip(ex,pf) if a<0 or b<1.0)
    reasons=[]
    if len(xs)<min_folds:reasons.append("INSUFFICIENT_FOLDS")
    if samples<min_samples:reasons.append("INSUFFICIENT_SAMPLES")
    if xs and profitable/len(xs)<min_profitable_fraction:reasons.append("UNSTABLE_OOS_EDGE")
    if xs and losing/len(xs)>max_loss_fold_fraction:reasons.append("MAJORITY_LOSS_MAKING")
    mean_e=sum(ex)/len(ex) if ex else 0.0
    finite_pf=[x for x in pf if x<1e100]
    mean_pf=sum(finite_pf)/len(finite_pf) if finite_pf else 0.0
    if mean_e<=min_expectancy:reasons.append("NON_POSITIVE_EXPECTANCY")
    if mean_pf<min_profit_factor:reasons.append("LOW_PROFIT_FACTOR")
    status="REJECT" if any(x in reasons for x in
      ("MAJORITY_LOSS_MAKING","NON_POSITIVE_EXPECTANCY","LOW_PROFIT_FACTOR")) else (
      "KEEP" if not reasons else "NEEDS_MORE_DATA")
    return EntryPatternVerdict(str(pattern),status,samples,profitable,losing,mean_e,mean_pf,tuple(reasons))

def segment_verdicts(pattern,trades,segment_keys=("volatility_regime","symbol","level_kind")):
    """Expose where an otherwise good entry is structurally bad."""
    out={}
    for key in segment_keys:
        groups={}
        for t in trades:
            md=getattr(t,"metadata",{}) or {}
            groups.setdefault(str(md.get(key,"UNKNOWN")),[]).append(t)
        out[key]={}
        for value,xs in groups.items():
            nets=[float(getattr(x,"net_pnl",0)) for x in xs]
            out[key][value]={
              "trades":len(xs),"expectancy":sum(nets)/len(nets) if nets else 0.0,
              "win_rate":sum(1 for x in nets if x>0)/len(nets) if nets else 0.0}
    return out
