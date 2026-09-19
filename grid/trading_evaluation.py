import math,statistics
from collections import defaultdict

def _metrics(trades):
    n=len(trades)
    if not n:return {"trades":0}
    pnl=[float(x.get("pnl",0)) for x in trades]
    wins=[x for x in pnl if x>0]; losses=[x for x in pnl if x<0]
    equity=0.0;peak=0.0;max_dd=0.0
    for x in pnl:
        equity+=x;peak=max(peak,equity);max_dd=max(max_dd,peak-equity)
    gross_win=sum(wins);gross_loss=-sum(losses)
    return {
      "trades":n,"net_pnl":sum(pnl),"expectancy":sum(pnl)/n,
      "hit_rate":len(wins)/n,"profit_factor":gross_win/gross_loss if gross_loss>0 else None,
      "max_drawdown":max_dd,
      "median_mfe":statistics.median(float(x.get("mfe",0)) for x in trades),
      "median_mae":statistics.median(float(x.get("mae",0)) for x in trades),
    }

def evaluate_trades(trades):
    rows=[dict(x) for x in trades]
    segments={"overall":_metrics(rows)}
    for field in ("symbol","regime","setup_type","fold"):
        groups=defaultdict(list)
        for r in rows: groups[str(r.get(field,"UNKNOWN"))].append(r)
        segments[field]={k:_metrics(v) for k,v in sorted(groups.items())}
    return segments

def stability_summary(report,min_trades=20):
    vals=[]
    for field in ("symbol","regime","setup_type","fold"):
        for m in report.get(field,{}).values():
            if m.get("trades",0)>=min_trades: vals.append(m.get("expectancy",0))
    return {"eligible_segments":len(vals),"positive_segments":sum(v>0 for v in vals),
            "positive_fraction":sum(v>0 for v in vals)/len(vals) if vals else None,
            "worst_expectancy":min(vals) if vals else None}
