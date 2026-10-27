"""Source-owned immutable minute records. Digests are integrity, never authentication."""
import copy
import hashlib
import json
import math
import re
import time
import uuid

SHA = re.compile(r"^[0-9a-f]{40}$")

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def producer(identity, revision, endpoint):
    # Market identity derives from the subscribed endpoint, never caller inference.
    return {"identity": identity, "source_revision": revision,
            "epoch": str(uuid.uuid4()),
            "market_type": "linear" if endpoint == "wss://stream.bybit.com/v5/public/linear" else None,
            "representation": "live_trade_aggregate"}


def data_integrity(row):
    try:
        def number(v):return type(v) in (int,float) and math.isfinite(v)
        values=[row[k] for k in ('open','high','low','close','buy_volume','sell_volume','delta','poc_price')]
        if not all(number(v) for v in values):return False
        if not 0 < row['low'] <= min(row['open'],row['close']) <= max(row['open'],row['close']) <= row['high']:return False
        if type(row['trade_count']) is not int or row['trade_count']<=0:return False
        levels=row['levels']
        if not isinstance(levels,list) or not 0<len(levels)<=10000:return False
        prices=set();buy=sell=trades=0
        for x in levels:
            if not all(number(x[k]) for k in ('price','buy_volume','sell_volume','delta','volume')):return False
            if x['price'] in prices or not row['low']<=x['price']<=row['high']:return False
            prices.add(x['price'])
            if min(x['buy_volume'],x['sell_volume'])<0:return False
            if not math.isclose(x['delta'],x['buy_volume']-x['sell_volume'],abs_tol=1e-9) or not math.isclose(x['volume'],x['buy_volume']+x['sell_volume'],abs_tol=1e-9):return False
            if any(type(x[k]) is not int or x[k]<0 for k in ('buy_count','sell_count')):return False
            buy+=x['buy_volume'];sell+=x['sell_volume'];trades+=x['buy_count']+x['sell_count']
        return (trades==row['trade_count'] and row['poc_price'] in prices and
                math.isclose(buy,row['buy_volume'],abs_tol=1e-9) and math.isclose(sell,row['sell_volume'],abs_tol=1e-9) and
                math.isclose(buy-sell,row['delta'],abs_tol=1e-9) and len(canonical(row))<=1048576)
    except (KeyError,TypeError,ValueError,OverflowError):return False

def minute_record(row, ingestion_ms, authenticated_identity=None):
    row = copy.deepcopy(row)
    source = row.get("source_provenance", {})
    valid = (isinstance(source, dict) and isinstance(source.get("identity"), str)
             and bool(source["identity"]) and SHA.fullmatch(str(source.get("source_revision", "")))
             and source.get("market_type") == "linear"
             and source.get("representation") == "live_trade_aggregate")
    try:
        uuid.UUID(source.get("epoch", ""))
    except (ValueError, TypeError, AttributeError):
        valid = False
    if authenticated_identity is not None and source.get("identity") != authenticated_identity:
        valid = False
    event_start, event_end = row.get("source_event_start_ms"), row.get("source_event_end_ms")
    start = row.get("start_ms")
    valid = bool(valid and type(start) is int and type(event_start) is int and type(event_end) is int
                 and start >= 0 and start % 60000 == 0 and start <= event_start <= event_end < start + 60000
                 and type(ingestion_ms) is int and event_end <= ingestion_ms)
    integral = data_integrity(row)
    valid = valid and integral
    record = {"api_version": {"major": 1, "minor": 1}, "producer": "bybit-cluster-grid",
              "source": source, "symbol": row["symbol"], "timeframe": "1m",
              "start_ms": start, "end_ms": start + 59999,
              "source_event_start_ms": event_start, "source_event_end_ms": event_end,
              "ingestion_ms": ingestion_ms, "representation": "historical_aggregate",
              "execution_authority": False, "quality_status": row.get("quality_status", "UNKNOWN") if integral else "INVALID",
              "quality_reasons": row.get("quality_reasons", []),
              "coverage": {"expected_minutes": 1, "observed_minutes": 1, "missing_minutes": 0,
                           "exchange_completeness_attested": False},
              "source_identity_verified": authenticated_identity is not None and valid,
              "status": "PARTIAL" if valid else "UNAVAILABLE",
              "reason": "EXCHANGE_COMPLETENESS_UNATTESTED" if valid else "SOURCE_PROVENANCE_UNAVAILABLE",
              "candle": {k: row[k] for k in ("open", "high", "low", "close", "buy_volume", "sell_volume", "delta", "trade_count", "poc_price")},
              "levels": row["levels"]}
    # Observing trades cannot attest exchange-wide completeness; never synthesize AVAILABLE.
    record["dataset_fingerprint"] = digest(record)
    return record

async def persist_minute(conn, row, authenticated_identity=None):
    record = minute_record(row, int(time.time()*1000), authenticated_identity)
    await conn.execute("""INSERT INTO provenance_minutes(fingerprint,content_id,symbol,start_ms,record)
        VALUES($1,$2,$3,$4,$5::jsonb) ON CONFLICT DO NOTHING""",
        record["dataset_fingerprint"], digest(row), row["symbol"], row["start_ms"], canonical(record).decode())
    return record
