"""Research-only causal tape signals inspired by VPA, tape reading, profile and price action.

Uses *past and current* completed trade-tape buckets only. Bucket-close
volume profile is a proxy, NOT a true exchange price-level footprint.
Never submits orders or promotes a model into live trading.
"""
from __future__ import annotations
from collections import defaultdict, deque
from math import isfinite

VERSION="book-tape-research-v1"


def _positive(value):
    try:
        number=float(value)
    except (ValueError,TypeError,OverflowError):
        return None
    return number if isfinite(number) and number>0 else None


def _nonnegative(value):
    try:
        number=float(value)
    except (ValueError,TypeError,OverflowError):
        return None
    return number if isfinite(number) and number>=0 else None


class BookTapeResearch:
    """Bounded, per-symbol causal observations; no lookahead or executions."""
    def __init__(self,window=32,min_history=8):
        if not isinstance(window,int) or isinstance(window,bool) or window<8:
            raise ValueError("window must be an integer >= 8")
        if not isinstance(min_history,int) or isinstance(min_history,bool) or not 4<=min_history<=window:
            raise ValueError("min_history must be between 4 and window")
        self.window=window
        self.min_history=min_history
        self.history=defaultdict(lambda:deque(maxlen=self.window))
        self.last_ts={}

    def observe(self,event):
        symbol=str(event.get("symbol") or "")
        if not symbol or event.get("event_type")!="trade_tape_250ms":
            return {"version":VERSION,"eligible":False,"reason":"unsupported_event"}
        payload=event.get("payload") or {}
        if not isinstance(payload,dict):
            return {"version":VERSION,"eligible":False,"reason":"invalid_payload"}
        ts=event.get("event_ts")
        if hasattr(ts,"timestamp"):
            ts=int(ts.timestamp()*1000)
        else:
            try:ts=int(ts)
            except (ValueError,TypeError,OverflowError):ts=None
        close=_positive(payload.get("close"))
        buy=_nonnegative(payload.get("buy_volume"))
        sell=_nonnegative(payload.get("sell_volume"))
        if ts is None or ts<=0 or close is None or buy is None or sell is None or buy+sell<=0:
            return {"version":VERSION,"eligible":False,"reason":"invalid_trade_bucket"}
        if ts<=self.last_ts.get(symbol,-1):
            return {"version":VERSION,"eligible":False,"reason":"replayed_or_out_of_order"}
        self.last_ts[symbol]=ts
        volume=buy+sell
        history=self.history[symbol]
        past=list(history)
        history.append((ts,close,volume,buy-sell))
        if len(past)<self.min_history:
            return {"version":VERSION,"eligible":False,"reason":"warmup","samples":len(history)}
        volumes=[x[2] for x in past]
        prices=[x[1] for x in past]
        avg_volume=sum(volumes)/len(volumes)
        relative_volume=volume/avg_volume if avg_volume>0 else 0.0
        delta_ratio=(buy-sell)/volume
        previous=prices[-1]
        high=max(prices)
        low=min(prices)
        # Price/volume confirmation and effort-versus-result anomaly (Coulling).
        direction=1 if close>previous else -1 if close<previous else 0
        effort_anomaly=relative_volume>=1.8 and abs(close-previous)/previous<0.0002
        volume_confirmation=relative_volume>=1.2 and direction*delta_ratio>=0.2
        # Past-only narrow base + expansion (Graifer/Schumacher).
        base=prices[-min(5,len(prices)):]
        base_high=max(base)
        base_low=min(base)
        base_width=(base_high-base_low)/previous
        breakout_long=close>base_high and base_width<=0.004 and relative_volume>=1.2 and delta_ratio>0.15
        breakout_short=close<base_low and base_width<=0.004 and relative_volume>=1.2 and delta_ratio< -0.15
        # Past-close weighted price proxy; not true price-level VAP (Forthmann).
        profile={}
        for _,price,qty,_ in past:
            profile[price]=profile.get(price,0.0)+qty
        proxy_poc=max(profile,key=profile.get)
        # Trend-bar continuation proxy (Brooks): recent directional closes.
        tail=prices[-4:]+[close]
        up_steps=sum(b>a for a,b in zip(tail,tail[1:]))
        down_steps=sum(b<a for a,b in zip(tail,tail[1:]))
        trend_long=up_steps>=3 and close>high
        trend_short=down_steps>=3 and close<low
        long_votes=int(breakout_long)+int(trend_long)+int(volume_confirmation and direction==1)
        short_votes=int(breakout_short)+int(trend_short)+int(volume_confirmation and direction==-1)
        # Fail closed on conflicting evidence or high-effort no-result anomalies.
        signal=1 if long_votes>=2 and short_votes==0 and not effort_anomaly else -1 if short_votes>=2 and long_votes==0 and not effort_anomaly else 0
        return {"version":VERSION,"eligible":True,"symbol":symbol,"ts_ms":ts,
                "direction":signal,"decision":"PAPER_CANDIDATE" if signal else "ABSTAIN",
                "patterns":{"jbe_proxy":breakout_long,"dbi_proxy":breakout_short,
                            "trend_continuation_long":trend_long,"trend_continuation_short":trend_short,
                            "volume_confirmation":volume_confirmation,
                            "effort_result_anomaly":effort_anomaly},
                "features":{"relative_volume":round(relative_volume,6),
                            "delta_ratio":round(delta_ratio,6),
                            "base_width_fraction":round(base_width,8),
                            "proxy_poc":proxy_poc,
                            "proxy_poc_distance":round((close-proxy_poc)/close,8)},
                "data_limitations":["250ms bucket-close profile is not true executed-price VAP",
                                    "trade bucket lacks intrabar high/low and order-level absorption"]}
