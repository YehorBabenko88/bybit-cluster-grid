from __future__ import annotations
from dataclasses import dataclass
from math import inf

@dataclass(frozen=True)
class TradeMetrics:
    trades:int=0
    wins:int=0
    losses:int=0
    win_rate:float=0.0
    gross_pnl:float=0.0
    net_pnl:float=0.0
    fees:float=0.0
    expectancy:float=0.0
    profit_factor:float=0.0
    max_drawdown:float=0.0
    avg_mae:float=0.0
    avg_mfe:float=0.0
    avg_r_multiple:float=0.0
    avg_holding_ms:float=0.0
    max_consecutive_losses:int=0

def evaluate_trades(trades)->TradeMetrics:
    xs=list(trades)
    if not xs:return TradeMetrics()
    nets=[float(x.net_pnl) for x in xs]
    wins=[x for x in nets if x>0]; losses=[x for x in nets if x<0]
    gross_profit=sum(wins); gross_loss=-sum(losses)
    pf=(gross_profit/gross_loss) if gross_loss>0 else (inf if gross_profit>0 else 0.0)
    equity=0.0; peak=0.0; max_dd=0.0; streak=0; max_streak=0
    for n in nets:
        equity+=n; peak=max(peak,equity); max_dd=max(max_dd,peak-equity)
        if n<0: streak+=1; max_streak=max(max_streak,streak)
        else: streak=0
    md=[getattr(x,'metadata',{}) or {} for x in xs]
    def avg(key):
        vals=[float(m[key]) for m in md if m.get(key) is not None]
        return sum(vals)/len(vals) if vals else 0.0
    holdings=[float(x.exit_time-x.entry_time) for x in xs if getattr(x,'exit_time',None) is not None and getattr(x,'entry_time',None) is not None]
    return TradeMetrics(
        trades=len(xs),wins=len(wins),losses=len(losses),win_rate=len(wins)/len(xs),
        gross_pnl=sum(float(x.gross_pnl) for x in xs),net_pnl=sum(nets),fees=sum(float(x.fees) for x in xs),
        expectancy=sum(nets)/len(xs),profit_factor=pf,max_drawdown=max_dd,
        avg_mae=avg('mae'),avg_mfe=avg('mfe'),avg_r_multiple=avg('r_multiple'),
        avg_holding_ms=sum(holdings)/len(holdings) if holdings else 0.0,max_consecutive_losses=max_streak)
