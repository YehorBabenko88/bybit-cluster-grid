"""Public Bybit V5 linear perpetual discovery and historical candle pagination."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from decimal import Decimal as D
import httpx
from .http_client import ManagedAsyncClient
from .core import Candle

INTERVALS = {"M1": "1", "H1": "60", "D1": "D", "W1": "W", "MO1": "M"}

class BybitPublic:
    def __init__(self, base="https://api.bybit.com"):
        self.client = ManagedAsyncClient(base_url=base, timeout=20)

    async def get(self, path, params=None):
        for attempt in range(4):
            try:
                resp = await self.client.get(path, params=params)
                resp.raise_for_status()
                body = resp.json()
                if body.get("retCode") == 0:
                    return body["result"]
                raise RuntimeError(f"Bybit response error: {body.get('retCode')} {body.get('retMsg')}")
            except (httpx.HTTPError, RuntimeError):
                if attempt == 3:
                    raise
                await asyncio.sleep(2 ** attempt)

    async def top_volatile(self, count=20, min_turnover=D("1000000")):
        result = await self.get("/v5/market/tickers", {"category": "linear"})
        ranked = []
        for row in result.get("list", []):
            try:
                if not row["symbol"].endswith("USDT"):
                    continue
                turn = D(row.get("turnover24h", "0"))
                last = D(row.get("lastPrice", "0"))
                prev = D(row.get("prevPrice24h", "0"))
                if turn < min_turnover or prev <= 0 or last <= 0:
                    continue
                score = abs(last / prev - 1)
                ranked.append((score, turn, row["symbol"]))
            except (ValueError, KeyError, ArithmeticError):
                continue
        ranked.sort(reverse=True)
        return [symbol for _, _, symbol in ranked[:count]]

    async def market_overview(self, symbols):
        """Public 24h change, turnover and OI for selected USDT perpetuals."""
        result = await self.get("/v5/market/tickers", {"category": "linear"})
        wanted = set(symbols)
        rows = {}
        for row in result.get("list", []):
            symbol = row.get("symbol")
            if symbol not in wanted:
                continue
            try:
                last, prev = D(row["lastPrice"]), D(row["prevPrice24h"])
                turnover = D(row["turnover24h"])
                oi = D(row["openInterest"])
                if not all(v.is_finite() for v in (last, prev, turnover, oi)) or prev <= 0:
                    continue
                rows[symbol] = ((last / prev - 1) * 100, turnover, oi)
            except (KeyError, ValueError, ArithmeticError):
                continue
        return rows

    async def candles(self, symbol: str, timeframe: str, start_ms: int, end_ms: int | None = None):
        """Paged oldest->newest. Caller must persist checkpoints and verify completeness."""
        if timeframe not in INTERVALS:
            raise ValueError("Year must be aggregated from daily data")
        end = end_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
        cursor = end
        seen = set()
        while cursor >= start_ms:
            result = await self.get("/v5/market/kline", {"category": "linear", "symbol": symbol,
                "interval": INTERVALS[timeframe], "start": start_ms, "end": cursor, "limit": 1000})
            raw = result.get("list", [])
            if not raw:
                break
            batch = []
            for item in raw:
                ts = int(item[0])
                if ts in seen or ts < start_ms or ts > end:
                    continue
                seen.add(ts)
                batch.append(Candle(datetime.fromtimestamp(ts / 1000, timezone.utc), D(item[2]), D(item[3]),
                                    D(item[1]), D(item[4]), D(item[5])))
            if batch:
                yield sorted(batch, key=lambda x: x.start)
            earliest = min(int(c[0]) for c in raw)
            if earliest >= cursor:
                break
            cursor = earliest - 1
            # A short page is not proof of exhausted exchange history.
            # Continue until the API returns no older candles or reaches start_ms.
            await asyncio.sleep(.12)

    async def close(self):
        await self.client.aclose()
