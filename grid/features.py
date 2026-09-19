from collections import deque
from math import sqrt

class FeatureEngine:
    """Online features aimed at volatility, impulse/breakout and POC setups."""
    def __init__(self, lookback=60):
        self.lookback=lookback
        self.hist={}

    def on_candle(self,row):
        h=self.hist.setdefault(row["symbol"],deque(maxlen=self.lookback+1))
        quality=(row.get("quality_status") or "UNKNOWN").upper()
        eligible=quality=="GOOD"
        prev=list(h)
        close=float(row["close"]); high=float(row["high"]); low=float(row["low"])
        volume=float(row["buy_volume"])+float(row["sell_volume"])
        delta=float(row["delta"])
        ret=0.0
        if prev and float(prev[-1]["close"]):
            ret=close/float(prev[-1]["close"])-1.0
        returns=[]
        for a,b in zip(prev,prev[1:]):
            ac=float(a["close"]); bc=float(b["close"])
            if ac: returns.append(bc/ac-1.0)
        rv=sqrt(sum(x*x for x in returns)/len(returns)) if returns else 0.0
        volumes=[float(x["buy_volume"])+float(x["sell_volume"]) for x in prev]
        avg_vol=sum(volumes)/len(volumes) if volumes else 0.0
        vol_ratio=volume/avg_vol if avg_vol else 0.0
        prior_high=max((float(x["high"]) for x in prev),default=high)
        prior_low=min((float(x["low"]) for x in prev),default=low)
        breakout_up=close>prior_high if prev else False
        breakout_down=close<prior_low if prev else False
        rng=max(high-low,1e-18)
        delta_ratio=delta/volume if volume else 0.0
        poc=float(row["poc_price"]) if row.get("poc_price") is not None else close
        feature={
            "data_quality":quality,
            "eligible":eligible,
            "return_1m":ret,
            "realized_volatility":rv,
            "range_pct":rng/close if close else 0.0,
            "volume_ratio":vol_ratio,
            "delta_ratio":delta_ratio,
            "breakout_up":breakout_up,
            "breakout_down":breakout_down,
            "breakout_distance":(close-prior_high)/close if breakout_up and close else ((prior_low-close)/close if breakout_down and close else 0.0),
            "close_vs_poc":(close-poc)/close if close else 0.0,
            "poc_location":(poc-low)/rng,
        }
        if eligible:
            h.append(row)
        return feature
