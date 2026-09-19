def apply_sizing(trades,mode="FIXED",base_size=1.0,multiplier=2.0,max_steps=3,max_size=4.0):
    """Research-only position sizing. Never places orders."""
    out=[];step=0
    for row in trades:
        x=dict(row)
        if mode=="FIXED":size=float(base_size)
        elif mode=="MARTINGALE":
            size=min(float(max_size),float(base_size)*(float(multiplier)**step))
        elif mode=="ANTI_MARTINGALE":
            size=min(float(max_size),float(base_size)*(float(multiplier)**step))
        else:raise ValueError("unknown sizing mode")
        x["sizing_mode"]=mode;x["size_multiplier"]=size
        for k in ("pnl","fees","slippage","mfe","mae"):
            if k in x and x[k] is not None:x[k]=float(x[k])*size
        net=float(x.get("pnl",0))-float(x.get("fees",0))-float(x.get("slippage",0))
        out.append(x)
        if mode=="MARTINGALE":step=min(int(max_steps),step+1) if net<0 else 0
        elif mode=="ANTI_MARTINGALE":step=min(int(max_steps),step+1) if net>0 else 0
    return out

def ruin_stats(trades,starting_equity=100.0,ruin_fraction=.5):
    equity=peak=float(starting_equity);min_eq=equity;max_dd=0.0
    ruined=False;threshold=starting_equity*float(ruin_fraction)
    for x in trades:
        equity+=float(x.get("pnl",0))-float(x.get("fees",0))-float(x.get("slippage",0))
        peak=max(peak,equity);min_eq=min(min_eq,equity);max_dd=max(max_dd,peak-equity)
        if equity<=threshold:ruined=True
    return {"ending_equity":equity,"min_equity":min_eq,"max_drawdown":max_dd,
            "ruin_threshold":threshold,"ruined":ruined}
