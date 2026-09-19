from .position_sizing_research import apply_sizing,ruin_stats
from .trading_evaluation import evaluate_trades

def sizing_comparison(trades,config=None):
    cfg=config or {};out={}
    for mode in ("FIXED","MARTINGALE","ANTI_MARTINGALE"):
        sized=apply_sizing(trades,mode,
          base_size=float(cfg.get("base_size",1.0)),
          multiplier=float(cfg.get("multiplier",2.0)),
          max_steps=int(cfg.get("max_steps",3)),
          max_size=float(cfg.get("max_size",4.0)))
        out[mode]={"evaluation":evaluate_trades(sized),
          "risk":ruin_stats(sized,float(cfg.get("starting_equity",100.0)),
                            float(cfg.get("ruin_fraction",.5)))}
    return out
