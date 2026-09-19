import aiohttp

async def linear_symbols(base_url: str):
    out=[]; cursor=None
    async with aiohttp.ClientSession() as s:
        while True:
            params={"category":"linear","limit":1000}
            if cursor: params["cursor"]=cursor
            async with s.get(base_url+"/v5/market/instruments-info",params=params,timeout=30) as r:
                r.raise_for_status(); j=await r.json()
            for x in j["result"]["list"]:
                if x.get("status")=="Trading" and x.get("contractType") in ("LinearPerpetual","LinearFutures"):
                    out.append({
                        "symbol":x["symbol"],
                        "tick_size":float(x["priceFilter"]["tickSize"]),
                        "contract_type":x.get("contractType"),
                        "status":x.get("status"),
                        "settle_coin":x.get("settleCoin"),
                        "launch_time":x.get("launchTime"),
                        "delivery_time":x.get("deliveryTime"),
                    })
            cursor=j["result"].get("nextPageCursor")
            if not cursor: break
    return out
