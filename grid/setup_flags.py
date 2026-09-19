def setup_flags(features,regime,eligible=True):
    """Deterministic labels/signals for later backtests; not execution logic."""
    if not eligible:
        return _empty()
    close_poc=float(features.get("close_vs_poc") or 0)
    delta=float(features.get("delta_ratio") or 0)
    vol=float(features.get("volume_ratio") or 0)
    imb=features.get("book_imbalance")
    imb=float(imb) if imb is not None else None
    expanding=regime in ("EXPANDING","VOLATILE")
    breakout_up=bool(features.get("breakout_up"))
    breakout_down=bool(features.get("breakout_down"))
    flow_long=delta>=0.12 and (imb is None or imb>=0)
    flow_short=delta<=-0.12 and (imb is None or imb<=0)
    return {
        "breakout_long_candidate": expanding and breakout_up and vol>=1.2 and flow_long,
        "breakout_short_candidate": expanding and breakout_down and vol>=1.2 and flow_short,
        "poc_above": close_poc>0,
        "poc_below": close_poc<0,
        "poc_near": abs(close_poc)<=0.0015,
        "poc_long_context": regime in ("EXPANDING","VOLATILE") and close_poc>=0 and delta>0,
        "poc_short_context": regime in ("EXPANDING","VOLATILE") and close_poc<=0 and delta<0,
    }

def _empty():
    return {"breakout_long_candidate":False,"breakout_short_candidate":False,
            "poc_above":False,"poc_below":False,"poc_near":False,
            "poc_long_context":False,"poc_short_context":False}
