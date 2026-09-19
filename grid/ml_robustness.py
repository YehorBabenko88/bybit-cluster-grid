import random,statistics
from .trading_evaluation import evaluate_trades,stability_summary

def stress_trades(trades,fee_mult=1.0,slippage_mult=1.0,entry_penalty=0.0,drop_rate=0.0,seed=1):
    rng=random.Random(seed);out=[]
    for x in trades:
        if drop_rate and rng.random()<drop_rate:continue
        r=dict(x)
        r["fees"]=float(r.get("fees",0))*fee_mult
        r["slippage"]=float(r.get("slippage",0))*slippage_mult+abs(float(entry_penalty))
        out.append(r)
    return out

def monte_carlo_drawdowns(trades,runs=500,seed=7):
    pnl=[float(x.get("pnl",0))-float(x.get("fees",0))-float(x.get("slippage",0)) for x in trades]
    if not pnl:return {}
    rng=random.Random(seed);dds=[]
    for _ in range(int(runs)):
        seq=list(pnl);rng.shuffle(seq);eq=peak=dd=0.0
        for x in seq:eq+=x;peak=max(peak,eq);dd=max(dd,peak-eq)
        dds.append(dd)
    dds.sort()
    def q(p):return dds[min(len(dds)-1,int((len(dds)-1)*p))]
    return {"runs":len(dds),"dd_p50":q(.50),"dd_p90":q(.90),"dd_p95":q(.95),"dd_p99":q(.99)}

def robustness_suite(trades):
    scenarios={
      "base":trades,
      "fees_x1_5":stress_trades(trades,fee_mult=1.5),
      "slippage_x2":stress_trades(trades,slippage_mult=2.0),
      "execution_delay":stress_trades(trades,entry_penalty=.0005),
      "drop_10pct":stress_trades(trades,drop_rate=.10,seed=11),
      "combined":stress_trades(trades,fee_mult=1.5,slippage_mult=2.0,entry_penalty=.0005,drop_rate=.10,seed=13),
    }
    reports={k:evaluate_trades(v) for k,v in scenarios.items()}
    return {"scenarios":reports,"monte_carlo":monte_carlo_drawdowns(trades),
            "stability":{k:stability_summary(v) for k,v in reports.items()}}
