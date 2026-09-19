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
