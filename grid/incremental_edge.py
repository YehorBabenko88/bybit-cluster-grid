from .trading_evaluation import evaluate_trades

def _overall(trades):
    return evaluate_trades(trades)["overall"]

def compare_variant(base_trades,variant_trades):
    b=_overall(base_trades);v=_overall(variant_trades)
    bn=max(1,b.get("trades",0));vn=max(1,v.get("trades",0))
    return {
      "base_trades":b.get("trades",0),"variant_trades":v.get("trades",0),
      "signals_removed":max(0,b.get("trades",0)-v.get("trades",0)),
      "retention_ratio":v.get("trades",0)/bn,
      "delta_net_pnl":v.get("net_pnl",0)-b.get("net_pnl",0),
      "delta_expectancy":v.get("expectancy",0)-b.get("expectancy",0),
      "delta_max_drawdown":v.get("max_drawdown",0)-b.get("max_drawdown",0),
      "base":b,"variant":v,
    }

def paired_signal_effect(base_trades,variant_trades,key="signal_id"):
    base={x.get(key):x for x in base_trades if x.get(key) is not None}
    kept={x.get(key) for x in variant_trades if x.get(key) is not None}
    removed=[x for k,x in base.items() if k not in kept]
    kept_base=[x for k,x in base.items() if k in kept]
    return {"removed":_overall(removed) if removed else {"trades":0},
            "kept_from_base":_overall(kept_base) if kept_base else {"trades":0},
            "paired_signals":len(base)}
