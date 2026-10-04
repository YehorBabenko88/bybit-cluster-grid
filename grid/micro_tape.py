class MicroTapeAggregator:
    """Event-time aggressor-flow buckets for microstructure research."""

    def __init__(self,bucket_ms=250,large_trade_mult=5.0,ema_alpha=.05):
        self.bucket_ms=max(50,int(bucket_ms))
        self.large_trade_mult=float(large_trade_mult)
        self.ema_alpha=float(ema_alpha)
        self.state={}
        self.cvd={}
        self.ema_qty={}
        self.latest_closed={}

    def _new_bucket(self,start_ms,price):
        return {
            "start_ms":int(start_ms),
            "open":float(price),"high":float(price),"low":float(price),"close":float(price),
            "buy_volume":0.0,"sell_volume":0.0,
            "large_buy_volume":0.0,"large_sell_volume":0.0,
            "buy_count":0,"sell_count":0,"trade_count":0,
            "first_trade_ts":None,"last_trade_ts":None,
            "first_seq":None,"last_seq":None,
            "block_trade_volume":0.0,"rpi_volume":0.0,"trade_gap":False,
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

        price=float(trade.price); qty=float(trade.qty)
        cur["high"]=max(cur["high"],price); cur["low"]=min(cur["low"],price); cur["close"]=price
        cur["trade_count"]+=1
        cur["first_trade_ts"]=int(trade.ts_ms) if cur["first_trade_ts"] is None else cur["first_trade_ts"]
        cur["last_trade_ts"]=int(trade.ts_ms)
        if trade.seq is not None:
            cur["first_seq"]=int(trade.seq) if cur["first_seq"] is None else min(cur["first_seq"],int(trade.seq))
            cur["last_seq"]=int(trade.seq) if cur["last_seq"] is None else max(cur["last_seq"],int(trade.seq))

        baseline=self.ema_qty.get(trade.symbol)
        is_large=baseline is not None and baseline>0 and qty>=baseline*self.large_trade_mult
        if str(trade.side).lower()=="buy":
            cur["buy_volume"]+=qty; cur["buy_count"]+=1
            if is_large: cur["large_buy_volume"]+=qty
        else:
            cur["sell_volume"]+=qty; cur["sell_count"]+=1
            if is_large: cur["large_sell_volume"]+=qty
        if getattr(trade,"continuity_gap",False): cur["trade_gap"]=True
        if getattr(trade,"block_trade",False): cur["block_trade_volume"]+=qty
        if getattr(trade,"rpi",False): cur["rpi_volume"]+=qty

        self.ema_qty[trade.symbol]=qty if baseline is None else (
            self.ema_alpha*qty+(1-self.ema_alpha)*baseline
        )
        return closed

    def flush(self,symbol):
        cur=self.state.pop(symbol,None)
        return self._finalize(symbol,cur) if cur is not None else None

    def latest(self,symbol):
        row=self.latest_closed.get(symbol)
        return dict(row) if row is not None else None

    def _finalize(self,symbol,row):
        delta=row["buy_volume"]-row["sell_volume"]
        cvd=self.cvd.get(symbol,0.0)+delta
        self.cvd[symbol]=cvd
        out=dict(row)
        out["delta"]=delta; out["cvd"]=cvd; out["range"]=row["high"]-row["low"]
        out["aggressor_imbalance"]=(
            delta/(row["buy_volume"]+row["sell_volume"])
            if (row["buy_volume"]+row["sell_volume"]) else 0.0
        )
        self.latest_closed[symbol]=out
        return out
