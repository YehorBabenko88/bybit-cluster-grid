"""Walk-forward evaluator for executable entry patterns."""
from __future__ import annotations
from dataclasses import dataclass
from .execution import simulate_trade,ExecutionPolicy
from .statistics import evaluate_trades
from .entry_screening import screen_entry_pattern
from .resampling import bootstrap_expectancy

@dataclass(frozen=True)
class PatternEvaluation:
    pattern:str
    folds:tuple
    verdict:object
    trades:int
    bootstrap_lower:float|None

def evaluate_entry_signals(pattern,signals,bars,*,policy:ExecutionPolicy,folds=5,
                           embargo_ms=0,min_samples=60):
    rows=sorted(list(bars),key=lambda x:x["t"])
    sigs=sorted(list(signals),key=lambda x:x.decision_time)
    if not rows or not sigs:return PatternEvaluation(pattern,(),screen_entry_pattern(pattern,(),min_samples=min_samples),0,None)
    lo=int(rows[0]["t"]);hi=int(rows[-1]["t"])+policy.bar_ms
    width=max(1,(hi-lo)//max(1,int(folds)));metrics=[];all_trades=[]
    for i in range(int(folds)):
        start=lo+i*width;end=hi if i==folds-1 else lo+(i+1)*width
        test_start=start+int(embargo_ms)
        fold_bars=[b for b in rows if test_start<=int(b["t"])<end]
        if not fold_bars:continue
        trades=[]
        for e in sigs:
            if not(test_start<=int(e.decision_time)<end):continue
            future=[b for b in fold_bars if int(b["t"])>=int(e.decision_time)]
            if not future:continue
            try:
                t=simulate_trade(e.signal,future,policy,{**dict(e.metadata),"pattern":pattern})
            except ValueError:
                continue
            trades.append(t);all_trades.append(t)
        metrics.append(evaluate_trades(trades))
    verdict=screen_entry_pattern(pattern,metrics,min_folds=min(3,int(folds)),min_samples=min_samples)
    ci=None
    if all_trades:
        ci=bootstrap_expectancy([x.net_pnl for x in all_trades],iterations=500,seed=17).lower
        # A positive point estimate is not enough. If uncertainty still includes
        # zero, keep the pattern in research rather than promoting it.
        if verdict.status=="KEEP" and ci<=0:
            verdict=type(verdict)(verdict.pattern,"NEEDS_MORE_DATA",verdict.samples,
              verdict.profitable_folds,verdict.losing_folds,verdict.mean_expectancy,
              verdict.mean_profit_factor,tuple(verdict.reasons)+("BOOTSTRAP_CROSSES_ZERO",))
    return PatternEvaluation(pattern,tuple(metrics),verdict,len(all_trades),ci)
