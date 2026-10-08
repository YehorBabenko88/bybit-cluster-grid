class BookVelocity:
    """Rates of visible book changes. Removals are not labelled executions without trade matching."""
    def __init__(self):
        self.state={}

    def update(self,symbol,ts_ms,bids,asks):
        cur={"b":dict(bids),"a":dict(asks)}
        prev=self.state.get(symbol)
        if prev is None:
            self.state[symbol]=(int(ts_ms),cur)
            return {"book_update_rate":None,"book_add_rate":None,"book_cancel_rate":None,
                    "book_consume_rate":None,"depth_change_rate":None}
        pts,oldbook=prev
        if int(ts_ms)<=pts:
            # Never fabricate extreme per-second rates from duplicate or
            # backwards exchange timestamps. Keep the last valid baseline.
            return {"book_update_rate":None,"book_add_rate":None,"book_cancel_rate":None,
                    "book_consume_rate":None,"depth_change_rate":None}
        self.state[symbol]=(int(ts_ms),cur)
        dt=(int(ts_ms)-pts)/1000.0
        adds=cancels=0.0; updates=0
        for side in ("b","a"):
            old=oldbook[side]; new=cur[side]
            for price in set(old)|set(new):
                before=float(old.get(price,0.0)); after=float(new.get(price,0.0))
                if before==after: continue
                updates+=1
                if after>before: adds+=after-before
                else: cancels+=before-after
        old_depth=sum(oldbook["b"].values())+sum(oldbook["a"].values())
        new_depth=sum(cur["b"].values())+sum(cur["a"].values())
        return {"book_update_rate":updates/dt,"book_add_rate":adds/dt,
                "book_cancel_rate":cancels/dt,"book_consume_rate":None,
                "depth_change_rate":(new_depth-old_depth)/dt}
