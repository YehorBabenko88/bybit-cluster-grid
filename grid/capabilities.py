def instrument_capabilities(meta):
    contract=(meta or {}).get("contract_type") or (meta or {}).get("contractType")
    status=(meta or {}).get("status")
    return {
        "trades": status=="Trading",
        "orderbook": status=="Trading",
        "open_interest": contract in ("LinearPerpetual","LinearFutures"),
        "funding": contract=="LinearPerpetual",
        "mark_index": contract in ("LinearPerpetual","LinearFutures"),
    }

def usable_for(feature_family,quality):
    feeds=quality.get("feeds",{})
    def ok(name):
        return feeds.get(name,{}).get("status")=="available"
    if feature_family=="footprint":
        return ok("trades")
    if feature_family=="volatility":
        return ok("trades")
    if feature_family=="breakout":
        return ok("trades")
    if feature_family=="poc":
        return ok("trades")
    if feature_family=="book_confirmation":
        return ok("orderbook")
    if feature_family=="oi_confirmation":
        return ok("open_interest")
    return False
