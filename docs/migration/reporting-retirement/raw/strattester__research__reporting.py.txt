from dataclasses import dataclass
from .statistics import evaluate_trades,TradeMetrics

@dataclass(frozen=True)
class ResearchReport:
    primary:TradeMetrics
    partial:TradeMetrics
    by_volatility:dict[str,TradeMetrics]
    partial_by_volatility:dict[str,TradeMetrics]

def _group(xs,key):
    out={}
    for x in xs:
        k=(getattr(x,'metadata',{}) or {}).get(key,'UNKNOWN')
        out.setdefault(k,[]).append(x)
    return {k:evaluate_trades(v) for k,v in out.items()}

def research_report(trades)->ResearchReport:
    xs=list(trades)
    complete=[x for x in xs if (getattr(x,'metadata',{}) or {}).get('coverage')=='COMPLETE_HISTORY']
    partial=[x for x in xs if (getattr(x,'metadata',{}) or {}).get('coverage')=='PARTIAL_HISTORY']
    return ResearchReport(evaluate_trades(complete),evaluate_trades(partial),_group(complete,'volatility'),_group(partial,'volatility'))
