"""Build live scalp-research context from true microstructure feeds."""
from __future__ import annotations
from .scalp_ontology import ScalpContext,validate_context

class LiveScalpAssembler:
    def __init__(self,max_age_ms=3000):
        self.max_age_ms=max(250,int(max_age_ms));self.state={}
    def update(self,symbol,ts_ms,event_type,payload,level=None,volatility_regime="UNKNOWN"):
        s=self.state.setdefault(str(symbol),{});ts=int(ts_ms);p=dict(payload or {})
        s[event_type]=(ts,p)
        if not level:return None
        trade=self._fresh(s.get("trade_tape_250ms"),ts)
        book=self._fresh(s.get("orderbook_snapshot"),ts)
        tick=self._fresh(s.get("derivatives_ticker"),ts)
        if trade is None:return None
        buy=float(trade.get("buy_volume") or 0);sell=float(trade.get("sell_volume") or 0)
        total=max(buy+sell,1e-12);delta=(buy-sell)/total
        updates=float((book or {}).get("book_update_rate") or 0)
        spread=_spread_bps(book or {})
        walls=(book or {}).get("walls") or []
        strongest=max((float(w.get("ratio") or 0) for w in walls),default=0.0)
        replen=max((float(w.get("replenishment_ratio") or 0) for w in walls),default=0.0)
        price=float(trade.get("close") or trade.get("vwap") or 0)
        level_price=float(level["price"]);direction=int(level["direction"])
        dist=abs(price-level_price)/max(price,1e-12)*10000 if price>0 else 999999
        state="LEVEL_APPROACH"
        if float(trade.get("trade_count") or 0)>=5 or abs(delta)>=.35:state="IMPULSE_BUILDUP"
        features={
          "level_distance_bps":dist,"level_kind":str(level.get("kind") or "UNKNOWN"),
          "volatility_regime":str(volatility_regime),
          "volume_expansion":level.get("volume_expansion"),
          "turnover_expansion":level.get("turnover_expansion"),
          "delta_ratio":delta,"cvd_slope":level.get("cvd_slope"),
          "open_interest_rate":(tick or {}).get("open_interest_rate"),
          "funding_rate":(tick or {}).get("funding_rate"),
          "long_short_ratio":level.get("long_short_ratio"),
          "tape_speed":float(trade.get("trade_count") or 0)/.25,
          "large_trade_ratio":level.get("large_trade_ratio"),
          "book_imbalance":(book or {}).get("imbalance"),
          "book_velocity":updates,"cancel_rate":(book or {}).get("book_cancel_rate"),
          "wall_ratio":strongest,"wall_replenishment":replen,"spread_bps":spread,
        }
        ctx=ScalpContext(str(symbol),ts,str(level.get("kind") or "UNKNOWN"),level_price,
                         direction,state,features,{})
        ok,_=validate_context(ctx,historical=False)
        return ctx if ok else None
    def _fresh(self,item,now):
        if item is None:return None
        ts,p=item
        return p if now-int(ts)<=self.max_age_ms else None

def _spread_bps(book):
    try:
        bid=float(book.get("best_bid") or 0);ask=float(book.get("best_ask") or 0)
        mid=(bid+ask)/2
        return (ask-bid)/mid*10000 if mid>0 and ask>=bid else None
    except (TypeError,ValueError):return None
