from dataclasses import dataclass

@dataclass
class BookLevel:
    price: float
    qty: float

def analyze_book(bids, asks, top_n=50, wall_mult=4.0):
    bids=sorted(bids,key=lambda x:x[0],reverse=True)[:top_n]
    asks=sorted(asks,key=lambda x:x[0])[:top_n]
    bid_depth=sum(q for _,q in bids); ask_depth=sum(q for _,q in asks)
    total=bid_depth+ask_depth
    imbalance=(bid_depth-ask_depth)/total if total else 0.0
    best_bid=bids[0][0] if bids else None; best_ask=asks[0][0] if asks else None
    spread=(best_ask-best_bid) if best_bid is not None and best_ask is not None else None
    qs=[q for _,q in bids+asks]
    avg=(sum(qs)/len(qs)) if qs else 0.0
    walls=[]
    if avg:
        walls += [{"side":"bid","price":p,"qty":q,"ratio":q/avg} for p,q in bids if q>=avg*wall_mult]
        walls += [{"side":"ask","price":p,"qty":q,"ratio":q/avg} for p,q in asks if q>=avg*wall_mult]
    return {"best_bid":best_bid,"best_ask":best_ask,"spread":spread,
            "bid_depth":bid_depth,"ask_depth":ask_depth,"imbalance":imbalance,"walls":walls,
            "book":{"bids":bids,"asks":asks}}

def parse_book_levels(levels, *, snapshot=False):
    """Validate exchange price/size before allowing an orderbook mutation."""
    import math
    if not isinstance(levels,list):
        raise ValueError("orderbook levels must be a list")
    # A depth-50 feed must not allocate arbitrarily large malformed frames.
    if len(levels)>200:
        raise ValueError("orderbook frame exceeds level limit")
    parsed={}
    for level in levels:
        if not isinstance(level,(list,tuple)) or len(level)!=2:
            raise ValueError("invalid orderbook level shape")
        try:
            price=float(level[0]); qty=float(level[1])
        except (TypeError,ValueError,OverflowError) as exc:
            raise ValueError("invalid orderbook price or size") from exc
        if not math.isfinite(price) or price<=0 or not math.isfinite(qty) or qty<0:
            raise ValueError("nonfinite or negative orderbook price/size")
        if snapshot and qty==0:
            raise ValueError("zero-sized level in orderbook snapshot")
        if price in parsed:
            raise ValueError("duplicate orderbook price level")
        parsed[price]=qty
    return parsed
