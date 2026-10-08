class WallTracker:
    """Tracks visible liquidity-wall persistence and replenishment.

    It deliberately does not label size reductions as executions; matching
    against the public trade tape is a later research step.
    """

    def __init__(self):
        self.state={}

    def update(self,symbol,ts_ms,walls):
        now=int(ts_ms)
        previous=self.state.get(symbol,{})
        # Do not roll back wall history or double-count liquidity changes when
        # the exchange replays an older analytics timestamp.
        if previous and now<max(item["last_seen_ms"] for item in previous.values()):
            return [],[]
        current={}
        enriched=[]

        for raw in walls:
            side=str(raw["side"])
            price=float(raw["price"])
            qty=float(raw["qty"])
            key=(side,price)
            old=previous.get(key)

            if old is None:
                item={
                    "first_seen_ms":now,
                    "last_seen_ms":now,
                    "last_qty":qty,
                    "peak_qty":qty,
                    "replenished_qty":0.0,
                    "depleted_qty":0.0,
                }
            else:
                item=dict(old)
                before=float(item["last_qty"])
                if qty>before:
                    item["replenished_qty"]+=qty-before
                elif qty<before:
                    item["depleted_qty"]+=before-qty
                item["last_seen_ms"]=now
                item["last_qty"]=qty
                item["peak_qty"]=max(float(item["peak_qty"]),qty)

            current[key]=item
            out=dict(raw)
            out.update({
                "lifetime_ms":max(0,now-int(item["first_seen_ms"])),
                "peak_qty":item["peak_qty"],
                "replenished_qty":item["replenished_qty"],
                "depleted_qty":item["depleted_qty"],
                "replenishment_ratio":(
                    item["replenished_qty"]/max(float(item["peak_qty"]),1e-12)
                ),
            })
            enriched.append(out)

        removed=[]
        for (side,price),item in previous.items():
            if (side,price) in current:
                continue
            removed.append({
                "side":side,
                "price":price,
                "lifetime_ms":max(0,now-int(item["first_seen_ms"])),
                "last_qty":item["last_qty"],
                "peak_qty":item["peak_qty"],
                "replenished_qty":item["replenished_qty"],
                "depleted_qty":item["depleted_qty"],
            })

        self.state[symbol]=current
        return enriched,removed
