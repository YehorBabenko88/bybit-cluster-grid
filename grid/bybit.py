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
    """Discover a COMPLETE linear universe through the sole bounded page reader.

    This is the existing Worker discovery entrypoint, not a second Bybit
    client. A failed or partial scan never replaces the current registry.
    """
    _bounded_int(max_attempts,"discovery attempts",1,16)
    out=[]
    cursor=None
    seen_cursors=set()
    for page_number in range(128):
        page=None
        for attempt in range(1,max_attempts+1):
            try:
                page=await fetch_linear_instruments_page(base_url,cursor=cursor)
                break
            except asyncio.CancelledError:
                raise
            except aiohttp.ClientResponseError as exc:
                if exc.status not in _RETRYABLE_STATUS or attempt==max_attempts:
                    raise
                delay=min(30.0,2**(attempt-1))
                raw_hint=exc.headers.get("Retry-After") if exc.headers else None
                try:
                    hinted=float(raw_hint) if raw_hint is not None else 0.0
                except (TypeError,ValueError,OverflowError):
                    hinted=0.0
                if not 0.0<=hinted<=30.0:
                    hinted=0.0
                delay=max(delay,hinted)
            except (aiohttp.ClientError,asyncio.TimeoutError) as exc:
                if attempt==max_attempts:
                    raise
                delay=min(30.0,2**(attempt-1))
            delay+=random.uniform(0,min(1.0,delay*0.1))
            log.warning("Bybit bounded discovery retry",
                        extra={"event":"bybit_discovery_retry","attempt":attempt})
            await asyncio.sleep(delay)
        if page is None:
            raise RuntimeError("Bybit discovery page unavailable")
        for x in page.items:
            try:
                if x.get("status")=="Trading" and x.get("contractType") in ("LinearPerpetual","LinearFutures"):
                    tick=float(x["priceFilter"]["tickSize"])
                    if not 0<tick<float("inf"):
                        raise ValueError("nonfinite or nonpositive tick")
                    symbol=x["symbol"]
                    if type(symbol) is not str or not symbol or not symbol.isascii():
                        raise ValueError("invalid symbol")
                    out.append({"symbol":symbol,"tick_size":tick,
                                "contract_type":x.get("contractType"),
                                "status":x.get("status"),
                                "settle_coin":x.get("settleCoin"),
                                "launch_time":x.get("launchTime"),
                                "delivery_time":x.get("deliveryTime")})
            except (KeyError,TypeError,ValueError,OverflowError) as exc:
                raise RuntimeError("Bybit discovery malformed instrument") from exc
        next_cursor=page.next_cursor
        if not next_cursor:
            break
        if next_cursor==cursor or next_cursor in seen_cursors:
            raise RuntimeError("Bybit discovery cursor loop detected")
        seen_cursors.add(next_cursor)
        cursor=next_cursor
    else:
        raise RuntimeError("Bybit discovery exceeded bounded page budget")
    # Never let a partial or empty scan retire the existing instrument universe.
    unique={}
    for item in out:
        unique[item["symbol"]]=item
    if not unique:
        raise RuntimeError("Bybit discovery returned an empty active linear universe")
    return list(unique.values())
