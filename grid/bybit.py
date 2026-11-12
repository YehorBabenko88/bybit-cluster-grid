import asyncio
import logging
import random
import hashlib
import json
from dataclasses import dataclass
from urllib.parse import urlsplit

import aiohttp

log=logging.getLogger("bybit")

_RETRYABLE_STATUS={408,425,429,500,502,503,504}


@dataclass(frozen=True)
class _HttpBody:
    """Local HTTP entity-body facts, not network-wire or storage evidence."""
    status: int
    body: bytes
    body_sha256: str
    content_encoding: str


@dataclass(frozen=True)
class LinearInstrumentPage:
    """A single page must never be used as a full registry universe."""
    items: tuple[dict, ...]
    next_cursor: str | None
    completeness: str
    response: _HttpBody


def _bounded_int(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"invalid {name}")
    return value


def _https_origin(base_url):
    if not isinstance(base_url, str) or len(base_url) > 2048:
        raise ValueError("invalid HTTPS origin")
    parsed = urlsplit(base_url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment or any(c.isspace() for c in base_url)):
        raise ValueError("invalid HTTPS origin")
    # Validate port syntax before constructing any client. This is not admission.
    parsed.port
    return base_url.rstrip("/")


async def _read_bounded_http_response(response, *, max_body_bytes: int = 1048576) -> _HttpBody:
    _bounded_int(max_body_bytes, "body limit", 1, 1048576)
    response.raise_for_status()
    if type(response.status) is not int or not 200 <= response.status < 300:
        raise ValueError("unsuccessful HTTP status")
    encoding = response.headers.get("Content-Encoding", "identity")
    if not isinstance(encoding, str) or encoding.strip().lower() != "identity":
        raise ValueError("unsupported HTTP content encoding")
    chunks = []
    size = 0
    while True:
        chunk = await response.content.read(min(65536, max_body_bytes - size + 1))
        if not isinstance(chunk, bytes):
            raise ValueError("invalid HTTP body chunk")
        size += len(chunk)
        if size > max_body_bytes:
            raise ValueError("HTTP body limit exceeded")
        if not chunk:
            break
        chunks.append(chunk)
    body = b"".join(chunks)
    return _HttpBody(response.status, body, hashlib.sha256(body).hexdigest(), "identity")


def _bounded_result(response):
    payload = json.loads(response.body.decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("retCode") != 0:
        raise ValueError("invalid or unsuccessful Bybit response")
    result = payload.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("list"), list):
        raise ValueError("Bybit response missing result.list")
    return result


async def fetch_linear_instruments_page(base_url: str, *, cursor: str | None = None,
                                        limit: int = 1000) -> LinearInstrumentPage:
    """One request only; no retries, normalization, registry update or admission."""
    origin = _https_origin(base_url)
    _bounded_int(limit, "page limit", 1, 1000)
    if cursor is not None and (not isinstance(cursor, str) or not cursor
                               or len(cursor.encode("utf-8")) > 4096):
        raise ValueError("invalid cursor")
    params = {"category": "linear", "limit": limit}
    if cursor is not None:
        params["cursor"] = cursor
    timeout = aiohttp.ClientTimeout(total=35, connect=10, sock_read=30)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=False,
                                    auto_decompress=False, cookie_jar=aiohttp.DummyCookieJar(),
                                    headers={"Accept-Encoding": "identity"}) as session:
        async with session.get(origin + "/v5/market/instruments-info", params=params,
                               allow_redirects=False) as response:
            raw = await _read_bounded_http_response(response)
    result = _bounded_result(raw)
    if any(not isinstance(item, dict) for item in result["list"]):
        raise ValueError("invalid instrument page record")
    next_cursor = result.get("nextPageCursor")
    if next_cursor is not None and (not isinstance(next_cursor, str)
                                    or len(next_cursor.encode("utf-8")) > 4096):
        raise ValueError("invalid next cursor")
    return LinearInstrumentPage(tuple(result["list"]), next_cursor or None, "INCOMPLETE", raw)


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
