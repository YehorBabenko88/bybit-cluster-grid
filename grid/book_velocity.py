class BookVelocity:
    """Rates and side-aware visible book changes.

    A visible size reduction is recorded as removed liquidity, not labelled as
    execution. Trade matching is performed separately.
    """
    def __init__(self):
        self.state={}

    def update(self,symbol,ts_ms,bids,asks):
        cur={"b":dict(bids),"a":dict(asks)}
        prev=self.state.get(symbol)
        self.state[symbol]=(int(ts_ms),cur)
        if prev is None:
            return {
                "book_update_rate":None,"book_add_rate":None,"book_cancel_rate":None,
                "book_consume_rate":None,"depth_change_rate":None,
                "added_bid":0.0,"removed_bid":0.0,"added_ask":0.0,"removed_ask":0.0,
            }
        pts,oldbook=prev
        dt=max((int(ts_ms)-pts)/1000.0,1e-3)
        adds=cancels=0.0; updates=0
        side_changes={"b":{"add":0.0,"remove":0.0},"a":{"add":0.0,"remove":0.0}}
        for side in ("b","a"):
            old=oldbook[side]; new=cur[side]
            for price in set(old)|set(new):
                before=float(old.get(price,0.0)); after=float(new.get(price,0.0))
                if before==after: continue
                updates+=1
                if after>before:
                    diff=after-before; adds+=diff; side_changes[side]["add"]+=diff
                else:
                    diff=before-after; cancels+=diff; side_changes[side]["remove"]+=diff
        old_depth=sum(oldbook["b"].values())+sum(oldbook["a"].values())
        new_depth=sum(cur["b"].values())+sum(cur["a"].values())
        return {
            "book_update_rate":updates/dt,"book_add_rate":adds/dt,
            "book_cancel_rate":cancels/dt,"book_consume_rate":None,
            "depth_change_rate":(new_depth-old_depth)/dt,
            "added_bid":side_changes["b"]["add"],"removed_bid":side_changes["b"]["remove"],
            "added_ask":side_changes["a"]["add"],"removed_ask":side_changes["a"]["remove"],
        }
