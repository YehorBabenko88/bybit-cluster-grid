def breakout_target(level_price,direction,bars):
    """Outcome labels computed only after horizon bars are complete."""
    p=float(level_price)
    if not bars: return {}
    highs=[float(x["high"]) for x in bars]; lows=[float(x["low"]) for x in bars]
    closes=[float(x["close"]) for x in bars]
    if direction=="UP":
        mfe=(max(highs)-p)/p; mae=(p-min(lows))/p
        returned=any(c<p for c in closes)
        end_ret=(closes[-1]-p)/p
    else:
        mfe=(p-min(lows))/p; mae=(max(highs)-p)/p
        returned=any(c>p for c in closes)
        end_ret=(p-closes[-1])/p
    return {"horizon_bars":len(bars),"mfe_pct":mfe,"mae_pct":mae,
            "end_return_pct":end_ret,"returned_through_level":returned,
            "continuation_positive":end_ret>0}
