from datetime import datetime,timezone
import hashlib

def normalize_archive_trade(row):
    """Normalize common Bybit public-trade archive columns without inventing missing fields."""
    lower={str(k).lower():v for k,v in row.items()}
    ts=lower.get("timestamp") or lower.get("time") or lower.get("trade_time")
    if ts is None:raise ValueError("archive trade missing timestamp")
    x=float(ts)
    if x>1e14:x/=1e6
    elif x>1e11:x/=1e3
    side=str(lower.get("side") or lower.get("taker_side") or "").capitalize()
    if side not in ("Buy","Sell"):raise ValueError("archive trade missing taker side")
    price=float(lower.get("price"));size=float(lower.get("size") or lower.get("qty") or lower.get("quantity"))
    trade_id=str(lower.get("trade_id") or lower.get("execid") or lower.get("id") or
                 hashlib.sha256(f"{x}:{price}:{size}:{side}".encode()).hexdigest())
    return {"ts":datetime.fromtimestamp(x,timezone.utc),"price":price,"size":size,
            "side":side,"trade_id":trade_id}

def aggregate_minute(symbol,trades,tick_size):
    buckets={}
    for t in trades:
        ts=t["ts"].replace(second=0,microsecond=0)
        b=buckets.setdefault(ts,{"prices":{},"open":t["price"],"high":t["price"],"low":t["price"],
          "close":t["price"],"buy_volume":0.0,"sell_volume":0.0,"trade_count":0})
        p=float(t["price"]);q=float(t["size"]);side=t["side"]
        b["high"]=max(b["high"],p);b["low"]=min(b["low"],p);b["close"]=p;b["trade_count"]+=1
        if side=="Buy":b["buy_volume"]+=q
        else:b["sell_volume"]+=q
        tick=round(p/float(tick_size))*float(tick_size)
        z=b["prices"].setdefault(tick,{"buy":0.0,"sell":0.0,"buy_count":0,"sell_count":0})
        if side=="Buy":z["buy"]+=q;z["buy_count"]+=1
        else:z["sell"]+=q;z["sell_count"]+=1
    out=[]
    for ts,b in sorted(buckets.items()):
        poc=max(b["prices"],key=lambda p:b["prices"][p]["buy"]+b["prices"][p]["sell"])
        out.append({"symbol":symbol,"ts":ts,**{k:v for k,v in b.items() if k!="prices"},
          "delta":b["buy_volume"]-b["sell_volume"],"poc_price":poc,"levels":b["prices"]})
    return out
