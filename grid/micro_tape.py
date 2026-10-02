class MicroTapeAggregator:
    """Event-time aggressor-flow buckets for microstructure research."""

    def __init__(self,bucket_ms=250):
        self.bucket_ms=max(50,int(bucket_ms))
        self.state={}
        self.cvd={}

    def _new_bucket(self,start_ms,price):
        return {
            "start_ms":int(start_ms),
            "open":float(price),
            "high":float(price),
            "low":float(price),
            "close":float(price),
            "buy_volume":0.0,
            "sell_volume":0.0,
            "buy_count":0,
            "sell_count":0,
            "trade_count":0,
        }

    def add(self,trade):
        start=(int(trade.ts_ms)//self.bucket_ms)*self.bucket_ms
        cur=self.state.get(trade.symbol)
        closed=None
        if cur is None or cur["start_ms"]!=start:
            if cur is not None:
                closed=self._finalize(trade.symbol,cur)
            cur=self._new_bucket(start,trade.price)
            self.state[trade.symbol]=cur

        price=float(trade.price)
        qty=float(trade.qty)
        cur["high"]=max(cur["high"],price)
        cur["low"]=min(cur["low"],price)
        cur["close"]=price
        cur["trade_count"]+=1

        if str(trade.side).lower()=="buy":
            cur["buy_volume"]+=qty
            cur["buy_count"]+=1
        else:
            cur["sell_volume"]+=qty
            cur["sell_count"]+=1

        return closed

    def flush(self,symbol):
        cur=self.state.pop(symbol,None)
        return self._finalize(symbol,cur) if cur is not None else None

    def _finalize(self,symbol,row):
        delta=row["buy_volume"]-row["sell_volume"]
        cvd=self.cvd.get(symbol,0.0)+delta
        self.cvd[symbol]=cvd
        out=dict(row)
        out["delta"]=delta
        out["cvd"]=cvd
        out["range"]=row["high"]-row["low"]
        out["aggressor_imbalance"]=(
            delta/(row["buy_volume"]+row["sell_volume"])
            if (row["buy_volume"]+row["sell_volume"]) else 0.0
        )
        return out
