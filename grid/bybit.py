import asyncio
import logging
import random

import aiohttp

log=logging.getLogger("bybit")

_RETRYABLE_STATUS={408,425,429,500,502,503,504}


async def linear_symbols(base_url: str, *, max_attempts: int = 8):
    """Return the active linear universe with bounded retry and cursor-loop protection.

    Discovery is control-plane input: transient exchange/network failures are retried,
    but malformed successful responses fail closed instead of silently producing an
    empty or partial universe.
    """
    out=[]
    cursor=None
    seen_cursors=set()
    timeout=aiohttp.ClientTimeout(total=35,connect=10,sock_read=30)

    async with aiohttp.ClientSession(timeout=timeout) as s:
        while True:
            params={"category":"linear","limit":1000}
            if cursor:
                params["cursor"]=cursor

            payload=None
            for attempt in range(1,max(1,int(max_attempts))+1):
                try:
                    async with s.get(base_url.rstrip("/")+"/v5/market/instruments-info",params=params) as resp:
                        if resp.status in _RETRYABLE_STATUS:
                            retry_after=resp.headers.get("Retry-After")
                            if attempt>=max_attempts:
                                resp.raise_for_status()
                            try:
                                delay=float(retry_after) if retry_after else min(30.0,2**(attempt-1))
                            except (TypeError,ValueError):
                                delay=min(30.0,2**(attempt-1))
                            delay+=random.uniform(0,min(1.0,delay*0.1))
                            log.warning("Bybit discovery retry",extra={"event":"bybit_discovery_retry","status":resp.status,"attempt":attempt})
                            await asyncio.sleep(delay)
                            continue
                        resp.raise_for_status()
                        payload=await resp.json(content_type=None)
                    break
                except asyncio.CancelledError:
                    raise
                except (aiohttp.ClientError,asyncio.TimeoutError,ValueError):
                    if attempt>=max_attempts:
                        raise
                    delay=min(30.0,2**(attempt-1))+random.uniform(0,0.5)
                    log.warning("Bybit discovery transport retry",extra={"event":"bybit_discovery_retry","attempt":attempt})
                    await asyncio.sleep(delay)

            if not isinstance(payload,dict):
                raise RuntimeError("Bybit discovery returned invalid payload")
            if payload.get("retCode",0)!=0:
                raise RuntimeError(f"Bybit discovery error {payload.get('retCode')}: {payload.get('retMsg','unknown')}")
            result=payload.get("result")
            if not isinstance(result,dict) or not isinstance(result.get("list"),list):
                raise RuntimeError("Bybit discovery response is missing result.list")

            for x in result["list"]:
                if not isinstance(x,dict):
                    raise RuntimeError("Bybit discovery contains malformed instrument record")
                try:
                    if x.get("status")=="Trading" and x.get("contractType") in ("LinearPerpetual","LinearFutures"):
                        tick=float(x["priceFilter"]["tickSize"])
                        if tick<=0:
                            raise ValueError("non-positive tick")
                        out.append({
                            "symbol":x["symbol"],
                            "tick_size":tick,
                            "contract_type":x.get("contractType"),
                            "status":x.get("status"),
                            "settle_coin":x.get("settleCoin"),
                            "launch_time":x.get("launchTime"),
                            "delivery_time":x.get("deliveryTime"),
                        })
                except (KeyError,TypeError,ValueError) as exc:
                    # Skipping an active contract can falsely retire it later.
                    raise RuntimeError("Bybit discovery malformed instrument: "+str(x.get("symbol","?"))) from exc

            next_cursor=result.get("nextPageCursor") or None
            if not next_cursor:
                break
            if next_cursor==cursor or next_cursor in seen_cursors:
                raise RuntimeError("Bybit discovery cursor loop detected")
            seen_cursors.add(next_cursor)
            cursor=next_cursor

    # Defensive de-duplication across paginated responses while preserving order.
    unique={}
    for item in out:
        unique[item["symbol"]]=item
    if not unique:
        # An empty successful snapshot is not proof that every contract delisted.
        # Preserve the last known universe instead of mass-retiring instruments.
        raise RuntimeError("Bybit discovery returned an empty active linear universe")
    return list(unique.values())
