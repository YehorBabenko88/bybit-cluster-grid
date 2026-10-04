import aiohttp,math

class BybitProtocolError(RuntimeError):
    pass

def _ok(payload,operation):
    if not isinstance(payload,dict):
        raise BybitProtocolError(f"{operation}: response is not an object")
    if payload.get("retCode")!=0:
        raise BybitProtocolError(f"{operation}: retCode={payload.get('retCode')} retMsg={payload.get('retMsg')}")
    result=payload.get("result")
    if not isinstance(result,dict):
        raise BybitProtocolError(f"{operation}: result missing")
    return result

def parse_public_trade(item,expected_symbol=None):
    if not isinstance(item,dict):raise BybitProtocolError("publicTrade item is not an object")
    symbol=str(item.get("s") or "")
    if expected_symbol and symbol!=expected_symbol:
        raise BybitProtocolError(f"publicTrade symbol mismatch: {symbol}")
    side=str(item.get("S") or "")
    if side not in ("Buy","Sell"):raise BybitProtocolError(f"invalid publicTrade side: {side}")
    try:
        ts=int(item["T"]);price=float(item["p"]);qty=float(item["v"])
    except (KeyError,TypeError,ValueError) as exc:
        raise BybitProtocolError("invalid publicTrade numeric fields") from exc
    if ts<=0 or not math.isfinite(price) or price<=0 or not math.isfinite(qty) or qty<=0:
        raise BybitProtocolError("invalid publicTrade values")
    seq=item.get("seq")
    try:seq=int(seq) if seq is not None else None
    except (TypeError,ValueError):raise BybitProtocolError("invalid publicTrade seq")
    return {"symbol":symbol,"ts_ms":ts,"price":price,"qty":qty,"side":side,
            "trade_id":str(item.get("i") or ""),"seq":seq,
            "block_trade":bool(item.get("BT",False)),"rpi":bool(item.get("RPI",False))}

async def linear_symbols(base_url: str):
    out=[]; cursor=None; seen=set()
    async with aiohttp.ClientSession() as s:
        while True:
            params={"category":"linear","limit":1000}
            if cursor: params["cursor"]=cursor
            async with s.get(base_url+"/v5/market/instruments-info",params=params,timeout=30) as r:
                r.raise_for_status(); result=_ok(await r.json(),"instruments-info")
            items=result.get("list")
            if not isinstance(items,list):raise BybitProtocolError("instruments-info: result.list missing")
            for x in items:
                if x.get("status")=="Trading" and x.get("contractType") in ("LinearPerpetual","LinearFutures"):
                    symbol=str(x.get("symbol") or "")
                    try:tick=float(x["priceFilter"]["tickSize"])
                    except (KeyError,TypeError,ValueError) as exc:
                        raise BybitProtocolError(f"instruments-info: invalid tick size for {symbol}") from exc
                    if not symbol or not math.isfinite(tick) or tick<=0:
                        raise BybitProtocolError(f"instruments-info: invalid instrument {symbol}")
                    if symbol in seen:continue
                    seen.add(symbol)
                    out.append({
                        "symbol":symbol,"tick_size":tick,
                        "contract_type":x.get("contractType"),"status":x.get("status"),
                        "settle_coin":x.get("settleCoin"),"launch_time":x.get("launchTime"),
                        "delivery_time":x.get("deliveryTime"),
                    })
            next_cursor=str(result.get("nextPageCursor") or "")
            if not next_cursor:break
            if next_cursor==cursor:raise BybitProtocolError("instruments-info cursor did not advance")
            cursor=next_cursor
    return out
