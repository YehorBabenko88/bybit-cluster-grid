"""Bybit V5 instrument metadata: exchange-provided tick size and listing timestamp."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class Instrument:
    symbol: str
    tick_size: Decimal
    launch_ms: int
    status: str

def parse_instrument(row):
    tick = Decimal(str(row["priceFilter"]["tickSize"]))
    launch = int(row["launchTime"])
    if tick <= 0 or launch <= 0:
        raise ValueError("invalid instrument metadata")
    return Instrument(str(row["symbol"]), tick, launch, str(row["status"]))

async def instruments(exchange):
    """Paginate V5 linear instruments-info; reject malformed metadata."""
    result = {}
    cursor = None
    seen = set()
    while True:
        params = {"category":"linear", "limit":1000}
        if cursor:
            params["cursor"] = cursor
        page = await exchange.get("/v5/market/instruments-info", params)
        for row in page.get("list", []):
            instrument = parse_instrument(row)
            if instrument.symbol.endswith("USDT") and instrument.status == "Trading":
                result[instrument.symbol] = instrument
        following = page.get("nextPageCursor") or ""
        if not following:
            break
        if following in seen:
            raise ValueError("repeated instruments pagination cursor")
        seen.add(following)
        cursor = following
    return result
